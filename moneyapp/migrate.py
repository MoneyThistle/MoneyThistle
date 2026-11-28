"""Moving in from another money program, in one go.

Reads one exported file holding every account:

  * QIF with all accounts (Microsoft Money, Quicken, Moneydance, KMyMoney, HomeBank,
    Money Manager Ex, Banktivity...): accounts and their types, the category list,
    transactions with splits, transfers between accounts, cleared/reconciled marks and
    opening balances;
  * CSV exports with an account column: YNAB, Actual Budget, Mint, Firefly III,
    GnuCash ("Export Transactions to CSV"), or any spreadsheet with Account, Date,
    Payee, Category and Amount (or Inflow/Outflow, Debit/Credit) columns.

First a preview (nothing changes): each account found, its entries, dates and balance,
and the categories to create. Then the person decides, per account, to add it as a new
account, into one they already have, or to leave it out, and it's brought in:
categories are created as needed, a transfer listed in both accounts becomes one
transfer (never two), splits stay together as one entry, and entries already in an
existing account aren't added twice. Scheduled bills, budgets and investment holdings
aren't in these files, so they're set up again here.
"""

import base64
import csv
import datetime as dt
import io
import re

from .fileio import match_category, parse_any_date
from . import defaults
from .store import ApiError, to_cents

QIF_TYPES = {"bank": "Checking", "ccard": "Credit Card", "cash": "Cash", "oth a": "Asset", "oth l": "Liability",
             "invst": "Investment", "port": "Investment", "401(k)/403(b)": "Retirement", "mutual": "Investment"}
TRANSFER_WORDS = ("transfer", "credit card payment", "payment thank you")


def decode(raw):
    """Text from the file's bytes: UTF-8, else Windows-1252 (what older programs write)."""
    if isinstance(raw, str):
        return raw.lstrip("﻿")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def guess_type(name, default="Checking"):
    """An account's type from words in its name (a firm's name says nothing: Fidelity, Schwab
    and Vanguard keep checking-like cash accounts and HSAs too)."""
    n = (name or "").lower()
    for words, t in ((("visa", "mastercard", "amex", "discover", "credit card", " card"), "Credit Card"),
                     (("mortgage", "loan", "heloc"), "Loan"),
                     (("401k", "401(k)", "403b", " ira", "roth", "retire", "pension", "tsp"), "Retirement"),
                     (("brokerage", "invest", "stocks", " etf", "mutual fund"), "Investment"),
                     ((" hsa", "health savings"), "Savings"),
                     (("cash management", "checking", "chequing"), "Checking"),
                     (("saving", "money market", "emergency"), "Savings"),
                     (("cash", "wallet", "petty"), "Cash")):
        if any(w in " " + n for w in words):
            return t
    return default


def _status(v):
    v = (v or "").strip().lower()
    return "R" if v in ("x", "r", "reconciled", "true", "yes") else ("C" if v in ("*", "c", "cleared") else "")


def _row(account, date, amount, payee="", memo="", number="", category=None, transfer_to=None, status="", splits=None):
    return {"account": account, "date": date, "amount": amount, "payee": (payee or "").strip(),
            "memo": (memo or "").strip(), "number": (number or "").strip(), "category": category or None,
            "transfer_to": transfer_to or None, "status": status, "splits": splits or None}


def _new_account(accounts, name, typ=None):
    key = name.strip() or "Imported"
    if key not in accounts:
        accounts[key] = {"name": key, "type": typ or guess_type(key), "rows": [], "opening": None, "opening_date": None}
    elif typ and accounts[key]["type"] == guess_type(key):
        accounts[key]["type"] = typ
    return accounts[key]


# ----- QIF ----------------------------------------------------------------------------
def _invest_type(name):
    """The type of an account a program keeps as investments, from its name: Retirement (a Roth
    IRA, a 401(k)), Savings (an HSA), Checking (a cash management account), else Investment."""
    t = guess_type(name, "Investment")
    return t if t in ("Retirement", "Savings", "Checking") else "Investment"


# What the investment-format entries ("!Type:Invst") do to the account's cash: income (with its
# usual category), money in or out (transfers when another account is named). Buys, sells and
# share moves only change what it holds, so they aren't entries here.
INVST_INCOME = {"div": "Investment Income : Dividends", "reinvdiv": "Investment Income : Dividends",
                "intinc": "Investment Income : Interest", "reinvint": "Investment Income : Interest",
                "cglong": "Investment Income : Capital Gains", "cgshort": "Investment Income : Capital Gains",
                "cgmid": "Investment Income : Capital Gains", "reinvlg": "Investment Income : Capital Gains",
                "reinvsh": "Investment Income : Capital Gains", "reinvmd": "Investment Income : Capital Gains",
                "miscinc": None, "rtrncap": None}
