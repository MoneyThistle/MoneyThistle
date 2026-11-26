"""The money file: accounts, transactions, categories, bills, budget and settings.

Everything lives in one SQLite file. Amounts are stored in cents: a positive
amount puts money into an account, a negative one takes it out.
"""

import calendar
import datetime as dt
import json
import os
import re
import sqlite3
import tempfile
import threading
import time

from . import currencies, defaults

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    opening_balance INTEGER NOT NULL DEFAULT 0,
    opening_date TEXT NOT NULL,
    closed INTEGER NOT NULL DEFAULT 0,
    favorite INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    reconciled_balance INTEGER,
    reconciled_date TEXT
);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,            -- income | expense | none
    tax_related INTEGER NOT NULL DEFAULT 0,
    in_budget INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    number TEXT NOT NULL DEFAULT '',
    payee TEXT NOT NULL DEFAULT '',
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    memo TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT '',   -- '' | C (cleared) | R (reconciled)
    transfer_id INTEGER,
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tx_account_date ON transactions(account_id, date);
CREATE INDEX IF NOT EXISTS tx_category ON transactions(category_id);
CREATE TABLE IF NOT EXISTS payees (
    name TEXT PRIMARY KEY COLLATE NOCASE,
    category_id INTEGER,
    last_amount INTEGER,
    used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,              -- bill | deposit | transfer
    payee TEXT NOT NULL DEFAULT '',
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    to_account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    amount INTEGER NOT NULL,         -- always positive
    frequency TEXT NOT NULL,
    next_date TEXT NOT NULL,
    anchor_day INTEGER NOT NULL,
    memo TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS budget (
    category_id INTEGER PRIMARY KEY REFERENCES categories(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL           -- per month, cents
);
CREATE TABLE IF NOT EXISTS loans (
    account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    original_amount INTEGER NOT NULL,     -- cents
    apr REAL NOT NULL,                    -- percent per year
    payments_per_year INTEGER NOT NULL,
    num_payments INTEGER NOT NULL,
    first_payment TEXT NOT NULL,
    payment_mode TEXT NOT NULL,           -- calc | fixed
    payment INTEGER NOT NULL,             -- principal + interest per payment, cents
    escrow INTEGER NOT NULL DEFAULT 0,    -- per payment, cents
    escrow_category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    escrow_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    interest_category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    pay_from_account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    payee TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS backup_log (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    destination TEXT NOT NULL,
    name TEXT NOT NULL,
    ok INTEGER NOT NULL,
    message TEXT NOT NULL DEFAULT ''
);
"""


class ApiError(Exception):
    """A message for the person. `field` names the form field it's about (the screen
    marks that field and puts the cursor there)."""

    def __init__(self, message, status=400, field=None):
        super().__init__(message)
        self.status = status
        self.field = field


class about:
    """`with about("due_day"):` tags any ApiError raised inside with that field."""

    def __init__(self, field):
        self.field = field

    def __enter__(self):
        return self

    def __exit__(self, typ, err, tb):
        if isinstance(err, ApiError) and not err.field:
            err.field = self.field
        return False


# Connection.serialize() came with Python 3.11; 3.10 copies through a temporary file instead.
_SERIALIZE = hasattr(sqlite3.Connection, "serialize")


def db_bytes(conn):
    """A consistent copy of a whole SQLite database, as bytes (for backups)."""
    if _SERIALIZE:
        mem = sqlite3.connect(":memory:")
        try:
            conn.backup(mem)
            return bytes(mem.serialize())
        finally:
            mem.close()
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        dst = sqlite3.connect(tmp)
        try:
            conn.backup(dst)
        finally:
            dst.close()
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def today():
    return dt.date.today()


def parse_date(s, field="date"):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except Exception:
        raise ApiError(f"'{field}' must be a date like 2026-01-31")


def normalize_number(v):
    """An amount as typed, in any of the styles used in the Americas and Europe, as plain
    digits with a decimal point: "$1,234.56", "R$ 1.234,56", "1 234,56", "1234,5", "(12.00)".
    The last of "," and "." is the decimal mark when both appear; one alone is the decimal
    mark unless exactly three digits follow it (then it groups thousands: "1,080", "1.080")."""
    s = re.sub(r"[^\d,.\-()]", "", str(v))
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s or "." in s:
        mark = "," if "," in s else "."
        parts = s.split(mark)
        if len(parts) > 2 or len(parts[-1].rstrip(")")) == 3:
            s = s.replace(mark, "")
        else:
            s = s.replace(",", ".")
    return s


def to_cents(v, field="amount"):
    if v is None or v == "":
        return 0
    try:
        s = normalize_number(v)
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()")
        cents = int(round(float(s) * 100))
        return -cents if neg else cents
    except Exception:
        raise ApiError(f"'{field}' must be a number")


def add_months(d, months, day=None):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, min(day or d.day, last))


# Frequencies counted in whole months: these can fall on the last day of the month.
MONTH_BASED = ("Monthly", "Every other month", "Every three months", "Twice a year", "Yearly", "Every other year")


def next_occurrence(d, frequency, anchor_day):
    """The date after d for a bill repeating at this frequency (None = done)."""
    if frequency == "Daily":
        return d + dt.timedelta(days=1)
    if frequency == "Weekly":
        return d + dt.timedelta(weeks=1)
    if frequency == "Every other week":
        return d + dt.timedelta(weeks=2)
    if frequency == "Every four weeks":
        return d + dt.timedelta(weeks=4)
    if frequency == "Twice a month":
        # Two dates a month, 15 days apart: e.g. the 1st and 16th, or the 15th and 30th.
        low, high = (anchor_day, anchor_day + 15) if anchor_day <= 15 else (anchor_day - 15, anchor_day)
        month_len = calendar.monthrange(d.year, d.month)[1]
        if d.day < min(high, month_len):
            return dt.date(d.year, d.month, min(high, month_len))
        return add_months(dt.date(d.year, d.month, 1), 1, low)
    if frequency == "Monthly":
        return add_months(d, 1, anchor_day)
    if frequency == "Every other month":
        return add_months(d, 2, anchor_day)
    if frequency == "Every three months":
        return add_months(d, 3, anchor_day)
    if frequency == "Twice a year":
        return add_months(d, 6, anchor_day)
    if frequency == "Yearly":
        return add_months(d, 12, anchor_day)
    if frequency == "Every other year":
        return add_months(d, 24, anchor_day)
    return None  # Only once


def guess_frequency(dates):
    """How often something repeats, from its dates (ISO, oldest first, one per time it
    happened): the median gap of the last 12 (see MECHANICS.md, "Schedule… from a register
    entry"). Returns (frequency, last day of the month)."""
    if len(dates) < 2:
        return "Monthly", False
    ds = [dt.date.fromisoformat(d) for d in dates]
    gaps = [g for g in ((b - a).days for a, b in zip(ds, ds[1:])) if g > 0][-12:]
    if not gaps:
        return "Monthly", False
    med = sorted(gaps)[len(gaps) // 2]
    recent = ds[-6:]
    month_end = all(d.day == calendar.monthrange(d.year, d.month)[1] for d in recent)
    if med <= 3:
        f = "Daily"
    elif med <= 10:
        f = "Weekly"
    elif med <= 18:
        # Every 14 days exactly, or the same few days of the month (the 1st and the 15th)?
        f = "Every other week" if all(g == 14 for g in gaps) else \
            ("Twice a month" if len({d.day for d in recent}) <= 3 else "Every other week")
    elif med <= 29 and all(g == 28 for g in gaps):
        f = "Every four weeks"
    elif med <= 45:
        f = "Monthly"
    elif med <= 75:
        f = "Every other month"
    elif med <= 120:
        f = "Every three months"
    elif med <= 250:
        f = "Twice a year"
    elif med <= 500:
        f = "Yearly"
    else:
        f = "Every other year"
    return f, month_end and f in MONTH_BASED[:5]


DEFAULT_BACKUP = {
    # Original defaults (mnyob99.dll 0x242a8afc): back up on close, keep 3,
    # compress, scheduled backup every 14 days, keep 3.
    "on_change": True,
    "keep_change": 3,
    "idle_minutes": 5,
    "scheduled": True,
    "interval_days": 14,
    "keep_scheduled": 3,
    # Kept on top of those (a daily / weekly / monthly rotation): the last backup of each
    # of the latest 7 days, 4 weeks and 12 months that have one.
    "keep_daily": 7,
    "keep_weekly": 4,
    "keep_monthly": 12,
    "compress": True,
    "local_enabled": True,
    "local_dir": "",
    "webdav_enabled": False,
    "webdav_url": "",
    "webdav_user": "",
    "webdav_password": "",
    "last_scheduled": None,
}


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.dirty_since = None      # time of the first change not yet backed up
        self.last_change = None
        self._open()

    # ----- connection -------------------------------------------------
    def _open(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._migrate()
        if not self.db.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
            self._seed_categories()
        self.db.commit()
        self._add_new_categories()
        self._name_starting_categories()
        # fx(amount, account_id): an amount in this file's main currency, for totals across
        # accounts (see _fx_load); NULL, so SUM leaves it out, when there's no rough rate.
        self._fx = None
        self.db.create_function("fx", 2, self._fx_sql, deterministic=True)

    # ----- currencies ---------------------------------------------------
    def money_settings(self):
        """The main currency (totals and the budget are in it) and the rough rates typed in
        for the others: {"home": "USD", "rates": {"BRL": "0.18"}} (1 BRL ≈ 0.18 USD)."""
        rates = self.get_setting("rough_rates", {}) or {}
        return {"home": self.get_setting("home_currency", currencies.DEFAULT) or currencies.DEFAULT,
                "rates": {k: v for k, v in rates.items() if k in currencies.CODES and v}}

    def set_money_settings(self, data):
        ms = self.money_settings()
        with about("home"):
            try:
                home = currencies.clean_code(data.get("home"), ms["home"]) if "home" in data else ms["home"]
            except ValueError as e:
                raise ApiError(str(e))
        rates = dict(ms["rates"])
        for code, v in (data.get("rates") or {}).items():
            with about("rate_" + str(code)):
                try:
                    code = currencies.clean_code(code)
                    rates[code] = currencies.clean_rate(v)
                except ValueError as e:
                    raise ApiError(str(e))
        rates = {k: v for k, v in rates.items() if v and k != home}
        with self.lock:
            self.set_setting("home_currency", home)
            self.set_setting("rough_rates", rates)
            self._fx = None
            self.changed()
        return self.money_settings()

    def _fx_load(self):
        ms = self.money_settings()
        rates = {k: float(v) for k, v in ms["rates"].items()}
        rates[ms["home"]] = 1.0
        self._fx = ({r["id"]: rates.get(r["currency"]) for r in
                     self.db.execute("SELECT id, currency FROM accounts").fetchall()}, ms["home"])
        return self._fx

    def _fx_sql(self, amount, account_id):
        if amount is None:
            return None
        fx = self._fx or self._fx_load()
        if account_id not in fx[0]:
            fx = self._fx_load()   # an account added since
        k = fx[0].get(account_id, 1.0)
        return None if k is None else (amount if k == 1.0 else int(round(amount * k)))

    def to_home(self, cents, code):
        """An amount in another currency, in the main one (rough rate); None without a rate."""
        ms = self.money_settings()
        if code == ms["home"]:
            return cents
        r = ms["rates"].get(code)
        return int(round(cents * float(r))) if r else None

    def _migrate(self):
        """Add columns that newer versions use to money files made by older ones."""
        def cols(table):
            return {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
        if "group_id" not in cols("transactions"):
            # Lines of one payment (e.g. principal + interest + escrow) share a group.
            self.db.execute("ALTER TABLE transactions ADD COLUMN group_id INTEGER")
        if "loan_account_id" not in cols("bills"):
            self.db.execute("ALTER TABLE bills ADD COLUMN loan_account_id INTEGER")
        if "xlink_id" not in cols("transactions"):
            # Transfers with an account in another environment: the connection and the
            # id of the mirror entry in that environment's money file.
            self.db.execute("ALTER TABLE transactions ADD COLUMN xlink_id INTEGER")
            self.db.execute("ALTER TABLE transactions ADD COLUMN xtx_id INTEGER")
        if "amount_mode" not in cols("bills"):
            # fixed = same each time; average = the amount varies: expect the average
            # of the last `average_count` recorded amounts (the estimate until then).
            self.db.execute("ALTER TABLE bills ADD COLUMN amount_mode TEXT NOT NULL DEFAULT 'fixed'")
            self.db.execute("ALTER TABLE bills ADD COLUMN average_count INTEGER NOT NULL DEFAULT 12")
        if "x_link_id" not in cols("bills"):
            # Scheduled transfers with an account in another environment (through a
            # connection): which one, which way ('out' leaves account_id, 'in' arrives),
            # and the other account's name for display.
            self.db.execute("ALTER TABLE bills ADD COLUMN x_link_id INTEGER")
            self.db.execute("ALTER TABLE bills ADD COLUMN x_dir TEXT")
            self.db.execute("ALTER TABLE bills ADD COLUMN x_label TEXT")
        if "details" not in cols("accounts"):
            # Optional account details (bank, numbers, rates, card due day...) as JSON.
            self.db.execute("ALTER TABLE accounts ADD COLUMN details TEXT NOT NULL DEFAULT '{}'")
        if "auto" not in cols("bills"):
            # auto: it happens by itself (autopay, automatic transfer, direct deposit);
            # auto_enter: MoneyThistle records it in the register on its date.
            self.db.execute("ALTER TABLE bills ADD COLUMN auto INTEGER NOT NULL DEFAULT 0")
            self.db.execute("ALTER TABLE bills ADD COLUMN auto_enter INTEGER NOT NULL DEFAULT 0")
        if "fitid" not in cols("transactions"):
            # The bank's own id for an imported entry (OFX FITID): never imported twice.
            self.db.execute("ALTER TABLE transactions ADD COLUMN fitid TEXT")
        if "seq" not in cols("transactions"):
            # Order within a day in a register (moved by the person; 0 = as entered).
            self.db.execute("ALTER TABLE transactions ADD COLUMN seq INTEGER NOT NULL DEFAULT 0")
        if "auto" not in cols("transactions"):
            # Entries MoneyThistle recorded by itself from an automatic scheduled item.
            self.db.execute("ALTER TABLE transactions ADD COLUMN auto INTEGER NOT NULL DEFAULT 0")
        if "tax_year" not in cols("transactions"):
            # An HSA contribution made Jan 1 - Apr 15 can count for the year before.
            self.db.execute("ALTER TABLE transactions ADD COLUMN tax_year INTEGER")
        if "card_account_id" not in cols("bills"):
            # The scheduled payment a credit card's details keep up to date.
            self.db.execute("ALTER TABLE bills ADD COLUMN card_account_id INTEGER")
        # Paystubs: a paycheck's earnings, taxes and deductions (see paystubs.py); its
        # entries are one group in the account the pay went into.
        self.db.execute("CREATE TABLE IF NOT EXISTS paystubs (group_id INTEGER PRIMARY KEY, "
                        "account_id INTEGER NOT NULL, employer TEXT NOT NULL DEFAULT '', date TEXT NOT NULL, "
                        "gross INTEGER NOT NULL, net INTEGER NOT NULL, net_category_id INTEGER, "
                        "lines TEXT NOT NULL DEFAULT '{}', bill_id INTEGER)")
        # Receipts and other files kept with entries (see attachments.py).
        from . import attachments
        attachments.migrate(self.db)
        # Paychecks: a scheduled deposit can be a paycheck; an entry recorded with only its
        # take-home pay is one (1, or 2 once marked complete as is); a paystub can be marked
        # complete as is too. See paystubs.paychecks().
        if "paycheck" not in cols("bills"):
            self.db.execute("ALTER TABLE bills ADD COLUMN paycheck INTEGER NOT NULL DEFAULT 0")
        if "paycheck" not in cols("transactions"):
            self.db.execute("ALTER TABLE transactions ADD COLUMN paycheck INTEGER")
        if "complete" not in cols("paystubs"):
            self.db.execute("ALTER TABLE paystubs ADD COLUMN complete INTEGER NOT NULL DEFAULT 0")
        # Currencies: each account's own (see currencies.py); a scheduled transfer between two
        # currencies can say what usually arrives.
        if "currency" not in cols("accounts"):
            self.db.execute("ALTER TABLE accounts ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'")
        if "received" not in cols("bills"):
            self.db.execute("ALTER TABLE bills ADD COLUMN received INTEGER")
        # A deposit into more than one account (a paycheck split by direct deposit): each other
        # account has its own scheduled deposit, with its own amount (set or averaged), kept on
        # the same dates as the main one and entered with it (split_of: the main one).
        if "split_of" not in cols("bills"):
            self.db.execute("ALTER TABLE bills ADD COLUMN split_of INTEGER REFERENCES bills(id) ON DELETE CASCADE")
        # A category's name in each language (see category_names()).
        self.db.execute("CREATE TABLE IF NOT EXISTS category_names (category_id INTEGER NOT NULL "
                        "REFERENCES categories(id) ON DELETE CASCADE, lang TEXT NOT NULL, name TEXT NOT NULL, "
                        "PRIMARY KEY (category_id, lang))")
        self.db.execute("CREATE TABLE IF NOT EXISTS bill_history (id INTEGER PRIMARY KEY, "
                        "bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE, "
                        "date TEXT NOT NULL, amount INTEGER NOT NULL, transaction_id INTEGER)")

    def close(self):
        with self.lock:
            self.db.close()

    def reopen(self):
        with self.lock:
            self._open()

    def snapshot_bytes(self):
        """A consistent copy of the whole money file."""
        with self.lock:
            # Every change is finished before the lock is let go, so one still open here
            # was left behind by mistake: finish it, or the copy below waits for it forever.
            if self.db.in_transaction:
                self.db.commit()
            return db_bytes(self.db)

    def changed(self):
        now = time.time()
        if self.dirty_since is None:
            self.dirty_since = now
        self.last_change = now

    # One connection is shared by the web server's threads, so reads take the same
    # lock as writes (two at once can fail with "bad parameter or other API misuse").
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def q1(self, sql, args=()):
        with self.lock:
            r = self.db.execute(sql, args).fetchone()
            return dict(r) if r else None

    # ----- settings ----------------------------------------------------
    def get_setting(self, key, default=None):
        r = self.q1("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(r["value"]) if r else default

    def set_setting(self, key, value):
        with self.lock:
            self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                            (key, json.dumps(value)))
            self.db.commit()

    def backup_settings(self):
        s = dict(DEFAULT_BACKUP)
        s.update(self.get_setting("backup", {}) or {})
        return s

    # ----- categories ---------------------------------------------------
    def _seed_categories(self):
        def add(name, kind, tax, budget, parent=None):
            cur = self.db.execute(
                "INSERT INTO categories(name,parent_id,kind,tax_related,in_budget) VALUES(?,?,?,?,?)",
                (name, parent, kind, int(tax), int(budget)))
            return cur.lastrowid
        for kind, table in (("income", defaults.INCOME_CATEGORIES),
                            ("expense", defaults.EXPENSE_CATEGORIES)):
            for name, tax, budget, subs in table:
                pid = add(name, kind, tax, budget)
                for sname, stax, sbudget in subs:
                    add(sname, kind, stax, sbudget, pid)
        add(defaults.NOT_AN_EXPENSE, "none", False, False)

    # A category is one category whatever language people use; it can have a name in each
    # language (category_names), shown instead of its own name to people using that language.
    NAME_LANGS = ("en", "fr", "es", "pt")

    def category_names(self):
        """Category id -> {language: name}."""
        out = {}
        for r in self.q("SELECT category_id, lang, name FROM category_names"):
            out.setdefault(r["category_id"], {})[r["lang"]] = r["name"]
        return out

    def _set_category_names(self, cid, names):
        for lang in self.NAME_LANGS:
            if lang not in names:
                continue
            v = str(names.get(lang) or "").strip()[:200]
            if v:
                self.db.execute("INSERT INTO category_names(category_id,lang,name) VALUES(?,?,?) "
                                "ON CONFLICT(category_id,lang) DO UPDATE SET name=excluded.name", (cid, lang, v))
            else:
                self.db.execute("DELETE FROM category_names WHERE category_id=? AND lang=?", (cid, lang))

    def _add_new_categories(self):
        """Once per file and group: the categories added after the first release (defaults.
        ADDED_CATEGORIES), with their names in each language. A new main category is added
        unless one of that name is there; subcategories go under their main category when it's
        still there. One already there (or a main category renamed or deleted) is left be."""
        from .category_names import NAMES
        named = bool(self.get_setting("category_names_v1"))
        for version, parent, new_parent, subs in defaults.ADDED_CATEGORIES:
            if self.get_setting(version):
                continue
            p = self.q1("SELECT * FROM categories WHERE name=? COLLATE NOCASE AND parent_id IS NULL", (parent,))
            if not p and new_parent:
                pid = self.db.execute(
                    "INSERT INTO categories(name,parent_id,kind,tax_related,in_budget) VALUES(?,?,?,?,?)",
                    (parent, None, "expense", int(new_parent[0]), int(new_parent[1]))).lastrowid
                if named:
                    self._set_category_names(pid, NAMES.get(parent) or {})
                p = self.q1("SELECT * FROM categories WHERE id=?", (pid,))
            if p and p["kind"] == "expense":
                have = {r["name"].lower() for r in self.q("SELECT name FROM categories WHERE parent_id=?", (p["id"],))}
                for name, tax, budget in subs:
                    if name.lower() in have:
                        continue
                    cid = self.db.execute(
                        "INSERT INTO categories(name,parent_id,kind,tax_related,in_budget) VALUES(?,?,?,?,?)",
                        (name, p["id"], "expense", int(tax), int(budget))).lastrowid
                    if named:
                        self._set_category_names(cid, NAMES.get(f"{parent} : {name}") or {})
            self.db.execute("INSERT INTO settings(key,value) VALUES(?,'true') "
                            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (version,))
        self.db.commit()

    def _name_starting_categories(self):
        """Give the starting categories (still named as they started) their French, Spanish and
        Portuguese names, once; a name already set by someone is left as it is."""
        if self.get_setting("category_names_v1"):
            return
        from .category_names import NAMES
        cats = {r["id"]: r for r in self.q("SELECT id, name, parent_id FROM categories")}
        have = {(r["category_id"], r["lang"]) for r in self.q("SELECT category_id, lang FROM category_names")}
        for c in cats.values():
            p = cats.get(c["parent_id"]) if c["parent_id"] else None
            key = f"{p['name']} : {c['name']}" if p else c["name"]
            for lang, name in (NAMES.get(key) or {}).items():
                if (c["id"], lang) not in have:
                    self.db.execute("INSERT INTO category_names(category_id,lang,name) VALUES(?,?,?)",
                                    (c["id"], lang, name))
        self.db.execute("INSERT INTO settings(key,value) VALUES('category_names_v1','true') "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        self.db.commit()

    def categories(self):
        rows = self.q("SELECT c.*, p.name AS parent_name FROM categories c "
                      "LEFT JOIN categories p ON p.id=c.parent_id")
        names = self.category_names()
        for r in rows:
            r["full_name"] = f"{r['parent_name']} : {r['name']}" if r["parent_name"] else r["name"]
            r["names"] = names.get(r["id"], {})
            r["used"] = 0
        used = {r["category_id"]: r["n"] for r in self.q(
            "SELECT category_id, COUNT(*) n FROM transactions GROUP BY category_id")}
        for r in rows:
            r["used"] = used.get(r["id"], 0)
        order = {"income": 0, "expense": 1, "none": 2}
        rows.sort(key=lambda r: (order.get(r["kind"], 3),
                                 (r["parent_name"] or r["name"]).lower(),
                                 r["parent_id"] is not None, r["name"].lower()))
        return rows

    def save_category(self, data, cid=None):
        name = (data.get("name") or "").strip()
        if not name:
            raise ApiError("A category needs a name")
        parent = data.get("parent_id") or None
        with self.lock:
            if parent:
                p = self.q1("SELECT * FROM categories WHERE id=?", (parent,))
                if not p or p["parent_id"]:
                    raise ApiError("Subcategories can only go under a main category")
                kind = p["kind"]
            else:
                kind = data.get("kind") or "expense"
                if kind not in ("income", "expense"):
                    raise ApiError("kind must be income or expense")
            vals = (name, parent, kind, int(bool(data.get("tax_related"))),
                    int(bool(data.get("in_budget"))))
            if cid:
                self.db.execute("UPDATE categories SET name=?,parent_id=?,kind=?,tax_related=?,in_budget=? "
                                "WHERE id=?", vals + (cid,))
            else:
                cid = self.db.execute("INSERT INTO categories(name,parent_id,kind,tax_related,in_budget) "
                                      "VALUES(?,?,?,?,?)", vals).lastrowid
            if isinstance(data.get("names"), dict):
                self._set_category_names(cid, data["names"])
            self.db.commit()
            self.changed()
        return cid

    def delete_category(self, cid):
        with self.lock:
            self.db.execute("DELETE FROM categories WHERE id=?", (cid,))
            self.db.commit()
            self.changed()

    # ----- accounts -----------------------------------------------------
    def accounts(self, include_closed=True):
        rows = self.q("SELECT a.*, "
                      "a.opening_balance + COALESCE((SELECT SUM(amount) FROM transactions t "
                      "  WHERE t.account_id=a.id),0) AS balance, "
                      "a.opening_balance + COALESCE((SELECT SUM(amount) FROM transactions t "
                      "  WHERE t.account_id=a.id AND t.status!=''),0) AS cleared_balance, "
                      "(SELECT COUNT(*) FROM transactions t WHERE t.account_id=a.id) AS tx_count, "
                      "EXISTS(SELECT 1 FROM loans l WHERE l.account_id=a.id) AS has_loan "
                      "FROM accounts a ORDER BY a.closed, a.favorite DESC, a.name COLLATE NOCASE")
        for r in rows:
            r["liability"] = r["type"] in defaults.LIABILITY_TYPES
            try:
                r["details"] = json.loads(r.get("details") or "{}")
            except ValueError:
                r["details"] = {}
        if not include_closed:
            rows = [r for r in rows if not r["closed"]]
        return rows

    # Account details: all optional. Text fields are kept as typed (trimmed, bounded);
    # numbers are checked. Card fields only apply to credit cards and lines of credit.
    DETAIL_TEXT = {"institution": 120, "account_number": 40, "routing_number": 20, "website": 300,
                   "phone": 40, "contact": 300}
    CARD_TYPES = ("Credit Card", "Line of Credit")
    # Accounts whose value moves with what they hold: their value is typed in now and then
    # ("Update value"); investment and retirement accounts are reminded about monthly.
    VALUE_TYPES = ("Investment", "Retirement", "Asset")
    VALUE_REMIND_TYPES = ("Investment", "Retirement")
    VALUE_CATEGORY = "Change in Value"

    def _clean_details(self, typ, d):
        if not isinstance(d, dict):
            raise ApiError("Account details must be an object")
        out = {}
        for k, n in self.DETAIL_TEXT.items():
            v = str(d.get(k) or "").strip()
            if len(v) > n:
                raise ApiError(f"{k.replace('_', ' ').capitalize()} is too long", field=k)
            if v:
                out[k] = v
        if out.get("website"):
            # Only web addresses: "chase.com" becomes https://chase.com; anything else is refused.
            w = out["website"]
            if not re.match(r"(?i)^https?://", w):
                if ":" in w.split("/")[0] or not re.match(r"^[\w.-]+\.[a-z]{2,}", w, re.I):
                    raise ApiError("The website must be a web address, like https://www.example.com", field="website")
                w = "https://" + w
            if re.search(r"\s", w):
                raise ApiError("The website must be a web address, like https://www.example.com", field="website")
            out["website"] = w
        if d.get("routing_number") and not re.fullmatch(r"\d{9}", out.get("routing_number", "")):
            raise ApiError("A routing number has 9 digits", field="routing_number")
        if d.get("interest_rate") not in (None, ""):
            try:
                rate = float(str(d["interest_rate"]).replace("%", ""))
            except ValueError:
                raise ApiError("Interest rate must be a number, like 4.25", field="interest_rate")
            if not 0 <= rate <= 100:
                raise ApiError("Interest rate must be between 0 and 100", field="interest_rate")
            out["interest_rate"] = rate
        if typ not in defaults.LIABILITY_TYPES and d.get("hsa"):
            # A Health Savings Account: its money in and out is gathered for the tax report.
            # Who puts money in decides how it's taxed: you, after tax (you deduct it), or
            # your employer / payroll, before tax (it's on your W-2).
            out["hsa"] = True
            src = d.get("hsa_source") or "personal"
            if src not in ("personal", "employer"):
                raise ApiError("HSA contributions come from you or from your employer", field="hsa_source")
            out["hsa_source"] = src
        if typ in self.CARD_TYPES:
            # A card kept for one kind of spending (HSA-eligible, giving...): its charges and
            # statements go in that category unless another is chosen.
            pc = d.get("purpose_category_id")
            if pc not in (None, "", 0, "0"):
                try:
                    pc = int(pc)
                except (TypeError, ValueError):
                    raise ApiError("Choose a category for what the card is used for", field="purpose_category_id")
                if not self.q1("SELECT 1 FROM categories WHERE id=?", (pc,)):
                    raise ApiError("That category doesn't exist", field="purpose_category_id")
                out["purpose_category_id"] = pc
            if d.get("credit_limit") not in (None, ""):
                with about("credit_limit"):
                    out["credit_limit"] = abs(to_cents(d["credit_limit"], "Credit limit"))
            for k, label in (("statement_day", "Statement closing day"), ("due_day", "Payment due day")):
                if d.get(k) not in (None, ""):
                    try:
                        day = int(d[k])
                    except (TypeError, ValueError):
                        raise ApiError(f"{label} must be a day of the month (1-31)", field=k)
                    if not 1 <= day <= 31:
                        raise ApiError(f"{label} must be a day of the month (1-31)", field=k)
                    out[k] = day
            # How the card is kept: each purchase entered, or one statement balance a month.
            mode = d.get("card_mode") or ("purchases" if d.get("track_purchases") else "statement")
            if mode not in ("purchases", "statement"):
                raise ApiError("A card is kept by purchases or by statement balance", field="card_mode")
            out["card_mode"] = mode
            out["track_purchases"] = mode == "purchases"
            if isinstance(d.get("last_statement"), dict):
                out["last_statement"] = d["last_statement"]   # kept as MoneyThistle wrote it
            out["auto_pay"] = bool(d.get("auto_pay"))
            if out["auto_pay"]:
                if not out.get("due_day"):
                    raise ApiError("To keep the card payment on the schedule, enter the day the payment is due", field="due_day")
                src = int(d.get("pay_from_account_id") or 0)
                if not src or not self.q1("SELECT 1 FROM accounts WHERE id=?", (src,)):
                    raise ApiError("Choose the account the card payment comes from", field="pay_from_account_id")
                out["pay_from_account_id"] = src
                mode = d.get("pay_mode") or "varies"
                if mode not in ("full", "fixed", "varies"):
                    raise ApiError("Payment amount must be full, fixed or varies", field="pay_mode")
                out["pay_mode"] = mode
                with about("pay_amount"):
                    amt = abs(to_cents(d.get("pay_amount") or 0, "Payment amount"))
                if mode == "fixed" and not amt:
                    raise ApiError("Enter the amount you pay each month (or choose \"It varies\")", field="pay_amount")
                out["pay_amount"] = amt
        if typ in self.VALUE_TYPES:
            # The monthly reminder to update the value: on for investments unless turned off.
            if "value_reminder" in d:
                out["value_reminder"] = bool(d.get("value_reminder"))
            if isinstance(d.get("last_value"), dict):
                out["last_value"] = d["last_value"]   # kept as MoneyThistle wrote it
        return out

    # ----- credit cards kept by statement balance --------------------------------
    @staticmethod
    def last_closing(day, on_or_before=None):
        """The latest statement closing date (day of month, the month's last day when
        shorter) on or before a date (default today)."""
        t = on_or_before or today()
        d = t.replace(day=min(day, calendar.monthrange(t.year, t.month)[1]))
        return d if d <= t else add_months(t.replace(day=1), -1, day)

    def balance_on(self, aid, date):
        """An account's balance at the end of a day."""
        a = self.q1("SELECT opening_balance, opening_date FROM accounts WHERE id=?", (aid,))
        if not a:
            raise ApiError("No such account", 404)
        start = a["opening_balance"] if a["opening_date"] <= date else 0
        return start + self.q1("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE account_id=? AND date<=?",
                               (aid, date))["s"]

    def enter_statement(self, aid, date, balance, category_id=None):
        """For a card kept by statement balance: one entry on the statement date that
        makes the card owe exactly the statement balance on that day (the purchases in
        one line). Entering it again for the same date replaces it. Returns the entry
        id (None when the card already owed exactly that)."""
        acc = self.account(aid)
        if acc["type"] not in self.CARD_TYPES:
            raise ApiError("Statement balances are for credit cards and lines of credit")
        d = parse_date(date, "statement date").isoformat()
        owed = to_cents(balance, "statement balance")   # what the card owes (a credit is negative)
        det = dict(acc["details"])
        with self.lock:
            last = det.get("last_statement") or {}
            if last.get("date") == d and last.get("tid") and \
                    self.q1("SELECT 1 FROM transactions WHERE id=? AND account_id=?", (last["tid"], aid)):
                self.delete_transaction(last["tid"])
            change = -owed - self.balance_on(aid, d)
            tid = None
            if change:
                tid = self.save_transaction({"account_id": aid, "date": d, "payee": f"{acc['name']} statement",
                                             "memo": f"Statement balance {owed / 100:,.2f}",
                                             "amount_cents": change, "category_id": category_id or None})
            det["last_statement"] = {"date": d, "balance": owed, "tid": tid}
            self.db.execute("UPDATE accounts SET details=? WHERE id=?", (json.dumps(det), aid))
            self.db.commit()
            self.changed()
        return tid

    def _value_category(self):
        """Where changes in an investment's value go: "Change in Value", neither income nor
        spending (budgets and spending reports leave it out), made the first time it's needed."""
        r = self.q1("SELECT id FROM categories WHERE name=? COLLATE NOCASE AND parent_id IS NULL AND kind='none'",
                    (self.VALUE_CATEGORY,))
        if r:
            return r["id"]
        from .category_names import NAMES
        cid = self.db.execute("INSERT INTO categories(name,parent_id,kind,tax_related,in_budget) VALUES(?,?,?,?,?)",
                              (self.VALUE_CATEGORY, None, "none", 0, 0)).lastrowid
        self._set_category_names(cid, NAMES.get(self.VALUE_CATEGORY) or {})
        return cid

    def update_value(self, aid, date, value):
        """An investment, retirement or asset account is worth `value` on `date` (from its
        statement or website): one "Change in Value" entry that day makes its balance that.
        Updating the same date again replaces it. MoneyThistle never looks values up."""
        acc = self.account(aid)
        if acc["type"] not in self.VALUE_TYPES:
            raise ApiError("Values are updated for investment, retirement and asset accounts")
        with about("date"):
            d = parse_date(date, "Date").isoformat()
        with about("value"):
            v = to_cents(value, "Value")
        det = dict(acc["details"])
        with self.lock:
            last = det.get("last_value") or {}
            if last.get("date") == d and last.get("tid") and \
                    self.q1("SELECT 1 FROM transactions WHERE id=? AND account_id=?", (last["tid"], aid)):
                self.delete_transaction(last["tid"])
            change = v - self.balance_on(aid, d)
            tid = None
            if change:
                tid = self.save_transaction({"account_id": aid, "date": d, "payee": "", "memo": "",
                                             "amount_cents": change, "category_id": self._value_category()})
            det["last_value"] = {"date": d, "value": v, "tid": tid}
            self.db.execute("UPDATE accounts SET details=? WHERE id=?", (json.dumps(det), aid))
            self.db.commit()
            self.changed()
        return {"id": tid, "change": change, "value": v}

    def values_due(self, days=30):
        """Investment and retirement accounts whose value hasn't been updated in `days` (from
        their opening date when never): a reminder beside the card statements."""
        out, t = [], today()
        for a in self.accounts(include_closed=False):
            d = a["details"] or {}
            if a["type"] not in self.VALUE_TYPES:
                continue
            if not d.get("value_reminder", a["type"] in self.VALUE_REMIND_TYPES):
                continue
            last = (d.get("last_value") or {}).get("date") or a["opening_date"]
            if (t - dt.date.fromisoformat(last)).days >= days:
                out.append({"kind": "value", "account_id": a["id"], "name": a["name"], "last_date": last,
                            "updated": bool(d.get("last_value")), "balance": a["balance"]})
        return out

    def statement_due(self, aid):
        """What's left to pay on a card's last entered statement: its balance less the
        payments into the card dated after it closed. None when no statement is entered."""
        acc = self.account(aid)
        last = (acc["details"] or {}).get("last_statement") if acc["type"] in self.CARD_TYPES else None
        if not last or not last.get("date"):
            return None
        paid = self.q1("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE account_id=? AND date>? "
                       "AND amount>0 AND (transfer_id IS NOT NULL OR xlink_id IS NOT NULL)", (aid, last["date"]))["s"]
        return {"account_id": aid, "name": acc["name"], "date": last["date"], "balance": last["balance"],
                "paid_since": paid, "left": max(0, last["balance"] - paid)}

    def statements_due(self):
        """Cards kept by statement balance whose latest statement has closed but whose
        balance hasn't been entered yet: a reminder for Home and Bills."""
        out = []
        for a in self.accounts(include_closed=False):
            d = a["details"]
            mode = d.get("card_mode") or ("purchases" if d.get("track_purchases") else "statement")
            if a["type"] not in self.CARD_TYPES or mode != "statement" or not d.get("statement_day"):
                continue
            closing = self.last_closing(d["statement_day"])
            if closing.isoformat() < a["opening_date"]:
                continue
            last = (d.get("last_statement") or {}).get("date") or ""
            if last >= (closing - dt.timedelta(days=3)).isoformat():   # entered (a few days' leeway)
                continue
            out.append({"account_id": a["id"], "name": a["name"], "closing_date": closing.isoformat(),
                        "website": d.get("website") or ""})
        return out + [dict(v, website=(self.account(v["account_id"])["details"] or {}).get("website") or "")
                      for v in self.values_due()]

    def _next_due(self, day, after=None):
        """The next date on this day of the month (the month's last day when shorter),
        from `after` (default today) on."""
        t = after or today()
        d = t.replace(day=min(day, calendar.monthrange(t.year, t.month)[1]))
        return d if d >= t else add_months(t.replace(day=1), 1, day)

    def _sync_card_bill(self, aid, name, det):
        """Keep one scheduled payment for a credit card whose details ask for it: from
        the paying account to the card, monthly on the due day. Turned off, it stops
        (kept inactive, so what was paid stays counted)."""
        bill = self.q1("SELECT * FROM bills WHERE card_account_id=? ORDER BY active DESC, id DESC", (aid,))
        if not det.get("auto_pay"):
            if bill:
                self.db.execute("UPDATE bills SET active=0 WHERE card_account_id=?", (aid,))
            return
        day = det["due_day"]
        mode = "fixed" if det["pay_mode"] == "fixed" else "average"
        vals = (f"{name} payment", det["pay_from_account_id"], aid, det.get("pay_amount") or 0, mode, day)
        if bill:
            nd = bill["next_date"]
            if not bill["active"] or bill["anchor_day"] != day:
                nd = self._next_due(day).isoformat()
            self.db.execute("UPDATE bills SET payee=?, account_id=?, to_account_id=?, amount=?, amount_mode=?, "
                            "anchor_day=?, next_date=?, frequency='Monthly', kind='transfer', active=1 WHERE id=?",
                            vals + (nd, bill["id"]))
        else:
            self.db.execute("INSERT INTO bills(kind,payee,account_id,to_account_id,amount,amount_mode,anchor_day,"
                            "next_date,frequency,card_account_id,memo) VALUES('transfer',?,?,?,?,?,?,?,'Monthly',?,'')",
                            vals + (self._next_due(day).isoformat(), aid))

    def account(self, aid):
        for a in self.accounts():
            if a["id"] == aid:
                return a
        raise ApiError("No such account", 404)

    def save_account(self, data, aid=None):
        name = (data.get("name") or "").strip()
        if not name:
            raise ApiError("An account needs a name", field="name")
        typ = data.get("type") or "Checking"
        if typ not in defaults.ACCOUNT_TYPES:
            raise ApiError("Unknown account type", field="type")
        with about("opening_balance"):
            opening = to_cents(data.get("opening_balance"), "Opening balance")
        with about("opening_date"):
            odate = parse_date(data.get("opening_date") or today().isoformat(), "As of").isoformat()
        with self.lock:
            # Details: replaced when given, kept as they were when not (older screens).
            if "details" in data:
                det = self._clean_details(typ, data.get("details") or {})
                old = self.q1("SELECT details FROM accounts WHERE id=?", (aid,)) if aid else None
                prev = json.loads(old["details"] or "{}") if old else {}
                if prev.get("last_statement") and "last_statement" not in det and typ in self.CARD_TYPES:
                    det["last_statement"] = prev["last_statement"]   # the form doesn't carry it
                if prev.get("last_value") and "last_value" not in det and typ in self.VALUE_TYPES:
                    det["last_value"] = prev["last_value"]
            elif aid:
                old = self.q1("SELECT details FROM accounts WHERE id=?", (aid,))
                det = json.loads(old["details"] or "{}") if old else {}
            else:
                det = {}
            if det.get("pay_from_account_id") and det["pay_from_account_id"] == aid:
                raise ApiError("A card can't be paid from itself", field="pay_from_account_id")
            # Its currency: as given, else as it was (or the main currency for a new one).
            was = self.q1("SELECT currency FROM accounts WHERE id=?", (aid,)) if aid else None
            try:
                currency = currencies.clean_code(data.get("currency"),
                                                 was["currency"] if was else self.money_settings()["home"])
            except ValueError as e:
                raise ApiError(str(e), field="currency")
            if aid:
                self.db.execute("UPDATE accounts SET name=?,type=?,opening_balance=?,opening_date=?,"
                                "closed=?,favorite=?,notes=?,details=?,currency=? WHERE id=?",
                                (name, typ, opening, odate, int(bool(data.get("closed"))),
                                 int(bool(data.get("favorite"))), data.get("notes") or "", json.dumps(det),
                                 currency, aid))
            else:
                aid = self.db.execute(
                    "INSERT INTO accounts(name,type,opening_balance,opening_date,favorite,notes,details,currency) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (name, typ, opening, odate, int(bool(data.get("favorite"))),
                     data.get("notes") or "", json.dumps(det), currency)).lastrowid
            self._fx = None
            if typ in self.CARD_TYPES or self.q1("SELECT 1 FROM bills WHERE card_account_id=?", (aid,)):
                self._sync_card_bill(aid, name, det if typ in self.CARD_TYPES else {})
            self.db.commit()
            self.changed()
        return aid

    def delete_account(self, aid):
        with self.lock:
            # Linked halves of transfers in other accounts lose their partner.
            self.db.execute("UPDATE transactions SET transfer_id=NULL WHERE transfer_id IN "
                            "(SELECT id FROM transactions WHERE account_id=?)", (aid,))
            self.db.execute("DELETE FROM bills WHERE loan_account_id=?", (aid,))
            self.db.execute("DELETE FROM accounts WHERE id=?", (aid,))
            self.db.commit()
            self.changed()

    # ----- transactions -------------------------------------------------
    TX_SELECT = ("SELECT t.*, a.name AS account_name, c.name AS category_name, a.currency AS currency, "
                 "o.amount AS transfer_amount, oa.currency AS transfer_currency, "
                 "(t.group_id IS NOT NULL AND EXISTS(SELECT 1 FROM paystubs ps WHERE ps.group_id=t.group_id)) AS paystub, "
                 "(SELECT COUNT(*) FROM attachments x WHERE x.transaction_id=t.id) AS attachments, "
                 "p.name AS parent_category_name, c.kind AS category_kind, "
                 "o.account_id AS transfer_account_id, oa.name AS transfer_account_name "
                 "FROM transactions t JOIN accounts a ON a.id=t.account_id "
                 "LEFT JOIN categories c ON c.id=t.category_id "
                 "LEFT JOIN categories p ON p.id=c.parent_id "
                 "LEFT JOIN transactions o ON o.id=t.transfer_id "
                 "LEFT JOIN accounts oa ON oa.id=o.account_id ")

    def _decorate(self, rows):
        for r in rows:
            if r["transfer_account_name"]:
                r["category_label"] = ("Transfer to " if r["amount"] < 0 else "Transfer from ") + r["transfer_account_name"]
            elif r["category_name"]:
                r["category_label"] = (f"{r['parent_category_name']} : {r['category_name']}"
                                       if r["parent_category_name"] else r["category_name"])
            else:
                r["category_label"] = ""
        return rows

    def transactions(self, account_id=None, search=None, start=None, end=None,
                     category_id=None, limit=2000):
        where, args = [], []
        if account_id:
            where.append("t.account_id=?"); args.append(account_id)
        if start:
            where.append("t.date>=?"); args.append(start)
        if end:
            where.append("t.date<=?"); args.append(end)
        if category_id:
            where.append("(t.category_id=? OR c.parent_id=?)"); args += [category_id, category_id]
        if search:
            # (a category is found by its name in any language)
            where.append("(t.payee LIKE ? OR t.memo LIKE ? OR t.number LIKE ? OR c.name LIKE ? OR EXISTS("
                         "SELECT 1 FROM category_names n WHERE n.category_id=t.category_id AND n.name LIKE ?))")
            args += [f"%{search}%"] * 5
        sql = self.TX_SELECT + ("WHERE " + " AND ".join(where) if where else "") + \
            " ORDER BY t.date, t.seq, t.id"
        rows = self._decorate(self.q(sql, args))
        if account_id:
            acc = self.q1("SELECT opening_balance FROM accounts WHERE id=?", (account_id,))
            bal = acc["opening_balance"] if acc else 0
            if start or end or category_id or search:
                bal = None
            for r in rows:
                if bal is not None:
                    bal += r["amount"]
                r["running_balance"] = bal
        rows.reverse()
        return rows[:limit]

    def move_transaction(self, tid, direction):
        """Move an entry earlier or later among the same day's entries in its register,
        so the running balance follows the real order (a deposit before a withdrawal).
        A split payment moves as one."""
        if direction not in ("earlier", "later"):
            raise ApiError("Move earlier or later")
        with self.lock:
            t = self.q1("SELECT account_id, date, group_id FROM transactions WHERE id=?", (tid,))
            if not t:
                raise ApiError("No such transaction", 404)
            day = self.q("SELECT id, group_id FROM transactions WHERE account_id=? AND date=? ORDER BY seq, id",
                         (t["account_id"], t["date"]))
            units, where = [], {}
            for r in day:   # a split payment's lines stay together
                key = ("g", r["group_id"]) if r["group_id"] else ("t", r["id"])
                if key not in where:
                    where[key] = len(units)
                    units.append([])
                units[where[key]].append(r["id"])
            i = where[("g", t["group_id"]) if t["group_id"] else ("t", tid)]
            j = i - 1 if direction == "earlier" else i + 1
            if 0 <= j < len(units):
                units[i], units[j] = units[j], units[i]
                for n, unit in enumerate(units):
                    for rid in unit:
                        self.db.execute("UPDATE transactions SET seq=? WHERE id=?", ((n + 1) * 10, rid))
                self.db.commit()
                self.changed()
        return {"moved": 0 <= j < len(units)}

    def transaction(self, tid):
        r = self.q(self.TX_SELECT + "WHERE t.id=?", (tid,))
        if not r:
            raise ApiError("No such transaction", 404)
        return self._decorate(r)[0]

    def _remember_payee(self, payee, category_id, amount):
        if payee:
            self.db.execute("INSERT INTO payees(name,category_id,last_amount,used) VALUES(?,?,?,1) "
                            "ON CONFLICT(name) DO UPDATE SET category_id=COALESCE(excluded.category_id, category_id),"
                            "last_amount=excluded.last_amount, used=used+1",
                            (payee, category_id, amount))

    def save_transaction(self, data, tid=None):
        """Create or change a transaction. data['amount'] is signed (+in, -out),
        or give 'deposit'/'payment'. A 'transfer_account_id' makes it a transfer."""
        aid = int(data.get("account_id") or 0)
        if not aid or not self.q1("SELECT id FROM accounts WHERE id=?", (aid,)):
            raise ApiError("Choose an account")
        date = parse_date(data.get("date") or today().isoformat()).isoformat()
        if data.get("amount_cents") is not None:
            amount = int(data["amount_cents"])
        elif "amount" in data and data.get("amount") not in (None, ""):
            amount = to_cents(data.get("amount"))
        else:
            amount = to_cents(data.get("deposit")) - to_cents(data.get("payment"))
        if amount == 0:
            raise ApiError("Enter an amount")
        status = data.get("status") or ""
        if status not in ("", "C", "R"):
            raise ApiError("status must be '', C or R")
        payee = (data.get("payee") or "").strip()
        memo = (data.get("memo") or "").strip()
        number = str(data.get("number") or "").strip()
        cat = data.get("category_id") or None
        xfer = data.get("transfer_account_id") or None
        if xfer:
            xfer = int(xfer)
            if xfer == aid:
                raise ApiError("A transfer needs two different accounts")
            if not self.q1("SELECT id FROM accounts WHERE id=?", (xfer,)):
                raise ApiError("Unknown transfer account")
            cat = None
        elif not tid and not cat and amount < 0 and not data.get("xlink_id"):
            # A new charge on a card kept for one kind of spending, with no category chosen.
            row = self.q1("SELECT type, details FROM accounts WHERE id=?", (aid,))
            if row["type"] in self.CARD_TYPES:
                try:
                    cat = json.loads(row["details"] or "{}").get("purpose_category_id") or None
                except ValueError:
                    cat = None
        now = dt.datetime.now().isoformat(timespec="seconds")
        with self.lock:
            old = self.q1("SELECT * FROM transactions WHERE id=?", (tid,)) if tid else None
            if tid and not old:
                raise ApiError("No such transaction", 404)
            old_partner = self._snap("transactions", old["transfer_id"]) if old and old["transfer_id"] else None
            # What arrives on the other side (checked before anything is written).
            other = self._received(aid, xfer, amount, data.get("received"), old["transfer_id"] if old else None) \
                if xfer else None
            if old:
                self.db.execute("UPDATE transactions SET account_id=?,date=?,number=?,payee=?,category_id=?,"
                                "memo=?,amount=?,status=? WHERE id=?",
                                (aid, date, number, payee, cat, memo, amount, status, tid))
            else:
                # On a day whose entries were put in order, a new one goes last.
                seq = self.q1("SELECT COALESCE(MAX(seq),0) m FROM transactions WHERE account_id=? AND date=?",
                              (aid, date))["m"]
                tid = self.db.execute("INSERT INTO transactions(account_id,date,number,payee,category_id,memo,"
                                      "amount,status,created,seq) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                      (aid, date, number, payee, cat, memo, amount, status, now,
                                       seq + 10 if seq else 0)).lastrowid
            partner = old["transfer_id"] if old else None
            if xfer:
                if partner:
                    self.db.execute("UPDATE transactions SET account_id=?,date=?,payee=?,memo=?,amount=?,"
                                    "category_id=NULL WHERE id=?",
                                    (xfer, date, payee, memo, other, partner))
                else:
                    partner = self.db.execute(
                        "INSERT INTO transactions(account_id,date,payee,memo,amount,transfer_id,created) "
                        "VALUES(?,?,?,?,?,?,?)", (xfer, date, payee, memo, other, tid, now)).lastrowid
                    self.db.execute("UPDATE transactions SET transfer_id=? WHERE id=?", (partner, tid))
            elif partner:
                self.db.execute("DELETE FROM transactions WHERE id=?", (partner,))
                self.db.execute("UPDATE transactions SET transfer_id=NULL WHERE id=?", (tid,))
            if not xfer:
                self._remember_payee(payee, cat, amount)
            self.db.commit()
            self.changed()
            # The change history: this entry, and the other side of a transfer.
            self._log_row("transaction", tid, old, self._snap("transactions", tid))
            pid = partner if xfer else None
            if old_partner or pid:
                self._log_row("transaction", (old_partner or {}).get("id") or pid, old_partner,
                              self._snap("transactions", pid) if pid else None)
        return tid

    def _received(self, aid, xfer, amount, received, partner=None):
        """The other side of a transfer: the same amount, or, between two currencies, what
        arrived (`received`, in the other account's currency; kept as it was when an entry
        is changed without it)."""
        c = {r["id"]: r for r in self.q("SELECT id, name, currency FROM accounts WHERE id IN (?,?)", (aid, xfer))}
        if c[aid]["currency"] == c[xfer]["currency"]:
            return -amount
        sign = 1 if amount < 0 else -1
        if received not in (None, ""):
            with about("received"):
                got = abs(to_cents(received, "Amount received"))
            if not got:
                raise ApiError(f"Enter what arrived in {c[xfer]['name']}", field="received")
            return sign * got
        if partner:
            prev = self.q1("SELECT amount FROM transactions WHERE id=?", (partner,))
            if prev:
                return sign * abs(prev["amount"])
        side = "arrived in" if amount < 0 else "left"
        raise ApiError(f"{c[aid]['name']} is in {c[aid]['currency']} and {c[xfer]['name']} in {c[xfer]['currency']}: "
                       f"enter how much {side} {c[xfer]['name']} ({c[xfer]['currency']})", field="received")

    # ----- change history --------------------------------------------------------------
    audit = None   # set by the System: records a change (kind, id, action, before, after, summary)
    LOG_FIELDS = {"transaction": ("account_id", "date", "number", "payee", "category_id", "memo", "amount", "status"),
                  "bill": ("kind", "payee", "account_id", "to_account_id", "category_id", "amount", "frequency",
                           "next_date", "anchor_day", "memo", "active", "auto", "auto_enter"),
                  "account": ("name", "type", "opening_balance", "opening_date", "closed", "favorite", "notes", "details",
                              "currency"),
                  "category": ("name", "parent_id", "kind", "tax_related", "in_budget")}

    def _snap(self, table, rid):
        if not rid:
            return None
        r = self.q1(f"SELECT * FROM {table} WHERE id=?", (rid,))
        return dict(r) if r else None

    def _describe(self, kind, r):
        if not r:
            return ""
        acct = lambda i: (self.q1("SELECT name FROM accounts WHERE id=?", (i,)) or {}).get("name", "") if i else ""
        money = lambda c: f"{'-' if c < 0 else ''}{abs(c) / 100:,.2f}"
        if kind == "transaction":
            return f"{r.get('payee') or '(no payee)'} · {money(r['amount'])} · {r['date']} · {acct(r['account_id'])}"
        if kind == "bill":
            return f"{r.get('payee') or r.get('kind', '').title()} · {money(r['amount'])} · {r.get('frequency', '')} · {acct(r['account_id'])}"
        if kind == "account":
            return f"{r.get('name')} ({r.get('type')})"
        if kind == "category":
            return r.get("name", "")
        return ""

    def _log_row(self, kind, oid, before, after, note=""):
        """Record one row's change if it really changed (in what a person sees)."""
        if not self.audit or not oid or (before is None and after is None):
            return
        fields = self.LOG_FIELDS.get(kind, ())
        if before and after and all(before.get(f) == after.get(f) for f in fields):
            return
        action = "add" if before is None else ("delete" if after is None else "change")
        verb = {"add": "Added", "change": "Changed", "delete": "Deleted"}[action]
        what = {"transaction": "entry", "bill": "scheduled item", "account": "account", "category": "category"}.get(kind, kind)
        try:
            self.audit(kind, oid, action, before, after,
                       note or f"{verb} {what}: {self._describe(kind, after or before)}")
        except Exception:
            import traceback
            traceback.print_exc()   # the history never stops a change from being saved

    def set_group_date(self, gid, date):
        """Move every line of one split payment (and their transfer partners) to a date.
        When it's the latest payment of a monthly loan and moves to another month, the
        loan's next scheduled payment moves by as many months, so the schedule still
        picks up after it (a payment recorded for Dec by mistake and moved to Nov
        leaves Dec's payment due again). Returns the date and any new next date."""
        new = parse_date(date, "date")
        moved_next = None
        with self.lock:
            rows = self.q("SELECT id, transfer_id, date FROM transactions WHERE group_id=?", (gid,))
            if not rows:
                raise ApiError("No such payment", 404)
            old = dt.date.fromisoformat(rows[0]["date"])
            ids = [r["id"] for r in rows] + [r["transfer_id"] for r in rows if r["transfer_id"]]
            # Which loan this pays, if any, and whether it's that loan's latest payment.
            loan = self.q1(f"SELECT l.account_id FROM transactions q JOIN loans l ON l.account_id=q.account_id "
                           f"WHERE q.id IN ({','.join('?' * len(ids))}) LIMIT 1", ids)
            bill = self.q1("SELECT * FROM bills WHERE kind='loan' AND active=1 AND loan_account_id=?",
                           (loan["account_id"],)) if loan else None
            months = (old.year * 12 + old.month) - (new.year * 12 + new.month)
            if bill and months and bill["frequency"] == "Monthly":
                later = self.q1("SELECT 1 FROM transactions p JOIN transactions q ON q.id=p.transfer_id "
                                "WHERE q.account_id=? AND p.date>? AND COALESCE(p.group_id,0)<>?",
                                (loan["account_id"], old.isoformat(), gid))
                if not later:
                    nd = add_months(dt.date.fromisoformat(bill["next_date"]), -months, bill["anchor_day"])
                    self.db.execute("UPDATE bills SET next_date=? WHERE id=?", (nd.isoformat(), bill["id"]))
                    moved_next = nd.isoformat()
            self.db.execute(f"UPDATE transactions SET date=? WHERE id IN ({','.join('?' * len(ids))})",
                            [new.isoformat()] + ids)
            self.db.execute("UPDATE paystubs SET date=? WHERE group_id=?", (new.isoformat(), gid))
            self.db.commit()
            self.changed()
        return {"date": new.isoformat(), "next_date": moved_next}

    def delete_group(self, gid):
        """Delete every line of one split payment (and their transfer partners)."""
        with self.lock:
            for r in self.q("SELECT id FROM transactions WHERE group_id=?", (gid,)):
                self.delete_transaction(r["id"])
            self.db.execute("DELETE FROM paystubs WHERE group_id=?", (gid,))   # a paystub's record goes too
            self.db.commit()

    def delete_transaction(self, tid):
        with self.lock:
            r = self._snap("transactions", tid)
            p = self._snap("transactions", r["transfer_id"]) if r and r["transfer_id"] else None
            if r and r["transfer_id"]:
                self.db.execute("DELETE FROM transactions WHERE id=?", (r["transfer_id"],))
            self.db.execute("DELETE FROM transactions WHERE id=?", (tid,))
            self.db.commit()
            self.changed()
        self._log_row("transaction", tid, r, None)
        if p:
            self._log_row("transaction", p["id"], p, None)

    def set_status(self, tid, status):
        if status not in ("", "C", "R"):
            raise ApiError("status must be '', C or R")
        with self.lock:
            before = self._snap("transactions", tid)
            self.db.execute("UPDATE transactions SET status=? WHERE id=?", (status, tid))
            self.db.commit()
            self.changed()
        self._log_row("transaction", tid, before, self._snap("transactions", tid))

    def payees(self):
        return self.q("SELECT p.*, c.name AS category_name FROM payees p "
                      "LEFT JOIN categories c ON c.id=p.category_id ORDER BY used DESC, name LIMIT 500")

    def reconcile(self, aid, statement_balance, statement_date, ids):
        """Balance an account against a statement: the chosen transactions become
        reconciled when the totals agree."""
        acc = self.account(aid)
        target = to_cents(statement_balance, "statement balance")
        ids = [int(i) for i in ids or []]
        with self.lock:
            base = acc["opening_balance"] + (self.q1(
                "SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE account_id=? AND status='R'",
                (aid,))["s"])
            chosen = 0
            if ids:
                marks = ",".join("?" * len(ids))
                chosen = self.q1(f"SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE account_id=? "
                                 f"AND status!='R' AND id IN ({marks})", [aid] + ids)["s"]
            diff = target - (base + chosen)
            if diff != 0:
                raise ApiError(f"The statement is off by {diff / 100:.2f}. Check the marked transactions.")
            if ids:
                self.db.execute(f"UPDATE transactions SET status='R' WHERE account_id=? AND id IN ({marks})",
                                [aid] + ids)
            self.db.execute("UPDATE accounts SET reconciled_balance=?, reconciled_date=? WHERE id=?",
                            (target, parse_date(statement_date or today().isoformat()).isoformat(), aid))
            self.db.commit()
            self.changed()
        return {"reconciled": len(ids)}

    # ----- bills & deposits --------------------------------------------
    def schedule_from_entry(self, tid, today=None):
        """A new scheduled item started from a register entry (Schedule…, for after moving in
        from another program): who, how much, the category and the account from the entry; how
        often and the next date from the same payee's other entries in that account, shaped
        like this one (single or split); an amount that differs from time to time varies, at
        its average. Nothing is saved: the person checks it first. Also says whether that payee
        is already scheduled on this account."""
        t = self.q1("SELECT * FROM transactions WHERE id=?", (tid,))
        if not t:
            raise ApiError("No such transaction", 404)
        today = today or dt.date.today()
        acc, payee = t["account_id"], (t["payee"] or "").strip()
        amount, cat, memo, other = t["amount"], t["category_id"], t["memo"] or "", None
        if t["group_id"]:
            # A split payment counts once, at its total, in the category of its biggest part.
            parts = self.q("SELECT * FROM transactions WHERE group_id=? AND account_id=?", (t["group_id"], acc))
            amount = sum(p["amount"] for p in parts)
            same = [p for p in parts if (p["amount"] > 0) == (amount > 0)] or parts
            cat, memo = max(same, key=lambda p: abs(p["amount"]))["category_id"], ""
        elif t["transfer_id"]:
            o = self.q1("SELECT account_id FROM transactions WHERE id=?", (t["transfer_id"],))
            other = o["account_id"] if o else None
        # The same payee's entries in this account, in the same direction (a split payment once).
        rows, groups = [], {}
        for r in (self.q("SELECT id, date, amount, group_id FROM transactions WHERE account_id=? AND "
                         "lower(trim(payee))=lower(?) ORDER BY date, id", (acc, payee)) if payee else []):
            if not r["group_id"]:
                rows.append(dict(r))
            elif r["group_id"] in groups:
                groups[r["group_id"]]["amount"] += r["amount"]
            else:
                groups[r["group_id"]] = dict(r)
                rows.append(groups[r["group_id"]])
        like = [r for r in rows if (r["amount"] > 0) == (amount > 0) and r["amount"]]
        shaped = [r for r in like if bool(r["group_id"]) == bool(t["group_id"])]
        if len(shaped) >= 2:
            like = shaped   # (take-home-only deposits and paystubs can follow different patterns)
        dates = sorted({r["date"] for r in like}) or [t["date"]]
        freq, last_day = guess_frequency(dates)
        nxt = dt.date.fromisoformat(dates[-1])
        anchor = 31 if last_day else nxt.day
        for _ in range(1000):
            if nxt > today:
                break
            nxt = next_occurrence(nxt, freq, anchor)
        amounts = [abs(r["amount"]) for r in like[-6:]]
        varies = len(set(amounts)) > 1
        avg = int(round(sum(amounts) / len(amounts))) if varies else abs(amount)
        start = {"payee": payee, "memo": memo, "frequency": freq, "last_day": last_day, "next_date": nxt.isoformat(),
                 "amount": avg, "estimate": avg if varies else abs(amount), "amount_mode": "average" if varies else "fixed",
                 "average_count": 12, "category_id": cat, "account_id": acc}
        if other:
            # A transfer: from the account the money left, to the one it reached.
            start.update(kind="transfer", category_id=None, account_id=acc if amount < 0 else other,
                         to_account_id=other if amount < 0 else acc)
        else:
            start["kind"] = "deposit" if amount > 0 else "bill"
            # A paycheck: marked as one, a paystub, or pay in Wages & Salary (not the employer's match).
            full = next((c["full_name"] for c in self.categories() if c["id"] == cat), "") if cat else ""
            wages = bool(re.fullmatch(r"Wages & Salary( : (?!Employer Matching).*)?", full or ""))
            stub = bool(t["group_id"]) and bool(self.q1("SELECT 1 FROM paystubs WHERE group_id=?", (t["group_id"],)))
            if amount > 0 and (t["paycheck"] is not None or stub or wages):
                start["paycheck"] = True
        already = next(({"frequency": b["frequency"], "last_day": b.get("last_day"), "next_date": b["next_date"]}
                        for b in self.bills() if not b.get("split_of") and payee
                        and (b["payee"] or "").strip().lower() == payee.lower()
                        and acc in (b["account_id"], b.get("to_account_id"))), None)
        return {"start": start, "already": already}

    def bills(self):
        rows = self.q("SELECT b.*, a.name AS account_name, COALESCE(ta.name, la.name) AS to_account_name, "
                      "c.name AS category_name, p.name AS parent_category_name FROM bills b "
                      "JOIN accounts a ON a.id=b.account_id LEFT JOIN accounts ta ON ta.id=b.to_account_id "
                      "LEFT JOIN accounts la ON la.id=b.loan_account_id "
                      "LEFT JOIN categories c ON c.id=b.category_id LEFT JOIN categories p ON p.id=c.parent_id "
                      "WHERE b.active=1 ORDER BY b.next_date, b.payee")
        t = today().isoformat()
        # Card payments kept by the card's details: "pay the full balance" expects what
        # the card owes now; each links to where the card can be paid online.
        cards = {a["id"]: a for a in self.accounts() if a["details"].get("auto_pay")} \
            if any(r.get("card_account_id") for r in rows) else {}
        for r in rows:
            r["overdue"] = r["next_date"] < t
            r["days_until"] = (dt.date.fromisoformat(r["next_date"]) - today()).days
            r["last_day"] = r["anchor_day"] >= 31 and r["frequency"] in MONTH_BASED
            card = cards.get(r.get("card_account_id"))
            if card:
                cd = card["details"]
                r["pay_url"] = cd.get("website") or ""
                r["pay_full"] = cd.get("pay_mode") == "full"
                r["card_mode"] = cd.get("card_mode") or ("purchases" if cd.get("track_purchases") else "statement")
                r["statement_day"] = cd.get("statement_day")
                r["card_owed"] = max(0, -card["balance"])
                r["last_statement"] = cd.get("last_statement")
            r["category_label"] = (f"{r['parent_category_name']} : {r['category_name']}"
                                   if r["parent_category_name"] else (r["category_name"] or ""))
            if r.get("x_link_id"):
                r["to_account_name"] = r.get("x_label") or "another environment"
            r["estimate"] = r["amount"]
            r["history"] = self.q("SELECT date, amount FROM bill_history WHERE bill_id=? "
                                  "ORDER BY date DESC, id DESC LIMIT ?", (r["id"], max(1, r["average_count"])))
            r["amount"] = self.expected_amount(r, r["history"])
            if card and r.get("pay_full"):
                r["amount"] = max(0, -card["balance"])   # what the card owes now
        # A deposit into more than one account: the main one lists the others ("splits") and
        # their total with it. The others stay in the list (forecasts and budgets count them);
        # lists people read leave them out (split_of).
        by_main = {}
        for r in rows:
            if r.get("split_of"):
                by_main.setdefault(r["split_of"], []).append(r)
        for r in rows:
            subs = by_main.get(r["id"], [])
            r["splits"] = [{"id": c["id"], "account_id": c["account_id"], "account_name": c["account_name"],
                            "amount": c["amount"], "estimate": c["estimate"], "amount_mode": c["amount_mode"],
                            "average_count": c["average_count"], "history": c["history"]} for c in subs]
            r["split_total"] = r["amount"] + sum(c["amount"] for c in subs)
        return rows

    def expected_amount(self, b, history=None):
        """What to expect next time. Fixed: the set amount. Varies: the average of up
        to the last `average_count` recorded amounts, or the estimate before any."""
        if b.get("amount_mode") != "average" or b.get("kind") == "loan":
            return b["amount"]
        if history is None:
            history = self.q("SELECT amount FROM bill_history WHERE bill_id=? ORDER BY date DESC, id DESC LIMIT ?",
                             (b["id"], max(1, b["average_count"])))
        if not history:
            return b["amount"]
        return int(round(sum(h["amount"] for h in history) / len(history)))

    def save_bill(self, data, bid=None):
        kind = data.get("kind") or "bill"
        if kind not in ("bill", "deposit", "transfer"):
            raise ApiError("kind must be bill, deposit or transfer")
        aid = int(data.get("account_id") or 0)
        if not aid:
            raise ApiError("Choose an account")
        to_aid = int(data.get("to_account_id") or 0) or None
        x_link = int(data.get("x_link_id") or 0) or None
        if x_link and kind == "transfer":
            to_aid = None
            if data.get("x_dir") not in ("in", "out"):
                raise ApiError("x_dir must be in or out")
        elif kind == "transfer" and (not to_aid or to_aid == aid):
            raise ApiError("A transfer needs a different 'to' account")
        amount = abs(to_cents(data.get("amount")))
        mode = data.get("amount_mode") or "fixed"
        if mode not in ("fixed", "average"):
            raise ApiError("amount_mode must be fixed or average")
        try:
            avg_n = int(data.get("average_count") or 12)
        except ValueError:
            raise ApiError("The number of payments to average must be a whole number")
        if not 1 <= avg_n <= 99:
            raise ApiError("Please enter a number between 1 and 99.")
        if not amount and mode == "fixed":
            raise ApiError("Enter an amount (or choose 'The amount varies')")
        freq = data.get("frequency") or "Monthly"
        if freq not in defaults.FREQUENCIES:
            raise ApiError("Unknown frequency")
        nd = parse_date(data.get("next_date") or today().isoformat(), "next date")
        anchor = nd.day
        # "On the last day of the month": the date moves to its month's last day and
        # every later date lands on the last day of its month (28th-31st).
        if data.get("last_day") and freq in MONTH_BASED:
            nd = nd.replace(day=calendar.monthrange(nd.year, nd.month)[1])
            anchor = 31
        received = None
        if kind == "transfer" and to_aid and data.get("received") not in (None, ""):
            with about("received"):
                received = abs(to_cents(data.get("received"), "Amount that arrives")) or None
        vals = (kind, (data.get("payee") or "").strip(), aid, to_aid if kind == "transfer" else None,
                (data.get("category_id") or None) if kind != "transfer" else None,
                amount, freq, nd.isoformat(), anchor, (data.get("memo") or "").strip())
        with self.lock:
            if bid:
                self.db.execute("UPDATE bills SET kind=?,payee=?,account_id=?,to_account_id=?,category_id=?,"
                                "amount=?,frequency=?,next_date=?,anchor_day=?,memo=?,amount_mode=?,average_count=? "
                                "WHERE id=?", vals + (mode, avg_n, bid))
            else:
                bid = self.db.execute("INSERT INTO bills(kind,payee,account_id,to_account_id,category_id,amount,"
                                      "frequency,next_date,anchor_day,memo,amount_mode,average_count) "
                                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", vals + (mode, avg_n)).lastrowid
            if x_link and kind == "transfer":
                self.db.execute("UPDATE bills SET x_link_id=?, x_dir=?, x_label=? WHERE id=?",
                                (x_link, data["x_dir"], (data.get("x_label") or "")[:200], bid))
            elif kind == "transfer" and to_aid:
                self.db.execute("UPDATE bills SET x_link_id=NULL, x_dir=NULL, x_label=NULL WHERE id=?", (bid,))
            if "auto" in data:
                auto = bool(data.get("auto"))
                self.db.execute("UPDATE bills SET auto=?, auto_enter=? WHERE id=?",
                                (int(auto), int(auto and bool(data.get("auto_enter"))), bid))
            if "paycheck" in data:
                # A paycheck: its amount is the take-home pay; entering it can bring a paystub.
                self.db.execute("UPDATE bills SET paycheck=? WHERE id=?",
                                (int(bool(data.get("paycheck")) and kind == "deposit"), bid))
            if "received" in data or kind != "transfer":
                # A transfer between two currencies: what usually arrives (optional).
                self.db.execute("UPDATE bills SET received=? WHERE id=?", (received, bid))
            self._save_splits(bid, kind, aid, data)
            self.db.commit()
            self.changed()
        return bid

    def _save_splits(self, bid, kind, aid, data):
        """The other accounts a deposit goes into (data["splits"]: account_id, amount,
        amount_mode, and id for one already there). Each is a scheduled deposit of its own, on
        the main one's dates; those not listed any more are removed. Without "splits", the ones
        there keep their amounts and follow the main one's schedule."""
        main = self.q1("SELECT * FROM bills WHERE id=?", (bid,))
        if main.get("split_of"):
            return   # (one of the others itself: changed on its own)
        have = {r["id"]: r for r in self.q("SELECT * FROM bills WHERE split_of=?", (bid,))}
        if kind != "deposit":
            self.db.execute("DELETE FROM bills WHERE split_of=?", (bid,))
            return
        wanted = None
        if isinstance(data.get("splits"), list):
            wanted, seen = [], set()
            for n, sp in enumerate(data["splits"]):
                to = int(sp.get("account_id") or 0)
                if not to or to == aid or not self.q1("SELECT 1 FROM accounts WHERE id=?", (to,)):
                    raise ApiError("Choose the other account for each amount", field=f"split_{n}_account")
                if to in seen:
                    raise ApiError("Each account can be listed once", field=f"split_{n}_account")
                seen.add(to)
                mode = sp.get("amount_mode") or "fixed"
                if mode not in ("fixed", "average"):
                    raise ApiError("amount_mode must be fixed or average")
                with about(f"split_{n}_amount"):
                    amount = abs(to_cents(sp.get("amount") or "0", "Amount"))
                if not amount and mode == "fixed":
                    raise ApiError("Enter the amount for each account (or choose Average)", field=f"split_{n}_amount")
                sid = int(sp.get("id") or 0)
                wanted.append((sid if sid in have else None, to, amount, mode))
            keep = {w[0] for w in wanted if w[0]}
            for old in have:
                if old not in keep:
                    self.db.execute("DELETE FROM bills WHERE id=?", (old,))
        sync = (main["kind"], main["payee"], main["category_id"], main["frequency"], main["next_date"],
                main["anchor_day"], main["memo"], main["active"], main.get("paycheck") or 0, main["average_count"])
        cols_ = "kind=?,payee=?,category_id=?,frequency=?,next_date=?,anchor_day=?,memo=?,active=?,paycheck=?,average_count=?"
        if wanted is None:
            for old in have:
                self.db.execute(f"UPDATE bills SET {cols_} WHERE id=?", sync + (old,))
            return
        for sid, to, amount, mode in wanted:
            if sid:
                self.db.execute(f"UPDATE bills SET {cols_},account_id=?,amount=?,amount_mode=? WHERE id=?",
                                sync + (to, amount, mode, sid))
            else:
                self.db.execute("INSERT INTO bills(kind,payee,category_id,frequency,next_date,anchor_day,memo,active,"
                                "paycheck,average_count,account_id,amount,amount_mode,split_of) "
                                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sync + (to, amount, mode, bid))

    def set_bill_auto(self, bid, auto, auto_enter=False):
        """Mark a scheduled item as happening by itself, and whether to record it in the
        register on its date (only an automatic item can be)."""
        auto = bool(auto)
        with self.lock:
            if not self.q1("SELECT 1 FROM bills WHERE id=?", (bid,)):
                raise ApiError("No such scheduled item", 404)
            self.db.execute("UPDATE bills SET auto=?, auto_enter=? WHERE id=?",
                            (int(auto), int(auto and bool(auto_enter)), bid))
            self.db.commit()
            self.changed()
        return {"auto": auto, "auto_enter": auto and bool(auto_enter)}

    def mark_auto(self, tid):
        """Flag an entry (its transfer partner, and every part of a split payment) as
        recorded automatically."""
        with self.lock:
            r = self.q1("SELECT id, transfer_id, group_id FROM transactions WHERE id=?", (tid,))
            if not r:
                return
            if r["group_id"]:
                ids = [x["id"] for x in self.q("SELECT id FROM transactions WHERE group_id=?", (r["group_id"],))]
                ids += [x["transfer_id"] for x in self.q("SELECT transfer_id FROM transactions WHERE group_id=? "
                                                         "AND transfer_id IS NOT NULL", (r["group_id"],))]
            else:
                ids = [r["id"]] + ([r["transfer_id"]] if r["transfer_id"] else [])
            self.db.execute(f"UPDATE transactions SET auto=1 WHERE id IN ({','.join('?' * len(ids))})", ids)
            self.db.commit()

    def delete_bill(self, bid):
        with self.lock:
            self.db.execute("DELETE FROM bills WHERE split_of=?", (bid,))
            self.db.execute("DELETE FROM bills WHERE id=?", (bid,))
            self.db.commit()
            self.changed()

    def _advance_bill(self, b):
        nxt = next_occurrence(dt.date.fromisoformat(b["next_date"]), b["frequency"], b["anchor_day"])
        # (a deposit's other accounts move with it)
        if nxt is None:
            self.db.execute("UPDATE bills SET active=0 WHERE id=? OR split_of=?", (b["id"], b["id"]))
        else:
            self.db.execute("UPDATE bills SET next_date=? WHERE id=? OR split_of=?", (nxt.isoformat(), b["id"], b["id"]))

    def split_bills(self, bid):
        """The other accounts a scheduled deposit goes into, each with what to expect."""
        out = []
        for c in self.q("SELECT * FROM bills WHERE split_of=? AND active=1 ORDER BY id", (bid,)):
            c["expected"] = self.expected_amount(c)
            out.append(c)
        return out

    def record_split(self, child_id, date, amount, tid):
        """One of a deposit's other accounts got its part: kept for its average."""
        self.db.execute("INSERT INTO bill_history(bill_id,date,amount,transaction_id) VALUES(?,?,?,?)",
                        (child_id, date, amount, tid))

    def enter_bill(self, bid, data=None):
        """Record this occurrence of a bill as a transaction and move to the next date."""
        data = data or {}
        with self.lock:
            b = self.q1("SELECT * FROM bills WHERE id=?", (bid,))
            if not b:
                raise ApiError("No such bill", 404)
            if b["kind"] == "loan":
                # Loan payment: split into principal / interest / escrow.
                from . import loans
                pay = dict(data)
                pay.setdefault("date", b["next_date"])
                pay.setdefault("account_id", b["account_id"])
                res = loans.pay(self, b["loan_account_id"], pay)
                self._advance_bill(b)
                self.db.commit()
                self.changed()
                return res["ids"][0]
            if b.get("x_link_id"):
                raise ApiError("This transfer reaches another environment; record it from the Bills page")
            amount = abs(to_cents(data["amount"])) if data.get("amount") not in (None, "") \
                else self.expected_amount(b)
            if b["kind"] == "deposit" and not data.get("plain") and not data.get("take_home"):
                # A paycheck that has had a paystub: a copy of the latest one (same lines).
                from . import paystubs
                given = abs(to_cents(data["amount"])) if data.get("amount") not in (None, "") else None
                res = paystubs.copy_for_bill(self, b, data.get("date") or b["next_date"], given)
                if res:
                    return res["ids"][0]
            if not amount:
                raise ApiError("Enter the amount for this time")
            tx = {"account_id": b["account_id"], "date": data.get("date") or b["next_date"],
                  "payee": b["payee"], "memo": b["memo"], "number": data.get("number") or "",
                  "amount_cents": amount if b["kind"] == "deposit" else -amount,
                  "category_id": b["category_id"]}
            if b["kind"] == "transfer":
                tx["transfer_account_id"] = b["to_account_id"]
                # Between two currencies: what arrived this time, or what usually arrives.
                tx["received"] = data.get("received") if data.get("received") not in (None, "") else \
                    (f"{b['received'] / 100:.2f}" if b.get("received") else None)
            tid = self.save_transaction(tx)
            if b["kind"] == "deposit" and b.get("paycheck"):
                # A paycheck with only its take-home pay (for now): paystub details can follow.
                self.db.execute("UPDATE transactions SET paycheck=1 WHERE id=?", (tid,))
            # Remember what was actually paid: bills whose amount varies average these.
            self.db.execute("INSERT INTO bill_history(bill_id,date,amount,transaction_id) VALUES(?,?,?,?)",
                            (b["id"], tx["date"], amount, tid))
            # A deposit into more than one account: each other account gets its part (what was
            # entered for it this time, else what's expected), on the same date.
            if b["kind"] == "deposit":
                from .paystubs import SPLIT_LABEL
                given = data.get("splits") if isinstance(data.get("splits"), dict) else {}
                for c in self.split_bills(b["id"]):
                    v = given.get(str(c["id"]), given.get(c["id"]))
                    with about(f"split_{c['id']}"):
                        part = abs(to_cents(v, "Amount")) if v not in (None, "") else c["expected"]
                    if not part:
                        continue
                    memo = (SPLIT_LABEL + (f" · {b['memo']}" if b["memo"] else "")) if b.get("paycheck") else b["memo"]
                    ctid = self.save_transaction({"account_id": c["account_id"], "date": tx["date"], "payee": b["payee"],
                                                  "memo": memo, "amount_cents": part, "category_id": c["category_id"]})
                    self.record_split(c["id"], tx["date"], part, ctid)
            self._advance_bill(b)
            self.db.commit()
            self.changed()
        return tid

    def skip_bill(self, bid):
        with self.lock:
            b = self.q1("SELECT * FROM bills WHERE id=?", (bid,))
            if not b:
                raise ApiError("No such bill", 404)
            self._advance_bill(b)
            self.db.commit()
            self.changed()

    def upcoming(self, days=31):
        """Each bill occurrence from overdue up to `days` ahead."""
        end = today() + dt.timedelta(days=days)
        out = []
        for b in self.bills():
            d = dt.date.fromisoformat(b["next_date"])
            n = 0
            while d and d <= end and n < 40:
                # Overdue is about this date, not the bill as a whole.
                out.append({**b, "date": d.isoformat(), "first": n == 0, "overdue": d < today()})
                d = next_occurrence(d, b["frequency"], b["anchor_day"])
                n += 1
        out.sort(key=lambda r: (r["date"], r["payee"]))
        return out

    def forecast(self, days=90):
        """Each account's balance day by day for `days` ahead, from today's balance plus
        every scheduled bill, deposit, transfer and loan payment at its expected amount
        (bills whose amount varies use their running average). Overdue items count today."""
        days = max(7, min(366, int(days)))
        t = today()
        accs = [a for a in self.accounts(include_closed=False)]
        bal = {a["id"]: a["balance"] for a in accs}
        moves = {}  # day index -> list of (account_id, cents)
        events = []
        for o in self.upcoming(days):
            d = max(dt.date.fromisoformat(o["date"]), t)
            i = (d - t).days
            amt = o["amount"]
            if o["kind"] == "deposit" or (o.get("x_link_id") and o.get("x_dir") == "in"):
                parts = [(o["account_id"], amt)]
            elif o.get("x_link_id"):   # out to an account in another environment
                parts = [(o["account_id"], -amt)]
            elif o["kind"] == "transfer":
                parts = [(o["account_id"], -amt), (o["to_account_id"], amt)]
            else:  # bill or loan payment (the loan's own balance isn't projected)
                parts = [(o["account_id"], -amt)]
            for aid, c in parts:
                if aid in bal:
                    moves.setdefault(i, []).append((aid, c))
            events.append({"date": d.isoformat(), "payee": o["payee"] or o["kind"].title(), "kind": o["kind"],
                           "account_id": o["account_id"], "account_name": o["account_name"],
                           "to_account_id": o.get("to_account_id") if o["kind"] == "transfer" and not o.get("x_link_id") else None,
                           "amount": amt if (o["kind"] == "deposit" or o.get("x_dir") == "in") else -amt,
                           "x_link_id": o.get("x_link_id"), "x_dir": o.get("x_dir"),
                           "estimated": o.get("amount_mode") == "average", "overdue": o["overdue"]})
        series = {aid: [] for aid in bal}
        for i in range(days + 1):
            for aid, c in moves.get(i, []):
                bal[aid] += c
            for aid in bal:
                series[aid].append(bal[aid])
        out = []
        for a in accs:
            s = series[a["id"]]
            low = min(range(len(s)), key=lambda k: s[k])
            # Today's balance before anything due today counts too.
            low_val, low_day = (a["balance"], 0) if a["balance"] < s[low] else (s[low], low)
            out.append({"id": a["id"], "name": a["name"], "type": a["type"], "liability": a["liability"],
                        "now": a["balance"], "end": s[-1], "low": low_val,
                        "low_date": (t + dt.timedelta(days=low_day)).isoformat(), "series": s,
                        "has_activity": any(aid == a["id"] for i in moves for aid, _ in moves[i])})
        return {"start": t.isoformat(), "days": days, "accounts": out, "events": events}

    # ----- budget --------------------------------------------------------
    def set_budget(self, items):
        with self.lock:
            for it in items:
                cid = int(it["category_id"])
                amt = abs(to_cents(it.get("amount")))
                self.db.execute("INSERT INTO budget(category_id,amount) VALUES(?,?) "
                                "ON CONFLICT(category_id) DO UPDATE SET amount=excluded.amount", (cid, amt))
                if "in_budget" in it:
                    self.db.execute("UPDATE categories SET in_budget=? WHERE id=?",
                                    (int(bool(it["in_budget"])), cid))
            self.db.commit()
            self.changed()

    def _actuals(self, start, end):
        """Category id -> signed total of non-transfer transactions in the range."""
        return {r["category_id"]: r["s"] for r in self.q(
            "SELECT category_id, SUM(fx(amount, account_id)) s FROM transactions WHERE transfer_id IS NULL "
            "AND category_id IS NOT NULL AND date>=? AND date<=? GROUP BY category_id", (start, end)) if r["s"] is not None}

    def category_totals(self, start, end, account_ids=None, exclude_group_ids=None):
        """Non-transfer totals per category in a date range, by name, so another
        environment can match them to its own categories (for shared accounts).
        Lines of the payment groups given are left out (a loan line counts them)."""
        extra, ids = self._acct_filter(account_ids)
        if exclude_group_ids:
            extra += f" AND COALESCE(t.group_id,0) NOT IN ({','.join('?' * len(exclude_group_ids))})"
            ids = ids + list(exclude_group_ids)
        rows = self.q("SELECT c.id, c.name, c.kind, p.name AS parent_name, COALESCE(SUM(fx(t.amount, t.account_id)),0) AS s "
                      "FROM transactions t JOIN categories c ON c.id=t.category_id "
                      "LEFT JOIN categories p ON p.id=c.parent_id WHERE t.transfer_id IS NULL "
                      "AND t.date>=? AND t.date<=?" + extra + " GROUP BY c.id", [start, end] + ids)
        # Paystubs count at their take-home pay (as in this file's own budget).
        sums = {r["id"]: r["s"] for r in rows}
        for cid, v in self._paystub_shift(start, end, account_ids).items():
            sums[cid] = sums.get(cid, 0) + v
        cats = {c["id"]: c for c in self.categories()}
        return [{"name": cats[cid]["name"], "parent_name": cats[cid]["parent_name"] if cats[cid]["parent_id"] else None,
                 "kind": cats[cid]["kind"], "total": v} for cid, v in sums.items() if v and cid in cats]

    @staticmethod
    def month_range(month=None):
        m = month or today().strftime("%Y-%m")
        y, mo = int(m[:4]), int(m[5:7])
        return m, dt.date(y, mo, 1), dt.date(y, mo, calendar.monthrange(y, mo)[1])

    def _scheduled_rows(self, month=None, account_ids=None):
        """(category id, kind, cents) for each bill or deposit occurrence in a month:
        those already entered (at the amount entered) and those still to come,
        overdue ones included (at the expected amount). Positive amounts."""
        m, start, end = self.month_range(month)
        extra, ids = self._acct_filter(account_ids, "b.account_id")
        out = [(r["category_id"], r["kind"], r["amount"]) for r in self.q(
            "SELECT b.category_id, b.kind, h.amount FROM bill_history h JOIN bills b ON b.id=h.bill_id "
            "WHERE b.kind IN ('bill','deposit') AND b.category_id IS NOT NULL AND h.date>=? AND h.date<=?" + extra,
            [start.isoformat(), end.isoformat()] + ids)]
        for b in self.bills():
            if b["kind"] not in ("bill", "deposit") or not b["category_id"]:
                continue
            if account_ids is not None and b["account_id"] not in ids:
                continue
            d, n = dt.date.fromisoformat(b["next_date"]), 0
            while d and d <= end and n < 400:
                if d >= start:
                    out.append((b["category_id"], b["kind"], b["amount"]))
                d = next_occurrence(d, b["frequency"], b["anchor_day"])
                n += 1
        return out

    def loan_lines(self, month=None, from_account_ids=None):
        """One budget line per loan: the whole of each payment made in the month
        (principal, interest and escrow, as the money left the paying account) and
        what's expected (those payments plus the scheduled ones still to come).
        `from_account_ids` limits it to payments from those accounts (shared ones).
        group_ids: the payments whose interest/escrow lines this line already counts."""
        m, start, end = self.month_range(month)
        s, e = start.isoformat(), end.isoformat()
        out = []
        for loan in self.q("SELECT l.account_id, a.name FROM loans l JOIN accounts a ON a.id=l.account_id"):
            aid = loan["account_id"]
            rows = self.q("SELECT p.id, p.account_id, p.amount, p.group_id FROM transactions p "
                          "JOIN transactions q ON q.id=p.transfer_id WHERE q.account_id=? AND p.account_id<>? "
                          "AND p.amount<0 AND p.date>=? AND p.date<=?", (aid, aid, s, e))
            if from_account_ids is not None:
                rows = [r for r in rows if r["account_id"] in from_account_ids]
            paid = -sum(r["amount"] for r in rows)
            gids = sorted({r["group_id"] for r in rows if r["group_id"]})
            if gids:
                marks = ",".join("?" * len(gids))
                principal_ids = [r["id"] for r in rows]
                pmarks = ",".join("?" * len(principal_ids))
                paid += -self.q1(f"SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE group_id IN ({marks}) "
                                 f"AND id NOT IN ({pmarks}) AND amount<0", gids + principal_ids)["s"]
            upcoming = 0
            bill = self.q1("SELECT * FROM bills WHERE kind='loan' AND loan_account_id=? AND active=1", (aid,))
            if bill and (from_account_ids is None or bill["account_id"] in from_account_ids):
                d, n = dt.date.fromisoformat(bill["next_date"]), 0
                while d and d <= end and n < 400:
                    if d >= start:
                        upcoming += bill["amount"]
                    d = next_occurrence(d, bill["frequency"], bill["anchor_day"])
                    n += 1
            if paid or upcoming:
                out.append({"loan_account_id": aid, "name": f"Loan payment: {loan['name']}",
                            "actual": paid, "scheduled": paid + upcoming, "group_ids": gids})
        return out

    def schedule_lines(self, month=None, account_ids=None):
        """The budget by scheduled items, for people who don't track categories: one
        line per bill, deposit, transfer and loan payment, with what it's expected
        to come to this month (entered already plus still to come) and what was
        entered from the schedule so far. `side`: in (deposits), out (bills, loan
        payments, transfers paying a credit card or loan) or move (transfers between
        your own accounts, e.g. to savings, which aren't spending).
        `account_ids` limits it to items of those accounts (shared ones)."""
        m, start, end = self.month_range(month)
        s, e = start.isoformat(), end.isoformat()
        hist = {r["bill_id"]: r for r in self.q(
            "SELECT bill_id, SUM(amount) s, COUNT(*) n FROM bill_history WHERE date>=? AND date<=? GROUP BY bill_id", (s, e))}
        active = self.bills()
        seen = {b["id"] for b in active}
        gone = [dict(b, amount=0, next_date="9999-12-31") for b in self.q(
            "SELECT b.*, a.name AS account_name, ta.name AS to_account_name FROM bills b "
            "JOIN accounts a ON a.id=b.account_id LEFT JOIN accounts ta ON ta.id=b.to_account_id "
            "WHERE b.active=0") if b["id"] in hist and b["id"] not in seen]
        liab = {a["id"]: a["liability"] for a in self.accounts(include_closed=True)}
        loans = {ln["loan_account_id"]: ln for ln in self.loan_lines(m, account_ids)}
        # Entries typed into a register rather than entered from the schedule still
        # count for the item they match: same account and payee (a transfer: same
        # accounts), money in the same direction. Each entry counts for one item.
        loose = self.q("SELECT t.id, t.account_id, t.payee, t.amount, t.transfer_id, t.group_id, q.account_id AS other "
                       "FROM transactions t LEFT JOIN transactions q ON q.id=t.transfer_id "
                       "WHERE t.date>=? AND t.date<=? AND t.id NOT IN "
                       "(SELECT transaction_id FROM bill_history WHERE transaction_id IS NOT NULL) "
                       "ORDER BY t.date, t.id", (s, e))
        # A paystub is one paycheck: one deposit of its net pay (its first entry stands
        # for it; its other parts aren't separate entries). One already counted through
        # the schedule (its first entry in the bill history) drops out entirely.
        # (what reached its account: a part deposited into another account is a move between
        # my own accounts here)
        from . import paystubs
        stubs = {p["group_id"]: paystubs.deposit_of(p["net"], json.loads(p["lines"] or "{}").get("lines", []))
                 for p in self.q("SELECT group_id, net, lines FROM paystubs WHERE date>=? AND date<=?", (s, e))}
        firsts = {g: self.q1("SELECT MIN(id) m FROM transactions WHERE group_id=?", (g,))["m"] for g in stubs}
        loose = [dict(t, amount=stubs[t["group_id"]], transfer_id=None) if t["group_id"] in stubs else t
                 for t in loose if t["group_id"] not in stubs or t["id"] == firsts[t["group_id"]]]
        used = set()

        def typed_in(b):
            payee = (b["payee"] or "").strip().lower()
            got = []
            for t in loose:
                if t["id"] in used or t["account_id"] != b["account_id"]:
                    continue
                same_payee = bool(payee) and (t["payee"] or "").strip().lower() == payee
                if b["kind"] == "deposit":
                    ok = same_payee and t["amount"] > 0 and not t["transfer_id"]
                elif b["kind"] == "bill":
                    ok = same_payee and t["amount"] < 0 and not t["transfer_id"]
                elif b["kind"] == "transfer" and not b.get("x_link_id"):
                    ok = t["amount"] < 0 and t["other"] == b.get("to_account_id") and \
                        (same_payee or -t["amount"] == b["amount"])
                else:
                    ok = False
                if ok:
                    got.append(t)
            for t in got:
                used.add(t["id"])
            return sum(abs(t["amount"]) for t in got), len(got)

        out = []
        for b in active + gone:
            if account_ids is not None and b["account_id"] not in account_ids and b.get("to_account_id") not in account_ids:
                continue
            upcoming, overdue, d, n = 0, 0, dt.date.fromisoformat(b["next_date"]), 0
            while d and d <= end and n < 400:
                if d >= start:
                    upcoming += 1
                    overdue += d < today()
                d = next_occurrence(d, b["frequency"], b["anchor_day"])
                n += 1
            if b["kind"] == "loan":
                ln = loans.get(b.get("loan_account_id"))
                actual, entered = (ln["actual"], len(ln["group_ids"]) or (1 if ln["actual"] else 0)) if ln else (0, 0)
            else:
                h = hist.get(b["id"])
                actual, entered = (h["s"], h["n"]) if h else (0, 0)
                more, k = typed_in(b)
                actual += more
                entered += k
                # A typed entry for a date the schedule still shows as overdue is that date.
                upcoming -= min(k, overdue)
            if b["kind"] == "deposit":
                side = "in"
            elif b["kind"] in ("bill", "loan"):
                side = "out"
            elif b.get("x_link_id"):
                side = "move"
            else:
                side = "out" if liab.get(b.get("to_account_id")) else "move"
            expected = actual + upcoming * b["amount"]
            if not expected and not actual:
                continue
            out.append({"bill_id": b["id"], "payee": b["payee"] or ("Transfer" if b["kind"] == "transfer" else b["kind"].title()),
                        "kind": b["kind"], "side": side, "account_name": b["account_name"],
                        "to_account_name": b.get("to_account_name") or b.get("x_label") or "",
                        "frequency": b["frequency"], "last_day": bool(b.get("last_day")),
                        "auto": bool(b.get("auto")), "auto_enter": bool(b.get("auto_enter")),
                        "amount_mode": b.get("amount_mode"),
                        "expected": expected, "actual": actual, "entered": entered, "to_come": upcoming,
                        "x_dir": b.get("x_dir")})
        out.sort(key=lambda r: (r["side"], -r["expected"], r["payee"].lower()))
        return out

    def card_charges(self, month=None, account_ids=None):
        """For cards whose details say "track purchases": what was charged in the month
        (less refunds), what the card owes, and its next scheduled payment. Charges are
        money you'll pay later, so the scheduled-items budget shows them as pending
        rather than counting them: the card payment is what counts."""
        m, start, end = self.month_range(month)
        s, e = start.isoformat(), end.isoformat()
        out = []
        for a in self.accounts(include_closed=False):
            if a["type"] not in self.CARD_TYPES or not a["details"].get("track_purchases"):
                continue
            if account_ids is not None and a["id"] not in account_ids:
                continue
            r = self.q1("SELECT COALESCE(SUM(CASE WHEN amount<0 THEN -amount END),0) AS charged, "
                        "COALESCE(SUM(CASE WHEN amount>0 THEN amount END),0) AS credits, COUNT(*) AS n "
                        "FROM transactions WHERE account_id=? AND transfer_id IS NULL AND xlink_id IS NULL "
                        "AND date>=? AND date<=?", (a["id"], s, e))
            bill = next((b for b in self.bills() if b.get("card_account_id") == a["id"]), None)
            limit = a["details"].get("credit_limit")
            out.append({"account_id": a["id"], "name": a["name"], "charged": r["charged"], "credits": r["credits"],
                        "count": r["n"], "owed": max(0, -a["balance"]),
                        "available": (limit + a["balance"]) if limit else None,
                        "due_day": a["details"].get("due_day"),
                        "next_payment_date": bill["next_date"] if bill else None,
                        "next_payment": bill["amount"] if bill else None})
        return out

    def entered_ahead(self, month=None, account_ids=None):
        """Scheduled items already recorded with a date after this month (entered early,
        or with a later date by mistake): they count in their own month, so the
        Budget names them. Only asked for the current month; looks two months on."""
        m, start, end = self.month_range(month)
        until = (end + dt.timedelta(days=62)).isoformat()
        e = end.isoformat()
        extra, ids = self._acct_filter(account_ids, "b.account_id")
        out = [{"payee": r["payee"], "date": r["date"], "amount": r["amount"], "account_id": r["account_id"],
                "kind": r["kind"]} for r in self.q(
            "SELECT b.payee, b.kind, h.date, h.amount, t.account_id FROM bill_history h JOIN bills b ON b.id=h.bill_id "
            "LEFT JOIN transactions t ON t.id=h.transaction_id WHERE h.date>? AND h.date<=?" + extra, [e, until] + ids)]
        # Loan payments: the whole payment, one row each.
        extra, ids = self._acct_filter(account_ids, "p.account_id")
        for r in self.q("SELECT p.group_id, p.date, p.payee, p.account_id, p.id FROM transactions p "
                        "JOIN transactions q ON q.id=p.transfer_id JOIN loans l ON l.account_id=q.account_id "
                        "WHERE p.amount<0 AND p.date>? AND p.date<=?" + extra, [e, until] + ids):
            amt = -self.q1("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE "
                           + ("group_id=? AND amount<0" if r["group_id"] else "id=?"),
                           (r["group_id"] or r["id"],))["s"]
            out.append({"payee": r["payee"], "date": r["date"], "amount": amt, "account_id": r["account_id"],
                        "kind": "loan", "group_id": r["group_id"]})
        out.sort(key=lambda r: (r["date"], r["payee"]))
        return out

    @staticmethod
    def schedule_budget(month, lines):
        """Totals for the scheduled-items budget, shaped like the category budget's so
        the Home card can show either."""
        m, start, end = Store.month_range(month)
        tot = lambda side, k: sum(r[k] for r in lines if r["side"] == side)
        rows = [{**r, "name": r["payee"], "item_kind": r["kind"],
                 "kind": {"in": "income", "out": "expense", "move": "move"}[r["side"]],
                 "budget": r["expected"]} for r in lines]
        return {"mode": "schedule", "month": m, "rows": rows,
                "income_budget": tot("in", "expected"), "income_actual": tot("in", "actual"),
                "expense_budget": tot("out", "expected"), "expense_actual": tot("out", "actual"),
                "moved_budget": tot("move", "expected"), "moved_actual": tot("move", "actual"),
                "days_in_month": end.day,
                "day_of_month": min(today().day, end.day) if today().strftime("%Y-%m") == m
                else (end.day if m < today().strftime("%Y-%m") else 0)}

    def _paystub_shift(self, start, end, account_ids=None):
        """Category id -> change that makes each paystub in the range count in the budget
        as one income of its net pay (in its net pay category) instead of gross pay
        less each tax: budgets are planned around take-home pay."""
        extra, ids = self._acct_filter(account_ids, "account_id")
        stubs = self.q("SELECT group_id, net, net_category_id FROM paystubs WHERE date>=? AND date<=?" + extra,
                       [start, end] + ids)
        shift = {cid: -v for cid, v in self._group_category_sums({p["group_id"] for p in stubs}).items()}
        for p in stubs:
            if p["net_category_id"] and p["net"]:
                shift[p["net_category_id"]] = shift.get(p["net_category_id"], 0) + p["net"]
        return shift

    def _group_category_sums(self, group_ids):
        """Category id -> signed total of the category lines in these payment groups."""
        if not group_ids:
            return {}
        marks = ",".join("?" * len(group_ids))
        return {r["category_id"]: r["s"] for r in self.q(
            f"SELECT category_id, SUM(amount) s FROM transactions WHERE group_id IN ({marks}) "
            "AND transfer_id IS NULL AND category_id IS NOT NULL GROUP BY category_id", list(group_ids))}

    def scheduled_totals(self, month=None, account_ids=None):
        """Scheduled bills and deposits for a month per category, by name, so another
        environment can match them to its own categories (for shared accounts)."""
        cats = {c["id"]: c for c in self.categories()}
        sums = {}
        for cid, kind, amt in self._scheduled_rows(month, account_ids):
            sums[(cid, kind)] = sums.get((cid, kind), 0) + amt
        return [{"name": cats[cid]["name"], "parent_name": cats[cid]["parent_name"] if cats[cid]["parent_id"] else None,
                 "kind": cats[cid]["kind"], "sched_kind": kind, "total": v}
                for (cid, kind), v in sums.items() if cid in cats and v]

    def budget(self, month=None, shared=None, shared_scheduled=None, shared_loans=None):
        """Budget vs actual for one month (YYYY-MM). `shared` adds category totals from
        accounts shared into this environment (category_totals of their own files):
        each counts toward this file's category of the same name, or failing that its
        main category; what still has no budget line here is listed apart.

        Each line expects the amount typed for it, or, left at 0, what the schedule
        holds for that month: deposits for income, bills for spending, whether
        already entered or still to come (`shared_scheduled`: the same for shared
        accounts, from scheduled_totals)."""
        m, start, end = self.month_range(month)
        cats = self.categories()
        amounts = {r["category_id"]: r["amount"] for r in self.q("SELECT * FROM budget")}
        actual = self._actuals(start.isoformat(), end.isoformat())
        # Loan payments get a line each (the whole payment); their interest and escrow
        # lines then don't count again under their categories.
        loans = self.loan_lines(m)
        for cid, v in self._group_category_sums({g for ln in loans for g in ln["group_ids"]}).items():
            actual[cid] = actual.get(cid, 0) - v
        # Paystubs count at their take-home pay.
        for cid, v in self._paystub_shift(start.isoformat(), end.isoformat()).items():
            actual[cid] = actual.get(cid, 0) + v
        from_shared = {}
        by_full = {c["full_name"].lower(): c for c in cats}
        by_main = {c["name"].lower(): c for c in cats if not c["parent_id"]}
        by_id = {c["id"]: c for c in cats}

        def match(s):
            full = (f"{s['parent_name']} : {s['name']}" if s["parent_name"] else s["name"]).lower()
            c = by_full.get(full) or by_main.get((s["parent_name"] or s["name"]).lower())
            return c if c and c["kind"] == s["kind"] else None

        loose = []
        for s in shared or []:
            c = match(s)
            if c:
                actual[c["id"]] = actual.get(c["id"], 0) + s["total"]
                from_shared[c["id"]] = from_shared.get(c["id"], 0) + s["total"]
            else:
                loose.append(s)
        # What the schedule holds this month, per category (only deposits count as
        # income and only bills as spending).
        fits = {"deposit": "income", "bill": "expense"}
        scheduled = {}
        for cid, kind, amt in self._scheduled_rows(m):
            if cid in by_id and by_id[cid]["kind"] == fits[kind]:
                scheduled[cid] = scheduled.get(cid, 0) + amt
        for s in shared_scheduled or []:
            c = match(s)
            if c and c["kind"] == fits.get(s["sched_kind"]):
                scheduled[c["id"]] = scheduled.get(c["id"], 0) + s["total"]
        # Budget lines: anything with an amount, every main category marked for the
        # budget, a marked subcategory only when its main category isn't a line, and
        # anything scheduled whose main category isn't a line.
        budgeted_ids = {c["id"] for c in cats if amounts.get(c["id"])}
        budgeted_ids |= {c["id"] for c in cats if c["in_budget"] and not c["parent_id"]}
        budgeted_ids |= {c["id"] for c in cats if c["in_budget"] and c["parent_id"]
                         and c["parent_id"] not in budgeted_ids}
        budgeted_ids |= {cid for cid in scheduled if by_id[cid]["parent_id"] not in budgeted_ids}
        children = {}
        for c in cats:
            if c["parent_id"]:
                children.setdefault(c["parent_id"], []).append(c["id"])
        rows = []
        counted = set()   # categories whose amounts landed on a budget line
        for c in cats:
            if c["kind"] == "none" or c["id"] not in budgeted_ids:
                continue
            ids = [c["id"]] + [ch for ch in children.get(c["id"], []) if ch not in budgeted_ids]
            counted.update(ids)
            # A main category also counts subcategories that have no budget line of their own.
            spent = sum(actual.get(i, 0) for i in ids)
            shared_part = sum(from_shared.get(i, 0) for i in ids)
            sched = sum(scheduled.get(i, 0) for i in ids)
            sign = -1 if c["kind"] == "expense" else 1
            typed = amounts.get(c["id"], 0)
            rows.append({"category_id": c["id"], "name": c["full_name"], "kind": c["kind"],
                         "budget": typed or sched, "typed": typed, "scheduled": sched,
                         "from_schedule": not typed and sched > 0, "actual": sign * spent,
                         "shared": sign * shared_part, "in_budget": c["in_budget"]})
        for ln, is_shared in [(x, False) for x in loans] + [(x, True) for x in shared_loans or []]:
            rows.append({"category_id": None, "loan_account_id": None if is_shared else ln["loan_account_id"],
                         "loan": True, "name": ln["name"], "kind": "expense",
                         "budget": ln["scheduled"], "typed": 0, "scheduled": ln["scheduled"],
                         "from_schedule": True, "actual": ln["actual"],
                         "shared": ln["actual"] if is_shared else 0, "in_budget": 1})
        # Money in shared accounts that has no budget line here: shown apart, so it can
        # be added (when this file has the category) and isn't silently left out.
        outside = [{"category_id": cid, "name": by_id[cid]["full_name"], "kind": by_id[cid]["kind"],
                    "actual": -v if by_id[cid]["kind"] == "expense" else v}
                   for cid, v in from_shared.items() if cid not in counted and v and by_id[cid]["kind"] != "none"]
        outside += [{"category_id": None, "name": f"{s['parent_name']} : {s['name']}" if s["parent_name"] else s["name"],
                     "kind": s["kind"], "actual": -s["total"] if s["kind"] == "expense" else s["total"]}
                    for s in loose if s["kind"] in ("income", "expense")]
        outside.sort(key=lambda r: (r["kind"] != "income", r["name"].lower()))
        inc_b = sum(r["budget"] for r in rows if r["kind"] == "income")
        exp_b = sum(r["budget"] for r in rows if r["kind"] == "expense")
        inc_a = sum(r["actual"] for r in rows if r["kind"] == "income")
        exp_a = sum(r["actual"] for r in rows if r["kind"] == "expense")
        return {"month": m, "rows": rows, "income_budget": inc_b, "expense_budget": exp_b,
                "income_actual": inc_a, "expense_actual": exp_a, "shared_outside": outside,
                "includes_shared": shared is not None,
                "days_in_month": end.day,
                "day_of_month": min(today().day, end.day) if today().strftime("%Y-%m") == m
                else (end.day if m < today().strftime("%Y-%m") else 0)}

    # ----- reports ------------------------------------------------------
    # Reports can be limited to some accounts (`account_ids`): used to add an account
    # shared from another environment into this one's reports.
    @staticmethod
    def _acct_filter(account_ids, col="t.account_id"):
        if account_ids is None:
            return "", []
        ids = [int(a) for a in account_ids] or [-1]
        return f" AND {col} IN ({','.join('?' * len(ids))})", ids

    def spending_by_category(self, start, end, kind="expense", account_ids=None):
        extra, ids = self._acct_filter(account_ids)
        rows = self.q("SELECT COALESCE(p.id, c.id) AS id, COALESCE(p.name, c.name) AS name, "
                      "COALESCE(SUM(fx(t.amount, t.account_id)),0) AS total FROM transactions t JOIN categories c ON c.id=t.category_id "
                      "LEFT JOIN categories p ON p.id=c.parent_id WHERE t.transfer_id IS NULL "
                      "AND c.kind=? AND t.date>=? AND t.date<=?" + extra + " GROUP BY 1,2", [kind, start, end] + ids)
        for r in rows:
            r["total"] = -r["total"] if kind == "expense" else r["total"]
        rows = [r for r in rows if r["total"] != 0]
        rows.sort(key=lambda r: -r["total"])
        return rows

    # ----- year-end tax report ------------------------------------------------------
    @staticmethod
    def _is_earnings(*names):
        """Money that grew inside an account (interest, dividends, gains), not money put in."""
        ns = [n.lower() for n in names if n]
        return any(n == "investment income" or any(w in n for w in ("interest", "dividend", "capital gain"))
                   for n in ns)

    def tax_report(self, year, account_ids=None):
        """Everything in tax-related categories for one calendar year, with each entry,
        plus what went into and out of Health Savings Accounts (HSA)."""
        try:
            y = int(year)
        except (TypeError, ValueError):
            raise ApiError("Year must be a number, like 2026")
        if not 1900 <= y <= 2200:
            raise ApiError("Year must be a number, like 2026")
        start, end = f"{y}-01-01", f"{y}-12-31"
        extra, ids = self._acct_filter(account_ids)
        rows = self.q("SELECT t.id, t.date, t.number, t.payee, t.memo, t.amount, a.name AS account_name, "
                      "c.name AS cname, c.kind AS kind, p.name AS pname FROM transactions t "
                      "JOIN accounts a ON a.id=t.account_id JOIN categories c ON c.id=t.category_id "
                      "LEFT JOIN categories p ON p.id=c.parent_id WHERE t.transfer_id IS NULL AND c.tax_related=1 "
                      "AND c.kind IN ('income','expense') AND t.date>=? AND t.date<=? AND a.currency=?" + extra +
                      " ORDER BY t.date, t.id", [start, end, self.money_settings()["home"]] + ids)
        # Accounts in other currencies aren't in it (a tax return needs official rates).
        others = self.q("SELECT name, currency FROM accounts WHERE currency!=? AND closed=0 ORDER BY name",
                        (self.money_settings()["home"],))
        groups = {}
        for r in rows:
            name = f"{r['pname']} : {r['cname']}" if r["pname"] else r["cname"]
            g = groups.setdefault((r["kind"], name), {"name": name, "kind": r["kind"], "total": 0, "items": []})
            amt = r["amount"] if r["kind"] == "income" else -r["amount"]
            g["total"] += amt
            g["items"].append({"id": r["id"], "date": r["date"], "number": r["number"], "payee": r["payee"],
                               "memo": r["memo"], "account_name": r["account_name"], "amount": amt})
        cats = sorted(groups.values(), key=lambda g: g["name"].lower())
        from . import paystubs
        return {"year": y, "other_currencies": others, "income": [g for g in cats if g["kind"] == "income"],
                "expense": [g for g in cats if g["kind"] == "expense"],
                "hsa": self.hsa_report(y, account_ids),
                "pay": paystubs.year_summary(self, y, account_ids),
                # Paychecks with less filled in than usual for their employer this year.
                "paychecks": paystubs.report(self, f"{y}-01-01", f"{y}-12-31",
                                             set(account_ids) if account_ids is not None else None)}

    def hsa_accounts(self):
        return [a for a in self.accounts() if a["details"].get("hsa")]

    def hsa_report(self, y, account_ids=None):
        """For each HSA: contributions (counted for the year they're for), money that grew
        in it, withdrawals, and moves between HSAs (rollovers, neither). Contributions made
        Jan 1 - Apr 15 of the next year are listed so they can be counted for this one."""
        all_hsa = {a["id"]: a for a in self.hsa_accounts()}
        accts = [a for a in all_hsa.values() if account_ids is None or a["id"] in account_ids]
        out = []
        for a in accts:
            rows = self.q("SELECT t.id, t.date, t.payee, t.memo, t.amount, t.tax_year, c.name AS cname, "
                          "p.name AS pname, o.account_id AS other_id, oa.name AS other_name, oa.type AS other_type, "
                          "(o.group_id IS NOT NULL AND EXISTS(SELECT 1 FROM paystubs ps WHERE ps.group_id=o.group_id)) "
                          "AS payroll "
                          "FROM transactions t LEFT JOIN categories c ON c.id=t.category_id "
                          "LEFT JOIN categories p ON p.id=c.parent_id LEFT JOIN transactions o ON o.id=t.transfer_id "
                          "LEFT JOIN accounts oa ON oa.id=o.account_id "
                          "WHERE t.account_id=? AND t.date>=? AND t.date<=? ORDER BY t.date, t.id",
                          (a["id"], f"{y}-01-01", f"{y + 1}-04-15"))
            acc = {"id": a["id"], "name": a["name"], "source": a["details"].get("hsa_source") or "personal",
                   "contributions": [], "next_year": [], "earnings": 0, "withdrawals": [], "between": 0}
            for r in rows:
                yr = int(r["date"][:4])
                item = {"id": r["id"], "date": r["date"], "amount": abs(r["amount"]),
                        "from": r["other_name"] or r["payee"], "memo": r["memo"]}
                if r["other_id"] in all_hsa:
                    if yr == y:
                        acc["between"] += r["amount"]
                elif r["amount"] > 0 and self._is_earnings(r["cname"], r["pname"]):
                    if yr == y:
                        acc["earnings"] += r["amount"]
                elif r["amount"] > 0:
                    counts = r["tax_year"] or yr
                    # Before tax: the account's money comes from the employer, or this came
                    # out of a paycheck (a paystub line): on the W-2, not deducted.
                    item["pretax"] = acc["source"] == "employer" or bool(r["payroll"])
                    if r["payroll"]:
                        item["from"] = f"{item['from']} (payroll)"
                    # Made Jan 1 - Apr 15: may count for the year before (the IRS allows it for
                    # your own contributions; employer money counts for the W-2 year).
                    item["may_move"] = r["date"][5:] <= "04-15" and not item["pretax"]
                    item["counts_for"] = counts
                    if counts == y:
                        acc["contributions"].append(item)
                    elif yr == y + 1 and item["may_move"]:
                        acc["next_year"].append(item)
                elif yr == y:
                    item["to"] = item.pop("from")
                    item["to_card"] = r["other_type"] in self.CARD_TYPES
                    item["to_id"] = r["other_id"]
                    acc["withdrawals"].append(item)
            acc["contributed"] = sum(i["amount"] for i in acc["contributions"])
            acc["pretax"] = sum(i["amount"] for i in acc["contributions"] if i["pretax"])
            acc["after_tax"] = acc["contributed"] - acc["pretax"]
            acc["withdrawn"] = sum(i["amount"] for i in acc["withdrawals"])
            # Paid to a card from the HSA vs what that card charged this year: a gap means a
            # statement or a payment is missing (or the card isn't only for HSA spending).
            cards = {}
            for w in acc["withdrawals"]:
                if w["to_card"] and w["to_id"]:
                    cards.setdefault(w["to_id"], {"name": w["to"], "paid": 0})["paid"] += w["amount"]
            for cid, c in cards.items():
                c["charged"] = -self.q1("SELECT COALESCE(SUM(amount),0) s FROM transactions WHERE account_id=? "
                                        "AND amount<0 AND transfer_id IS NULL AND date>=? AND date<=?",
                                        (cid, f"{y}-01-01", f"{y}-12-31"))["s"]
            acc["cards"] = list(cards.values())
            out.append(acc)
        return out

    def hsa_limit(self, y):
        return (self.get_setting("hsa_limits", {}) or {}).get(str(int(y)))

    def set_hsa_limit(self, year, amount):
        try:
            y = int(year)
        except (TypeError, ValueError):
            raise ApiError("Year must be a number, like 2026")
        limits = dict(self.get_setting("hsa_limits", {}) or {})
        if amount in (None, ""):
            limits.pop(str(y), None)
        else:
            cents = abs(to_cents(amount, "HSA limit"))
            limits[str(y)] = cents
        self.set_setting("hsa_limits", limits)
        self.changed()
        return limits.get(str(y))

    def set_tax_year(self, tid, year):
        """Count an HSA contribution made Jan 1 - Apr 15 for the year before (or not)."""
        r = self.q1("SELECT t.date, t.amount, a.details FROM transactions t JOIN accounts a ON a.id=t.account_id "
                    "WHERE t.id=?", (tid,))
        if not r:
            raise ApiError("No such transaction", 404)
        det = json.loads(r["details"] or "{}")
        if not det.get("hsa") or r["amount"] <= 0:
            raise ApiError("Only money put into an HSA can count for another year")
        made = int(r["date"][:4])
        y = int(year) if year not in (None, "") else made
        payroll = self.q1("SELECT 1 FROM transactions t JOIN transactions o ON o.id=t.transfer_id "
                          "JOIN paystubs ps ON ps.group_id=o.group_id WHERE t.id=?", (tid,))
        if (det.get("hsa_source") == "employer" or payroll) and y != made:
            raise ApiError("Employer contributions count for the year they were made (as on your W-2)")
        if y not in (made, made - 1) or (y == made - 1 and r["date"][5:] > "04-15"):
            raise ApiError(f"A contribution made on {r['date']} can only count for {made}"
                           + (f" or {made - 1}" if r["date"][5:] <= "04-15" else ""))
        with self.lock:
            self.db.execute("UPDATE transactions SET tax_year=? WHERE id=?", (None if y == made else y, tid))
            self.db.commit()
            self.changed()
        return y

    def income_vs_spending(self, months=12, account_ids=None):
        first = add_months(today().replace(day=1), -(months - 1), 1)
        extra, ids = self._acct_filter(account_ids)
        rows = self.q("SELECT substr(t.date,1,7) AS month, c.kind AS kind, COALESCE(SUM(fx(t.amount, t.account_id)),0) AS total "
                      "FROM transactions t JOIN categories c ON c.id=t.category_id "
                      "WHERE t.transfer_id IS NULL AND c.kind IN ('income','expense') AND t.date>=?" + extra +
                      " GROUP BY 1,2", [first.isoformat()] + ids)
        out = []
        for i in range(months):
            m = add_months(first, i, 1).strftime("%Y-%m")
            inc = sum(r["total"] for r in rows if r["month"] == m and r["kind"] == "income")
            exp = -sum(r["total"] for r in rows if r["month"] == m and r["kind"] == "expense")
            out.append({"month": m, "income": inc, "spending": exp, "net": inc - exp})
        return out

    def net_worth_history(self, months=12, account_ids=None):
        extra_a, ids_a = self._acct_filter(account_ids, "id")
        extra_t, ids_t = self._acct_filter(account_ids, "account_id")
        accs = self.q("SELECT id, opening_balance, opening_date, fx(opening_balance, id) AS opening_home "
                      "FROM accounts WHERE 1=1" + extra_a, ids_a)
        out = []
        first = today().replace(day=1)
        for i in range(months - 1, -1, -1):
            mstart = add_months(first, -i, 1)
            mend = add_months(mstart, 1, 1) - dt.timedelta(days=1)
            if mend > today():
                mend = today()
            # Other currencies at their rough rate; left out without one.
            total = sum(a["opening_home"] or 0 for a in accs if a["opening_date"] <= mend.isoformat())
            total += self.q1("SELECT COALESCE(SUM(fx(amount, account_id)),0) s FROM transactions WHERE date<=?" + extra_t,
                             [mend.isoformat()] + ids_t)["s"]
            out.append({"month": mstart.strftime("%Y-%m"), "net_worth": total})
        return out

    def totals(self, accs):
        """What these accounts hold, per currency, and all together in the main currency
        (other currencies at their rough rate, marked approximate; left out without one)."""
        ms = self.money_settings()
        per, assets, debts, left_out, approx = {}, 0, 0, set(), False
        for a in accs:
            code = a.get("currency") or ms["home"]
            p = per.setdefault(code, {"currency": code, "assets": 0, "debts": 0, "net_worth": 0, "accounts": 0})
            p["debts" if a["liability"] else "assets"] += a["balance"]
            p["net_worth"] += a["balance"]
            p["accounts"] += 1
            h = self.to_home(a["balance"], code)
            if h is None:
                left_out.add(code)
                continue
            approx = approx or code != ms["home"]
            if a["liability"]:
                debts += h
            else:
                assets += h
        order = sorted(per.values(), key=lambda p: (p["currency"] != ms["home"], p["currency"]))
        return {"home": ms["home"], "rates": ms["rates"], "currencies": order, "assets": assets, "debts": debts,
                "net_worth": assets + debts, "approximate": approx, "left_out": sorted(left_out)}

    def summary(self, due_days=14, recent=8):
        accs = self.accounts(include_closed=False)
        t = today()
        mstart = t.replace(day=1).isoformat()
        tot = self.totals(accs)
        return {
            "today": t.isoformat(),
            "accounts": accs,
            "assets": tot["assets"], "debts": tot["debts"], "net_worth": tot["net_worth"], "money": tot,
            "upcoming": [u for u in self.upcoming(max(1, min(90, due_days))) if not u.get("split_of")],
            "spending": self.spending_by_category(mstart, t.isoformat()),
            "budget": self.budget(),
            "recent": self.transactions(limit=recent),
            "backup": self.backup_status(),
        }

    def backup_status(self):
        last = self.q1("SELECT * FROM backup_log WHERE ok=1 ORDER BY id DESC LIMIT 1")
        failed = self.q1("SELECT * FROM backup_log ORDER BY id DESC LIMIT 1")
        return {"last_ok": last, "last": failed, "pending_changes": self.dirty_since is not None}

    def log_backup(self, kind, destination, name, ok, message=""):
        with self.lock:
            self.db.execute("INSERT INTO backup_log(at,kind,destination,name,ok,message) VALUES(?,?,?,?,?,?)",
                            (dt.datetime.now().isoformat(timespec="seconds"), kind, destination, name,
                             int(ok), message[:500]))
            self.db.execute("DELETE FROM backup_log WHERE id NOT IN (SELECT id FROM backup_log "
                            "ORDER BY id DESC LIMIT 200)")
            self.db.commit()

    def backup_log(self, n=30):
        return self.q("SELECT * FROM backup_log ORDER BY id DESC LIMIT ?", (n,))


# ----- the change history for accounts, scheduled items, categories and budgets ------------
# (Entries record their own changes in save_transaction / delete_transaction.)
def _logged_save(fn, kind, table):
    def save(self, data, xid=None, *a, **k):
        before = self._snap(table, xid) if xid else None
        rid = fn(self, data, xid, *a, **k)
        self._log_row(kind, rid or xid, before, self._snap(table, rid or xid))
        return rid
    save.__doc__ = fn.__doc__
    return save


def _logged_delete(fn, kind, table, extra=None):
    def delete(self, xid, *a, **k):
        before = self._snap(table, xid)
        note = extra(self, before) if extra and before else ""
        out = fn(self, xid, *a, **k)
        self._log_row(kind, xid, before, None, note)
        return out
    delete.__doc__ = fn.__doc__
    return delete


def _logged_skip(fn):
    def skip(self, bid):
        before = self._snap("bills", bid)
        out = fn(self, bid)
        after = self._snap("bills", bid)
        self._log_row("bill", bid, before, after,
                      f"Skipped a date: {self._describe('bill', before)} (next {after['next_date'] if after else '?'})")
        return out
    return skip


def _logged_budget(fn):
    def set_budget(self, items):
        names = {c["id"]: c["full_name"] for c in self.categories()}
        state = lambda: ({r["category_id"]: r["amount"] for r in self.q("SELECT * FROM budget")},
                         {c["id"]: c["in_budget"] for c in self.categories()})
        before = state()
        out = fn(self, items)
        after = state()
        lines = []
        for cid in sorted(set(before[0]) | set(after[0]) | {c for c in after[1] if after[1][c] != before[1].get(c)},
                          key=lambda c: names.get(c, "")):
            b, a = before[0].get(cid, 0), after[0].get(cid, 0)
            if b != a:
                lines.append(f"{names.get(cid, '?')} {b / 100:,.2f} → {a / 100:,.2f}")
            elif after[1].get(cid) != before[1].get(cid):
                lines.append(f"{names.get(cid, '?')} {'added to' if after[1].get(cid) else 'taken out of'} the budget")
        if lines and self.audit:
            try:
                self.audit("budget", None, "change", {"amounts": {str(k): v for k, v in before[0].items()}},
                           {"amounts": {str(k): v for k, v in after[0].items()}}, "Budget: " + "; ".join(lines))
            except Exception:
                pass
        return out
    return set_budget


Store.save_account = _logged_save(Store.save_account, "account", "accounts")
Store.delete_account = _logged_delete(
    Store.delete_account, "account", "accounts",
    lambda self, r: f"Deleted account: {r['name']} ({r['type']}) with its "
                    f"{self.q1('SELECT COUNT(*) n FROM transactions WHERE account_id=?', (r['id'],))['n']} entries")
Store.save_bill = _logged_save(Store.save_bill, "bill", "bills")
Store.delete_bill = _logged_delete(Store.delete_bill, "bill", "bills")
Store.skip_bill = _logged_skip(Store.skip_bill)
Store.save_category = _logged_save(Store.save_category, "category", "categories")
Store.delete_category = _logged_delete(Store.delete_category, "category", "categories")
Store.set_budget = _logged_budget(Store.set_budget)
