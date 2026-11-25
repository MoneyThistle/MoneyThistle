"""People, environments and the connections between them.

- Every person signs in with their own user name and password.
- An environment is a separate money file (its own accounts, categories, bills,
  budget). People are members of an environment as owner, editor or viewer;
  someone who isn't a member can't see anything in it.
- A connection links one account in one environment with one account in another,
  so money can be transferred between them. It is proposed by an owner of one side
  and only works after an owner of the other side approves it (and picks the
  account). Either side's owner can end it.

All of this lives in system.db next to the money files. The first environment keeps
the original money file (money.db), so existing data simply becomes "Personal".
"""

import base64
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
import zipfile

from .store import ApiError, Store, db_bytes, to_cents

ROLES = {"viewer": 1, "editor": 2, "owner": 3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL DEFAULT '',
    pw_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    ui_json TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS environments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    file TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    env_id INTEGER NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    PRIMARY KEY (env_id, user_id)
);
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY,
    env_a INTEGER NOT NULL, account_a INTEGER NOT NULL,
    env_b INTEGER NOT NULL, account_b INTEGER,
    status TEXT NOT NULL,            -- pending | active | declined | ended
    created_by INTEGER, created TEXT NOT NULL,
    approved_a_by INTEGER, approved_b_by INTEGER, approved TEXT,
    ended_by INTEGER, ended TEXT,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS shares (
    id INTEGER PRIMARY KEY,
    env_a INTEGER NOT NULL, account_a INTEGER NOT NULL,   -- where the account lives
    env_b INTEGER NOT NULL,                               -- where it also shows up
    access TEXT NOT NULL,            -- view | edit
    include_bills INTEGER NOT NULL DEFAULT 0,   -- also share its bills & deposits
    status TEXT NOT NULL,            -- pending | active | declined | ended
    created_by INTEGER, created TEXT NOT NULL,
    approved_by INTEGER, approved TEXT,
    ended_by INTEGER, ended TEXT,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS backup_log (
    id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, destination TEXT NOT NULL,
    name TEXT NOT NULL, ok INTEGER NOT NULL, message TEXT NOT NULL DEFAULT ''
);
"""

SESSION_DAYS = 30
IDLE_MINUTES = 60      # a sign-in not kept on the device ends after this long unused
PBKDF2_ROUNDS = 200_000


def hash_password(pw):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def check_password(pw, stored):
    try:
        _, rounds, salt, dk = stored.split("$")
        got = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(got, base64.b64decode(dk))
    except Exception:
        return False


def _now():
    return dt.datetime.now().isoformat(timespec="seconds")


def backup_version(z):
    """The MoneyThistle version that made a backup zip (None for backups older than 1.0.0)."""
    try:
        return json.loads(z.read("moneythistle-backup.json")).get("version")
    except Exception:
        return None


class System:
    def __init__(self, data_dir):
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(os.path.join(self.data_dir, "envs"), exist_ok=True)
        self.path = os.path.join(self.data_dir, "system.db")
        self.lock = threading.RLock()
        self.stores = {}
        self._auto_ran = {}   # environment -> when automatic items were last recorded
        self._dirty = None
        self._last = None
        self._fail = {}  # sign-in failures per address
        self._open()

    # ----- files ----------------------------------------------------------
    def _open(self):
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        share_cols = {r[1] for r in self.db.execute("PRAGMA table_info(shares)")}
        if "include_bills" not in share_cols:
            self.db.execute("ALTER TABLE shares ADD COLUMN include_bills INTEGER NOT NULL DEFAULT 0")
        if "target_user_id" not in share_cols:
            # Shares go to a person, who picks the environment (env_b = 0 until then).
            self.db.execute("ALTER TABLE shares ADD COLUMN target_user_id INTEGER")
        if "remember" not in {r[1] for r in self.db.execute("PRAGMA table_info(sessions)")}:
            # "Keep me signed in on this device" (30 days); otherwise a sign-in ends when the
            # browser closes or after IDLE_MINUTES without use. Earlier sign-ins were kept.
            self.db.execute("ALTER TABLE sessions ADD COLUMN remember INTEGER NOT NULL DEFAULT 1")
            self.db.execute("ALTER TABLE sessions ADD COLUMN last_used REAL")
        if "email" not in {r[1] for r in self.db.execute("PRAGMA table_info(users)")}:
            # Where "forgot my password" links (and notices of a changed password) go.
            self.db.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
        from . import history
        history.setup(self.db)   # the change history (who changed what)
        # Links that let someone who forgot their password set a new one: only the hash
        # of each is kept; each works once, for a short time.
        self.db.execute("CREATE TABLE IF NOT EXISTS password_resets (token_hash TEXT PRIMARY KEY, "
                        "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
                        "created REAL NOT NULL, expires REAL NOT NULL)")
        # Choices an administrator makes for everyone on this MoneyThistle (key -> text).
        self.db.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if not self.q1("SELECT 1 FROM environments"):
            # The money file that existed before environments becomes "Personal".
            self.db.execute("INSERT INTO environments(name,file,created) VALUES('Personal','money.db',?)", (_now(),))
        self.db.commit()

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def q1(self, sql, args=()):
        with self.lock:
            r = self.db.execute(sql, args).fetchone()
            return dict(r) if r else None

    def exec(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            self.changed()
            return cur.lastrowid

    def store(self, env_id):
        with self.lock:
            st = self.stores.get(env_id)
            if st:
                return st
            env = self.q1("SELECT * FROM environments WHERE id=?", (env_id,))
            if not env:
                raise ApiError("No such environment", 404)
            st = Store(os.path.join(self.data_dir, env["file"]))
            # One lock for the people file and every money file. Two locks taken in opposite
            # orders by two threads (a backup reading everything while an entry is saved and
            # its change recorded) waited for each other forever, and every page hung.
            st.lock = self.lock
            from . import history
            # Its changes go into the change history, under this environment.
            st.audit = lambda kind, oid, action, before, after, summary, _e=env_id: \
                history.record(self, _e, kind, oid, action, before, after, summary)
            self.stores[env_id] = st
            return st

    def close(self):
        with self.lock:
            for st in self.stores.values():
                st.close()
            self.stores = {}
            self.db.close()

    # Change tracking across every money file, for "back up after changes".
    def changed(self):
        now = time.time()
        if self._dirty is None:
            self._dirty = now
        self._last = now

    @property
    def dirty_since(self):
        ds = [self._dirty] + [s.dirty_since for s in list(self.stores.values())]
        ds = [d for d in ds if d is not None]
        return min(ds) if ds else None

    @dirty_since.setter
    def dirty_since(self, value):
        self._dirty = value
        for s in list(self.stores.values()):
            s.dirty_since = value

    @property
    def last_change(self):
        ls = [self._last] + [s.last_change for s in list(self.stores.values())]
        ls = [x for x in ls if x is not None]
        return max(ls) if ls else None

    # ----- backups of everything --------------------------------------------
    def snapshot_bytes(self, compress=True):
        """One zip with system.db and every environment's money file."""
        from . import attachments
        # The money files are copied in one go (a consistent moment); the attached files,
        # which never change once written, are read afterwards without holding anything up.
        with self.lock:
            if self.db.in_transaction:   # (see Store.snapshot_bytes)
                self.db.commit()
            files = [("system.db", db_bytes(self.db))]
            for env in self.q("SELECT * FROM environments"):
                files.append((env["file"], self.store(env["id"]).snapshot_bytes()))
            shas = sorted(attachments.in_use(self))
        buf = io.BytesIO()
        method = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
        with zipfile.ZipFile(buf, "w", method) as z:
            for name, data in files:
                z.writestr(name, data)
            # Receipts and other attached files (photos and PDFs are compressed already).
            n_att = 0
            for sha in shas:
                p = attachments.path_for(self.data_dir, sha)
                if os.path.exists(p):
                    z.write(p, "attachments/" + sha, compress_type=zipfile.ZIP_STORED)
                    n_att += 1
            from .version import VERSION
            z.writestr("moneythistle-backup.json", json.dumps({"format": 2, "made": _now(), "attachments": n_att,
                                                               "version": VERSION}))
        return buf.getvalue()

    @staticmethod
    def backup_info(data):
        """What a (decrypted) backup says about itself: version that made it, when, attachments."""
        if data[:2] != b"PK":
            return {}
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return json.loads(z.read("moneythistle-backup.json"))
        except Exception:
            return {}

    def restore_bytes(self, data):
        """Put a backup back: a zip of everything, or (older backups) one money file,
        which then replaces the Personal environment."""
        with self.lock:
            if data[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    names = z.namelist()
                    if "system.db" not in names:
                        raise ApiError("That zip is not a MoneyThistle backup")
                    # A restore puts back the data, not the program: this version must be at least
                    # as new as the one that made the backup (newer ones read older data fine).
                    made_by = backup_version(z)
                    from .version import VERSION, newer
                    if made_by and newer(made_by, VERSION):
                        raise ApiError(f"This backup was made by MoneyThistle {made_by}, newer than this one ({VERSION}). "
                                       f"Update MoneyThistle to {made_by} or later first, then restore it.")
                    files = {n: z.read(n) for n in names if n.endswith(".db")}
                    from . import attachments
                    att = [n for n in names if n.startswith("attachments/")
                           and attachments.SHA_RE.match(n.split("/", 1)[1])]
                    for n, b in files.items():
                        if not b.startswith(b"SQLite format 3\x00") or ".." in n or n.startswith(("/", "\\")):
                            raise ApiError("That backup could not be read")
                    # Attached files come back too (ones already here are the same file:
                    # each is named by its own SHA-256).
                    for n in att:
                        p = attachments.path_for(self.data_dir, n.split("/", 1)[1])
                        if not os.path.exists(p):
                            self._write_atomic(p, z.read(n))
                self.close()
                for n, b in files.items():
                    self._write_atomic(os.path.join(self.data_dir, n), b)
                self._open()
            elif data.startswith(b"SQLite format 3\x00"):
                first = self.q1("SELECT * FROM environments ORDER BY id LIMIT 1")
                st = self.store(first["id"])
                with st.lock:
                    st.close()
                    self._write_atomic(st.path, data)
                    st.reopen()
            else:
                raise ApiError("That file is not a backup from this app")
            self.dirty_since = None

    def _write_atomic(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def log_backup(self, kind, destination, name, ok, message=""):
        with self.lock:
            self.db.execute("INSERT INTO backup_log(at,kind,destination,name,ok,message) VALUES(?,?,?,?,?,?)",
                            (_now(), kind, destination, name, int(ok), message[:500]))
            self.db.execute("DELETE FROM backup_log WHERE id NOT IN (SELECT id FROM backup_log ORDER BY id DESC LIMIT 200)")
            self.db.commit()

    def backup_log(self, n=30):
        return self.q("SELECT * FROM backup_log ORDER BY id DESC LIMIT ?", (n,))

    def backup_status(self):
        return {"last_ok": self.q1("SELECT * FROM backup_log WHERE ok=1 ORDER BY id DESC LIMIT 1"),
                "last": self.q1("SELECT * FROM backup_log ORDER BY id DESC LIMIT 1"),
                "pending_changes": self.dirty_since is not None}

    # ----- people -----------------------------------------------------------
    def has_users(self):
        return bool(self.q1("SELECT 1 FROM users"))

    def _check_new_user(self, username, password):
        if not re.fullmatch(r"[A-Za-z0-9._@-]{2,40}", username or ""):
            raise ApiError("User names are 2-40 letters, numbers or . _ @ -")
        if len(password or "") < 8:
            raise ApiError("Passwords need at least 8 characters")

    def create_user(self, username, password, display_name="", is_admin=False, detail="simple"):
        self._check_new_user(username, password)
        if self.q1("SELECT 1 FROM users WHERE username=?", (username,)):
            raise ApiError("That user name is taken")
        with self.lock:
            first = not self.has_users()
            # New sign-ins start Simple (extras folded away); "full" shows everything.
            ui = json.dumps({"detail": "full" if detail == "full" else "simple"})
            uid = self.db.execute("INSERT INTO users(username,display_name,pw_hash,is_admin,created,ui_json) "
                                  "VALUES(?,?,?,?,?,?)",
                                  (username, display_name or username, hash_password(password),
                                   int(is_admin or first), _now(), ui)).lastrowid
            if first:
                # The first person owns every environment that has no owner yet (the
                # existing money file).
                for env in self.q("SELECT id FROM environments"):
                    self.db.execute("INSERT OR IGNORE INTO members(env_id,user_id,role) VALUES(?,?,'owner')",
                                    (env["id"], uid))
            self.db.commit()
            self.changed()
        return uid

    def users(self):
        return self.q("SELECT id, username, display_name, email, is_admin, created FROM users ORDER BY username")

    def user(self, uid):
        return self.q1("SELECT id, username, display_name, email, is_admin, ui_json FROM users WHERE id=?", (uid,))

    @staticmethod
    def clean_email(v):
        v = (v or "").strip()
        if v and (len(v) > 200 or not re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", v)):
            raise ApiError("That doesn't look like an email address", field="email")
        return v

    def set_password(self, uid, password):
        """A new password: every sign-in of that person ends, and unused reset links stop working."""
        if len(password or "") < 8:
            raise ApiError("Passwords need at least 8 characters", field="password")
        with self.lock:
            self.db.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_password(password), uid))
            self.db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            self.db.execute("DELETE FROM password_resets WHERE user_id=?", (uid,))
            self.db.commit()
            self.changed()

    def update_user(self, uid, data, by_admin):
        u = self.user(uid)
        if not u:
            raise ApiError("No such person", 404)
        if "display_name" in data:
            self.exec("UPDATE users SET display_name=? WHERE id=?", ((data["display_name"] or u["username"]).strip(), uid))
        if "email" in data:
            self.exec("UPDATE users SET email=? WHERE id=?", (self.clean_email(data["email"]), uid))
        if data.get("password"):
            self.set_password(uid, data["password"])
        if by_admin and "is_admin" in data:
            if not data["is_admin"] and u["is_admin"] and \
                    self.q1("SELECT COUNT(*) n FROM users WHERE is_admin=1")["n"] <= 1:
                raise ApiError("Someone has to stay an administrator")
            self.exec("UPDATE users SET is_admin=? WHERE id=?", (int(bool(data["is_admin"])), uid))

    def delete_user(self, uid):
        u = self.user(uid)
        if not u:
            raise ApiError("No such person", 404)
        if u["is_admin"] and self.q1("SELECT COUNT(*) n FROM users WHERE is_admin=1")["n"] <= 1:
            raise ApiError("Someone has to stay an administrator")
        for env in self.q("SELECT env_id FROM members WHERE user_id=? AND role='owner'", (uid,)):
            if self.q1("SELECT COUNT(*) n FROM members WHERE env_id=? AND role='owner'", (env["env_id"],))["n"] <= 1:
                name = self.q1("SELECT name FROM environments WHERE id=?", (env["env_id"],))["name"]
                raise ApiError(f"Give \"{name}\" another owner first")
        self.exec("DELETE FROM users WHERE id=?", (uid,))

    # ----- forgotten passwords ------------------------------------------------------
    RESET_MINUTES = 30

    def start_reset(self, username):
        """A one-time link token for someone who forgot their password: (user, token), or
        None when there's no such person, they have no email address, or they've asked
        three times in the last hour."""
        u = self.q1("SELECT id, username, display_name, email FROM users WHERE username=?", ((username or "").strip(),))
        if not u or not u["email"]:
            return None
        now = time.time()
        with self.lock:
            self.db.execute("DELETE FROM password_resets WHERE expires < ?", (now,))
            if self.q1("SELECT COUNT(*) n FROM password_resets WHERE user_id=? AND created > ?",
                       (u["id"], now - 3600))["n"] >= 3:
                return None
            token = secrets.token_urlsafe(32)
            self.db.execute("INSERT INTO password_resets(token_hash,user_id,created,expires) VALUES(?,?,?,?)",
                            (self._th(token), u["id"], now, now + self.RESET_MINUTES * 60))
            self.db.commit()
        return u, token

    def reset_user(self, token):
        """Who a reset link is for (None when it's unknown, used or expired)."""
        r = self.q1("SELECT u.id, u.username, u.display_name, u.email FROM password_resets p "
                    "JOIN users u ON u.id=p.user_id WHERE p.token_hash=? AND p.expires>?",
                    (self._th(token or ""), time.time()))
        return r

    def finish_reset(self, token, password):
        u = self.reset_user(token)
        if not u:
            raise ApiError("This link has expired or was already used. Ask for a new one from the sign-in page.", 400)
        self.set_password(u["id"], password)
        return u

    def app_setting(self, key, default=None):
        r = self.q1("SELECT value FROM app_settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_app_setting(self, key, value):
        self.exec("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, str(value)))

    def ui_settings(self, uid):
        u = self.user(uid)
        try:
            return json.loads(u["ui_json"] or "{}")
        except ValueError:
            return {}

    def save_ui_settings(self, uid, s):
        self.exec("UPDATE users SET ui_json=? WHERE id=?", (json.dumps(s), uid))

    # ----- signing in -----------------------------------------------------------
    def login(self, username, password, addr="?", remember=True):
        fails = [t for t in self._fail.get(addr, []) if time.time() - t < 600]
        if len(fails) >= 10:
            raise ApiError("Too many tries. Wait a few minutes.", 429)
        u = self.q1("SELECT * FROM users WHERE username=?", (username or "",))
        if not u or not check_password(password or "", u["pw_hash"]):
            fails.append(time.time())
            self._fail[addr] = fails
            time.sleep(0.5)
            raise ApiError("Wrong user name or password", 401)
        self._fail.pop(addr, None)
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            self.db.execute("INSERT INTO sessions(token_hash,user_id,created,expires,remember,last_used) "
                            "VALUES(?,?,?,?,?,?)", (self._th(token), u["id"], time.time(),
                                                    time.time() + SESSION_DAYS * 86400, int(bool(remember)), time.time()))
            self.db.commit()
        return token, u["id"]

    def _th(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    def session_user(self, token):
        if not token:
            return None
        now = time.time()
        s = self.q1("SELECT * FROM sessions WHERE token_hash=? AND expires > ?", (self._th(token), now))
        if not s:
            return None
        if not s.get("remember", 1):
            # Not kept on this device: it ends after a while without use, wherever the
            # browser restored it from (browsers that reopen their tabs keep its cookie).
            last = s.get("last_used") or s["created"]
            if now - last > IDLE_MINUTES * 60:
                self.logout(token)
                return None
            if now - last > 60:
                with self.lock:
                    self.db.execute("UPDATE sessions SET last_used=? WHERE token_hash=?", (now, s["token_hash"]))
                    self.db.commit()
        return self.user(s["user_id"])

    def logout(self, token):
        with self.lock:
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (self._th(token or ""),))
            self.db.commit()

    # ----- environments ---------------------------------------------------------
    def role(self, uid, env_id):
        r = self.q1("SELECT role FROM members WHERE env_id=? AND user_id=?", (env_id, uid))
        return r["role"] if r else None

    def require(self, uid, env_id, need):
        r = self.role(uid, env_id)
        if not r:
            raise ApiError("You don't have access to that environment", 403)
        if ROLES[r] < ROLES[need]:
            raise ApiError({"editor": "You can look but not change things here",
                            "owner": "Only an owner of this environment can do that"}[need], 403)
        return r

    def my_envs(self, uid):
        rows = self.q("SELECT e.id, e.name, m.role FROM environments e JOIN members m ON m.env_id=e.id "
                      "WHERE m.user_id=? ORDER BY e.id", (uid,))
        for r in rows:
            r["members"] = self.q("SELECT u.id, u.username, u.display_name, m.role FROM members m "
                                  "JOIN users u ON u.id=m.user_id WHERE m.env_id=? ORDER BY u.username", (r["id"],))
        return rows

    def all_env_names(self):
        return self.q("SELECT id, name FROM environments ORDER BY name")

    def create_env(self, uid, name):
        name = (name or "").strip()
        if not name:
            raise ApiError("Give the environment a name")
        with self.lock:
            eid = self.db.execute("INSERT INTO environments(name,file,created) VALUES(?,?,?)",
                                  (name, "pending", _now())).lastrowid
            self.db.execute("UPDATE environments SET file=? WHERE id=?", (f"envs/env-{eid}.db", eid))
            self.db.execute("INSERT INTO members(env_id,user_id,role) VALUES(?,?,'owner')", (eid, uid))
            self.db.commit()
            self.changed()
        self.store(eid)
        return eid

    def rename_env(self, env_id, name):
        if not (name or "").strip():
            raise ApiError("Give the environment a name")
        self.exec("UPDATE environments SET name=? WHERE id=?", (name.strip(), env_id))

    def delete_env(self, env_id):
        if self.q1("SELECT COUNT(*) n FROM environments")["n"] <= 1:
            raise ApiError("Keep at least one environment")
        env = self.q1("SELECT * FROM environments WHERE id=?", (env_id,))
        st = self.store(env_id)
        if st.accounts():
            raise ApiError("Delete or move its accounts first; this can't be undone")
        with self.lock:
            st.close()
            self.stores.pop(env_id, None)
            self.db.execute("UPDATE links SET status='ended', ended=? WHERE (env_a=? OR env_b=?) AND status IN ('pending','active')",
                            (_now(), env_id, env_id))
            self.db.execute("UPDATE shares SET status='ended', ended=? WHERE (env_a=? OR env_b=?) AND status IN ('pending','active')",
                            (_now(), env_id, env_id))
            self.db.execute("DELETE FROM environments WHERE id=?", (env_id,))
            self.db.commit()
            self.changed()
        try:
            os.replace(os.path.join(self.data_dir, env["file"]), os.path.join(self.data_dir, env["file"] + ".deleted"))
        except OSError:
            pass

    def reset_env(self, env_id):
        """Start an environment over, as if new: an empty money file with the starting
        categories takes the place of the one there, which is kept beside it in the data folder
        (renamed "<file>.before-reset-<date-time>"), never deleted. Its connections and shares
        with other environments end and its change history goes. People, sign-ins, access,
        backup settings, other environments and the main currency stay as they are."""
        env = self.q1("SELECT * FROM environments WHERE id=?", (env_id,))
        if not env:
            raise ApiError("No such environment", 404)
        home = self.store(env_id).money_settings()["home"]
        with self.lock:
            st = self.stores.pop(env_id, None)
            if st:
                st.close()
            self.db.execute("UPDATE links SET status='ended', ended=? WHERE (env_a=? OR env_b=?) AND status IN ('pending','active')",
                            (_now(), env_id, env_id))
            self.db.execute("UPDATE shares SET status='ended', ended=? WHERE (env_a=? OR env_b=?) AND status IN ('pending','active')",
                            (_now(), env_id, env_id))
            try:
                self.db.execute("DELETE FROM changes WHERE env_id=?", (env_id,))
            except sqlite3.OperationalError:
                pass   # (no change history yet)
            self.db.commit()
            src = os.path.join(self.data_dir, env["file"])
            kept = src + ".before-reset-" + time.strftime("%Y%m%d-%H%M%S")
            for ext in ("", "-wal", "-shm"):
                if os.path.exists(src + ext):
                    os.replace(src + ext, kept + ext)
            st = self.store(env_id)   # a new file, with the starting categories
            if home != st.money_settings()["home"]:
                st.set_money_settings({"home": home})
            self.changed()
        return {"kept": os.path.basename(kept)}

    def set_member(self, env_id, username, role):
        if role not in ROLES:
            raise ApiError("Role must be owner, editor or viewer")
        u = self.q1("SELECT id FROM users WHERE username=?", ((username or "").strip(),))
        if not u:
            raise ApiError("No one has that user name. An administrator can add them under People.")
        cur = self.role(u["id"], env_id)
        if cur == "owner" and role != "owner" and self._owner_count(env_id) <= 1:
            raise ApiError("An environment needs at least one owner")
        self.exec("INSERT INTO members(env_id,user_id,role) VALUES(?,?,?) "
                  "ON CONFLICT(env_id,user_id) DO UPDATE SET role=excluded.role", (env_id, u["id"], role))

    def remove_member(self, env_id, user_id):
        if self.role(user_id, env_id) == "owner" and self._owner_count(env_id) <= 1:
            raise ApiError("An environment needs at least one owner")
        self.exec("DELETE FROM members WHERE env_id=? AND user_id=?", (env_id, user_id))

    def _owner_count(self, env_id):
        return self.q1("SELECT COUNT(*) n FROM members WHERE env_id=? AND role='owner'", (env_id,))["n"]

    def env_name(self, env_id):
        """The environment's name; when another environment has the same name (two
        people's "Personal"), its owner's name is added: "Personal · Alex"."""
        r = self.q1("SELECT name FROM environments WHERE id=?", (env_id,))
        if not r:
            return "?"
        if self.q1("SELECT COUNT(*) n FROM environments WHERE name=? COLLATE NOCASE", (r["name"],))["n"] > 1:
            o = self.q1("SELECT u.display_name FROM members m JOIN users u ON u.id=m.user_id "
                        "WHERE m.env_id=? AND m.role='owner' ORDER BY m.rowid LIMIT 1", (env_id,))
            if o:
                return f"{r['name']} · {o['display_name']}"
        return r["name"]

    def account_name(self, env_id, account_id):
        if not account_id:
            return None
        try:
            r = self.store(env_id).q1("SELECT name FROM accounts WHERE id=?", (account_id,))
        except ApiError:
            return None
        return r["name"] if r else None

    # ----- connections between environments ----------------------------------------
    def _link_view(self, l, uid):
        a_role, b_role = self.role(uid, l["env_a"]), self.role(uid, l["env_b"])
        names = {u["id"]: u["display_name"] for u in self.users()}
        if (l.get("note") or "").startswith("via-share:"):
            l = {**l, "note": "made through a shared account (ends when the share ends)"}
        return {**l, "env_a_name": self.env_name(l["env_a"]), "env_b_name": self.env_name(l["env_b"]),
                "account_a_name": self.account_name(l["env_a"], l["account_a"]),
                "account_b_name": self.account_name(l["env_b"], l["account_b"]),
                "created_by_name": names.get(l["created_by"]), "approved_b_name": names.get(l["approved_b_by"]),
                "i_own_a": a_role == "owner", "i_own_b": b_role == "owner",
                "can_approve": l["status"] == "pending" and b_role == "owner",
                "can_end": l["status"] in ("pending", "active") and "owner" in (a_role, b_role)}

    def links_for(self, uid):
        mine = [e["id"] for e in self.my_envs(uid) if e["role"] == "owner"]
        if not mine:
            return []
        marks = ",".join("?" * len(mine))
        rows = self.q(f"SELECT * FROM links WHERE env_a IN ({marks}) OR env_b IN ({marks}) ORDER BY id DESC", mine + mine)
        return [self._link_view(l, uid) for l in rows]

    def request_link(self, uid, env_a, account_a, env_b, account_b=None, note=""):
        self.require(uid, env_a, "owner")
        env_a, env_b, account_a = int(env_a), int(env_b), int(account_a)
        if env_a == env_b:
            raise ApiError("Accounts in the same environment can already transfer to each other")
        if not self.q1("SELECT 1 FROM environments WHERE id=?", (env_b,)):
            raise ApiError("No such environment")
        if not self.account_name(env_a, account_a):
            raise ApiError("Choose one of your accounts")
        if account_b:
            # Only someone who can see the other environment may pick its account.
            self.require(uid, env_b, "viewer")
            if not self.account_name(env_b, int(account_b)):
                raise ApiError("No such account in the other environment")
        if self.q1("SELECT 1 FROM links WHERE status IN ('pending','active') AND ((env_a=? AND account_a=? AND env_b=?) "
                   "OR (env_b=? AND account_b=? AND env_a=?))", (env_a, account_a, env_b, env_a, account_a, env_b)):
            raise ApiError("That account already has a connection (or a request) to that environment")
        lid = self.exec("INSERT INTO links(env_a,account_a,env_b,account_b,status,created_by,created,approved_a_by,note) "
                        "VALUES(?,?,?,?,'pending',?,?,?,?)",
                        (env_a, account_a, env_b, int(account_b) if account_b else None, uid, _now(), uid,
                         (note or "")[:300]))
        return lid

    def approve_link(self, uid, lid, account_b=None):
        l = self.q1("SELECT * FROM links WHERE id=?", (lid,))
        if not l or l["status"] != "pending":
            raise ApiError("That request isn't waiting for approval", 404)
        self.require(uid, l["env_b"], "owner")
        acct = int(account_b or l["account_b"] or 0)
        if not self.account_name(l["env_b"], acct):
            raise ApiError("Choose which of your accounts to connect")
        self.exec("UPDATE links SET status='active', account_b=?, approved_b_by=?, approved=? WHERE id=?",
                  (acct, uid, _now(), lid))

    def decline_link(self, uid, lid):
        l = self.q1("SELECT * FROM links WHERE id=?", (lid,))
        if not l or l["status"] != "pending":
            raise ApiError("That request isn't waiting", 404)
        if "owner" not in (self.role(uid, l["env_a"]), self.role(uid, l["env_b"])):
            raise ApiError("Only an owner of either side can do that", 403)
        self.exec("UPDATE links SET status='declined', ended_by=?, ended=? WHERE id=?", (uid, _now(), lid))

    def end_link(self, uid, lid):
        """End a connection. Transfers already made stay in both registers, as plain
        entries that are no longer tied together."""
        l = self.q1("SELECT * FROM links WHERE id=?", (lid,))
        if not l or l["status"] not in ("pending", "active"):
            raise ApiError("That connection isn't active", 404)
        if "owner" not in (self.role(uid, l["env_a"]), self.role(uid, l["env_b"])):
            raise ApiError("Only an owner of either side can do that", 403)
        self._end_link_now(uid, lid)

    def _end_link_now(self, uid, lid):
        l = self.q1("SELECT * FROM links WHERE id=?", (lid,))
        for env in (l["env_a"], l["env_b"]):
            st = self.store(env)
            with st.lock:
                # Scheduled transfers through it stop (they can't be recorded any more).
                st.db.execute("UPDATE bills SET active=0 WHERE x_link_id=?", (lid,))
                st.db.commit()
            st = self.store(env)
            with st.lock:
                st.db.execute("UPDATE transactions SET memo = CASE WHEN memo='' THEN ? ELSE memo || ' · ' || ? END, "
                              "xlink_id=NULL, xtx_id=NULL WHERE xlink_id=?",
                              ("transfer between environments", "transfer between environments", lid))
                st.db.commit()
                st.changed()
        self.exec("UPDATE links SET status='ended', ended_by=?, ended=? WHERE id=?", (uid, _now(), lid))

    def usable_links(self, env_id, account_id):
        """Active connections from this account: where money can go."""
        rows = self.q("SELECT * FROM links WHERE status='active' AND ((env_a=? AND account_a=?) OR (env_b=? AND account_b=?))",
                      (env_id, account_id, env_id, account_id))
        out = []
        for l in rows:
            other_env, other_acct = (l["env_b"], l["account_b"]) if l["env_a"] == env_id else (l["env_a"], l["account_a"])
            out.append({"link_id": l["id"], "env_id": other_env, "env_name": self.env_name(other_env),
                        "account_id": other_acct, "account_name": self.account_name(other_env, other_acct)})
        return out

    def link_other_side(self, lid, env_id, account_id):
        l = self.q1("SELECT * FROM links WHERE id=? AND status='active'", (lid,))
        if not l:
            raise ApiError("That connection isn't active")
        if (l["env_a"], l["account_a"]) == (env_id, account_id):
            return l["env_b"], l["account_b"]
        if (l["env_b"], l["account_b"]) == (env_id, account_id):
            return l["env_a"], l["account_a"]
        raise ApiError("That connection doesn't belong to this account")

    # ----- accounts shared into another environment ------------------------------------
    # The account stays in its own environment (one register, one balance); the other
    # environment's members see it in their account list and can open its register:
    # read-only, or entering transactions too when shared with "edit" and they are
    # editors there. Asked for by an owner of the account's environment, approved by an
    # owner of the receiving one; either can end it.

    def people(self):
        """Names to pick from when sharing (no environments or money)."""
        return self.q("SELECT id, username, display_name FROM users ORDER BY display_name COLLATE NOCASE")

    def request_share(self, uid, env_a, account_a, to_user, access="view", note="", include_bills=False):
        """Offer one of your accounts to a person; they choose which of their
        environments it appears in when they accept."""
        env_a, account_a = int(env_a), int(account_a)
        self.require(uid, env_a, "owner")
        if access not in ("view", "edit"):
            raise ApiError("Access must be view or edit")
        target = self.q1("SELECT id FROM users WHERE id=? OR username=?", (to_user if str(to_user).isdigit() else -1,
                                                                          str(to_user or "")))
        if not target:
            raise ApiError("Choose the person to share it with")
        if not self.account_name(env_a, account_a):
            raise ApiError("Choose one of your accounts")
        if self.q1("SELECT 1 FROM shares WHERE env_a=? AND account_a=? AND target_user_id=? AND status='pending'",
                   (env_a, account_a, target["id"])):
            raise ApiError("That person already has this offer waiting")
        return self.exec("INSERT INTO shares(env_a,account_a,env_b,target_user_id,access,include_bills,status,"
                         "created_by,created,note) VALUES(?,?,0,?,?,?,'pending',?,?,?)",
                         (env_a, account_a, target["id"], access, int(bool(include_bills)), uid, _now(),
                          (note or "")[:300]))

    def approve_share(self, uid, sid, env_b=None):
        """The person it was offered to accepts, into an environment they own."""
        s = self.q1("SELECT * FROM shares WHERE id=?", (sid,))
        if not s or s["status"] != "pending":
            raise ApiError("That offer isn't waiting", 404)
        if s["target_user_id"]:
            if s["target_user_id"] != uid:
                raise ApiError("This was offered to someone else", 403)
            env_b = int(env_b or 0)
        else:  # older requests addressed to an environment
            env_b = s["env_b"]
        if not env_b:
            raise ApiError("Choose the environment it should appear in")
        self.require(uid, env_b, "owner")
        if env_b == s["env_a"]:
            raise ApiError("It already lives in that environment; choose another one")
        if self.q1("SELECT 1 FROM shares WHERE env_a=? AND account_a=? AND env_b=? AND status='active'",
                   (s["env_a"], s["account_a"], env_b)):
            raise ApiError("That account already appears in that environment")
        self.exec("UPDATE shares SET status='active', env_b=?, approved_by=?, approved=? WHERE id=?",
                  (env_b, uid, _now(), sid))

    def ensure_share_link(self, uid, sid, other_account, env_b=None):
        """A share with entering allowed lets its receiver move money between the shared
        account and accounts in the environment it appears in. The share is the
        owner's sign-off, so the connection is made (or reused) here."""
        s = self.q1("SELECT * FROM shares WHERE id=? AND status='active'", (sid,))
        if not s:
            raise ApiError("That account isn't shared any more", 403)
        if env_b is not None and s["env_b"] != env_b:
            raise ApiError("That shared account isn't in this environment", 403)
        if s["access"] != "edit":
            raise ApiError("That account is shared to view only", 403)
        self.require(uid, s["env_b"], "editor")
        other_account = int(other_account)
        if not self.account_name(s["env_b"], other_account):
            raise ApiError("Choose one of the accounts in your environment")
        l = self.q1("SELECT id FROM links WHERE status='active' AND ((env_a=? AND account_a=? AND env_b=? AND account_b=?) "
                    "OR (env_a=? AND account_a=? AND env_b=? AND account_b=?))",
                    (s["env_a"], s["account_a"], s["env_b"], other_account,
                     s["env_b"], other_account, s["env_a"], s["account_a"]))
        if l:
            return l["id"]
        return self.exec("INSERT INTO links(env_a,account_a,env_b,account_b,status,created_by,created,approved_a_by,"
                         "approved_b_by,approved,note) VALUES(?,?,?,?,'active',?,?,?,?,?,?)",
                         (s["env_a"], s["account_a"], s["env_b"], other_account, uid, _now(), s["created_by"], uid,
                          _now(), f"via-share:{sid}"))

    def share_link_label(self, lid, env_id, account_id):
        """'Her Checking (Personal)' for the far side of a connection, seen from env_id."""
        oe, oa = self.link_other_side(lid, env_id, account_id)
        return f"{self.account_name(oe, oa)} ({self.env_name(oe)})", oe, oa

    def _share_party(self, uid, s):
        """Owner of the account's environment, the person it was offered to, or an
        owner of the environment it appears in."""
        return self.role(uid, s["env_a"]) == "owner" or s["target_user_id"] == uid or \
            (s["env_b"] and self.role(uid, s["env_b"]) == "owner")

    def decline_share(self, uid, sid):
        s = self.q1("SELECT * FROM shares WHERE id=?", (sid,))
        if not s or s["status"] != "pending":
            raise ApiError("That offer isn't waiting", 404)
        if not self._share_party(uid, s):
            raise ApiError("Only the people involved can do that", 403)
        self.exec("UPDATE shares SET status='declined', ended_by=?, ended=? WHERE id=?", (uid, _now(), sid))

    def end_share(self, uid, sid):
        s = self.q1("SELECT * FROM shares WHERE id=?", (sid,))
        if not s or s["status"] not in ("pending", "active"):
            raise ApiError("That share isn't active", 404)
        if not self._share_party(uid, s):
            raise ApiError("Only the people involved can do that", 403)
        self.exec("UPDATE shares SET status='ended', ended_by=?, ended=? WHERE id=?", (uid, _now(), sid))
        # Connections that existed only because of this share end with it.
        for l in self.q("SELECT id FROM links WHERE status='active' AND note=?", (f"via-share:{sid}",)):
            self._end_link_now(uid, l["id"])
    def set_share_access(self, uid, sid, access=None, include_bills=None):
        s = self.q1("SELECT * FROM shares WHERE id=?", (sid,))
        if not s or s["status"] not in ("pending", "active"):
            raise ApiError("That share isn't active", 404)
        self.require(uid, s["env_a"], "owner")   # only the account's side may widen or narrow it
        if access is not None:
            if access not in ("view", "edit"):
                raise ApiError("Access must be view or edit")
            self.exec("UPDATE shares SET access=? WHERE id=?", (access, sid))
        if include_bills is not None:
            self.exec("UPDATE shares SET include_bills=? WHERE id=?", (int(bool(include_bills)), sid))

    @staticmethod
    def bill_accounts(b):
        """Every account a scheduled item touches (paying account, transfer target, loan)."""
        ids = {b["account_id"]}
        if b.get("kind") == "transfer" and b.get("to_account_id"):
            ids.add(b["to_account_id"])
        if b.get("kind") == "loan" and b.get("loan_account_id"):
            ids.add(b["loan_account_id"])
        return ids

    def shared_bill_sets(self, uid, sid):
        """For the environment a share points into: which of the source environment's
        accounts are shared there with their bills (seen), and which of those this person
        may also change (edit access and at least editor there)."""
        s = self.q1("SELECT * FROM shares WHERE id=? AND status='active'", (sid,))
        if not s:
            return set(), set()
        role = self.role(uid, s["env_b"])
        rows = self.q("SELECT account_a, access FROM shares WHERE env_a=? AND env_b=? AND status='active' "
                      "AND include_bills=1", (s["env_a"], s["env_b"]))
        seen = {r["account_a"] for r in rows}
        edit = {r["account_a"] for r in rows if r["access"] == "edit"} if role and ROLES[role] >= ROLES["editor"] else set()
        return seen, edit

    def bill_visible(self, b, acct):
        """Shown through a share of `acct` when the item involves that account."""
        return acct in self.bill_accounts(b)

    def incoming_bills(self, uid, env_id, days=31):
        """Upcoming scheduled items (bills, deposits, transfers, loan payments) that involve
        an account shared into env_id with its bills. Each item once, even when it moves
        money between two shared accounts."""
        out, seen_keys = [], set()
        for a in self.incoming_shares(uid, env_id):
            if not a["include_bills"]:
                continue
            _, edit = self.shared_bill_sets(uid, a["share_id"])
            for o in self.store(a["env_id"]).upcoming(days):
                key = (a["env_id"], o["id"], o["date"])
                if key in seen_keys or not self.bill_visible(o, a["id"]):
                    continue
                seen_keys.add(key)
                out.append({**o, "share_id": a["share_id"], "share_env_id": a["env_id"],
                            "env_name": a["env_name"], "can_edit": self.bill_accounts(o) <= edit})
        out.sort(key=lambda r: (r["date"], r["payee"]))
        return out

    def shares_for(self, uid):
        """Shares this person deals with: offered to them, or touching environments they own."""
        mine = [e["id"] for e in self.my_envs(uid) if e["role"] == "owner"] or [-1]
        marks = ",".join("?" * len(mine))
        rows = self.q(f"SELECT * FROM shares WHERE env_a IN ({marks}) OR env_b IN ({marks}) OR target_user_id=? "
                      "ORDER BY id DESC", mine + mine + [uid])
        names = {u["id"]: u["display_name"] for u in self.users()}
        out = []
        for s in rows:
            a_role = self.role(uid, s["env_a"])
            for_me = s["target_user_id"] == uid or (not s["target_user_id"] and s["env_b"]
                                                    and self.role(uid, s["env_b"]) == "owner")
            out.append({**s, "env_a_name": self.env_name(s["env_a"]),
                        "env_b_name": self.env_name(s["env_b"]) if s["env_b"] else None,
                        "account_name": self.account_name(s["env_a"], s["account_a"]),
                        "created_by_name": names.get(s["created_by"]),
                        "target_name": names.get(s["target_user_id"]),
                        "i_own_a": a_role == "owner",
                        "needs_env": bool(s["target_user_id"]),
                        "can_approve": s["status"] == "pending" and bool(for_me),
                        "can_end": s["status"] in ("pending", "active") and self._share_party(uid, s)})
        return out

    def incoming_shares(self, uid, env_id):
        """Accounts shared into env_id, as this person sees them (balance and access)."""
        role = self.role(uid, env_id)
        if not role:
            return []
        out = []
        names = {u["id"]: u["display_name"] for u in self.users()}
        for s in self.q("SELECT * FROM shares WHERE env_b=? AND status='active' ORDER BY id", (env_id,)):
            try:
                acc = self.store(s["env_a"]).account(s["account_a"])
            except ApiError:
                continue
            out.append({"share_id": s["id"], "env_id": s["env_a"], "env_name": self.env_name(s["env_a"]),
                        "shared_by": names.get(s["created_by"], "someone"),
                        "id": acc["id"], "name": acc["name"], "type": acc["type"], "balance": acc["balance"],
                        "cleared_balance": acc["cleared_balance"], "liability": acc["liability"],
                        "closed": acc["closed"], "access": s["access"], "include_bills": bool(s["include_bills"]),
                        "can_edit": s["access"] == "edit" and ROLES[role] >= ROLES["editor"]})
        return out

    def share_access(self, uid, sid):
        """(environment, account, may enter transactions) for opening a shared account."""
        s = self.q1("SELECT * FROM shares WHERE id=? AND status='active'", (sid,))
        if not s:
            raise ApiError("That account isn't shared any more", 403)
        role = self.role(uid, s["env_b"])
        if not role:
            raise ApiError("You don't have access to that environment", 403)
        return (s["env_a"], s["account_a"], s["access"] == "edit" and ROLES[role] >= ROLES["editor"],
                bool(s["include_bills"]))

    # ----- transfers between environments --------------------------------------------
    def enter_scheduled(self, env_id, bid, data=None):
        """Record one occurrence of a scheduled item in its register and move the
        schedule on. A transfer with another environment gets both sides."""
        data = dict(data or {})
        st = self.store(env_id)
        bill = st.q1("SELECT * FROM bills WHERE id=?", (bid,))
        if bill and bill.get("card_account_id") and data.get("statement_balance") not in (None, ""):
            # A card kept by statement balance: the statement goes in first (dated its
            # closing day), then the payment, which defaults to the statement balance.
            pay_date = dt.date.fromisoformat(str(data.get("date") or bill["next_date"])[:10])
            day = st.account(bill["card_account_id"])["details"].get("statement_day")
            sdate = data.get("statement_date") or (st.last_closing(day, pay_date) if day else pay_date).isoformat()
            st.enter_statement(bill["card_account_id"], sdate, data["statement_balance"], data.get("statement_category_id"))
            if data.get("amount") in (None, ""):
                data["amount"] = data["statement_balance"]
        if not bill or not bill.get("x_link_id"):
            return st.enter_bill(bid, data)
        with st.lock:
            amount = abs(to_cents(data["amount"])) if data.get("amount") not in (None, "") else st.expected_amount(bill)
            if not amount:
                raise ApiError("Enter the amount for this time")
            date = data.get("date") or bill["next_date"]
            tid = self.cross_transfer(env_id, {
                "account_id": bill["account_id"], "date": date, "payee": bill["payee"], "memo": bill["memo"],
                "number": data.get("number") or "", "xlink_id": bill["x_link_id"],
                "amount_cents": -amount if bill["x_dir"] == "out" else amount})
            st.db.execute("INSERT INTO bill_history(bill_id,date,amount,transaction_id) VALUES(?,?,?,?)",
                          (bid, date, amount, tid))
            st._advance_bill(bill)
            st.db.commit()
            st.changed()
        return tid

    def enter_automatic(self, env_id=None, min_gap=60):
        """Items marked "record it for me": every occurrence due by today is entered in
        its register on its own date, at its expected amount, and marked as recorded
        automatically. Items whose amount isn't known yet (varies, nothing to average)
        are left for the person. Runs at most once a minute per environment."""
        done = []
        envs = [env_id] if env_id else [e["id"] for e in self.q("SELECT id FROM environments")]
        now = time.time()
        for eid in envs:
            if now - self._auto_ran.get(eid, 0) < min_gap:
                continue
            self._auto_ran[eid] = now
            st = self.store(eid)
            t = dt.date.today().isoformat()
            skip = set()   # items it can't record (no amount to go by): left for the person
            for _ in range(24):   # several missed occurrences are caught up, but not forever
                due = [b for b in st.bills() if b.get("auto_enter") and b["next_date"] <= t and b["id"] not in skip]
                if not due:
                    break
                for b in due:
                    if b["kind"] != "loan" and not b["amount"]:
                        skip.add(b["id"])
                        continue
                    try:
                        data = {} if b["kind"] == "loan" else {"amount": f"{b['amount'] / 100:.2f}"}
                        tid = self.enter_scheduled(eid, b["id"], data)
                        st.mark_auto(tid)
                        done.append({"env_id": eid, "payee": b["payee"], "date": b["next_date"], "amount": b["amount"]})
                    except ApiError:
                        skip.add(b["id"])
        return done

    def cross_transfer(self, env_id, data, tid=None):
        """Save a transfer whose other side is in another environment: the entry here
        and its mirror there (opposite amount), kept in step."""
        st = self.store(env_id)
        lid = int(data["xlink_id"])
        aid = int(data.get("account_id") or 0)
        other_env, other_acct = self.link_other_side(lid, env_id, aid)
        other = self.store(other_env)
        mine = dict(data)
        for k in ("xlink_id", "transfer_account_id", "category_id"):
            mine.pop(k, None)
        with self.lock, st.lock, other.lock:
            old = st.q1("SELECT * FROM transactions WHERE id=?", (tid,)) if tid else None
            # (An old same-environment transfer partner is removed by save_transaction.)
            tid = st.save_transaction(mine, tid)
            row = st.q1("SELECT * FROM transactions WHERE id=?", (tid,))
            partner = {"account_id": other_acct, "date": row["date"], "payee": row["payee"], "memo": row["memo"],
                       "amount_cents": -row["amount"]}
            ptid = row["xtx_id"] if row["xlink_id"] == lid else None
            if old and old["xlink_id"] and old["xlink_id"] != lid and old["xtx_id"]:
                self._delete_partner(env_id, old)
            if ptid and not other.q1("SELECT 1 FROM transactions WHERE id=?", (ptid,)):
                ptid = None
            ptid = other.save_transaction(partner, ptid)
            other.db.execute("UPDATE transactions SET xlink_id=?, xtx_id=? WHERE id=?", (lid, tid, ptid))
            st.db.execute("UPDATE transactions SET xlink_id=?, xtx_id=?, category_id=NULL WHERE id=?", (lid, ptid, tid))
            other.db.commit()
            st.db.commit()
        return tid

    def _delete_partner(self, env_id, row):
        """Delete the mirror of `row` (which lives in env_id). Entry numbers repeat
        between money files, so only the *other* environment is searched."""
        l = self.q1("SELECT * FROM links WHERE id=?", (row["xlink_id"],))
        if not l:
            return
        other_env = l["env_b"] if env_id == l["env_a"] else l["env_a"]
        st = self.store(other_env)
        p = st.q1("SELECT * FROM transactions WHERE id=? AND xlink_id=?", (row["xtx_id"], row["xlink_id"]))
        if p and p["xtx_id"] == row["id"]:
            st.delete_transaction(p["id"])

    def detach_cross(self, env_id, tid):
        """Before a cross-environment transfer is deleted or turned into something else,
        remove its mirror in the other environment."""
        st = self.store(env_id)
        row = st.q1("SELECT * FROM transactions WHERE id=?", (tid,))
        if row and row.get("xlink_id"):
            self._delete_partner(env_id, row)
            with st.lock:
                st.db.execute("UPDATE transactions SET xlink_id=NULL, xtx_id=NULL WHERE id=?", (tid,))
                st.db.commit()

    def decorate(self, env_id, rows):
        """Label cross-environment transfers as 'Transfer to Business Checking (Business)'."""
        cache = {}
        for r in rows:
            if r.get("xlink_id"):
                key = (r["xlink_id"], r["account_id"])
                if key not in cache:
                    try:
                        oe, oa = self.link_other_side(r["xlink_id"], env_id, r["account_id"])
                        cache[key] = f"{self.account_name(oe, oa)} ({self.env_name(oe)})"
                    except ApiError:
                        cache[key] = "another environment"
                r["category_label"] = ("Transfer to " if r["amount"] < 0 else "Transfer from ") + cache[key]
        return rows