INVST_IN = ("xin", "contribx", "buyx")
INVST_OUT = ("xout", "withdrwx", "sellx")
INVST_EXPENSE = ("miscexp", "margint")


def _invst_row(acc, r):
    """One investment-format entry as a row of the account's cash; None when it only changes
    holdings (a buy or sell), False when there's nothing to bring in."""
    action = (r.get("N") or "").strip().lower().replace(" ", "")
    if "D" not in r:
        return False
    if action.endswith("x") and action[:-1] in INVST_INCOME:
        return None   # income paid out to another account: that account lists it
    money = r.get("T") or r.get("U") or ((r.get("$") or [""])[0] if isinstance(r.get("$"), list) else r.get("$"))
    if not money:
        return None
    amount = abs(to_cents(money))
    if not amount:
        return False
    date = parse_any_date(r["D"]).isoformat()
    lab = (r.get("L") or "").strip()
    transfer = lab[1:lab.index("]")].strip() if lab.startswith("[") and "]" in lab else None
    cat = None if transfer is not None else (lab.split("/")[0].strip() or None)
    payee = (r.get("P") or "").strip() or (r.get("Y") or "").strip()
    memo = r.get("M", "")
    if action in INVST_INCOME:
        if transfer is not None:
            return None
        return _row(acc["name"], date, amount, payee, memo, "", cat or INVST_INCOME[action], None, _status(r.get("C")))
    if action in INVST_IN or action in INVST_OUT:
        sign = 1 if action in INVST_IN else -1
        if transfer is not None and transfer.lower() == acc["name"].lower():
            if acc["opening"] is None and sign > 0 and not acc["rows"]:   # its opening balance
                acc["opening"], acc["opening_date"] = amount, date
            return False
        return _row(acc["name"], date, sign * amount, payee, memo, "", None if transfer is not None else cat,
                    transfer, _status(r.get("C")))
    if action in INVST_EXPENSE:
        return _row(acc["name"], date, -amount, payee, memo, "", cat, None, _status(r.get("C")))
    if action == "cash":
        signed = to_cents(money)
        return _row(acc["name"], date, signed, payee, memo, "", None if transfer is not None else cat,
                    transfer, _status(r.get("C")))
    return None


