"""Paystubs: one paycheck recorded in full, not only what reached the bank.

A paystub is kept as one group of entries in the account the pay went into, like a
split loan payment:

  + each earning (gross pay, overtime, bonus...)       in an income category
  - each tax or deduction (federal tax, Medicare...)   in an expense category, or
  - money sent to another account of yours (401(k),     as a transfer to that account
    HSA through payroll...)
  - part of the take-home pay deposited straight into   as a transfer to that account
    another account ($250 to savings, the rest here)

so the group adds up to what was deposited into this account. The `paystubs` table keeps the lines as
typed (their labels and where each one goes) to edit the paystub later, to copy it for
the next paycheck, and for the year-end summary of gross vs net pay.

The category budget counts a paystub as one income of its net pay (in the net pay
category), so budgets made around take-home pay stay right; the reports show every
line, which is where the money went.
"""

import json

from .store import ApiError, about, parse_date, to_cents

# earn: gross pay, overtime...; deduct: a tax or deduction (or the remainder, "Other
# deductions": gross pay + additions - take-home pay - the itemized deductions); add: money
# added after taxes (an expense reimbursement), which take-home pay includes; split: part of
# the take-home pay deposited into another account (direct deposit split between accounts),
# the rest going into the paystub's own account.
SIDES = ("earn", "deduct", "add", "split")
SPLIT_LABEL = "Direct deposit"
OTHER_LABEL = "Other deductions"
OTHER_CATEGORY = "Paycheck Deductions"


def _other_category(store):
    """Where deductions that aren't itemized go: a "Paycheck Deductions" spending category,
    made the first time it's needed."""
    for c in store.categories():
        if c["name"].lower() == OTHER_CATEGORY.lower() and c["kind"] == "expense" and not c["parent_id"]:
            return c["id"]
    from .category_names import NAMES   # with its name in the other languages
    return store.save_category({"name": OTHER_CATEGORY, "kind": "expense", "names": NAMES.get(OTHER_CATEGORY, {})})


def is_other(ln):
    """The remainder line: marked so, or what older simple paystubs called it."""
    return bool(ln.get("other")) or ln.get("label", "").strip().lower() in ("taxes and deductions", "other deductions")


def _net_category(store, earn_cats):
    """Where the take-home pay counts in the category budget: "Wages & Salary : Net Pay"
    when it exists (the usual budget line for a paycheck), else the first earning's."""
    for c in store.categories():
        if c["name"].lower() == "net pay" and c["kind"] == "income":
            return c["id"]
    return earn_cats[0] if earn_cats else None


