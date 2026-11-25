"""A small web server: the browser screens plus a JSON API.

Every API call is made by a signed-in person (a session cookie) and, for money
data, inside one environment (the X-HomeLedger-Env header, or ?env= for links).
Viewers may read; editors and owners may change things; owners manage members and
connections; administrators manage people, backups and restarts.
"""

import base64
import datetime as dt
import hmac
import json
import mimetypes
import os
import re
import socket
import threading
import traceback
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import attachments, autostart, currencies, defaults, fileio, history, loans, migrate, moveacct, paystubs, version
from .notify import Notifier
from .demo import load_sample
from .store import ApiError, to_cents

# Raise when the screens need something new from the server; app.js checks it.
API_VERSION = 7

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
mimetypes.add_type("application/manifest+json", ".webmanifest")   # the home-screen app description
COOKIE = "hl_session"
RAW_UPLOADS = ("/api/setup/restore-upload", "/api/backup/restore-upload")   # bodies that are files


class Raw:
    """A route's answer that is a file, not JSON."""

    def __init__(self, data, ctype, headers=None):
        self.data, self.ctype, self.headers = data, ctype, headers or {}


class App:
    # detail: "simple" folds extras away, "full" shows everything. Sign-ins made before this
    # choice existed have no value and keep everything; new ones are made "simple".
    UI_DEFAULTS = {"theme": "light", "accent": "#1c4b8a", "currency": "", "date_style": "system",
                   "due_days": 14, "budget_mode": "categories", "register_order": "newest",
                   "detail": "full", "folds": {}, "lang": ""}

    def __init__(self, system, backups):
        self.system = system
        self.backups = backups
        self.build_id = ""          # set by main.py
        self.control_token = ""     # set by main.py; lets a newer start stop this copy
        self.request_stop = None
        self.request_restart = None  # set by main.py
        self.launch_args = None      # set by main.py: --data (and --port/--host if given), for shortcuts
        self.auto_user_id = None     # only for --screenshot: acts as this person
        self.in_docker = os.path.exists("/.dockerenv")
        self.listen_host = None      # set by main.py: the address it listens on now
        self.urls = None             # set by main.py: addresses to open it at (this start)
        self.find_urls = None        # set by main.py: looks them up again (the network may come later)
        self._urls_at = 0.0
        self.host_fixed = False      # set by main.py: --host / HOST given
        self.updates = None          # set by main.py: checking for (and installing) new versions
        self.ctx = threading.local()
        self.routes = []
        r = self.route
        # Notifications: a daily summary by email, Pushover, ntfy or Gotify.
        self.notifier = Notifier(system)
        self._forgot = {}            # "forgot password" requests per address (a few per 15 minutes)
        try:
            attachments.tidy(system)   # receipts of entries deleted long ago, files nothing lists
        except Exception:
            traceback.print_exc()
        if backups is not None:
            backups.notifier = self.notifier
        # Each person's own setup (administrators share one that covers everything).
        r("GET", r"/api/notify", lambda q, b: self.notifier.public(self._notify_who()), "user")
        r("PUT", r"/api/notify", lambda q, b: self.notifier.save(b, self._notify_who()), "user")
        r("POST", r"/api/notify/test", self.notify_test, "user")
        r("GET", r"/api/notify/preview", lambda q, b: {"text": self.notifier.summary(who=self._notify_who())}, "user")
        # Where it listens (desktop): this computer only, or the home network too.
        # Starting and stopping a copy on a computer: shortcuts, with sign-in, with the computer.
        r("GET", r"/api/admin/startup", lambda q, b: self.startup_info(), "admin")
        r("PUT", r"/api/admin/startup", self.save_startup, "admin")
        r("POST", r"/api/admin/shutdown", self.shutdown, "admin")
        r("GET", r"/api/admin/network", lambda q, b: self.network_info(), "admin")
        r("PUT", r"/api/admin/network", lambda q, b: self.save_network(b), "admin")
        # Signing in
        r("GET", r"/api/meta", self.meta, "public")
        # The source code of this copy (AGPL-3.0: anyone using it may have it).
        r("GET", r"/api/source.zip", lambda q, b: Raw(version.source_zip(), "application/zip", {
            "Content-Disposition": f'attachment; filename="moneythistle-{version.VERSION}-{self.build_id or "dev"}-source.zip"'}),
          "public")
        r("POST", r"/api/login", self.login, "public")
        r("POST", r"/api/setup", self.setup, "public")
        # Forgot my password: a one-time link by email (when mail is set up).
        r("POST", r"/api/password/forgot", self.forgot_password, "public")
        r("GET", r"/api/password/reset", lambda q, b: self.reset_info(q.get("token")), "public")
        r("POST", r"/api/password/reset", self.reset_password, "public")
        r("POST", r"/api/logout", self.logout, "user")
        r("GET", r"/api/me", self.me, "user")
        r("PUT", r"/api/me", self.update_me, "user")
        r("GET", r"/api/settings", lambda q, b: self.ui_settings(), "user")
        r("PUT", r"/api/settings", lambda q, b: self.save_ui_settings(b), "user")
        r("GET", r"/api/version", self.version_info, "user")
        # New versions (administrators): see updates.py
        r("GET", r"/api/updates", lambda q, b: self._updater().status(), "admin")
        r("POST", r"/api/updates/check", lambda q, b: self._updater().check(force=True), "admin")
        r("PUT", r"/api/updates/settings", lambda q, b: self._updater().save_settings(b or {}), "admin")
        r("POST", r"/api/updates/install", lambda q, b: self._updater().install(), "admin")
        # Environments, members and connections
        r("POST", r"/api/envs", lambda q, b: {"id": self.system.create_env(self.uid, b.get("name"))}, "user")
        r("PUT", r"/api/envs/(\d+)", self.rename_env, "user")
        r("DELETE", r"/api/envs/(\d+)", self.delete_env, "user")
        r("POST", r"/api/envs/(\d+)/start-fresh", self.start_fresh, "user")
        r("PUT", r"/api/envs/(\d+)/members", self.set_member, "user")
        r("DELETE", r"/api/envs/(\d+)/members/(\d+)", self.remove_member, "user")
        r("GET", r"/api/envs/(\d+)/accounts", self.env_accounts, "user")
        r("GET", r"/api/env-names", lambda q, b: self.system.all_env_names(), "user")
        r("GET", r"/api/links", lambda q, b: self.system.links_for(self.uid), "user")
        r("POST", r"/api/links", self.request_link, "user")
        r("POST", r"/api/links/(\d+)/approve", lambda q, b, i: self.system.approve_link(self.uid, int(i), b.get("account_id")), "user")
        r("POST", r"/api/links/(\d+)/decline", lambda q, b, i: self.system.decline_link(self.uid, int(i)), "user")
        r("POST", r"/api/links/(\d+)/end", lambda q, b, i: self.system.end_link(self.uid, int(i)), "user")
        # Accounts shared into another environment
        r("GET", r"/api/shares", lambda q, b: self.system.shares_for(self.uid), "user")
        r("POST", r"/api/shares", lambda q, b: {"id": self.system.request_share(
            self.uid, b.get("env_id"), b.get("account_id"), b.get("to_user"), b.get("access") or "view",
            b.get("note"), bool(b.get("include_bills")))}, "user")
        r("POST", r"/api/shares/(\d+)/approve", lambda q, b, i: self.system.approve_share(self.uid, int(i), b.get("env_id")), "user")
        r("GET", r"/api/people", lambda q, b: self.system.people(), "user")
        r("POST", r"/api/shares/(\d+)/decline", lambda q, b, i: self.system.decline_share(self.uid, int(i)), "user")
        r("POST", r"/api/shares/(\d+)/end", lambda q, b, i: self.system.end_share(self.uid, int(i)), "user")
        r("PUT", r"/api/shares/(\d+)", lambda q, b, i: self.system.set_share_access(
            self.uid, int(i), b.get("access"), b.get("include_bills")), "user")
        # People (administrators)
        r("GET", r"/api/users", lambda q, b: self.system.users(), "admin")
        r("POST", r"/api/users", self.create_user, "admin")
        r("PUT", r"/api/users/(\d+)", self.admin_update_user, "admin")
        r("DELETE", r"/api/users/(\d+)", self.delete_user, "admin")
        r("GET", r"/api/backup/settings", lambda q, b: self.backups.public_settings(), "admin")
        r("PUT", r"/api/backup/settings", lambda q, b: self.backups.update_settings(b), "admin")
        r("POST", r"/api/backup/now", lambda q, b: {"results": self.backups.run("manual")}, "admin")
        r("GET", r"/api/backup/list", lambda q, b: self.backups.list_all(), "admin")
        r("GET", r"/api/backup/log", lambda q, b: self.system.backup_log(), "admin")
        r("POST", r"/api/backup/restore", lambda q, b: self.backups.restore(b.get("destination"), b.get("name"), b.get("password")), "admin")
        # Starting over from a backup: on a new install (before anyone is set up), or by an
        # administrator from a file.
        r("POST", r"/api/setup/restore-upload", self.setup_restore_upload, "public")
        r("POST", r"/api/setup/webdav-list", self.setup_webdav_list, "public")
        r("POST", r"/api/setup/restore-webdav", self.setup_restore_webdav, "public")
        r("POST", r"/api/backup/restore-upload", lambda q, b: self._restore_upload(b), "admin")
        r("POST", r"/api/backup/delete", lambda q, b: self.backups.delete(b.get("destination"), b.get("name")), "admin")
        r("POST", r"/api/backup/verify", lambda q, b: self.backups.verify(b.get("destination"), b.get("name"), b.get("password")), "admin")
        # Money data, inside the chosen environment
        r("GET", r"/api/summary", lambda q, b: self.all_envs_summary(q, b) if q.get("scope") == "all" else self.summary(q, b))
        r("GET", r"/api/accounts", self.list_accounts, share="read")
        r("POST", r"/api/accounts", lambda q, b: {"id": self.store.save_account(b)})
        r("PUT", r"/api/accounts/(\d+)", lambda q, b, i: {"id": self.store.save_account(b, int(i))})
        r("DELETE", r"/api/accounts/(\d+)", self.delete_account)
        r("POST", r"/api/accounts/(\d+)/value", lambda q, b, i: self.store.update_value(
            int(i), b.get("date"), b.get("value")), share="write")
        r("POST", r"/api/accounts/(\d+)/reconcile", self.reconcile, share="write")
        # Change history: who changed what, and undo.
        r("GET", r"/api/history", self.history_list, "user")
        r("GET", r"/api/history/(transaction|bill)/(\d+)", lambda q, b, kind, i: history.for_object(
            self.system, self.uid, self.env_id, kind, int(i)))
        r("POST", r"/api/history/undo", lambda q, b: history.undo(self.system, self.uid, str(b.get("op") or "")), "user")
        # Moving accounts to another environment (owner of both).
        r("POST", r"/api/accounts/move/plan", lambda q, b: moveacct.plan(self.system, self.uid, self.env_id, b.get("to"),
                                                                        b.get("accounts")))
        r("POST", r"/api/accounts/move", self.move_accounts)
        r("GET", r"/api/accounts/(\d+)/statement", lambda q, b, i: {"due": self.store.statement_due(self._share_acct(int(i)))}, share="read")
        r("POST", r"/api/accounts/(\d+)/statement", lambda q, b, i: {"id": self.store.enter_statement(
            self._share_acct(int(i)), b.get("date"), b.get("balance"), b.get("category_id"))}, share="write")
        r("GET", r"/api/transactions", self.list_tx, share="read")
        r("POST", r"/api/transactions", lambda q, b: {"id": self.save_tx(b)}, share="write")
        r("PUT", r"/api/transactions/(\d+)", lambda q, b, i: {"id": self.save_tx(b, int(i))}, share="write")
        r("DELETE", r"/api/transactions/(\d+)", self.delete_tx, share="write")
        r("POST", r"/api/transactions/(\d+)/status", self.set_status, share="write")
        r("POST", r"/api/transactions/(\d+)/move", self.move_tx, share="write")
        # Receipts and other files kept with an entry.
        r("GET", r"/api/transactions/(\d+)/attachments", self.list_attachments, share="read")
        r("POST", r"/api/transactions/(\d+)/attachments", self.add_attachment, share="write")
        r("GET", r"/api/accounts/(\d+)/attachments", self.list_account_files, share="read")
        r("POST", r"/api/accounts/(\d+)/attachments", self.add_account_file, share="write")
        r("GET", r"/api/attachments", self.search_attachments, share="read")
        r("GET", r"/api/attachments/(\d+)", self.open_attachment, share="read")
        r("PUT", r"/api/attachments/(\d+)", self.update_attachment, share="write")
        r("DELETE", r"/api/attachments/(\d+)", self.delete_attachment, share="write")
        r("DELETE", r"/api/transactions/group/(\d+)", lambda q, b, g: self.store.delete_group(int(g)))
        r("PUT", r"/api/transactions/group/(\d+)", lambda q, b, g: self.store.set_group_date(int(g), b.get("date")))
        r("GET", r"/api/links/usable", lambda q, b: [] if self.share else self.system.usable_links(self.env_id, int(q.get("account", 0))), share="read")
        r("GET", r"/api/shares/incoming", lambda q, b: self.system.incoming_shares(self.uid, self.env_id))
        r("POST", r"/api/loans/preview", lambda q, b: loans.preview(self.store, b))
        # The loan calculator and a loan's "what if": arithmetic only, nothing is saved.
        # (GET, so people who may only look can use them too)
        r("GET", r"/api/loans/calculate", lambda q, b: loans.calculate(q), share="read")
        r("GET", r"/api/loans/(\d+)/what-if", lambda q, b, i: self.loan_what_if(int(i), q), share="read")
        r("POST", r"/api/loans", lambda q, b: {"id": loans.save(self.store, b)})
        r("GET", r"/api/loans/(\d+)", lambda q, b, i: self.get_loan(int(i)), share="read")
        r("PUT", r"/api/loans/(\d+)", lambda q, b, i: {"id": loans.save(self.store, b, int(i))})
        r("POST", r"/api/loans/(\d+)/pay", lambda q, b, i: self.pay_loan(int(i), b))
        r("GET", r"/api/payees", lambda q, b: self.store.payees(), share="read")
        r("GET", r"/api/categories", lambda q, b: self.store.categories(), share="read")
        # This environment's main currency and the rough rates for the others.
        r("GET", r"/api/money", lambda q, b: dict(self.store.money_settings(), codes=list(currencies.CODES)), share="read")
        r("PUT", r"/api/money", lambda q, b: dict(self.store.set_money_settings(b), codes=list(currencies.CODES)))
        r("POST", r"/api/categories", lambda q, b: {"id": self.store.save_category(b)})
        r("PUT", r"/api/categories/(\d+)", lambda q, b, i: {"id": self.store.save_category(b, int(i))})
        r("DELETE", r"/api/categories/(\d+)", lambda q, b, i: self.store.delete_category(int(i)))
        r("GET", r"/api/bills", self.list_bills, share="read")
        r("POST", r"/api/bills", lambda q, b: {"id": self.save_bill(b)}, share="bills")
        r("PUT", r"/api/bills/(\d+)", lambda q, b, i: {"id": self.save_bill(b, int(i))}, share="bills")
        r("DELETE", r"/api/bills/(\d+)", lambda q, b, i: self._shared_bill_ok(int(i)) or self.store.delete_bill(int(i)), share="bills")
        r("POST", r"/api/bills/(\d+)/enter", lambda q, b, i: {"id": self.enter_bill(int(i), b)}, share="bills")
        r("PUT", r"/api/bills/(\d+)/auto", lambda q, b, i: self._shared_bill_ok(int(i)) or
          self.store.set_bill_auto(int(i), b.get("auto"), b.get("auto_enter")), share="bills")
        r("POST", r"/api/bills/(\d+)/skip", lambda q, b, i: self._shared_bill_ok(int(i)) or self.store.skip_bill(int(i)), share="bills")
        r("GET", r"/api/shares/bills", lambda q, b: self.system.incoming_bills(self.uid, self.env_id, int(q.get("days", 31))))
        r("GET", r"/api/budget", lambda q, b: self.all_envs_budget(q.get("month"), q.get("mode")) if q.get("scope") == "all"
          else self.budget(q.get("month"), q.get("mode")))
        r("PUT", r"/api/budget", lambda q, b: self.store.set_budget(b.get("items", [])))
        # Reports for this environment, or (scope=all) for every environment you belong to.
        r("GET", r"/api/reports/spending", lambda q, b: self.all_envs_spending(
            q.get("from", "0000"), q.get("to", "9999"), q.get("kind", "expense")) if q.get("scope") == "all" else
            self.report_spending(q.get("from", "0000"), q.get("to", "9999"), q.get("kind", "expense")))
        r("GET", r"/api/reports/entries", lambda q, b: self.all_envs_entries(
            q.get("name"), q.get("kind", "expense"), q.get("from", "0000"), q.get("to", "9999")))
        r("GET", r"/api/reports/monthly", lambda q, b: self.all_envs_sum(
            lambda: self.report_monthly(int(q.get("months", 12))), ("income", "spending", "net")) if q.get("scope") == "all"
            else self.report_monthly(int(q.get("months", 12))))
        r("GET", r"/api/forecast", lambda q, b: self.all_envs_forecast(int(q.get("days", 90))) if q.get("scope") == "all"
            else self.report_forecast(int(q.get("days", 90))))
        r("GET", r"/api/reports/networth", lambda q, b: self.all_envs_sum(
            lambda: self.report_networth(int(q.get("months", 12))), ("net_worth",)) if q.get("scope") == "all"
            else self.report_networth(int(q.get("months", 12))))
        r("GET", r"/api/reports/tax", lambda q, b: self.all_envs_tax(q.get("year") or dt.date.today().year - 1)
            if q.get("scope") == "all" else self.report_tax(q.get("year") or dt.date.today().year - 1))
        r("PUT", r"/api/tax/hsa-limit", lambda q, b: {"limit": self.store.set_hsa_limit(b.get("year"), b.get("amount"))})
        r("PUT", r"/api/transactions/(\d+)/tax-year", lambda q, b, i: {"tax_year": self.store.set_tax_year(
            int(i), b.get("tax_year"))})
        # Paystubs: a paycheck's earnings, taxes and deductions.
        r("GET", r"/api/paystubs/template", lambda q, b: {"template": paystubs.template(
            self.store, q.get("employer"), q.get("account"), q.get("bill"))})
        r("GET", r"/api/paystubs/(\d+)", lambda q, b, g: paystubs.get(self.store, int(g)))
        r("POST", r"/api/paystubs", lambda q, b: paystubs.save(self.store, b))
        r("PUT", r"/api/paystubs/(\d+)", lambda q, b, g: paystubs.save(self.store, b, int(g)))
        r("DELETE", r"/api/paystubs/(\d+)", lambda q, b, g: paystubs.delete(self.store, int(g)))
        # Paychecks: take-home only for now, "complete as is", and what's missing per employer.
        r("POST", r"/api/paychecks/net", lambda q, b: paystubs.save_net(self.store, b))
        r("POST", r"/api/paychecks/complete", lambda q, b: paystubs.set_complete(
            self.store, "stub" if b.get("kind") == "stub" else "tx", b.get("id"), b.get("complete", True)))
        r("GET", r"/api/paychecks", lambda q, b: {"employers": paystubs.report(
            self.store, q.get("from") or None, q.get("to") or None)})
        r("POST", r"/api/import", self.import_file)
        # Moving in from another money program (one file with every account).
        r("POST", r"/api/migrate/preview", lambda q, b: migrate.preview(self.store, b.get("files"), b.get("aliases")))
        r("POST", r"/api/migrate", lambda q, b: migrate.bring_in(self.store, b.get("files"), b.get("choices"),
                                                                b.get("aliases")))
        r("POST", r"/api/sample", lambda q, b: {"loaded": load_sample(self.store)})

    def route(self, method, pattern, fn, scope="env", share=None):
        # share: what someone opening an account shared into their environment may do
        # here (None = nothing, "read" = look, "write" = enter transactions if allowed).
        self.routes.append((method, re.compile("^" + pattern + "$"), fn, scope, share))

    @property
    def share(self):
        """(share id, account id, may edit) when this request opens a shared account."""
        return getattr(self.ctx, "share", None)

    def _share_tx_ok(self, tid):
        """A shared-account visitor may only change plain entries of that one account."""
        if not self.share:
            return
        row = self.store.q1("SELECT * FROM transactions WHERE id=?", (tid,))
        if not row or row["account_id"] != self.share[1]:
            raise ApiError("That entry isn't in the shared account", 403)
        if row["transfer_id"] or row["xlink_id"] or row["group_id"]:
            raise ApiError("Transfers and split payments in a shared account can only be changed "
                           "in its own environment", 403)

    def _share_sets(self):
        """(accounts shared with bills into the same environment, those this person may change)."""
        if not self.share or not self.share[3]:
            return set(), set()
        return self.system.shared_bill_sets(self.uid, self.share[0])

    def _shared_bill_ok(self, bid):
        """Through a share, an item may be recorded, skipped, changed or deleted when every
        account it touches is shared into this environment with entering allowed."""
        if not self.share:
            return None
        bill = self.store.q1("SELECT * FROM bills WHERE id=?", (bid,))
        seen, edit = self._share_sets()
        if not bill or not (self.system.bill_accounts(bill) & seen):
            raise ApiError("That item isn't shared with you", 403)
        if not self.system.bill_accounts(bill) <= edit:
            raise ApiError("This item also moves money in an account that isn't shared with you for entering, "
                           "so it's changed in its own environment", 403)
        return None

    def _shared_bill_body_ok(self, b):
        """An item added or changed through a share may only involve accounts shared
        into this environment with entering allowed (and not loan payments, which come
        from a loan's own details)."""
        if not self.share:
            return None
        kind = b.get("kind") or "bill"
        involved = {int(b.get("account_id") or 0)}
        if kind == "transfer":
            involved.add(int(b.get("to_account_id") or 0))
        _, edit = self._share_sets()
        if kind not in ("bill", "deposit", "transfer") or not involved <= edit or self.share[1] not in involved:
            raise ApiError("Through a shared account you can schedule items only between accounts shared with you "
                           "for entering", 403)
        return None

    def save_bill(self, b, bid=None):
        b = dict(b)
        if bid:
            self._shared_bill_ok(bid)
            old = self.store.q1("SELECT * FROM bills WHERE id=?", (bid,))
            if old and old.get("x_link_id") and not b.get("x_account_id") and not b.get("to_account_id"):
                # A transfer with another environment keeps where it goes.
                b.update(account_id=old["account_id"], x_link_id=old["x_link_id"], x_dir=old["x_dir"],
                         x_label=old["x_label"], kind="transfer")
        if b.get("x_account_id") and (b.get("kind") or "bill") == "transfer":
            # Shared account <-> an account in the environment it's shared into.
            if not self.share:
                raise ApiError("Schedule this from the shared account's side", 400)
            if int(b.get("account_id") or 0) != self.share[1]:
                raise ApiError("Only the shared account", 403)
            if b.get("x_dir") not in ("in", "out"):
                raise ApiError("Say which way the money goes")
            lid = self.system.ensure_share_link(self.uid, self.share[0], b["x_account_id"])
            label, _, _ = self.system.share_link_label(lid, self.env_id, self.share[1])
            b.update(x_link_id=lid, x_label=label, to_account_id=None)
            _, edit = self._share_sets()
            if self.share[1] not in edit:
                raise ApiError("This shared account can be viewed but not changed", 403)
        elif not b.get("x_link_id"):
            self._shared_bill_body_ok(b)
        return self.store.save_bill(b, bid)

    def enter_bill(self, bid, b):
        self._shared_bill_ok(bid)
        return self.system.enter_scheduled(self.env_id, bid, b)

    def _auto_enter(self):
        """Record automatic items that are due before showing what's due (at most once
        a minute; the backup timer also does it in the background)."""
        try:
            done = self.system.enter_automatic(self.env_id)
            if done:
                self.notifier.note_recorded(done)
        except Exception:
            traceback.print_exc()

    def list_bills(self, q, b):
        self._auto_enter()
        out = self._list_bills(q, b)
        if isinstance(out, dict) and not self.share:
            out["statements_due"] = self.store.statements_due()
        return out

    def _list_bills(self, q, b):
        days = int(q.get("days", 31))
        bills, upcoming = self.store.bills(), self.store.upcoming(days)
        # (a deposit's other accounts are shown with it, not as items of their own)
        bills, upcoming = [x for x in bills if not x.get("split_of")], [x for x in upcoming if not x.get("split_of")]
        if self.share:
            # Items that involve the shared account (bills, deposits, transfers, loan
            # payments), and only if its bills are shared; each says if it may be changed.
            seen, edit = self._share_sets()
            acct = self.share[1]
            keep = lambda x: self.share[3] and acct in self.system.bill_accounts(x)
            bills, upcoming = [x for x in bills if keep(x)], [x for x in upcoming if keep(x)]
            for x in bills + upcoming:
                x["share_editable"] = self.system.bill_accounts(x) <= edit
                # Names of accounts on the other side, for display.
        return {"bills": bills, "upcoming": upcoming}

    def get_loan(self, i):
        if self.share:
            seen, _ = self._share_sets()
            if i not in seen:
                raise ApiError("That loan isn't shared with you", 403)
        return loans.get(self.store, i)

    def loan_what_if(self, i, b):
        if self.share:
            seen, _ = self._share_sets()
            if i not in seen:
                raise ApiError("That loan isn't shared with you", 403)
        return loans.what_if(self.store, i, b)

    def list_accounts(self, q, b):
        rows = self.store.accounts()
        if self.share:
            keep = {self.share[1]}
            if q.get("scope") == "bills":
                # Scheduling through a share may use every account shared for entering.
                keep |= self._share_sets()[1]
            rows = [a for a in rows if a["id"] in keep]
        return rows

    def _notify_who(self):
        """Administrators use the administrators' setup; everyone else their own."""
        return "admin" if self.ctx.user["is_admin"] else self.uid

    def notify_test(self, q, b):
        """Send a test message to one service (saved settings) and say how it went."""
        ch = b.get("channel")
        if ch not in ("email", "pushover", "ntfy", "gotify"):
            raise ApiError("Unknown notification service")
        who = self._notify_who()
        text = self.notifier.summary(who=who) or "Nothing needs your attention today."
        r = self.notifier.send("MoneyThistle: test message", "This is a test from MoneyThistle.\n\n" + text, [ch], who=who)
        return {"channel": ch, "result": r.get(ch, "not sent")}

    # ----- where it listens ----------------------------------------------------------
    def _network_path(self):
        return os.path.join(self.system.data_dir, "network.json")

    def _network_saved(self):
        try:
            with open(self._network_path(), encoding="utf-8") as f:
                saved = json.load(f)
            return saved if isinstance(saved, dict) else {}
        except (OSError, ValueError):
            return {}

    def network_info(self):
        saved = self._network_saved()
        lan_now = self.listen_host in ("0.0.0.0", "::") or (self.listen_host or "127.0.0.1") not in ("127.0.0.1", "::1", "localhost")
        fixed = bool(self.host_fixed or self.in_docker)
        return {"listen_lan": bool(saved.get("listen_lan")), "listening_on_network": bool(lan_now),
                "fixed": fixed, "in_docker": self.in_docker,
                "custom_urls": saved.get("custom_urls") or [],
                "restart_needed": bool(saved.get("listen_lan")) != bool(lan_now) and not fixed}

    @staticmethod
    def _clean_urls(v):
        """Your own addresses for MoneyThistle (e.g. a name a reverse proxy such as Nginx
        Proxy Manager serves): web addresses only, at most five."""
        items = v if isinstance(v, list) else re.split(r"[\s,]+", str(v or ""))
        out = []
        for u in (x.strip() for x in items):
            if not u:
                continue
            if not re.match(r"(?i)^https?://", u):
                u = "https://" + u
            if not re.fullmatch(r"(?i)https?://[a-z0-9.-]+(:\d{1,5})?(/[^\s]*)?", u):
                raise ApiError(f"\"{u}\" isn't a web address like https://ledger.example.com")
            u = u if u.endswith("/") else u + "/"
            if u not in out:
                out.append(u)
        if len(out) > 5:
            raise ApiError("Up to five addresses")
        return out

    def save_network(self, b):
        saved = self._network_saved()
        if "listen_lan" in b:
            if self.host_fixed or self.in_docker:
                raise ApiError("Where MoneyThistle listens is set when it's started (Docker or --host), not here")
            saved["listen_lan"] = bool(b.get("listen_lan"))
        if "custom_urls" in b:
            saved["custom_urls"] = self._clean_urls(b.get("custom_urls"))
        with open(self._network_path(), "w", encoding="utf-8") as f:
            json.dump(saved, f)
        return self.network_info()

    def move_tx(self, q, b, i):
        if self.share:
            row = self.store.q1("SELECT account_id FROM transactions WHERE id=?", (int(i),))
            if not row or row["account_id"] != self.share[1]:
                raise ApiError("Only the shared account", 403)
        return self.store.move_transaction(int(i), b.get("direction"))

    def _share_acct(self, aid):
        """In a shared visit, only the shared account itself."""
        if self.share and aid != self.share[1]:
            raise ApiError("Only the shared account", 403)
        return aid

    def reconcile(self, q, b, i):
        if self.share and int(i) != self.share[1]:
            raise ApiError("Only the shared account", 403)
        return self.store.reconcile(int(i), b.get("statement_balance"), b.get("statement_date"), b.get("ids"))

    def set_status(self, q, b, i):
        if self.share:
            row = self.store.q1("SELECT account_id FROM transactions WHERE id=?", (int(i),))
            if not row or row["account_id"] != self.share[1]:
                raise ApiError("That entry isn't in the shared account", 403)
        return self.store.set_status(int(i), b.get("status", ""))

    # ----- who and where (set per request) --------------------------------------
    @property
    def uid(self):
        return self.ctx.user["id"]

    @property
    def env_id(self):
        return self.ctx.env_id

    @property
    def store(self):
        return self.system.store(self.ctx.env_id)

    # ----- signing in ---------------------------------------------------------------
    def meta(self, q, b):
        return {"account_types": defaults.ACCOUNT_TYPES, "liability_types": sorted(defaults.LIABILITY_TYPES),
                "frequencies": defaults.FREQUENCIES,
                "currency": os.environ.get("CURRENCY_SYMBOL", "$"),
                # Where people can open the app (set by main.py or the Unraid install script).
                # Your own addresses (Settings) first, then the ones found at start.
                "addresses": self._addresses(),
                "custom_addresses": self._network_saved().get("custom_urls") or [],
                "port": int(os.environ.get("PUBLIC_PORT") or os.environ.get("PORT") or 8080),
                "api_version": API_VERSION, "build": self.build_id, "ui_build": version.static_id(),
                "version": version.VERSION,
                "needs_setup": not self.system.has_users(),
                # A copy on a computer (not Docker) that an administrator can shut down.
                "can_shutdown": self.request_stop is not None and not self.in_docker,
                # Setting up: offer a desktop icon (copies on Windows or Linux computers).
                "desktop_icon_offer": self.launch_args is not None and not self.in_docker
                and autostart.platform() != "mac" and not autostart.service_account(),
                "password_reset": self.notifier.mail_server() is not None}

    # ----- forgotten passwords -------------------------------------------------------
    FORGOT_MSG = ("If that user name has an email address, a link to set a new password is on its way. "
                  "It works once, for 30 minutes. Nothing arrived? Check spam, or ask an administrator.")

    def _addresses(self):
        return (self._network_saved().get("custom_urls") or []) + \
            (self._found_urls() if self.urls is not None else
             [u.strip() for u in os.environ.get("APP_URLS", "").split(",") if u.strip()])

    def _found_urls(self):
        """The addresses found now (looked up again at most every 30 seconds): started with
        the computer, MoneyThistle may be up before Wi-Fi is, when only virtual adapters
        have addresses."""
        if not self.find_urls:
            return self.urls
        now = time.time()
        if now - self._urls_at > 30:
            try:
                self.urls = self.find_urls()
            except Exception:
                pass
            self._urls_at = now
        return self.urls

    def _link_base(self):
        """Where a link in an email should point: the known address this page was opened
        at, else the first known address. The request's own Host is only trusted when it
        is one of those (so nobody can make the email point elsewhere), or this computer."""
        known = self._addresses()
        host = (self.ctx.host or "").lower()
        for u in known:
            if urllib.parse.urlparse(u).netloc.lower() == host:
                return u if u.endswith("/") else u + "/"
        if known:
            return known[0] if known[0].endswith("/") else known[0] + "/"
        if re.fullmatch(r"(localhost|127\.0\.0\.1|\[::1\])(:\d+)?", host):
            return f"http://{host}/"
        return f"http://localhost:{int(os.environ.get('PUBLIC_PORT') or os.environ.get('PORT') or 8080)}/"

    def _mail_later(self, to, title, body):
        """Send in the background: the answer comes back at once either way, so how long it
        takes says nothing about whether the person exists."""
        def go():
            try:
                self.notifier.mail_to(to, title, body)
            except Exception:
                traceback.print_exc()
        threading.Thread(target=go, daemon=True).start()

    def forgot_password(self, q, b):
        now = time.time()
        recent = [t for t in self._forgot.get(self.ctx.addr, []) if now - t < 900]
        if len(recent) >= 5:
            raise ApiError("Too many requests. Wait a few minutes.", 429)
        self._forgot[self.ctx.addr] = recent + [now]
        if self.notifier.mail_server() is None:
            raise ApiError("Email isn't set up in this MoneyThistle, so it can't send a link. "
                           "Ask an administrator to set a new password for you.")
        res = self.system.start_reset(b.get("username"))
        if res:
            u, token = res
            link = f"{self._link_base()}#/reset/{token}"
            self._mail_later(u["email"], "MoneyThistle: set a new password",
                             f"Hello {u['display_name'] or u['username']},\n\n"
                             f"Someone (hopefully you) asked to set a new password for the MoneyThistle sign-in "
                             f"\"{u['username']}\". Open this link to choose one:\n\n{link}\n\n"
                             f"It works once, for {self.system.RESET_MINUTES} minutes, from your home network or "
                             f"Tailscale like MoneyThistle itself. If you didn't ask, ignore this email: your "
                             f"password stays as it is.\n")
        return {"ok": True, "message": self.FORGOT_MSG}

    def reset_info(self, token):
        u = self.system.reset_user(token)
        if not u:
            raise ApiError("This link has expired or was already used. Ask for a new one from the sign-in page.")
        return {"username": u["username"]}

    def reset_password(self, q, b):
        u = self.system.finish_reset(b.get("token"), b.get("password"))
        self.password_changed_notice(u)
        return {"ok": True, "username": u["username"]}

    def password_changed_notice(self, u):
        """Tell the person by email that their password changed (when they have an
        address and mail is set up), so a change they didn't make doesn't go unnoticed."""
        if u and u.get("email") and self.notifier.mail_server():
            self._mail_later(u["email"], "MoneyThistle: your password was changed",
                             f"The password for the MoneyThistle sign-in \"{u['username']}\" was just changed "
                             f"and every device using it was signed out.\n\nIf that wasn't you, ask an "
                             f"administrator to set a new one right away.\n")

    def login(self, q, b):
        # "Keep me signed in on this device": 30 days. Otherwise it ends when the browser
        # closes, or after an hour without use.
        keep = bool(b.get("remember"))
        token, uid = self.system.login(b.get("username"), b.get("password"), self.ctx.addr, keep)
        self.ctx.set_cookie, self.ctx.cookie_keep = token, keep
        return {"ok": True}

    def setup(self, q, b):
        """The very first person: becomes an administrator and owner of everything."""
        if self.system.has_users():
            raise ApiError("MoneyThistle is already set up; sign in instead", 403)
        self.system.create_user(b.get("username"), b.get("password"), b.get("display_name"), True)
        if b.get("desktop_icon") and self.launch_args is not None and not self.in_docker:
            try:   # chosen while setting it up; never stops the setup
                autostart.Autostart(self.system.data_dir, self.launch_args).set_desktop(True)
            except Exception:
                traceback.print_exc()
        return self.login(q, b)

    # ----- starting over from a backup ------------------------------------------------
    def _only_before_setup(self):
        if self.system.has_users():
            raise ApiError("MoneyThistle is already set up here. An administrator restores backups on the "
                           "Backups page.", 403)

    def _restore_upload(self, b):
        blob = b.get("raw") or b""
        if not blob:
            raise ApiError("Choose a backup file")
        return self.backups.restore_blob(blob, b.get("password"), "file", b.get("filename") or "uploaded backup")

    def setup_restore_upload(self, q, b):
        self._only_before_setup()
        return self._restore_upload(b)

    def setup_webdav_list(self, q, b):
        self._only_before_setup()
        return {"backups": self.backups.webdav_preview(str(b.get("url") or ""), str(b.get("user") or ""),
                                                       str(b.get("password") or ""))}

    def setup_restore_webdav(self, q, b):
        self._only_before_setup()
        return self.backups.restore_from_webdav(str(b.get("url") or ""), str(b.get("user") or ""),
                                                str(b.get("password") or ""), str(b.get("name") or ""),
                                                b.get("backup_password") or None)

    def logout(self, q, b):
        self.system.logout(self.ctx.token)
        self.ctx.set_cookie = ""
        return {"ok": True}

    def me(self, q, b):
        u = self.ctx.user
        links = self.system.links_for(u["id"])
        envs = self.system.my_envs(u["id"])
        for e in envs:
            # (holding the made-up sample data: the screens offer Start fresh)
            try:
                e["sample_data"] = bool(self.system.store(e["id"]).get_setting("sample_data"))
            except ApiError:
                e["sample_data"] = False
        return {"user": {k: u.get(k) for k in ("id", "username", "display_name", "email", "is_admin")},
                "envs": envs,
                "approvals_waiting": sum(1 for l in links if l["can_approve"]) +
                sum(1 for s in self.system.shares_for(u["id"]) if s["can_approve"])}

    def update_me(self, q, b):
        if b.get("password"):
            full = self.system.q1("SELECT pw_hash FROM users WHERE id=?", (self.uid,))
            from .system import check_password
            if not check_password(b.get("current_password") or "", full["pw_hash"]):
                raise ApiError("Your current password isn't right")
        was = self.system.q1("SELECT remember FROM sessions WHERE token_hash=?", (self.system._th(self.ctx.token or ""),))
        self.system.update_user(self.uid, {k: b[k] for k in ("display_name", "email", "password") if k in b}, False)
        if b.get("password"):
            # Changing the password signs out everywhere; sign this browser back in, kept as it was.
            keep = bool(was["remember"]) if was else False
            token, _ = self.system.login(self.ctx.user["username"], b["password"], self.ctx.addr, keep)
            self.ctx.set_cookie, self.ctx.cookie_keep = token, keep
            self.password_changed_notice(self.system.user(self.uid))
        return {"ok": True}

    def history_list(self, q, b):
        """Recent changes in the environments this person belongs to (one, or all)."""
        mine = [e["id"] for e in self.system.my_envs(self.uid)]
        env = q.get("env") or "all"
        envs = mine if env == "all" else [int(env)] if env.isdigit() and int(env) in mine else []
        if not envs:
            raise ApiError("You don't have access to that environment", 403)
        try:
            offset = max(0, int(q.get("offset", 0)))
        except ValueError:
            offset = 0
        return history.listing(self.system, self.uid, envs, q.get("user") or None, (q.get("q") or "").strip() or None,
                               limit=50, offset=offset)

    def move_accounts(self, q, b):
        """Move accounts to another environment, after a backup of everything (a move
        touches two money files)."""
        moveacct.plan(self.system, self.uid, self.env_id, b.get("to"), b.get("accounts"))   # checks first
        if self.backups is not None and self.backups.targets(self.backups.settings()):
            results = self.backups.run("manual")
            if results and not any(r.get("ok") for r in results):
                raise ApiError("Couldn't make a backup before moving, so nothing was moved: "
                               + "; ".join(str(r.get("error") or "") for r in results))
        return moveacct.move(self.system, self.uid, self.env_id, b.get("to"), b.get("accounts"))

    def admin_update_user(self, q, b, i):
        self.system.update_user(int(i), b, True)
        if b.get("password"):
            self.password_changed_notice(self.system.user(int(i)))
        return {"ok": True}

    def create_user(self, q, b):
        email = self.system.clean_email(b.get("email"))
        uid = self.system.create_user(b.get("username"), b.get("password"), b.get("display_name"),
                                      bool(b.get("is_admin")), "full" if b.get("show_everything") else "simple")
        if email:
            self.system.update_user(uid, {"email": email}, True)
        return {"id": uid}

    def delete_user(self, q, b, i):
        if int(i) == self.uid:
            raise ApiError("You can't delete yourself")
        self.system.delete_user(int(i))

    # ----- environments -----------------------------------------------------------
    def rename_env(self, q, b, i):
        self.system.require(self.uid, int(i), "owner")
        self.system.rename_env(int(i), b.get("name"))

    def delete_env(self, q, b, i):
        self.system.require(self.uid, int(i), "owner")
        self.system.delete_env(int(i))

    def start_fresh(self, q, b, i):
        """Start an environment over (owners only). Sample data goes with a click; anything else
        needs the environment's name typed, so it's never done by accident."""
        env_id = int(i)
        self.system.require(self.uid, env_id, "owner")
        env = self.system.q1("SELECT name FROM environments WHERE id=?", (env_id,))
        st = self.system.store(env_id)
        if not st.get_setting("sample_data") and \
                (b.get("confirm") or "").strip().lower() != (env["name"] or "").strip().lower():
            raise ApiError("Type the environment's name to confirm", field="confirm")
        return self.system.reset_env(env_id)

    def set_member(self, q, b, i):
        self.system.require(self.uid, int(i), "owner")
        self.system.set_member(int(i), b.get("username"), b.get("role"))

    def remove_member(self, q, b, i, u):
        self.system.require(self.uid, int(i), "owner")
        self.system.remove_member(int(i), int(u))

    def env_accounts(self, q, b, i):
        self.system.require(self.uid, int(i), "viewer")
        return [{"id": a["id"], "name": a["name"], "type": a["type"]}
                for a in self.system.store(int(i)).accounts(include_closed=False)]

    def request_link(self, q, b):
        return {"id": self.system.request_link(self.uid, b.get("env_id"), b.get("account_id"),
                                               b.get("other_env_id"), b.get("other_account_id"), b.get("note"))}

    # ----- settings per person ---------------------------------------------------------
    def ui_settings(self):
        s = dict(self.UI_DEFAULTS)
        s.update(self.system.ui_settings(self.uid))
        if not isinstance(s.get("home"), dict):
            s["home"] = json.loads(json.dumps(self.HOME_DEFAULT))
        return s

    def save_ui_settings(self, b):
        s = self.ui_settings()
        if "theme" in b:
            if b["theme"] not in ("light", "dark", "auto"):
                raise ApiError("Theme must be light, dark or auto")
            s["theme"] = b["theme"]
        if "accent" in b:
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(b["accent"])):
                raise ApiError("Accent color must look like #1c4b8a")
            s["accent"] = b["accent"].lower()
        if "currency" in b:
            s["currency"] = str(b["currency"] or "")[:4]
        if "date_style" in b:
            if b["date_style"] not in ("system", "us", "uk", "eu", "iso"):
                raise ApiError("Unknown date style")
            s["date_style"] = b["date_style"]
        if "lang" in b:
            # Each person's language ("" = like this browser, when it's one of these).
            if b["lang"] not in ("", "en", "fr", "es", "pt"):
                raise ApiError("Unknown language")
            s["lang"] = b["lang"]
        if "due_days" in b:
            try:
                d = int(b["due_days"])
            except Exception:
                raise ApiError("Days must be a whole number")
            if not 1 <= d <= 90:
                raise ApiError("Please enter a number between 1 and 90.")
            s["due_days"] = d
        if "home" in b:
            s["home"] = self.clean_home(b["home"])
        if "register_order" in b:
            if b["register_order"] not in ("newest", "oldest"):
                raise ApiError("Register order must be newest or oldest")
            s["register_order"] = b["register_order"]
        if "budget_mode" in b:
            if b["budget_mode"] not in ("categories", "schedule"):
                raise ApiError("Budget style must be categories or schedule")
            s["budget_mode"] = b["budget_mode"]
        if "tour_done" in b:
            # The first-run tour was finished or skipped (it can be replayed from Help).
            s["tour_done"] = bool(b["tour_done"])
        if "detail" in b:
            if b["detail"] not in ("simple", "full"):
                raise ApiError("Choose simple or full")
            s["detail"] = b["detail"]
            s["folds"] = {}   # a new overall choice: every "More options" starts from it again
        if isinstance(b.get("folds"), dict):
            # Each "More options" fold someone opened or closed, remembered for them per area.
            folds = dict(s.get("folds") or {})
            for k, v in b["folds"].items():
                if re.fullmatch(r"[a-z0-9_-]{1,40}", str(k)):
                    if v is None:
                        folds.pop(k, None)
                    else:
                        folds[k] = bool(v)
            s["folds"] = dict(list(folds.items())[-100:])
        self.system.save_ui_settings(self.uid, s)
        return s

    # The Home page: which cards show, in which column and order, plus a few choices
    # inside cards. Each person keeps their own.
    HOME_CARDS = ("accounts", "due", "recent", "spending", "budget", "forecast")
    HOME_DEFAULT = {"cards": [{"id": "accounts", "show": True, "col": 1}, {"id": "due", "show": True, "col": 2},
                              {"id": "recent", "show": True, "col": 2}, {"id": "spending", "show": True, "col": 3},
                              {"id": "budget", "show": True, "col": 3}, {"id": "forecast", "show": True, "col": 3}],
                    "forecast_view": "table", "forecast_days": 30, "recent_count": 8,
                    "hide_zero": False, "show_networth": True}

    def clean_home(self, h):
        if h is None:
            return json.loads(json.dumps(self.HOME_DEFAULT))
        if not isinstance(h, dict):
            raise ApiError("Home layout must be an object")
        cur = self.ui_settings().get("home") or self.HOME_DEFAULT
        out = {k: cur.get(k, v) for k, v in self.HOME_DEFAULT.items()}
        if "cards" in h:
            cards, seen = [], set()
            for c in h["cards"] if isinstance(h["cards"], list) else []:
                cid = c.get("id") if isinstance(c, dict) else None
                if cid not in self.HOME_CARDS or cid in seen:
                    continue
                seen.add(cid)
                col = c.get("col", 1)
                cards.append({"id": cid, "show": bool(c.get("show", True)),
                              "col": col if col in (1, 2, 3) else 1})
            # A card the page doesn't list yet (added in a later version) is kept, shown.
            for d in self.HOME_DEFAULT["cards"]:
                if d["id"] not in seen:
                    cards.append(dict(d))
            out["cards"] = cards
        if "forecast_view" in h:
            if h["forecast_view"] not in ("table", "chart"):
                raise ApiError("The forecast card shows a table or a chart")
            out["forecast_view"] = h["forecast_view"]
        if "forecast_days" in h:
            if h["forecast_days"] not in (30, 60, 90):
                raise ApiError("The forecast card looks 30, 60 or 90 days ahead")
            out["forecast_days"] = h["forecast_days"]
        if "recent_count" in h:
            try:
                n = int(h["recent_count"])
            except (TypeError, ValueError):
                raise ApiError("Recent transactions must be a whole number")
            if not 3 <= n <= 30:
                raise ApiError("Show between 3 and 30 recent transactions")
            out["recent_count"] = n
        for k in ("hide_zero", "show_networth"):
            if k in h:
                out[k] = bool(h[k])
        return out

    # ----- starting and stopping -----------------------------------------------------
    def _autostart(self):
        if self.in_docker:
            raise ApiError("In Docker, the container's restart policy starts MoneyThistle with the server.")
        if self.launch_args is None:
            raise ApiError("This copy wasn't started by MoneyThistle's own program, so it can't set this up.")
        return autostart.Autostart(self.system.data_dir, self.launch_args)

    def _local(self):
        """The browser is on the computer MoneyThistle runs on: it connected over this
        computer's own loopback, or from the very address it reached (its network address
        or Tailscale name used on the same computer)."""
        norm = lambda a: str(a or "").replace("::ffff:", "").split("%")[0]
        addr = norm(getattr(self.ctx, "addr", ""))
        return addr.startswith("127.") or addr == "::1" or (addr != "" and addr == norm(getattr(self.ctx, "server_addr", "")))

    def startup_info(self):
        out = {"in_docker": self.in_docker, "can_shutdown": self.request_stop is not None and not self.in_docker,
               "local": self._local()}
        if self.in_docker or self.launch_args is None:
            return dict(out, supported=False)
        try:
            out.update(self._autostart().status(), supported=True)
        except Exception as e:
            out.update(supported=False, error=str(e))
        return out

    def save_startup(self, q, b):
        a = self._autostart()
        # With the computer first: if Windows' permission is refused, nothing else changes.
        if "always" in b:
            a.set_always(bool(b["always"]), self._local())
        if "login" in b:
            a.set_login(bool(b["login"]))
        if "desktop" in b:
            a.set_desktop(bool(b["desktop"]))
        return self.startup_info()

    def shutdown(self, q, b):
        """Stop MoneyThistle (desktop copies): it saves and makes its after-changes backup
        first. It starts again from its shortcut, or with the computer if set to."""
        if self.in_docker:
            raise ApiError("In Docker, stop the container instead (docker stop moneythistle); "
                           "otherwise Docker starts it again.")
        if not self.request_stop:
            raise ApiError("This copy can't be shut down from here; close the program that started it.")
        who = self.ctx.user["display_name"] or self.ctx.user["username"]
        threading.Timer(0.5, lambda: self.request_stop(f"the Shut down button ({who})")).start()
        return {"stopping": True}

    def _updater(self):
        if not self.updates:
            raise ApiError("Checking for updates isn't available in this copy", 404)
        return self.updates

    def version_info(self, q, b):
        disk = version.build_id()
        waiting = bool(self.build_id) and disk != self.build_id
        out = {"running": self.build_id, "files": disk, "version": version.VERSION,
               "update_waiting": waiting,
               # Administrators can always restart; anyone signed in can when an update
               # is waiting to be applied.
               "can_restart": self.request_restart is not None and (bool(self.ctx.user["is_admin"]) or waiting),
               "is_admin": bool(self.ctx.user["is_admin"]),
               "in_docker": self.in_docker, "files_mounted": self.in_docker and os.path.ismount("/app")}
        if self.ctx.user["is_admin"]:
            data_dir = self.system.data_dir
            local = self.backups.settings().get("local_dir", "")
            if self.in_docker:
                # Inside a container the folders have container names (/app, /data); the
                # install script passes the server's own folders along to show here.
                def on_server(var, inside, sub=""):
                    host = os.environ.get(var, "").rstrip("/")
                    if host:
                        return (host + "/" + sub if sub else host) + f"  (inside the container: {inside})"
                    return f"{inside} (inside the container)"
                local_shown = on_server("HOST_BACKUP_DIR", local) if local and local == os.environ.get("BACKUP_DIR") else local
                where = {"app_folder": on_server("HOST_APP_DIR", "/app"),
                         "data_file": on_server("HOST_DATA_DIR", data_dir),
                         "log_file": on_server("HOST_DATA_DIR", os.path.join(data_dir, "moneythistle.log"), "moneythistle.log"),
                         "backup_folder": local_shown}
            else:
                where = {"app_folder": version.HERE, "data_file": data_dir,
                         "log_file": os.path.join(data_dir, "moneythistle.log"), "backup_folder": local}
            out["where"] = {"mode": "Docker container" if self.in_docker else "Program on this computer (not Docker)",
                            **where,
                            "process_id": os.getpid(), "started": getattr(self, "started_at", ""),
                            "host": "container " + socket.gethostname() if self.in_docker else socket.gethostname()}
        return out

    # ----- reports, including accounts shared into this environment ------------------------
    def _shared_in(self):
        # Reporting across every environment: accounts shared from one of them are
        # counted where they live, not a second time where they're shared into.
        skip = getattr(self.ctx, "skip_shares_from", None) or ()
        return [a for a in self.system.incoming_shares(self.uid, self.env_id)
                if not a["closed"] and a["env_id"] not in skip]

    # ----- reports across all my environments --------------------------------------------
    def _member_envs(self):
        """The environments to show together: the ones asked for (?envs=1,2; every one this
        person belongs to when not given), only those they belong to, the one in view
        always included and first."""
        mine = [e["id"] for e in self.system.my_envs(self.uid)]
        asked = getattr(self.ctx, "req_envs", None)
        if asked:
            want = {int(x) for x in str(asked).split(",") if x.strip().isdigit()}
            envs = [e for e in mine if e in want or e == self.env_id]
        else:
            envs = mine
        return sorted(envs, key=lambda e: e != self.env_id)

    def _each_env(self, fn):
        """Run a report once per environment (as if each were in view) and return
        [(env id, result)]. Shares between these environments are skipped, so an account
        counts once, in its own environment."""
        envs = self._member_envs()
        saved = self.ctx.env_id
        self.ctx.skip_shares_from = set(envs)
        out = []
        try:
            for e in envs:
                self.ctx.env_id = e
                out.append((e, fn()))
        finally:
            self.ctx.env_id = saved
            self.ctx.skip_shares_from = None
        return out

    def all_envs_summary(self, q, b):
        """Home across every environment you belong to: accounts, what's due, recent
        entries, spending and the budget, each item saying which environment it's in."""
        try:
            recent = max(1, min(30, int(q.get("recent", 8))))
        except ValueError:
            recent = 8
        res = self._each_env(lambda: self.summary(q, b))
        names = {e: self.system.env_name(e) for e, _ in res}
        tag = lambda e, x: dict(x, env_id=e, env_name=names[e])
        out = {"today": res[0][1]["today"], "backup": res[0][1]["backup"], "all_envs": [names[e] for e, _ in res]}
        out["accounts"] = [tag(e, a) for e, s in res for a in s["accounts"]]
        out["shared_accounts"] = [tag(e, a) for e, s in res for a in s["shared_accounts"]]
        out["upcoming"] = sorted([tag(e, u) for e, s in res for u in s["upcoming"]], key=lambda u: (u["date"], u["payee"]))
        out["shared_upcoming"] = [tag(e, u) for e, s in res for u in s["shared_upcoming"]]
        out["statements_due"] = [tag(e, x) for e, s in res for x in s["statements_due"]]
        out["recent"] = sorted([tag(e, t) for e, s in res for t in s["recent"]],
                               key=lambda t: (t["date"], t.get("created") or ""), reverse=True)[:recent]
        spend = {}
        for _, s in res:
            for r in s["spending"]:
                spend[r["name"]] = spend.get(r["name"], 0) + r["total"]
        out["spending"] = sorted([{"id": None, "name": n, "total": v} for n, v in spend.items() if v], key=lambda r: -r["total"])
        out["budget"] = self._merge_budgets(res and [(e, s["budget"]) for e, s in res])
        for k in ("assets", "debts", "net_worth"):
            out[k] = sum(s[k] for _, s in res)
        return out

    def all_envs_budget(self, month=None, mode=None):
        return self._merge_budgets(self._each_env(lambda: self.budget(month, mode)))

    def _merge_budgets(self, res):
        """Budgets of several environments as one, for looking at (amounts are changed in
        each environment's own budget). Lines with the same category or item add up."""
        names = {e: self.system.env_name(e) for e, _ in res}
        first = res[0][1]
        out = {k: first[k] for k in ("month", "days_in_month", "day_of_month") if k in first}
        out.update(combined=True, all_envs=list(names.values()), mode=first.get("mode", "categories"))
        sum_keys = ("income_budget", "income_actual", "expense_budget", "expense_actual", "moved_budget", "moved_actual")
        for k in sum_keys:
            if any(k in r for _, r in res):
                out[k] = sum(r.get(k, 0) for _, r in res)
        out["entered_ahead"] = [dict(x, account_name=f"{x.get('account_name') or ''} · {names[e]}", shared=True)
                                for e, r in res for x in r.get("entered_ahead", [])]
        if out["mode"] == "schedule":
            out["rows"] = [dict(x, account_name=f"{x['account_name']} · {names[e]}") for e, r in res for x in r["rows"]]
            out["card_charges"] = [dict(c, name=f"{c['name']} · {names[e]}", shared=True) for e, r in res
                                   for c in r.get("card_charges", [])]
            return out
        rows = {}
        for e, r in res:
            for x in r["rows"]:
                k = (x["kind"], x["name"].lower(), bool(x.get("loan")))
                if k not in rows:
                    rows[k] = dict(x, category_id=None, loan_account_id=None, envs=[])
                else:
                    for f in ("budget", "typed", "scheduled", "actual", "shared"):
                        rows[k][f] = rows[k].get(f, 0) + x.get(f, 0)
                    rows[k]["from_schedule"] = rows[k]["from_schedule"] and x.get("from_schedule")
                rows[k]["envs"].append(names[e])
        out["rows"] = sorted(rows.values(), key=lambda x: x["name"].lower())
        out["shared_outside"] = [dict(x, category_id=None) for _, r in res for x in r.get("shared_outside", [])]
        out["includes_shared"] = any(r.get("includes_shared") for _, r in res)
        return out

    def all_envs_spending(self, start, end, kind):
        by_name = {}
        for env, rows in self._each_env(lambda: self.report_spending(start, end, kind)):
            for r in rows:
                t = by_name.setdefault(r["name"], {"id": None, "name": r["name"], "total": 0, "envs": []})
                t["total"] += r["total"]
                t["envs"].append(self.system.env_name(env))
        out = [r for r in by_name.values() if r["total"]]
        out.sort(key=lambda r: -r["total"])
        return out

    def all_envs_entries(self, name, kind, start, end):
        """The entries behind one line of "Where the money goes" across environments: every
        entry whose category (or main category) has that name."""
        if not name:
            raise ApiError("Which category?")

        def one():
            rows = self.store.q(
                self.store.TX_SELECT + "WHERE t.transfer_id IS NULL AND c.kind=? AND t.date>=? AND t.date<=? "
                "AND (COALESCE(p.name, c.name)=? COLLATE NOCASE) ORDER BY t.date DESC", (kind, start, end, name))
            return self.store._decorate(rows)
        out = []
        for env, rows in self._each_env(one):
            label = self.system.env_name(env)
            out += [dict(r, account_name=f"{r['account_name']} ({label})") for r in rows]
        out.sort(key=lambda r: r["date"], reverse=True)
        return out

    def all_envs_sum(self, fn, keys):
        """Month-by-month reports: the same months in every environment, added up."""
        res = self._each_env(fn)
        base = [dict(r) for r in res[0][1]]
        for _, rows in res[1:]:
            for mine, theirs in zip(base, rows):
                for k in keys:
                    mine[k] += theirs[k]
        return base

    def all_envs_forecast(self, days):
        res = self._each_env(lambda: self.report_forecast(days))
        envs = [e for e, _ in res]
        names = {e: self.system.env_name(e) for e in envs}
        f = {k: v for k, v in res[0][1].items() if k not in ("accounts", "events")}
        f["accounts"], f["events"] = [], []
        key = lambda e, i: None if i is None else f"{e}:{i}"
        for e, one in res:
            f["accounts"] += [dict(a, id=key(e, a["id"]), name=f"{a['name']} · {names[e]}") for a in one["accounts"]]
            f["events"] += [dict(ev, account_id=key(e, ev.get("account_id")), to_account_id=key(e, ev.get("to_account_id")),
                                 account_name=f"{ev['account_name']} · {names[e]}") for ev in one["events"]]
        # A scheduled transfer between two of these environments lives with one side; the
        # other side's balance moves too.
        rows = {a["id"]: a for a in f["accounts"]}
        start = dt.date.fromisoformat(f["start"])
        for e in envs:
            for o in self.system.store(e).upcoming(f["days"]):
                if not o.get("x_link_id"):
                    continue
                try:
                    oe, oa = self.system.link_other_side(o["x_link_id"], e, o["account_id"])
                except ApiError:
                    continue
                row = rows.get(key(oe, oa))
                if oe not in envs or not row:
                    continue
                amt = o["amount"] if o["x_dir"] == "out" else -o["amount"]
                i = max(0, (dt.date.fromisoformat(o["date"]) - start).days)
                row["series"] = row["series"][:i] + [v + amt for v in row["series"][i:]]
                lo = min(range(len(row["series"])), key=lambda k: row["series"][k])
                row.update(end=row["series"][-1], low=row["series"][lo], has_activity=True,
                           low_date=(start + dt.timedelta(days=lo)).isoformat())
                f["events"].append({"date": max(o["date"], f["start"]), "payee": o["payee"] or "Transfer",
                                    "kind": "transfer", "account_id": key(oe, oa), "account_name": row["name"],
                                    "amount": amt, "estimated": o.get("amount_mode") == "average",
                                    "overdue": o["overdue"]})
        f["events"].sort(key=lambda ev: (ev["date"], ev["payee"]))
        f["all_envs"] = [names[e] for e in envs]
        return f

    def all_envs_tax(self, year):
        res = self._each_env(lambda: self.report_tax(year))
        out = dict(res[0][1])
        for side in ("income", "expense"):
            merged = {}
            for e, r in res:
                label = self.system.env_name(e)
                for g in r[side]:
                    m = merged.setdefault(g["name"], {**g, "total": 0, "items": []})
                    m["total"] += g["total"]
                    m["items"] += [dict(i, account_name=f"{i['account_name']} ({label})") for i in g["items"]]
            out[side] = sorted(merged.values(), key=lambda g: g["name"].lower())
            for g in out[side]:
                g["items"].sort(key=lambda i: i["date"])
        out["hsa"] = [dict(h, name=f"{h['name']} ({self.system.env_name(e)})") for e, r in res for h in r["hsa"]]
        out["pay"] = [p for _, r in res for p in r["pay"]]
        # Paychecks to check, from every environment (links open the account in its own one).
        out["paychecks"] = [dict(p, employer=f"{p['employer']} ({self.system.env_name(e)})")
                            for e, r in res for p in r.get("paychecks", [])]
        limit = next((r["hsa_totals"]["limit"] for _, r in res if r["hsa_totals"]["limit"] is not None), None)
        personal = sum(h["after_tax"] for h in out["hsa"])
        employer = sum(h["pretax"] for h in out["hsa"])
        out["hsa_totals"] = {"personal": personal, "employer": employer, "total": personal + employer,
                             "earnings": sum(h["earnings"] for h in out["hsa"]),
                             "withdrawn": sum(h["withdrawn"] for h in out["hsa"]),
                             "limit": limit, "room": None if limit is None else limit - personal - employer}
        out["has_hsa_accounts"] = any(r["has_hsa_accounts"] for _, r in res)
        out["all_envs"] = [self.system.env_name(e) for e, _ in res]
        return out

    def report_spending(self, start, end, kind="expense"):
        rows = self.store.spending_by_category(start, end, kind)
        by_name = {r["name"]: r for r in rows}
        for a in self._shared_in():
            # A shared account uses its own environment's categories: merged here by name.
            for r in self.system.store(a["env_id"]).spending_by_category(start, end, kind, [a["id"]]):
                if r["name"] in by_name:
                    by_name[r["name"]]["total"] += r["total"]
                    by_name[r["name"]]["includes_shared"] = True
                else:
                    by_name[r["name"]] = {"id": None, "name": r["name"], "total": r["total"], "includes_shared": True}
        out = [r for r in by_name.values() if r["total"] != 0]
        out.sort(key=lambda r: -r["total"])
        return out

    def budget(self, month=None, mode=None):
        """This environment's budget in the person's chosen style: by categories, or
        by scheduled items (Bills & Deposits) for those who don't track categories.
        Accounts shared into the environment count too."""
        mode = mode or self.ui_settings().get("budget_mode", "categories")
        if mode == "schedule":
            return self.schedule_budget(month)
        if mode != "categories":
            raise ApiError("Budget style must be categories or schedule")
        out = self.category_budget(month)
        out["entered_ahead"] = self.entered_ahead(out["month"])
        return out

    def schedule_budget(self, month=None):
        try:
            m, start, end = self.store.month_range(month)
        except (ValueError, IndexError):
            raise ApiError("Month must look like 2026-11")
        lines = self.store.schedule_lines(m)
        for a in self._shared_in():
            if not a["include_bills"]:
                continue
            for ln in self.system.store(a["env_id"]).schedule_lines(m, [a["id"]]):
                lines.append({**ln, "shared": True, "account_name": f"{ln['account_name']} (shared)"})
        lines.sort(key=lambda r: (r["side"], -r["expected"], r["payee"].lower()))
        out = self.store.schedule_budget(m, lines)
        out["entered_ahead"] = self.entered_ahead(m)
        cards = self.store.card_charges(m)
        for a in self._shared_in():
            cards += [dict(c, name=f"{c['name']} (shared)", shared=True)
                      for c in self.system.store(a["env_id"]).card_charges(m, [a["id"]])]
        out["card_charges"] = cards
        return out

    def entered_ahead(self, month):
        """Payments from the schedule already recorded with a later month's date (only
        for the current month), shared accounts included."""
        if month != dt.date.today().strftime("%Y-%m"):
            return []
        rows = [dict(r, account_name=next((a["name"] for a in self.store.accounts() if a["id"] == r["account_id"]), ""))
                for r in self.store.entered_ahead(month)]
        for a in self._shared_in():
            if a["include_bills"]:
                rows += [dict(r, account_name=f"{a['name']} (shared)", shared=True, group_id=None)
                         for r in self.system.store(a["env_id"]).entered_ahead(month, [a["id"]])]
        return sorted(rows, key=lambda r: (r["date"], r["payee"]))

    def category_budget(self, month=None):
        shares = self._shared_in()
        if not shares:
            return self.store.budget(month)
        try:
            m, start, end = self.store.month_range(month)
        except (ValueError, IndexError):
            raise ApiError("Month must look like 2026-11")
        totals, sched, loan_rows = [], [], []
        for a in shares:
            other = self.system.store(a["env_id"])
            # Loan payments made from the shared account: a line each, whole payment.
            lines = other.loan_lines(m, [a["id"]])
            for ln in lines:
                if not a["include_bills"]:   # its schedule isn't shared: only what was paid
                    ln["scheduled"] = ln["actual"]
                loan_rows.append({**ln, "name": f"{ln['name']} (from {a['name']}, shared)"})
            totals += other.category_totals(start.isoformat(), end.isoformat(), [a["id"]],
                                            [g for ln in lines for g in ln["group_ids"]])
            if a["include_bills"]:   # its schedule is shared too: it sets expectations here
                sched += other.scheduled_totals(m, [a["id"]])
        return self.store.budget(m, totals, sched, [r for r in loan_rows if r["actual"] or r["scheduled"]])

    def report_tax(self, year):
        """The year-end tax report, accounts shared into this environment included (their
        categories merged by name). One HSA limit covers every HSA here: the IRS limit is
        for all of a person's (or family's) HSAs together, employer money included."""
        out = self.store.tax_report(year)
        y = out["year"]
        for a in self._shared_in():
            other = self.system.store(a["env_id"]).tax_report(y, [a["id"]])
            for side in ("income", "expense"):
                mine = {g["name"]: g for g in out[side]}
                for g in other[side]:
                    items = [dict(i, account_name=f"{i['account_name']} (shared)", shared=True) for i in g["items"]]
                    if g["name"] in mine:
                        mine[g["name"]]["total"] += g["total"]
                        mine[g["name"]]["items"] = sorted(mine[g["name"]]["items"] + items, key=lambda i: i["date"])
                    else:
                        out[side].append({**g, "items": items})
                out[side].sort(key=lambda g: g["name"].lower())
            out["hsa"] += [dict(h, name=f"{h['name']} (shared)", shared=True) for h in other["hsa"]]
            out["pay"] += [dict(p, employer=f"{p['employer']} (shared)", shared=True) for p in other["pay"]]
        # After tax (you deduct it) vs before tax (employer money, or out of a paycheck).
        personal = sum(h["after_tax"] for h in out["hsa"])
        employer = sum(h["pretax"] for h in out["hsa"])
        limit = self.store.hsa_limit(y)
        out["hsa_totals"] = {"personal": personal, "employer": employer, "total": personal + employer,
                             "earnings": sum(h["earnings"] for h in out["hsa"]),
                             "withdrawn": sum(h["withdrawn"] for h in out["hsa"]),
                             "limit": limit, "room": None if limit is None else limit - personal - employer}
        out["has_hsa_accounts"] = bool(self.store.hsa_accounts())
        return out

    def report_monthly(self, months):
        rows = self.store.income_vs_spending(months)
        for a in self._shared_in():
            for mine, theirs in zip(rows, self.system.store(a["env_id"]).income_vs_spending(months, [a["id"]])):
                for k in ("income", "spending", "net"):
                    mine[k] += theirs[k]
        return rows

    def report_networth(self, months):
        rows = self.store.net_worth_history(months)
        for a in self._shared_in():
            for mine, theirs in zip(rows, self.system.store(a["env_id"]).net_worth_history(months, [a["id"]])):
                mine["net_worth"] += theirs["net_worth"]
        return rows

    def report_forecast(self, days):
        f = self.store.forecast(days)
        # A shared account goes by "s<share id>" here, so its scheduled items can be
        # matched to its line on the chart.
        sid_of = {(a["env_id"], a["id"]): f"s{a['share_id']}" for a in self._shared_in()}
        for a in self._shared_in():
            other = self.system.store(a["env_id"]).forecast(days)
            row = next((r for r in other["accounts"] if r["id"] == a["id"]), None)
            if not row:
                continue
            if not a["include_bills"]:
                # Its schedule isn't shared: today's balance, flat.
                row = {**row, "series": [row["now"]] * (f["days"] + 1), "low": row["now"], "end": row["now"],
                       "low_date": f["start"], "has_activity": False}
            else:
                f["events"] += [{**e, "account_name": f"{e['account_name']} (shared by {a['shared_by']})", "shared": True,
                                 "account_id": sid_of[(a["env_id"], a["id"])],
                                 "to_account_id": sid_of.get((a["env_id"], e.get("to_account_id")))}
                                for e in other["events"] if e["account_id"] == a["id"]]
            f["accounts"].append({**row, "id": f"s{a['share_id']}", "name": f"{a['name']} (shared by {a['shared_by']})",
                                  "shared": True})
        # Scheduled transfers kept with a shared account that reach one of this
        # environment's accounts: that account's side counts here too.
        own = {r["id"]: r for r in f["accounts"] if not r.get("shared")}
        done = set()
        start = dt.date.fromisoformat(f["start"])
        for a in self._shared_in():
            if not a["include_bills"]:
                continue
            for o in self.system.store(a["env_id"]).upcoming(f["days"]):
                if not o.get("x_link_id") or (a["env_id"], o["id"], o["date"]) in done:
                    continue
                try:
                    oe, oa = self.system.link_other_side(o["x_link_id"], a["env_id"], o["account_id"])
                except ApiError:
                    continue
                if oe != self.env_id or oa not in own:
                    continue
                done.add((a["env_id"], o["id"], o["date"]))
                amt = o["amount"] if o["x_dir"] == "out" else -o["amount"]
                i = max(0, (dt.date.fromisoformat(o["date"]) - start).days)
                row = own[oa]
                row["series"] = row["series"][:i] + [v + amt for v in row["series"][i:]]
                lo = min(range(len(row["series"])), key=lambda k: row["series"][k])
                row.update(end=row["series"][-1], low=row["series"][lo], has_activity=True,
                           low_date=(start + dt.timedelta(days=lo)).isoformat())
                f["events"].append({"date": max(o["date"], f["start"]), "payee": o["payee"] or "Transfer",
                                    "kind": "transfer", "account_id": oa, "account_name": row["name"],
                                    "amount": amt, "estimated": o.get("amount_mode") == "average",
                                    "overdue": o["overdue"], "shared": True})
        f["events"].sort(key=lambda e: (e["date"], e["payee"]))
        return f

    # ----- money data -----------------------------------------------------------------
    def summary(self, q, b):
        try:
            recent = max(1, min(30, int(q.get("recent", 8))))
        except ValueError:
            recent = 8
        self._auto_enter()
        s = self.store.summary(int(q.get("days", 14)), recent)
        self.system.decorate(self.env_id, s["recent"])
        s["backup"] = self.system.backup_status()
        # Accounts shared into this environment count in its totals too.
        shared = self._shared_in()
        s["shared_accounts"] = shared
        if shared:   # "where the money went this month" includes shared accounts too
            t = dt.date.today()
            s["spending"] = self.report_spending(t.replace(day=1).isoformat(), t.isoformat())
        if shared or self.ui_settings().get("budget_mode") == "schedule":
            s["budget"] = self.budget()   # the person's budget style, shared accounts included
        s["statements_due"] = self.store.statements_due()
        skip = getattr(self.ctx, "skip_shares_from", None) or ()
        s["shared_upcoming"] = [u for u in self.system.incoming_bills(self.uid, self.env_id, int(q.get("days", 14)))
                                if u["share_env_id"] not in skip]
        if shared:
            s["money"] = self.store.totals(s["accounts"] + shared)
            s["assets"], s["debts"], s["net_worth"] = s["money"]["assets"], s["money"]["debts"], s["money"]["net_worth"]
        return s

    def list_tx(self, q, b):
        if self.share:
            q = dict(q, account=str(self.share[1]))   # a shared visit sees only that account
        rows = self.store.transactions(account_id=int(q["account"]) if q.get("account") else None,
                                       search=q.get("q") or None, start=q.get("from") or None,
                                       end=q.get("to") or None,
                                       category_id=int(q["category"]) if q.get("category") else None,
                                       limit=int(q.get("limit", 2000)))
        # Paychecks with less filled in than usual for their employer: flagged in the register.
        if any(r.get("paycheck") is not None or r.get("paystub") for r in rows):
            fl = paystubs.flags(self.store)
            for r in rows:
                key = ("stub", r["group_id"]) if r.get("paystub") else (("tx", r["id"]) if r.get("paycheck") is not None else None)
                if key and key in fl:
                    r["pay_flag"] = fl[key]
        return self.system.decorate(self.env_id, rows)

    def save_tx(self, b, tid=None):
        if b.get("share_xfer") and not self.share:
            # From one of this environment's accounts to (or from) an account shared into it
            # with entering allowed: the share is the owner's sign-off for this connection.
            b = dict(b, xlink_id=self.system.ensure_share_link(self.uid, int(b["share_xfer"]),
                                                               int(b.get("account_id") or 0), self.env_id))
        if self.share:
            if int(b.get("account_id") or 0) != self.share[1]:
                raise ApiError("Only the shared account", 403)
            if b.get("xlink_id") or b.get("transfer_account_id"):
                raise ApiError("Transfers from a shared account are made in its own environment", 403)
            if tid:
                self._share_tx_ok(tid)
        if b.get("xlink_id"):
            return self.system.cross_transfer(self.env_id, b, tid)
        if tid:
            self.system.detach_cross(self.env_id, tid)
        return self.store.save_transaction(b, tid)

    # ----- attachments --------------------------------------------------------------
    def _attach_tx(self, tid):
        """The entry an attachment belongs to must be visible here (a shared visit: that account)."""
        row = self.store.q1("SELECT id, account_id, payee, date FROM transactions WHERE id=?", (tid,))
        if not row:
            raise ApiError("No such entry", 404)
        if self.share and row["account_id"] != self.share[1]:
            raise ApiError("That entry isn't in the shared account", 403)
        return row

    def list_attachments(self, q, b, i):
        self._attach_tx(int(i))
        return attachments.listing(self.store, int(i))

    def add_attachment(self, q, b, i):
        t = self._attach_tx(int(i))
        aid, name = attachments.add(self.system, self.store, self.system.data_dir, t["id"], self.uid, b)
        history.record(self.system, self.env_id, "attachment", t["id"], "add", None, None,
                       f"Attached {name} to {t['payee'] or 'an entry'} on {t['date']}")
        return {"id": aid, "attachments": attachments.listing(self.store, t["id"])}

    def _attach_acct(self, aid):
        row = self.store.q1("SELECT id, name FROM accounts WHERE id=?", (aid,))
        if not row:
            raise ApiError("No such account", 404)
        if self.share and row["id"] != self.share[1]:
            raise ApiError("That isn't the shared account", 403)
        return row

    def _attach_owner(self, row):
        """Where a file is kept, checked as visible here: (what to call it, list again)."""
        if row["transaction_id"]:
            t = self._attach_tx(row["transaction_id"])
            return (f"{t['payee'] or 'an entry'} on {t['date']}",
                    lambda: attachments.listing(self.store, t["id"]))
        a = self._attach_acct(row["account_id"])
        return f"account {a['name']}", lambda: attachments.listing(self.store, account_id=a["id"])

    def list_account_files(self, q, b, i):
        self._attach_acct(int(i))
        return attachments.listing(self.store, account_id=int(i))

    def add_account_file(self, q, b, i):
        a = self._attach_acct(int(i))
        aid, name = attachments.add(self.system, self.store, self.system.data_dir, None, self.uid, b, account_id=a["id"])
        history.record(self.system, self.env_id, "attachment", None, "add", None, None,
                       f"Attached {name} to account {a['name']}")
        return {"id": aid, "attachments": attachments.listing(self.store, account_id=a["id"])}

    def search_attachments(self, q, b):
        acct = int(q["account"]) if q.get("account") else None
        if self.share:
            acct = self.share[1]
        rows = attachments.search(self.store, q.get("q"), acct, q.get("from") or None, q.get("to") or None)
        return {"files": rows, "accounts": self.store.q(
            "SELECT DISTINCT a.id, a.name FROM attachments x LEFT JOIN transactions t ON t.id=x.transaction_id "
            "JOIN accounts a ON a.id=COALESCE(x.account_id, t.account_id) ORDER BY a.name")}

    def open_attachment(self, q, b, i):
        row = attachments.get(self.store, int(i))
        self._attach_owner(row)
        name = urllib.parse.quote(row["name"])
        how = "attachment" if q.get("download") else "inline"
        return Raw(attachments.read(self.system.data_dir, row), row["mime"],
                   {"Content-Disposition": f"{how}; filename*=UTF-8''{name}"})

    def update_attachment(self, q, b, i):
        row = attachments.get(self.store, int(i))
        self._attach_owner(row)
        return attachments.update(self.store, int(i), b)

    def delete_attachment(self, q, b, i):
        row = attachments.get(self.store, int(i))
        where, again = self._attach_owner(row)
        attachments.remove(self.store, int(i))
        history.record(self.system, self.env_id, "attachment", row["transaction_id"], "delete", None, None,
                       f"Removed {row['name']} from {where}")
        return {"attachments": again()}

    def delete_tx(self, q, b, i):
        self._share_tx_ok(int(i))
        self.system.detach_cross(self.env_id, int(i))
        self.store.delete_transaction(int(i))

    def delete_account(self, q, b, i):
        if self.system.q1("SELECT 1 FROM links WHERE status IN ('pending','active') AND "
                          "((env_a=? AND account_a=?) OR (env_b=? AND account_b=?))",
                          (self.env_id, int(i), self.env_id, int(i))):
            raise ApiError("This account is connected to another environment. End that connection first "
                           "(People & access).")
        if self.system.q1("SELECT 1 FROM shares WHERE status IN ('pending','active') AND env_a=? AND account_a=?",
                          (self.env_id, int(i))):
            raise ApiError("This account is shared with another environment. Stop sharing it first "
                           "(People & access).")
        self.store.delete_account(int(i))

    def pay_loan(self, aid, b):
        """A payment made from the loan screen; if it's the scheduled one, move the schedule on."""
        res = loans.pay(self.store, aid, b)
        bill = self.store.q1("SELECT * FROM bills WHERE kind='loan' AND loan_account_id=? AND active=1", (aid,))
        if bill and b.get("advance_schedule", True):
            with self.store.lock:
                self.store._advance_bill(bill)
                self.store.db.commit()
        return res

    def import_file(self, q, b):
        aid = int(b.get("account_id") or 0)
        self.store.account(aid)
        text = b.get("text") or ""
        name = (b.get("filename") or "").lower()
        info = {}
        if name.endswith((".ofx", ".qfx", ".qbo")) or "OFXHEADER" in text[:300].upper() or "<OFX" in text[:2000].upper():
            rows, info = fileio.parse_ofx(text)
        elif name.endswith(".qif") or text.lstrip().startswith("!Type"):
            rows = fileio.parse_qif(text)
        else:
            rows = fileio.parse_csv(text)
        plan = fileio.plan_import(self.store, aid, rows)
        if b.get("preview"):
            # Review first: what would happen to each row; nothing is changed.
            return {"plan": plan, "file_account": info.get("account_last4"),
                    "bank_balance": info.get("balance"), "bank_balance_date": info.get("balance_date")}
        out = fileio.apply_import(self.store, aid, rows, plan, b.get("choices"))
        if info.get("balance") is not None:
            # The bank's balance next to the register's on the same day: a quick check.
            d = info.get("balance_date") or dt.date.today().isoformat()
            out.update(bank_balance=info["balance"], bank_balance_date=d,
                       register_balance=self.store.balance_on(aid, d))
        if info.get("account_last4"):
            out["file_account"] = info["account_last4"]
        return out


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MoneyThistle/1.0"

        def log_message(self, fmt, *args):
            if os.environ.get("ACCESS_LOG"):
                super().log_message(fmt, *args)

        def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            sc = getattr(app.ctx, "set_cookie", None)
            if sc is not None:
                if sc:
                    # Kept on this device: 30 days. Otherwise a browser-session cookie.
                    keep = getattr(app.ctx, "cookie_keep", True)
                    self.send_header("Set-Cookie", f"{COOKIE}={sc}; Path=/; HttpOnly; SameSite=Lax"
                                     + (f"; Max-Age={30 * 86400}" if keep else ""))
                    app.ctx.cookie_keep = True
                else:
                    self.send_header("Set-Cookie", f"{COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
                app.ctx.set_cookie = None
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj, default=str))

        def _token(self):
            c = SimpleCookie()
            try:
                c.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            return c[COOKIE].value if COOKIE in c else None

        def _dispatch(self, method):
            url = urllib.parse.urlsplit(self.path)
            q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
            path = url.path
            ctx = app.ctx
            ctx.set_cookie, ctx.addr = None, self.client_address[0]
            try:
                ctx.server_addr = self.connection.getsockname()[0]   # the address the browser reached
            except Exception:
                ctx.server_addr = ""
            ctx.host = self.headers.get("Host", "")
            if path == "/healthz":
                return self._send(200, "ok", "text/plain", {"X-HomeLedger-Build": app.build_id})
            if path == "/api/admin/stop" and method == "POST":
                given = self.headers.get("X-HomeLedger-Control", "")
                if not (app.control_token and app.request_stop and
                        hmac.compare_digest(given.encode(), app.control_token.encode())):
                    return self._json(403, {"error": "Not allowed"})
                self._json(200, {"ok": True, "stopping": True})
                app.request_stop()
                return
            if not path.startswith("/api/"):
                if method not in ("GET", "HEAD"):
                    return self._json(405, {"error": "Method not allowed"})
                return self._static(path)
            # Changes only from this app's own pages: they add a header that other
            # websites can't send without the server's permission.
            if method != "GET" and self.headers.get("X-HomeLedger") != "1":
                return self._json(403, {"error": "Not allowed"})
            # A link to a file (a receipt opened in a new tab) can't send headers: its
            # shared account comes in the address instead, for reading only.
            ctx.q_share = q.get("share") if method == "GET" else None
            ctx.token = self._token()
            ctx.user = app.system.session_user(ctx.token)
            if not ctx.user and app.auto_user_id:
                ctx.user = app.system.user(app.auto_user_id)
            try:
                env_raw = self.headers.get("X-HomeLedger-Env") or q.get("env")
                ctx.env_id = int(env_raw) if env_raw else None
            except ValueError:
                ctx.env_id = None
            if path == "/api/admin/restart" and method == "POST":
                if not ctx.user:
                    return self._json(401, {"error": "Please sign in"})
                waiting = bool(app.build_id) and version.build_id() != app.build_id
                if not ctx.user["is_admin"] and not waiting:
                    return self._json(403, {"error": "No update is waiting. Only an administrator can restart "
                                                     "MoneyThistle at other times."})
                if not app.request_restart:
                    return self._json(400, {"error": "This copy can't restart itself"})
                self._json(200, {"ok": True, "restarting": True})
                app.request_restart()
                return
            body = {}
            if method == "POST" and path in RAW_UPLOADS:
                # A whole backup file, sent as it is (it may be large with many receipts). Its
                # password, if any, comes base64-encoded in a header, never in the address.
                n = int(self.headers.get("Content-Length") or 0)
                if n > 2 * 1024 * 1024 * 1024:
                    return self._json(413, {"error": "That file is larger than 2 GB"})
                pw = self.headers.get("X-Backup-Password") or ""
                try:
                    pw = base64.b64decode(pw).decode("utf-8") if pw else ""
                except Exception:
                    pw = ""
                body = {"raw": self.rfile.read(n) if n else b"", "password": pw,
                        "filename": urllib.parse.unquote(self.headers.get("X-File-Name") or "")[:200]}
            elif method in ("POST", "PUT"):
                n = int(self.headers.get("Content-Length") or 0)
                if n > 50 * 1024 * 1024:
                    return self._json(413, {"error": "Too large"})
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw or b"{}")
                except ValueError:
                    return self._json(400, {"error": "Bad JSON"})
            try:
                if path == "/api/export.csv":
                    self._check("env", "GET", None)
                    aid = int(q["account"]) if q.get("account") else None
                    return self._send(200, fileio.export_csv(app.store, aid), "text/csv; charset=utf-8",
                                      {"Content-Disposition": 'attachment; filename="transactions.csv"'})
                for m, rx, fn, scope, share in app.routes:
                    if m != method:
                        continue
                    mt = rx.match(path)
                    if mt:
                        self._check(scope, method, share)
                        # Changes made while serving this request are this person's, as one action.
                        history.set_actor(ctx.user["id"] if getattr(ctx, "user", None) else None)
                        ctx.req_envs = q.get("envs")   # which environments a combined view covers
                        try:
                            res = fn(q, body, *mt.groups())
                        finally:
                            history.clear_actor()
                        if isinstance(res, Raw):
                            return self._send(200, res.data, res.ctype, res.headers)
                        return self._json(200, {"ok": True} if res is None else res)
                return self._json(404, {"error": "Not found"})
            except ApiError as e:
                return self._json(e.status, {"error": str(e), **({"field": e.field} if e.field else {})})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": f"Something went wrong: {e}"})

        def _check(self, scope, method, share_rule):
            ctx = app.ctx
            ctx.share = None
            if scope == "public":
                return
            if not ctx.user:
                raise ApiError("Please sign in", 401)
            if scope == "admin" and not ctx.user["is_admin"]:
                raise ApiError("Only an administrator can do that", 403)
            if scope == "env":
                sid = self.headers.get("X-HomeLedger-Share") or getattr(ctx, "q_share", None)
                if sid:
                    # Opening an account shared into one of this person's environments:
                    # only that account, and only what the share allows.
                    try:
                        env_a, acct, can_edit, with_bills = app.system.share_access(ctx.user["id"], int(sid))
                    except ValueError:
                        raise ApiError("Bad share", 400)
                    if share_rule is None or (share_rule == "write" and not can_edit) or \
                            (share_rule == "bills" and not (can_edit and with_bills)):
                        raise ApiError("This shared account can be viewed but not changed" if share_rule
                                       else "Not available for a shared account", 403)
                    ctx.env_id, ctx.share = env_a, (int(sid), acct, can_edit, with_bills)
                    return
                if not ctx.env_id:
                    raise ApiError("Choose an environment", 400)
                app.system.require(ctx.user["id"], ctx.env_id, "viewer" if method == "GET" else "editor")

        def _static(self, path):
            if path in ("", "/"):
                path = "/index.html"
            full = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
            if not full.startswith(STATIC) or not os.path.isfile(full):
                full = os.path.join(STATIC, "index.html")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            with open(full, "rb") as f:
                self._send(200, f.read(), ctype)

        def do_GET(self):
            self._dispatch("GET")

        def do_HEAD(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

    return Handler


class _Server6(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        # Only IPv6 here; IPv4 has its own listener.
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        except (OSError, AttributeError):
            pass
        super().server_bind()


def make_server(app, host, port):
    cls = _Server6 if ":" in host else ThreadingHTTPServer
    httpd = cls((host.strip("[]"), port), make_handler(app))
    httpd.daemon_threads = True
    return httpd


def companion_host(host):
    """The other loopback/any address to listen on too, so "localhost" works
    whether a browser tries IPv4 or IPv6 first."""
    if not socket.has_ipv6:
        return None
    return {"127.0.0.1": "::1", "localhost": "::1", "0.0.0.0": "::"}.get(host)
