"""Loans and mortgages: terms, the payment split (principal / interest / escrow),
the remaining balance and the payment schedule.

The loan is an account whose balance is what you still owe (stored negative,
like other debts). Each payment from your bank account becomes up to three
lines that share a group id:
  - principal: a transfer into the loan account (lowers what you owe),
  - interest: an expense in the interest category,
  - escrow: an expense in a category, a transfer to an escrow account, or,
    when the lender keeps the escrow, an expense with no category.
Interest for a payment = balance owed x APR / payments per year, rounded to the
cent; the fixed payment uses the standard amortization formula.
"""

import datetime as dt

from .store import ApiError, next_occurrence, parse_date, to_cents

FREQ_BY_PPY = {1: "Yearly", 2: "Twice a year", 4: "Every three months", 6: "Every other month",
               12: "Monthly", 24: "Twice a month", 26: "Every other week", 52: "Weekly"}


def period_rate(apr, ppy):
    return (apr or 0) / 100.0 / ppy


def calc_payment(principal_cents, apr, ppy, n):
    """Principal + interest per payment that pays the loan off in n payments."""
    if n <= 0:
        raise ApiError("Number of payments must be at least 1")
    r = period_rate(apr, ppy)
    if r == 0:
        return int(round(principal_cents / n))
    return int(round(principal_cents * r / (1 - (1 + r) ** -n)))