def _clean(store, data):
    aid = int(data.get("account_id") or 0)
    acc = store.q1("SELECT id, type FROM accounts WHERE id=?", (aid,))
    if not acc:
        raise ApiError("Choose the account the pay went into", field="account_id")
    with about("date"):
        date = parse_date(data.get("date"), "Pay date").isoformat()
    employer = (data.get("employer") or "").strip()
    if not employer:
        raise ApiError("Enter who paid you (the employer)", field="employer")
    memo = (data.get("memo") or "").strip()
    raw = data.get("lines")
    if not isinstance(raw, list) or not raw:
        raise ApiError("A paystub needs at least the gross pay")
    cats = {c["id"]: c for c in store.categories()}
    lines = []
    for i, ln in enumerate(raw):
        if not isinstance(ln, dict):
            raise ApiError("Each paystub line must be an object")
        side = ln.get("side")
        if side not in SIDES:
            raise ApiError("Each line is an earning or a deduction")
        label = (ln.get("label") or "").strip()[:80]
        with about(f"line_{i}_amount"):
            amount = abs(to_cents(ln.get("amount"), f"Amount of {label or 'a line'}"))
        if not amount:
            continue   # empty lines (a blank row, a tax that was 0 this time) are left out
        cid = int(ln.get("category_id") or 0) or None
        to = int(ln.get("account_id") or 0) or None
        if side == "deduct" and ln.get("other"):
            lines.append({"side": "deduct", "label": OTHER_LABEL, "amount": amount, "category_id": _other_category(store),
                          "account_id": None, "other": True})
            continue
        if side == "split":
            # Part of the take-home pay, deposited into another of my accounts.
            if not to or to == aid:
                raise ApiError(f"Choose the other account {label or 'that part'} went into", field=f"line_{i}_to")
            if not store.q1("SELECT 1 FROM accounts WHERE id=?", (to,)):
                raise ApiError("That account doesn't exist", field=f"line_{i}_to")
            lines.append({"side": "split", "label": label or SPLIT_LABEL, "amount": amount, "category_id": None,
                          "account_id": to})
            continue
        if side == "add":
            # Added after taxes: an income category (a reimbursement), or none.
            if cid and (cid not in cats or cats[cid]["kind"] != "income"):
                raise ApiError(f"Choose an income category for {label or 'each addition'}", field=f"line_{i}_to")
            lines.append({"side": "add", "label": label or "Addition", "amount": amount, "category_id": cid, "account_id": None})
            continue
        if side == "earn":
            if not cid or cid not in cats or cats[cid]["kind"] != "income":
                raise ApiError(f"Choose an income category for {label or 'each earning'}", field=f"line_{i}_to")
            to = None
        else:
            if to:
                if to == aid:
                    raise ApiError(f"{label or 'A deduction'} can't go to the account the pay went into",
                                   field=f"line_{i}_to")
                if not store.q1("SELECT 1 FROM accounts WHERE id=?", (to,)):
                    raise ApiError("That account doesn't exist", field=f"line_{i}_to")
                cid = None
            elif not cid or cid not in cats:
                raise ApiError(f"Choose where {label or 'each deduction'} goes: a category or one of your accounts",
                               field=f"line_{i}_to")
        lines.append({"side": side, "label": label or (cats[cid]["name"] if cid else "Deduction"),
                      "amount": amount, "category_id": cid, "account_id": to})
    gross = sum(ln["amount"] for ln in lines if ln["side"] == "earn")
    if not gross:
        raise ApiError("Enter the gross pay")
    net = gross - sum(ln["amount"] for ln in lines if ln["side"] == "deduct") \
        + sum(ln["amount"] for ln in lines if ln["side"] == "add")
    if net < 0:
        raise ApiError("The deductions come to more than the earnings")
    split = sum(ln["amount"] for ln in lines if ln["side"] == "split")
    if split > net:
        raise ApiError("The parts deposited into other accounts come to more than the take-home pay")
    return {"account_id": aid, "date": date, "employer": employer, "memo": memo, "lines": lines,
            "gross": gross, "net": net, "deposit": net - split,
            "net_category_id": _net_category(store, [ln["category_id"] for ln in lines if ln["side"] == "earn"])}


def _write_lines(store, p, gid, status=""):
    """The entries of one paystub (all in its account, one group)."""
    ids = []
    for ln in p["lines"]:
        tx = {"account_id": p["account_id"], "date": p["date"], "payee": p["employer"],
              "memo": ln["label"] + (f" · {p['memo']}" if p["memo"] else ""),
              "amount_cents": -ln["amount"] if ln["side"] in ("deduct", "split") else ln["amount"], "status": status}
        if ln["account_id"]:
            tx["transfer_account_id"] = ln["account_id"]
        else:
            tx["category_id"] = ln["category_id"]
        ids.append(store.save_transaction(tx))
    marks = ",".join("?" * len(ids))
    store.db.execute(f"UPDATE transactions SET group_id=? WHERE id IN ({marks})", [gid] + ids)
    # Typing the employer in the register later suggests what reached this account.
    store.db.execute("UPDATE payees SET last_amount=?, category_id=COALESCE(?, category_id) WHERE name=?",
                     (p["deposit"], p["net_category_id"], p["employer"]))
    return ids


def _split_history(store, p, ids, bill_id, old_by_acct, new_entry):
    """A scheduled paycheck into more than one account: each other account's own schedule
    keeps what it got (for its average). An entry it already had (the take-home-only one this
    paystub replaces, or the paystub's earlier version) now points at the paystub's."""
    for ln, tid in zip(p["lines"], ids):
        if ln["side"] != "split":
            continue
        partner = store.q1("SELECT transfer_id FROM transactions WHERE id=?", (tid,))["transfer_id"]
        old = old_by_acct.get(ln["account_id"])
        if old and store.q1("SELECT 1 FROM bill_history WHERE transaction_id=?", (old,)):
            store.db.execute("UPDATE bill_history SET transaction_id=?, amount=?, date=? WHERE transaction_id=?",
                             (partner, ln["amount"], p["date"], old))
        elif bill_id and new_entry:
            child = store.q1("SELECT id FROM bills WHERE split_of=? AND account_id=?", (bill_id, ln["account_id"]))
            if child:
                store.record_split(child["id"], p["date"], ln["amount"], partner)


