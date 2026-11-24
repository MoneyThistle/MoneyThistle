"""Bringing transactions in from files (no bank connection needed) and out again.

Reads CSV files (most banks offer a CSV download) and QIF files (the classic
money-program exchange format). Writes CSV.
"""

import csv
import datetime as dt
import io

from .store import ApiError, to_cents

DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d",
                "%m-%d-%Y", "%b %d, %Y", "%d %b %Y"]


def parse_any_date(s, prefer_dmy=False):
    s = (s or "").strip().replace("'", "/")
    fmts = DATE_FORMATS
    if prefer_dmy:
        fmts = ["%d/%m/%Y", "%d.%m.%Y"] + fmts
    for f in fmts:
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    # QIF short years like 1/31/26
    try:
        m, d, y = s.replace("-", "/").split("/")
        y = int(y.strip())
        y += 2000 if y < 70 else (1900 if y < 100 else 0)
        return dt.date(y, int(m), int(d))
    except Exception:
        raise ApiError(f"Can't read the date '{s}'")


def _pick(header, *names):
    low = [h.strip().lower() for h in header]
    for n in names:
        for i, h in enumerate(low):
            if h == n:
                return i
    for n in names:
        for i, h in enumerate(low):
            if n in h:
                return i
    return None


def parse_csv(text):
    text = text.lstrip("ï»¿")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ApiError("The file has no rows to import")
    header = rows[0]
    di = _pick(header, "date", "posted", "booking date", "transaction date")
    pi = _pick(header, "payee", "description", "name", "merchant")
    ai = _pick(header, "amount")
    debit = _pick(header, "debit", "withdrawal", "payment")
    credit = _pick(header, "credit", "deposit")
    mi = _pick(header, "memo", "note", "notes", "reference")
    ci = _pick(header, "category")
    ni = _pick(header, "number", "check", "check number", "num")
    if di is None or (ai is None and debit is None and credit is None):
        raise ApiError("The CSV needs a 'Date' column and an 'Amount' column (or 'Debit'/'Credit')")
    out = []
    for r in rows[1:]:
        def col(i):
            return r[i].strip() if i is not None and i < len(r) else ""
        if ai is not None and col(ai):
            amount = to_cents(col(ai))
        else:
            amount = to_cents(col(credit) or 0) - abs(to_cents(col(debit) or 0))
        out.append({"date": parse_any_date(col(di)).isoformat(), "payee": col(pi), "amount": amount,
                    "memo": col(mi), "category": col(ci), "number": col(ni)})
    return out


def parse_qif(text):
    out, cur = [], {}
    for line in text.splitlines():
        if not line:
            continue
        code, val = line[0], line[1:].strip()
        if code == "!":
            continue
        if code == "^":
            if "date" in cur and "amount" in cur:
                out.append(cur)
            cur = {}
        elif code == "D":
            cur["date"] = parse_any_date(val).isoformat()
        elif code in ("T", "U"):
            cur["amount"] = to_cents(val)
        elif code == "P":
            cur["payee"] = val
        elif code == "M":
            cur["memo"] = val
        elif code == "N":
            cur["number"] = val
        elif code == "L":
            cur["category"] = val
        elif code == "C":
            cur["status"] = "R" if val.upper() in ("X", "R") else ("C" if val == "*" else "")
    if "date" in cur and "amount" in cur:
        out.append(cur)
    if not out:
        raise ApiError("No transactions found in the QIF file")
    return out


