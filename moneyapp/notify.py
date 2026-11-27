"""Notifications: a daily summary sent by email (SMTP), Pushover, ntfy or Gotify.

Each person sets up their own in Settings: which services (with their own credentials),
what to hear about and when. Administrators' setup covers every environment; everyone
else's covers the environments they belong to. An administrator can share their email
server, so others only enter their own address. Kept in data/notify.json, secrets
included, like the backup settings; secrets are never sent back to the page. Once a day,
at each person's hour, MoneyThistle sends them one short summary if there's anything to
say. Only the Python standard library is used (smtplib, urllib); services are reached
over HTTPS or TLS unless told otherwise.
"""

import datetime as dt
import json
import os
import smtplib
import ssl
import threading
import time
import urllib.parse
import urllib.request
import html as _html
import re as _re
from email.message import EmailMessage
from email.utils import make_msgid

_BRAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "brand", "wordmark-450.png")


def _wordmark():
    """The MoneyThistle wordmark (sent inside the email, so nothing is fetched from anywhere)."""
    try:
        with open(_BRAND, "rb") as f:
            return f.read()
    except OSError:
        return None


def email_html(title, body, logo_cid=None):
    """An email's text as a small, tidy HTML page: the wordmark on the app's navy band, the
    message on a white card. Paragraphs come from blank lines, "  - " lines become a list, web
    addresses become links, and a link on a line of its own becomes a button (a password link
    says what it's for). Everything else is the same words as the plain text."""
    url = _re.compile(r"https?://\S+")

    def inline(s):
        out, last = [], 0
        for m in url.finditer(s):
            out.append(_html.escape(s[last:m.start()]))
            u = m.group(0)
            out.append(f'<a href="{_html.escape(u, quote=True)}" style="color:#1c4b8a">{_html.escape(u)}</a>')
            last = m.end()
        out.append(_html.escape(s[last:]))
        return "".join(out)

    blocks = []
    for para in _re.split(r"\n\s*\n", body.strip("\n")):
        lines = [ln.rstrip() for ln in para.split("\n") if ln.strip()]
        if not lines:
            continue
        if len(lines) == 1 and url.fullmatch(lines[0].strip()):
            u = lines[0].strip()
            label = "Choose your password" if "#/reset/" in u else "Open MoneyThistle"
            blocks.append(f'<p style="margin:18px 0"><a href="{_html.escape(u, quote=True)}" style="display:inline-block;'
                          f'background:#1c4b8a;color:#ffffff;text-decoration:none;font-weight:600;padding:11px 20px;'
                          f'border-radius:8px">{label}</a></p><p style="margin:0 0 14px;font-size:12px;color:#6b7a8c;'
                          f'word-break:break-all">{_html.escape(u)}</p>')
            continue
        items = [ln.strip()[2:] for ln in lines if ln.strip().startswith("- ")]
        head = [ln for ln in lines if not ln.strip().startswith("- ")]
        if items and len(items) == len(lines) - len(head) and all(not ln.strip().startswith("- ") for ln in lines[:len(head)]):
            if head:
                blocks.append('<p style="margin:0 0 6px">' + "<br>".join(inline(h.strip()) for h in head) + "</p>")
            blocks.append('<ul style="margin:0 0 14px;padding-left:20px">' +
                          "".join(f'<li style="margin:3px 0">{inline(i)}</li>' for i in items) + "</ul>")
            continue
        blocks.append('<p style="margin:0 0 14px">' + "<br>".join(inline(ln.strip()) for ln in lines) + "</p>")
    logo = (f'<img src="cid:{logo_cid}" alt="MoneyThistle" width="240" style="display:block;border:0;width:240px;'
            f'max-width:70%;height:auto">' if logo_cid else
            '<span style="font:700 22px Arial,sans-serif;color:#ffffff">MoneyThistle</span>')
    return (f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>{_html.escape(title)}</title></head>'
            f'<body style="margin:0;padding:0;background:#eef1f6">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f6">'
            f'<tr><td align="center" style="padding:24px 12px">'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">'
            f'<tr><td style="background:#13294b;border-radius:12px 12px 0 0;padding:18px 24px">{logo}</td></tr>'
            f'<tr><td style="background:#ffffff;border-radius:0 0 12px 12px;padding:24px;'
            f'font:15px/1.5 -apple-system,Segoe UI,Arial,sans-serif;color:#1d2733">'
            f'<h1 style="margin:0 0 14px;font-size:19px;color:#13294b">{_html.escape(title.replace("MoneyThistle: ", ""))}</h1>'
            f'{"".join(blocks)}</td></tr>'
            f'<tr><td style="padding:12px 8px;font:12px/1.4 Arial,sans-serif;color:#6b7a8c;text-align:center">'
            f'Sent by MoneyThistle, your household money app. It works on your home network, not from the internet.'
            f'</td></tr></table></td></tr></table></body></html>')