def save(store, data, gid=None):
    """Record a paystub (or replace one, keeping its group). `bill_id` (new ones only):
    the scheduled paycheck it is, which then moves to its next date. `replace_tx`: a
    paycheck recorded with only its take-home pay, which this paystub now details (it
    takes that entry's place, its status and its place in the schedule's history)."""
    from . import attachments
    p = _clean(store, data)
    with store.lock:
        status, bill_id, old_first, old_ids = "", None, None, []
        if data.get("replace_tx") and not gid:
            t = store.q1("SELECT * FROM transactions WHERE id=? AND paycheck IS NOT NULL", (int(data["replace_tx"]),))
            if not t:
                raise ApiError("That paycheck isn't there any more", 404)
            bh = store.q1("SELECT bill_id FROM bill_history WHERE transaction_id=?", (t["id"],))
            gid = store.q1("SELECT COALESCE(MAX(group_id),0)+1 AS g FROM transactions")["g"]
            status, old_first, bill_id = t["status"], t["id"], (bh["bill_id"] if bh else None)
            # The same paycheck's deposits into other accounts (recorded with it as take-home
            # only) are now the paystub's split lines: they give way to them.
            old_by_acct = {}
            for ln in p["lines"]:
                if ln["side"] == "split":
                    dup = store.q1("SELECT id FROM transactions WHERE account_id=? AND date=? AND payee=? COLLATE NOCASE "
                                   "AND group_id IS NULL AND transfer_id IS NULL AND paycheck IS NULL "
                                   "AND memo LIKE ? ORDER BY id LIMIT 1",
                                   (ln["account_id"], t["date"], t["payee"], SPLIT_LABEL + "%"))
                    if dup:
                        old_by_acct[ln["account_id"]] = dup["id"]
                        store.delete_transaction(dup["id"])
            ids = _write_lines(store, p, gid, status)
            _split_history(store, p, ids, bill_id, old_by_acct, True)
            store.delete_transaction(t["id"])
            attachments.relink(store, t["id"], ids[0])   # its receipts and papers stay with the paycheck
            store.db.execute("INSERT INTO paystubs(group_id,account_id,employer,date,gross,net,net_category_id,lines,bill_id) "
                             "VALUES(?,?,?,?,?,?,?,?,?)",
                             (gid, p["account_id"], p["employer"], p["date"], p["gross"], p["net"], p["net_category_id"],
                              json.dumps({"memo": p["memo"], "lines": p["lines"]}), bill_id))
            # The schedule's history (averages) now points at the paystub, once.
            store.db.execute("UPDATE bill_history SET transaction_id=?, amount=?, date=? WHERE transaction_id=?",
                             (ids[0], p["deposit"], p["date"], old_first))
            store.db.commit()
            store.changed()
            return {"group_id": gid, "ids": ids, "gross": p["gross"], "net": p["net"], "deposit": p["deposit"]}
        if gid:
            old = store.q1("SELECT * FROM paystubs WHERE group_id=?", (gid,))
            if not old:
                raise ApiError("No such paystub", 404)
            bill_id = old["bill_id"]
            first = store.q1("SELECT id, status FROM transactions WHERE group_id=? ORDER BY id LIMIT 1", (gid,))
            if first:
                status, old_first = first["status"], first["id"]
            old_ids = [r["id"] for r in store.q("SELECT id FROM transactions WHERE group_id=?", (gid,))]
            old_by_acct = {r["account_id"]: r["id"] for r in store.q(
                "SELECT q.id, q.account_id FROM transactions t JOIN transactions q ON q.id=t.transfer_id "
                "WHERE t.group_id=?", (gid,))}
            for oid in old_ids:
                store.delete_transaction(oid)
        else:
            gid = store.q1("SELECT COALESCE(MAX(group_id),0)+1 AS g FROM transactions")["g"]
            b = store.q1("SELECT * FROM bills WHERE id=?", (int(data.get("bill_id") or 0),))
            bill_id = b["id"] if b else None
        ids = _write_lines(store, p, gid, status)
        _split_history(store, p, ids, bill_id, old_by_acct if old_ids else {}, not old_ids)
        # An edited paystub's files move to its new take-home entry.
        for oid in old_ids:
            attachments.relink(store, oid, ids[0])
        store.db.execute("INSERT INTO paystubs(group_id,account_id,employer,date,gross,net,net_category_id,lines,bill_id) "
                         "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(group_id) DO UPDATE SET account_id=excluded.account_id,"
                         "employer=excluded.employer,date=excluded.date,gross=excluded.gross,net=excluded.net,"
                         "net_category_id=excluded.net_category_id,lines=excluded.lines,bill_id=excluded.bill_id",
                         (gid, p["account_id"], p["employer"], p["date"], p["gross"], p["net"], p["net_category_id"],
                          json.dumps({"memo": p["memo"], "lines": p["lines"]}), bill_id))
        # A scheduled paycheck counts once, at what reached its account (the take-home pay, less
        # any part deposited elsewhere), through the paystub's first entry.
        if old_first:
            store.db.execute("UPDATE bill_history SET transaction_id=?, amount=?, date=? WHERE transaction_id=?",
                             (ids[0], p["deposit"], p["date"], old_first))
        elif bill_id:
            store.db.execute("INSERT INTO bill_history(bill_id,date,amount,transaction_id) VALUES(?,?,?,?)",
                             (bill_id, p["date"], p["deposit"], ids[0]))
            store._advance_bill(b)
        store.db.commit()
        store.changed()
    return {"group_id": gid, "ids": ids, "gross": p["gross"], "net": p["net"], "deposit": p["deposit"]}