def parse_qif_all(text, fallback_name="Imported account"):
    """Every account in a QIF file (or the one account of a single-account file)."""
    accounts, kinds, skipped = {}, {}, {"investment entries": 0}
    section, current, in_list, rec = None, None, False, {}
    renamed = [None]
    last_acc = [None]   # the latest account header (Moneydance never clears AutoSwitch: see below)

    def flush():
        nonlocal rec, current
        r = rec
        rec = {}
        if not r:
            return
        if section == "account":
            name = (r.get("N") or "").strip()
            if not name:
                return
            qtyp = (r.get("T") or "").strip().lower()
            typ = QIF_TYPES.get(qtyp)
            if typ == "Checking":
                typ = guess_type(name)   # QIF calls savings "Bank" too: the name tells them apart
            elif typ == "Investment":
                typ = _invest_type(name)  # a Roth IRA, an HSA or a cash account kept as investments
            elif typ == "Liability" and guess_type(name, "Liability") == "Loan":
                typ = "Loan"              # a mortgage
            acc = _new_account(accounts, name, typ)
            if typ in ("Investment", "Retirement") or qtyp in ("invst", "port", "401(k)/403(b)", "mutual"):
                # Its buys and sells aren't brought in (MoneyThistle keeps investments as
                # balances), but the account is, with its dividends, interest and transfers.
                acc["keep"] = True
            last_acc[0] = acc
            if not in_list:
                current = acc   # the transactions that follow are this account's
            return
        if section == "cat":
            name = (r.get("N") or "").strip()
            if name:
                kinds[name] = "income" if "I" in r else "expense"
            return
        if section in ("bank", "ccard", "cash", "oth a", "oth l"):
            acc = current or _new_account(accounts, fallback_name, QIF_TYPES.get(section))
            if "D" not in r or ("T" not in r and "U" not in r):
                return
            date = parse_any_date(r["D"]).isoformat()
            amount = to_cents(r.get("T") or r.get("U"))
            cat = (r.get("L") or "").strip()
            transfer = cat[1:-1].strip() if cat.startswith("[") and "]" in cat else None
            if transfer is not None and "/" in cat:   # "[Account]/Class"
                transfer = cat[1:cat.index("]")].strip()
            if not transfer and "/" in cat:
                cat = cat.split("/")[0]                  # "Category/Class": the class is dropped
            payee = r.get("P", "")
            # The opening balance: an entry transferring to the account itself.
            if transfer is not None and transfer.lower() == acc["name"].lower():
                if acc["opening"] is None:
                    acc["opening"], acc["opening_date"] = amount, date
                return
            if payee.strip().lower() == "opening balance" and not acc["rows"] and acc["opening"] is None:
                acc["opening"], acc["opening_date"] = amount, date
                if transfer and current is None:
                    # A one-account file (Microsoft Money exports one account per file):
                    # "[Account name]" on its opening balance is the account's real name.
                    renamed[0] = transfer
                return
            splits = None
            if r.get("S"):
                splits = []
                for i, sc in enumerate(r["S"]):
                    sc = sc.strip()
                    st = sc[1:-1].strip() if sc.startswith("[") and sc.endswith("]") else None
                    amt = to_cents(r["$"][i]) if i < len(r.get("$", [])) else 0
                    if amt:
                        splits.append({"category": None if st is not None else (sc.split("/")[0] or None),
                                       "transfer_to": st, "memo": r["E"][i] if i < len(r.get("E", [])) else "",
                                       "amount": amt})
                if len(splits) <= 1:
                    if splits:
                        cat, transfer = splits[0]["category"] or "", splits[0]["transfer_to"]
                    splits = None
            acc["rows"].append(_row(acc["name"], date, amount, payee, r.get("M", ""), r.get("N", ""),
                                    None if transfer is not None else (cat or None), transfer, _status(r.get("C")),
                                    splits))
        elif section == "invst":
            acc = current or _new_account(accounts, fallback_name, "Investment")
            row = _invst_row(acc, r)
            if row:
                acc["rows"].append(row)
            elif row is None:
                skipped["investment entries"] += 1
        elif section == "port":
            skipped["investment entries"] += 1

    for line in text.splitlines():
        line = line.rstrip("\r")
        if not line.strip():
            continue
        if line.startswith("!"):
            flush()
            head = line[1:].strip().lower()
            if head.startswith("option:autoswitch"):
                in_list = True
            elif head.startswith("clear:autoswitch"):
                in_list = False
            elif head == "account":
                section = "account"
            elif head.startswith("type:"):
                t = head[5:].strip()
                section = {"cat": "cat", "class": "skip", "memorized": "skip", "security": "skip",
                           "prices": "skip", "invitem": "skip", "budget": "skip"}.get(t, t)
                # Entries straight after an account header are that account's, even in the
                # account-list mode (Moneydance turns AutoSwitch on and never clears it).
                if section in ("bank", "ccard", "cash", "oth a", "oth l", "invst", "port") and last_acc[0]:
                    current = last_acc[0]
                last_acc[0] = None
                if section in ("invst", "port") and current:
                    if current["type"] not in ("Investment", "Retirement", "Savings", "Checking"):
                        current["type"] = _invest_type(current["name"])
                    current["keep"] = True
            else:
                section = "skip"
            continue
        if line.startswith("^"):
            flush()
            continue
        code, val = line[0], line[1:]
        if code in ("S", "E", "$"):
            rec.setdefault(code, [])
            if code == "S":
                rec["S"].append(val)
                rec.setdefault("E", []), rec.setdefault("$", [])
                # Keep E and $ aligned with their S.
            elif code == "E":
                rec["E"] += [""] * (len(rec.get("S", [])) - 1 - len(rec["E"]))
                rec["E"].append(val)
            else:
                rec["$"] += [""] * (len(rec.get("S", [])) - 1 - len(rec["$"]))
                rec["$"].append(val)
        else:
            rec[code] = val
    flush()
    accounts = {k: a for k, a in accounts.items() if a["rows"] or a["opening"] or a.get("keep")}
    if renamed[0] and list(accounts) == [fallback_name]:
        a = accounts.pop(fallback_name)
        a["name"] = renamed[0]
        for r in a["rows"]:
            r["account"] = renamed[0]
        if a["type"] == "Checking":
            a["type"] = guess_type(renamed[0])
        accounts[renamed[0]] = a
    if not accounts:
        raise ApiError("No accounts or transactions found in this QIF file")
    return accounts, kinds, skipped


