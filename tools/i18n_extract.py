"""List the English text MoneyThistle's screens show, and what each language still lacks.

    python tools/i18n_extract.py                 # counts per language
    python tools/i18n_extract.py --missing pt    # pieces of text Portuguese doesn't have yet
    python tools/i18n_extract.py --all --max 60  # every piece up to 60 characters

It reads app.js, help.js and index.html the way the page shows them: the text between tags
(a value worked out while drawing, `${...}`, becomes "{}"), and title, placeholder,
aria-label and alt attributes. Some of what it finds is code rather than words; a dictionary
entry that never shows up costs nothing.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "moneyapp", "static")
ATTRS = ("title", "placeholder", "aria-label", "alt")


def literals(src):
    """Every string and template literal in a JavaScript source, with ${...} as \x00."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "\"'":
            j, buf = i + 1, []
            while j < n and src[j] != c:
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j + 1]); j += 2; continue
                if src[j] == "\n":
                    break
                buf.append(src[j]); j += 1
            out.append("".join(buf))
            i = j + 1
            continue
        if c == "`":
            j, buf = template(src, i + 1)
            out.append(buf)
            i = j
            continue
        i += 1
    return out


def template(src, i):
    """A template literal from just after its backtick: (index after it, text with \x00)."""
    buf, n = [], len(src)
    while i < n:
        c = src[i]
        if c == "\\" and i + 1 < n:
            buf.append(src[i + 1]); i += 2; continue
        if c == "`":
            return i + 1, "".join(buf)
        if c == "$" and i + 1 < n and src[i + 1] == "{":
            # Skip the expression (with nested templates and braces), but keep templates
            # inside it: they're text too.
            depth, i = 1, i + 2
            while i < n and depth:
                d = src[i]
                if d == "`":
                    i, inner = template(src, i + 1)
                    NESTED.append(inner)
                    continue
                if d in "\"'":
                    # A quoted string inside the expression is text too ("Light", "Yes").
                    q, i, start = d, i + 1, i + 1
                    while i < n and src[i] != q and src[i] != "\n":
                        i += 2 if src[i] == "\\" else 1
                    NESTED.append(src[start:i].replace('\\"', '"').replace("\\'", "'"))
                    i += 1
                    continue
                if d == "{":
                    depth += 1
                elif d == "}":
                    depth -= 1
                i += 1
            buf.append("\x00")
            continue
        buf.append(c); i += 1
    return i, "".join(buf)


NESTED = []
TAG = re.compile(r"<[^<>]*>")
ATTR = re.compile(r'\b(%s)="([^"]*)"' % "|".join(ATTRS))
CODEY = re.compile(r"^[\w\-.#:/\[\]=>()*$&|!?,;+{}\x00 ]*$")


def pieces(text):
    """Text a template shows: between tags, and in shown attributes."""
    for m in ATTR.finditer(text):
        yield m.group(2)
    for part in TAG.split(text):
        yield part


def keep(s):
    s = re.sub(r"\s+", " ", s.replace("\x00", "{}")).strip()
    s = re.sub(r"(\{\}\s*)+", "{} ", s).strip() if s.count("{}") > 1 and re.fullmatch(r"(\{\}\s*)+", s) else s
    if len(s) < 2 or not re.search(r"[A-Za-z]{2}", s):
        return None
    if s.startswith(("#", ".", "/", "http", "data:", "api/", "[")) or "=>" in s or "==" in s:
        return None
    # Code, CSS and headers rather than words.
    if any(x in s for x in ("${", "`", ".test(", "return", "use strict", "px;", "[data-", "[open]")):
        return None
    if " " not in s and re.search(r"[.,:\[(=_]", s.rstrip(":…")) and not re.fullmatch(r"[A-Z][\w'’-]*[:…]?", s):
        return None
    if re.fullmatch(r"[a-z]+:", s) or re.fullmatch(r"X-[\w-]+", s) or re.fullmatch(r"[A-Z][a-z]+(-[A-Z][a-z]+)+", s):
        return None
    if re.fullmatch(r"[A-Z][a-z]+[A-Z]\w+", s) or re.fullmatch(r"\((pointer|prefers|min|max)[^)]*\)", s):
        return None
    if re.match(r"(margin|padding|minmax|grid|display|font|width|height)\b", s):
        return None
    words = re.findall(r"[A-Za-z']+", s)
    # Class lists, ids and code: lower-case words only, without sentence punctuation.
    if not re.search(r"[A-Z]", s) and not re.search(r"[ .,:?!…]", s.strip("{} ")):
        return None
    if re.fullmatch(r"[a-z0-9_\-]+( [a-z0-9_\-]+)*", s) and len(words) > 1 and not re.search(r"[.,:?!]", s):
        # "small muted", "btn small filepick": class names
        if all(len(w) < 14 for w in words) and any(w in CLASSES for w in words):
            return None
    if re.fullmatch(r"[A-Z_]+", s) or re.fullmatch(r"[a-z]+[A-Z]\w*", s):   # CONSTANTS, camelCase
        return None
    if s.strip("{} ") == "":
        return None
    return s


