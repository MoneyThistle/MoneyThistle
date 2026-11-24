"""Automatic backups to a folder and/or a WebDAV server (Nextcloud, ownCloud,
Synology, Box, any WebDAV share).

Same rules as the original (MECHANICS.md):
- a backup after changes (the original did this every time it closed; a server
  never closes, so it happens once the app has been idle a few minutes after a
  change, and again when the container stops),
- a scheduled backup every N days (1-99, 14 by default),
- keep the N newest of each kind (1-99, 3 by default), optionally compressed.
"""

import base64
import datetime as dt
import gzip
import hashlib
import io
import json
import zipfile
import os
import re
import sqlite3
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import crypt
from .store import DEFAULT_BACKUP, ApiError

# .zip: everything (since environments); .zip.enc: the same, encrypted with the backup
# password; .db/.db.gz: one money file (older backups).
NAME_RE = re.compile(r"^money-(auto|scheduled|manual)-(\d{8}-\d{6})\.(zip\.enc|zip|db|db\.gz)$")


def backup_name(kind, compress, when=None, encrypted=False):
    when = when or dt.datetime.now()
    return f"money-{kind}-{when.strftime('%Y%m%d-%H%M%S')}.zip" + (".enc" if encrypted else "")


def check_backup(blob, password=None):
    """Open a backup the way a restore would: decrypt it (password checked), then read
    every file in the zip (CRCs checked) and make sure people and money files are in it.
    Returns the plain bytes; ApiError says what's wrong."""
    data = crypt.decrypt(blob, password) if crypt.is_encrypted(blob) else blob
    if data[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            bad = z.testzip()
        except zipfile.BadZipFile:
            raise ApiError("The backup's zip is damaged")
        if bad:
            raise ApiError(f"The backup's zip is damaged ({bad})")
        names = z.namelist()
        if "system.db" not in names or not any(n.endswith(".db") and n != "system.db" for n in names):
            raise ApiError("The backup is missing its people or money files")
    elif not data.startswith(b"SQLite format 3\x00"):
        raise ApiError("That file is not a backup from this app")
    return data


def _when(name):
    m = NAME_RE.match(name)
    return dt.datetime.strptime(m.group(2), "%Y%m%d-%H%M%S") if m else None


def keep_plan(names, s):
    """Which automatic backups to keep, and why (name -> reason). Tiers, like a daily /
    weekly / monthly rotation, so a mistake found days or months later can still be undone
    from a backup made before it:
      - the newest `keep_change` after-change backups and `keep_scheduled` scheduled ones;
      - the last backup of each of the latest `keep_daily` days that have one;
      - the last of each of the latest `keep_weekly` weeks (Monday to Sunday);
      - the last of each of the latest `keep_monthly` months.
    Manual backups aren't in the plan: they're never deleted."""
    items = sorted(((_when(n), n) for n in names if NAME_RE.match(n) and NAME_RE.match(n).group(1) != "manual"),
                   reverse=True)
    keep = {}
    for kind, n, why in (("auto", s.get("keep_change", 3), "recent"),
                         ("scheduled", s.get("keep_scheduled", 3), "recent scheduled")):
        for _, name in [x for x in items if NAME_RE.match(x[1]).group(1) == kind][:int(n or 0)]:
            keep.setdefault(name, why)
    for n, why, period in ((s.get("keep_daily", 7), "daily", lambda w: w.date()),
                           (s.get("keep_weekly", 4), "weekly", lambda w: w.isocalendar()[:2]),
                           (s.get("keep_monthly", 12), "monthly", lambda w: (w.year, w.month))):
        seen = set()
        for when, name in items:      # newest first: the first seen in a period is its last backup
            p = period(when)
            if p in seen:
                continue
            if len(seen) >= int(n or 0):
                break
            seen.add(p)
            keep.setdefault(name, why)
    return keep


def env_overrides(settings):
    """Docker users can set the WebDAV account through environment variables."""
    s = dict(settings)
    if os.environ.get("WEBDAV_URL"):
        s["webdav_url"] = os.environ["WEBDAV_URL"]
        s["webdav_enabled"] = True
    if os.environ.get("WEBDAV_USER"):
        s["webdav_user"] = os.environ["WEBDAV_USER"]
    if os.environ.get("WEBDAV_PASSWORD"):
        s["webdav_password"] = os.environ["WEBDAV_PASSWORD"]
    if os.environ.get("BACKUP_DIR"):
        s["local_dir"] = os.environ["BACKUP_DIR"]
    return s


class LocalTarget:
    label = "folder"

    def __init__(self, folder):
        self.folder = folder

    def put(self, name, data):
        os.makedirs(self.folder, exist_ok=True)
        tmp = os.path.join(self.folder, "." + name + ".part")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, os.path.join(self.folder, name))

    def list(self):
        if not os.path.isdir(self.folder):
            return []
        out = []
        for n in os.listdir(self.folder):
            if NAME_RE.match(n):
                p = os.path.join(self.folder, n)
                out.append({"name": n, "size": os.path.getsize(p)})
        return out

    def get(self, name):
        with open(os.path.join(self.folder, name), "rb") as f:
            return f.read()

    def delete(self, name):
        os.remove(os.path.join(self.folder, name))


