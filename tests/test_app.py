"""Checks for the money rules and the backups (run: python -m unittest discover -s tests)."""

import base64
import datetime as dt
import gzip
import json
import os
import re
import shutil
import struct
import sys
import time
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from moneyapp.backup import BackupManager  # noqa: E402
from moneyapp.demo import load_sample  # noqa: E402
from moneyapp.server import App, make_server  # noqa: E402
from moneyapp.store import ApiError, Store, next_occurrence  # noqa: E402
from moneyapp.system import System  # noqa: E402
from moneyapp import fileio  # noqa: E402


class FakeDav(BaseHTTPRequestHandler):
    """Just enough WebDAV (like Nextcloud) to test uploads, listing, pruning and restore."""
    files = {}
    folders = {"/"}
    auth = "Basic " + base64.b64encode(b"me:secret").decode()

    def log_message(self, *a):
        pass

    def _ok(self):
        if self.headers.get("Authorization") != self.auth:
            self.send_response(401); self.end_headers(); return False
        return True

    def _end(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Like Nextcloud: only the user's own files area can be looked at or changed;
    # above it (/remote.php/, /remote.php/dav/...) requests are refused.
    strict = False
    home = "/remote.php/dav/files/me/"

    def _above_home(self, p):
        return FakeDav.strict and len(p) < len(self.home) and self.home.startswith(p)

    def do_MKCOL(self):
        if not self._ok(): return
        p = self.path.rstrip("/") + "/"
        if self._above_home(p): return self._end(403)
        if p in self.folders: return self._end(405)
        parent = p.rstrip("/").rsplit("/", 1)[0] + "/"
        if FakeDav.strict and parent not in self.folders: return self._end(409)   # parent missing
        self.folders.add(p); self._end(201)

    def do_PUT(self):
        if not self._ok(): return
        n = int(self.headers["Content-Length"])
        folder = self.path.rsplit("/", 1)[0] + "/"
        if folder not in self.folders: return self._end(409)
        self.files[self.path] = self.rfile.read(n); self._end(201)

    corrupt = False   # serve a changed byte on download (a damaged copy on the server)

    def do_GET(self):
        if not self._ok(): return
        if self.path in self.files:
            body = self.files[self.path]
            if FakeDav.corrupt:
                body = body[:-40] + bytes([body[-40] ^ 1]) + body[-39:]
            return self._end(200, body)
        self._end(404)

    def do_DELETE(self):
        if not self._ok(): return
        self.files.pop(self.path, None); self._end(204)

    def do_PROPFIND(self):
        if not self._ok(): return
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        p = self.path.rstrip("/") + "/"
        if self._above_home(p): return self._end(403)
        if p not in self.folders: return self._end(404)
        items = [f'<d:response><d:href>{p}</d:href></d:response>']
        if self.headers.get("Depth") == "1":
            for k, v in self.files.items():
                if k.rsplit("/", 1)[0] + "/" == p:
                    items.append(f'<d:response><d:href>{k}</d:href><d:propstat><d:prop>'
                                 f'<d:getcontentlength>{len(v)}</d:getcontentlength></d:prop></d:propstat></d:response>')
        self._end(207, ('<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">' + "".join(items) +
                        '</d:multistatus>').encode())


class Client:
    """A browser stand-in: keeps its sign-in cookie and sends the app's header."""

    def __init__(self, base):
        import http.cookiejar
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _req(self, method, path, body=None, env=None, header=True):
        h = {"Content-Type": "application/json"}
        if header:
            h["X-HomeLedger"] = "1"
        if env:
            h["X-HomeLedger-Env"] = str(env)
        return urllib.request.Request(self.base + path, method=method, headers=h,
                                      data=json.dumps(body).encode() if body is not None else None)

    def call(self, method, path, body=None, env=None):
        with self.opener.open(self._req(method, path, body, env)) as r:
            return json.loads(r.read())

    def status(self, method, path, body=None, env=None, header=True):
        try:
            with self.opener.open(self._req(method, path, body, env, header)) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def raw(self, path):
        with self.opener.open(self.base + path) as r:
            return r.read()


class MoneyTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.system = System(self.dir)
        self.bm = BackupManager(self.system, os.path.join(self.dir, "backups"), os.path.join(self.dir, "settings.json"))

    @property
    def store(self):
        # The Personal environment's money file (re-fetched: a restore reopens it).
        return self.system.store(1)

    def tearDown(self):
        self.system.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_default_categories(self):
        names = {c["full_name"] for c in self.store.categories()}
        for n in ("Groceries", "Dining Out", "Bills : Electricity", "Wages & Salary : Net Pay",
                  "Healthcare : Dental", "Not an Expense"):
            self.assertIn(n, names)
        g = next(c for c in self.store.categories() if c["full_name"] == "Groceries")
        self.assertTrue(g["in_budget"])

    def test_balances_and_transfers(self):
        a = self.store.save_account({"name": "Chk", "type": "Checking", "opening_balance": "100"})
        b = self.store.save_account({"name": "Sav", "type": "Savings", "opening_balance": "0"})
        self.store.save_transaction({"account_id": a, "amount": "-25.50", "payee": "Shop"})
        t = self.store.save_transaction({"account_id": a, "amount": "-40", "transfer_account_id": b})
        self.assertEqual(self.store.account(a)["balance"], 10000 - 2550 - 4000)
        self.assertEqual(self.store.account(b)["balance"], 4000)
        self.store.save_transaction({"account_id": a, "amount": "-50", "transfer_account_id": b}, t)
        self.assertEqual(self.store.account(b)["balance"], 5000)
        self.store.delete_transaction(t)
        self.assertEqual(self.store.account(b)["balance"], 0)
        with self.assertRaises(ApiError):
            self.store.save_transaction({"account_id": a, "amount": "0"})

    def test_reconcile(self):
        a = self.store.save_account({"name": "Chk", "type": "Checking", "opening_balance": "100"})
        t1 = self.store.save_transaction({"account_id": a, "amount": "-30"})
        self.store.save_transaction({"account_id": a, "amount": "-5"})
        with self.assertRaises(ApiError):
            self.store.reconcile(a, "60", None, [t1])
        self.store.reconcile(a, "70", None, [t1])
        self.assertEqual(self.store.transaction(t1)["status"], "R")

    def test_frequencies(self):
        d = dt.date(2026, 1, 31)
        self.assertEqual(next_occurrence(d, "Monthly", 31), dt.date(2026, 2, 28))
        self.assertEqual(next_occurrence(dt.date(2026, 2, 28), "Monthly", 31), dt.date(2026, 3, 31))
        self.assertEqual(next_occurrence(dt.date(2026, 1, 1), "Twice a month", 1), dt.date(2026, 1, 16))
        self.assertEqual(next_occurrence(dt.date(2026, 1, 16), "Twice a month", 1), dt.date(2026, 2, 1))
        self.assertEqual(next_occurrence(dt.date(2026, 1, 5), "Every other week", 5), dt.date(2026, 1, 19))
        self.assertIsNone(next_occurrence(d, "Only once", 31))

    def test_account_details_and_card_payment(self):
        st = self.store
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "1000",
                               "details": {"institution": "Chase", "account_number": "000123456789",
                                           "routing_number": "021000021", "website": "chase.com"}})
        d = st.account(chk)["details"]
        self.assertEqual((d["institution"], d["website"]), ("Chase", "https://chase.com"))
        for bad in ({"routing_number": "12"}, {"website": "javascript:alert(1)"}, {"interest_rate": "lots"}):
            with self.assertRaises(ApiError):
                st.save_account({"name": "X", "type": "Checking", "details": bad})
        # Editing without details (older screens) keeps them.
        st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "1000"}, chk)
        self.assertEqual(st.account(chk)["details"]["institution"], "Chase")
        # A card due on the 5th, paid from checking: one scheduled payment, kept in step.
        card = st.save_account({"name": "Visa", "type": "Credit Card",
                                "details": {"credit_limit": "5000", "due_day": "5", "auto_pay": True,
                                            "pay_from_account_id": chk, "pay_mode": "full",
                                            "track_purchases": True, "website": "https://visa.example"}})
        bills = [b for b in st.bills() if b.get("card_account_id") == card]
        self.assertEqual(len(bills), 1)
        b = bills[0]
        self.assertEqual((b["kind"], b["account_id"], b["to_account_id"], b["frequency"], b["anchor_day"]),
                         ("transfer", chk, card, "Monthly", 5))
        self.assertEqual(dt.date.fromisoformat(b["next_date"]).day, 5)
        self.assertEqual(b["pay_url"], "https://visa.example")
        groc = next(c["id"] for c in st.categories() if c["full_name"] == "Groceries")
        st.save_transaction({"account_id": card, "amount": "-80", "category_id": groc})
        st.save_transaction({"account_id": card, "amount": "-20", "category_id": groc})
        b = next(x for x in st.bills() if x.get("card_account_id") == card)
        self.assertEqual(b["amount"], 10000)                     # full balance owed
        m = dt.date.today().strftime("%Y-%m")
        cc = st.card_charges(m)
        self.assertEqual([(r["name"], r["charged"], r["owed"], r["available"]) for r in cc],
                         [("Visa", 10000, 10000, 490000)])
        # The purchases aren't "going out"; the card payment is.
        lines = st.schedule_lines(m)
        self.assertFalse(any(r["payee"] in ("", "Groceries") for r in lines if r["side"] == "out" and r["kind"] != "transfer"))
        # Due day changed: the schedule follows. Turned off: it stops.
        det = dict(st.account(card)["details"], due_day=20)
        st.save_account({"name": "Visa", "type": "Credit Card", "details": det}, card)
        self.assertEqual(next(x for x in st.bills() if x.get("card_account_id") == card)["anchor_day"], 20)
        st.save_account({"name": "Visa", "type": "Credit Card", "details": dict(det, auto_pay=False)}, card)
        self.assertFalse(any(x.get("card_account_id") == card for x in st.bills()))
        with self.assertRaises(ApiError):   # scheduling needs a due day and a paying account
            st.save_account({"name": "Visa", "type": "Credit Card", "details": {"auto_pay": True}}, card)

    def test_ofx_import(self):
        st = self.store
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "1000", "opening_date": "2030-01-01"})
        # Typed earlier by hand (2 days off the bank's date), and an automatic estimate.
        st.save_transaction({"account_id": chk, "date": "2030-01-03", "amount": "-45.10", "payee": "Gas station"})
        auto = st.save_transaction({"account_id": chk, "date": "2030-01-10", "amount": "-90", "payee": "City Power"})
        st.mark_auto(auto)
        ofx = """OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><ACCTID>000123456789</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20300105120000<TRNAMT>-45.10<FITID>A1<NAME>SHELL OIL 123</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20300111<TRNAMT>-97.42<FITID>A2<NAME>CITY POWER &amp; LIGHT</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20300115<TRNAMT>2500.00<FITID>A3<NAME>PAYROLL<MEMO>Net pay</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>3357.48<DTASOF>20300115</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""
        rows, info = fileio.parse_ofx(ofx)
        # Review first: the plan changes nothing.
        plan = fileio.plan_import(st, chk, rows)
        self.assertEqual([p["action"] for p in plan], ["match", "correct", "add"])
        self.assertEqual(len(st.transactions(account_id=chk)), 2)
        self.assertEqual(st.balance_on(chk, "2030-01-15"), 100000 - 4510 - 9000)
        # Choices: a match can become a new entry instead.
        other = st.save_account({"name": "Other", "type": "Checking"})
        st.save_transaction({"account_id": other, "date": "2030-01-05", "amount": "-45.10", "payee": "Gas"})
        r = fileio.apply_import(st, other, rows, fileio.plan_import(st, other, rows), {0: "add", 2: "skip"})
        self.assertEqual((r["added"], r["matched"], r["skipped"]), (2, 0, 1))
        self.assertEqual([p["action"] for p in plan], ["match", "correct", "add"])
        self.assertEqual([(r["date"], r["amount"], r["fitid"]) for r in rows],
                         [("2030-01-05", -4510, "A1"), ("2030-01-11", -9742, "A2"), ("2030-01-15", 250000, "A3")])
        self.assertEqual(rows[1]["payee"], "CITY POWER & LIGHT")
        self.assertEqual((info["balance"], info["balance_date"], info["account_last4"]), (335748, "2030-01-15", "6789"))
        r = fileio.import_rows(st, chk, rows)
        self.assertEqual((r["added"], r["matched"], r["corrected"]), (1, 1, 1))
        txs = {t["payee"]: t for t in st.transactions(account_id=chk)}
        self.assertEqual((txs["Gas station"]["fitid"], txs["Gas station"]["status"]), ("A1", "C"))
        self.assertEqual(txs["City Power"]["amount"], -9742)         # the estimate took the bank's amount
        self.assertEqual(st.balance_on(chk, "2030-01-15"), 335748)   # matches the bank
        # The same file again: nothing changes.
        self.assertEqual(fileio.import_rows(st, chk, rows)["added"], 0)
        self.assertEqual(len(st.transactions(account_id=chk)), 3)
        # Version 2 (XML) reads the same way.
        xml = '<?xml version="1.0"?><OFX><STMTTRN><DTPOSTED>20300201</DTPOSTED><TRNAMT>-5.00</TRNAMT><FITID>B1</FITID><NAME>Cafe</NAME></STMTTRN></OFX>'
        self.assertEqual(fileio.parse_ofx(xml)[0][0]["amount"], -500)

    def test_notifications(self):
        from moneyapp.notify import Notifier
        got = []

        class FakeNtfy(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                got.append((self.path, self.headers.get("Title"), self.headers.get("Authorization"),
                            self.rfile.read(n).decode()))
                self.send_response(200); self.end_headers()

            def log_message(self, *a):
                pass
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeNtfy)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        nt = Notifier(self.system, self.dir)
        st = self.store
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "50"})
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        st.save_bill({"kind": "bill", "payee": "Rent", "account_id": chk, "amount": "900",
                      "frequency": "Monthly", "next_date": yesterday})
        text = nt.summary()
        self.assertIn("OVERDUE", text)
        self.assertIn("Rent $900.00", text)
        self.assertIn("forecast to go below zero", text)
        # Secrets are kept but never handed back; left empty, they stay.
        pub = nt.save({"ntfy": {"enabled": True, "server": f"http://127.0.0.1:{srv.server_address[1]}",
                                "topic": "ledger-x7", "token": "tok123"}})
        self.assertEqual((pub["ntfy"]["token"], pub["ntfy"]["token_set"]), ("", True))
        nt.save({"ntfy": {"token": ""}})
        self.assertEqual(nt.settings()["ntfy"]["token"], "tok123")
        # Once a day, at its hour.
        early = dt.datetime.combine(dt.date.today(), dt.time(5, 0))
        self.assertEqual(nt.tick(early), {})
        r = nt.tick(dt.datetime.combine(dt.date.today(), dt.time(9, 0)))
        self.assertEqual(r, {"admin": {"ntfy": "ok"}})
        self.assertEqual(got[0][0], "/ledger-x7")
        self.assertEqual((got[0][1], got[0][2]), ("MoneyThistle: today", "Bearer tok123"))
        self.assertIn("Rent", got[0][3])
        self.assertEqual(nt.tick(dt.datetime.combine(dt.date.today(), dt.time(10, 0))), {})   # not twice a day
        # Someone else: their own setup, for their own environments. The admin shares the
        # email server; they only give their address (and never see the password).
        uid = self.system.create_user("jo", "another-pass", "Jo", False)
        nt.save({"email": {"enabled": False, "host": "smtp.example.com", "to": "admin@example.com",
                           "password": "s3cret"}, "share_email": True})
        pub = nt.public(uid)
        self.assertTrue(pub["shared_email_available"])
        self.assertEqual(pub["email"]["password"], "")
        pub = nt.save({"email": {"enabled": True, "use_shared": True, "to": "jo@example.com"},
                       "ntfy": {"enabled": True, "server": f"http://127.0.0.1:{srv.server_address[1]}", "topic": "jo-ledger"}}, uid)
        self.assertTrue(pub["email"]["use_shared"])
        self.assertEqual(nt.settings(uid)["email"]["host"], "")     # the server is lent at sending time, not copied
        self.system.exec("INSERT OR IGNORE INTO members(env_id,user_id,role) VALUES(1,?,'viewer')", (uid,))
        self.assertIn("Rent", nt.summary(who=uid))
        self.system.exec("DELETE FROM members WHERE user_id=?", (uid,))
        self.assertEqual(nt.summary(who=uid), "")                    # only the environments Jo is in
        self.system.exec("INSERT INTO members(env_id,user_id,role) VALUES(1,?,'viewer')", (uid,))
        self.assertNotIn("Backups", nt.summary(who=uid))
        got.clear()
        r = nt.tick(dt.datetime.combine(dt.date.today(), dt.time(9, 30)))
        self.assertEqual(r[str(uid)]["ntfy"], "ok")
        self.assertEqual(got[0][0], "/jo-ledger")
        nt.save({"share_email": False})
        with self.assertRaises(ApiError):   # no shared server any more
            nt.save({"email": {"enabled": True, "use_shared": True, "to": "jo@example.com"}}, uid)
        for bad in ({"ntfy": {"enabled": True, "server": "ftp://x", "topic": "t"}},
                    {"email": {"enabled": True, "host": ""}}, {"hour": 30}):
            with self.assertRaises(ApiError):
                nt.save(bad)

    def test_same_day_order(self):
        # A withdrawal entered before the paycheck on the same day looks like the account
        # went negative; moving the paycheck earlier puts the running balance right.
        st = self.store
        a = st.save_account({"name": "Chk", "type": "Checking", "opening_balance": "100", "opening_date": "2030-01-01"})
        w = st.save_transaction({"account_id": a, "date": "2030-01-05", "amount": "-300", "payee": "Rent"})
        p = st.save_transaction({"account_id": a, "date": "2030-01-05", "amount": "1000", "payee": "Paycheck"})
        bal = lambda: {t["payee"]: t["running_balance"] for t in st.transactions(account_id=a)}
        self.assertEqual(bal()["Rent"], -20000)                      # looks negative
        st.move_transaction(p, "earlier")
        self.assertEqual(bal(), {"Paycheck": 110000, "Rent": 80000})
        self.assertEqual([t["payee"] for t in st.transactions(account_id=a)], ["Rent", "Paycheck"])  # newest first
        # A new entry that day goes last; moving past the end does nothing.
        st.save_transaction({"account_id": a, "date": "2030-01-05", "amount": "-5", "payee": "Coffee"})
        self.assertEqual(st.transactions(account_id=a)[0]["payee"], "Coffee")
        self.assertFalse(st.move_transaction(p, "earlier")["moved"])
        with self.assertRaises(ApiError):
            st.move_transaction(p, "sideways")

    def test_card_kept_by_statement(self):
        # The person's case: a new card at 0, paid from checking; the statement balance
        # goes in so the card owes it, and the payment brings it back to 0 (not positive).
        st = self.store
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "5000",
                               "opening_date": "2030-01-01"})
        card = st.save_account({"name": "Visa", "type": "Credit Card", "opening_date": "2030-01-01",
                                "details": {"statement_day": "12", "due_day": "5", "auto_pay": True,
                                            "pay_from_account_id": chk, "pay_mode": "full", "card_mode": "statement"}})
        self.assertEqual(st.account(card)["details"]["card_mode"], "statement")
        # Paid before the statement was entered: the card went positive...
        st.save_transaction({"account_id": chk, "date": "2030-02-05", "amount": "-400", "transfer_account_id": card})
        self.assertEqual(st.account(card)["balance"], 40000)
        # ...entering the Jan 12 statement (400 owed) puts it right.
        st.enter_statement(card, "2030-01-12", "400")
        self.assertEqual(st.account(card)["balance"], 0)
        self.assertEqual(st.balance_on(card, "2030-01-12"), -40000)
        # Again for the same date replaces it, it isn't added twice.
        st.enter_statement(card, "2030-01-12", "450")
        self.assertEqual(st.account(card)["balance"], -5000)
        st.enter_statement(card, "2030-01-12", "400")
        # Editing the card's details keeps the last statement (the form doesn't send it).
        det = {k: v for k, v in st.account(card)["details"].items() if k != "last_statement"}
        st.save_account({"name": "Visa", "type": "Credit Card", "opening_date": "2030-01-01", "details": det}, card)
        self.assertEqual(st.account(card)["details"]["last_statement"]["date"], "2030-01-12")
        # Statement with the payment: Feb 12 statement 250, paid on Mar 5 through the schedule.
        bill = next(b for b in st.bills() if b.get("card_account_id") == card)
        st.db.execute("UPDATE bills SET next_date='2030-03-05' WHERE id=?", (bill["id"],)); st.db.commit()
        self.system.enter_scheduled(1, bill["id"], {"statement_balance": "250", "date": "2030-03-05"})
        self.assertEqual(st.balance_on(card, "2030-02-12"), -25000)
        self.assertEqual(st.account(card)["balance"], 0)                 # paid in full
        self.assertEqual(st.account(card)["details"]["last_statement"]["date"], "2030-02-12")
        # What's left to pay on the last statement (for the one-tap "pay the statement").
        due = st.statement_due(card)
        self.assertEqual((due["date"], due["balance"], due["left"]), ("2030-02-12", 25000, 0))   # paid in full on Mar 5
        st.enter_statement(card, "2030-03-12", "300")
        st.save_transaction({"account_id": chk, "date": "2030-03-20", "amount": "-100", "transfer_account_id": card})
        due = st.statement_due(card)
        self.assertEqual((due["balance"], due["paid_since"], due["left"]), (30000, 10000, 20000))
        self.assertIsNone(st.statement_due(chk))
        # Reminder: closed but not entered.
        self.assertEqual(Store.last_closing(12, dt.date(2030, 3, 11)), dt.date(2030, 2, 12))
        self.assertEqual(Store.last_closing(31, dt.date(2030, 3, 11)), dt.date(2030, 2, 28))
        amex = st.save_account({"name": "Amex", "type": "Credit Card", "opening_date": "2020-01-01",
                                "details": {"statement_day": "1", "card_mode": "statement"}})
        closing = Store.last_closing(1).isoformat()
        self.assertIn({"account_id": amex, "name": "Amex", "closing_date": closing, "website": ""}, st.statements_due())
        st.enter_statement(amex, closing, "120")
        self.assertNotIn("Amex", [d["name"] for d in st.statements_due()])
        st.save_account({"name": "Amex", "type": "Credit Card", "opening_date": "2020-01-01",
                         "details": {"statement_day": "1", "card_mode": "purchases"}}, amex)
        self.assertEqual(st.account(amex)["details"]["card_mode"], "purchases")   # purchases: no reminder
        with self.assertRaises(ApiError):
            st.enter_statement(chk, "2030-01-12", "10")                   # only cards

    def test_automatic_items(self):
        from moneyapp import loans
        st = self.store
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "5000"})
        sav = st.save_account({"name": "Savings", "type": "Savings"})
        past = (dt.date.today() - dt.timedelta(days=15)).isoformat()
        # An automatic transfer to savings, recorded for the person: every week due so far.
        xfer = st.save_bill({"kind": "transfer", "payee": "Auto save", "account_id": chk, "to_account_id": sav,
                             "amount": "50", "frequency": "Weekly", "next_date": past, "auto": True, "auto_enter": True})
        # Automatic but recorded by hand; and one whose amount isn't known yet.
        hand = st.save_bill({"kind": "bill", "payee": "Gym", "account_id": chk, "amount": "30",
                             "frequency": "Monthly", "next_date": past, "auto": True})
        unknown = st.save_bill({"kind": "bill", "payee": "Water", "account_id": chk, "amount": "0",
                                "amount_mode": "average", "frequency": "Monthly", "next_date": past,
                                "auto": True, "auto_enter": True})
        b = {x["id"]: x for x in st.bills()}
        self.assertEqual((b[xfer]["auto"], b[xfer]["auto_enter"], b[hand]["auto"], b[hand]["auto_enter"]), (1, 1, 1, 0))
        done = self.system.enter_automatic(1)
        self.assertEqual(len(done), 3)                                     # 15, 8 and 1 days ago
        self.assertEqual(st.account(sav)["balance"], 15000)
        self.assertTrue(all(t["auto"] for t in st.transactions(account_id=sav)))
        b = {x["id"]: x for x in st.bills()}
        self.assertGreater(b[xfer]["next_date"], dt.date.today().isoformat())
        self.assertEqual((b[hand]["next_date"], b[unknown]["next_date"]), (past, past))   # left for the person
        self.assertEqual(self.system.enter_automatic(1), [])              # not again within the minute
        # A loan payment marked automatic is recorded as its usual split.
        loan = loans.save(st, {"name": "Car", "original_amount": "10000", "apr": "6", "payments_per_year": 12,
                               "num_payments": 48, "first_payment": past, "pay_from_account_id": chk})
        lb = next(x for x in st.bills() if x["kind"] == "loan")
        st.set_bill_auto(lb["id"], True, True)
        st.db.execute("UPDATE bills SET next_date=? WHERE id=?", (dt.date.today().isoformat(), lb["id"]))
        st.db.commit()
        self.system._auto_ran.clear()
        self.system.enter_automatic(1)
        ltx = st.transactions(account_id=loan)
        self.assertTrue(ltx and all(t["auto"] for t in ltx))
        # Turning "automatic" off turns off recording too.
        self.assertEqual(st.set_bill_auto(xfer, False, True), {"auto": False, "auto_enter": False})

    def test_last_day_of_month(self):
        # Interest posted at month end: Nov 30, Dec 31, Jan 31, Feb 28...
        a = self.store.save_account({"name": "Sav", "type": "Savings"})
        bid = self.store.save_bill({"kind": "deposit", "payee": "Interest", "account_id": a, "amount": "1",
                                    "frequency": "Monthly", "next_date": "2030-11-30", "last_day": True})
        b = next(x for x in self.store.bills() if x["id"] == bid)
        self.assertTrue(b["last_day"])
        d, seen = dt.date.fromisoformat(b["next_date"]), []
        for _ in range(4):
            seen.append(d.isoformat()); d = next_occurrence(d, b["frequency"], b["anchor_day"])
        self.assertEqual(seen, ["2030-11-30", "2030-12-31", "2031-01-31", "2031-02-28"])
        # Ticking it moves a mid-month date to the month's end; unticking goes back to that day.
        self.store.save_bill({"kind": "deposit", "payee": "Interest", "account_id": a, "amount": "1",
                              "frequency": "Monthly", "next_date": "2030-12-15", "last_day": True}, bid)
        self.assertEqual(next(x for x in self.store.bills() if x["id"] == bid)["next_date"], "2030-12-31")
        self.store.save_bill({"kind": "deposit", "payee": "Interest", "account_id": a, "amount": "1",
                              "frequency": "Monthly", "next_date": "2030-11-30"}, bid)
        self.assertFalse(next(x for x in self.store.bills() if x["id"] == bid)["last_day"])

    def test_overdue_only_past_dates(self):
        a = self.store.save_account({"name": "Chk", "type": "Checking"})
        past = (dt.date.today() - dt.timedelta(days=3)).isoformat()
        self.store.save_bill({"kind": "bill", "payee": "Gym", "account_id": a, "amount": "30",
                              "frequency": "Weekly", "next_date": past})
        occ = [o for o in self.store.upcoming(31) if o["payee"] == "Gym"]
        self.assertTrue(occ[0]["overdue"])
        self.assertFalse(any(o["overdue"] for o in occ[1:]))
        self.assertGreater(len(occ), 3)

    def test_bills(self):
        a = self.store.save_account({"name": "Chk", "type": "Checking", "opening_balance": "100"})
        bid = self.store.save_bill({"kind": "bill", "payee": "Power", "account_id": a, "amount": "20",
                                    "frequency": "Monthly", "next_date": "2026-03-10"})
        self.store.enter_bill(bid)
        self.assertEqual(self.store.account(a)["balance"], 8000)
        self.assertEqual(self.store.bills()[0]["next_date"], "2026-04-10")
        self.store.skip_bill(bid)
        self.assertEqual(self.store.bills()[0]["next_date"], "2026-05-10")

    def test_sample_reports_budget(self):
        self.assertTrue(load_sample(self.store))
        s = self.store.summary()
        self.assertEqual(len(s["accounts"]), 5)
        self.assertTrue(s["spending"] or dt.date.today().day < 3)
        self.assertEqual(len(self.store.income_vs_spending(12)), 12)
        b = self.store.budget()
        self.assertTrue(any(r["name"] == "Groceries" and r["budget"] == 52000 for r in b["rows"]))

    def test_budget_expects_scheduled(self):
        # A paycheck every other week whose amount varies: the budget's expected income
        # for the month is what was entered plus what's still to come, unless an
        # amount is typed for the line.
        a = self.store.save_account({"name": "Chk", "type": "Checking"})
        pay = next(c["id"] for c in self.store.categories() if c["full_name"] == "Wages & Salary : Net Pay")
        bid = self.store.save_bill({"kind": "deposit", "payee": "Payroll", "account_id": a, "amount": "2000",
                                    "amount_mode": "average", "category_id": pay,
                                    "frequency": "Every other week", "next_date": "2030-03-06"})
        self.store.enter_bill(bid, {"amount": "2100"})          # Mar 6, entered at 2100
        b = self.store.budget("2030-03")
        row = next(r for r in b["rows"] if r["name"] in ("Wages & Salary", "Wages & Salary : Net Pay"))
        self.assertEqual((row["scheduled"], row["budget"], row["from_schedule"]), (420000, 420000, True))  # + Mar 20 at the 2100 average
        self.assertEqual(b["income_budget"], 420000)
        self.assertEqual(b["income_actual"], 210000)
        self.assertEqual(self.store.budget("2030-04")["income_budget"], 420000)   # Apr 3 and 17
        self.store.set_budget([{"category_id": row["category_id"], "amount": "5000"}])
        row = next(r for r in self.store.budget("2030-03")["rows"] if r["category_id"] == row["category_id"])
        self.assertEqual((row["budget"], row["scheduled"], row["from_schedule"]), (500000, 420000, False))
        # Interest on savings, scheduled monthly as a reminder with an amount that varies:
        # its estimate counts, then the average of what was entered.
        sav = self.store.save_account({"name": "Sav", "type": "Savings"})
        interest = next(c["id"] for c in self.store.categories() if c["full_name"] == "Investment Income : Interest")
        ib = self.store.save_bill({"kind": "deposit", "payee": "Interest", "account_id": sav, "amount": "3.50",
                                   "amount_mode": "average", "category_id": interest,
                                   "frequency": "Monthly", "next_date": "2030-03-31"})
        inv = lambda m: next(r for r in self.store.budget(m)["rows"] if r["name"] in ("Investment Income", "Investment Income : Interest"))
        self.assertEqual(inv("2030-03")["budget"], 350)
        self.store.enter_bill(ib, {"amount": "4.10"})
        self.assertEqual((inv("2030-03")["budget"], inv("2030-03")["actual"]), (410, 410))
        self.assertEqual(inv("2030-04")["budget"], 410)          # next month expects the average

    def test_import_csv_and_qif(self):
        a = self.store.save_account({"name": "Chk", "type": "Checking"})
        rows = fileio.parse_csv("Date,Description,Amount,Category\n01/05/2026,Fresh Market,-42.10,Groceries\n"
                                "01/06/2026,Payroll,1000.00,\n")
        r = fileio.import_rows(self.store, a, rows)
        self.assertEqual(r["added"], 2)
        self.assertEqual(fileio.import_rows(self.store, a, rows)["skipped"], 2)
        q = fileio.parse_qif("!Type:Bank\nD1/7/26\nT-9.99\nPStreamly\nLHobbies/Leisure:Movies & Video Rentals\n^\n")
        fileio.import_rows(self.store, a, q)
        tx = self.store.transactions(account_id=a)
        self.assertEqual(tx[0]["category_label"], "Hobbies/Leisure : Movies & Video Rentals")
        self.assertEqual(self.store.account(a)["balance"], 100000 - 4210 - 999)

    def test_backup_defaults_and_limits(self):
        s = self.bm.settings()
        self.assertEqual((s["on_change"], s["keep_change"], s["scheduled"], s["interval_days"],
                          s["keep_scheduled"], s["compress"]), (True, 3, True, 14, 3, True))
        with self.assertRaises(ApiError):
            self.bm.update_settings({"interval_days": 100})
        # Never backed up: the scheduled one is due straight away (original: -1 means never).
        self.assertIn("scheduled", self.bm.due())

    def test_local_backup_prune_restore(self):
        a = self.store.save_account({"name": "Chk", "type": "Checking", "opening_balance": "1"})
        names = []
        for i in range(5):
            r = self.bm.run("auto")
            names.append(r[0]["name"])
            # unique timestamps
            os.utime(self.dir)
            import time; time.sleep(1.05)
        left = [b for b in self.bm.list_all()["backups"] if b["kind"] == "auto"]
        self.assertEqual(len(left), 3)
        self.store.delete_account(a)
        self.assertEqual(self.store.accounts(), [])
        self.bm.restore("folder", left[0]["name"])
        self.assertEqual(len(self.store.accounts()), 1)
        with open(os.path.join(self.dir, "backups", left[0]["name"]), "rb") as f:
            import zipfile, io
            names = zipfile.ZipFile(io.BytesIO(f.read())).namelist()
        self.assertIn("system.db", names)
        self.assertIn("money.db", names)

    def test_webdav_backup(self):
        FakeDav.files, FakeDav.folders = {}, {"/"}
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeDav)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}/remote.php/dav/files/me/Backups/Money"
            self.bm.update_settings({"local_enabled": False, "webdav_enabled": True, "webdav_url": url,
                                     "webdav_user": "me", "webdav_password": "secret"})
            self.store.save_account({"name": "Chk", "type": "Checking", "opening_balance": "5"})
            r = self.bm.run("scheduled")
            self.assertTrue(r[0]["ok"], r)
            lst = self.bm.list_all()
            self.assertEqual(len(lst["backups"]), 1, lst)
            self.assertEqual(self.bm.settings()["last_scheduled"], dt.date.today().isoformat())
            self.store.delete_account(self.store.accounts()[0]["id"])
            self.bm.restore("webdav", lst["backups"][0]["name"])
            self.assertEqual(self.store.accounts()[0]["name"], "Chk")
            self.bm.update_settings({"webdav_password": "wrong"})
            r = self.bm.run("manual")
            self.assertFalse(r[0]["ok"])
            self.assertIn("refused", r[0]["error"])
            self.assertNotIn("webdav_password", self.bm.public_settings())
        finally:
            srv.shutdown()

    def test_webdav_creates_missing_folders(self):
        # Like Nextcloud: only the user's own files can be touched; the backup folder
        # (three levels deep, none of them there yet) is created, then used.
        FakeDav.files, FakeDav.folders, FakeDav.corrupt = {}, {"/", FakeDav.home}, False
        FakeDav.strict = True
        self.addCleanup(setattr, FakeDav, "strict", False)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeDav)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}/remote.php/dav/files/me/Finance/Backups/Money Thistle"
        self.bm.update_settings({"local_enabled": False, "webdav_enabled": True, "webdav_url": url,
                                 "webdav_user": "me", "webdav_password": "secret"})
        r = self.bm.run("manual")[0]
        self.assertTrue(r["ok"], r)
        for f in ("/remote.php/dav/files/me/Finance/", "/remote.php/dav/files/me/Finance/Backups/",
                  "/remote.php/dav/files/me/Finance/Backups/Money%20Thistle/"):
            self.assertIn(f, FakeDav.folders)
        self.assertEqual(len(self.bm.list_all()["backups"]), 1)
        self.assertTrue(self.bm.run("manual")[0]["ok"])            # and again, now that it's there

    def test_encryption_vectors(self):
        from moneyapp import crypt
        # RFC 8439, 2.4.2: the "sunscreen" test vector.
        pt = (b"Ladies and Gentlemen of the class of '99: If I could offer you only one tip for "
              b"the future, sunscreen would be it.")
        ct = crypt.chacha20(bytes(range(32)), bytes.fromhex("000000000000004a00000000"), pt, 1)
        self.assertEqual(ct.hex(), "6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0b"
                                   "f91b65c5524733ab8f593dabcd62b3571639d624e65152ab8f530c359f0861d8"
                                   "07ca0dbf500d6a6156a38e088a22b65e52bc514d16ccf806818ce91ab7793736"
                                   "5af90bbf74a35be6b40b8eedf2785e42874d")
        blob = crypt.encrypt(b"money", "a long password")
        self.assertNotIn(b"money", blob)
        self.assertEqual(crypt.decrypt(blob, "a long password"), b"money")
        with self.assertRaises(ApiError):
            crypt.decrypt(blob, "wrong password!")
        with self.assertRaises(ApiError):   # one changed byte is refused, never half-read
            crypt.decrypt(blob[:60] + bytes([blob[60] ^ 1]) + blob[61:], "a long password")

    def test_encrypted_webdav_backup_verified(self):
        # Encrypted backup to a WebDAV server: read back after upload (same SHA-256,
        # decrypts, every file in the zip opens) before it counts; restorable with the
        # password; a copy damaged on the server is caught and removed.
        import hashlib
        FakeDav.files, FakeDav.folders, FakeDav.corrupt = {}, {"/"}, False
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeDav)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}/remote.php/dav/files/me/Backups/Money"
        with self.assertRaises(ApiError):   # encryption needs a password
            self.bm.update_settings({"encrypt": True})
        with self.assertRaises(ApiError):   # a long one
            self.bm.update_settings({"encrypt": True, "backup_password": "short"})
        self.bm.update_settings({"local_enabled": False, "webdav_enabled": True, "webdav_url": url,
                                 "webdav_user": "me", "webdav_password": "secret",
                                 "encrypt": True, "backup_password": "correct horse battery"})
        self.assertTrue(self.bm.public_settings()["backup_password_set"])
        self.assertNotIn("backup_password", self.bm.public_settings())
        self.store.save_account({"name": "Chk", "type": "Checking", "opening_balance": "5"})
        r = self.bm.run("manual")[0]
        self.assertTrue(r["ok"] and r["verified"] and r["encrypted"], r)
        self.assertTrue(r["name"].endswith(".zip.enc"))
        stored = next(v for k, v in FakeDav.files.items() if k.endswith(r["name"]))
        self.assertEqual(hashlib.sha256(stored).hexdigest(), r["sha256"])
        self.assertTrue(stored.startswith(b"HLEDGER-ENC1"))
        self.assertNotIn(b"SQLite format", stored)              # nothing readable on the server
        v = self.bm.verify("webdav", r["name"])
        self.assertEqual((v["ok"], v["sha256"], v["encrypted"]), (True, r["sha256"], True))
        # Restore: with the saved password; on a "new computer" (password not saved) only
        # with the right one typed in.
        self.store.delete_account(self.store.accounts()[0]["id"])
        self.bm.restore("webdav", r["name"])
        self.assertEqual(self.store.accounts()[0]["name"], "Chk")
        cur = self.bm._load(); cur["backup_password"] = ""; cur["encrypt"] = False; self.bm._save(cur)
        with self.assertRaises(ApiError):
            self.bm.restore("webdav", r["name"])
        with self.assertRaises(ApiError):
            self.bm.restore("webdav", r["name"], "not the password")
        self.bm.restore("webdav", r["name"], "correct horse battery")
        # A copy that comes back changed: not a success, and the bad copy is removed.
        self.bm.update_settings({"encrypt": True, "backup_password": "correct horse battery"})
        FakeDav.corrupt = True
        bad = self.bm.run("manual")[0]
        FakeDav.corrupt = False
        self.assertFalse(bad["ok"])
        self.assertIn("Verification failed", bad["error"])
        self.assertEqual(sum(1 for k in FakeDav.files if k.endswith(".zip.enc")), 1)   # only the good one is left

    def _serve(self):
        app = App(self.system, self.bm)
        httpd = make_server(app, "127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        return app, f"http://127.0.0.1:{httpd.server_address[1]}"

    def test_reports_across_environments(self):
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        me = c.call("GET", "/api/me")["user"]["id"]
        home = self.system.create_env(me, "Household")
        p, h = self.system.store(1), self.system.store(home)
        groc_p = next(x["id"] for x in p.categories() if x["full_name"] == "Groceries")
        groc_h = next(x["id"] for x in h.categories() if x["full_name"] == "Groceries")
        mine = p.save_account({"name": "My Checking", "type": "Checking", "opening_balance": "100"})
        joint = h.save_account({"name": "Joint Checking", "type": "Checking", "opening_balance": "1000"})
        today = dt.date.today().isoformat()
        p.save_transaction({"account_id": mine, "date": today, "amount": "-30", "payee": "Shop", "category_id": groc_p})
        h.save_transaction({"account_id": joint, "date": today, "amount": "-70", "payee": "Market", "category_id": groc_h})
        # The joint account is also shared into Personal: it must count once across both.
        sid = self.system.request_share(me, home, joint, "alex", "view")
        self.system.approve_share(me, sid, 1)
        q = f"kind=expense&from={today}&to={today}"
        one = {r["name"]: r["total"] for r in c.call("GET", f"/api/reports/spending?{q}", env=1)}
        self.assertEqual(one["Groceries"], 10000)   # Personal, with the shared joint account
        both = {r["name"]: r["total"] for r in c.call("GET", f"/api/reports/spending?{q}&scope=all", env=1)}
        self.assertEqual(both["Groceries"], 10000)  # not 17000: the shared account counts once
        entries = c.call("GET", f"/api/reports/entries?name=Groceries&{q}", env=1)
        self.assertEqual(sorted(e["amount"] for e in entries), [-7000, -3000])
        self.assertIn("(Household)", next(e for e in entries if e["amount"] == -7000)["account_name"])
        nw = c.call("GET", "/api/reports/networth?months=1&scope=all", env=1)[-1]["net_worth"]
        self.assertEqual(nw, 10000 - 3000 + 100000 - 7000)
        f = c.call("GET", "/api/forecast?days=30&scope=all", env=1)
        self.assertEqual(sorted(a["name"] for a in f["accounts"]), ["Joint Checking · Household", "My Checking · Personal"])
        tax = c.call("GET", f"/api/reports/tax?year={today[:4]}&scope=all", env=1)
        self.assertEqual(tax["all_envs"], ["Personal", "Household"])
        self.assertEqual(c.call("GET", "/api/reports/monthly?months=1&scope=all", env=1)[-1]["spending"], 10000)

    def test_change_history_and_undo(self):
        app, base = self._serve()
        a = Client(base)
        a.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        me = a.call("GET", "/api/me")["user"]["id"]
        a.call("POST", "/api/users", {"username": "tati", "password": "tati-pass-1", "display_name": "Tati"})
        home = self.system.create_env(me, "Household")
        self.system.set_member(home, "tati", "editor")
        h = self.system.store(home)
        chk = h.save_account({"name": "Joint Checking", "type": "Checking", "opening_balance": "1000"})
        sav = h.save_account({"name": "Joint Savings", "type": "Savings"})
        t = Client(base)
        t.call("POST", "/api/login", {"username": "tati", "password": "tati-pass-1"})
        tid = t.call("POST", "/api/transactions", {"account_id": chk, "amount": "-42.10", "payee": "Market"}, env=home)["id"]
        t.call("PUT", f"/api/transactions/{tid}", {"account_id": chk, "amount": "-45.10", "payee": "Market"}, env=home)
        t.call("DELETE", f"/api/transactions/{tid}", env=home)
        xid = t.call("POST", "/api/transactions", {"account_id": chk, "amount": "-100", "payee": "Save",
                                                    "transfer_account_id": sav}, env=home)["id"]
        t.call("DELETE", f"/api/transactions/{xid}", env=home)
        hist = a.call("GET", "/api/history")["ops"]
        self.assertEqual([o["user"] for o in hist[:5]], ["Tati"] * 5)
        self.assertTrue(hist[0]["summary"] if "summary" in hist[0] else hist[0]["changes"][0]["summary"].startswith("Deleted entry"))
        self.assertEqual(len(hist[0]["changes"]), 2)          # a transfer: both sides, one action
        self.assertEqual(hist[0]["env_name"], "Household")
        # Undo the transfer's deletion: both sides come back, tied together again.
        a.call("POST", "/api/history/undo", {"op": hist[0]["op"]})
        self.assertEqual(h.account(chk)["balance"], 100000 - 10000)
        self.assertEqual(h.account(sav)["balance"], 10000)
        back = h.q1("SELECT transfer_id FROM transactions WHERE id=?", (xid,))
        self.assertTrue(back["transfer_id"])
        self.assertEqual(a.status("POST", "/api/history/undo", {"op": hist[0]["op"]}), 400)   # already undone
        # Undo the deletion of the market entry, then its change: it's as first entered.
        # (The transfer was given the market entry's old number, so pick the one-change delete.)
        del_op = next(o for o in hist if len(o["changes"]) == 1 and o["changes"][0]["action"] == "delete")
        chg_op = next(o for o in hist if o["changes"][0]["action"] == "change" and o["changes"][0]["object_id"] == tid)
        self.assertEqual(a.status("POST", "/api/history/undo", {"op": chg_op["op"]}), 400)   # later delete first
        a.call("POST", "/api/history/undo", {"op": del_op["op"]})
        a.call("POST", "/api/history/undo", {"op": chg_op["op"]})
        market = h.q1("SELECT id, amount FROM transactions WHERE payee='Market'")
        self.assertEqual(market["amount"], -4210)
        self.assertEqual(h.account(sav)["balance"], 10000)   # the transfer that took its old number is untouched
        # One entry's own history, oldest first, names who did what.
        mine = t.call("GET", f"/api/history/transaction/{market['id']}", env=home)
        self.assertEqual([o["changes"][0]["action"] for o in mine], ["add", "change", "delete", "undo", "undo"])
        self.assertEqual(mine[0]["user"], "Tati")
        self.assertEqual(mine[-1]["user"], "alex")
        # Someone who only views can't undo; nobody sees environments they're not in.
        self.system.set_member(home, "tati", "viewer")
        last = t.call("GET", "/api/history")["ops"][0]
        self.assertFalse(last["can_undo"])
        self.assertEqual(t.status("GET", "/api/history?env=1"), 403)
        # Budget amounts, scheduled items and accounts are recorded too.
        groc = next(c["id"] for c in h.categories() if c["full_name"] == "Groceries")
        a.call("PUT", "/api/budget", {"items": [{"category_id": groc, "amount": "300"}]}, env=home)
        bid = a.call("POST", "/api/bills", {"kind": "bill", "payee": "Power", "account_id": chk, "amount": "80",
                                            "frequency": "Monthly", "next_date": "2026-12-05"}, env=home)["id"]
        a.call("POST", f"/api/bills/{bid}/skip", env=home)
        ops = a.call("GET", f"/api/history?env={home}")["ops"]
        sums = [o["changes"][0]["summary"] for o in ops[:3]]
        self.assertTrue(sums[0].startswith("Skipped a date: Power"))
        self.assertTrue(sums[1].startswith("Added scheduled item: Power"))
        self.assertIn("Groceries 0.00 → 300.00", sums[2])
        a.call("POST", "/api/history/undo", {"op": ops[0]["op"]})   # the skip
        self.assertEqual(h.q1("SELECT next_date FROM bills WHERE id=?", (bid,))["next_date"], "2026-12-05")

    def test_starting_and_stopping(self):
        from moneyapp import autostart
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        self.assertFalse(c.call("GET", "/api/admin/startup")["supported"])   # not started by main.py
        app.launch_args = ["--data", self.dir]
        stopped = []
        app.request_stop = lambda why="": stopped.append(why)
        self.assertTrue(c.call("GET", "/api/meta")["can_shutdown"])
        # Shortcuts and the sign-in start-up go into this person's own folders (here: a test folder).
        fake = os.path.join(self.dir, "home")
        if autostart.platform() == "windows":
            autostart._folders.update(startup=os.path.join(fake, "Startup"), programs=os.path.join(fake, "Programs"),
                                      desktop=os.path.join(fake, "Desktop"))
            self.addCleanup(autostart._folders.clear)
        else:
            self._env(XDG_CONFIG_HOME=os.path.join(fake, "cfg"), XDG_DATA_HOME=os.path.join(fake, "share"), HOME=fake)
        a = autostart.Autostart(self.dir, app.launch_args)
        if autostart.platform() != "mac":
            # The Start menu entries are made by themselves (at every start, when missing or moved).
            self.assertFalse(a.menu_current())
            a.ensure_menu()
            self.assertTrue(a.menu_current())
            self.assertFalse(autostart.Autostart(self.dir, ["--data", "elsewhere"]).menu_current())
        st = c.call("PUT", "/api/admin/startup", {"desktop": True, "login": True})
        if autostart.platform() != "mac":
            self.assertTrue(st["menu"] and st["desktop"])
        self.assertTrue(st["login"] and not st["always"])
        self.assertTrue(st["local"])          # this test's browser is on the same computer
        made = [os.path.join(r, f) for r, _, fs in os.walk(fake) for f in fs]
        self.assertTrue(made and all(os.path.getsize(p) > 0 for p in made))
        st = c.call("PUT", "/api/admin/startup", {"desktop": False, "login": False})
        self.assertFalse(st["login"] or st["desktop"])
        # The same computer reached at its own network address still counts as this computer.
        app.ctx.addr, app.ctx.server_addr = "192.168.4.20", "192.168.4.20"
        self.assertTrue(app._local())
        app.ctx.addr = "192.168.4.33"
        self.assertFalse(app._local())
        # The icon is a real Windows icon made of the app's pictures.
        with open(autostart.icon_path(self.dir), "rb") as f:
            ico = f.read()
        self.assertEqual(ico[:4], b"\x00\x00\x01\x00")
        self.assertGreaterEqual(struct.unpack("<H", ico[4:6])[0], 2)
        # Starting with Windows: a task with no 3-day time limit, as Windows' own account.
        script = a._service_script()
        self.assertIn("-ExecutionTimeLimit ([TimeSpan]::Zero)", script)
        self.assertIn("-AtStartup", script)
        self.assertIn("'SYSTEM'", script)
        self.assertIn(self.dir.replace("'", "''"), script)
        # Shutting down: administrators only.
        c.call("POST", "/api/users", {"username": "vic", "password": "vic-pass-12"})
        v = Client(base)
        v.call("POST", "/api/login", {"username": "vic", "password": "vic-pass-12"})
        self.assertEqual(v.status("POST", "/api/admin/shutdown"), 403)
        self.assertTrue(c.call("POST", "/api/admin/shutdown")["stopping"])
        time.sleep(0.8)
        self.assertEqual(stopped, ["the Shut down button (alex)"])

    def test_sign_in_kept_or_not(self):
        from moneyapp import system as sysmod
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        # Not kept: a browser-session cookie, ended after an hour unused.
        req = c._req("POST", "/api/login", {"username": "alex", "password": "correct-horse"})
        with c.opener.open(req) as r:
            self.assertNotIn("Max-Age", r.headers["Set-Cookie"])
        s = self.system.q1("SELECT * FROM sessions ORDER BY created DESC LIMIT 1")
        self.assertEqual(s["remember"], 0)
        with self.system.lock:
            self.system.db.execute("UPDATE sessions SET last_used=? WHERE token_hash=?",
                                   (time.time() - sysmod.IDLE_MINUTES * 60 - 5, s["token_hash"]))
            self.system.db.commit()
        self.assertEqual(c.status("GET", "/api/me"), 401)
        # Kept on this device: 30 days.
        req = c._req("POST", "/api/login", {"username": "alex", "password": "correct-horse", "remember": True})
        with c.opener.open(req) as r:
            self.assertIn(f"Max-Age={30 * 86400}", r.headers["Set-Cookie"])
        s = self.system.q1("SELECT * FROM sessions ORDER BY created DESC LIMIT 1")
        self.assertEqual(s["remember"], 1)
        with self.system.lock:
            self.system.db.execute("UPDATE sessions SET last_used=? WHERE token_hash=?", (time.time() - 86400, s["token_hash"]))
            self.system.db.commit()
        self.assertEqual(c.call("GET", "/api/me")["user"]["username"], "alex")

    def test_addresses_looked_up_again(self):
        app, base = self._serve()
        found = [["http://localhost:8080/", "http://172.22.112.1:8080/"]]
        app.urls, app.find_urls = found[0], lambda: found[0]
        c = Client(base)
        self.assertEqual(c.call("GET", "/api/meta")["addresses"], found[0])
        # Wi-Fi connects after MoneyThistle started with the computer: the list follows.
        found[0] = ["http://localhost:8080/", "http://192.168.4.201:8080/", "http://172.22.112.1:8080/"]
        app._urls_at = 0
        self.assertIn("http://192.168.4.201:8080/", c.call("GET", "/api/meta")["addresses"])

    def test_start_with_computer_choice_is_read_back(self):
        from moneyapp import autostart
        a = autostart.Autostart(self.dir, ["--data", self.dir])
        # Windows PowerShell 5 writes a byte-order mark: it must still read as "on".
        with open(os.path.join(self.dir, "autostart.json"), "wb") as f:
            f.write(b'\xef\xbb\xbf{"always": true}\r\n')
        self.assertTrue(a._load()["always"])
        a._save(folders={"startup": "S", "programs": "P", "desktop": "D"})
        self.assertEqual(a._load(), {"always": True, "folders": {"startup": "S", "programs": "P", "desktop": "D"}})

    def _env(self, **kw):
        old = {k: os.environ.get(k) for k in kw}
        os.environ.update(kw)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in old.items()])

    def test_start_over_from_a_backup_file(self):
        import base64 as b64
        # The old computer: a sign-in, an entry, a receipt, an encrypted backup file.
        old = System(os.path.join(self.dir, "old"))
        old_bm = BackupManager(old, os.path.join(self.dir, "old", "backups"), os.path.join(self.dir, "old", "s.json"))
        old.create_user("alex", "correct-horse", "Alex", True)
        st = old.store(1)
        acct = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "250"})
        st.save_transaction({"account_id": acct, "amount": "-12", "payee": "Hardware"})
        from moneyapp import attachments, crypt
        tid = st.q1("SELECT id FROM transactions")["id"]
        attachments.add(old, st, old.data_dir, tid, 1, {"name": "r.pdf", "data": b64.b64encode(b"%PDF-1.4 r").decode()})
        blob = crypt.encrypt(old.snapshot_bytes(), "a long backup password")
        old.close()
        # The new computer: a fresh install, nobody set up yet.
        app, base = self._serve()
        c = Client(base)
        self.assertTrue(c.call("GET", "/api/meta")["needs_setup"])

        def upload(path, data, pw=None, client=c):
            h = {"X-HomeLedger": "1", "Content-Type": "application/octet-stream", "X-File-Name": "money-auto-x.zip.enc"}
            if pw:
                h["X-Backup-Password"] = b64.b64encode(pw.encode()).decode()
            req = urllib.request.Request(base + path, data=data, method="POST", headers=h)
            try:
                with client.opener.open(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        self.assertEqual(upload("/api/setup/restore-upload", blob, "wrong password")[0], 400)
        self.assertTrue(c.call("GET", "/api/meta")["needs_setup"])          # nothing changed
        code, r = upload("/api/setup/restore-upload", blob, "a long backup password")
        self.assertEqual((code, r["people"]), (200, ["alex"]))
        self.assertFalse(c.call("GET", "/api/meta")["needs_setup"])
        c.call("POST", "/api/login", {"username": "alex", "password": "correct-horse"})
        self.assertEqual([t["payee"] for t in c.call("GET", f"/api/transactions?account={acct}", env=1)], ["Hardware"])
        files = c.call("GET", "/api/attachments", env=1)["files"]
        with c.opener.open(urllib.request.Request(f"{base}/api/attachments/{files[0]['id']}?env=1")) as resp:
            self.assertEqual(resp.read(), b"%PDF-1.4 r")                     # receipts come back too
        self.assertTrue(self.bm.settings()["encrypt"])                         # new backups use the same password
        # Once set up, the start-over door is shut; administrators restore from the Backups page.
        self.assertEqual(upload("/api/setup/restore-upload", blob, "a long backup password", Client(base))[0], 403)
        self.assertEqual(Client(base).status("POST", "/api/setup/webdav-list", {"url": "https://x/"}), 403)
        code, r = upload("/api/backup/restore-upload", blob)          # the saved password is used
        self.assertEqual(code, 200)
        self.assertTrue(any(n.startswith("money-manual-") for n in os.listdir(self.bm.settings()["local_dir"])))

    def test_restore_on_the_command_line(self):
        import subprocess
        src = System(os.path.join(self.dir, "src"))
        src.create_user("alex", "correct-horse", "", True)
        src.store(1).save_account({"name": "Savings", "type": "Savings", "opening_balance": "9"})
        path = os.path.join(self.dir, "money-manual-20261122-120000.zip")
        with open(path, "wb") as f:
            f.write(src.snapshot_bytes())
        src.close()
        dest = os.path.join(self.dir, "dest")
        main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
        r = subprocess.run([sys.executable, main, "--restore", path, "--data", dest, "--port", "8197"],
                           capture_output=True, text=True, timeout=120, env=dict(os.environ, NO_SHORTCUTS="1"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Sign-ins in it: alex", r.stdout)
        back = System(dest)
        self.assertEqual([a["name"] for a in back.store(1).accounts()], ["Savings"])
        back.close()

    def test_paychecks_take_home_and_flags(self):
        from moneyapp import paystubs
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        st = self.system.store(1)
        chk = st.save_account({"name": "Checking", "type": "Checking"})
        cat = lambda full: next(x["id"] for x in st.categories() if x["full_name"] == full)
        gross_c, fed_c, med_c = cat("Wages & Salary : Gross Pay"), cat("Taxes : Federal Income Tax"), cat("Taxes : Medicare Tax")

        def stub(date, lines, employer="Acme"):
            return c.call("POST", "/api/paystubs", {"employer": employer, "date": date, "account_id": chk, "lines": lines}, env=1)
        full = lambda: [{"side": "earn", "label": "Gross pay", "amount": "2000", "category_id": gross_c},
                        {"side": "deduct", "label": "Federal income tax", "amount": "200", "category_id": fed_c},
                        {"side": "deduct", "label": "Medicare", "amount": "29", "category_id": med_c}]
        # Usually every tax and deduction from Acme.
        for d in ("2026-01-02", "2026-01-16", "2026-01-30"):
            stub(d, full())
        # A scheduled paycheck: entered as take-home only, it's marked and flagged.
        bid = c.call("POST", "/api/bills", {"kind": "deposit", "payee": "Acme", "account_id": chk, "amount": "1771",
                                            "frequency": "Every other week", "next_date": "2026-02-13", "paycheck": True}, env=1)["id"]
        self.assertEqual(st.q1("SELECT paycheck FROM bills WHERE id=?", (bid,))["paycheck"], 1)
        tid = c.call("POST", f"/api/bills/{bid}/enter", {"amount": "1771", "take_home": True}, env=1)["id"]
        row = next(t for t in c.call("GET", f"/api/transactions?account={chk}", env=1) if t["id"] == tid)
        self.assertEqual((row["paycheck"], row["pay_flag"]), (1, "missing gross pay and deductions"))
        # A detailed paystub without the usual Medicare: flagged with what's missing.
        g = stub("2026-02-27", [full()[0], full()[1]])["group_id"]
        self.assertEqual(paystubs.flags(st)[("stub", g)], "missing: Medicare")
        # "Complete as is" stops the flag; the paystub says so.
        c.call("POST", "/api/paychecks/complete", {"kind": "stub", "id": g, "complete": True}, env=1)
        self.assertNotIn(("stub", g), paystubs.flags(st))
        self.assertTrue(c.call("GET", f"/api/paystubs/{g}", env=1)["complete"])
        # Adding the paystub details later takes the take-home entry's place, once in the schedule's history.
        r = c.call("POST", "/api/paystubs", {"employer": "Acme", "date": "2026-02-13", "account_id": chk,
                                             "lines": full(), "replace_tx": tid}, env=1)
        self.assertIsNone(st.q1("SELECT id FROM transactions WHERE id=?", (tid,)))
        hist = st.q("SELECT transaction_id FROM bill_history WHERE bill_id=?", (bid,))
        self.assertEqual([h["transaction_id"] for h in hist], [r["ids"][0]])
        self.assertEqual(st.q1("SELECT bill_id FROM paystubs WHERE group_id=?", (r["group_id"],))["bill_id"], bid)
        self.assertEqual(paystubs.flags(st), {})
        # Someone who only ever records take-home pay is never flagged.
        n1 = c.call("POST", "/api/paychecks/net", {"employer": "Corner Cafe", "date": "2026-03-01", "account_id": chk, "net": "640.15"}, env=1)
        c.call("POST", "/api/paychecks/net", {"employer": "Corner Cafe", "date": "2026-03-15", "account_id": chk, "net": "610"}, env=1)
        self.assertEqual(st.q1("SELECT paycheck, amount FROM transactions WHERE id=?", (n1["id"],)), {"paycheck": 1, "amount": 64015})
        self.assertEqual(paystubs.flags(st), {})
        # The tax report lists each employer's paychecks and what's usual for them.
        rep = {e["employer"]: e for e in c.call("GET", "/api/reports/tax?year=2026", env=1)["paychecks"]}
        self.assertEqual((rep["Acme"]["usual"], rep["Acme"]["flagged"]), ("detail", []))
        self.assertEqual((rep["Corner Cafe"]["usual"], rep["Corner Cafe"]["take_home_only"]), ("net", 2))
        self.assertEqual(c.status("POST", "/api/paychecks/net", {"employer": "X", "date": "2026-03-01", "account_id": chk, "net": ""}, env=1), 400)

    def test_paystub_other_deductions(self):
        from moneyapp import paystubs
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        st = self.system.store(1)
        chk = st.save_account({"name": "Checking", "type": "Checking"})
        cat = lambda full: next(x["id"] for x in st.categories() if x["full_name"] == full)
        gross_c, fed_c = cat("Wages & Salary : Gross Pay"), cat("Taxes : Federal Income Tax")

        def stub(date, lines, employer="Acme"):
            return c.call("POST", "/api/paystubs", {"employer": employer, "date": date, "account_id": chk, "lines": lines}, env=1)
        gross = lambda a="2000": {"side": "earn", "label": "Gross pay", "amount": a, "category_id": gross_c}
        fed = lambda a="200": {"side": "deduct", "label": "Federal income tax", "amount": a, "category_id": fed_c}
        other = lambda a: {"side": "deduct", "label": "Other deductions", "amount": a, "other": True}
        # Acme is usually fully itemized; a paycheck with $300 left over is flagged.
        for d in ("2026-01-02", "2026-01-16", "2026-01-30"):
            stub(d, [gross(), fed()])
        r = stub("2026-02-13", [gross(), fed(), other("300")])
        self.assertEqual(r["net"], 150000)
        self.assertEqual(paystubs.flags(st)[("stub", r["group_id"])], "$300.00 not itemized")
        # The remainder goes to its own expense category and keeps its name.
        p = c.call("GET", f"/api/paystubs/{r['group_id']}", env=1)
        oth = next(ln for ln in p["lines"] if ln.get("other"))
        self.assertEqual((oth["label"], oth["amount"]), ("Other deductions", 30000))
        self.assertEqual(next(x for x in st.categories() if x["id"] == oth["category_id"])["name"], "Paycheck Deductions")
        self.assertEqual(p["flag"], "$300.00 not itemized")
        # Beta usually gives only gross and take-home: the rest in Other deductions isn't flagged.
        for d in ("2026-01-09", "2026-01-23", "2026-02-06"):
            stub(d, [gross("1500"), other("400")], employer="Beta")
        self.assertEqual({k: v for k, v in paystubs.flags(st).items() if k[1] != r["group_id"]}, {})
        rep = {e["employer"]: e for e in c.call("GET", "/api/reports/tax?year=2026", env=1)["paychecks"]}
        self.assertEqual(rep["Beta"]["usual"], "gross")
        # Something added after taxes (a reimbursement) raises take-home pay.
        a = stub("2026-02-20", [gross(), fed(), {"side": "add", "label": "Mileage reimbursement", "amount": "50"}], employer="Gamma")
        self.assertEqual((a["gross"], a["net"]), (200000, 185000))
        amounts = sorted(t["amount"] for t in st.q("SELECT amount FROM transactions WHERE id IN (%s)" % ",".join("?" * len(a["ids"])), a["ids"]))
        self.assertIn(5000, amounts)
        # A paystub picture attached to a take-home paycheck stays with it when the details
        # are added, and when that paystub is edited again.
        import base64
        n = c.call("POST", "/api/paychecks/net", {"employer": "Delta", "date": "2026-03-06", "account_id": chk, "net": "1800"}, env=1)
        c.call("POST", f"/api/transactions/{n['id']}/attachments",
               {"name": "stub.pdf", "data": base64.b64encode(b"%PDF-1.4 stub").decode()}, env=1)
        d = c.call("POST", "/api/paystubs", {"employer": "Delta", "date": "2026-03-06", "account_id": chk,
                                             "lines": [gross("2000"), fed()], "replace_tx": n["id"]}, env=1)
        self.assertEqual([x["name"] for x in c.call("GET", f"/api/transactions/{d['ids'][0]}/attachments", env=1)], ["stub.pdf"])
        d2 = c.call("PUT", f"/api/paystubs/{d['group_id']}", {"employer": "Delta", "date": "2026-03-06", "account_id": chk,
                                                               "lines": [gross("2000"), fed("150")]}, env=1)
        self.assertEqual([x["name"] for x in c.call("GET", f"/api/transactions/{d2['ids'][0]}/attachments", env=1)], ["stub.pdf"])

    def test_backup_without_serialize(self):
        """Python 3.10 has no Connection.serialize(): backups copy through a temporary file."""
        import io
        import sqlite3
        import zipfile
        from moneyapp import store as store_mod
        self.system.store(1).save_account({"name": "Checking", "type": "Checking", "opening_balance": "12.34"})
        was = store_mod._SERIALIZE
        try:
            for flag in (False, True):
                store_mod._SERIALIZE = flag
                z = zipfile.ZipFile(io.BytesIO(self.system.snapshot_bytes()))
                money = next(n for n in z.namelist() if n.endswith(".db") and n != "system.db")
                p = os.path.join(self.dir, f"check-{flag}.db")
                with open(p, "wb") as f:
                    f.write(z.read(money))
                con = sqlite3.connect(p)
                self.assertEqual(con.execute("SELECT opening_balance FROM accounts").fetchone()[0], 1234)
                con.close()
        finally:
            store_mod._SERIALIZE = was

    def test_start_fresh(self):
        """Sample data, then Start fresh: an empty file with the starting categories, the old one kept."""
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        env = c.call("GET", "/api/me")["envs"][0]
        self.assertFalse(env["sample_data"])
        c.call("PUT", "/api/money", {"home": "CAD"}, env=1)
        c.call("POST", "/api/sample", {}, env=1)
        self.assertTrue(c.call("GET", "/api/me")["envs"][0]["sample_data"])
        self.assertTrue(c.call("GET", "/api/accounts", env=1))
        # Sample data goes with one click.
        r = c.call("POST", f"/api/envs/{env['id']}/start-fresh", {})
        self.assertIn("before-reset", r["kept"])
        self.assertTrue(os.path.exists(os.path.join(self.dir, r["kept"])))
        self.assertEqual(c.call("GET", "/api/accounts", env=1), [])
        self.assertEqual(c.call("GET", "/api/bills", env=1)["bills"], [])
        cats = c.call("GET", "/api/categories", env=1)
        cats = cats.get("categories", cats) if isinstance(cats, dict) else cats
        self.assertTrue(any(x["name"] == "Bills" and x["names"].get("pt") == "Contas" for x in cats))
        self.assertEqual(c.call("GET", "/api/money", env=1)["home"], "CAD")   # a preference, kept
        self.assertFalse(c.call("GET", "/api/me")["envs"][0]["sample_data"])
        # Real data needs the environment's name typed.
        c.call("POST", "/api/accounts", {"name": "Mine", "type": "Checking", "opening_balance": "10"}, env=1)
        self.assertEqual(c.status("POST", f"/api/envs/{env['id']}/start-fresh", {"confirm": "nope"}), 400)
        self.assertTrue(c.call("GET", "/api/accounts", env=1))
        c.call("POST", f"/api/envs/{env['id']}/start-fresh", {"confirm": env["name"].upper()})
        self.assertEqual(c.call("GET", "/api/accounts", env=1), [])

    def test_category_names(self):
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        cats = c.call("GET", "/api/categories", env=1)
        cats = cats.get("categories", cats) if isinstance(cats, dict) else cats
        bills = next(x for x in cats if x["name"] == "Bills" and not x["parent_id"])
        self.assertEqual(bills["names"].get("pt"), "Contas")
        self.assertEqual(bills["names"].get("fr"), "Factures")
        # A name per language is set, changed and removed; the category's own name stays.
        c.call("PUT", f"/api/categories/{bills['id']}", {"name": "Bills", "kind": "expense",
                                                         "names": {"pt": "Contas da casa", "es": ""}}, env=1)
        st = self.system.store(1)
        names = st.category_names()[bills["id"]]
        self.assertEqual(names.get("pt"), "Contas da casa")
        self.assertNotIn("es", names)
        self.assertEqual(names.get("fr"), "Factures")
        self.assertEqual(st.q1("SELECT name FROM categories WHERE id=?", (bills["id"],))["name"], "Bills")
        # A new category typed in Portuguese, with its English name.
        cid = c.call("POST", "/api/categories", {"name": "Mercado", "kind": "expense",
                                                 "names": {"pt": "Mercado", "en": "Market"}}, env=1)["id"]
        self.assertEqual(st.category_names()[cid], {"pt": "Mercado", "en": "Market"})
        # The paystub insurance subcategories are there, with their names.
        ins = st.q1("SELECT id FROM categories WHERE name='Insurance' AND parent_id IS NULL")["id"]
        subs = {r["name"]: r["id"] for r in st.q("SELECT id, name FROM categories WHERE parent_id=?", (ins,))}
        for n in ("Accident", "Dental", "Disability", "Legal Plan", "Vision", "Health"):
            self.assertIn(n, subs)
        self.assertEqual(st.category_names()[subs["Dental"]].get("pt"), "Odontológico")
        # A file from before them gets them once; one deleted afterwards stays deleted.
        st.db.execute("DELETE FROM categories WHERE id IN (?,?)", (subs["Dental"], subs["Vision"]))
        st.db.execute("DELETE FROM settings WHERE key='categories_v2'")
        st.db.commit()
        st._add_new_categories()
        dental = st.q1("SELECT id FROM categories WHERE name='Dental' AND parent_id=?", (ins,))
        self.assertTrue(dental)
        self.assertEqual(st.category_names()[dental["id"]].get("fr"), "Dentaire")
        st.db.execute("DELETE FROM categories WHERE id=?", (dental["id"],))
        st.db.commit()
        st._add_new_categories()
        self.assertFalse(st.q1("SELECT id FROM categories WHERE name='Dental' AND parent_id=?", (ins,)))
        # Paycheck savings without the account they go to: Savings & Investments, added to older files.
        sav = st.q1("SELECT id FROM categories WHERE name='Savings & Investments' AND parent_id IS NULL")
        self.assertTrue(sav)
        st.db.execute("DELETE FROM categories WHERE id=? OR parent_id=?", (sav["id"], sav["id"]))
        st.db.execute("DELETE FROM settings WHERE key='categories_v3'")
        st.db.commit()
        st._add_new_categories()
        sav = st.q1("SELECT id FROM categories WHERE name='Savings & Investments' AND parent_id IS NULL")
        self.assertEqual(st.category_names()[sav["id"]].get("pt"), "Poupança e investimentos")
        ret = st.q1("SELECT id FROM categories WHERE name='Retirement Plan' AND parent_id=?", (sav["id"],))
        self.assertEqual(st.category_names()[ret["id"]].get("es"), "Plan de jubilación")
        self.assertFalse(st.q1("SELECT id FROM categories WHERE name='Dental' AND parent_id=?", (ins,)))

    def test_currencies(self):
        from moneyapp.store import to_cents
        # Amounts typed in the styles of the Americas and Europe.
        for typed, cents in (("1,234.56", 123456), ("R$ 1.234,56", 123456), ("1 234,56", 123456), ("1234,5", 123450),
                             ("1,080", 108000), ("12.50", 1250), ("(12.00)", -1200), ("-5", -500), ("$80", 8000)):
            self.assertEqual(to_cents(typed), cents, typed)
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        st = self.system.store(1)
        us = c.call("POST", "/api/accounts", {"name": "US Checking", "type": "Checking", "opening_balance": "1000"}, env=1)["id"]
        br = c.call("POST", "/api/accounts", {"name": "Brazil", "type": "Checking", "currency": "BRL", "opening_balance": "500"}, env=1)["id"]
        self.assertEqual(st.account(us)["currency"], "USD")
        self.assertEqual(st.account(br)["currency"], "BRL")
        self.assertEqual(c.status("POST", "/api/accounts", {"name": "X", "type": "Checking", "currency": "XYZ"}, env=1), 400)
        # A transfer between currencies needs what arrived; it's kept on the other side.
        self.assertEqual(c.status("POST", "/api/transactions", {"account_id": us, "date": "2026-03-01", "amount": "-200",
                                                                 "transfer_account_id": br}, env=1), 400)
        tid = c.call("POST", "/api/transactions", {"account_id": us, "date": "2026-03-01", "amount": "-200",
                                                   "transfer_account_id": br, "received": "1080"}, env=1)["id"]
        self.assertEqual(st.account(us)["balance"], 80000)
        self.assertEqual(st.account(br)["balance"], 158000)
        row = st.transaction(tid)
        self.assertEqual((row["transfer_amount"], row["transfer_currency"]), (108000, "BRL"))
        # Changing the date alone keeps what arrived.
        c.call("PUT", f"/api/transactions/{tid}", {"account_id": us, "date": "2026-03-02", "amount": "-200",
                                                   "transfer_account_id": br}, env=1)
        self.assertEqual(st.account(br)["balance"], 158000)
        # Totals: per currency, and together only with a rough rate (marked approximate).
        m = c.call("GET", "/api/summary", env=1)["money"]
        self.assertEqual([(x["currency"], x["net_worth"]) for x in m["currencies"]], [("USD", 80000), ("BRL", 158000)])
        self.assertEqual((m["net_worth"], m["left_out"], m["approximate"]), (80000, ["BRL"], False))
        self.assertEqual(c.status("PUT", "/api/money", {"rates": {"BRL": "abc"}}, env=1), 400)
        c.call("PUT", "/api/money", {"rates": {"BRL": "0,20"}}, env=1)
        m = c.call("GET", "/api/summary", env=1)["money"]
        self.assertEqual((m["net_worth"], m["left_out"], m["approximate"]), (80000 + 31600, [], True))
        # Spending in reais counts in reports at the rough rate.
        cat = next(x["id"] for x in st.categories() if x["kind"] == "expense")
        c.call("POST", "/api/transactions", {"account_id": br, "date": "2026-03-05", "amount": "-100", "category_id": cat}, env=1)
        rows = st.spending_by_category("2026-03-01", "2026-03-31")
        self.assertEqual(sum(r["total"] for r in rows), 2000)
        # The tax report keeps to the main currency and names the others.
        self.assertEqual([a["name"] for a in st.tax_report(2026)["other_currencies"]], ["Brazil"])
        # A scheduled transfer can say what usually arrives.
        bid = c.call("POST", "/api/bills", {"kind": "transfer", "payee": "To Brazil", "account_id": us, "to_account_id": br,
                                            "amount": "100", "received": "540", "frequency": "Monthly",
                                            "next_date": "2026-04-01"}, env=1)["id"]
        c.call("POST", f"/api/bills/{bid}/enter", {}, env=1)
        self.assertEqual(st.account(br)["balance"], 158000 - 10000 + 54000)

    def test_simple_or_everything(self):
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        # Any new install's first person, and every new sign-in, starts Simple.
        self.assertEqual(c.call("GET", "/api/settings")["detail"], "simple")
        c.call("POST", "/api/users", {"username": "sis", "password": "sister-pass-1"})
        c.call("POST", "/api/users", {"username": "pro", "password": "pro-pass-123", "show_everything": True})
        self.assertEqual(self.system.ui_settings(self.system.q1("SELECT id FROM users WHERE username='sis'")["id"])["detail"], "simple")
        self.assertEqual(self.system.ui_settings(self.system.q1("SELECT id FROM users WHERE username='pro'")["id"])["detail"], "full")
        # Sign-ins from before the choice existed keep everything.
        with self.system.lock:
            self.system.db.execute("UPDATE users SET ui_json='{}' WHERE username='alex'")
            self.system.db.commit()
        self.assertEqual(c.call("GET", "/api/settings")["detail"], "full")
        # Folds are remembered per person and place; a new overall choice starts them afresh.
        s = c.call("PUT", "/api/settings", {"folds": {"paystub": True, "entry": False, "Bad Key!": True}})
        self.assertEqual(s["folds"], {"paystub": True, "entry": False})
        s = c.call("PUT", "/api/settings", {"folds": {"entry": None}})
        self.assertEqual(s["folds"], {"paystub": True})
        s = c.call("PUT", "/api/settings", {"detail": "simple"})
        self.assertEqual((s["detail"], s["folds"]), ("simple", {}))
        self.assertEqual(c.status("PUT", "/api/settings", {"detail": "expert"}), 400)

    def test_backup_knows_its_version(self):
        import io, zipfile
        from moneyapp import version
        self.assertTrue(version.newer("1.10.0", "1.2.0"))
        self.assertFalse(version.newer("1.0.0", "1.0.0"))
        self.assertTrue(version.newer("2.0", "1.9.9"))
        snap = self.system.snapshot_bytes()
        self.assertEqual(System.backup_info(snap)["version"], version.VERSION)
        self.system.restore_bytes(snap)                        # same version: fine

        def stamped(v):
            src = zipfile.ZipFile(io.BytesIO(snap))
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for n in src.namelist():
                    data = src.read(n)
                    if n == "moneythistle-backup.json":
                        info = json.loads(data)
                        if v is None:
                            info.pop("version")
                        else:
                            info["version"] = v
                        data = json.dumps(info).encode()
                    z.writestr(n, data)
            return buf.getvalue()
        self.system.restore_bytes(stamped(None))               # from before 1.0.0: fine
        self.system.restore_bytes(stamped("0.9.0"))            # older: fine (newer code reads older data)
        with self.assertRaises(ApiError) as e:
            self.system.restore_bytes(stamped("99.0.0"))       # newer: update first
        self.assertIn("Update MoneyThistle to 99.0.0", str(e.exception))

    def test_deleting_a_backup(self):
        folder = os.path.join(self.dir, "bk")
        self.bm.update_settings({"local_enabled": True, "local_dir": folder})
        first = self.bm.run("manual")[0]["name"]
        time.sleep(1.1)
        second = self.bm.run("manual")[0]["name"]
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        self.assertEqual(c.call("POST", "/api/backup/delete", {"destination": "folder", "name": first}), {"deleted": first})
        self.assertEqual(os.listdir(folder), [second])
        # The last one stays; names that aren't backups (or try to leave the folder) are refused.
        self.assertEqual(c.status("POST", "/api/backup/delete", {"destination": "folder", "name": second}), 400)
        self.assertEqual(c.status("POST", "/api/backup/delete", {"destination": "folder", "name": "..\\system.db"}), 400)
        self.assertEqual(os.listdir(folder), [second])
        self.assertEqual(self.system.backup_log(1)[0]["kind"], "delete")
        # Administrators only.
        c.call("POST", "/api/users", {"username": "vic", "password": "vic-pass-12"})
        v = Client(base)
        v.call("POST", "/api/login", {"username": "vic", "password": "vic-pass-12"})
        self.assertEqual(v.status("POST", "/api/backup/delete", {"destination": "folder", "name": second}), 403)

    def test_source_code_of_this_copy(self):
        import io, zipfile
        from moneyapp import version
        # A copy's own program files, with a data folder, backups and settings beside it.
        root = os.path.join(self.dir, "copy")
        os.makedirs(os.path.join(root, "moneyapp", "static"))
        os.makedirs(os.path.join(root, "data"))
        for p, text in (("main.py", "print('changed')"), ("moneyapp/server.py", "x = 1"), ("LICENSE", "AGPL"),
                        ("moneyapp/static/app.js", "//"), ("data/money.db", "SECRET"), ("settings.json", "pw"),
                        ("moneyapp/backup.db", "SECRET")):
            with open(os.path.join(root, p), "w") as f:
                f.write(text)
        z = zipfile.ZipFile(io.BytesIO(version.source_zip(root)))
        names = sorted(z.namelist())
        self.assertEqual(names, ["moneythistle/LICENSE", "moneythistle/main.py",
                                 "moneythistle/moneyapp/server.py", "moneythistle/moneyapp/static/app.js"])
        self.assertEqual(z.read("moneythistle/main.py"), b"print('changed')")   # changes included
        # Anyone using it can download it, signed in or not.
        app, base = self._serve()
        with urllib.request.urlopen(base + "/api/source.zip") as r:
            self.assertEqual(r.headers["Content-Type"], "application/zip")
            got = zipfile.ZipFile(io.BytesIO(r.read())).namelist()
        self.assertIn("moneythistle/main.py", got)
        self.assertFalse(any("/data/" in n or n.endswith((".db", "settings.json")) for n in got))

    def test_backups_kept_daily_weekly_monthly(self):
        from moneyapp.backup import keep_plan
        s = {"keep_change": 3, "keep_scheduled": 3, "keep_daily": 7, "keep_weekly": 4, "keep_monthly": 12}
        name = lambda d, kind="auto": f"money-{kind}-{d:%Y%m%d-%H%M%S}.zip.enc"
        today = dt.datetime(2026, 11, 22, 20, 0)
        # A busy day: morning, noon and evening backups, then the days and months before.
        names = [name(today.replace(hour=h)) for h in (8, 12, 20)]
        names += [name(today - dt.timedelta(days=d, hours=2)) for d in range(1, 120)]
        names.append(name(today - dt.timedelta(days=3), "manual"))
        keep = keep_plan(names, s)
        self.assertEqual(keep[name(today.replace(hour=20))], "recent")
        self.assertIn(name(today - dt.timedelta(days=1, hours=2)), keep)      # yesterday survives the busy day
        self.assertEqual(keep[name(today - dt.timedelta(days=6, hours=2))], "daily")
        self.assertEqual(keep[name(today - dt.timedelta(days=7, hours=2))], "weekly")   # Sunday: last of its week
        self.assertNotIn(name(today - dt.timedelta(days=8, hours=2)), keep)  # 7 days in all, counting today
        self.assertEqual(sorted(n[11:19] for n, v in keep.items() if v == "weekly"), ["20261101", "20261108", "20261115"])
        self.assertEqual(sorted(n[11:19] for n, v in keep.items() if v == "monthly"),
                         ["20260731", "20260831", "20260930", "20261031"])   # last of each month (all there is)
        self.assertNotIn(name(today - dt.timedelta(days=3), "manual"), keep)  # manual: never in the plan, never deleted
        # Pruning a folder keeps exactly the plan (and every manual backup).
        folder = os.path.join(self.dir, "tiers")
        os.makedirs(folder)
        for n in names:
            open(os.path.join(folder, n), "wb").close()
        from moneyapp.backup import LocalTarget
        self.bm._prune(LocalTarget(folder), "auto", dict(self.bm.settings(), **s))
        left = set(os.listdir(folder))
        self.assertEqual(left, set(keep) | {name(today - dt.timedelta(days=3), "manual")})
        self.assertLess(len(left), 30)
        # Settings: limits, 0 turns a tier off.
        self.assertEqual(self.bm.update_settings({"keep_monthly": 0})["keep_monthly"], 0)
        with self.assertRaises(ApiError):
            self.bm.update_settings({"keep_daily": 120})

    def test_backup_after_start_never_waits_forever(self):
        # Tidying old receipts at start once left each untouched money file with an unfinished
        # change, and every backup waited for it forever (no backup, and every page hung).
        import threading
        self.system.create_env(self.system.create_user("alex", "correct-horse", "", True), "Household")
        App(self.system, self.bm)          # tidies at start
        for e in self.system.q("SELECT id FROM environments"):
            self.assertFalse(self.system.store(e["id"]).db.in_transaction)
        # And a change left open by mistake anywhere doesn't stop a backup either.
        st = self.system.store(1)
        st.db.execute("UPDATE settings SET value=value WHERE 0")
        st.db.execute("INSERT INTO settings(key,value) VALUES('leftover','1')")
        done = []
        t = threading.Thread(target=lambda: done.append(self.system.snapshot_bytes()), daemon=True)
        t.start(); t.join(20)
        self.assertTrue(done, "the backup waited forever")
        self.bm.update_settings({"local_enabled": True, "local_dir": os.path.join(self.dir, "bk")})
        self.assertTrue(self.bm.run("manual")[0]["ok"])

    def test_backups_while_entries_are_saved_never_hang(self):
        # A backup reading everything while entries are saved (each recording its change)
        # once took two locks in opposite orders and every page hung.
        import threading
        st = self.system.store(1)
        self.assertIs(st.lock, self.system.lock)
        acct = st.save_account({"name": "Chk", "type": "Checking", "opening_balance": "10"})
        stop, errors = threading.Event(), []

        def saving():
            try:
                for i in range(150):
                    st.save_transaction({"account_id": acct, "amount": "-1", "payee": f"P{i}"})
            except Exception as e:
                errors.append(e)

        def backing_up():
            try:
                while not stop.is_set():
                    self.system.snapshot_bytes()
            except Exception as e:
                errors.append(e)
        a, b = threading.Thread(target=saving, daemon=True), threading.Thread(target=backing_up, daemon=True)
        a.start(); b.start()
        a.join(60)
        stop.set(); b.join(60)
        self.assertFalse(a.is_alive() or b.is_alive(), "saving and backing up waited for each other")
        self.assertEqual(errors, [])

    def test_receipts_attached_to_entries(self):
        import base64, hashlib, io, zipfile
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        st = self.system.store(1)
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "100"})
        tid = c.call("POST", "/api/transactions", {"account_id": chk, "amount": "-12.34", "payee": "Hardware"}, env=1)["id"]
        photo = b"\xff\xd8\xff\xe0" + b"receipt pixels" * 50
        sha = hashlib.sha256(photo).hexdigest()
        r = c.call("POST", f"/api/transactions/{tid}/attachments",
                   {"name": "IMG_0042.JPG", "data": base64.b64encode(photo).decode()}, env=1)
        self.assertEqual([a["name"] for a in r["attachments"]], ["IMG_0042.JPG"])
        aid = r["id"]
        # Kept once in the data folder, named by its contents; the register shows a paper clip.
        self.assertTrue(os.path.exists(os.path.join(self.dir, "attachments", sha)))
        row = next(t for t in c.call("GET", f"/api/transactions?account={chk}", env=1) if t["id"] == tid)
        self.assertEqual(row["attachments"], 1)
        # Opened in the browser: the file itself, with its type (a link passes the environment in the address).
        with c.opener.open(urllib.request.Request(f"{base}/api/attachments/{aid}?env=1")) as resp:
            self.assertEqual((resp.read(), resp.headers["Content-Type"]), (photo, "image/jpeg"))
        # Only photos and PDFs, recognised by their contents (not their name).
        bad = base64.b64encode(b"<script>alert(1)</script>").decode()
        self.assertEqual(c.status("POST", f"/api/transactions/{tid}/attachments", {"name": "x.jpg", "data": bad}, env=1), 400)
        pdf = c.call("POST", f"/api/transactions/{tid}/attachments",
                     {"name": "invoice", "data": base64.b64encode(b"%PDF-1.4 hello").decode()}, env=1)
        self.assertEqual(pdf["attachments"][1]["name"], "invoice.pdf")
        # In every backup, and back after a restore.
        z = zipfile.ZipFile(io.BytesIO(self.system.snapshot_bytes()))
        self.assertEqual(z.read("attachments/" + sha), photo)
        snap = self.system.snapshot_bytes()
        os.remove(os.path.join(self.dir, "attachments", sha))
        self.system.restore_bytes(snap)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "attachments", sha)))
        # Deleting the entry sets its receipts aside; undoing the delete brings them back.
        c.call("DELETE", f"/api/transactions/{tid}", env=1)
        st = self.system.store(1)
        self.assertEqual(st.q1("SELECT COUNT(*) n FROM attachments WHERE transaction_id IS NOT NULL")["n"], 0)
        newer = c.call("POST", "/api/transactions", {"account_id": chk, "amount": "-1", "payee": "Other"}, env=1)["id"]
        self.assertEqual(c.call("GET", f"/api/transactions/{newer}/attachments", env=1), [])   # not someone else's receipts
        op = next(o for o in c.call("GET", "/api/history")["ops"] if o["changes"][0]["action"] == "delete"
                  and o["changes"][0]["kind"] == "transaction")
        c.call("POST", "/api/history/undo", {"op": op["op"]})
        back = st.q1("SELECT id FROM transactions WHERE payee='Hardware'")["id"]
        self.assertEqual(len(c.call("GET", f"/api/transactions/{back}/attachments", env=1)), 2)
        # Removing one; the history says who attached and removed what.
        c.call("DELETE", f"/api/attachments/{aid}", env=1)
        self.assertEqual(len(c.call("GET", f"/api/transactions/{back}/attachments", env=1)), 1)
        sums = [o["changes"][0]["summary"] for o in c.call("GET", "/api/history")["ops"][:2]]
        self.assertTrue(sums[0].startswith("Removed IMG_0042.JPG from Hardware"))
        # Files nothing lists any more are cleared away (the PDF stays).
        from moneyapp import attachments
        attachments.tidy(self.system)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "attachments", sha)))
        self.assertEqual(len(os.listdir(os.path.join(self.dir, "attachments"))), 1)
        # Papers kept with an account (no entry): a card where only statements are entered.
        card = st.save_account({"name": "Costco Visa", "type": "Credit Card"})
        tv = c.call("POST", f"/api/accounts/{card}/attachments",
                    {"name": "tv.pdf", "data": base64.b64encode(b"%PDF-1.4 tv").decode(),
                     "note": "Big TV, warranty 2 years", "doc_date": "2026-03-14"}, env=1)
        self.assertEqual([(a["name"], a["note"], a["doc_date"]) for a in tv["attachments"]],
                         [("tv.pdf", "Big TV, warranty 2 years", "2026-03-14")])
        tv_id = tv["id"]
        with c.opener.open(urllib.request.Request(f"{base}/api/attachments/{tv_id}?env=1")) as resp:
            self.assertEqual(resp.read(), b"%PDF-1.4 tv")
        # Notes can be added or changed later; search finds words in notes, payees, accounts.
        pdf_id = pdf["id"]
        c.call("PUT", f"/api/attachments/{pdf_id}", {"note": "Drill invoice"}, env=1)
        found = lambda qs: [f["name"] for f in c.call("GET", "/api/attachments" + qs, env=1)["files"]]
        self.assertEqual(found("?q=warranty"), ["tv.pdf"])
        self.assertEqual(found("?q=hardware"), ["invoice.pdf"])          # the entry's payee
        self.assertEqual(found("?q=drill+invoice"), ["invoice.pdf"])     # every word must be found
        self.assertEqual(found("?q=costco"), ["tv.pdf"])                 # the account's name
        self.assertEqual(found(f"?account={card}"), ["tv.pdf"])
        self.assertEqual(found("?from=2026-03-01&to=2026-03-31"), ["tv.pdf"])
        self.assertEqual(sorted(found("")), ["invoice.pdf", "tv.pdf"])
        self.assertEqual(c.status("PUT", f"/api/attachments/{tv_id}", {"doc_date": "soon"}, env=1), 400)
        # Moving the card to another environment takes its papers along.
        me = c.call("GET", "/api/me")["user"]["id"]
        biz = self.system.create_env(me, "Business")
        c.call("POST", "/api/accounts/move", {"to": biz, "accounts": [card]}, env=1)
        self.assertEqual(found(f"?q=warranty"), [])
        moved = c.call("GET", "/api/attachments?q=warranty", env=biz)["files"]
        self.assertEqual([(f["name"], f["account_name"], f["date"]) for f in moved], [("tv.pdf", "Costco Visa", "2026-03-14")])
        # A viewer can look but not add.
        c.call("POST", "/api/users", {"username": "vic", "password": "vic-pass-12"})
        self.system.set_member(1, "vic", "viewer")
        v = Client(base)
        v.call("POST", "/api/login", {"username": "vic", "password": "vic-pass-12"})
        self.assertEqual(len(v.call("GET", f"/api/transactions/{back}/attachments", env=1)), 1)
        self.assertEqual(v.status("POST", f"/api/transactions/{back}/attachments", {"name": "a.pdf", "data": base64.b64encode(b"%PDF-1").decode()}, env=1), 403)

    def test_home_and_budget_across_environments(self):
        app, base = self._serve()
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        me = c.call("GET", "/api/me")["user"]["id"]
        home = self.system.create_env(me, "Household")
        p, h = self.system.store(1), self.system.store(home)
        groc = lambda st: next(x["id"] for x in st.categories() if x["full_name"] == "Groceries")
        mine = p.save_account({"name": "My Checking", "type": "Checking", "opening_balance": "100"})
        joint = h.save_account({"name": "Joint Checking", "type": "Checking", "opening_balance": "1000"})
        today = dt.date.today().isoformat()
        p.save_transaction({"account_id": mine, "date": today, "amount": "-30", "payee": "Shop", "category_id": groc(p)})
        h.save_transaction({"account_id": joint, "date": today, "amount": "-70", "payee": "Market", "category_id": groc(h)})
        p.set_budget([{"category_id": groc(p), "amount": "200", "in_budget": True}])
        h.set_budget([{"category_id": groc(h), "amount": "500", "in_budget": True}])
        s = c.call("GET", "/api/summary?scope=all", env=1)
        self.assertEqual(sorted((a["name"], a["env_name"]) for a in s["accounts"]),
                         [("Joint Checking", "Household"), ("My Checking", "Personal")])
        self.assertEqual(s["net_worth"], 10000 - 3000 + 100000 - 7000)
        self.assertEqual({t["payee"] for t in s["recent"]}, {"Shop", "Market"})
        self.assertEqual(s["spending"][0]["total"], 10000)
        b = c.call("GET", f"/api/budget?scope=all&month={today[:7]}", env=1)
        g = next(r for r in b["rows"] if r["name"] == "Groceries")
        self.assertEqual((g["budget"], g["actual"], b["combined"]), (70000, 10000, True))
        self.assertEqual(sorted(g["envs"]), ["Household", "Personal"])
        # Choosing which environments: Personal + Household, leaving Business out.
        biz = self.system.create_env(me, "Business")
        bs = self.system.store(biz)
        bacct = bs.save_account({"name": "Business Checking", "type": "Checking", "opening_balance": "5000"})
        bs.save_transaction({"account_id": bacct, "date": today, "amount": "-900", "payee": "Supplies", "category_id": groc(bs)})
        every = c.call("GET", "/api/summary?scope=all", env=1)
        self.assertEqual(len(every["accounts"]), 3)
        two = c.call("GET", f"/api/summary?scope=all&envs=1,{home}", env=1)
        self.assertEqual(sorted(a["name"] for a in two["accounts"]), ["Joint Checking", "My Checking"])
        self.assertEqual(two["net_worth"], 10000 - 3000 + 100000 - 7000)
        sp = c.call("GET", f"/api/reports/spending?kind=expense&from={today}&to={today}&scope=all&envs=1,{home}", env=1)
        self.assertEqual(sp[0]["total"], 10000)
        # The one in view is always included; environments you don't belong to never are.
        only = c.call("GET", f"/api/summary?scope=all&envs={biz}", env=home)
        self.assertEqual(sorted(a["name"] for a in only["accounts"]), ["Business Checking", "Joint Checking"])
        self.assertEqual(len(c.call("GET", "/api/summary?scope=all&envs=999", env=1)["accounts"]), 1)

    def test_forgot_password_and_recovery(self):
        app, base = self._serve()
        sent = []
        app._mail_later = lambda to, title, body: sent.append((to, title, body))
        c = Client(base)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        # No mail server: no link, and the page knows not to offer it.
        self.assertFalse(c.call("GET", "/api/meta")["password_reset"])
        self.assertEqual(c.status("POST", "/api/password/forgot", {"username": "alex"}), 400)
        app.notifier.mail_server = lambda: {"host": "smtp.example.com"}
        self.assertTrue(c.call("GET", "/api/meta")["password_reset"])
        # No email on the sign-in: the same answer, nothing sent; same for a made-up name.
        anon = Client(base)
        r1 = anon.call("POST", "/api/password/forgot", {"username": "alex"})
        r2 = anon.call("POST", "/api/password/forgot", {"username": "nobody"})
        self.assertEqual(r1, r2)
        self.assertEqual(sent, [])
        self.assertEqual(c.status("PUT", "/api/me", {"email": "not-an-email"}), 400)
        c.call("PUT", "/api/me", {"email": "alex@example.com"})
        self.assertEqual(c.call("GET", "/api/me")["user"]["email"], "alex@example.com")
        anon.call("POST", "/api/password/forgot", {"username": "ALEX"})
        self.assertEqual(sent[0][0], "alex@example.com")
        token = re.search(r"#/reset/(\S+)", sent[0][2]).group(1)
        self.assertEqual(anon.call("GET", "/api/password/reset?token=" + token)["username"], "alex")
        self.assertEqual(anon.status("POST", "/api/password/reset", {"token": token, "password": "short"}), 400)
        anon.call("POST", "/api/password/reset", {"token": token, "password": "new-horse-battery"})
        self.assertIn("was changed", sent[-1][1])
        # The link works once; the old sign-in is signed out; the new password works.
        self.assertEqual(anon.status("POST", "/api/password/reset", {"token": token, "password": "another-one-9"}), 400)
        self.assertEqual(c.status("GET", "/api/me"), 401)
        self.assertEqual(anon.status("POST", "/api/login", {"username": "alex", "password": "correct-horse"}), 401)
        anon.call("POST", "/api/login", {"username": "alex", "password": "new-horse-battery"})
        # Too many requests from one place are refused.
        codes = [Client(base).status("POST", "/api/password/forgot", {"username": "x"}) for _ in range(6)]
        self.assertIn(429, codes)
        # The link points at a known address, never at a Host header someone sent.
        app.urls = ["http://tower:8080/"]
        app.ctx.host = "evil.example"
        self.assertEqual(app._link_base(), "http://tower:8080/")
        # The recovery command (no email needed): on the computer itself.
        import main
        env = dict(os.environ, MONEYTHISTLE_NEW_PASSWORD="from-the-console-1")
        args = type("A", (), {"data": self.dir, "list_users": False, "reset_password": "Alex"})()
        old = os.environ.get("MONEYTHISTLE_NEW_PASSWORD")
        os.environ["MONEYTHISTLE_NEW_PASSWORD"] = env["MONEYTHISTLE_NEW_PASSWORD"]
        try:
            self.assertEqual(main.recover(args), 0)
        finally:
            if old is None:
                os.environ.pop("MONEYTHISTLE_NEW_PASSWORD", None)
            else:
                os.environ["MONEYTHISTLE_NEW_PASSWORD"] = old
        Client(base).call("POST", "/api/login", {"username": "alex", "password": "from-the-console-1"})
        args.reset_password = "nobody"
        self.assertEqual(main.recover(args), 1)

    def test_http_api(self):
        app, base = self._serve()
        c = Client(base)
        self.assertTrue(c.call("GET", "/api/meta")["needs_setup"])
        self.assertEqual(c.status("GET", "/api/summary", env=1), 401)
        c.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        me = c.call("GET", "/api/me")
        self.assertTrue(me["user"]["is_admin"])
        self.assertEqual(me["envs"][0]["role"], "owner")
        aid = c.call("POST", "/api/accounts", {"name": "Chk", "type": "Checking", "opening_balance": "10"}, env=1)["id"]
        c.call("POST", "/api/transactions", {"account_id": aid, "amount": "-2.5", "payee": "Cafe"}, env=1)
        self.assertEqual(c.call("GET", "/api/summary", env=1)["net_worth"], 750)
        with urllib.request.urlopen(base + "/") as r:
            self.assertIn(b"MoneyThistle", r.read())
        self.assertIn(b"Cafe", c.raw("/api/export.csv?env=1"))
        # Changes need the app's own header (other websites can't send it).
        self.assertEqual(c.status("POST", "/api/accounts", {"name": "X"}, env=1, header=False), 403)
        self.assertEqual(c.status("POST", "/api/setup", {"username": "eve", "password": "12345678"}), 403)

    def test_import_transfers(self):
        chk = self.store.save_account({"name": "Checking", "type": "Checking", "opening_balance": "500"})
        sav = self.store.save_account({"name": "Savings", "type": "Savings"})
        q = fileio.parse_qif("!Type:Bank\nD3/1/26\nT-100\nPMove\nL[Savings]\n^\n")
        fileio.import_rows(self.store, chk, q)
        self.assertEqual(self.store.account(sav)["balance"], 10000)
        self.assertEqual(self.store.account(chk)["balance"], 40000)
        # The savings side of the same transfer, imported later, isn't added twice.
        q2 = fileio.parse_qif("!Type:Bank\nD3/1/26\nT100\nPMove\nL[Checking]\n^\n")
        self.assertEqual(fileio.import_rows(self.store, sav, q2)["skipped"], 1)
        self.assertEqual(self.store.transactions(account_id=sav)[0]["category_label"], "Transfer from Checking")

    def test_loan(self):
        from moneyapp import loans
        chk = self.store.save_account({"name": "Checking", "type": "Checking", "opening_balance": "5000"})
        cats = {c["full_name"]: c["id"] for c in self.store.categories()}
        # Textbook check: 200,000 at 6% for 360 monthly payments = 1,199.10
        self.assertEqual(loans.calc_payment(20000000, 6.0, 12, 360), 119910)
        first = (dt.date.today().replace(day=1) + dt.timedelta(days=40)).replace(day=1)  # starts next month
        lid = loans.save(self.store, {"name": "Mortgage", "original_amount": "200000", "apr": "6",
                                      "payments_per_year": 12, "num_payments": 360,
                                      "first_payment": first.isoformat(), "escrow": "300",
                                      "interest_category_id": cats["Loan : Mortgage Interest"],
                                      "pay_from_account_id": chk})
        info = loans.get(self.store, lid)
        self.assertEqual(info["owed"], 20000000)
        self.assertEqual(info["next"]["interest"], 100000)       # 200,000 x 0.5%
        self.assertEqual(info["next"]["principal"], 19910)
        self.assertEqual(info["next"]["total"], 119910 + 30000)
        self.assertEqual(info["payments_left"], 360)
        bill = next(b for b in self.store.bills() if b["kind"] == "loan")
        self.assertEqual(bill["amount"], 149910)
        self.store.enter_bill(bill["id"])
        self.assertEqual(self.store.account(lid)["balance"], -(20000000 - 19910))
        self.assertEqual(self.store.account(chk)["balance"], 500000 - 149910)
        lines = self.store.transactions(account_id=chk)
        self.assertEqual(len({t["group_id"] for t in lines if t["group_id"]}), 1)
        self.assertEqual(sorted(t["amount"] for t in lines), [-100000, -30000, -19910])
        info = loans.get(self.store, lid)
        self.assertEqual(info["interest_paid"], 100000)
        self.assertEqual(info["payments_left"], 359)
        self.assertEqual(self.store.bills()[0]["next_date"] > first.isoformat(), True)
        # Deleting the payment removes all its lines, including the loan side.
        self.store.delete_group(lines[0]["group_id"])
        self.assertEqual(self.store.account(lid)["balance"], -20000000)
        # A loan that started years ago: balance owed now comes from the schedule.
        p = loans.preview(self.store, {"original_amount": "200000", "apr": "6", "payments_per_year": 12,
                                       "num_payments": 360, "first_payment": "2016-01-01"})
        self.assertTrue(100 < p["payments_made"] < 360)
        self.assertTrue(0 < p["balance_now"] < 20000000)

    def test_budget_by_scheduled_items(self):
        # For people who don't sort every purchase: paychecks in; bills, loan and card
        # payments out; transfers to savings aside; card purchases not counted.
        st = self.store
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "5000"})
        sav = st.save_account({"name": "Savings", "type": "Savings"})
        card = st.save_account({"name": "Visa", "type": "Credit Card"})
        groc = next(c["id"] for c in st.categories() if c["full_name"] == "Groceries")
        pay = st.save_bill({"kind": "deposit", "payee": "Payroll", "account_id": chk, "amount": "2000",
                            "frequency": "Every other week", "next_date": "2030-03-06"})
        st.save_bill({"kind": "bill", "payee": "Power", "account_id": chk, "amount": "120",
                      "frequency": "Monthly", "next_date": "2030-03-20"})
        st.save_bill({"kind": "transfer", "payee": "Visa payment", "account_id": chk, "to_account_id": card,
                      "amount": "500", "frequency": "Monthly", "next_date": "2030-03-15"})
        st.save_bill({"kind": "transfer", "payee": "Save", "account_id": chk, "to_account_id": sav,
                      "amount": "200", "frequency": "Monthly", "next_date": "2030-03-10"})
        st.enter_bill(pay, {"amount": "2100"})                              # Mar 6 paycheck
        st.save_transaction({"account_id": card, "amount": "-75", "date": "2030-03-08", "category_id": groc})
        lines = st.schedule_lines("2030-03")
        by = {r["payee"]: r for r in lines}
        self.assertEqual((by["Payroll"]["side"], by["Payroll"]["actual"], by["Payroll"]["expected"]), ("in", 210000, 410000))
        self.assertEqual((by["Visa payment"]["side"], by["Visa payment"]["expected"]), ("out", 50000))
        self.assertEqual((by["Power"]["side"], by["Save"]["side"]), ("out", "move"))
        b = Store.schedule_budget("2030-03", lines)
        self.assertEqual((b["income_budget"], b["income_actual"], b["expense_budget"], b["moved_budget"]),
                         (410000, 210000, 62000, 20000))                  # the 75 on the card isn't counted
        # Typed into the register instead of entered from the schedule: still counts,
        # and for the date the schedule still shows as overdue (not twice).
        st.save_bill({"kind": "bill", "payee": "Water", "account_id": chk, "amount": "40",
                      "frequency": "Monthly", "next_date": "2020-05-20"})
        st.save_transaction({"account_id": chk, "amount": "-43", "date": "2020-05-21", "payee": "water"})
        w = next(r for r in st.schedule_lines("2020-05") if r["payee"] == "Water")
        self.assertEqual((w["actual"], w["entered"], w["to_come"], w["expected"]), (4300, 1, 0, 4300))

    def test_budget_counts_loan_payments(self):
        # A mortgage payment is spending in the budget: the whole payment (principal,
        # interest and the escrow the lender keeps), once, and the next one expected.
        from moneyapp import loans
        chk = self.store.save_account({"name": "Checking", "type": "Checking", "opening_balance": "5000"})
        cats = {c["full_name"]: c["id"] for c in self.store.categories()}
        lid = loans.save(self.store, {"name": "Mortgage", "original_amount": "200000", "apr": "6",
                                      "payments_per_year": 12, "num_payments": 360,
                                      "first_payment": "2030-03-01", "escrow": "300",
                                      "interest_category_id": cats["Loan : Mortgage Interest"],
                                      "pay_from_account_id": chk})
        self.store.set_budget([{"category_id": cats["Loan : Mortgage Interest"], "amount": "0", "in_budget": True}])
        before = self.store.budget("2030-03")
        line = next(r for r in before["rows"] if r.get("loan"))
        self.assertEqual((line["name"], line["actual"], line["budget"]), ("Loan payment: Mortgage", 0, 149910))
        bill = next(b for b in self.store.bills() if b["kind"] == "loan")
        self.store.enter_bill(bill["id"])                       # paid on Mar 1
        b = self.store.budget("2030-03")
        line = next(r for r in b["rows"] if r.get("loan"))
        self.assertEqual((line["actual"], line["budget"]), (149910, 149910))
        interest = next(r for r in b["rows"] if r["category_id"] in (cats["Loan : Mortgage Interest"], cats["Loan"]))
        self.assertEqual(interest["actual"], 0)                  # counted once, in the loan line
        self.assertEqual(b["expense_actual"] - before["expense_actual"], 149910)
        april = next(r for r in self.store.budget("2030-04")["rows"] if r.get("loan"))
        self.assertEqual((april["actual"], april["budget"]), (0, 149910))
        # Recorded with a later month's date: named for the earlier month...
        ahead = self.store.entered_ahead("2030-02")
        self.assertEqual([(r["payee"], r["date"], r["amount"]) for r in ahead], [("Mortgage", "2030-03-01", 149910)])
        # ...and moved back a month, the schedule moves with it: March is due again.
        gid = ahead[0]["group_id"]
        self.assertEqual(self.store.set_group_date(gid, "2030-02-01"), {"date": "2030-02-01", "next_date": "2030-03-01"})
        self.assertEqual(self.store.account(lid)["balance"], -(20000000 - 19910))   # loan side moved, not lost
        feb = next(r for r in self.store.schedule_lines("2030-02") if r["kind"] == "loan")
        mar = next(r for r in self.store.schedule_lines("2030-03") if r["kind"] == "loan")
        self.assertEqual((feb["actual"], mar["actual"], mar["expected"]), (149910, 0, 149910))
        self.assertEqual(self.store.entered_ahead("2030-02"), [])

    def test_varying_bill_average_and_forecast(self):
        a = self.store.save_account({"name": "Chk", "type": "Checking", "opening_balance": "1000"})
        start = dt.date.today()
        bid = self.store.save_bill({"kind": "bill", "payee": "Power", "account_id": a, "amount": "125",
                                    "frequency": "Monthly", "next_date": start.isoformat(),
                                    "amount_mode": "average", "average_count": 3})
        self.assertEqual(self.store.bills()[0]["amount"], 12500)        # estimate first
        for paid in ("100", "140", "90", "200"):
            self.store.enter_bill(bid, {"amount": paid})
        # Average of the last 3 recorded: (140 + 90 + 200) / 3 = 143.33
        self.assertEqual(self.store.bills()[0]["amount"], 14333)
        self.assertEqual(self.store.bills()[0]["estimate"], 12500)
        # Entering without an amount uses the average.
        self.store.enter_bill(bid)
        self.assertEqual(self.store.transactions(account_id=a)[0]["amount"], -14333)
        # Fixed bills still need an amount; varying ones may start empty.
        with self.assertRaises(ApiError):
            self.store.save_bill({"kind": "bill", "account_id": a, "amount": "", "frequency": "Monthly"})
        self.store.save_bill({"kind": "bill", "payee": "Water", "account_id": a, "amount": "",
                              "frequency": "Monthly", "amount_mode": "average"})
        # Forecast: today's balance minus the expected bills.
        f = self.store.forecast(200)
        acc = f["accounts"][0]
        bal = self.store.account(a)["balance"]
        due = [e for e in f["events"] if e["payee"] == "Power"]
        self.assertTrue(due)
        self.assertEqual(acc["end"], bal + sum(e["amount"] for e in f["events"] if e["account_id"] == a))
        self.assertEqual(len(acc["series"]), 201)
        # After that 5th payment the last 3 are 90, 200, 143.33: average 144.44.
        self.assertTrue(any(e["estimated"] and e["amount"] == -14444 for e in due))

    def test_ui_settings_per_person(self):
        app, base = self._serve()
        a = Client(base)
        a.call("POST", "/api/setup", {"username": "alex", "password": "correct-horse"})
        a.call("POST", "/api/users", {"username": "jo", "password": "another-pass"})
        j = Client(base)
        j.call("POST", "/api/login", {"username": "jo", "password": "another-pass"})
        s = a.call("PUT", "/api/settings", {"theme": "dark", "accent": "#1F8A8A", "date_style": "eu", "due_days": "30"})
        self.assertEqual((s["theme"], s["accent"], s["date_style"], s["due_days"]), ("dark", "#1f8a8a", "eu", 30))
        self.assertEqual(j.call("GET", "/api/settings")["theme"], "light")   # each person has their own look
        for bad in ({"theme": "pink"}, {"accent": "red"}, {"due_days": 0}, {"date_style": "x"}):
            self.assertEqual(a.status("PUT", "/api/settings", bad), 400)
        # Home page cards: each person's own, checked and kept whole.
        h = a.call("GET", "/api/settings")["home"]
        self.assertEqual([c["id"] for c in h["cards"]], ["accounts", "due", "recent", "spending", "budget", "forecast"])
        cards = [{"id": "forecast", "show": True, "col": 1}, {"id": "budget", "show": False, "col": 3},
                 {"id": "nonsense", "show": True, "col": 2}, {"id": "forecast", "show": False, "col": 2}]
        s = a.call("PUT", "/api/settings", {"home": {"cards": cards, "forecast_view": "chart", "forecast_days": 60,
                                                     "recent_count": 15, "hide_zero": True}})["home"]
        self.assertEqual(s["cards"][:2], [{"id": "forecast", "show": True, "col": 1}, {"id": "budget", "show": False, "col": 3}])
        self.assertEqual(len(s["cards"]), 6)   # unknown and repeated cards dropped, missing ones added back
        self.assertEqual((s["forecast_view"], s["forecast_days"], s["recent_count"], s["hide_zero"], s["show_networth"]),
                         ("chart", 60, 15, True, True))
        self.assertEqual(a.call("PUT", "/api/settings", {"theme": "light"})["home"]["forecast_view"], "chart")  # other saves keep it
        self.assertEqual(j.call("GET", "/api/settings")["home"]["forecast_view"], "table")
        for bad in ({"forecast_view": "pie"}, {"forecast_days": 45}, {"recent_count": 100}, {"recent_count": "x"}):
            self.assertEqual(a.status("PUT", "/api/settings", {"home": bad}), 400)
        self.assertEqual(a.call("PUT", "/api/settings", {"home": None})["home"]["forecast_view"], "table")
        # Desktop: let other devices on the network open it (admins; after a restart).
        n = a.call("GET", "/api/admin/network")
        self.assertEqual((n["listen_lan"], n["listening_on_network"], n["restart_needed"]), (False, False, False))
        n = a.call("PUT", "/api/admin/network", {"listen_lan": True})
        self.assertEqual((n["listen_lan"], n["restart_needed"]), (True, True))
        with open(os.path.join(self.dir, "network.json"), encoding="utf-8") as f:
            self.assertTrue(json.load(f)["listen_lan"])
        self.assertEqual(j.status("PUT", "/api/admin/network", {"listen_lan": False}), 403)
        # Your own address (e.g. from Nginx Proxy Manager): shown first, the network choice kept.
        n = a.call("PUT", "/api/admin/network", {"custom_urls": "ledger.example.casa"})
        self.assertEqual((n["custom_urls"], n["listen_lan"]), (["https://ledger.example.casa/"], True))
        self.assertEqual(a.call("GET", "/api/meta")["addresses"][0], "https://ledger.example.casa/")
        for bad in ("javascript:alert(1)", "https://bad_host!/", "<script>"):
            self.assertEqual(a.status("PUT", "/api/admin/network", {"custom_urls": bad}), 400)
        # Budget style: each person's own; the budget follows it.
        self.assertEqual(a.call("GET", "/api/settings")["budget_mode"], "categories")
        a.call("PUT", "/api/settings", {"budget_mode": "schedule"})
        self.assertEqual(a.call("GET", "/api/budget", env=1)["mode"], "schedule")
        self.assertEqual(a.call("GET", "/api/summary", env=1)["budget"]["mode"], "schedule")
        self.assertNotIn("mode", a.call("GET", "/api/budget?mode=categories", env=1))
        self.assertEqual(j.call("GET", "/api/settings")["budget_mode"], "categories")
        self.assertEqual(a.status("PUT", "/api/settings", {"budget_mode": "loose"}), 400)

    def test_restart_permission(self):
        from moneyapp import version
        app, base = self._serve()
        calls = []
        app.request_restart = lambda: calls.append(1)
        admin, user = Client(base), Client(base)
        admin.call("POST", "/api/setup", {"username": "boss", "password": "pw-boss-123"})
        admin.call("POST", "/api/users", {"username": "kim", "password": "pw-kim-1234"})
        user.call("POST", "/api/login", {"username": "kim", "password": "pw-kim-1234"})
        app.build_id = version.build_id()                 # up to date
        self.assertFalse(user.call("GET", "/api/version")["can_restart"])
        self.assertEqual(user.status("POST", "/api/admin/restart"), 403)
        self.assertEqual(admin.status("POST", "/api/admin/restart"), 200)
        app.build_id = "older-build"                      # an update is waiting
        self.assertTrue(user.call("GET", "/api/version")["can_restart"])
        self.assertEqual(user.status("POST", "/api/admin/restart"), 200)
        import time
        for _ in range(50):   # the restart is triggered just after the reply is sent
            if len(calls) == 2:
                break
            time.sleep(0.02)
        self.assertEqual(len(calls), 2)
        self.assertEqual(Client(base).status("POST", "/api/admin/restart"), 401)   # not signed in
        self.assertTrue(admin.call("GET", "/api/meta")["ui_build"])

    def test_shared_transfers_and_loans(self):
        app, base = self._serve()
        me, wife = Client(base), Client(base)
        me.call("POST", "/api/setup", {"username": "me", "password": "pw-me-123"})
        me.call("POST", "/api/users", {"username": "wife", "password": "pw-wife-123"})
        wife.call("POST", "/api/login", {"username": "wife", "password": "pw-wife-123"})
        hers = wife.call("POST", "/api/envs", {"name": "Personal"})["id"]
        chk = me.call("POST", "/api/accounts", {"name": "Checking", "type": "Checking", "opening_balance": "5000"}, env=1)["id"]
        sav = me.call("POST", "/api/accounts", {"name": "Savings", "type": "Savings"}, env=1)["id"]
        mort = me.call("POST", "/api/loans", {"name": "Mortgage", "original_amount": "200000", "apr": "6",
                                              "payments_per_year": 12, "num_payments": 360,
                                              "first_payment": (dt.date.today() + dt.timedelta(days=3)).isoformat(),
                                              "pay_from_account_id": chk}, env=1)["id"]
        today = dt.date.today().isoformat()
        me.call("POST", "/api/bills", {"kind": "transfer", "payee": "To savings", "account_id": chk, "to_account_id": sav,
                                       "amount": "200", "frequency": "Every other week", "next_date": today}, env=1)
        sids = {}
        for a in (chk, sav, mort):
            s = me.call("POST", "/api/shares", {"env_id": 1, "account_id": a, "to_user": "wife", "access": "edit",
                                                "include_bills": True})["id"]
            wife.call("POST", f"/api/shares/{s}/approve", {"env_id": hers})
            sids[a] = s

        def via(acct, method, path, body=None):
            h = {"X-HomeLedger": "1", "X-HomeLedger-Env": "1", "X-HomeLedger-Share": str(sids[acct]),
                 "Content-Type": "application/json"}
            req = urllib.request.Request(base + path, method=method, headers=h,
                                         data=json.dumps(body).encode() if body is not None else None)
            try:
                with wife.opener.open(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, None
        kinds = sorted(b["kind"] for b in via(chk, "GET", "/api/bills")[1]["bills"])
        self.assertEqual(kinds, ["loan", "transfer"])                      # both now visible
        self.assertEqual([b["kind"] for b in via(sav, "GET", "/api/bills")[1]["bills"]], ["transfer"])
        self.assertTrue(all(b["share_editable"] for b in via(chk, "GET", "/api/bills")[1]["bills"]))
        up = wife.call("GET", "/api/shares/bills?days=10", env=hers)
        self.assertEqual(sum(1 for u in up if u["payee"] == "To savings" and u["date"] == today), 1)   # once
        # She records the transfer: both accounts move.
        tr = next(b for b in via(chk, "GET", "/api/bills")[1]["bills"] if b["kind"] == "transfer")
        self.assertEqual(via(chk, "POST", f"/api/bills/{tr['id']}/enter", {})[0], 200)
        accts = {a["id"]: a["balance"] for a in me.call("GET", "/api/accounts", env=1)}
        self.assertEqual((accts[chk], accts[sav]), (480000, 20000))
        # She can read the loan to record its payment.
        self.assertEqual(via(chk, "GET", f"/api/loans/{mort}")[0], 200)
        # The mortgage paid from the shared checking is planned spending in both budgets.
        due_month = (dt.date.today() + dt.timedelta(days=3)).strftime("%Y-%m")
        mine = [r for r in me.call("GET", f"/api/budget?month={due_month}", env=1)["rows"] if r.get("loan")]
        theirs = [r for r in wife.call("GET", f"/api/budget?month={due_month}", env=hers)["rows"] if r.get("loan")]
        self.assertEqual([(r["name"], r["budget"]) for r in mine], [("Loan payment: Mortgage", 119910)])
        self.assertEqual([(r["name"], r["budget"]) for r in theirs], [("Loan payment: Mortgage (from Checking, shared)", 119910)])
        # With savings shared view-only, the transfer becomes view-only for her.
        me.call("PUT", f"/api/shares/{sids[sav]}", {"access": "view"})
        self.assertFalse(next(b for b in via(chk, "GET", "/api/bills")[1]["bills"] if b["kind"] == "transfer")["share_editable"])
        self.assertEqual(via(chk, "POST", f"/api/bills/{tr['id']}/skip", {})[0], 403)

    def test_transfer_between_shared_and_own_account(self):
        app, base = self._serve()
        me, wife = Client(base), Client(base)
        me.call("POST", "/api/setup", {"username": "me", "password": "pw-me-123", "display_name": "Me"})
        me.call("POST", "/api/users", {"username": "wife", "password": "pw-wife-123"})
        wife.call("POST", "/api/login", {"username": "wife", "password": "pw-wife-123"})
        hers = wife.call("POST", "/api/envs", {"name": "Personal"})["id"]
        joint = me.call("POST", "/api/accounts", {"name": "Joint Checking", "type": "Checking", "opening_balance": "3000"}, env=1)["id"]
        mine = wife.call("POST", "/api/accounts", {"name": "Her Checking", "type": "Checking"}, env=hers)["id"]
        sid = me.call("POST", "/api/shares", {"env_id": 1, "account_id": joint, "to_user": "wife", "access": "edit",
                                              "include_bills": True})["id"]
        wife.call("POST", f"/api/shares/{sid}/approve", {"env_id": hers})
        # One-off, from her own register: Her Checking <- Joint Checking (no separate approval needed).
        wife.call("POST", "/api/transactions", {"account_id": mine, "amount": "100", "payee": "Allowance",
                                                "share_xfer": sid}, env=hers)
        bal = lambda c, e: {a["name"]: a["balance"] for a in c.call("GET", "/api/accounts", env=e)}
        self.assertEqual(bal(me, 1)["Joint Checking"], 290000)
        self.assertEqual(bal(wife, hers)["Her Checking"], 10000)
        # Recurring, scheduled from her side and kept with the shared account.
        h = {"X-HomeLedger": "1", "X-HomeLedger-Env": "1", "X-HomeLedger-Share": str(sid), "Content-Type": "application/json"}
        req = urllib.request.Request(base + "/api/bills", method="POST", headers=h, data=json.dumps({
            "kind": "transfer", "payee": "Weekly money", "account_id": joint, "x_account_id": mine, "x_dir": "out",
            "amount": "50", "frequency": "Weekly", "next_date": dt.date.today().isoformat()}).encode())
        with wife.opener.open(req) as r:
            bid = json.loads(r.read())["id"]
        mybill = next(b for b in me.call("GET", "/api/bills", env=1)["bills"] if b["id"] == bid)
        # I see it too; both environments are called "Personal", so hers is labelled with her name.
        self.assertEqual(mybill["to_account_name"], "Her Checking (Personal · wife)")
        # Her forecast counts it for her own account as well.
        fc = wife.call("GET", "/api/forecast?days=10", env=hers)
        her_row = next(a for a in fc["accounts"] if a["id"] == mine)
        self.assertGreater(her_row["end"], her_row["now"])
        # I record it from my side; both registers move.
        me.call("POST", f"/api/bills/{bid}/enter", {}, env=1)
        self.assertEqual(bal(me, 1)["Joint Checking"], 285000)
        self.assertEqual(bal(wife, hers)["Her Checking"], 15000)
        # The automatic connection shows, and ends with the share (schedule stops too).
        links = me.call("GET", "/api/links")
        self.assertIn("shared account", links[0]["note"])
        me.call("POST", f"/api/shares/{sid}/end")
        self.assertEqual(me.call("GET", "/api/links")[0]["status"], "ended")
        self.assertFalse(any(b["id"] == bid for b in me.call("GET", "/api/bills", env=1)["bills"]))
        # A view-only share can't be used for transfers.
        sid2 = me.call("POST", "/api/shares", {"env_id": 1, "account_id": joint, "to_user": "wife", "access": "view"})["id"]
        wife.call("POST", f"/api/shares/{sid2}/approve", {"env_id": hers})
        self.assertEqual(wife.status("POST", "/api/transactions", {"account_id": mine, "amount": "5", "share_xfer": sid2},
                                     env=hers), 403)

    def test_shared_account(self):
        app, base = self._serve()
        me, wife, other = Client(base), Client(base), Client(base)
        me.call("POST", "/api/setup", {"username": "me", "password": "pw-me-123"})
        for u in ("wife", "other"):
            me.call("POST", "/api/users", {"username": u, "password": f"pw-{u}-123"})
        wife.call("POST", "/api/login", {"username": "wife", "password": "pw-wife-123"})
        other.call("POST", "/api/login", {"username": "other", "password": "pw-other-123"})
        chk = me.call("POST", "/api/accounts", {"name": "Personal Checking", "type": "Checking",
                                                "opening_balance": "1000"}, env=1)["id"]
        sav = me.call("POST", "/api/accounts", {"name": "My Savings", "type": "Savings"}, env=1)["id"]
        hers = wife.call("POST", "/api/envs", {"name": "Wife Personal"})["id"]
        # Share checking into her environment, entering allowed; she approves.
        # Offered to a person (not an environment); she picks where it appears.
        self.assertIn("wife", [p["username"] for p in wife.call("GET", "/api/people")])
        sid = me.call("POST", "/api/shares", {"env_id": 1, "account_id": chk, "to_user": "wife", "access": "edit"})["id"]
        self.assertEqual(wife.call("GET", "/api/shares/incoming", env=hers), [])           # waits for approval
        self.assertEqual(wife.call("GET", "/api/me")["approvals_waiting"], 1)
        self.assertEqual(other.call("GET", "/api/me")["approvals_waiting"], 0)               # not offered to them
        self.assertEqual(other.status("POST", f"/api/shares/{sid}/approve", {"env_id": hers}), 403)
        self.assertEqual(wife.status("POST", f"/api/shares/{sid}/approve", {"env_id": 1}), 403)  # not her environment
        wife.call("POST", f"/api/shares/{sid}/approve", {"env_id": hers})
        inc = wife.call("GET", "/api/shares/incoming", env=hers)
        self.assertEqual((inc[0]["name"], inc[0]["balance"], inc[0]["can_edit"]), ("Personal Checking", 100000, True))
        self.assertEqual(wife.call("GET", "/api/summary", env=hers)["net_worth"], 100000)   # counts in her totals

        def shared(client, method, path, body=None):
            h = {"X-HomeLedger": "1", "X-HomeLedger-Env": "1", "X-HomeLedger-Share": str(sid),
                 "Content-Type": "application/json"}
            req = urllib.request.Request(base + path, method=method, headers=h,
                                         data=json.dumps(body).encode() if body is not None else None)
            try:
                with client.opener.open(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, None
        # She opens it: only that account, not my savings, not my other screens.
        st, accts = shared(wife, "GET", "/api/accounts")
        self.assertEqual([a["name"] for a in accts], ["Personal Checking"])
        self.assertEqual(shared(wife, "GET", "/api/summary")[0], 403)
        self.assertEqual(shared(wife, "GET", f"/api/transactions?account={sav}")[1], [])  # forced to the shared one
        # She enters a purchase; it's in the one register.
        st, r = shared(wife, "POST", "/api/transactions", {"account_id": chk, "amount": "-40", "payee": "Pharmacy"})
        self.assertEqual(st, 200)
        self.assertEqual(next(a for a in me.call("GET", "/api/accounts", env=1) if a["id"] == chk)["balance"], 96000)
        # Her reports include the shared account (forecast, spending, net worth).
        fc = wife.call("GET", "/api/forecast?days=30", env=hers)
        self.assertIn("Personal Checking (shared by me)", [a["name"] for a in fc["accounts"]])
        # Every scheduled item points at a line on her chart (shared ones as "s<id>").
        ids = {str(a["id"]) for a in fc["accounts"]}
        for e in fc["events"]:
            self.assertIn(str(e["account_id"]), ids)
            if e.get("to_account_id") is not None:
                self.assertIn(str(e["to_account_id"]), ids)
        groceries = me.call("GET", "/api/categories", env=1)
        cat = next(c["id"] for c in groceries if c["full_name"] == "Groceries")
        me.call("POST", "/api/transactions", {"account_id": chk, "amount": "-60", "payee": "Market", "category_id": cat}, env=1)
        sp = wife.call("GET", "/api/reports/spending?from=2000-01-01&to=2100-01-01", env=hers)
        self.assertEqual(next(r for r in sp if r["name"] == "Groceries")["total"], 6000)
        self.assertEqual(wife.call("GET", "/api/reports/networth?months=1", env=hers)[0]["net_worth"], 90000)
        # Her budget counts the shared account too: a paycheck there is income for her,
        # under her own category of the same name.
        pay_cat = next(c["id"] for c in groceries if c["full_name"] == "Wages & Salary : Net Pay")
        pay = me.call("POST", "/api/transactions", {"account_id": chk, "amount": "2000", "payee": "Payroll",
                                                    "category_id": pay_cat}, env=1)["id"]
        her_cats = wife.call("GET", "/api/categories", env=hers)
        her_wages = next(c["id"] for c in her_cats if c["full_name"] == "Wages & Salary")
        her_groc = next(c["id"] for c in her_cats if c["full_name"] == "Groceries")
        wife.call("PUT", "/api/budget", {"items": [{"category_id": her_wages, "amount": "0", "in_budget": True},
                                                   {"category_id": her_groc, "amount": "0", "in_budget": False}]}, env=hers)
        bud = wife.call("GET", "/api/budget", env=hers)
        self.assertTrue(bud["includes_shared"])
        self.assertEqual(bud["income_actual"], 200000)
        self.assertEqual(next(r for r in bud["rows"] if r["category_id"] == her_wages)["shared"], 200000)
        # Groceries isn't in her budget: shown apart, with her category to add it.
        self.assertIn({"category_id": her_groc, "name": "Groceries", "kind": "expense", "actual": 6000}, bud["shared_outside"])
        self.assertEqual(wife.call("GET", "/api/summary", env=hers)["budget"]["income_actual"], 200000)
        # His own budget isn't changed by sharing.
        self.assertFalse(me.call("GET", "/api/budget", env=1)["includes_shared"])
        me.call("DELETE", f"/api/transactions/{pay}", env=1)
        me.call("DELETE", f"/api/transactions/{me.call('GET', '/api/transactions?account=%d' % chk, env=1)[0]['id']}", env=1)
        self.assertEqual(shared(wife, "POST", "/api/transactions", {"account_id": sav, "amount": "-1"})[0], 403)
        self.assertEqual(shared(wife, "POST", "/api/transactions", {"account_id": chk, "amount": "-1",
                                                                   "transfer_account_id": sav})[0], 403)
        # Bills of the shared account: hidden until "share related bills & deposits" is on.
        power = me.call("POST", "/api/bills", {"kind": "bill", "payee": "Power Co", "account_id": chk, "amount": "80",
                                               "frequency": "Monthly", "next_date": dt.date.today().isoformat()}, env=1)["id"]
        me.call("POST", "/api/bills", {"kind": "bill", "payee": "My savings bill", "account_id": sav, "amount": "5",
                                       "frequency": "Monthly", "next_date": dt.date.today().isoformat()}, env=1)
        self.assertEqual(wife.call("GET", "/api/shares/bills", env=hers), [])
        self.assertEqual(shared(wife, "POST", f"/api/bills/{power}/enter", {})[0], 403)
        me.call("PUT", f"/api/shares/{sid}", {"include_bills": True})
        sb = wife.call("GET", "/api/shares/bills", env=hers)
        self.assertEqual([b["payee"] for b in sb if b["first"]], ["Power Co"])          # not the savings bill
        self.assertTrue(wife.call("GET", "/api/summary", env=hers)["shared_upcoming"])
        self.assertEqual(shared(wife, "POST", f"/api/bills/{power}/enter", {})[0], 200)
        self.assertEqual(next(a for a in me.call("GET", "/api/accounts", env=1) if a["id"] == chk)["balance"], 88000)
        other_bill = next(b for b in me.call("GET", "/api/bills", env=1)["bills"] if b["payee"] == "My savings bill")["id"]
        self.assertEqual(shared(wife, "POST", f"/api/bills/{other_bill}/enter", {})[0], 403)
        # Through the share she sees only that account's bills...
        self.assertEqual([b["payee"] for b in shared(wife, "GET", "/api/bills")[1]["bills"]], ["Power Co"])
        # ...and a bill she adds for it shows up on my side too.
        st, r = shared(wife, "POST", "/api/bills", {"kind": "bill", "payee": "Daycare", "account_id": chk,
                                                     "amount": "300", "frequency": "Monthly"})
        self.assertEqual(st, 200)
        self.assertIn("Daycare", [b["payee"] for b in me.call("GET", "/api/bills", env=1)["bills"]])
        self.assertEqual(shared(wife, "POST", "/api/bills", {"kind": "bill", "payee": "X", "account_id": sav,
                                                              "amount": "1", "frequency": "Monthly"})[0], 403)
        self.assertEqual(shared(wife, "DELETE", f"/api/bills/{other_bill}")[0], 403)
        self.assertEqual(shared(wife, "DELETE", f"/api/bills/{r['id']}")[0], 200)
        # View-only: she can still look but not enter.
        me.call("PUT", f"/api/shares/{sid}", {"access": "view"})
        self.assertEqual(shared(wife, "POST", f"/api/bills/{power}/skip", {})[0], 403)
        self.assertEqual(shared(wife, "GET", "/api/transactions")[0], 200)
        self.assertEqual(shared(wife, "POST", "/api/transactions", {"account_id": chk, "amount": "-1"})[0], 403)
        # Someone outside her environment can't use the share.
        self.assertEqual(shared(other, "GET", "/api/accounts")[0], 403)
        # The account can't be deleted while shared; ending the share removes it from her list.
        self.assertEqual(me.status("DELETE", f"/api/accounts/{chk}", env=1), 400)
        wife.call("POST", f"/api/shares/{sid}/end")
        self.assertEqual(wife.call("GET", "/api/shares/incoming", env=hers), [])
        self.assertEqual(shared(wife, "GET", "/api/accounts")[0], 403)

    def test_environments_and_access(self):
        app, base = self._serve()
        me, wife, inlaw = Client(base), Client(base), Client(base)
        me.call("POST", "/api/setup", {"username": "me", "password": "pw-me-123"})
        for u in ("wife", "inlaw"):
            me.call("POST", "/api/users", {"username": u, "password": f"pw-{u}-123"})
        wife.call("POST", "/api/login", {"username": "wife", "password": "pw-wife-123"})
        inlaw.call("POST", "/api/login", {"username": "inlaw", "password": "pw-inlaw-123"})
        self.assertEqual(wife.status("POST", "/api/login", {"username": "wife", "password": "nope-nope"}), 401)
        # Personal (env 1) shared with my wife as editor.
        me.call("PUT", "/api/envs/1/members", {"username": "wife", "role": "editor"})
        chk = me.call("POST", "/api/accounts", {"name": "Personal Checking", "type": "Checking",
                                                "opening_balance": "1000"}, env=1)["id"]
        self.assertEqual(len(wife.call("GET", "/api/accounts", env=1)), 1)
        self.assertEqual(inlaw.status("GET", "/api/accounts", env=1), 403)         # not a member
        # My wife's business: I can't see it.
        biz = wife.call("POST", "/api/envs", {"name": "Business"})["id"]
        bchk = wife.call("POST", "/api/accounts", {"name": "Business Checking", "type": "Checking"}, env=biz)["id"]
        self.assertEqual(me.status("GET", "/api/accounts", env=biz), 403)
        self.assertNotIn(biz, [e["id"] for e in me.call("GET", "/api/me")["envs"]])
        # A viewer can look but not change.
        wife.call("PUT", f"/api/envs/{biz}/members", {"username": "inlaw", "role": "viewer"})
        self.assertEqual(inlaw.status("GET", "/api/accounts", env=biz), 200)
        self.assertEqual(inlaw.status("POST", "/api/accounts", {"name": "X", "type": "Cash"}, env=biz), 403)
        # Only owners manage members; editors can't.
        self.assertEqual(wife.status("PUT", "/api/envs/1/members", {"username": "inlaw", "role": "viewer"}), 403)
        # Connection Personal Checking -> Business: I ask, she approves (picks her account).
        lid = me.call("POST", "/api/links", {"env_id": 1, "account_id": chk, "other_env_id": biz})["id"]
        self.assertEqual(me.call("GET", "/api/links/usable?account=%d" % chk, env=1), [])  # not until approved
        self.assertEqual(me.status("POST", f"/api/links/{lid}/approve", {"account_id": bchk}), 403)  # not my side
        self.assertEqual(wife.call("GET", "/api/me")["approvals_waiting"], 1)
        wife.call("POST", f"/api/links/{lid}/approve", {"account_id": bchk})
        usable = me.call("GET", "/api/links/usable?account=%d" % chk, env=1)
        self.assertEqual(usable[0]["account_name"], "Business Checking")
        # Transfer 250 to the business: both registers get their side.
        tid = me.call("POST", "/api/transactions", {"account_id": chk, "amount": "-250", "payee": "Capital",
                                                    "xlink_id": lid}, env=1)["id"]
        self.assertEqual(me.call("GET", "/api/accounts", env=1)[0]["balance"], 75000)
        b = wife.call("GET", "/api/transactions?account=%d" % bchk, env=biz)
        self.assertEqual(b[0]["amount"], 25000)
        self.assertEqual(b[0]["category_label"], "Transfer from Personal Checking (Personal)")
        # Changing my side changes hers; deleting removes both.
        me.call("PUT", f"/api/transactions/{tid}", {"account_id": chk, "amount": "-300", "xlink_id": lid}, env=1)
        self.assertEqual(wife.call("GET", "/api/transactions?account=%d" % bchk, env=biz)[0]["amount"], 30000)
        me.call("DELETE", f"/api/transactions/{tid}", env=1)
        self.assertEqual(wife.call("GET", "/api/transactions?account=%d" % bchk, env=biz), [])
        # Either owner can end it; then no more transfers through it.
        wife.call("POST", f"/api/links/{lid}/end")
        self.assertEqual(me.call("GET", "/api/links/usable?account=%d" % chk, env=1), [])
        self.assertEqual(me.status("POST", "/api/transactions", {"account_id": chk, "amount": "-5",
                                                                 "xlink_id": lid}, env=1), 400)
        # People management is for administrators.
        self.assertEqual(wife.status("POST", "/api/users", {"username": "x1", "password": "12345678"}), 403)
        # The backup holds every environment.
        r = self.bm.run("manual")
        self.assertTrue(r[0]["ok"], r)


class TaxReportTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.system = System(self.dir)
        self.st = self.system.store(1)

    def tearDown(self):
        self.system.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cat(self, full):
        return next(c["id"] for c in self.st.categories() if c["full_name"] == full)

    def test_tax_report_hsa_and_single_purpose_card(self):
        st = self.st
        health = self.cat("Healthcare")
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_balance": "5000", "opening_date": "2026-01-01"})
        fid = st.save_account({"name": "Fidelity HSA", "type": "Investment", "opening_date": "2026-01-01",
                               "details": {"hsa": True, "hsa_source": "personal"}})
        emp = st.save_account({"name": "Work HSA", "type": "Savings", "opening_date": "2026-01-01",
                               "details": {"hsa": True, "hsa_source": "employer"}})
        card = st.save_account({"name": "HSA card", "type": "Credit Card", "opening_date": "2026-01-01",
                                "details": {"purpose_category_id": health, "statement_day": 9}})
        self.assertEqual(st.account(fid)["details"]["hsa_source"], "personal")
        self.assertEqual(st.account(card)["details"]["purpose_category_id"], health)
        # A liability can't be an HSA; a card's purpose must be a real category.
        self.assertNotIn("hsa", st.account(st.save_account({"name": "L", "type": "Loan", "details": {"hsa": True}}))["details"])
        with self.assertRaises(ApiError):
            st.save_account({"name": "X", "type": "Credit Card", "details": {"purpose_category_id": 99999}})

        st.save_transaction({"account_id": chk, "date": "2026-03-01", "amount": "-3000", "transfer_account_id": fid})
        late = st.save_transaction({"account_id": chk, "date": "2027-02-10", "amount": "-1000", "transfer_account_id": fid})
        late_hsa = st.q1("SELECT transfer_id FROM transactions WHERE id=?", (late,))["transfer_id"]
        st.save_transaction({"account_id": emp, "date": "2026-01-15", "amount": "1400", "payee": "Employer"})
        st.save_transaction({"account_id": fid, "date": "2026-06-30", "amount": "5",
                             "category_id": self.cat("Investment Income : Interest")})
        # The card's statement and charges go to its purpose category without asking.
        st.enter_statement(card, "2026-05-09", "200")
        charge = st.save_transaction({"account_id": card, "date": "2026-05-12", "amount": "-50", "payee": "Pharmacy"})
        self.assertEqual(st.q1("SELECT category_id FROM transactions WHERE id=?", (charge,))["category_id"], health)
        st.save_transaction({"account_id": fid, "date": "2026-05-20", "amount": "-200", "transfer_account_id": card})

        r = st.tax_report(2026)
        hc = next(g for g in r["expense"] if g["name"] == "Healthcare")
        self.assertEqual(hc["total"], 25000)
        self.assertEqual(next(g for g in r["income"] if g["name"] == "Investment Income : Interest")["total"], 500)
        h = {a["name"]: a for a in r["hsa"]}
        self.assertEqual(h["Fidelity HSA"]["contributed"], 300000)
        self.assertEqual(h["Fidelity HSA"]["earnings"], 500)
        self.assertEqual(h["Fidelity HSA"]["withdrawn"], 20000)
        self.assertEqual([i["id"] for i in h["Fidelity HSA"]["next_year"]], [late_hsa])
        self.assertEqual(h["Fidelity HSA"]["cards"], [{"name": "HSA card", "paid": 20000, "charged": 25000}])
        self.assertEqual(h["Work HSA"]["contributed"], 140000)
        self.assertEqual(h["Work HSA"]["source"], "employer")
        self.assertFalse(h["Work HSA"]["contributions"][0]["may_move"])   # employer money: the W-2 year
        # The early-2027 contribution counts for 2026 once marked; not for 2027 then.
        self.assertEqual(st.set_tax_year(late_hsa, 2026), 2026)
        self.assertEqual({a["name"]: a for a in st.tax_report(2026)["hsa"]}["Fidelity HSA"]["contributed"], 400000)
        self.assertEqual({a["name"]: a for a in st.tax_report(2027)["hsa"]}["Fidelity HSA"]["contributed"], 0)
        with self.assertRaises(ApiError):
            st.set_tax_year(late_hsa, 2025)
        with self.assertRaises(ApiError):   # the checking side isn't money into an HSA
            st.set_tax_year(late, 2026)
        # One limit for all HSAs together.
        st.set_hsa_limit(2026, "4400")
        self.assertEqual(st.hsa_limit(2026), 440000)
        st.set_hsa_limit(2026, "")
        self.assertIsNone(st.hsa_limit(2026))


class PaystubTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.system = System(self.dir)
        self.st = self.system.store(1)

    def tearDown(self):
        self.system.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cat(self, full):
        return next(c["id"] for c in self.st.categories() if c["full_name"] == full)

    def test_paystub(self):
        from moneyapp import paystubs
        st = self.st
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_date": "2026-01-01"})
        k401 = st.save_account({"name": "401k", "type": "Retirement", "opening_date": "2026-01-01"})
        hsa = st.save_account({"name": "HSA", "type": "Investment", "opening_date": "2026-01-01",
                               "details": {"hsa": True, "hsa_source": "personal"}})
        lines = [
            {"side": "earn", "label": "Gross pay", "amount": "3000", "category_id": self.cat("Wages & Salary : Gross Pay")},
            {"side": "deduct", "label": "Federal income tax", "amount": "300", "category_id": self.cat("Taxes : Federal Income Tax")},
            {"side": "deduct", "label": "Social Security", "amount": "186", "category_id": self.cat("Taxes : Social Security Tax")},
            {"side": "deduct", "label": "Medicare", "amount": "43.50", "category_id": self.cat("Taxes : Medicare Tax")},
            {"side": "deduct", "label": "401(k)", "amount": "150", "account_id": k401},
            {"side": "deduct", "label": "HSA", "amount": "100", "account_id": hsa},
            {"side": "deduct", "label": "Dental", "amount": "0", "category_id": self.cat("Healthcare : Dental")},
        ]
        # Each refusal names its field.
        with self.assertRaises(ApiError) as cm:
            paystubs.save(st, {"account_id": chk, "date": "2026-11-06", "employer": "", "lines": lines})
        self.assertEqual(cm.exception.field, "employer")
        with self.assertRaises(ApiError):
            paystubs.save(st, {"account_id": chk, "date": "2026-11-06", "employer": "Acme",
                               "lines": [{"side": "deduct", "label": "Tax", "amount": "5", "account_id": chk}]})
        # A scheduled paycheck at the take-home amount.
        bill = st.save_bill({"kind": "deposit", "payee": "Acme", "account_id": chk, "amount": "2220.50",
                             "category_id": self.cat("Wages & Salary : Net Pay"), "frequency": "Every other week",
                             "next_date": "2026-11-06"})
        r = paystubs.save(st, {"account_id": chk, "date": "2026-11-06", "employer": "Acme", "lines": lines, "bill_id": bill})
        self.assertEqual((r["gross"], r["net"]), (300000, 222050))
        self.assertEqual(len(r["ids"]), 6)   # the 0 line is left out
        self.assertEqual(st.account(chk)["balance"], 222050)
        self.assertEqual(st.account(k401)["balance"], 15000)
        self.assertEqual(st.account(hsa)["balance"], 10000)
        self.assertEqual(st.q1("SELECT next_date FROM bills WHERE id=?", (bill,))["next_date"], "2026-11-20")
        tx = st.q(st.TX_SELECT + "WHERE t.account_id=?", (chk,))
        self.assertTrue(all(t["paystub"] for t in tx))
        # The budget counts it as take-home pay, once.
        b = st.budget("2026-11")
        rows = {r["name"]: r for r in b["rows"]} if "rows" in b else {}
        actual = st._actuals("2026-11-01", "2026-11-30")
        for cid, v in st._paystub_shift("2026-11-01", "2026-11-30").items():
            actual[cid] = actual.get(cid, 0) + v
        self.assertEqual(actual.get(self.cat("Wages & Salary : Net Pay")), 222050)
        self.assertFalse(actual.get(self.cat("Wages & Salary : Gross Pay")))
        self.assertFalse(actual.get(self.cat("Taxes : Federal Income Tax")))
        sched = {ln["payee"]: ln for ln in st.schedule_lines("2026-11")}
        self.assertEqual(sched["Acme"]["actual"], 222050)
        self.assertEqual(sched["Acme"]["entered"], 1)
        # Entering the next paycheck from the schedule copies the paystub.
        tid = st.enter_bill(bill)
        g2 = st.q1("SELECT group_id FROM transactions WHERE id=?", (tid,))["group_id"]
        self.assertTrue(st.q1("SELECT 1 FROM paystubs WHERE group_id=?", (g2,)))
        self.assertEqual(st.account(chk)["balance"], 2 * 222050)
        sched = {ln["payee"]: ln for ln in st.schedule_lines("2026-11")}
        self.assertEqual((sched["Acme"]["actual"], sched["Acme"]["entered"]), (444100, 2))
        # Editing one: the schedule's record follows.
        edited = [dict(ln) for ln in lines]
        edited[1]["amount"] = "310"
        paystubs.save(st, {"account_id": chk, "date": "2026-11-20", "employer": "Acme", "lines": edited}, g2)
        self.assertEqual(st.account(chk)["balance"], 222050 + 221050)
        sched = {ln["payee"]: ln for ln in st.schedule_lines("2026-11")}
        self.assertEqual(sched["Acme"]["actual"], 222050 + 221050)
        # The year: gross vs net and where it went; payroll HSA money is pre-tax.
        rep = st.tax_report(2026)
        pay = rep["pay"][0]
        self.assertEqual((pay["employer"], pay["paystubs"], pay["gross"], pay["net"]), ("Acme", 2, 600000, 443100))
        fed = next(d for d in pay["deductions"] if d["label"] == "Federal income tax")
        self.assertEqual(fed["total"], 61000)
        self.assertTrue(next(d for d in pay["deductions"] if d["label"] == "401(k)")["transfer"])
        h = rep["hsa"][0]
        self.assertEqual((h["contributed"], h["pretax"], h["after_tax"]), (20000, 20000, 0))
        self.assertEqual(next(g for g in rep["income"] if g["name"] == "Wages & Salary : Gross Pay")["total"], 600000)
        # Template and delete.
        self.assertEqual(paystubs.template(st, employer="acme")["group_id"], g2)
        paystubs.delete(st, g2)
        self.assertEqual(st.account(chk)["balance"], 222050)
        self.assertEqual(st.account(k401)["balance"], 15000)
        self.assertFalse(st.q1("SELECT 1 FROM paystubs WHERE group_id=?", (g2,)))

    def test_split_deposit(self):
        """Direct deposit split between accounts: a set amount into savings, the rest here."""
        from moneyapp import paystubs
        st = self.st
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_date": "2026-01-01"})
        sav = st.save_account({"name": "Savings", "type": "Savings", "opening_date": "2026-01-01"})
        lines = [
            {"side": "earn", "label": "Gross pay", "amount": "4909.65", "category_id": self.cat("Wages & Salary : Gross Pay")},
            {"side": "deduct", "label": "Withholding Tax", "amount": "1449.51", "category_id": self.cat("Taxes : Federal Income Tax")},
            {"side": "split", "label": "", "amount": "250", "account_id": sav},
        ]
        # The part elsewhere needs its account, not this one, and can't be more than the take-home pay.
        with self.assertRaises(ApiError):
            paystubs.save(st, {"account_id": chk, "date": "2026-11-06", "employer": "Acme",
                               "lines": lines[:2] + [{"side": "split", "amount": "250", "account_id": chk}]})
        with self.assertRaises(ApiError):
            paystubs.save(st, {"account_id": chk, "date": "2026-11-06", "employer": "Acme",
                               "lines": lines[:2] + [{"side": "split", "amount": "5000", "account_id": sav}]})
        # The schedule expects what reaches checking.
        bill = st.save_bill({"kind": "deposit", "payee": "Acme", "account_id": chk, "amount": "3210.14",
                             "category_id": self.cat("Wages & Salary : Net Pay"), "frequency": "Every other week",
                             "next_date": "2026-11-06"})
        r = paystubs.save(st, {"account_id": chk, "date": "2026-11-06", "employer": "Acme", "lines": lines, "bill_id": bill})
        self.assertEqual((r["net"], r["deposit"]), (346014, 321014))
        self.assertEqual(st.account(chk)["balance"], 321014)
        self.assertEqual(st.account(sav)["balance"], 25000)
        self.assertEqual(paystubs.get(st, r["group_id"])["lines"][-1]["label"], "Direct deposit")
        # The budget counts the whole take-home pay as income; the schedule what reached checking.
        actual = st._actuals("2026-11-01", "2026-11-30")
        for cid, v in st._paystub_shift("2026-11-01", "2026-11-30").items():
            actual[cid] = actual.get(cid, 0) + v
        self.assertEqual(actual.get(self.cat("Wages & Salary : Net Pay")), 346014)
        sched = {ln["payee"]: ln for ln in st.schedule_lines("2026-11")}
        self.assertEqual(sched["Acme"]["actual"], 321014)
        # The next one from the schedule is a copy, split the same way.
        st.enter_bill(bill)
        self.assertEqual(st.account(chk)["balance"], 2 * 321014)
        self.assertEqual(st.account(sav)["balance"], 50000)
        # The year: the take-home pay went into both accounts; the split isn't a deduction.
        pay = st.tax_report(2026)["pay"][0]
        self.assertEqual(pay["net"], 2 * 346014)
        self.assertEqual(pay["accounts"], ["Checking", "Savings"])
        self.assertFalse([d for d in pay["deductions"] if d["label"] == "Direct deposit"])
        # Take-home only, into two accounts: each gets its deposit, the take-home pay is the total.
        with self.assertRaises(ApiError) as cm:
            paystubs.save_net(st, {"account_id": chk, "date": "2026-12-04", "employer": "Acme", "net": "3210.14",
                                   "splits": [{"line": 7, "account_id": chk, "amount": "250"}]})
        self.assertEqual(cm.exception.field, "line_7_to")
        before = (st.account(chk)["balance"], st.account(sav)["balance"])
        r = paystubs.save_net(st, {"account_id": chk, "date": "2026-12-04", "employer": "Acme", "net": "3210.14",
                                   "splits": [{"account_id": sav, "amount": "250"}]})
        self.assertEqual((r["net"], r["deposit"]), (346014, 321014))
        self.assertEqual((st.account(chk)["balance"], st.account(sav)["balance"]), (before[0] + 321014, before[1] + 25000))
        actual = st._actuals("2026-12-01", "2026-12-31")
        self.assertEqual(actual.get(self.cat("Wages & Salary : Net Pay")), 346014)
        # Its paystub details later, with the same split: the savings deposit isn't doubled.
        paystubs.save(st, {"account_id": chk, "date": "2026-12-04", "employer": "Acme", "lines": lines, "replace_tx": r["id"]})
        self.assertEqual((st.account(chk)["balance"], st.account(sav)["balance"]), (before[0] + 321014, before[1] + 25000))

    def test_scheduled_split(self):
        """A scheduled deposit into two accounts: each its own amount (set or average), moved and entered together."""
        from moneyapp import paystubs
        st = self.st
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_date": "2026-01-01"})
        sav = st.save_account({"name": "Savings", "type": "Savings", "opening_date": "2026-01-01"})
        net_cat = self.cat("Wages & Salary : Net Pay")
        with self.assertRaises(ApiError) as cm:
            st.save_bill({"kind": "deposit", "payee": "Acme", "account_id": chk, "amount": "3210.14", "category_id": net_cat,
                          "frequency": "Every other week", "next_date": "2026-11-06",
                          "splits": [{"account_id": chk, "amount": "250"}]})
        self.assertEqual(cm.exception.field, "split_0_account")
        bid = st.save_bill({"kind": "deposit", "payee": "Acme", "account_id": chk, "amount": "3210.14", "category_id": net_cat,
                            "frequency": "Every other week", "next_date": "2026-11-06", "paycheck": True,
                            "splits": [{"account_id": sav, "amount": "250", "amount_mode": "fixed"}]})
        main = next(b for b in st.bills() if b["id"] == bid)
        self.assertEqual((len(main["splits"]), main["split_total"]), (1, 346014))
        child = main["splits"][0]["id"]
        # The forecast counts both accounts.
        fc = {a["id"]: a for a in st.forecast(30)["accounts"]}
        self.assertTrue(fc[sav]["has_activity"])
        # Entered together (take-home only): each account gets its part; both move to the next payday.
        st.enter_bill(bid, {"take_home": True, "amount": "3210.14"})
        self.assertEqual((st.account(chk)["balance"], st.account(sav)["balance"]), (321014, 25000))
        dates = {r["id"]: r["next_date"] for r in st.q("SELECT id, next_date FROM bills")}
        self.assertEqual((dates[bid], dates[child]), ("2026-11-20", "2026-11-20"))
        # Changing the main one keeps the other's id; savings now varies (its average).
        st.save_bill({"kind": "deposit", "payee": "Acme", "account_id": chk, "amount": "3210.14", "category_id": net_cat,
                      "frequency": "Every other week", "next_date": "2026-11-20", "paycheck": True,
                      "splits": [{"id": child, "account_id": sav, "amount": "", "amount_mode": "average"}]}, bid)
        main = next(b for b in st.bills() if b["id"] == bid)
        self.assertEqual((main["splits"][0]["id"], main["splits"][0]["amount_mode"], main["splits"][0]["amount"]),
                         (child, "average", 25000))
        # An amount for this time, then the average follows it.
        st.enter_bill(bid, {"take_home": True, "amount": "3160.14", "splits": {str(child): "300"}})
        self.assertEqual(st.account(sav)["balance"], 55000)
        main = next(b for b in st.bills() if b["id"] == bid)
        self.assertEqual(main["splits"][0]["amount"], 27500)
        # A paystub for the scheduled paycheck: the savings part goes into its schedule too.
        lines = [{"side": "earn", "label": "Gross pay", "amount": "4909.65", "category_id": self.cat("Wages & Salary : Gross Pay")},
                 {"side": "deduct", "label": "Tax", "amount": "1449.51", "category_id": self.cat("Taxes : Federal Income Tax")},
                 {"side": "split", "amount": "250", "account_id": sav}]
        paystubs.save(st, {"account_id": chk, "date": "2026-12-04", "employer": "Acme", "lines": lines, "bill_id": bid})
        self.assertEqual(st.q1("SELECT COUNT(*) n FROM bill_history WHERE bill_id=?", (child,))["n"], 3)
        self.assertEqual(st.q1("SELECT next_date FROM bills WHERE id=?", (child,))["next_date"], "2026-12-18")
        # Lists people read show it once; deleting it removes both.
        self.assertTrue(any(u.get("split_of") for u in st.upcoming(60)))
        self.assertFalse(any(u.get("split_of") for u in st.summary()["upcoming"]))
        st.delete_bill(bid)
        self.assertFalse(st.q1("SELECT 1 FROM bills WHERE id=?", (child,)))

    def test_update_value(self):
        """An investment's value typed in: one Change in Value entry, kept out of spending; a monthly reminder."""
        import datetime as dt
        st = self.st
        old = (dt.date.today() - dt.timedelta(days=60)).isoformat()
        roth = st.save_account({"name": "Roth IRA", "type": "Retirement", "opening_balance": "10000", "opening_date": old})
        house = st.save_account({"name": "House", "type": "Asset", "opening_balance": "300000", "opening_date": old})
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_date": old})
        due = [x for x in st.statements_due() if x.get("kind") == "value"]
        self.assertEqual([x["name"] for x in due], ["Roth IRA"])   # assets aren't reminded unless asked
        with self.assertRaises(ApiError):
            st.update_value(chk, dt.date.today().isoformat(), "5")
        t = dt.date.today().isoformat()
        r = st.update_value(roth, t, "10,750.25")
        self.assertEqual((r["change"], st.account(roth)["balance"]), (75025, 1075025))
        cat = st.q1("SELECT category_id FROM transactions WHERE id=?", (r["id"],))["category_id"]
        self.assertEqual(st.q1("SELECT kind, name FROM categories WHERE id=?", (cat,))["kind"], "none")
        self.assertEqual(st.category_names()[cat].get("pt"), "Variação de valor")
        # Again the same day: replaced, not added.
        st.update_value(roth, t, "10500")
        self.assertEqual(st.account(roth)["balance"], 1050000)
        self.assertEqual(st.q1("SELECT COUNT(*) n FROM transactions WHERE account_id=?", (roth,))["n"], 1)
        self.assertFalse([x for x in st.statements_due() if x.get("kind") == "value"])
        # Not spending or income.
        month = dt.date.today().replace(day=1).isoformat()
        self.assertFalse(any(x.get("category_id") == cat for x in st.spending_by_category(month, t)))
        self.assertFalse(any(x.get("category_id") == cat for x in st.spending_by_category(month, t, "income")))
        # Saving the details keeps the last value; the reminder can be turned off, or on for an asset.
        acc = st.account(roth)
        st.save_account({"name": "Roth IRA", "type": "Retirement", "opening_balance": "10000", "opening_date": old,
                         "details": {"value_reminder": False}}, roth)
        self.assertEqual(st.account(roth)["details"]["last_value"]["value"], 1050000)
        st.save_account({"name": "House", "type": "Asset", "opening_balance": "300000", "opening_date": old,
                         "details": {"value_reminder": True}}, house)
        self.assertEqual([x["name"] for x in st.statements_due() if x.get("kind") == "value"], ["House"])

    def test_line_order(self):
        """Deductions keep the order they were put in (the paystub's own), also in the copy."""
        from moneyapp import paystubs
        st = self.st
        chk = st.save_account({"name": "Checking", "type": "Checking", "opening_date": "2026-01-01"})
        ded = ["Legal AT Deduction", "Dental", "Vision", "Health Care", "Accidental Death"]
        lines = [{"side": "earn", "label": "Gross pay", "amount": "4909.65", "category_id": self.cat("Wages & Salary : Gross Pay")}] + \
            [{"side": "deduct", "label": n, "amount": "5", "category_id": self.cat("Insurance : Health")} for n in ded]
        r = paystubs.save(st, {"account_id": chk, "date": "2026-11-06", "employer": "Acme", "lines": lines})
        got = [ln["label"] for ln in paystubs.get(st, r["group_id"])["lines"] if ln["side"] == "deduct"]
        self.assertEqual(got, ded)
        self.assertEqual([ln["label"] for ln in paystubs.template(st, employer="Acme")["lines"] if ln["side"] == "deduct"], ded)


