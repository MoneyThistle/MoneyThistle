"""Moving accounts from one environment to another (for example from Personal to a new
Household environment that two people own).

Each environment is its own money file, so a move copies everything that belongs to the
accounts into the other file and then removes it from the first:

  * the accounts (details included) and every transaction, with splits kept together,
    cleared/reconciled marks, bank ids, paystubs and the HSA tax-year choices;
  * categories and payees they use (created in the other environment when missing);
  * their scheduled bills and deposits with their history, and loan details;
  * transfers between moved accounts stay transfers; a transfer to an account that stays
    behind becomes a transfer between environments, through a connection made for it
    (the person moving owns both sides, so it's approved at once). Scheduled transfers
    to or from an account that stays behind become scheduled transfers between
    environments the same way;
  * connections and shares follow the account. A share into the environment it moves to
    ends (the account now lives there), and a connection to an account there turns back
    into plain transfers.

A loan moves only together with the account its payments come from (a loan payment is
one split entry in that account).
"""

import json

from .store import ApiError

# Columns copied as they are; ids that point at other rows are mapped separately.
TX_SKIP = {"id", "account_id", "category_id", "transfer_id", "group_id", "xlink_id", "xtx_id"}


def _cols(st, table):
    return [r[1] for r in st.db.execute(f"PRAGMA table_info({table})")]


def _insert(st, table, row):
    keys = list(row)
    cur = st.db.execute(f"INSERT INTO {table}({','.join(keys)}) VALUES({','.join('?' * len(keys))})",
                        [row[k] for k in keys])
    return cur.lastrowid


def plan(system, uid, src, dst, account_ids):
    """What a move would do, changing nothing (shown before the person confirms)."""
    src, dst = int(src), int(dst)
    if src == dst:
        raise ApiError("Choose another environment to move to")
    system.require(uid, src, "owner")
    system.require(uid, dst, "owner")
    ids = {int(a) for a in account_ids or []}
    if not ids:
        raise ApiError("Choose the accounts to move")
    s = system.store(src)
    accs = {a["id"]: a for a in s.accounts()}
    missing = ids - set(accs)
    if missing:
        raise ApiError("Some of those accounts aren't in this environment")
    # A loan needs the account its payments come from.
    for loan in s.q("SELECT * FROM loans"):
        if loan["account_id"] in ids and loan["pay_from_account_id"] and loan["pay_from_account_id"] not in ids:
            raise ApiError(f"\"{accs[loan['account_id']]['name']}\" is a loan paid from "
                           f"\"{accs.get(loan['pay_from_account_id'], {}).get('name', '?')}\": move them together")
        if loan["account_id"] not in ids and loan["pay_from_account_id"] in ids:
            raise ApiError(f"\"{accs[loan['pay_from_account_id']]['name']}\" pays the loan "
                           f"\"{accs[loan['account_id']]['name']}\": move them together")
    marks = ",".join("?" * len(ids))
    tx = s.q(f"SELECT t.id, t.account_id, p.account_id AS other FROM transactions t "
             f"LEFT JOIN transactions p ON p.id=t.transfer_id WHERE t.account_id IN ({marks})", list(ids))
    staying = {}
    for t in tx:
        if t["other"] and t["other"] not in ids:
            k = (accs[t["account_id"]]["name"], accs[t["other"]]["name"])
            staying[k] = staying.get(k, 0) + 1
    bills = s.q(f"SELECT * FROM bills WHERE account_id IN ({marks}) OR to_account_id IN ({marks}) "
                f"OR loan_account_id IN ({marks}) OR card_account_id IN ({marks})", list(ids) * 4)
    shares = system.q("SELECT * FROM shares WHERE env_a=? AND status IN ('pending','active')", (src,))
    return {"accounts": [{"id": i, "name": accs[i]["name"], "type": accs[i]["type"],
                          "transactions": sum(1 for t in tx if t["account_id"] == i)} for i in sorted(ids)],
            "to_env_name": system.env_name(dst),
            "transfers_to_staying": [{"moving": k[0], "staying": k[1], "count": n} for k, n in sorted(staying.items())],
            "bills": len(bills),
            "shares_ending": sum(1 for x in shares if x["account_a"] in ids and x["env_b"] == dst),
            "shares_following": sum(1 for x in shares if x["account_a"] in ids and x["env_b"] != dst)}