# ----- CSV exports -----------------------------------------------------------------------
def _csv_rows(text):
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ApiError("The file has no rows to bring in")
    head = [h.strip().lower() for h in rows[0]]
    return head, rows[1:]


def _col(head, *names):
    for n in names:
        if n in head:
            return head.index(n)
    return None


def _money(v):
    v = (v or "").strip().replace(" ", "")
    if not v:
        return 0
    v = re.sub(r"[^\d,.\-()]", "", v)   # currency symbols and letters out
    return to_cents(v)


def _transfer_from_payee(p):
    """'Transfer : Savings' (YNAB), 'Transfer: Savings' (Actual) -> 'Savings'."""
    m = re.match(r"\s*transfer\s*:\s*(.+)$", p or "", re.I)
    return m.group(1).strip() if m else None


def parse_csv_all(text):
    head, data = _csv_rows(text)
    g = lambda r, i: r[i].strip() if i is not None and i < len(r) else ""
    accounts = {}

    # GnuCash: one row per split, grouped into transactions.
    if _col(head, "full account name") is not None and _col(head, "transaction id") is not None:
        return _gnucash(head, data, accounts), "GnuCash"

    # Firefly III: source and destination accounts, typed.
    if _col(head, "source_name") is not None and _col(head, "destination_name") is not None:
        ti, ai, di = _col(head, "type"), _col(head, "amount"), _col(head, "date")
        si, de, ci = _col(head, "source_name"), _col(head, "destination_name"), _col(head, "category")
        pi, ni = _col(head, "description"), _col(head, "notes")
        for r in data:
            kind, amt = g(r, ti).lower(), abs(_money(g(r, ai)))
            date = parse_any_date(g(r, di)[:10]).isoformat()
            if kind == "deposit":
                _new_account(accounts, g(r, de))["rows"].append(
                    _row(g(r, de), date, amt, g(r, si) or g(r, pi), g(r, ni), category=g(r, ci)))
            elif kind == "transfer":
                _new_account(accounts, g(r, si))["rows"].append(
                    _row(g(r, si), date, -amt, g(r, pi), g(r, ni), transfer_to=g(r, de)))
                _new_account(accounts, g(r, de))["rows"].append(
                    _row(g(r, de), date, amt, g(r, pi), g(r, ni), transfer_to=g(r, si)))
            elif kind in ("withdrawal", "payment"):
                _new_account(accounts, g(r, si))["rows"].append(
                    _row(g(r, si), date, -amt, g(r, de) or g(r, pi), g(r, ni), category=g(r, ci)))
            elif kind == "opening balance":
                acc = _new_account(accounts, g(r, de) if g(r, de) else g(r, si))
                acc["opening"], acc["opening_date"] = (amt if g(r, de) else -amt), date
        return accounts, "Firefly III"

    acct = _col(head, "account", "account name", "account_name")
    if acct is None:
        raise ApiError("This CSV has no Account column. To bring in one account, use Import file in that "
                       "account's register instead.")
    di = _col(head, "date", "transaction date", "posted date")
    pi = _col(head, "payee", "description", "name", "merchant")
    ci = _col(head, "category group/category", "category", "category name")
    mi = _col(head, "memo", "notes", "note")
    ni = _col(head, "number", "check number", "num")
    sti = _col(head, "cleared", "status", "reconciled")
    out_i, in_i = _col(head, "outflow", "debit", "withdrawal"), _col(head, "inflow", "credit", "deposit")
    ai = _col(head, "amount")
    tti = _col(head, "transaction type")
    if di is None or (ai is None and out_i is None and in_i is None):
        raise ApiError("The CSV needs Date and Amount columns (or Inflow/Outflow, Debit/Credit)")
    fmt = "YNAB" if "category group/category" in head else ("Mint" if "original description" in head else
                                                             ("Actual Budget" if "split_amount" in head else "CSV"))
    for r in data:
        name = g(r, acct)
        if not name or not g(r, di):
            continue
        if ai is not None and g(r, ai):
            amt = _money(g(r, ai))
            if tti is not None:   # Mint: positive amounts, with debit/credit beside them
                amt = -abs(amt) if g(r, tti).lower() == "debit" else abs(amt)
        else:
            amt = abs(_money(g(r, in_i))) - abs(_money(g(r, out_i)))
        cat = g(r, ci)
        if fmt == "YNAB" and cat.lower().startswith("inflow:"):
            cat = ""   # "Inflow: Ready to Assign" is YNAB's own bookkeeping
        payee = g(r, pi)
        xfer = _transfer_from_payee(payee)
        row =_row(name, parse_any_date(g(r, di)).isoformat(), amt, payee if not xfer else f"Transfer: {xfer}",
                   g(r, mi), g(r, ni), None if xfer else (cat.replace(": ", ":") or None), xfer,
                   _status(g(r, sti)))
        _new_account(accounts, name)["rows"].append(row)
    _pair_transfers(accounts)
    return accounts, fmt