class MigrateTests(unittest.TestCase):
    """Moving in from another program: one file with every account."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.system = System(self.dir)
        self.st = self.system.store(1)

    def tearDown(self):
        self.system.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    @staticmethod
    def b64(text, enc="utf-8"):
        return base64.b64encode(text.encode(enc)).decode()

    def bal(self, name):
        return next(a["balance"] for a in self.st.accounts() if a["name"] == name)

    def test_qif_moneydance(self):
        """Moneydance's "All accounts" QIF turns the account list mode on and never off: each
        account header is still followed by that account's own entries."""
        text = ("!Option:AutoSwitch\n"
                "!Account\nNMortgage\nTOth L\n^\n!Type:Oth L\nD01/01/2026\nT-200,000.00\nPOpening Balance\nL[Mortgage]\n^\n"
                "D02/01/2026\nT1,000.00\nPPayment\nL[Checking]\n^\n"
                "!Account\nNChecking\nTBank\n^\n!Type:Bank\nD01/01/2026\nT5,000.00\nPOpening Balance\nL[Checking]\n^\n"
                "D02/01/2026\nT-1,000.00\nPPayment\nL[Mortgage]\n^\nD02/03/2026\nT-45.10\nPGrocer\nLGroceries\n^\n"
                "!Account\nNSavings\nTBank\n^\n!Type:Bank\nD01/01/2026\nT2,500.00\nPOpening Balance\nL[Savings]\n^\n")
        from moneyapp import migrate
        accounts, _kinds, _skipped = migrate.parse_qif_all(text)
        self.assertEqual(sorted(accounts), ["Checking", "Mortgage", "Savings"])
        self.assertEqual(accounts["Checking"]["opening"], 500000)
        self.assertEqual(len(accounts["Checking"]["rows"]), 2)
        self.assertEqual(accounts["Savings"]["type"], "Savings")
        self.assertEqual(accounts["Mortgage"]["opening"], -20000000)

    def test_qif_investment_account(self):
        """An investment account (a Roth IRA in Moneydance) comes in, with the transfers into it,
        though its buys and dividends aren't brought in."""
        import base64
        from moneyapp import migrate
        text = ("!Option:AutoSwitch\n"
                "!Account\nNChecking\nTBank\n^\n!Type:Bank\nD01/01/2026\nT5,000.00\nPOpening Balance\nL[Checking]\n^\n"
                "D02/01/2026\nT-500.00\nPRoth contribution\nL[Roth IRA]\n^\n"
                "!Account\nNRoth IRA\nTInvst\n^\n!Type:Invst\nD02/01/2026\nNXIn\nT500.00\nL[Checking]\n$500.00\n^\n"
                "D02/02/2026\nNBuy\nYTotal Market Fund\nI100\nQ5\nT500.00\n^\n")
        accounts, _k, skipped = migrate.parse_qif_all(text)
        self.assertEqual(accounts["Roth IRA"]["type"], "Retirement")
        self.assertEqual(skipped["investment entries"], 1)   # the buy (the transfer in pairs with checking's)
        data = base64.b64encode(text.encode()).decode()
        p = migrate.preview(self.st, [{"filename": "moneydance.qif", "content": data}])
        self.assertEqual(sorted(a["name"] for a in p["accounts"]), ["Checking", "Roth IRA"])
        self.assertFalse(p.get("missing"))
        migrate.bring_in(self.st, [{"filename": "moneydance.qif", "content": data}], {})
        self.assertEqual(self.bal("Roth IRA"), 50000)
        self.assertEqual(self.bal("Checking"), 450000)

    def test_qif_hsa(self):
        """An HSA by its name comes in as Savings, marked as an HSA, also when the program kept it as
        investments; a cash management account as Checking; a mortgage as a Loan. Dividends and
        interest in investment-format entries come across as income."""
        import base64
        from moneyapp import migrate
        text = ("!Account\nNWork HSA\nTBank\n^\n!Type:Bank\nD01/01/2026\nT800.00\nPOpening Balance\nL[Work HSA]\n^\n"
                "!Account\nNFidelity HSA\nTInvst\n^\n!Type:Invst\nD01/02/2026\nNXIn\nT1,200.00\nPOpening Balance\n"
                "L[Fidelity HSA]\n^\nD01/05/2026\nNBuy\nT100.00\n^\nD01/31/2026\nNDiv\nYGovernment Money Market\nT3.12\n^\n"
                "!Account\nNFidelity Cash Management Account\nTInvst\n^\n!Type:Invst\nD01/01/2026\nNXIn\nT2,000.00\n"
                "L[Fidelity Cash Management Account]\n^\nD01/31/2026\nNIntInc\nT1.05\n^\n"
                "!Account\nNMortgage\nTOth L\n^\n!Type:Oth L\nD01/01/2026\nT-200,000.00\nPOpening Balance\nL[Mortgage]\n^\n")
        data = base64.b64encode(text.encode()).decode()
        migrate.bring_in(self.st, [{"filename": "hsa.qif", "content": data}], {})
        accs = {a["name"]: a for a in self.st.accounts()}
        self.assertEqual((accs["Work HSA"]["type"], accs["Work HSA"]["details"].get("hsa")), ("Savings", True))
        self.assertEqual((accs["Fidelity HSA"]["type"], accs["Fidelity HSA"]["details"].get("hsa")), ("Savings", True))
        self.assertEqual(self.bal("Fidelity HSA"), 120312)                  # opening + the dividend
        self.assertEqual(accs["Fidelity Cash Management Account"]["type"], "Checking")
        self.assertEqual(self.bal("Fidelity Cash Management Account"), 200105)
        self.assertEqual(accs["Mortgage"]["type"], "Loan")
        div = self.st.q1("SELECT c.name FROM transactions t JOIN categories c ON c.id=t.category_id WHERE t.amount=312")
        self.assertEqual(div["name"], "Dividends")

    def test_qif_all_accounts(self):
        from moneyapp import migrate
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "money-export.qif")
        with open(path, encoding="utf-8") as f:
            data = self.b64(f.read(), "cp1252")
        p = migrate.preview(self.st, [{"filename": "money-export.qif", "content": data}])
        acc = {a["name"]: a for a in p["accounts"]}
        self.assertEqual(p["format"], "QIF")
        self.assertEqual(set(acc), {"Main Checking", "Store Card", "Vacation Savings"})
        self.assertEqual((acc["Store Card"]["type"], acc["Vacation Savings"]["type"]), ("Credit Card", "Savings"))
        self.assertEqual(acc["Main Checking"]["opening"], 100000)
        self.assertEqual(acc["Main Checking"]["balance"], 274785)
        self.assertEqual(acc["Main Checking"]["splits"], 1)
        self.assertIn("Salary", p["new_categories"])
        self.assertIn("Home:Repairs", p["new_categories"])
        self.assertEqual(self.st.accounts(), [])   # a preview changes nothing
        out = migrate.bring_in(self.st, [{"filename": "money-export.qif", "content": data}], {})
        self.assertEqual(out["accounts"], 3)
        self.assertEqual(out["transfers"], 2)       # listed in both accounts, made once
        self.assertEqual(out["unmatched_transfers"], 0)
        self.assertEqual(self.bal("Main Checking"), 274785)
        self.assertEqual(self.bal("Store Card"), -12500)
        self.assertEqual(self.bal("Vacation Savings"), 30000)
        cats = {c["full_name"]: c for c in self.st.categories()}
        self.assertEqual(cats["Salary"]["kind"], "income")
        self.assertEqual(cats["Home : Repairs"]["kind"], "expense")
        # The split stays one entry of two parts; cleared/reconciled marks come along.
        chk = next(a["id"] for a in self.st.accounts() if a["name"] == "Main Checking")
        tx = self.st.transactions(account_id=chk, limit=100)
        grp = [t for t in tx if t["group_id"]]
        self.assertEqual(sorted(t["amount"] for t in grp), [-10000, -5000])
        self.assertEqual(next(t for t in tx if t["payee"] == "Corner Market")["status"], "C")
        # Bringing the same file into the same accounts again adds nothing.
        ids = {a["name"]: a["id"] for a in self.st.accounts()}
        again = migrate.bring_in(self.st, [{"filename": "money-export.qif", "content": data}],
                                 {k: {"to": ids[k]} for k in ids})
        self.assertEqual(again["accounts"], 0)
        self.assertEqual(self.bal("Main Checking"), 274785)
        # Leaving an account out: its transfers are kept as plain entries with a note.
        st2 = self.system.store(self.system.create_env(self.system.create_user("sam", "password-1"), "Other"))
        out = migrate.bring_in(st2, [{"filename": "money-export.qif", "content": data}], {"Vacation Savings": {"to": "skip"}})
        self.assertEqual(out["unmatched_transfers"], 1)
        self.assertEqual(len(st2.accounts()), 2)

    def test_money_one_file_per_account(self):
        """Microsoft Money exports one account per QIF file: chosen together, each account
        takes its real name from its opening balance, and transfers pair across files.
        A name that differs between files is matched by hand (aliases)."""
        from moneyapp import migrate
        chk = ("!Type:Bank\nD1/1'26\nT500.00\nPOpening Balance\nL[Joint Checking]\n^\n"
               "D2/3'26\nT-75.00\nPTo savings\nL[Rainy Day]\n^\n"
               "D2/9'26\nT-20.00\nPTo the old card\nL[Old Visa]\n^\n")
        sav = "!Type:Bank\nD1/1'26\nT1,000.00\nPOpening Balance\nL[Rainy Day]\n^\nD2/3'26\nT75.00\nPFrom checking\nL[Joint Checking]\n^\n"
        visa = "!Type:CCard\nD1/1'26\nT-40.00\nPOpening Balance\nL[Visa Card]\n^\nD2/9'26\nT20.00\nPPayment\nL[Joint Checking]\n^\n"
        files = [{"filename": "checking.qif", "content": self.b64(chk, "cp1252")},
                 {"filename": "savings.qif", "content": self.b64(sav)}, {"filename": "card.qif", "content": self.b64(visa)}]
        p = migrate.preview(self.st, files)
        self.assertEqual({a["name"] for a in p["accounts"]}, {"Joint Checking", "Rainy Day", "Visa Card"})
        self.assertEqual(p["missing_transfer_accounts"], [{"name": "Old Visa", "count": 1}])
        out = migrate.bring_in(self.st, files, {}, {"Old Visa": "Visa Card"})
        self.assertEqual((out["transfers"], out["unmatched_transfers"]), (2, 0))
        self.assertEqual(self.bal("Joint Checking"), 50000 - 7500 - 2000)
        self.assertEqual(self.bal("Rainy Day"), 107500)
        self.assertEqual(self.bal("Visa Card"), -2000)

    def test_csv_exports(self):
        from moneyapp import migrate
        ynab = ('"Account","Flag","Date","Payee","Category Group/Category","Category Group","Category","Memo","Outflow","Inflow","Cleared"\n'
                '"Checking","","01/02/2026","Corner Market","Everyday: Groceries","Everyday","Groceries","","$42.10","$0.00","Cleared"\n'
                '"Checking","","01/03/2026","Transfer : Savings","","","","","$100.00","$0.00","Cleared"\n'
                '"Savings","","01/03/2026","Transfer : Checking","","","","","$0.00","$100.00","Cleared"\n'
                '"Checking","","01/01/2026","Starting Balance","Inflow: Ready to Assign","Inflow","Ready to Assign","","$0.00","$500.00","Reconciled"\n')
        out = migrate.bring_in(self.st, [{"filename": "ynab.csv", "content": self.b64(ynab)}], {})
        self.assertEqual((out["accounts"], out["transfers"]), (2, 1))
        self.assertEqual(self.bal("Checking"), 50000 - 4210 - 10000)
        self.assertEqual(self.bal("Savings"), 10000)
        # "Everyday: Groceries" finds the Groceries category already here rather than making another.
        chk = next(a["id"] for a in self.st.accounts() if a["name"] == "Checking")
        self.assertEqual(next(t for t in self.st.transactions(account_id=chk, limit=20) if t["payee"] == "Corner Market")["category_name"], "Groceries")
        # Mint: positive amounts with debit/credit; card payments paired across accounts.
        st2 = self.system.store(self.system.create_env(self.system.create_user("sam", "password-1"), "Mint"))
        mint = ('"Date","Description","Original Description","Amount","Transaction Type","Category","Account Name","Labels","Notes"\n'
                '"1/05/2026","Visa Payment","VISA PMT","250.00","debit","Credit Card Payment","Everyday Checking","",""\n'
                '"1/06/2026","Payment Thank You","PAYMENT","250.00","credit","Credit Card Payment","Rewards Visa","",""\n'
                '"1/07/2026","Coffee","COFFEE","4.50","debit","Coffee Shops","Rewards Visa","",""\n')
        out = migrate.bring_in(st2, [{"filename": "mint.csv", "content": self.b64(mint)}], {})
        self.assertEqual(out["transfers"], 1)
        bal = {a["name"]: a for a in st2.accounts()}
        self.assertEqual(bal["Rewards Visa"]["type"], "Credit Card")
        self.assertEqual(bal["Rewards Visa"]["balance"], 25000 - 450)
        self.assertEqual(bal["Everyday Checking"]["balance"], -25000)
        # GnuCash: one row per split; opening balances from Equity; a two-way split.
        st3 = self.system.store(self.system.create_env(self.system.create_user("kim", "password-1"), "Gnu"))
        gnu = ('"Date","Transaction ID","Number","Description","Notes","Commodity/Currency","Void Reason","Action","Memo","Full Account Name","Account Name","Amount With Sym","Amount Num.","Value With Sym","Value Num.","Reconcile","Reconcile Date","Rate/Price"\n'
               '"01/01/2026","t1","","Opening","","USD","","","","Assets:Current Assets:Checking Account","Checking Account","$1,000.00","1,000.00","","1,000.00","n","",""\n'
               '"01/01/2026","t1","","Opening","","USD","","","","Equity:Opening Balances","Opening Balances","-$1,000.00","-1,000.00","","-1,000.00","n","",""\n'
               '"01/04/2026","t2","101","Grocer","","USD","","","","Assets:Current Assets:Checking Account","Checking Account","-$60.00","-60.00","","-60.00","c","",""\n'
               '"01/04/2026","t2","","Grocer","","USD","","","food","Expenses:Groceries","Groceries","$40.00","40.00","","40.00","n","",""\n'
               '"01/04/2026","t2","","Grocer","","USD","","","home","Expenses:Household","Household","$20.00","20.00","","20.00","n","",""\n'
               '"01/09/2026","t3","","Pay card","","USD","","","","Assets:Current Assets:Checking Account","Checking Account","-$30.00","-30.00","","-30.00","n","",""\n'
               '"01/09/2026","t3","","Pay card","","USD","","","","Liabilities:Credit Card","Credit Card","$30.00","30.00","","30.00","n","",""\n')
        p = migrate.preview(st3, [{"filename": "gnucash.csv", "content": self.b64(gnu)}])
        self.assertEqual(p["format"], "GnuCash")
        out = migrate.bring_in(st3, [{"filename": "gnucash.csv", "content": self.b64(gnu)}], {})
        bal = {a["name"]: a for a in st3.accounts()}
        self.assertEqual(bal["Checking Account"]["balance"], 100000 - 6000 - 3000)
        self.assertEqual(bal["Credit Card"]["balance"], 3000)
        self.assertEqual(out["transfers"], 1)
        self.assertEqual(len([t for t in st3.transactions(account_id=bal["Checking Account"]["id"], limit=50) if t["group_id"]]), 2)
        # A CSV without an Account column is pointed to the per-account import.
        with self.assertRaises(ApiError):
            migrate.preview(st3, [{"filename": "bank.csv", "content": self.b64("Date,Amount\n2026-01-01,5\n")}])