def deposit_of(net, lines):
    """What reached a paystub's own account: its take-home pay less the parts deposited into
    other accounts."""
    return net - sum(ln["amount"] for ln in lines if ln.get("side") == "split")


def get(store, gid):
    r = store.q1("SELECT * FROM paystubs WHERE group_id=?", (gid,))
    if not r:
        raise ApiError("No such paystub", 404)
    body = json.loads(r["lines"] or "{}")
    out = {"group_id": gid, "account_id": r["account_id"], "employer": r["employer"], "date": r["date"],
           "gross": r["gross"], "net": r["net"], "memo": body.get("memo", ""), "lines": body.get("lines", []),
           "bill_id": r["bill_id"], "complete": bool(r.get("complete"))}
    out["deposit"] = deposit_of(r["net"], out["lines"])
    out["flag"] = flags(store, employer=r["employer"]).get(("stub", gid))
    return out


# ----- paychecks: take-home only, or with a paystub, and what's usually filled in ---------
def save_net(store, data):
    """A paycheck with only its take-home pay (what reached the bank): one deposit, marked
    as a paycheck so its paystub details can be added later. `bill_id`: the scheduled
    paycheck it is (which moves to its next date)."""
    aid = int(data.get("account_id") or 0)
    if not store.q1("SELECT 1 FROM accounts WHERE id=?", (aid,)):
        raise ApiError("Choose the account the pay went into", field="account_id")
    employer = (data.get("employer") or "").strip()
    if not employer:
        raise ApiError("Enter who paid you (the employer)", field="employer")
    with about("date"):
        date = parse_date(data.get("date"), "Pay date").isoformat()
    with about("net"):
        net = abs(to_cents(data.get("net"), "Take-home pay"))
    if not net:
        raise ApiError("Enter the take-home pay: what reached your account", field="net")
    # Deposited into other accounts too (direct deposit split between accounts): each is a
    # deposit of take-home pay there, from the same employer.
    splits = []
    for n, sp in enumerate(data.get("splits") or []):
        field = f"line_{sp.get('line', n)}"
        with about(f"{field}_amount"):
            amount = abs(to_cents(sp.get("amount"), "Amount"))
        if not amount:
            continue
        to = int(sp.get("account_id") or 0)
        if not to or to == aid or not store.q1("SELECT 1 FROM accounts WHERE id=?", (to,)):
            raise ApiError("Choose the other account that amount went into", field=f"{field}_to")
        splits.append((to, amount))
    memo = (data.get("memo") or "").strip()
    with store.lock:
        b = store.q1("SELECT * FROM bills WHERE id=?", (int(data.get("bill_id") or 0),))
        tid = store.save_transaction({"account_id": aid, "date": date, "payee": employer,
                                      "memo": memo, "amount_cents": net,
                                      "category_id": _net_category(store, [])})
        store.db.execute("UPDATE transactions SET paycheck=1 WHERE id=?", (tid,))
        for to, amount in splits:
            sid = store.save_transaction({"account_id": to, "date": date, "payee": employer,
                                          "memo": SPLIT_LABEL + (f" · {memo}" if memo else ""), "amount_cents": amount,
                                          "category_id": _net_category(store, [])})
            child = store.q1("SELECT id FROM bills WHERE split_of=? AND account_id=?", (b["id"], to)) if b else None
            if child:
                store.record_split(child["id"], date, amount, sid)   # that account's own schedule
        if b:
            store.db.execute("INSERT INTO bill_history(bill_id,date,amount,transaction_id) VALUES(?,?,?,?)",
                             (b["id"], date, net, tid))
            store._advance_bill(b)
        store.db.commit()
        store.changed()
    return {"id": tid, "net": net + sum(a for _t, a in splits), "deposit": net}