def _gnucash(head, data, accounts):
    c = {k: _col(head, *v) for k, v in {
        "date": ("date",), "id": ("transaction id",), "num": ("number",), "desc": ("description",),
        "notes": ("notes",), "memo": ("memo",), "acct": ("full account name",),
        "amt": ("amount num.", "amount num", "value num.", "amount"), "rec": ("reconcile",)}.items()}
    g = lambda r, k: r[c[k]].strip() if c[k] is not None and c[k] < len(r) else ""
    groups, order, last = {}, [], {}
    for r in data:
        tid = g(r, "id") or last.get("id")
        if not tid:
            continue
        if tid not in groups:
            groups[tid] = {"date": g(r, "date") or last.get("date"), "num": g(r, "num"), "desc": g(r, "desc"),
                           "notes": g(r, "notes"), "splits": []}
            order.append(tid)
        last = {"id": tid, "date": groups[tid]["date"]}
        if g(r, "acct"):
            groups[tid]["splits"].append({"acct": g(r, "acct"), "amt": _money(g(r, "amt")),
                                          "memo": g(r, "memo"), "rec": g(r, "rec")})
    top = lambda a: a.split(":")[0].strip().lower()
    for tid in order:
        t = groups[tid]
        if not t["date"]:
            continue
        date = parse_any_date(t["date"]).isoformat()
        money = [s for s in t["splits"] if top(s["acct"]) not in ("income", "expenses", "expense", "equity")
                 and not top(s["acct"]).startswith(("imbalance", "orphan"))]
        cats = [s for s in t["splits"] if s not in money]
        for m in money:
            leaf = m["acct"].split(":")[-1].strip()
            typ = guess_type(m["acct"], "Liability" if top(m["acct"]).startswith("liabilit") else "Checking")
            acc = _new_account(accounts, leaf, typ)
            if any(top(s["acct"]) == "equity" for s in cats) and len(money) == 1:
                acc["opening"] = (acc["opening"] or 0) + m["amt"]
                acc["opening_date"] = min(acc["opening_date"] or date, date)
                continue
            others = [x for x in money if x is not m]
            real_cats = [s for s in cats if top(s["acct"]) in ("income", "expenses", "expense")]
            path = lambda s: ":".join(p.strip() for p in s["acct"].split(":")[1:]) or None
            if others and not real_cats:
                acc["rows"].append(_row(leaf, date, m["amt"], t["desc"], m["memo"] or t["notes"], t["num"],
                                        transfer_to=others[0]["acct"].split(":")[-1].strip(), status=_status(m["rec"]) if m["rec"].lower() != "n" else ""))
            elif len(real_cats) == 1 and not others:
                acc["rows"].append(_row(leaf, date, m["amt"], t["desc"], m["memo"] or t["notes"], t["num"],
                                        category=path(real_cats[0]), status=_status(m["rec"]) if m["rec"].lower() != "n" else ""))
            else:
                parts = [{"category": path(s), "transfer_to": None, "memo": s["memo"], "amount": -s["amt"]} for s in real_cats]
                parts += [{"category": None, "transfer_to": x["acct"].split(":")[-1].strip(), "memo": x["memo"],
                           "amount": -x["amt"]} for x in others]
                acc["rows"].append(_row(leaf, date, m["amt"], t["desc"], t["notes"], t["num"],
                                        splits=parts if len(parts) > 1 else None,
                                        category=parts[0]["category"] if len(parts) == 1 else None,
                                        transfer_to=parts[0]["transfer_to"] if len(parts) == 1 else None))
    return accounts