class MoveAccountsTests(unittest.TestCase):
    """Moving shared accounts from Personal to a Household environment two people own."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.system = System(self.dir)

    def tearDown(self):
        self.system.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_move_to_household(self):
        from moneyapp import moveacct
        sy = self.system
        me = sy.create_user("alex", "password-1")
        tati = sy.create_user("tati", "password-2")
        home = sy.create_env(me, "Household")
        sy.set_member(home, "tati", "owner")
        p, h = sy.store(1), sy.store(home)
        mine = p.save_account({"name": "My Checking", "type": "Checking", "opening_balance": "100", "opening_date": "2026-01-01"})
        joint = p.save_account({"name": "Joint Checking", "type": "Checking", "opening_balance": "1000", "opening_date": "2026-01-01"})
        pet = p.save_category({"name": "Pets", "kind": "expense"})
        visa = p.save_account({"name": "Joint Visa", "type": "Credit Card", "opening_date": "2026-01-01",
                               "details": {"due_day": 5, "auto_pay": True, "pay_from_account_id": joint, "pay_mode": "fixed",
                                           "pay_amount": "100", "purpose_category_id": pet}})
        p.save_transaction({"account_id": mine, "date": "2026-02-01", "amount": "-500", "transfer_account_id": joint,
                            "payee": "To joint"})
        p.save_transaction({"account_id": visa, "date": "2026-02-03", "amount": "-60", "payee": "Vet"})   # Pets, by its purpose
        p.save_transaction({"account_id": joint, "date": "2026-02-05", "amount": "-100", "transfer_account_id": visa,
                            "payee": "Visa payment"})
        p.save_bill({"kind": "transfer", "payee": "Monthly to joint", "account_id": mine, "to_account_id": joint,
                     "amount": "200", "frequency": "Monthly", "next_date": "2026-03-01"})
        sid = sy.request_share(me, 1, joint, "tati", "edit")
        sy.approve_share(tati, sid, home)
        bal = lambda st, n: next(a["balance"] for a in st.accounts() if a["name"] == n)
        before = {n: bal(p, n) for n in ("My Checking", "Joint Checking", "Joint Visa")}

        plan = moveacct.plan(sy, me, 1, home, [joint, visa])
        self.assertEqual(plan["transfers_to_staying"], [{"moving": "Joint Checking", "staying": "My Checking", "count": 1}])
        self.assertEqual(plan["shares_ending"], 1)
        with self.assertRaises(ApiError):   # only an owner of both may move
            moveacct.plan(sy, tati, 1, home, [joint])
        out = moveacct.move(sy, me, 1, home, [joint, visa])
        self.assertEqual(out["connections_made"], 1)

        # Gone from Personal, in Household, balances the same.
        self.assertEqual([a["name"] for a in p.accounts()], ["My Checking"])
        self.assertEqual({a["name"] for a in h.accounts()}, {"Joint Checking", "Joint Visa"})
        self.assertEqual(bal(p, "My Checking"), before["My Checking"])
        self.assertEqual(bal(h, "Joint Checking"), before["Joint Checking"])
        self.assertEqual(bal(h, "Joint Visa"), before["Joint Visa"])
        # The card payment between two moved accounts is still a plain transfer; the card
        # keeps its payment schedule and its purpose (the category came along).
        hj = next(a for a in h.accounts() if a["name"] == "Joint Checking")
        hv = next(a for a in h.accounts() if a["name"] == "Joint Visa")
        pay = next(t for t in h.transactions(account_id=hj["id"]) if t["payee"] == "Visa payment")
        self.assertEqual(pay["transfer_account_id"], hv["id"])
        self.assertEqual(hv["details"]["pay_from_account_id"], hj["id"])
        self.assertEqual(h.q1("SELECT * FROM bills WHERE card_account_id=?", (hv["id"],))["account_id"], hj["id"])
        self.assertEqual(next(c for c in h.categories() if c["id"] == hv["details"]["purpose_category_id"])["name"], "Pets")
        self.assertEqual(next(t for t in h.transactions(account_id=hv["id"]) if t["payee"] == "Vet")["category_name"], "Pets")
        # The transfer from my personal checking is now a transfer between environments.
        mine_tx = next(t for t in p.transactions(account_id=mine) if t["payee"] == "To joint")
        self.assertTrue(mine_tx["xlink_id"])
        self.assertIsNone(mine_tx["transfer_id"])
        other = h.q1("SELECT * FROM transactions WHERE id=?", (mine_tx["xtx_id"],))
        self.assertEqual((other["account_id"], other["amount"], other["xtx_id"]), (hj["id"], 50000, mine_tx["id"]))
        sy.decorate(1, [mine_tx])
        self.assertEqual(mine_tx["category_label"], "Transfer to Joint Checking (Household)")
        # Deleting one side of it removes the other (it's tied across environments).
        sy.detach_cross(1, mine_tx["id"])
        self.assertIsNone(h.q1("SELECT 1 FROM transactions WHERE id=?", (other["id"],)))
        # The scheduled transfer from my checking now goes across to Household.
        b = p.q1("SELECT * FROM bills WHERE payee='Monthly to joint'")
        self.assertTrue(b["x_link_id"])
        self.assertIsNone(b["to_account_id"])
        self.assertEqual(b["x_label"], "Joint Checking (Household)")
        # The share into Household ended: the account lives there now.
        self.assertEqual(sy.q1("SELECT status FROM shares WHERE id=?", (sid,))["status"], "ended")
        # Tati, an owner of Household, owns them now.
        self.assertEqual(sy.role(tati, home), "owner")

    def test_loan_moves_with_its_payer(self):
        from moneyapp import moveacct, loans
        sy = self.system
        me = sy.create_user("alex", "password-1")
        home = sy.create_env(me, "Household")
        p = sy.store(1)
        chk = p.save_account({"name": "Chk", "type": "Checking", "opening_balance": "5000"})
        lid = loans.save(p, {"name": "Car", "original_amount": "10000", "apr": "5", "payments_per_year": 12,
                             "num_payments": 36, "first_payment": "2026-02-01", "pay_from_account_id": chk})
        with self.assertRaises(ApiError):
            moveacct.plan(sy, me, 1, home, [lid])
        moveacct.move(sy, me, 1, home, [lid, chk])
        h = sy.store(home)
        self.assertEqual({a["name"] for a in h.accounts()}, {"Chk", "Car"})
        self.assertTrue(h.q1("SELECT 1 FROM loans"))


class FieldErrorTests(unittest.TestCase):
    """A refused save names the field it's about, so the screen can point at it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.system = System(self.dir)
        self.st = self.system.store(1)

    def tearDown(self):
        self.system.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def field_of(self, data):
        with self.assertRaises(ApiError) as cm:
            self.st.save_account(data)
        return cm.exception.field

    def test_fields(self):
        chk = self.st.save_account({"name": "Chk", "type": "Checking"})
        card = {"name": "Card", "type": "Credit Card"}
        self.assertEqual(self.field_of({"name": " ", "type": "Checking"}), "name")
        self.assertEqual(self.field_of({**card, "opening_balance": "abc"}), "opening_balance")
        self.assertEqual(self.field_of({**card, "details": {"auto_pay": True}}), "due_day")
        self.assertEqual(self.field_of({**card, "details": {"auto_pay": True, "due_day": 5}}), "pay_from_account_id")
        self.assertEqual(self.field_of({**card, "details": {"auto_pay": True, "due_day": 5, "pay_from_account_id": chk,
                                                            "pay_mode": "fixed"}}), "pay_amount")
        self.assertEqual(self.field_of({**card, "details": {"statement_day": 40}}), "statement_day")
        self.assertEqual(self.field_of({**card, "details": {"website": "not a site"}}), "website")


