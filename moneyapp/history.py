"""Change history: who added, changed or deleted what, when, in which environment, with
how it looked before and after; and undo for entries and scheduled items.

Every money file (Store) reports its own changes through `store.audit`, which the System
points here; the person making the change and the action it belongs to come from the
request being served (set_actor). Changes MoneyThistle makes by itself (automatic items)
have no person. One action (saving a paystub, a transfer, an import) is one "op" made of
several changes, shown and undone together.

Kept in the system file (so backups hold it) for a year.
"""

import datetime as dt
import json
import threading
import uuid

from .store import ApiError

SCHEMA = """
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    op TEXT NOT NULL,                 -- one action of one person (several changes)
    user_id INTEGER,                  -- NULL: MoneyThistle itself (automatic items)
    env_id INTEGER NOT NULL,
    kind TEXT NOT NULL,               -- transaction | account | bill | category | budget
    object_id INTEGER,
    action TEXT NOT NULL,             -- add | change | delete | undo
    summary TEXT NOT NULL DEFAULT '',
    before TEXT,                      -- the row as it was (JSON), NULL for an add
    after TEXT,                       -- the row as it became (JSON), NULL for a delete
    undone_by TEXT                    -- the op that undid this one
);
CREATE INDEX IF NOT EXISTS changes_env_at ON changes(env_id, at);
CREATE INDEX IF NOT EXISTS changes_obj ON changes(env_id, kind, object_id);
CREATE INDEX IF NOT EXISTS changes_op ON changes(op);
"""
KEEP_DAYS = 366
UNDOABLE = {"transaction": "transactions", "bill": "bills"}
# What must still match for an undo to be safe (later bookkeeping such as ordering or a
# group number doesn't count as a change).
COMPARE = {"transactions": ("account_id", "date", "number", "payee", "category_id", "memo", "amount", "status"),
           "bills": ("kind", "payee", "account_id", "to_account_id", "category_id", "amount", "frequency",
                     "next_date", "anchor_day", "memo", "active")}

_actor = threading.local()


def set_actor(user_id):
    """The person (and a fresh action id) for changes made while serving one request."""
    _actor.user_id = user_id
    _actor.op = uuid.uuid4().hex[:16]


def clear_actor():
    _actor.user_id = None
    _actor.op = None


def current_op():
    op = getattr(_actor, "op", None)
    if not op:   # outside a request (automatic items, start-up): one op per change
        return uuid.uuid4().hex[:16], None
    return op, getattr(_actor, "user_id", None)


def setup(db):
    db.executescript(SCHEMA)


