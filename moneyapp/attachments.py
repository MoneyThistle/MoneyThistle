"""Receipts and other files kept with an entry: a photo taken on a phone, a scanned
receipt, a PDF invoice.

The files live in the data folder under attachments/, named by their SHA-256 (the
same file attached twice is kept once), and go into every backup with the money
files. Each money file has the list of what's attached to which entry.

An entry that's deleted keeps its attachments aside for a while, so undoing the
delete brings them back; after ORPHAN_DAYS they're cleared away.
"""

import base64
import datetime as dt
import hashlib
import os
import re

from .store import ApiError

MAX_BYTES = 20 * 1024 * 1024
ORPHAN_DAYS = 60
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

# What may be attached, recognised from the file's first bytes (not its name).
KINDS = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
)


def sniff(data):
    for magic, mime in KINDS:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc", b"ftypmsf1"):
        return "image/heic"
    return None


SCHEMA = ("CREATE TABLE IF NOT EXISTS attachments (id INTEGER PRIMARY KEY, transaction_id INTEGER, "
          "name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, "
          "added TEXT NOT NULL, added_by INTEGER, orphan_of INTEGER, orphaned TEXT)",
          "CREATE INDEX IF NOT EXISTS att_tx ON attachments(transaction_id)",
          # An entry deleted in any way (on its own, with its account, by a move...) sets its
          # attachments aside instead of leaving them on a number a new entry may get.
          "CREATE TRIGGER IF NOT EXISTS att_orphan AFTER DELETE ON transactions BEGIN "
          "UPDATE attachments SET orphan_of=OLD.id, orphaned=datetime('now'), transaction_id=NULL "
          "WHERE transaction_id=OLD.id; END")


def migrate(db):
    for sql in SCHEMA:
        db.execute(sql)
    cols = {r[1] for r in db.execute("PRAGMA table_info(attachments)")}
    if "account_id" not in cols:
        # Papers kept with an account rather than one entry (a purchase on a card whose
        # entries aren't tracked one by one: the receipt, the warranty), a short note or
        # keywords to find it by, and the date it's from.
        db.execute("ALTER TABLE attachments ADD COLUMN account_id INTEGER")
        db.execute("ALTER TABLE attachments ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE attachments ADD COLUMN doc_date TEXT")
    db.execute("CREATE INDEX IF NOT EXISTS att_acct ON attachments(account_id)")
    # A deleted account's own papers are set aside like a deleted entry's.
    db.execute("CREATE TRIGGER IF NOT EXISTS att_acct_orphan AFTER DELETE ON accounts BEGIN "
               "UPDATE attachments SET orphaned=datetime('now'), account_id=NULL "
               "WHERE account_id=OLD.id AND transaction_id IS NULL; END")


FIELDS = "id, transaction_id, account_id, name, mime, size, added, note, doc_date"


def clean_note(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()[:500]


def clean_date(v):
    if not v:
        return None
    try:
        return dt.date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise ApiError("The date must look like 2026-01-31", field="doc_date")


def folder(data_dir):
    return os.path.join(data_dir, "attachments")


def path_for(data_dir, sha):
    if not SHA_RE.match(sha or ""):
        raise ApiError("Bad attachment")
    return os.path.join(folder(data_dir), sha)


def clean_name(name, mime):
    name = re.sub(r"[\x00-\x1f/\\:*?\"<>|]+", " ", str(name or "")).strip()[:120]
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
           "image/heic": ".heic", "application/pdf": ".pdf"}[mime]
    if not name:
        name = "receipt"
    if not name.lower().endswith(ext) and not (ext == ".jpg" and name.lower().endswith(".jpeg")):
        name = os.path.splitext(name)[0] + ext
    return name


def listing(store, tid=None, account_id=None):
    """An entry's files, or an account's own papers (not its entries' receipts)."""
    if tid:
        return store.q(f"SELECT {FIELDS} FROM attachments WHERE transaction_id=? ORDER BY id", (tid,))
    return store.q(f"SELECT {FIELDS} FROM attachments WHERE account_id=? AND transaction_id IS NULL "
                   "ORDER BY COALESCE(doc_date, substr(added,1,10)) DESC, id DESC", (account_id,))


def search(store, text=None, account_id=None, start=None, end=None, limit=500):
    """Every file kept in this money file: with entries and with accounts. Each word typed
    must be found in the note, the file's name, the entry (payee, memo, category) or the
    account's name. The date is the paper's own, else its entry's, else when it was added."""
    where, args = ["(x.transaction_id IS NOT NULL OR x.account_id IS NOT NULL)"], []
    when = "COALESCE(x.doc_date, t.date, substr(x.added,1,10))"
    if account_id:
        where.append("COALESCE(x.account_id, t.account_id)=?"); args.append(account_id)
    if start:
        where.append(f"{when}>=?"); args.append(clean_date(start))
    if end:
        where.append(f"{when}<=?"); args.append(clean_date(end))
    for w in str(text or "").split()[:8]:
        like = f"%{w}%"
        where.append("(x.note LIKE ? OR x.name LIKE ? OR t.payee LIKE ? OR t.memo LIKE ? OR a.name LIKE ? OR c.name LIKE ?)")
        args += [like] * 6
    rows = store.q(f"SELECT x.id, x.transaction_id, x.name, x.mime, x.size, x.added, x.note, x.doc_date, {when} AS date, "
                   "COALESCE(x.account_id, t.account_id) AS account_id, a.name AS account_name, "
                   "t.payee, t.amount, t.memo, c.name AS category_name "
                   "FROM attachments x LEFT JOIN transactions t ON t.id=x.transaction_id "
                   "JOIN accounts a ON a.id=COALESCE(x.account_id, t.account_id) "
                   "LEFT JOIN categories c ON c.id=t.category_id "
                   f"WHERE {' AND '.join(where)} ORDER BY date DESC, x.id DESC LIMIT ?", args + [int(limit)])
    return rows