class LastDayTests(unittest.TestCase):
    """Day 31 on a card means the last day of each month."""

    def test_day_31_is_the_last_day(self):
        S = Store
        self.assertEqual(S.last_closing(31, dt.date(2026, 3, 15)), dt.date(2026, 2, 28))
        self.assertEqual(S.last_closing(31, dt.date(2028, 3, 1)), dt.date(2028, 2, 29))
        self.assertEqual(S.last_closing(31, dt.date(2026, 4, 30)), dt.date(2026, 4, 30))
        self.assertEqual(S.last_closing(30, dt.date(2026, 3, 1)), dt.date(2026, 2, 28))
        # 29 and 30 in February: its last day (28, or 29 in a leap year).
        self.assertEqual(S.last_closing(29, dt.date(2026, 3, 1)), dt.date(2026, 2, 28))
        self.assertEqual(S.last_closing(29, dt.date(2028, 3, 1)), dt.date(2028, 2, 29))
        self.assertEqual(S.last_closing(30, dt.date(2028, 3, 1)), dt.date(2028, 2, 29))
        self.assertEqual(next_occurrence(dt.date(2026, 1, 30), "Monthly", 30), dt.date(2026, 2, 28))
        self.assertEqual(next_occurrence(dt.date(2026, 2, 28), "Monthly", 30), dt.date(2026, 3, 30))
        self.assertEqual(next_occurrence(dt.date(2026, 1, 29), "Monthly", 29), dt.date(2026, 2, 28))
        self.assertEqual(next_occurrence(dt.date(2026, 2, 28), "Monthly", 29), dt.date(2026, 3, 29))
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        system = System(d)
        self.addCleanup(system.close)
        st = system.store(1)
        self.assertEqual(st._next_due(31, dt.date(2026, 4, 10)), dt.date(2026, 4, 30))
        self.assertEqual(st._next_due(31, dt.date(2026, 2, 1)), dt.date(2026, 2, 28))
        # The card's scheduled payment keeps to the last day after a short month.
        chk = st.save_account({"name": "Chk", "type": "Checking"})
        card = st.save_account({"name": "Card", "type": "Credit Card", "details": {
            "due_day": 31, "auto_pay": True, "pay_from_account_id": chk, "pay_mode": "fixed", "pay_amount": "50"}})
        bill = st.q1("SELECT * FROM bills WHERE card_account_id=?", (card,))
        self.assertEqual(bill["anchor_day"], 31)
        self.assertEqual(next_occurrence(dt.date(2026, 2, 28), "Monthly", 31), dt.date(2026, 3, 31))
        self.assertEqual(next_occurrence(dt.date(2026, 3, 31), "Monthly", 31), dt.date(2026, 4, 30))