def record(system, env_id, kind, object_id, action, before, after, summary=""):
    op, uid = current_op()
    with system.lock:
        system.db.execute("INSERT INTO changes(at,op,user_id,env_id,kind,object_id,action,summary,before,after) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (dt.datetime.now().isoformat(timespec="seconds"), op, uid, env_id, kind, object_id, action,
                           summary[:300], json.dumps(before) if before is not None else None,
                           json.dumps(after) if after is not None else None))
        system._history_n = getattr(system, "_history_n", 0) + 1
        if system._history_n % 200 == 1:
            cut = (dt.datetime.now() - dt.timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
            system.db.execute("DELETE FROM changes WHERE at < ?", (cut,))
        system.db.commit()


def _row(c):
    for k in ("before", "after"):
        c[k] = json.loads(c[k]) if c.get(k) else None
    return c


def _names(system, env_id, rows):
    """Account and category names for showing a change."""
    try:
        st = system.store(env_id)
    except ApiError:
        return {}, {}
    accs = {a["id"]: a["name"] for a in st.q("SELECT id, name FROM accounts")}
    cats = {c["id"]: c["full_name"] for c in st.categories()}
    return accs, cats


def listing(system, uid, env_ids, user=None, text=None, limit=100, offset=0):
    """Recent actions in these environments, newest first, each with its changes."""
    if not env_ids:
        return {"ops": [], "more": False}
    marks = ",".join("?" * len(env_ids))
    args = list(env_ids)
    where = f"env_id IN ({marks})"
    if user:
        where += " AND user_id=?"
        args.append(int(user))
    if text:
        where += " AND summary LIKE ?"
        args.append(f"%{text}%")
    ops = system.q(f"SELECT op, MAX(at) AS at FROM changes WHERE {where} GROUP BY op ORDER BY at DESC, MAX(id) DESC "
                   f"LIMIT ? OFFSET ?", args + [int(limit) + 1, int(offset)])
    more = len(ops) > limit
    ops = ops[:limit]
    people = {u["id"]: u["display_name"] or u["username"] for u in system.users()}
    roles = {e["id"]: e["role"] for e in system.my_envs(uid)}
    out = []
    lookups = {}
    for o in ops:
        rows = [_row(c) for c in system.q("SELECT * FROM changes WHERE op=? ORDER BY id", (o["op"],))
                if c["env_id"] in env_ids]
        for c in rows:
            if c["env_id"] not in lookups:
                lookups[c["env_id"]] = _names(system, c["env_id"], rows)
            accs, cats = lookups[c["env_id"]]
            c["env_name"] = system.env_name(c["env_id"])
            for side in ("before", "after"):
                r = c[side]
                if r:
                    r["_account"] = accs.get(r.get("account_id"), "")
                    r["_category"] = cats.get(r.get("category_id"), "")
                    if r.get("to_account_id"):
                        r["_to_account"] = accs.get(r["to_account_id"], "")
        first = rows[0] if rows else {}
        undoable = bool(rows) and all(c["kind"] in UNDOABLE and c["action"] != "undo" for c in rows) and \
            not any(c["undone_by"] for c in rows) and all(roles.get(c["env_id"]) in ("owner", "editor") for c in rows)
        out.append({"op": o["op"], "at": o["at"], "user": people.get(first.get("user_id"), "MoneyThistle (automatic)")
                    if first.get("user_id") else "MoneyThistle (automatic)",
                    "env_name": first.get("env_name", ""), "changes": rows, "can_undo": undoable,
                    "undone": any(c["undone_by"] for c in rows)})
    return {"ops": out, "more": more}


def for_object(system, uid, env_id, kind, object_id):
    """Every recorded change of one entry (or item), oldest first."""
    rows = system.q("SELECT op, action FROM changes WHERE env_id=? AND kind=? AND object_id=? ORDER BY id",
                    (env_id, kind, int(object_id)))
    # Numbers can be used again after a delete: this entry's story starts at its latest "add".
    starts = [i for i, r in enumerate(rows) if r["action"] == "add"]
    rows = rows[starts[-1]:] if starts else rows
    ops = []
    for r in rows:
        if r["op"] not in ops:
            ops.append(r["op"])
    res = listing(system, uid, [env_id], limit=10000)
    return [o for o in res["ops"] if o["op"] in ops][::-1]


def undo(system, uid, op):
    """Put back what one action changed: added entries go, changed ones return to how they
    were, deleted ones come back (with their ids, so transfers pair up again). Refused if
    anything was changed again since, so nothing later is lost."""
    rows = [_row(c) for c in system.q("SELECT * FROM changes WHERE op=? ORDER BY id", (op,))]
    if not rows:
        raise ApiError("Nothing to undo", 404)
    if any(c["undone_by"] for c in rows):
        raise ApiError("That was already undone")
    for c in rows:
        if c["kind"] not in UNDOABLE or c["action"] == "undo":
            raise ApiError("Only changes to entries and scheduled items can be undone here; "
                           "for anything else, restore a backup")
        system.require(uid, c["env_id"], "editor")
    # Check everything first (each thing's last state in this action against how it is
    # now): undo all of it or none.
    last = {}
    for c in rows:
        last[(c["env_id"], c["kind"], c["object_id"])] = c
    for c in last.values():
        st = system.store(c["env_id"])
        table = UNDOABLE[c["kind"]]
        cur = st.q1(f"SELECT * FROM {table} WHERE id=?", (c["object_id"],))
        if c["action"] in ("add", "change"):
            if not cur or any(cur.get(k) != (c["after"] or {}).get(k) for k in COMPARE[table]):
                raise ApiError("It was changed again afterwards. Undo the later change first.")
        # A deleted one whose number has since gone to a new entry comes back under a new number.
    new_op = uuid.uuid4().hex[:16]
    stores, idmap, restored = set(), {}, []
    for c in reversed(rows):
        st = system.store(c["env_id"])
        table = UNDOABLE[c["kind"]]
        cols = [r[1] for r in st.db.execute(f"PRAGMA table_info({table})")]
        final = c["object_id"]
        with st.lock:
            if c["action"] == "add":
                st.db.execute(f"DELETE FROM {table} WHERE id=?", (c["object_id"],))
            else:
                row = {k: v for k, v in (c["before"] or {}).items() if k in cols}
                row["id"] = c["object_id"]   # (its number, if it came back under a new one since)
                taken = c["action"] == "delete" and st.q1(f"SELECT 1 FROM {table} WHERE id=?", (c["object_id"],))
                if taken:
                    row.pop("id", None)
                    final = st.db.execute(f"INSERT INTO {table}({','.join(row)}) VALUES({','.join('?' * len(row))})",
                                          list(row.values())).lastrowid
                    idmap[(c["env_id"], table, c["object_id"])] = final
                    # Its earlier history follows it to the new number.
                    with system.lock:
                        system.db.execute("UPDATE changes SET object_id=? WHERE env_id=? AND kind=? AND object_id=? "
                                          "AND id<=?", (final, c["env_id"], c["kind"], c["object_id"], c["id"]))
                else:
                    st.db.execute(f"INSERT OR REPLACE INTO {table}({','.join(row)}) VALUES({','.join('?' * len(row))})",
                                  list(row.values()))
                if c["action"] == "delete":
                    restored.append((c["env_id"], table, final, c["before"] or {}))
                    if table == "transactions":
                        # Its receipts were set aside when it was deleted: they come back with it.
                        from . import attachments
                        attachments.relink(st, c["object_id"], final)
        stores.add(c["env_id"])
        with system.lock:
            system.db.execute("INSERT INTO changes(at,op,user_id,env_id,kind,object_id,action,summary,before,after) "
                              "VALUES(?,?,?,?,?,?,'undo',?,?,?)",
                              (dt.datetime.now().isoformat(timespec="seconds"), new_op, uid, c["env_id"], c["kind"],
                               final, "Undid: " + c["summary"],
                               json.dumps(c["after"]) if c["after"] else None,
                               json.dumps(c["before"]) if c["before"] else None))
    # Entries brought back under a new number: their transfer partners point at it again.
    for env, table, final, before in restored:
        if table != "transactions":
            continue
        st = system.store(env)
        with st.lock:
            p = before.get("transfer_id")
            if p and (env, table, p) in idmap:
                st.db.execute("UPDATE transactions SET transfer_id=? WHERE id=?", (idmap[(env, table, p)], final))
            x = before.get("xtx_id")
            if x and before.get("xlink_id"):
                for (e2, t2, old), new in idmap.items():
                    if t2 == table and old == x and e2 != env:
                        st.db.execute("UPDATE transactions SET xtx_id=? WHERE id=?", (new, final))
    for e in stores:
        st = system.store(e)
        with st.lock:
            st.db.commit()
            st.changed()
    with system.lock:
        system.db.execute("UPDATE changes SET undone_by=? WHERE op=?", (new_op, op))
        system.db.commit()
    return {"undone": len(rows)}