def _pair_transfers(accounts):
    """Exports that don't name the other side of a transfer (Mint): an entry in a
    transfer or card-payment category matched with the opposite amount in another
    account within 3 days becomes a transfer between the two."""
    import datetime as dt
    loose = [r for a in accounts.values() for r in a["rows"]
             if not r["transfer_to"] and r["category"] and any(w in r["category"].lower() for w in TRANSFER_WORDS)]
    used = set()
    for i, r in enumerate(loose):
        if i in used:
            continue
        d = dt.date.fromisoformat(r["date"])
        for j in range(i + 1, len(loose)):
            o = loose[j]
            if j in used or o["account"] == r["account"] or o["amount"] != -r["amount"]:
                continue
            if abs((dt.date.fromisoformat(o["date"]) - d).days) <= 3:
                r["transfer_to"], o["transfer_to"] = o["account"], r["account"]
                r["category"] = o["category"] = None
                used.update((i, j))
                break


# ----- preview and bringing it in ---------------------------------------------------------
def read(files):
    """One or more exported files (Microsoft Money writes one account per QIF file) as
    one set of accounts. `files`: [{"filename", "content" (base64)}]."""
    if not isinstance(files, list) or not files:
        raise ApiError("Choose the exported file (or files) first")
    out = {"format": "", "accounts": {}, "kinds": {}, "skipped": {}}
    formats = []
    for f in files[:50]:
        try:
            one = read_one(f.get("filename"), f.get("content"))
        except ApiError as e:
            raise ApiError(f"{f.get('filename') or 'A file'}: {e}")
        formats.append(one["format"])
        for k, a in one["accounts"].items():
            have = next((x for x in out["accounts"] if x.lower() == k.lower()), None)
            if have:   # the same account in two files: its entries together
                out["accounts"][have]["rows"] += a["rows"]
                if out["accounts"][have]["opening"] is None:
                    out["accounts"][have].update(opening=a["opening"], opening_date=a["opening_date"])
            else:
                out["accounts"][k] = a
        out["kinds"].update(one["kinds"])
        for k, v in one["skipped"].items():
            out["skipped"][k] = out["skipped"].get(k, 0) + v
    out["format"] = " + ".join(sorted(set(formats)))
    return out


def missing_targets(p):
    """Accounts that transfers name but that aren't among the accounts read (a file not
    chosen, or an account named differently in another file): name -> how many."""
    have = {k.lower() for k in p["accounts"]}
    miss = {}
    for a in p["accounts"].values():
        for r in a["rows"]:
            for part in (r["splits"] or [r]):
                t = part.get("transfer_to")
                if t and t.lower() not in have:
                    miss[t] = miss.get(t, 0) + 1
    return miss


def read_one(filename, content_b64):
    try:
        raw = base64.b64decode(content_b64 or "", validate=False)
    except Exception:
        raise ApiError("The file couldn't be read")
    if not raw:
        raise ApiError("The file is empty")
    text = decode(raw)
    name = (filename or "").lower()
    if name.endswith(".qif") or text.lstrip().startswith("!"):
        base = re.sub(r"\.qif$", "", (filename or "Imported account").rsplit("/", 1)[-1].rsplit("\\", 1)[-1], flags=re.I)
        accounts, kinds, skipped = parse_qif_all(text, base or "Imported account")
        return {"format": "QIF", "accounts": accounts, "kinds": kinds, "skipped": skipped}
    # Name the kind of file it really is (never guess "CSV" for something else).
    head = text[:4096].upper()
    if re.search(r"\.(ofx|qfx|qbo)$", name) or "OFXHEADER" in head or "<OFX>" in head:
        raise ApiError("This OFX file is a single-account bank download, not a full export from another "
                       "program. To bring in one account, use Import file in that account's register instead.")
    if raw[:4] in (b"%PDF", b"PK\x03\x04") or (b"\x00" in raw[:4096] and raw[:2] not in (b"\xff\xfe", b"\xfe\xff")):
        raise ApiError("This file isn't a QIF or CSV export. Move in reads QIF files (Microsoft Money, "
                       "Quicken, Moneydance) and CSV exports with an Account column.")
    accounts, fmt = parse_csv_all(text)
    if not accounts:
        raise ApiError("No accounts or transactions found in this file")
    return {"format": fmt, "accounts": accounts, "kinds": {}, "skipped": {}}


def _categories_used(parsed):
    used = {}
    for a in parsed["accounts"].values():
        for r in a["rows"]:
            for part in (r["splits"] or [r]):
                c = part.get("category")
                if c:
                    used[c] = used.get(c, 0) + part["amount"]
    return used