def set_complete(store, kind, xid, complete=True):
    """"Complete as is": this paycheck has all the detail it will get; don't flag it."""
    with store.lock:
        if kind == "stub":
            n = store.db.execute("UPDATE paystubs SET complete=? WHERE group_id=?", (int(bool(complete)), int(xid))).rowcount
        else:
            n = store.db.execute("UPDATE transactions SET paycheck=? WHERE id=? AND paycheck IS NOT NULL",
                                 (2 if complete else 1, int(xid))).rowcount
        if not n:
            raise ApiError("No such paycheck", 404)
        store.db.commit()
        store.changed()
    return {"complete": bool(complete)}


LEVELS = {"net": 0, "gross": 1, "partial": 2, "detail": 3}
LEVEL_WORDS = {"net": "take-home only", "gross": "gross and take-home", "partial": "deductions itemized",
               "detail": "deductions itemized"}
ITEMIZING = ("partial", "detail")
USUAL_OF = 6   # what's usual for an employer: its latest this-many paychecks
SIMPLE_DEDUCTIONS = "taxes and deductions"   # the one line a simple paystub records


def paychecks(store, employer=None):
    """Every paycheck, newest first: paystubs, and entries recorded with only their
    take-home pay. Each says how much was filled in: net, gross (gross and take-home, the
    deductions as one amount) or detail (each tax and deduction)."""
    out = []
    args, where = [], ""
    if employer:
        where, args = " WHERE employer=? COLLATE NOCASE", [employer]
    for r in store.q("SELECT * FROM paystubs" + where, args):
        body = json.loads(r["lines"] or "{}")
        ded = [ln for ln in body.get("lines", []) if ln["side"] == "deduct"]
        itemized = [ln for ln in ded if not is_other(ln)]
        other = sum(ln["amount"] for ln in ded if is_other(ln))
        # gross: gross and take-home, nothing itemized; partial: some itemized, the rest in
        # Other deductions; detail: every deduction itemized (Other deductions $0).
        level = "gross" if not itemized else ("partial" if other else "detail")
        out.append({"kind": "stub", "id": r["group_id"], "employer": r["employer"], "date": r["date"],
                    "account_id": r["account_id"], "net": r["net"], "gross": r["gross"], "level": level,
                    "other": other, "labels": sorted({ln["label"].strip().lower() for ln in itemized}),
                    "complete": bool(r.get("complete"))})
    tw, ta = ("", []) if not employer else (" AND payee=? COLLATE NOCASE", [employer])
    for t in store.q("SELECT id, payee, date, account_id, amount, paycheck FROM transactions WHERE paycheck IS NOT NULL" + tw, ta):
        out.append({"kind": "tx", "id": t["id"], "employer": t["payee"], "date": t["date"], "account_id": t["account_id"],
                    "net": t["amount"], "gross": None, "level": "net", "other": 0, "labels": [],
                    "complete": t["paycheck"] == 2})
    out.sort(key=lambda p: (p["date"], p["id"]), reverse=True)
    return out