class WebDavTarget:
    label = "webdav"

    def __init__(self, url, user, password, timeout=60):
        if not url.lower().startswith(("http://", "https://")):
            raise ApiError("The WebDAV address must start with https://")
        # Folder names may have spaces or other characters ("MoneyThistle"): the path is
        # encoded once (what's already encoded, like %20, stays as it is).
        p = urllib.parse.urlsplit(url.strip())
        path = urllib.parse.quote(urllib.parse.unquote(p.path), safe="/")
        self.url = urllib.parse.urlunsplit((p.scheme, p.netloc, path, "", "")).rstrip("/") + "/"
        self.timeout = timeout
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": "Basic " + token, "User-Agent": "MoneyThistle-backup"}

    def _req(self, method, url, data=None, headers=None):
        h = dict(self.headers)
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except urllib.error.URLError as e:
            raise ApiError(f"Could not reach the WebDAV server: {e.reason}")

    def ensure_folder(self):
        """Make sure the backup folder exists, creating it (and any missing folders above
        it) when it doesn't. Starts from the folder itself and walks up only until it
        finds one that's there, because servers like Nextcloud refuse requests above the
        user's own files (/remote.php/, /remote.php/dav/...)."""
        if getattr(self, "_ready", False):
            return
        parts = urllib.parse.urlsplit(self.url)
        segs = [s for s in parts.path.split("/") if s]
        url = lambda i: urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/" + "/".join(segs[:i]) + ("/" if i else ""), "", ""))

        def state(i):
            st, _ = self._req("PROPFIND", url(i), headers={"Depth": "0"})
            if st == 401:
                raise ApiError("The WebDAV server refused the user name or password")
            if st in (200, 207):
                return "there"
            return "missing" if st == 404 else "unknown"   # 403/405...: not ours to look at

        if state(len(segs)) == "there":
            self._ready = True
            return
        # Walk up to the nearest folder that exists (or that the server won't show,
        # which is above the user's own files: taken as there).
        i = len(segs) - 1
        while i > 0 and state(i) == "missing":
            i -= 1
        for j in range(i + 1, len(segs) + 1):
            st, _ = self._req("MKCOL", url(j))
            if st == 401:
                raise ApiError("The WebDAV server refused the user name or password")
            if st not in (201, 405):   # 405: it's already there
                where = "/" + "/".join(segs[:j]) + "/"
                hint = " (a folder above it is missing or can't be created)" if st == 409 else \
                    " (no permission to create it there)" if st == 403 else ""
                raise ApiError(f"Could not create the backup folder {where} on the server (HTTP {st}){hint}")
        self._ready = True

    def put(self, name, data):
        self.ensure_folder()
        st, _ = self._req("PUT", self.url + urllib.parse.quote(name), data=data,
                          headers={"Content-Type": "application/octet-stream"})
        if st not in (200, 201, 204):
            if st == 401:
                raise ApiError("The WebDAV server refused the user name or password")
            raise ApiError(f"Upload failed (HTTP {st})")

    def list(self):
        body = b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getcontentlength/></d:prop></d:propfind>'
        st, data = self._req("PROPFIND", self.url, data=body,
                             headers={"Depth": "1", "Content-Type": "application/xml"})
        if st == 404:
            return []
        if st == 401:
            raise ApiError("The WebDAV server refused the user name or password")
        if st not in (200, 207):
            raise ApiError(f"Could not list backups (HTTP {st})")
        out = []
        root = ET.fromstring(data)
        for resp in root.findall("{DAV:}response"):
            href = resp.findtext("{DAV:}href") or ""
            name = urllib.parse.unquote(href.rstrip("/").rsplit("/", 1)[-1])
            if NAME_RE.match(name):
                size = resp.findtext(".//{DAV:}getcontentlength")
                out.append({"name": name, "size": int(size) if size and size.isdigit() else None})
        return out

    def get(self, name):
        st, data = self._req("GET", self.url + urllib.parse.quote(name))
        if st != 200:
            raise ApiError(f"Download failed (HTTP {st})")
        return data

    def delete(self, name):
        self._req("DELETE", self.url + urllib.parse.quote(name))


class BackupManager:
    def __init__(self, store, default_dir, config_path):
        self.store = store
        self.default_dir = default_dir
        # Kept outside the money file, so restoring an old backup keeps today's
        # backup settings and password.
        self.config_path = config_path
        self.run_lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None

    # ----- settings --------------------------------------------------------
    def _load(self):
        s = dict(DEFAULT_BACKUP)
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                s.update(json.load(f).get("backup", {}))
        except FileNotFoundError:
            pass
        except Exception:
            pass
        return s

    def _save(self, s):
        os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
        tmp = self.config_path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"backup": s}, f, indent=2)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, self.config_path)

    def settings(self):
        s = env_overrides(self._load())
        if not s.get("local_dir"):
            s["local_dir"] = self.default_dir
        return s

    def public_settings(self):
        s = self.settings()
        s["webdav_password_set"] = bool(s.pop("webdav_password", ""))
        s["backup_password_set"] = bool(s.pop("backup_password", ""))
        s["env_locked"] = sorted(k for k in ("WEBDAV_URL", "WEBDAV_USER", "WEBDAV_PASSWORD", "BACKUP_DIR")
                                 if os.environ.get(k))
        return s

    def update_settings(self, data):
        cur = self._load()
        for key in ("on_change", "scheduled", "compress", "local_enabled", "webdav_enabled"):
            if key in data:
                cur[key] = bool(data[key])
        for key, lo, hi in (("keep_change", 1, 99), ("keep_scheduled", 1, 99),
                            ("keep_daily", 0, 99), ("keep_weekly", 0, 99), ("keep_monthly", 0, 99),
                            ("interval_days", 1, 99), ("idle_minutes", 1, 1440)):
            if key in data:
                try:
                    v = int(data[key])
                except Exception:
                    raise ApiError(f"{key} must be a whole number")
                if not lo <= v <= hi:
                    # Same limits and wording idea as the original's settings dialog.
                    raise ApiError(f"Please enter a number between {lo} and {hi}.")
                cur[key] = v
        for key in ("local_dir", "webdav_url", "webdav_user"):
            if key in data:
                cur[key] = str(data[key] or "").strip()
        if data.get("webdav_password"):
            cur["webdav_password"] = str(data["webdav_password"])
        if data.get("clear_webdav_password"):
            cur["webdav_password"] = ""
        # Encryption: a password every new backup is encrypted with. It's kept here (the
        # server makes backups on its own), so it protects copies that leave this
        # computer, like Nextcloud; it must be known to restore them anywhere else.
        if data.get("backup_password"):
            pw = str(data["backup_password"])
            if len(pw) < 10:
                raise ApiError("Use a backup password of at least 10 characters")
            cur["backup_password"] = pw
        if "encrypt" in data:
            cur["encrypt"] = bool(data["encrypt"])
            if cur["encrypt"] and not cur.get("backup_password"):
                raise ApiError("Set a backup password to encrypt backups")
        self._save(cur)
        return self.public_settings()

    def targets(self, s=None):
        s = s or self.settings()
        out = []
        if s["local_enabled"]:
            out.append(LocalTarget(s["local_dir"]))
        if s["webdav_enabled"] and s["webdav_url"]:
            out.append(WebDavTarget(s["webdav_url"], s["webdav_user"], s["webdav_password"]))
        return out

    # ----- running a backup ------------------------------------------------
    def run(self, kind):
        """Write one backup to every destination; returns per-destination results."""
        with self.run_lock:
            s = self.settings()
            targets = self.targets(s)
            if not targets:
                raise ApiError("Turn on a backup destination first (a folder or WebDAV)")
            changes_at = self.store.last_change
            # One zip: people, environments and every money file; encrypted when asked.
            data = self.store.snapshot_bytes(s["compress"])
            enc = bool(s.get("encrypt") and s.get("backup_password"))
            if enc:
                data = crypt.encrypt(data, s["backup_password"])
            sha = hashlib.sha256(data).hexdigest()
            # Never the name of a backup already there (two within one second): a failed
            # check deletes its own copy, which must not be an earlier good one.
            taken = set()
            for t in targets:
                try:
                    taken.update(b["name"] for b in t.list())
                except Exception:
                    pass
            when = dt.datetime.now()
            name = backup_name(kind, s["compress"], when, encrypted=enc)
            while name in taken:
                when += dt.timedelta(seconds=1)
                name = backup_name(kind, s["compress"], when, encrypted=enc)
            results = []
            any_ok = False
            for t in targets:
                try:
                    t.put(name, data)
                    # Not a success until it's read back: downloaded, the same SHA-256
                    # as what was sent, and it opens (decrypts, every file in the zip
                    # reads) the way a restore would.
                    try:
                        got = t.get(name)
                        if hashlib.sha256(got).hexdigest() != sha:
                            raise ApiError("the copy read back differs from what was sent")
                        check_backup(got, s.get("backup_password"))
                    except Exception as e:
                        try:
                            t.delete(name)   # never leave a bad copy to restore from
                        except Exception:
                            pass
                        raise ApiError(f"Verification failed: {e}")
                    self._prune(t, kind, s)
                    self.store.log_backup(kind, t.label, name, True,
                                          f"{len(data)} bytes · verified · sha256 {sha[:16]}" + (" · encrypted" if enc else ""))
                    results.append({"destination": t.label, "ok": True, "name": name, "sha256": sha,
                                    "verified": True, "encrypted": enc})
                    any_ok = True
                except Exception as e:  # keep going with the other destination
                    msg = str(e)
                    self.store.log_backup(kind, t.label, name, False, msg)
                    results.append({"destination": t.label, "ok": False, "error": msg})
            if any_ok:
                # Changes made while this ran stay pending.
                if self.store.last_change == changes_at:
                    self.store.dirty_since = None
                if kind == "scheduled":
                    cur = self._load()
                    cur["last_scheduled"] = dt.date.today().isoformat()
                    self._save(cur)
            return results

    def _prune(self, target, kind, s):
        """Delete automatic backups no tier keeps (manual ones are never deleted)."""
        if kind == "manual":
            return
        names = [b["name"] for b in target.list()]
        keep = keep_plan(names, s)
        for n in names:
            m = NAME_RE.match(n)
            if m and m.group(1) != "manual" and n not in keep:
                try:
                    target.delete(n)
                except Exception:
                    pass

    def days_since_scheduled(self, s):
        """-1 when there has never been one (the original's rule), else whole days."""
        last = s.get("last_scheduled")
        if not last:
            return -1
        return (dt.date.today() - dt.date.fromisoformat(last)).days

    def due(self):
        """What should run now, in the original's order: after-changes, then scheduled."""
        s = self.settings()
        kinds = []
        if s["on_change"] and self.store.dirty_since is not None and self.store.last_change and \
                time.time() - self.store.last_change >= s["idle_minutes"] * 60:
            kinds.append("auto")
        if s["scheduled"]:
            d = self.days_since_scheduled(s)
            if d == -1 or d >= s["interval_days"]:
                kinds.append("scheduled")
        return kinds

    def tick(self):
        # Automatic items due by today go into their registers (see System.enter_automatic).
        notifier = getattr(self, "notifier", None)
        try:
            if hasattr(self.store, "enter_automatic"):
                done = self.store.enter_automatic()
                if done and notifier:
                    notifier.note_recorded(done)
        except Exception:
            pass   # never let this stop backups; it's tried again next minute
        try:
            if notifier:
                notifier.tick()   # the daily summary, once a day at its hour
        except Exception:
            pass
        for kind in self.due():
            try:
                self.run(kind)
            except Exception as e:
                self.store.log_backup(kind, "-", "-", False, str(e))

    def on_shutdown(self):
        """Like the original's back-up-on-close."""
        s = self.settings()
        if s["on_change"] and self.store.dirty_since is not None:
            try:
                self.run("auto")
            except Exception as e:
                self.store.log_backup("auto", "-", "-", False, str(e))

    def start(self, every=60):
        def loop():
            # A first check soon after start, then every minute.
            if not self.stop.wait(20):
                self.tick()
            while not self.stop.wait(every):
                self.tick()
        self.thread = threading.Thread(target=loop, daemon=True, name="backups")
        self.thread.start()

    # ----- listing and restoring -------------------------------------------
    def list_all(self):
        out, errors = [], []
        s = self.settings()
        for t in self.targets():
            try:
                found = t.list()
                why = keep_plan([b["name"] for b in found], s)   # which tier keeps each one
                for b in found:
                    m = NAME_RE.match(b["name"])
                    stamp = dt.datetime.strptime(m.group(2), "%Y%m%d-%H%M%S")
                    out.append({**b, "destination": t.label, "kind": m.group(1),
                                "when": stamp.isoformat(timespec="seconds"),
                                "kept_as": "kept until you delete it" if m.group(1) == "manual"
                                else why.get(b["name"], "next to be cleared")})
            except Exception as e:
                errors.append({"destination": t.label, "error": str(e)})
        out.sort(key=lambda b: b["when"], reverse=True)
        return {"backups": out, "errors": errors}

    def verify(self, destination, name, password=None):
        """Download one backup and check it opens: SHA-256, decryption, every zip entry."""
        if not NAME_RE.match(name or ""):
            raise ApiError("Not a backup file name")
        target = next((t for t in self.targets() if t.label == destination), None)
        if not target:
            raise ApiError("That destination is turned off")
        blob = target.get(name)
        if name.endswith(".gz"):
            blob = gzip.decompress(blob)
        check_backup(blob, password or self.settings().get("backup_password"))
        return {"name": name, "destination": destination, "bytes": len(blob),
                "sha256": hashlib.sha256(blob).hexdigest(), "encrypted": crypt.is_encrypted(blob), "ok": True}

    def restore(self, destination, name, password=None):
        if not NAME_RE.match(name or ""):
            raise ApiError("Not a backup file name")
        target = next((t for t in self.targets() if t.label == destination), None)
        if not target:
            raise ApiError("That destination is turned off")
        data = target.get(name)
        if name.endswith(".gz"):
            data = gzip.decompress(data)
        # Encrypted: the password given, else the saved one; checked before anything changes.
        data = check_backup(data, password or self.settings().get("backup_password"))
        # Safety copy of everything as it is now, then put the backup back.
        s = self.settings()
        safety = LocalTarget(s["local_dir"])
        safety.put(backup_name("manual", True), self.store.snapshot_bytes(True))
        self.store.restore_bytes(data)
        self.store.log_backup("restore", destination, name, True, "restored")
        return {"restored": name}

    def delete(self, destination, name):
        """Delete one backup (a Back up now copy, or any other). The last backup at a
        destination is never deleted: there'd be nothing left to restore."""
        if not NAME_RE.match(name or ""):
            raise ApiError("Not a backup file name")
        target = next((t for t in self.targets() if t.label == destination), None)
        if not target:
            raise ApiError("That destination is turned off")
        names = [b["name"] for b in target.list()]
        if name not in names:
            raise ApiError("That backup isn't there any more", 404)
        if len(names) == 1:
            raise ApiError("That's the only backup in this place, so it's kept. Make another first.")
        with self.run_lock:
            target.delete(name)
        if name in [b["name"] for b in target.list()]:
            raise ApiError("The backup couldn't be deleted there; nothing changed.")
        self.store.log_backup("delete", destination, name, True, "deleted by an administrator")
        return {"deleted": name}

    # ----- starting over from a backup (a new computer or server) ---------------------
    def restore_blob(self, blob, password=None, label="file", name="uploaded backup"):
        """Put back a backup file brought in by hand: uploaded in the browser, given on the
        command line, or fetched from WebDAV while setting up. Checked first (password,
        every file in it); a safety copy is made when there's anything here to keep."""
        if blob[:2] == b"\x1f\x8b":
            blob = gzip.decompress(blob)   # older .db.gz backups
        typed = password or None
        data = check_backup(blob, typed or self.settings().get("backup_password"))
        if self.store.has_users():
            s = self.settings()
            LocalTarget(s["local_dir"]).put(backup_name("manual", True), self.store.snapshot_bytes(True))
        self.store.restore_bytes(data)
        if typed and crypt.is_encrypted(blob):
            # Keep making encrypted backups with the same password (this computer had none).
            cur = self._load()
            if not cur.get("backup_password"):
                cur.update(backup_password=typed, encrypt=True)
                self._save(cur)
        self.store.log_backup("restore", label, name, True, "restored")
        return {"restored": name, "people": [u["username"] for u in self.store.users()]}

    def webdav_preview(self, url, user, password):
        """Setting up from Nextcloud: the backups in that folder, newest first."""
        t = WebDavTarget(url, user, password)
        rows = [b for b in t.list() if NAME_RE.match(b["name"])]
        rows.sort(key=lambda b: _when(b["name"]) or dt.datetime.min, reverse=True)
        return [{**b, "kind": NAME_RE.match(b["name"]).group(1),
                 "when": _when(b["name"]).isoformat(timespec="seconds")} for b in rows]

    def restore_from_webdav(self, url, user, password, name, backup_password=None):
        """Setting up from Nextcloud: fetch one backup, put it back, and keep backing up to
        that same folder from now on."""
        if not NAME_RE.match(name or ""):
            raise ApiError("Not a backup file name")
        t = WebDavTarget(url, user, password)
        out = self.restore_blob(t.get(name), backup_password, "webdav", name)
        cur = self._load()
        cur.update(webdav_enabled=True, webdav_url=url.strip(), webdav_user=user, webdav_password=password)
        self._save(cur)
        return out