def _apply_aliases(p, aliases):
    """'Checking (old name)' -> an account read from the files: transfers to it pair up."""
    keys = {k.lower(): k for k in p["accounts"]}
    amap = {str(n).lower(): keys.get(str(v).lower()) for n, v in (aliases or {}).items() if v}
    if not amap:
        return
    for a in p["accounts"].values():
        for r in a["rows"]:
            for part in (r["splits"] or [r]):
                t = part.get("transfer_to")
                if t and amap.get(t.lower()):
                    part["transfer_to"] = amap[t.lower()]


def preview(store, files, aliases=None):
    p = read(files)
    _apply_aliases(p, aliases)
    mine = {a["name"].lower(): a for a in store.accounts()}
    accounts = []
    for key, a in p["accounts"].items():
        dates = [r["date"] for r in a["rows"]]
        accounts.append({"key": key, "name": a["name"], "type": a["type"], "count": len(a["rows"]),
                         "first": min(dates) if dates else a["opening_date"], "last": max(dates) if dates else a["opening_date"],
                         "opening": a["opening"] or 0,
                         "balance": (a["opening"] or 0) + sum(r["amount"] for r in a["rows"]),
                         "transfers": sum(1 for r in a["rows"] if r["transfer_to"]),
                         "splits": sum(1 for r in a["rows"] if r["splits"]),
                         "same_name_id": (mine.get(a["name"].lower()) or {}).get("id")})
    accounts.sort(key=lambda x: (-x["count"], x["name"].lower()))
    new_cats = sorted(c for c in _categories_used(p) if not match_category(store, c))
    return {"format": p["format"], "accounts": accounts, "new_categories": new_cats,
            "skipped": {k: v for k, v in p["skipped"].items() if v},
            "transactions": sum(a["count"] for a in accounts),
            "missing_transfer_accounts": [{"name": n, "count": c} for n, c in sorted(missing_targets(p).items())]}


def _ensure_category(store, path, kind, made):
    """A category for 'Parent:Child' (deeper levels fold into the child's name)."""
    cid = match_category(store, path)
    if cid:
        return cid
    parts = [x.strip() for x in path.replace(" : ", ":").split(":") if x.strip()]
    if not parts:
        return None
    parent_name, child = parts[0], " : ".join(parts[1:])
    parent = next((c for c in store.categories() if not c["parent_id"] and c["name"].lower() == parent_name.lower()), None)
    if not parent:
        pid = store.save_category({"name": parent_name, "kind": kind})
        made.append(parent_name)
    else:
        pid = parent["id"]
    if not child:
        return pid
    cid = store.save_category({"name": child, "parent_id": pid})
    made.append(f"{parent_name} : {child}")
    return cid