def parse_ofx(text):
    """OFX / QFX / QBO bank downloads (version 1 SGML or version 2 XML): each
    transaction with the bank's own id (FITID), plus the balance the bank reports."""
    import re
    if "<OFX" not in text.upper():
        raise ApiError("This doesn't look like an OFX/QFX file")

    def field(block, tag):
        m = re.search(rf"<{tag}>\s*([^<\r\n]*)", block, re.I)
        return m.group(1).strip() if m else ""

    def ofx_date(s):
        m = re.match(r"(\d{4})(\d{2})(\d{2})", s or "")
        if not m:
            raise ApiError(f"Can't read the date '{s}'")
        return dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()

    def unescape(s):
        return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&apos;", "'").replace("&quot;", '"')

    out = []
    for block in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, re.I | re.S):
        amt = field(block, "TRNAMT")
        posted = field(block, "DTPOSTED") or field(block, "DTUSER")
        if not amt or not posted:
            continue
        name = unescape(field(block, "NAME") or field(block, "PAYEEID"))
        memo = unescape(field(block, "MEMO"))
        out.append({"date": ofx_date(posted), "amount": to_cents(amt.replace(",", ".") if amt.count(",") == 1 and "." not in amt else amt),
                    "payee": name or memo, "memo": memo if name else "",
                    "number": field(block, "CHECKNUM"), "fitid": field(block, "FITID"),
                    "status": "C"})
    if not out:
        raise ApiError("No transactions found in the OFX/QFX file")
    bal = re.search(r"<LEDGERBAL>(.*?)(</LEDGERBAL>|<AVAILBAL>|</STMTRS>|</CCSTMTRS>)", text, re.I | re.S)
    info = {}
    if bal:
        b = field(bal.group(1), "BALAMT")
        d = field(bal.group(1), "DTASOF")
        if b:
            info = {"balance": to_cents(b), "balance_date": ofx_date(d) if d else None}
    acct = field(text, "ACCTID")
    if acct:
        info["account_last4"] = acct[-4:]
    return out, info


def match_category(store, name):
    """Find a category from text like 'Bills:Electricity' or 'Groceries'."""
    if not name or name.startswith("["):
        return None
    parts = [p.strip().lower() for p in name.replace(" : ", ":").split(":")]
    cats = store.categories()
    if len(parts) >= 2:
        for c in cats:
            if c["parent_name"] and c["parent_name"].lower() == parts[0] and c["name"].lower() == parts[1]:
                return c["id"]
    for c in cats:
        if not c["parent_id"] and c["name"].lower() == parts[-1]:
            return c["id"]
    for c in cats:
        if c["name"].lower() == parts[-1]:
            return c["id"]
    return None


def transfer_account(store, account_id, name):
    """QIF writes transfers as [Account name] in the category; CSV may say 'Transfer to X'."""
    if not name:
        return None
    n = name.strip()
    if n.startswith("[") and n.endswith("]"):
        n = n[1:-1]
    else:
        low = n.lower()
        for prefix in ("transfer to ", "transfer from "):
            if low.startswith(prefix):
                n = n[len(prefix):]
                break
        else:
            return None
    for a in store.accounts():
        if a["name"].lower() == n.strip().lower() and a["id"] != account_id:
            return a["id"]
    return None


def _first_word(s):
    w = "".join(ch if ch.isalnum() else " " for ch in (s or "").lower()).split()
    return w[0] if w else ""