def split_payment(owed, apr, ppy, payment):
    """(principal, interest) of the next payment when `owed` cents are owed."""
    interest = int(round(owed * period_rate(apr, ppy)))
    principal = max(0, min(payment - interest, owed))
    # Cents left over from rounding go into the last payment, as lenders do.
    if 0 < owed - principal <= max(100, payment // 100):
        principal = owed
    return principal, interest


def schedule(owed, apr, ppy, payment, start_date, anchor_day, limit=1200):
    """Payments from start_date until the loan is paid off."""
    freq = FREQ_BY_PPY.get(ppy, "Monthly")
    rows, d, n = [], start_date, 0
    while owed > 0 and n < limit:
        principal, interest = split_payment(owed, apr, ppy, payment)
        if principal <= 0:
            break  # payment doesn't cover the interest: it would never end
        owed -= principal
        rows.append({"n": n + 1, "date": d.isoformat(), "principal": principal, "interest": interest,
                     "payment": principal + interest, "balance": owed})
        d = next_occurrence(d, freq, anchor_day)
        n += 1
    return rows


def payment_dates_until(first, ppy, until):
    """How many payments fall on or before `until`, and the first one after it."""
    freq = FREQ_BY_PPY.get(ppy, "Monthly")
    d, k = first, 0
    while d <= until and k < 5000:
        k += 1
        d = next_occurrence(d, freq, first.day)
    return k, d


def _terms(store, data):
    original = abs(to_cents(data.get("original_amount"), "loan amount"))
    if not original:
        raise ApiError("Enter the loan amount")
    try:
        apr = float(str(data.get("apr") or 0).replace("%", ""))
        ppy = int(data.get("payments_per_year") or 12)
        n = int(data.get("num_payments") or 0)
    except ValueError:
        raise ApiError("APR, payments per year and number of payments must be numbers")
    if not 0 <= apr <= 100:
        raise ApiError("APR must be between 0 and 100")
    if ppy not in FREQ_BY_PPY:
        raise ApiError("Payments per year must be 1, 2, 4, 6, 12, 24, 26 or 52")
    if not 1 <= n <= 1200:
        raise ApiError("Number of payments must be between 1 and 1200")
    first = parse_date(data.get("first_payment") or dt.date.today().isoformat(), "first payment date")
    mode = data.get("payment_mode") or "calc"
    payment = calc_payment(original, apr, ppy, n) if mode == "calc" else abs(to_cents(data.get("payment"), "payment"))
    if not payment:
        raise ApiError("Enter the payment amount")
    def opt_int(k):
        v = data.get(k)
        return int(v) if v not in (None, "", 0, "0") else None
    return {"original_amount": original, "apr": apr, "payments_per_year": ppy, "num_payments": n,
            "first_payment": first.isoformat(), "payment_mode": mode, "payment": payment,
            "escrow": abs(to_cents(data.get("escrow") or 0, "escrow")),
            "escrow_category_id": opt_int("escrow_category_id"), "escrow_account_id": opt_int("escrow_account_id"),
            "interest_category_id": opt_int("interest_category_id"),
            "pay_from_account_id": opt_int("pay_from_account_id"),
            "payee": (data.get("payee") or "").strip()}


def preview(store, data):
    """What the form would create: payment, payments made so far, balance owed now."""
    t = _terms(store, data)
    first = dt.date.fromisoformat(t["first_payment"])
    # Payments dated before today count as made; one due today is still to record.
    made, nxt = payment_dates_until(first, t["payments_per_year"], dt.date.today() - dt.timedelta(days=1))
    made = min(made, t["num_payments"])
    rows = schedule(t["original_amount"], t["apr"], t["payments_per_year"], t["payment"], first, first.day,
                    limit=max(made, 1))
    if not made:
        owed = t["original_amount"]
    else:
        owed = rows[min(made, len(rows)) - 1]["balance"] if rows else t["original_amount"]
    return {**t, "payments_made": made, "balance_now": owed, "next_payment_date": nxt.isoformat()}


def save(store, data, aid=None):
    """Create or change a loan account with its terms and its scheduled payment."""
    name = (data.get("name") or "").strip()
    if not name:
        raise ApiError("A loan needs a name")
    t = _terms(store, data)
    p = preview(store, data)
    with store.lock:
        owed_now = abs(to_cents(data["balance_now"], "balance owed")) if data.get("balance_now") not in (None, "") \
            else p["balance_now"]
        first = dt.date.fromisoformat(t["first_payment"])
        nxt = dt.date.fromisoformat(p["next_payment_date"])
        as_of = (nxt - dt.timedelta(days=1)) if p["payments_made"] else (first - dt.timedelta(days=1))
        acct = {"name": name, "type": data.get("type") or "Loan", "notes": data.get("notes") or "",
                "favorite": data.get("favorite"), "closed": data.get("closed")}
        if aid:
            old = store.account(aid)
            keep_opening = data.get("balance_now") in (None, "")
            acct["opening_balance"] = f"{(old['opening_balance'] if keep_opening else -owed_now) / 100:.2f}"
            acct["opening_date"] = old["opening_date"] if keep_opening else as_of.isoformat()
            store.save_account(acct, aid)
        else:
            acct["opening_balance"] = f"{-owed_now / 100:.2f}"
            acct["opening_date"] = as_of.isoformat()
            aid = store.save_account(acct)
        cols = list(t.keys())
        store.db.execute(f"INSERT INTO loans(account_id,{','.join(cols)}) VALUES(?{',?' * len(cols)}) "
                         f"ON CONFLICT(account_id) DO UPDATE SET " + ",".join(f"{c}=excluded.{c}" for c in cols),
                         [aid] + [t[c] for c in cols])
        _sync_bill(store, aid, t, nxt)
        store.db.commit()
        store.changed()
    return aid


def _sync_bill(store, aid, t, next_date):
    """Keep one scheduled 'loan payment' item for the loan (shown in Bills and Home)."""
    bill = store.q1("SELECT * FROM bills WHERE kind='loan' AND loan_account_id=?", (aid,))
    if not t["pay_from_account_id"]:
        if bill:
            store.db.execute("DELETE FROM bills WHERE id=?", (bill["id"],))
        return
    name = store.q1("SELECT name FROM accounts WHERE id=?", (aid,))["name"]
    vals = (t["payee"] or name, t["pay_from_account_id"], t["payment"] + t["escrow"],
            FREQ_BY_PPY[t["payments_per_year"]], dt.date.fromisoformat(t["first_payment"]).day)
    if bill:
        # Keep the bill's own next date (it moves as payments are recorded).
        store.db.execute("UPDATE bills SET payee=?, account_id=?, amount=?, frequency=?, anchor_day=?, active=1 "
                         "WHERE id=?", vals + (bill["id"],))
    else:
        store.db.execute("INSERT INTO bills(kind,payee,account_id,amount,frequency,next_date,anchor_day,"
                         "loan_account_id,memo) VALUES('loan',?,?,?,?,?,?,?,'')",
                         vals[:4] + (next_date.isoformat(), vals[4], aid))


def get(store, aid):
    loan = store.q1("SELECT * FROM loans WHERE account_id=?", (aid,))
    if not loan:
        raise ApiError("This account has no loan details", 404)
    acc = store.account(aid)
    owed = max(0, -acc["balance"])
    bill = store.q1("SELECT * FROM bills WHERE kind='loan' AND loan_account_id=? AND active=1", (aid,))
    if bill:
        start = dt.date.fromisoformat(bill["next_date"])
    else:
        _, start = payment_dates_until(dt.date.fromisoformat(loan["first_payment"]), loan["payments_per_year"],
                                      dt.date.today() - dt.timedelta(days=1))
    first = dt.date.fromisoformat(loan["first_payment"])
    rows = schedule(owed, loan["apr"], loan["payments_per_year"], loan["payment"], start, first.day)
    principal, interest = split_payment(owed, loan["apr"], loan["payments_per_year"], loan["payment"])
    paid = store.q1(
        "SELECT COALESCE(SUM(CASE WHEN t.category_id=? THEN -t.amount END),0) AS interest, "
        "COUNT(DISTINCT t.group_id) AS payments FROM transactions t WHERE t.group_id IN "
        "(SELECT p.group_id FROM transactions p JOIN transactions q ON q.id=p.transfer_id "
        " WHERE q.account_id=? AND p.group_id IS NOT NULL)", (loan["interest_category_id"], aid))
    names = {a["id"]: a["name"] for a in store.accounts()}
    cats = {c["id"]: c["full_name"] for c in store.categories()}
    return {**loan, "account": acc, "owed": owed, "bill": bill,
            "next": {"date": start.isoformat(), "principal": principal, "interest": interest,
                     "escrow": loan["escrow"] if owed else 0,
                     "total": principal + interest + (loan["escrow"] if owed else 0)},
            "payments_left": len(rows), "payoff_date": rows[-1]["date"] if rows else None,
            "total_interest_left": sum(r["interest"] for r in rows),
            "interest_paid": paid["interest"], "payments_recorded": paid["payments"],
            "never_ends": owed > 0 and not rows,
            "schedule": rows[:600],
            "pay_from_name": names.get(loan["pay_from_account_id"]),
            "escrow_account_name": names.get(loan["escrow_account_id"]),
            "escrow_category_name": cats.get(loan["escrow_category_id"]),
            "interest_category_name": cats.get(loan["interest_category_id"])}


def pay(store, aid, data=None):
    """Record one payment: principal to the loan, interest and escrow as expenses,
    all from the paying account, kept together as one group."""
    data = data or {}
    loan = store.q1("SELECT * FROM loans WHERE account_id=?", (aid,))
    if not loan:
        raise ApiError("This account has no loan details", 404)
    info = get(store, aid)
    src = int(data.get("account_id") or loan["pay_from_account_id"] or 0)
    if not src or src == aid:
        raise ApiError("Choose the account the payment comes from")
    def amount(key, default):
        v = data.get(key)
        return abs(to_cents(v, key)) if v not in (None, "") else default
    principal = amount("principal", info["next"]["principal"])
    interest = amount("interest", info["next"]["interest"])
    escrow = amount("escrow", info["next"]["escrow"])
    if principal + interest + escrow == 0:
        raise ApiError("Nothing to pay")
    date = data.get("date") or info["next"]["date"]
    payee = (data.get("payee") or loan["payee"] or info["account"]["name"]).strip()
    memo = (data.get("memo") or "").strip()
    number = str(data.get("number") or "")
    with store.lock:
        gid = (store.q1("SELECT COALESCE(MAX(group_id),0)+1 AS g FROM transactions")["g"])
        ids = []
        def line(amount_cents, part, **kw):
            tx = {"account_id": src, "date": date, "payee": payee, "number": number,
                  "memo": f"{part}" + (f" · {memo}" if memo else ""), "amount_cents": -amount_cents}
            tx.update(kw)
            ids.append(store.save_transaction(tx))
        if principal:
            line(principal, "Principal", transfer_account_id=aid)
        if interest:
            line(interest, "Interest", category_id=loan["interest_category_id"])
        if escrow:
            if loan["escrow_account_id"] and loan["escrow_account_id"] != src:
                line(escrow, "Escrow", transfer_account_id=loan["escrow_account_id"])
            else:
                line(escrow, "Escrow", category_id=loan["escrow_category_id"])
        marks = ",".join("?" * len(ids))
        store.db.execute(f"UPDATE transactions SET group_id=? WHERE id IN ({marks})", [gid] + ids)
        store.db.commit()
        store.changed()
    return {"group_id": gid, "ids": ids, "principal": principal, "interest": interest, "escrow": escrow,
            "total": principal + interest + escrow}