from .store import ApiError

CHANNELS = ("email", "pushover", "ntfy", "gotify")
SECRETS = {"email": ("password",), "pushover": ("app_token", "user_key"), "ntfy": ("token",), "gotify": ("token",)}
SERVER_KEYS = ("host", "port", "security", "username", "password", "from")   # what sharing the email server lends
DEFAULTS = {
    "hour": 8,                  # local time the daily summary goes out
    "due_days": 3,              # items due within this many days (0: none)
    "overdue": True, "statements": True, "auto_recorded": True, "below_zero": True, "backups": True,
    "auto_due": False,          # also remind of automatic items (autopay, direct deposit) coming due
    "email": {"enabled": False, "use_shared": False, "host": "", "port": 587, "security": "starttls",
              "username": "", "password": "", "from": "", "to": ""},
    "pushover": {"enabled": False, "app_token": "", "user_key": "", "device": ""},
    "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": "", "token": ""},
    "gotify": {"enabled": False, "server": "", "token": ""},
}
ADMIN = "admin"   # the administrators' setup (every environment; can share its email server)


def _https_or_local(url, what):
    """Web addresses for services: https, or http (a self-hosted server at home)."""
    p = urllib.parse.urlparse(url or "")
    if p.scheme not in ("https", "http") or not p.netloc:
        raise ApiError(f"{what} must be a web address like https://example.com")
    return url.rstrip("/")


