"""Make the language files (moneyapp/static/lang/<code>.js) from the translation sources.

    python tools/i18n_build.py

Sources, in tools/i18n/: part*.txt lines "number|French|Spanish|Portuguese" (the number is
the English text's place in lang/catalog.js), and extra.txt lines
"@English|French|Spanish|Portuguese" for text not in the catalog. An empty field leaves that
text in English. A translation must keep every "{}" of its English text: one that doesn't is
refused here, so it can't scramble a value on screen.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i18n_extract  # noqa: E402

LANGS = ("fr", "es", "pt")
OUT = os.path.join(HERE, "..", "moneyapp", "static", "lang")


def read_sources():
    cat = i18n_extract.catalog()
    out = {c: {} for c in LANGS}
    problems = []
    files = sorted(glob.glob(os.path.join(HERE, "i18n", "part*.txt"))) + [os.path.join(HERE, "i18n", "extra.txt")]
    for path in files:
        if not os.path.exists(path):
            continue
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split("|")
            if 1 < len(parts) < 4 and not any(p.strip() for p in parts[1:]):
                continue   # "123||": stays in English
            if len(parts) != 4:
                problems.append(f"{os.path.basename(path)}:{n}: needs 4 fields, has {len(parts)}")
                continue
            key = parts[0]
            if key.startswith("@"):
                en = key[1:]
            else:
                try:
                    en = cat[int(key)]
                except (ValueError, IndexError):
                    problems.append(f"{os.path.basename(path)}:{n}: no catalog entry {key}")
                    continue
            for code, tx in zip(LANGS, parts[1:]):
                tx = tx.strip()
                if not tx:
                    continue
                # Fewer is allowed only for "s" endings English adds ("account{}"), which the
                # translation writes its own way ("conta(s)"); "{}" stays in English order.
                import re as _re
                marks = _re.findall(r"\{(\d*)\}", tx)
                numbered = [int(m) for m in marks if m]
                if numbered and (max(numbered) > en.count("{}") or min(numbered) < 1):
                    problems.append(f"{os.path.basename(path)}:{n} ({code}): '{tx}' points past the {en.count('{}')} {{}} of '{en}'")
                    continue
                if not numbered and (len(marks) > en.count("{}") or (len(marks) < en.count("{}") and "(s)" not in tx and "(x)" not in tx and "(es)" not in tx)):
                    problems.append(f"{os.path.basename(path)}:{n} ({code}): '{tx}' doesn't keep the {en.count('{}')} {{}} of '{en}'")
                    continue
                out[code][en] = tx
    return out, problems


def write_category_names():
    """moneyapp/category_names.py: the starting categories' names in each language, by their
    English full name ("Taxes : Medicare Tax"). The catalog starts with the starting categories
    in order (tools/i18n_extract.category_names), so their translations are found by number."""
    sys.path.insert(0, os.path.join(HERE, ".."))
    from moneyapp import defaults
    order = []
    for name, _t, _b, subs in defaults.INCOME_CATEGORIES + defaults.EXPENSE_CATEGORIES:
        if name in defaults.ADDED_FULL_NAMES:
            continue
        order.append(name)
        order += [f"{name} : {s[0]}" for s in subs if f"{name} : {s[0]}" not in defaults.ADDED_FULL_NAMES]
    order.append(defaults.NOT_AN_EXPENSE)
    by_number = {}
    for path in sorted(glob.glob(os.path.join(HERE, "i18n", "part*.txt"))):
        for line in open(path, encoding="utf-8"):
            parts = line.rstrip("\n").split("|")
            if len(parts) == 4 and parts[0].isdigit():
                by_number[int(parts[0])] = parts[1:]
    names = {}
    for i, full in enumerate(order):
        tx = by_number.get(i)
        if tx:
            names[full] = {code: t.strip() for code, t in zip(LANGS, tx) if t.strip()}
    # Categories MoneyThistle adds itself when needed.
    names["Paycheck Deductions"] = {"fr": "Retenues sur la paie", "es": "Deducciones de nómina", "pt": "Descontos em folha"}
    # Made by MoneyThistle when an investment's value is updated.
    names["Change in Value"] = {"fr": "Variation de valeur", "es": "Cambio de valor", "pt": "Variação de valor"}
    # Categories added after the first release (defaults.ADDED_CATEGORIES).
    names.update({
        "Insurance : Accident": {"fr": "Accident", "es": "Accidentes", "pt": "Acidentes"},
        "Insurance : Dental": {"fr": "Dentaire", "es": "Dental", "pt": "Odontológico"},
        "Insurance : Disability": {"fr": "Invalidité", "es": "Discapacidad", "pt": "Invalidez"},
        "Insurance : Legal Plan": {"fr": "Assurance juridique", "es": "Plan legal", "pt": "Plano jurídico"},
        "Insurance : Vision": {"fr": "Soins de la vue", "es": "Visión", "pt": "Oftalmológico"},
        "Savings & Investments": {"fr": "Épargne et placements", "es": "Ahorros e inversiones", "pt": "Poupança e investimentos"},
        "Savings & Investments : Retirement Plan": {"fr": "Régime de retraite", "es": "Plan de jubilación", "pt": "Plano de previdência"},
        "Savings & Investments : HSA/FSA": {"fr": "Compte santé (HSA/FSA)", "es": "Cuenta de salud (HSA/FSA)", "pt": "Conta de saúde (HSA/FSA)"},
    })
    missing = defaults.ADDED_FULL_NAMES - set(names)
    if missing:
        raise SystemExit(f"category names missing for {sorted(missing)}")
    path = os.path.join(HERE, "..", "moneyapp", "category_names.py")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write('"""The starting categories\' names in French, Spanish and Portuguese, by their English full\n'
                'name. Made by tools/i18n_build.py from tools/i18n/ (translated by AI)."""\n\n')
        f.write("NAMES = " + json.dumps(names, ensure_ascii=False, indent=4, sort_keys=True) + "\n")
    print(f"category names: {len(names)}")


def main():
    write_category_names()
    out, problems = read_sources()
    for p in problems:
        print("skipped:", p)
    os.makedirs(OUT, exist_ok=True)
    for code, d in out.items():
        with open(os.path.join(OUT, code + ".js"), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"// {code}: translations of MoneyThistle's English text, made by tools/i18n_build.py from tools/i18n/.\n"
                    "// Translated by AI; not yet checked by a native speaker.\n")
            f.write(f"I18N.add({json.dumps(code)}, " + json.dumps(d, ensure_ascii=False, indent=0, sort_keys=True) + ");\n")
        print(f"{code}: {len(d)} entries")


if __name__ == "__main__":
    main()
