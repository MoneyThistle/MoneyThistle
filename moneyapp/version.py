"""Which version of the server code this is, as a short fingerprint.

The running copy remembers the fingerprint it started with; comparing it with the
files on disk now tells whether an update is waiting for a restart. Screens
(static files) are served straight from disk, so only Python files count;
the Restart MoneyThistle button (Settings) applies a waiting update.
"""

import hashlib
import os

# The release number people see (Settings, the installer, GitHub releases). Raise it with
# each release and add what changed to CHANGELOG.md: MAJOR.MINOR.PATCH (semantic versioning).
VERSION = "1.0.5"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _parts(v):
    out = []
    for p in str(v).split("-")[0].split("."):
        out.append(int(p) if p.isdigit() else 0)
    return tuple(out + [0] * (3 - len(out)))


def newer(a, b):
    """Whether version a is newer than version b ("1.2.0" > "1.10.0" is False)."""
    return _parts(a) > _parts(b)


_static_cache = {}


def static_id(root=HERE):
    """Fingerprint of the screens (the files the browser loads). An open page compares
    it with the one it started with, to offer a reload after an update."""
    folder = os.path.join(root, "moneyapp", "static")
    try:
        # Every file, subfolders (like brand/) included, as paths relative to the folder.
        files = sorted(os.path.relpath(os.path.join(d, f), folder).replace(os.sep, "/")
                       for d, _, names in os.walk(folder) for f in names)
        stamp = tuple((f, os.path.getmtime(os.path.join(folder, f)), os.path.getsize(os.path.join(folder, f)))
                      for f in files)
    except OSError:
        return ""
    if _static_cache.get("stamp") != stamp:
        h = hashlib.sha256()
        for f in files:
            with open(os.path.join(folder, f), "rb") as fh:
                h.update(f.encode() + b"\0" + fh.read())
        _static_cache.update(stamp=stamp, id=h.hexdigest()[:12])
    return _static_cache["id"]


_source_cache = {}
SOURCE_SKIP_DIRS = {"data", "backups", "shots", "dist", "build", "__pycache__", ".git", ".venv", "venv", "runtime"}
SOURCE_SKIP_FILES = {"settings.json", "notify.json", "network.json", "autostart.json", "shortcuts.json", ".control-token"}


def source_zip(root=HERE):
    """The source code of this very copy, as a zip (AGPL-3.0 section 13: everyone using
    MoneyThistle over the network can get the source of the version they're using, changes
    included). Program files only: never money data, backups, logs or settings."""
    key = (build_id(root), static_id(root))
    if _source_cache.get("key") == key:
        return _source_cache["zip"]
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(root):
            dirs[:] = sorted(x for x in dirs if x not in SOURCE_SKIP_DIRS)
            for f in sorted(files):
                if f in SOURCE_SKIP_FILES or f.endswith((".pyc", ".db", ".log", ".enc")):
                    continue
                full = os.path.join(d, f)
                z.write(full, "moneythistle/" + os.path.relpath(full, root).replace(os.sep, "/"))
        # An installed copy keeps the license beside its app folder.
        if not os.path.exists(os.path.join(root, "LICENSE")):
            for extra in ("LICENSE", "CHANGELOG.md"):
                p = os.path.join(os.path.dirname(root), extra)
                if os.path.exists(p):
                    z.write(p, "moneythistle/" + extra)
    _source_cache.update(key=key, zip=buf.getvalue())
    return _source_cache["zip"]


def build_id(root=HERE):
    h = hashlib.sha256()
    files = [os.path.join(root, "main.py")]
    pkg = os.path.join(root, "moneyapp")
    try:
        files += sorted(os.path.join(pkg, f) for f in os.listdir(pkg) if f.endswith(".py"))
    except OSError:
        pass
    for f in files:
        try:
            with open(f, "rb") as fh:
                h.update(fh.read().replace(b"\r\n", b"\n"))
        except OSError:
            h.update(b"missing:" + os.path.basename(f).encode())
    return h.hexdigest()[:12]