class DataFolderTests(unittest.TestCase):
    """Where a copy started without --data keeps its money files."""

    def test_fresh_install_uses_the_person_s_app_data_folder(self):
        import main
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        prog = os.path.join(tmp, "program")
        os.makedirs(prog)
        old_file, old_cwd, old_env = main.__file__, os.getcwd(), os.environ.pop("DATA_DIR", None)
        self.addCleanup(os.chdir, old_cwd)
        self.addCleanup(setattr, main, "__file__", old_file)
        if old_env is not None:
            self.addCleanup(os.environ.__setitem__, "DATA_DIR", old_env)
        main.__file__ = os.path.join(prog, "main.py")
        os.chdir(prog)
        # Fresh: nothing beside the program, so the per-person folder.
        self.assertEqual(main.default_data_dir(), main.user_data_dir())
        self.assertIn("oney", os.path.basename(main.user_data_dir()))   # MoneyThistle / moneythistle
        # An existing copy with a data folder beside the program keeps it.
        os.makedirs(os.path.join(prog, "data"))
        open(os.path.join(prog, "data", "system.db"), "wb").close()
        self.assertEqual(os.path.normcase(main.default_data_dir()), os.path.normcase(os.path.join(prog, "data")))
        # DATA_DIR (Docker's /data) always wins.
        os.environ["DATA_DIR"] = os.path.join(tmp, "elsewhere")
        self.addCleanup(os.environ.pop, "DATA_DIR", None)
        self.assertEqual(main.default_data_dir(), os.path.join(tmp, "elsewhere"))


if __name__ == "__main__":
    unittest.main()