def update(store, aid, body):
    """Change a file's note, name or date."""
    row = get(store, aid)
    note = clean_note(body["note"]) if "note" in body else row["note"]
    name = clean_name(body["name"], row["mime"]) if body.get("name") else row["name"]
    doc_date = clean_date(body["doc_date"]) if "doc_date" in body else row["doc_date"]
    with store.lock:
        store.db.execute("UPDATE attachments SET note=?, name=?, doc_date=? WHERE id=?", (note, name, doc_date, aid))
        store.db.commit()
        store.changed()
    return dict(row, note=note, name=name, doc_date=doc_date)


def add(system, store, data_dir, tid, uid, body, account_id=None):
    if tid and not store.q1("SELECT 1 FROM transactions WHERE id=?", (tid,)):
        raise ApiError("No such entry", 404)
    if not tid and not store.q1("SELECT 1 FROM accounts WHERE id=?", (account_id or 0,)):
        raise ApiError("No such account", 404)
    note = clean_note(body.get("note"))
    doc_date = clean_date(body.get("doc_date")) or (None if tid else dt.date.today().isoformat())
    try:
        data = base64.b64decode(str(body.get("data") or ""), validate=True)
    except Exception:
        raise ApiError("The file didn't arrive in one piece. Try again.")
    if not data:
        raise ApiError("That file is empty")
    if len(data) > MAX_BYTES:
        raise ApiError("That file is larger than 20 MB")
    mime = sniff(data)
    if not mime:
        raise ApiError("Attach a photo (JPEG, PNG, HEIC, WebP, GIF) or a PDF")
    sha = hashlib.sha256(data).hexdigest()
    p = path_for(data_dir, sha)
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
    name = clean_name(body.get("name"), mime)
    with store.lock:
        aid = store.db.execute("INSERT INTO attachments(transaction_id,account_id,name,mime,size,sha256,added,added_by,"
                               "note,doc_date) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (tid or None, None if tid else account_id, name, mime, len(data), sha,
                                dt.datetime.now().isoformat(timespec="seconds"), uid, note, doc_date)).lastrowid
        store.db.commit()
        store.changed()
    return aid, name


def get(store, aid):
    row = store.q1("SELECT * FROM attachments WHERE id=? AND (transaction_id IS NOT NULL OR account_id IS NOT NULL)",
                   (aid,))
    if not row:
        raise ApiError("No such attachment", 404)
    return row


def read(data_dir, row):
    try:
        with open(path_for(data_dir, row["sha256"]), "rb") as f:
            return f.read()
    except FileNotFoundError:
        raise ApiError("The file is missing from the data folder. Restoring a backup brings it back.", 404)


def remove(store, aid):
    row = get(store, aid)
    with store.lock:
        store.db.execute("DELETE FROM attachments WHERE id=?", (aid,))
        store.db.commit()
        store.changed()
    return row


def relink(store, old_tid, new_tid):
    """An entry brought back by undo gets its attachments back."""
    store.db.execute("UPDATE attachments SET transaction_id=?, orphan_of=NULL, orphaned=NULL "
                     "WHERE orphan_of=? AND transaction_id IS NULL", (new_tid, old_tid))


def in_use(system):
    """Every file any money file still lists (attached or set aside)."""
    used = set()
    for env in system.q("SELECT id FROM environments"):
        try:
            used.update(r["sha256"] for r in system.store(env["id"]).q("SELECT DISTINCT sha256 FROM attachments"))
        except Exception:
            pass
    return used


def tidy(system):
    """Clear away attachments of entries deleted long ago, then files nothing lists."""
    for env in system.q("SELECT id FROM environments"):
        st = system.store(env["id"])
        with st.lock:
            st.db.execute("DELETE FROM attachments WHERE transaction_id IS NULL AND orphaned < datetime('now', ?)",
                          (f"-{ORPHAN_DAYS} days",))
            # Always finished, also when nothing was deleted: an unfinished change left open
            # here made every backup wait for it forever (and every page with it).
            st.db.commit()
    d = folder(system.data_dir)
    if not os.path.isdir(d):
        return
    used = in_use(system)
    for n in os.listdir(d):
        if SHA_RE.match(n) and n not in used:
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass
