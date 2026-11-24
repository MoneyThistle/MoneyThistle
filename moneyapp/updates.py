"""New versions of MoneyThistle: checking for them, and installing them on Windows.

Once a day MoneyThistle asks GitHub for its latest release: the version number, the notes and
the files. Nothing about the person or their money is sent (the request carries only
"MoneyThistle/<version>" as its program name). What happens next depends on how this copy was
installed:

  windows  The setup from the release is downloaded, checked against the SHA-256 the release
           publishes beside it, and run quietly. The setup stops this copy (which saves and
           backs up first), replaces the program files and starts it again. One click
           (Settings, or the note on Home), or by itself when "install automatically" is on.
  docker   Docker updates the container's image (Unraid: the Docker tab's "update ready";
           Docker Compose: pull, then up). MoneyThistle only says a new version is out.
  source   Run from a copy of the code: it says where to get the new version.

The choices live in updates.json in the data folder: {"check": true, "auto": false}.
"""

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from .store import ApiError
from .version import VERSION, newer

REPO = "MoneyThistle/MoneyThistle"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CHECK_EVERY = 24 * 3600            # seconds between checks
SETUP_LIMIT = 300 * 1024 * 1024    # the largest setup file downloaded
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_PREFIX = "moneythistle-update-"


def install_kind(root=APP_ROOT):
    """docker, windows (installed by the setup: its own Python and an uninstaller beside the
    app folder) or source (run from a copy of the code)."""
    if os.environ.get("MONEYTHISTLE_INSTALL") == "docker" or os.path.exists("/.dockerenv"):
        return "docker"
    base = os.path.dirname(root)
    try:
        names = os.listdir(base)
    except OSError:
        names = []
    if sys.platform == "win32" and os.path.isfile(os.path.join(base, "runtime", "python.exe")) and \
            any(n.lower().startswith("unins") and n.lower().endswith(".exe") for n in names):
        return "windows"
    return "source"


def fetch(url, timeout=20, limit=None):
    """The bytes at a web address (GitHub), refusing more than `limit` bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": f"MoneyThistle/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1) if limit else r.read()
    if limit and len(data) > limit:
        raise ValueError("The download is larger than expected")
    return data


class Updater:
    def __init__(self, data_dir, get=None, kind=None):
        self.path = os.path.join(data_dir, "updates.json")
        self.get = get or fetch
        self.kind = kind or install_kind()
        self.lock = threading.Lock()
        self.installing = False
        self.saved = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                self.saved = json.load(f) or {}
        except (OSError, ValueError):
            self.saved = {}

    # ----- choices -----------------------------------------------------------------------
    def settings(self):
        return {"check": self.saved.get("check", True) is not False,
                "auto": bool(self.saved.get("auto")) and self.kind == "windows"}

    def save_settings(self, data):
        if "check" in data:
            self.saved["check"] = bool(data["check"])
        if "auto" in data:
            if data["auto"] and self.kind != "windows":
                raise ApiError("Updates install by themselves only in the Windows program; "
                               "Docker and Unraid update the container instead")
            self.saved["auto"] = bool(data["auto"])
        self._write()
        return self.status()

    def _write(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.saved, f)
        os.replace(tmp, self.path)

    # ----- checking ----------------------------------------------------------------------
    def check(self, force=False):
        """Ask GitHub for the latest release, at most once a day unless forced."""
        if not force and (not self.settings()["check"] or time.time() - self.saved.get("checked_at", 0) < CHECK_EVERY):
            return self.status()
        try:
            rel = json.loads(self.get(LATEST_URL, timeout=20).decode("utf-8"))
            self.saved["latest"] = self._parse(rel)
            self.saved["error"] = ""
        except urllib.error.HTTPError as e:
            # 404: no release published yet, so nothing newer than this copy.
            self.saved["error"] = "" if e.code == 404 else "unreachable"
        except Exception:
            self.saved["error"] = "unreachable"
        self.saved["checked_at"] = time.time()
        self._write()
        return self.status()

    @staticmethod
    def _parse(rel):
        v = str(rel.get("tag_name") or "").strip().lstrip("vV")
        if not re.fullmatch(r"\d+(\.\d+){0,2}", v):
            raise ValueError("Not a version number")
        assets = {a.get("name"): a.get("browser_download_url") for a in rel.get("assets") or [] if isinstance(a, dict)}
        setup = f"MoneyThistle-Setup-{v}.exe"
        return {"version": v, "url": rel.get("html_url") or RELEASES_PAGE,
                "notes": str(rel.get("body") or "")[:4000], "published": str(rel.get("published_at") or "")[:10],
                "setup_url": assets.get(setup) or "", "sha256_url": assets.get(setup + ".sha256") or ""}

    def status(self):
        st = self.saved.get("latest") or {}
        available = bool(st.get("version")) and newer(st["version"], VERSION)
        when = self.saved.get("checked_at")
        return {"current": VERSION, "kind": self.kind, **self.settings(),
                "checked_at": dt.datetime.fromtimestamp(when).isoformat(timespec="minutes") if when else None,
                "latest": st.get("version"), "available": available, "url": st.get("url") or RELEASES_PAGE,
                "notes": st.get("notes") or "", "published": st.get("published") or "",
                "can_install": bool(available and self.kind == "windows" and st.get("setup_url") and st.get("sha256_url")),
                "installing": self.installing, "error": self.saved.get("error") or ""}

    # ----- installing (Windows) ----------------------------------------------------------
    def install(self):
        """Download the new setup, check its SHA-256, and run it quietly. It stops this copy
        (which backs up first), updates the program and starts it again."""
        st = self.status()
        if not st["can_install"]:
            raise ApiError("There's no update to install here" if not st["available"] else
                           "This copy can't install updates itself: see how to update it below")
        with self.lock:
            if self.installing:
                raise ApiError("The update is already being installed")
            self.installing = True
        try:
            latest = self.saved["latest"]
            want = self.get(latest["sha256_url"], timeout=30).decode("ascii", "replace").split()
            want = want[0].lower() if want else ""
            if not re.fullmatch(r"[0-9a-f]{64}", want):
                raise ApiError("The update's checksum couldn't be read, so it wasn't installed")
            data = self.get(latest["setup_url"], timeout=600, limit=SETUP_LIMIT)
            if hashlib.sha256(data).hexdigest() != want:
                raise ApiError("The download didn't match its checksum, so it wasn't installed")
            folder = tempfile.mkdtemp(prefix=TEMP_PREFIX)
            exe = os.path.join(folder, f"MoneyThistle-Setup-{latest['version']}.exe")
            with open(exe, "wb") as f:
                f.write(data)
            self.launch(exe)
        except ApiError:
            self.installing = False
            raise
        except Exception:
            self.installing = False
            raise ApiError("The update couldn't be downloaded from GitHub. Try again later.")
        return {"started": True, "version": latest["version"]}

    def launch(self, exe):
        """Run the setup on its own (it outlives this copy, which it stops): quietly, and
        starting MoneyThistle again at the end (/AUTOSTART=1)."""
        flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([exe, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/AUTOSTART=1"],
                         creationflags=flags, close_fds=True, cwd=os.path.dirname(exe))

    # ----- in the background -------------------------------------------------------------
    def tidy(self):
        """Setups downloaded by earlier updates (a day old or more) go."""
        base = tempfile.gettempdir()
        try:
            names = os.listdir(base)
        except OSError:
            return
        for n in names:
            p = os.path.join(base, n)
            if n.startswith(TEMP_PREFIX) and os.path.isdir(p):
                try:
                    if time.time() - os.path.getmtime(p) > 86400:
                        shutil.rmtree(p, ignore_errors=True)
                except OSError:
                    pass

    def start(self, first_wait=90, every=6 * 3600):
        """Check once a day (looked at every few hours); install by itself when asked to."""
        def run():
            self.tidy()
            time.sleep(first_wait)
            while True:
                try:
                    st = self.check()
                    if st["can_install"] and st["auto"] and not st["installing"]:
                        self.install()
                except Exception:
                    pass
                time.sleep(every)
        threading.Thread(target=run, daemon=True, name="updates").start()