def usual(items):
    """What's usual for one employer's paychecks (newest first): the most common amount of
    detail among the latest ones (a tie goes to more detail), and for detailed ones the
    deductions that appear on most of them."""
    recent = items[:USUAL_OF]
    if not recent:
        return {"level": "net", "labels": []}
    counts = {}
    for p in recent:
        counts[p["level"]] = counts.get(p["level"], 0) + 1
    # Itemizing (some or all) counts as one habit: partly itemized paychecks are the ones to finish.
    if counts.get("partial") or counts.get("detail"):
        counts["detail"] = counts.pop("partial", 0) + counts.get("detail", 0)
    level = max(counts, key=lambda k: (counts[k], LEVELS[k]))
    labels = []
    if level == "detail":
        det = [p for p in recent if p["level"] in ITEMIZING]
        seen = {}
        for p in det:
            for lb in p["labels"]:
                seen[lb] = seen.get(lb, 0) + 1
        labels = sorted(lb for lb, n in seen.items() if n * 2 >= len(det) and n >= 2)
    return {"level": level, "labels": labels}


def _money(cents):
    return f"${cents / 100:,.2f}"


def flags(store, employer=None):
    """Paychecks with less filled in than is usual for their employer, and not marked
    complete as is:
      - usually itemized: any Other deductions left ("$220.00 not itemized"), and the usual
        deductions missing ("missing: Medicare");
      - usually gross and take-home: only a missing gross pay;
      - usually take-home only: nothing.
    {(kind, id): message}."""
    by = {}
    for p in paychecks(store, employer):
        by.setdefault(p["employer"].strip().lower(), []).append(p)
    out = {}
    for items in by.values():
        u = usual(items)
        for p in items:
            if p["complete"]:
                continue
            msgs = []
            if p["level"] == "net" and u["level"] != "net":
                msgs.append("missing gross pay" + (" and deductions" if u["level"] == "detail" else ""))
            elif u["level"] == "detail" and p["level"] != "net":
                if p["other"]:
                    msgs.append(f"{_money(p['other'])} not itemized")
                if p["level"] in ITEMIZING and u["labels"]:
                    missing = [lb for lb in u["labels"] if lb not in p["labels"]]
                    if missing:
                        msgs.append("missing: " + ", ".join(m.capitalize() for m in missing))
            if msgs:
                out[(p["kind"], p["id"])] = "; ".join(msgs)
    return out


def report(store, start=None, end=None, account_ids=None):
    """For the reports: each employer's paychecks in a period, what's usual for them, and
    the ones with something missing (each with where to find it)."""
    allp = paychecks(store)
    fl = flags(store)
    by = {}
    for p in allp:
        by.setdefault(p["employer"].strip().lower(), []).append(p)
    out = []
    for items in by.values():
        u = usual(items)
        inside = [p for p in items if (not start or p["date"] >= start) and (not end or p["date"] <= end)
                  and (account_ids is None or p["account_id"] in account_ids)]
        if not inside:
            continue
        missing = [dict(p, flag=fl[(p["kind"], p["id"])]) for p in inside if (p["kind"], p["id"]) in fl]
        out.append({"employer": items[0]["employer"], "usual": u["level"], "usual_words": LEVEL_WORDS[u["level"]],
                    "usual_labels": u["labels"], "count": len(inside), "flagged": missing,
                    "take_home_only": sum(1 for p in inside if p["level"] == "net")})
    out.sort(key=lambda e: e["employer"].lower())
    return out


def delete(store, gid):
    with store.lock:
        if not store.q1("SELECT 1 FROM paystubs WHERE group_id=?", (gid,)):
            raise ApiError("No such paystub", 404)
        for r in store.q("SELECT id FROM transactions WHERE group_id=?", (gid,)):
            store.delete_transaction(r["id"])
        store.db.execute("DELETE FROM paystubs WHERE group_id=?", (gid,))
        store.db.commit()
        store.changed()