CLASSES = {"small", "muted", "num", "btn", "pill", "card", "wide", "check", "primary", "danger", "tiny", "on", "neg",
           "green", "red", "amber", "click", "status", "notice", "err", "empty", "toolbar", "form", "row", "flush",
           "head", "grid", "sel", "linkbtn", "filepick", "noprint", "printonly", "auto", "more", "fold", "hint",
           "big", "trash", "closed", "acctrow", "xtra", "req", "settings", "kind", "env", "tag", "dot", "warn"}


def english():
    found = {}
    # Help (help.js) is translated as whole documents (lang/help.<code>.js), not piece by piece.
    for name in ("app.js",):
        src = open(os.path.join(STATIC, name), encoding="utf-8").read()
        NESTED.clear()
        lits = literals(src) + NESTED[:]
        for lit in lits:
            for p in pieces(lit):
                k = keep(p)
                if k:
                    found[k] = found.get(k, 0) + 1
    html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
    body = html.split("<body>", 1)[-1].split("<script", 1)[0]
    for p in pieces(body.replace("&amp;", "&")):
        k = keep(p)
        if k:
            found[k] = found.get(k, 0) + 1
    return found


CATALOG = os.path.join(STATIC, "lang", "catalog.js")


def catalog():
    """The numbered English text the translations follow (lang/catalog.js). Only ever added
    to at the end, so each language's list keeps lining up with it."""
    if not os.path.exists(CATALOG):
        return []
    src = open(CATALOG, encoding="utf-8").read()
    return json.loads(src[src.index("["): src.rindex("]") + 1])


def write_catalog(items):
    os.makedirs(os.path.dirname(CATALOG), exist_ok=True)
    with open(CATALOG, "w", encoding="utf-8", newline="\n") as f:
        f.write("// The English text MoneyThistle shows, numbered by position. Made by tools/i18n_extract.py;\n"
                "// only ever added to at the end (each lang/<code>.js list follows this order).\n"
                "I18N.catalog = " + json.dumps(items, ensure_ascii=False, indent=0) + ";\n")


def category_names():
    sys.path.insert(0, os.path.join(HERE, ".."))
    from moneyapp import defaults
    out = []
    for name, _t, _b, subs in defaults.INCOME_CATEGORIES + defaults.EXPENSE_CATEGORIES:
        if name in defaults.ADDED_FULL_NAMES:
            continue
        out.append(name)
        out += [s[0] for s in subs if f"{name} : {s[0]}" not in defaults.ADDED_FULL_NAMES]
    return out + [defaults.NOT_AN_EXPENSE] + defaults.ACCOUNT_TYPES + defaults.FREQUENCIES


def dictionary(code):
    """English -> translation for one language, from its list and the catalog."""
    path = os.path.join(STATIC, "lang", code + ".js")
    if not os.path.exists(path):
        return {}
    src = open(path, encoding="utf-8").read()
    body = src.split("I18N.add(", 1)[1]
    return json.loads(body[body.index("{"): body.rindex("}") + 1])


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    mx = int(argv[argv.index("--max") + 1]) if "--max" in argv else 10 ** 6
    mn = int(argv[argv.index("--min") + 1]) if "--min" in argv else 0
    en = {k: v for k, v in english().items() if mn <= len(k) <= mx}
    if "--grow" in argv:
        # Add the text not in the catalog yet (default categories first time), at the end.
        cat = catalog()
        have = set(cat)
        new = [k for k in (category_names() if not cat else []) if k not in have]
        have |= set(new)
        new += [k for k in sorted(en, key=lambda k: (len(k), k)) if k not in have]
        write_catalog(cat + new)
        print(f"catalog: {len(cat)} + {len(new)} = {len(cat) + len(new)}")
        return
    if "--list" in argv:
        # Numbered catalog lines from..to, for translating.
        a, b = (int(x) for x in argv[argv.index("--list") + 1].split(":"))
        for i, k in enumerate(catalog()[a:b], a):
            print(f"{i}\t{k}")
        return
    if "--all" in argv:
        print(json.dumps(sorted(en, key=lambda k: (len(k), k)), ensure_ascii=False, indent=0))
        return
    if "--missing" in argv:
        d = set(dictionary(argv[argv.index("--missing") + 1]))
        print(json.dumps(sorted((k for k in en if k not in d), key=lambda k: (len(k), k)), ensure_ascii=False, indent=0))
        return
    print(f"{len(en)} pieces of English text")
    for code in ("fr", "es", "pt"):
        d = set(dictionary(code))
        have = sum(1 for k in en if k in d)
        print(f"{code}: {have} translated ({100 * have // max(1, len(en))}%)")


if __name__ == "__main__":
    main(sys.argv[1:])