def bring_in(store, files, choices, aliases=None):
    """choices: {account key: {"to": "new" | "skip" | <account id>, "type": "Checking"...}};
    aliases: {name transfers use: account key} for names that differ between files."""
    p = read(files)
    _apply_aliases(p, aliases)
    choices = choices or {}
    target, created = {}, []
    for key, a in p["accounts"].items():
        ch = choices.get(key) or {"to": "new"}
        to = ch.get("to", "new")
        if to == "skip":
            continue
        if to == "new":
            name, n = a["name"], 2
            while any(x["name"].lower() == name.lower() for x in store.accounts()):
                name, n = f"{a['name']} ({n})", n + 1
            # (an investment account with none of its own entries starts at the first transfer to it)
            named = [r["date"] for b in p["accounts"].values() for r in b["rows"]
                     for part in (r["splits"] or [r]) if (part.get("transfer_to") or "").lower() == a["name"].lower()]
            first = min([r["date"] for r in a["rows"]] + ([a["opening_date"]] if a["opening_date"] else []) + named
                        or [dt.date.today().isoformat()])
            typ = ch.get("type") or a["type"]
            # (an HSA by its name: marked as one, for the tax report; its details can say more)
            hsa = any(w in " " + a["name"].lower() for w in (" hsa", "health savings")) and typ not in defaults.LIABILITY_TYPES
            aid = store.save_account({"name": name, "type": typ, **({"details": {"hsa": True}} if hsa else {}),
                                      "opening_balance": f"{(a['opening'] or 0) / 100:.2f}",
                                      "opening_date": a["opening_date"] or first})
            created.append(name)
            target[key] = (aid, True)
        else:
            store.account(int(to))
            target[key] = (int(to), False)
    by_name = {k.lower(): v for k, v in target.items()}
    used = _categories_used(p)
    kinds = {k: v for k, v in p["kinds"].items()}
    cat_ids, made = {}, []

    def cat_id(path):
        if not path:
            return None
        if path not in cat_ids:
            kind = kinds.get(path) or kinds.get(path.split(":")[0]) or ("income" if used.get(path, 0) > 0 else "expense")
            cat_ids[path] = _ensure_category(store, path, kind, made)
        return cat_ids[path]

    counts = {"accounts": len(created), "added": 0, "transfers": 0, "duplicates": 0, "unmatched_transfers": 0}
    pending = {}   # transfers created, waiting for their other half: (src, dst, date, amount for dst) -> n

    def take_mirror(src, dst, date, amount):
        """True when this row is the other half of a transfer already made."""
        import datetime as dt
        src, dst = src.lower(), dst.lower()
        for k, n in pending.items():
            if n and k[0] == dst and k[1] == src and k[3] == amount and \
                    abs((dt.date.fromisoformat(k[2]) - dt.date.fromisoformat(date)).days) <= 3:
                pending[k] -= 1
                return True
        return False

    for key, a in p["accounts"].items():
        if key not in target:
            continue
        aid, fresh = target[key]
        # Into an account that already has entries: what's there already isn't added again.
        # Plain entries match by date, amount and payee; transfers by date, amount and the
        # other account (their payee may differ between the two sides); splits by their total.
        seen, seen_x, seen_g = set(), set(), set()
        if not fresh:
            have = store.transactions(account_id=aid, limit=1000000)
            groups = {}
            for t in have:
                seen.add((t["date"], t["amount"], (t["payee"] or "").lower()))
                if t.get("transfer_account_id") and not t["group_id"]:
                    seen_x.add((t["date"], t["amount"], t["transfer_account_id"]))
                if t["group_id"]:
                    g = groups.setdefault(t["group_id"], [t["date"], 0, (t["payee"] or "").lower()])
                    g[1] += t["amount"]
            seen_g = {tuple(g) for g in groups.values()}
        for r in a["rows"]:
            other_acct = by_name.get((r["transfer_to"] or "").lower())
            if (r["splits"] and (r["date"], r["amount"], r["payee"].lower()) in seen_g) or \
                    (not r["splits"] and other_acct and (r["date"], r["amount"], other_acct[0]) in seen_x) or \
                    (not r["splits"] and not r["transfer_to"] and (r["date"], r["amount"], r["payee"].lower()) in seen):
                counts["duplicates"] += 1
                continue
            base = {"account_id": aid, "date": r["date"], "payee": r["payee"], "number": r["number"],
                    "status": r["status"]}
            parts = r["splits"] or [{"category": r["category"], "transfer_to": r["transfer_to"], "memo": r["memo"],
                                     "amount": r["amount"]}]
            ids = []
            for part in parts:
                tx = dict(base, amount_cents=part["amount"], memo=part.get("memo") or (r["memo"] if r["splits"] else r["memo"]))
                other = part.get("transfer_to")
                if other:
                    o = by_name.get(other.lower())
                    if o:
                        if take_mirror(key, other, r["date"], part["amount"]):
                            continue   # the other account already made this transfer
                        tx["transfer_account_id"] = o[0]
                        pk = (key.lower(), other.lower(), r["date"], -part["amount"])
                        pending[pk] = pending.get(pk, 0) + 1
                        counts["transfers"] += 1
                    else:
                        tx["memo"] = (f"Transfer {'to' if part['amount'] < 0 else 'from'} {other}"
                                      + (f" · {tx['memo']}" if tx["memo"] else ""))
                        counts["unmatched_transfers"] += 1
                else:
                    tx["category_id"] = cat_id(part.get("category"))
                if not tx["amount_cents"]:
                    continue
                ids.append(store.save_transaction(tx))
            if len(ids) > 1:
                with store.lock:
                    gid = store.q1("SELECT COALESCE(MAX(group_id),0)+1 AS g FROM transactions")["g"]
                    store.db.execute(f"UPDATE transactions SET group_id=? WHERE id IN ({','.join('?' * len(ids))})",
                                     [gid] + ids)
                    store.db.commit()
            counts["added"] += len(ids) > 0
    counts["categories"] = len(made)
    counts["created_accounts"] = created
    return counts