def template(store, employer=None, account_id=None, bill_id=None):
    """The latest paystub to start the next one from: for this scheduled paycheck, else
    this employer, else the latest into this account. None when there's none."""
    tries = []
    if bill_id:
        tries.append(("bill_id=?", (int(bill_id),)))
    if employer:
        tries.append(("employer=? COLLATE NOCASE", (employer.strip(),)))
    if account_id:
        tries.append(("account_id=?", (int(account_id),)))
    for where, args in tries:
        r = store.q1(f"SELECT group_id FROM paystubs WHERE {where} ORDER BY date DESC, group_id DESC LIMIT 1", args)
        if r:
            return get(store, r["group_id"])
    return None


def copy_for_bill(store, bill, date, amount=None):
    """Entering a scheduled paycheck that has had a paystub: a copy of the latest one on
    the new date (the person edits it when this one differs). None when there's no
    paystub for it yet, or the amount entered isn't that paystub's net pay."""
    t = template(store, employer=bill["payee"], bill_id=bill["id"])
    if not t or t["account_id"] != bill["account_id"]:
        return None
    # (the amount entered may be the whole take-home pay, or what reached this account)
    if amount is not None and amount not in (t["net"], t["deposit"]):
        return None
    lines = [dict(ln, amount=f"{ln['amount'] / 100:.2f}") for ln in t["lines"]]   # stored in cents
    res = save(store, {"account_id": t["account_id"], "date": date, "employer": t["employer"], "memo": t["memo"],
                       "lines": lines, "bill_id": bill["id"]})
    return res


def group_ids_between(store, start, end, account_ids=None):
    extra, ids = store._acct_filter(account_ids, "account_id")
    return store.q("SELECT group_id, account_id, net, net_category_id, date FROM paystubs "
                   "WHERE date>=? AND date<=?" + extra, [start, end] + ids)


def year_summary(store, year, account_ids=None):
    """Gross vs net pay for a calendar year, per employer, and where the rest went:
    each earning, tax and deduction (by its label) added up, with what it was."""
    y = int(year)
    rows = store.q("SELECT * FROM paystubs WHERE date>=? AND date<=? ORDER BY date",
                   (f"{y}-01-01", f"{y}-12-31"))
    if account_ids is not None:
        rows = [r for r in rows if r["account_id"] in account_ids]
    cats = {c["id"]: c["full_name"] for c in store.categories()}
    accs = {a["id"]: a["name"] for a in store.accounts()}
    out = {}
    for r in rows:
        e = out.setdefault(r["employer"].lower(), {"employer": r["employer"], "paystubs": 0, "gross": 0, "net": 0,
                                                    "earnings": {}, "deductions": {}, "first": r["date"],
                                                    "last": r["date"], "accounts": set()})
        e["paystubs"] += 1
        e["gross"] += r["gross"]
        e["net"] += r["net"]
        e["last"] = r["date"]
        e["accounts"].add(accs.get(r["account_id"], "?"))
        for ln in json.loads(r["lines"] or "{}").get("lines", []):
            if ln["side"] == "split":
                e["accounts"].add(accs.get(ln.get("account_id"), "?"))   # part of the take-home pay went there
                continue
            where = (f"to {accs.get(ln['account_id'], 'an account')}" if ln.get("account_id")
                     else cats.get(ln.get("category_id"), ""))
            bucket = e["deductions" if ln["side"] == "deduct" else "earnings"]
            if ln["side"] == "add":
                where = (where + " · " if where else "") + "added after taxes"
            k = (ln["label"].lower(), where)
            it = bucket.setdefault(k, {"label": ln["label"], "goes_to": where, "total": 0,
                                       "transfer": bool(ln.get("account_id")), "count": 0})
            it["total"] += ln["amount"]
            it["count"] += 1
    result = []
    for e in out.values():
        e["accounts"] = sorted(e["accounts"])
        e["earnings"] = sorted(e["earnings"].values(), key=lambda i: -i["total"])
        e["deductions"] = sorted(e["deductions"].values(), key=lambda i: -i["total"])
        result.append(e)
    result.sort(key=lambda e: -e["gross"])
    return result