class Notifier:
    def __init__(self, system, data_dir=None):
        self.system = system
        self.path = os.path.join(data_dir or system.data_dir, "notify.json")
        self.lock = threading.RLock()
        self.recorded = []   # automatic items recorded lately: [{env_id, payee, date, amount, at}]

    # ----- the file: {"admin": profile, "share_email": bool, "users": {id: profile}} ------
    def _raw(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        if "admin" not in raw and any(k in raw for k in DEFAULTS):
            # Older single setup: it becomes the administrators'.
            raw = {"admin": {k: v for k, v in raw.items() if k != "share_email"},
                   "share_email": bool(raw.get("share_email")), "users": {}}
        raw.setdefault("admin", {})
        raw.setdefault("users", {})
        return raw

    def _write(self, raw):
        with self.lock, open(self.path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=1)
        try:
            os.chmod(self.path, 0o600)   # secrets inside: owner only (where supported)
        except OSError:
            pass

    @staticmethod
    def _merged(saved):
        s = json.loads(json.dumps(DEFAULTS))
        for k, v in (saved or {}).items():
            if isinstance(v, dict) and isinstance(s.get(k), dict):
                s[k].update(v)
            elif k in s or k in ("last_sent", "last_sent_at"):
                s[k] = v
        return s

    def settings(self, who=ADMIN):
        raw = self._raw()
        return self._merged(raw["admin"] if who == ADMIN else raw["users"].get(str(who)))

    def shared_email(self):
        """The administrators' email server when they share it (else None)."""
        raw = self._raw()
        if not raw.get("share_email"):
            return None
        e = self._merged(raw["admin"])["email"]
        return {k: e[k] for k in SERVER_KEYS} if e.get("host") else None

    def public(self, who=ADMIN):
        """A setup for the page: secrets replaced by whether they're set."""
        s = self.settings(who)
        for ch, keys in SECRETS.items():
            for k in keys:
                s[ch][k + "_set"] = bool(s[ch].get(k))
                s[ch][k] = ""
        s["is_admin_setup"] = who == ADMIN
        s["share_email"] = bool(self._raw().get("share_email")) if who == ADMIN else None
        s["shared_email_available"] = who != ADMIN and self.shared_email() is not None
        s.pop("last_sent_at", None)
        return s

    def save(self, b, who=ADMIN):
        raw = self._raw()
        s = self.settings(who)
        if "hour" in b:
            h = int(b["hour"])
            if not 0 <= h <= 23:
                raise ApiError("The hour must be 0 to 23")
            s["hour"] = h
        if "due_days" in b:
            d = int(b["due_days"])
            if not 0 <= d <= 31:
                raise ApiError("Days ahead must be 0 to 31")
            s["due_days"] = d
        for k in ("overdue", "statements", "auto_recorded", "below_zero", "backups", "auto_due"):
            if k in b:
                s[k] = bool(b[k])
        for ch in CHANNELS:
            if not isinstance(b.get(ch), dict):
                continue
            cur = s[ch]
            for k, v in b[ch].items():
                if k not in DEFAULTS[ch]:
                    continue
                if k in SECRETS[ch] and v in ("", None):
                    continue   # left empty: keep what's saved
                cur[k] = bool(v) if k in ("enabled", "use_shared") else (int(v) if k == "port" else str(v).strip())
            if who == ADMIN:
                cur.pop("use_shared", None) if ch == "email" else None
            self._check(ch, cur, who)
        if who == ADMIN:
            if "share_email" in b:
                raw["share_email"] = bool(b["share_email"])
            raw["admin"] = s
        else:
            raw["users"][str(who)] = s
        self._write(raw)
        return self.public(who)

    def _check(self, ch, c, who):
        if not c.get("enabled"):
            return
        if ch == "email":
            if c.get("use_shared") and who != ADMIN:
                if self.shared_email() is None:
                    raise ApiError("No shared email server: an administrator has to share theirs first")
                if "@" not in (c.get("to") or ""):
                    raise ApiError("Enter the email address to send to")
                return
            if not c["host"] or not c["to"]:
                raise ApiError("Email needs the server (SMTP host) and who to send to")
            if c["security"] not in ("starttls", "ssl", "none"):
                raise ApiError("Email security must be STARTTLS, SSL or none")
            if not 1 <= int(c["port"]) <= 65535:
                raise ApiError("Email port must be 1-65535")
        elif ch == "pushover":
            if not c["app_token"] or not c["user_key"]:
                raise ApiError("Pushover needs the application token and your user key")
        elif ch == "ntfy":
            c["server"] = _https_or_local(c["server"] or "https://ntfy.sh", "The ntfy server")
            if not c["topic"] or "/" in c["topic"]:
                raise ApiError("ntfy needs a topic name (letters and numbers, no slashes)")
        elif ch == "gotify":
            c["server"] = _https_or_local(c["server"], "The Gotify server")
            if not c["token"]:
                raise ApiError("Gotify needs an application token")

    # ----- sending -----------------------------------------------------------------
    def send(self, title, body, channels=None, settings=None, who=ADMIN):
        """Send to every enabled channel of a setup (or the ones named). Returns
        {channel: "ok" or the error}."""
        s = settings or self.settings(who)
        out = {}
        for ch in channels or CHANNELS:
            c = dict(s[ch])
            if channels is None and not c.get("enabled"):
                continue
            try:
                if ch == "email" and c.get("use_shared"):
                    server = self.shared_email()
                    if not server:
                        raise ApiError("The shared email server isn't shared any more")
                    c.update(server)
                getattr(self, "_send_" + ch)(c, title, body)
                out[ch] = "ok"
            except ApiError as e:
                out[ch] = str(e)
            except Exception as e:   # network and server errors: reported, never raised
                out[ch] = f"{type(e).__name__}: {e}"
        return out

    # ----- messages to one person (password reset) ----------------------------------
    def mail_server(self):
        """The administrators' email server (Settings → Notifications), used for messages
        MoneyThistle itself sends to one person, such as a password reset link. None when
        there isn't one."""
        e = self.settings(ADMIN)["email"]
        return {k: e[k] for k in SERVER_KEYS} if e.get("host") else None

    def mail_to(self, to, title, body):
        server = self.mail_server()
        if not server or not to:
            raise ApiError("Email isn't set up")
        self._send_email(dict(server, to=to), title, body)

    def _post(self, url, data, headers=None):
        req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
        with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as r:
            if r.status >= 300:
                raise ApiError(f"The service answered {r.status}")

    def _send_email(self, c, title, body):
        if not c.get("host") or not c.get("to"):
            raise ApiError("Email isn't set up")
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = c.get("from") or c.get("username") or "moneythistle@localhost"
        msg["To"] = c["to"]
        # Plain text for every email app, and a dressed-up version (the wordmark on the
        # header band, links and buttons) for the ones that show it.
        msg.set_content(body)
        logo = _wordmark()
        cid = make_msgid(domain="moneythistle.local")
        msg.add_alternative(email_html(title, body, cid[1:-1] if logo else None), subtype="html")
        if logo:
            msg.get_payload()[1].add_related(logo, "image", "png", cid=cid, filename="moneythistle.png")
        port, sec = int(c.get("port") or 587), c.get("security", "starttls")
        ctx = ssl.create_default_context()
        if sec == "ssl":
            server = smtplib.SMTP_SSL(c["host"], port, timeout=20, context=ctx)
        else:
            server = smtplib.SMTP(c["host"], port, timeout=20)
        with server:
            if sec == "starttls":
                server.starttls(context=ctx)
            if c.get("username"):
                server.login(c["username"], c.get("password") or "")
            server.send_message(msg)

    def _send_pushover(self, c, title, body):
        if not c.get("app_token") or not c.get("user_key"):
            raise ApiError("Pushover isn't set up")
        form = {"token": c["app_token"], "user": c["user_key"], "title": title, "message": body[:1024]}
        if c.get("device"):
            form["device"] = c["device"]
        self._post("https://api.pushover.net/1/messages.json", urllib.parse.urlencode(form).encode())

    def _send_ntfy(self, c, title, body):
        if not c.get("topic"):
            raise ApiError("ntfy isn't set up")
        server = _https_or_local(c.get("server") or "https://ntfy.sh", "The ntfy server")
        h = {"Title": title.encode("ascii", "replace").decode(), "Tags": "moneybag"}
        if c.get("token"):
            h["Authorization"] = "Bearer " + c["token"]
        self._post(f"{server}/{urllib.parse.quote(c['topic'])}", body.encode("utf-8"), h)

    def _send_gotify(self, c, title, body):
        if not c.get("server") or not c.get("token"):
            raise ApiError("Gotify isn't set up")
        server = _https_or_local(c["server"], "The Gotify server")
        self._post(f"{server}/message", json.dumps({"title": title, "message": body, "priority": 5}).encode(),
                   {"Content-Type": "application/json", "X-Gotify-Key": c["token"]})

    # ----- the daily summary -------------------------------------------------------
    def note_recorded(self, done):
        """Automatic items System.enter_automatic just recorded (for the next summaries)."""
        now = time.time()
        with self.lock:
            self.recorded = [r for r in self.recorded if now - r["at"] < 3 * 86400] + \
                [dict(d, at=now) for d in done[:200]]

    def _env_ids(self, who):
        if who == ADMIN:
            return [e["id"] for e in self.system.q("SELECT id FROM environments ORDER BY id")]
        return [r["env_id"] for r in self.system.q("SELECT env_id FROM members WHERE user_id=? ORDER BY env_id", (int(who),))]

    def summary(self, s=None, who=ADMIN):
        """The summary text for a setup's environments (empty when there's nothing to say)."""
        s = s or self.settings(who)
        money = lambda c: f"${abs(c) / 100:,.2f}" if c >= 0 else f"-${abs(c) / 100:,.2f}"
        today = dt.date.today()
        since = s.get("last_sent_at") or 0
        parts = []
        env_ids = self._env_ids(who)
        seen = set()      # (environment, item, date): each item once, however it's reached
        for eid in env_ids:
            name = (self.system.q1("SELECT name FROM environments WHERE id=?", (eid,)) or {}).get("name", "?")
            st = self.system.store(eid)
            lines = []
            # What needs the person: automatic items (autopay, direct deposit) happen by themselves,
            # so they're left out unless the person asked for them too (auto_due). A deposit into
            # more than one account: once, at its total.
            wanted = lambda u: s.get("auto_due") or not u.get("auto")   # noqa: E731
            up = [dict(u, amount=u.get("split_total") or u["amount"]) for u in st.upcoming(max(s["due_days"], 0))
                  if u["first"] and not u.get("split_of") and wanted(u)]
            if who != ADMIN:
                # Items of accounts shared into this environment with their bills, kept elsewhere.
                try:
                    for u in self.system.incoming_bills(int(who), eid, max(s["due_days"], 0)):
                        if u["first"] and not u.get("split_of") and wanted(u) and u["share_env_id"] not in env_ids:
                            up.append(dict(u, amount=u.get("split_total") or u["amount"], _env=u["share_env_id"],
                                           account_name=f"{u['account_name']}, shared"))
                except Exception:
                    pass
            up = [u for u in up if (u.get("_env", eid), u["id"], u["date"]) not in seen]
            seen.update((u.get("_env", eid), u["id"], u["date"]) for u in up)
            up.sort(key=lambda u: (u["date"], u.get("payee") or ""))
            if s["overdue"]:
                for u in (u for u in up if u["overdue"]):
                    lines.append(f"OVERDUE {u['date']}: {u['payee'] or u['kind']} {money(u['amount'])} ({u['account_name']})")
            if s["due_days"]:
                for u in (u for u in up if not u["overdue"]):
                    when = "today" if u["date"] == today.isoformat() else u["date"]
                    lines.append(f"Due {when}: {u['payee'] or u['kind']} {money(u['amount'])}"
                                 f"{' (automatic)' if u.get('auto') else ''} ({u['account_name']})")
            if s["statements"]:
                for d in st.statements_due():
                    if d.get("kind") == "value":
                        lines.append(f"Update the {d['name']} value (last updated {d['last_date']})")
                    else:
                        lines.append(f"Enter the {d['name']} statement (closed {d['closing_date']})")
            if s["auto_recorded"]:
                with self.lock:
                    mine = [r for r in self.recorded if r.get("env_id") == eid and r["at"] > since]
                for r in mine:
                    lines.append(f"Recorded for you: {r['payee']} {money(r['amount'])} on {r['date']}")
            if s["below_zero"]:
                try:
                    for a in st.forecast(14)["accounts"]:
                        if a["low"] < 0 <= a["now"] and not a["liability"]:
                            lines.append(f"{a['name']} is forecast to go below zero ({money(a['low'])} on {a['low_date']})")
                except Exception:
                    pass
            if lines:
                parts.append((name, lines))
        if s["backups"] and who == ADMIN:
            try:
                last = self.system.backup_status().get("last")
                if last and not last.get("ok"):
                    parts.append(("Backups", [f"The last backup failed: {last.get('message') or 'see Backups'}"]))
            except Exception:
                pass
        if not parts:
            return ""
        if len(parts) == 1:
            return "\n".join(parts[0][1])
        return "\n\n".join(f"{name}:\n" + "\n".join(lines) for name, lines in parts)

    def tick(self, now=None):
        """Called every minute: each setup gets its summary once a day, at its hour.
        Returns {who: result} for the setups sent to."""
        now = now or dt.datetime.now()
        raw = self._raw()
        sent = {}
        people = [(ADMIN, raw["admin"])] + [(uid, p) for uid, p in raw["users"].items()]
        for who, saved in people:
            s = self._merged(saved)
            if not any(s[ch].get("enabled") for ch in CHANNELS):
                continue
            if now.hour < s["hour"] or s.get("last_sent") == now.date().isoformat():
                continue
            if who != ADMIN and not self.system.q1("SELECT 1 FROM users WHERE id=?", (int(who),)):
                continue   # that person was removed
            text = self.summary(s, who)
            sent[who] = self.send("MoneyThistle: today", text, settings=s) if text else {}
            saved["last_sent"] = now.date().isoformat()
            saved["last_sent_at"] = time.time()
        if sent:
            self._write(raw)
        return sent