def plan_import(store, account_id, rows, skip_duplicates=True):
    """What importing would do with each row, changing nothing (shown for review):
    - skip: the bank's id (OFX FITID) was imported before, or the same date, amount and
      payee is already there ("same" names that entry, which takes the bank's id);
    - match: an entry already in the register (typed, entered from the schedule, or
      recorded automatically) with the same amount within 4 days: it takes the bank's
      id and is marked cleared instead of a second one being added;
    - correct: an automatic entry recorded at an estimate (same payee, same direction,
      within 4 days) takes the bank's real amount;
    - add: a new entry."""
    existing, by_fitid, open_rows = {}, set(), []
    if skip_duplicates:
        for t in store.transactions(account_id=account_id, limit=100000):
            existing.setdefault((t["date"], t["amount"], (t["payee"] or "").lower()), t)
            if t.get("fitid"):
                by_fitid.add(t["fitid"])
            else:
                open_rows.append(t)
    near = lambda a, b: abs((dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days) <= 4
    brief = lambda t: {"id": t["id"], "date": t["date"], "payee": t["payee"], "amount": t["amount"],
                       "auto": bool(t.get("auto"))}
    plan, seen_keys = [], set()
    for i, r in enumerate(rows):
        fitid = r.get("fitid") or ""
        item = {"i": i, "date": r["date"], "payee": r.get("payee", ""), "amount": r["amount"],
                "memo": r.get("memo", ""), "fitid": fitid}
        key = (r["date"], r["amount"], (r.get("payee") or "").lower())
        if r["amount"] == 0 or (fitid and fitid in by_fitid):
            item.update(action="skip", why="imported before" if r["amount"] else "zero amount")
        elif skip_duplicates and (key in existing or key in seen_keys):
            same = existing.get(key)
            item.update(action="skip", why="already in the register")
            if same and same in open_rows:
                open_rows.remove(same)
                item["same"] = brief(same)
        else:
            hit = next((t for t in open_rows if t["amount"] == r["amount"] and near(t["date"], r["date"])), None)
            fix = None if hit else next(
                (t for t in open_rows if t.get("auto") and (t["amount"] < 0) == (r["amount"] < 0)
                 and near(t["date"], r["date"]) and _first_word(t["payee"]) == _first_word(r.get("payee"))), None)
            if hit or fix:
                open_rows.remove(hit or fix)
                item.update(action="match" if hit else "correct", target=brief(hit or fix))
            else:
                item["action"] = "add"
        if fitid:
            by_fitid.add(fitid)
        seen_keys.add(key)
        plan.append(item)
    return plan


def apply_import(store, account_id, rows, plan, choices=None):
    """Carry out a plan. `choices` ({row number: action}) can turn a match or a
    correction into "add" (it's a different entry) and anything into "skip"."""
    payees = {p["name"].lower(): p["category_id"] for p in store.payees()}
    choices = {int(k): v for k, v in (choices or {}).items()}
    counts = {"added": 0, "skipped": 0, "matched": 0, "corrected": 0}
    for item in plan:
        r = rows[item["i"]]
        action = item["action"]
        want = choices.get(item["i"])
        if want == "skip" or (want == "add" and action in ("match", "correct")):
            action = want
        fitid = item.get("fitid") or None
        if action == "skip":
            if item.get("same") and fitid:
                with store.lock:
                    store.db.execute("UPDATE transactions SET fitid=? WHERE id=?", (fitid, item["same"]["id"]))
                    store.db.commit()
            counts["skipped"] += 1
            continue
        if action in ("match", "correct"):
            t = store.q1("SELECT id, transfer_id FROM transactions WHERE id=?", (item["target"]["id"],))
            if not t:
                action = "add"
            else:
                with store.lock:
                    if action == "correct":   # the estimate becomes the bank's amount (both sides of a transfer)
                        store.db.execute("UPDATE transactions SET amount=? WHERE id=?", (r["amount"], t["id"]))
                        if t["transfer_id"]:
                            store.db.execute("UPDATE transactions SET amount=? WHERE id=?", (-r["amount"], t["transfer_id"]))
                    store.db.execute("UPDATE transactions SET fitid=?, status=CASE WHEN status='' THEN 'C' ELSE status END "
                                     "WHERE id=?", (fitid, t["id"]))
                    store.db.commit()
                    store.changed()
                counts["matched" if action == "match" else "corrected"] += 1
                continue
        tx = {"account_id": account_id, "date": r["date"], "payee": r.get("payee", ""),
              "amount_cents": r["amount"], "memo": r.get("memo", ""),
              "number": r.get("number", ""), "status": r.get("status", "")}
        other = transfer_account(store, account_id, r.get("category"))
        if other:
            tx["transfer_account_id"] = other
        else:
            tx["category_id"] = match_category(store, r.get("category")) or payees.get((r.get("payee") or "").lower())
        tid = store.save_transaction(tx)
        if fitid:
            with store.lock:
                store.db.execute("UPDATE transactions SET fitid=? WHERE id=?", (fitid, tid))
                store.db.commit()
        counts["added"] += 1
    return counts


def import_rows(store, account_id, rows, skip_duplicates=True, choices=None):
    """Plan and carry out an import in one go (see plan_import)."""
    return apply_import(store, account_id, rows, plan_import(store, account_id, rows, skip_duplicates), choices)

def export_csv(store, account_id=None):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Account", "Number", "Payee", "Category", "Memo", "Amount", "Status"])
    rows = store.transactions(account_id=account_id, limit=10 ** 9)
    rows.reverse()
    for t in rows:
        w.writerow([t["date"], t["account_name"], t["number"], t["payee"], t["category_label"],
                    t["memo"], f"{t['amount'] / 100:.2f}", t["status"]])
    return buf.getvalue()