def move(system, uid, src, dst, account_ids):
    info = plan(system, uid, src, dst, account_ids)
    src, dst = int(src), int(dst)
    ids = {a["id"] for a in info["accounts"]}
    s, d = system.store(src), system.store(dst)
    links_made = 0
    with system.lock, s.lock, d.lock:
        # ----- categories: by full name; missing ones are created there --------------------
        dcats = {c["full_name"].lower(): c["id"] for c in d.categories()}
        scats = {c["id"]: c for c in s.categories()}
        cmap = {}

        def cat(cid):
            if not cid or cid not in scats:
                return None
            if cid in cmap:
                return cmap[cid]
            c = scats[cid]
            hit = dcats.get(c["full_name"].lower())
            if not hit:
                pid = cat(c["parent_id"]) if c["parent_id"] else None
                hit = d.db.execute("INSERT INTO categories(name,parent_id,kind,tax_related,in_budget) VALUES(?,?,?,?,?)",
                                   (c["name"], pid, c["kind"], c["tax_related"], c["in_budget"])).lastrowid
                dcats[c["full_name"].lower()] = hit
            cmap[cid] = hit
            return hit

        # ----- accounts ------------------------------------------------------------------------
        amap, taken = {}, {a["name"].lower() for a in d.accounts()}
        for a in s.q(f"SELECT * FROM accounts WHERE id IN ({','.join('?' * len(ids))})", list(ids)):
            row = {k: a[k] for k in _cols(s, "accounts") if k != "id" and k in _cols(d, "accounts")}
            name, n = a["name"], 2
            while name.lower() in taken:
                name, n = f"{a['name']} ({n})", n + 1
            taken.add(name.lower())
            row["name"] = name
            amap[a["id"]] = _insert(d, "accounts", row)

        def link(moved_old, staying_id):
            """An active connection between a moved account (in dst) and one left in src."""
            nonlocal links_made
            new = amap[moved_old]
            l = system.q1("SELECT id FROM links WHERE status='active' AND ((env_a=? AND account_a=? AND env_b=? AND account_b=?) "
                          "OR (env_a=? AND account_a=? AND env_b=? AND account_b=?))",
                          (dst, new, src, staying_id, src, staying_id, dst, new))
            if l:
                return l["id"]
            links_made += 1
            return system.db.execute(
                "INSERT INTO links(env_a,account_a,env_b,account_b,status,created_by,created,approved_a_by,approved_b_by,"
                "approved,note) VALUES(?,?,?,?,'active',?,datetime('now'),?,?,datetime('now'),?)",
                (dst, new, src, staying_id, uid, uid, uid, "made when the account moved")).lastrowid

        # ----- transactions ----------------------------------------------------------------
        marks = ",".join("?" * len(ids))
        rows = s.q(f"SELECT * FROM transactions WHERE account_id IN ({marks}) ORDER BY id", list(ids))
        tcols = [c for c in _cols(s, "transactions") if c not in TX_SKIP and c in _cols(d, "transactions")]
        gbase = d.q1("SELECT COALESCE(MAX(group_id),0) g FROM transactions")["g"]
        gmap, tmap = {}, {}
        for t in rows:
            row = {k: t[k] for k in tcols}
            row["account_id"] = amap[t["account_id"]]
            row["category_id"] = cat(t["category_id"])
            if t["group_id"]:
                if t["group_id"] not in gmap:
                    gbase += 1
                    gmap[t["group_id"]] = gbase
                row["group_id"] = gmap[t["group_id"]]
            tmap[t["id"]] = _insert(d, "transactions", row)
        moved_ids = set(tmap)
        for t in rows:
            new = tmap[t["id"]]
            if t["transfer_id"]:
                if t["transfer_id"] in moved_ids:
                    d.db.execute("UPDATE transactions SET transfer_id=? WHERE id=?", (tmap[t["transfer_id"]], new))
                else:
                    # The other side stays behind: a transfer between environments from now on.
                    p = s.q1("SELECT id, account_id FROM transactions WHERE id=?", (t["transfer_id"],))
                    if p:
                        lid = link(t["account_id"], p["account_id"])
                        d.db.execute("UPDATE transactions SET xlink_id=?, xtx_id=? WHERE id=?", (lid, p["id"], new))
                        s.db.execute("UPDATE transactions SET transfer_id=NULL, xlink_id=?, xtx_id=? WHERE id=?",
                                     (lid, new, p["id"]))
            elif t["xlink_id"]:
                l = system.q1("SELECT * FROM links WHERE id=?", (t["xlink_id"],))
                if not l:
                    continue
                other_env = l["env_b"] if (l["env_a"], l["account_a"]) == (src, t["account_id"]) else l["env_a"]
                if other_env == dst:
                    # Its other side lives where it's moving: a plain transfer there.
                    p = d.q1("SELECT id FROM transactions WHERE id=? AND xlink_id=?", (t["xtx_id"], t["xlink_id"]))
                    if p:
                        d.db.execute("UPDATE transactions SET transfer_id=?, xlink_id=NULL, xtx_id=NULL, category_id=NULL "
                                     "WHERE id=?", (new, p["id"]))
                        d.db.execute("UPDATE transactions SET transfer_id=? WHERE id=?", (p["id"], new))
                else:
                    d.db.execute("UPDATE transactions SET xlink_id=?, xtx_id=? WHERE id=?", (t["xlink_id"], t["xtx_id"], new))
                    o = system.store(other_env)
                    with o.lock:
                        o.db.execute("UPDATE transactions SET xtx_id=? WHERE id=? AND xlink_id=?",
                                     (new, t["xtx_id"], t["xlink_id"]))
                        o.db.commit()

        # ----- details that point at other rows ------------------------------------------
        for old, new in amap.items():
            det = json.loads(d.q1("SELECT details FROM accounts WHERE id=?", (new,))["details"] or "{}")
            if det.get("purpose_category_id"):
                det["purpose_category_id"] = cat(det["purpose_category_id"])
            if det.get("pay_from_account_id"):
                if det["pay_from_account_id"] in amap:
                    det["pay_from_account_id"] = amap[det["pay_from_account_id"]]
                else:
                    # Paid from an account left behind: the schedule keeps the payment as a
                    # transfer between environments (below); the card no longer manages it.
                    det.pop("pay_from_account_id", None)
                    det["auto_pay"] = False
            ls = det.get("last_statement")
            if isinstance(ls, dict) and ls.get("tid"):
                ls["tid"] = tmap.get(ls["tid"])
            d.db.execute("UPDATE accounts SET details=? WHERE id=?", (json.dumps(det), new))

        # ----- loans -----------------------------------------------------------------------
        for loan in s.q(f"SELECT * FROM loans WHERE account_id IN ({marks})", list(ids)):
            row = {k: loan[k] for k in _cols(s, "loans") if k in _cols(d, "loans")}
            row["account_id"] = amap[loan["account_id"]]
            for k in ("pay_from_account_id", "escrow_account_id"):
                if row.get(k):
                    row[k] = amap.get(row[k])
            for k in ("interest_category_id", "escrow_category_id"):
                if row.get(k):
                    row[k] = cat(row[k])
            _insert(d, "loans", row)

        # ----- scheduled items -------------------------------------------------------------
        bcols = [c for c in _cols(s, "bills") if c != "id" and c in _cols(d, "bills")]
        move_bills, cross_here, bmap = [], [], {}
        for b in s.q("SELECT * FROM bills"):
            acct_in, to_in = b["account_id"] in ids, (b["to_account_id"] or 0) in ids
            touches = acct_in or to_in or (b["loan_account_id"] or 0) in ids or (b["card_account_id"] or 0) in ids
            if not touches:
                continue
            if acct_in and (not b["to_account_id"] or to_in):
                move_bills.append((b, None))
            elif acct_in:
                move_bills.append((b, b["to_account_id"]))   # moved -> staying: a transfer between environments
            elif to_in:
                cross_here.append(b)                          # staying -> moved: stays here, across environments
            elif (b["card_account_id"] or 0) in ids:
                # A card's payment from an account staying here, already a transfer elsewhere:
                # it's an ordinary scheduled item from now on.
                s.db.execute("UPDATE bills SET card_account_id=NULL WHERE id=?", (b["id"],))
        for b, staying in move_bills:
            row = {k: b[k] for k in bcols}
            row["account_id"] = amap.get(b["account_id"], b["account_id"])
            for k in ("to_account_id", "loan_account_id", "card_account_id"):
                if row.get(k):
                    row[k] = amap.get(row[k])
            row["category_id"] = cat(b["category_id"])
            if staying:
                lid = link(b["account_id"], staying)
                row.update(to_account_id=None, card_account_id=None, x_link_id=lid, x_dir="out",
                           x_label=f"{system.account_name(src, staying)} ({system.env_name(src)})")
            nb = _insert(d, "bills", row)
            bmap[b["id"]] = nb
            for h in s.q("SELECT * FROM bill_history WHERE bill_id=?", (b["id"],)):
                d.db.execute("INSERT INTO bill_history(bill_id,date,amount,transaction_id) VALUES(?,?,?,?)",
                             (nb, h["date"], h["amount"], tmap.get(h["transaction_id"])))
        for b in cross_here:
            lid = link(b["to_account_id"], b["account_id"])
            s.db.execute("UPDATE bills SET to_account_id=NULL, card_account_id=NULL, x_link_id=?, x_dir='out', x_label=? "
                         "WHERE id=?", (lid, f"{d.q1('SELECT name FROM accounts WHERE id=?', (amap[b['to_account_id']],))['name']} "
                                             f"({system.env_name(dst)})", b["id"]))
        # Paystubs (their lines name categories and accounts).
        for p in s.q(f"SELECT * FROM paystubs WHERE account_id IN ({marks})", list(ids)):
            body = json.loads(p["lines"] or "{}")
            for ln in body.get("lines", []):
                ln["category_id"] = cat(ln.get("category_id"))
                if ln.get("account_id"):
                    ln["account_id"] = amap.get(ln["account_id"])   # an account left behind: chosen again when edited
            d.db.execute("INSERT INTO paystubs(group_id,account_id,employer,date,gross,net,net_category_id,lines,bill_id) "
                         "VALUES(?,?,?,?,?,?,?,?,?)",
                         (gmap.get(p["group_id"]), amap[p["account_id"]], p["employer"], p["date"], p["gross"], p["net"],
                          cat(p["net_category_id"]), json.dumps(body), bmap.get(p["bill_id"])))
        # Payees they use, with their usual category.
        for p in s.q(f"SELECT DISTINCT y.* FROM payees y JOIN transactions t ON t.payee=y.name WHERE t.account_id IN ({marks})",
                     list(ids)):
            d.db.execute("INSERT OR IGNORE INTO payees(name,category_id,last_amount,used) VALUES(?,?,?,?)",
                         (p["name"], cat(p["category_id"]), p["last_amount"], p["used"]))

        # ----- connections and shares follow the account ------------------------------------
        for old, new in amap.items():
            for l in system.q("SELECT * FROM links WHERE status IN ('pending','active') AND "
                              "((env_a=? AND account_a=?) OR (env_b=? AND account_b=?))", (src, old, src, old)):
                side_a = (l["env_a"], l["account_a"]) == (src, old)
                other_env = l["env_b"] if side_a else l["env_a"]
                if other_env == dst:
                    system.db.execute("UPDATE links SET status='ended', ended=datetime('now'), ended_by=? WHERE id=?",
                                      (uid, l["id"]))
                    continue
                if side_a:
                    system.db.execute("UPDATE links SET env_a=?, account_a=? WHERE id=?", (dst, new, l["id"]))
                else:
                    system.db.execute("UPDATE links SET env_b=?, account_b=? WHERE id=?", (dst, new, l["id"]))
                # Its scheduled transfers in the other environment keep working; ours moved with the bills.
            for sh in system.q("SELECT * FROM shares WHERE env_a=? AND account_a=? AND status IN ('pending','active')",
                               (src, old)):
                if sh["env_b"] == dst:
                    system.db.execute("UPDATE shares SET status='ended', ended=datetime('now'), ended_by=?, "
                                      "note=? WHERE id=?", (uid, "the account moved into this environment", sh["id"]))
                else:
                    system.db.execute("UPDATE shares SET env_a=?, account_a=? WHERE id=?", (dst, new, sh["id"]))
        d.db.commit()

        # Receipts go with their entries (the files themselves are shared by every environment).
        # So do the papers kept with the accounts themselves.
        for a in s.q("SELECT * FROM attachments WHERE transaction_id IS NOT NULL OR account_id IS NOT NULL"):
            if a["transaction_id"] in tmap or (not a["transaction_id"] and a["account_id"] in amap):
                d.db.execute("INSERT INTO attachments(transaction_id,account_id,name,mime,size,sha256,added,added_by,"
                             "note,doc_date) VALUES(?,?,?,?,?,?,?,?,?,?)",
                             (tmap.get(a["transaction_id"]), None if a["transaction_id"] else amap[a["account_id"]],
                              a["name"], a["mime"], a["size"], a["sha256"], a["added"], a["added_by"],
                              a["note"], a["doc_date"]))
                s.db.execute("DELETE FROM attachments WHERE id=?", (a["id"],))
        d.db.commit()

        # ----- and out of the old environment ------------------------------------------------
        old_bills = [b["id"] for b, _ in move_bills]
        if old_bills:
            bm = ",".join("?" * len(old_bills))
            s.db.execute(f"DELETE FROM bill_history WHERE bill_id IN ({bm})", old_bills)
            s.db.execute(f"DELETE FROM bills WHERE id IN ({bm})", old_bills)
        s.db.execute(f"DELETE FROM paystubs WHERE account_id IN ({marks})", list(ids))
        s.db.execute(f"DELETE FROM loans WHERE account_id IN ({marks})", list(ids))
        s.db.execute(f"DELETE FROM transactions WHERE account_id IN ({marks})", list(ids))
        s.db.execute(f"DELETE FROM accounts WHERE id IN ({marks})", list(ids))
        s.db.commit()
        system.db.commit()
        s.changed()
        d.changed()
        system.changed()
    from . import history
    for a in info["accounts"]:
        history.record(system, src, "account", None, "change", None, None,
                       f"Moved account {a['name']} ({a['transactions']} entries) to {info['to_env_name']}")
        history.record(system, dst, "account", amap.get(a["id"]), "change", None, None,
                       f"Moved account {a['name']} ({a['transactions']} entries) here from {system.env_name(src)}")
    return {"moved": [a["name"] for a in info["accounts"]], "to": info["to_env_name"],
            "connections_made": links_made, "transactions": len(tmap)}
