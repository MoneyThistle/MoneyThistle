"use strict";
// Languages. MoneyThistle's screens are written in English; with another language chosen,
// each piece of text is looked up in that language's dictionary (lang/<code>.js) as it
// appears on the page (labels, buttons, messages, tips), so the screens' own code doesn't
// change and a language can be added by adding a dictionary. Text without a translation
// yet stays in English. What people type (names, payees, memos) is never translated: it
// sits in input boxes, or inside an element marked translate="no".
//
// A dictionary entry is "English text": "translation". "{}" in an entry stands for a
// number, amount, date or name: "Started from your {} paystub": "Iniciado do seu holerite de {}".

const LANGS = [
  ["en", "English", "en-US"],
  ["fr", "Français", "fr-CA"],
  ["es", "Español", "es-419"],
  ["pt", "Português", "pt-BR"],
];
let LANG = "en", LOCALE = "en-US";

const I18N = {
  dicts: {},
  // Called by each lang/<code>.js file.
  add(code, entries) {
    const d = this.dicts[code] || (this.dicts[code] = { exact: new Map(), patterns: new Map(), loose: [], values: new Set() });
    for (const [en, tx] of Object.entries(entries)) {
      // (text written as HTML in the screens' code shows "&" where the code says "&amp;")
      const key = norm(en.replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">"));
      if (!key.includes("{}")) { d.exact.set(key, tx); d.values.add(norm(tx)); continue; }
      const parts = key.split("{}");
      // A pattern with hardly any words of its own would match almost anything (and slowly).
      if (parts.join("").replace(/[^A-Za-z]/g, "").length < 2) continue;
      // Two values side by side ("{}{}"): the second is an ending ("s") or nothing. A value
      // straight after a word ("account{}", "together{}.") may be nothing too.
      const re = new RegExp("^" + parts.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        .reduce((acc, p, i) => i === 0 ? p : acc + ((parts[i - 1] === "" && i > 1) || (p === "" && i === parts.length - 1) ||
          /[A-Za-z]$/.test(parts[i - 1]) ? "(.*?)" : "(.+?)") + p, "") + "$", "s");   // (a value at the very end may be nothing: an "s")
      d.values.add(tx);
      const pat = { re, tx };
      // Indexed by the words before the first {}, so each piece of text tries only a few.
      const head = parts[0].slice(0, 2);
      if (head.length === 2) {
        if (!d.patterns.has(head)) d.patterns.set(head, []);
        d.patterns.get(head).push(pat);
      } else d.loose.push(pat);
    }
  },
};
// Help (guides, questions and answers, words, About) is translated as whole documents in
// lang/help.<code>.js: each replaces the English of the same guide, question or word.
I18N.helpText = function (t) {
  if (typeof HELP === "undefined" || !t) return;
  for (const g of HELP.guides) {
    const x = (t.guides || {})[g.id];
    if (x) { if (x.title) g.title = x.title; if (x.body) g.body = x.body; }
  }
  (t.faq || []).forEach((x, i) => { if (HELP.faq[i] && x) Object.assign(HELP.faq[i], x); });
  (t.terms || []).forEach((x, i) => { if (HELP.terms[i] && x) Object.assign(HELP.terms[i], x); });
  HELP.translated = true;
};
function norm(s) { return String(s).replace(/\s+/g, " ").trim(); }

// What people typed or named is never translated: environments, accounts, categories,
// payees and people. Their names are collected as the page loads (keepAsTyped); text that is
// exactly one of them stays as it is, also inside a sentence ("Transfer to {}").
const I18N_KEEP = new Set();
function keepAsTyped(names) {
  for (const n of names) if (n != null && typeof n !== "object" && String(n).trim()) I18N_KEEP.add(norm(n));
}
// Every answer from the server adds the names in it (fields that hold what people typed).
const I18N_DATA_FIELDS = new Set(["name", "full_name", "parent_name", "payee", "account_name", "to_account_name",
  "transfer_account_name", "env_name", "category_name", "parent_category_name", "display_name", "username", "memo",
  "employer", "shared_by", "note", "x_label", "title", "institution", "contact", "number"]);
// (paystub line names aren't here: most are MoneyThistle's own, "Gross pay", "Other deductions")
// (notes MoneyThistle itself writes in those fields: these are translated)
const I18N_SERVER_TEXT = new Set(["made when the account moved", "made through a shared account (ends when the share ends)"]);
function keepFromAnswer(data, depth) {
  depth = depth || 0;
  if (!data || typeof data !== "object" || depth > 6) return;
  if (Array.isArray(data)) { for (const x of data) keepFromAnswer(x, depth + 1); return; }
  for (const [k, v] of Object.entries(data)) {
    if (typeof v === "string") {
      // (a budget line for a loan is named "Loan payment: <the loan>": only the loan's name is kept)
      if (I18N_DATA_FIELDS.has(k) && v.trim() && !I18N_SERVER_TEXT.has(norm(v))) I18N_KEEP.add(norm(v.replace(/^Loan payment: /, "")));
    }
    else if (v && typeof v === "object") keepFromAnswer(v, depth + 1);
  }
}

// Categories are the one kind of name with a name per language (set in a category's details;
// the starting categories come with all of them). Where the server writes a category's name
// into text ("Bills : Electricity" in a register), it's shown with the person's language's
// name. Names of environments, accounts, payees and people are never changed, even when one
// is spelled like a category.
const I18N_CATS = new Map();    // a category's own name or full name -> its name in this language
const I18N_NAMES = new Set();   // names that aren't categories
let I18N_CAT_SRC = [[], []];
function catName(c) { return (c && c.names && c.names[LANG]) || (c && c.name) || ""; }
function i18nCategories(cats, otherNames) {
  if (cats) I18N_CAT_SRC = [cats, otherNames || []];
  [cats, otherNames] = I18N_CAT_SRC;
  I18N_CATS.clear(); I18N_NAMES.clear();
  for (const n of otherNames) if (n != null && String(n).trim()) I18N_NAMES.add(norm(n));
  const byId = new Map(cats.map(c => [c.id, c]));
  const seen = new Map();   // own name -> its name here (null: two categories disagree)
  for (const c of cats) {
    const p = c.parent_id && byId.get(c.parent_id);
    const full = p ? catName(p) + " : " + catName(c) : catName(c);
    if (c.full_name && full !== c.full_name) I18N_CATS.set(norm(c.full_name), full);
    const k = norm(c.name), n = catName(c);
    if (!seen.has(k)) seen.set(k, n); else if (seen.get(k) !== n) seen.set(k, null);
  }
  for (const [k, n] of seen) if (n != null && n !== k && !I18N_CATS.has(k)) I18N_CATS.set(k, n);
  for (const n of I18N_CATS.values()) I18N_KEEP.add(norm(n));
  I18N_CACHE.clear();
}
function trCategory(key) {
  if (!I18N_CATS.size || I18N_NAMES.has(key)) return null;
  const c = I18N_CATS.get(key);
  return c == null ? null : c;
}
const i18nOn = () => LANG !== "en" || I18N_CATS.size > 0;

// The translation of one piece of English text (itself when there's none).
function tr(en, fixedChoice) {
  if (en == null) return en;
  const d = I18N.dicts[LANG];
  const key = norm(en);
  // (a fixed choice, like an account type, is never a name someone typed, even when it's
  // spelled like one: "Loan" the type and "Loan" a category)
  if (fixedChoice) { const x = d && d.exact.get(key); if (x != null) return x; }
  const cat = fixedChoice ? null : trCategory(key);
  if (cat != null) return cat;
  if (LANG === "en" || !d) return en;
  if (I18N_KEEP.has(key)) return en;
  let r = I18N_CACHE.get(key);
  if (r === undefined) {
    r = trWhole(key, d, 0);
    if (I18N_CACHE.size > 20000) I18N_CACHE.clear();
    I18N_CACHE.set(key, r);
  }
  if (r == null) { i18nMissed(en); return en; }
  return r;
}
const I18N_CACHE = new Map();   // text -> its translation (null: none), for this language
// Nothing to translate: no letters, a name someone gave, a number, an address or a code.
function i18nBare(s) {
  return !s || !/[A-Za-z]/.test(s) || I18N_KEEP.has(s) || /^(https?:\/\/|www\.|[\w.+-]+@)/.test(s) ||
    // a date already written in the person's language: "23 de nov. de 2026", "15 nov. 2026", "novembro de 2026"
    /^(\d{1,2}\.?\s+(de\s+)?)?[A-Za-zÀ-ÿ]{3,12}\.?,?(\s+de)?(\s+\d{1,2},)?\s+\d{4}(,?\s+\d{1,2}:\d{2})?$/.test(s) ||
    /^[A-Z]{3}$/.test(s) || /^[\d\s.,:/$€%()+\-−≈#]*[A-Za-z]{0,3}\$?[\d\s.,:/$€%()+\-−]*$/.test(s) && /\d/.test(s);
}
// A piece of text as a whole, then (when that fails) in parts: the halves around " · ", a
// list's items around ", ", what's inside brackets, without a final ":" or ".". Parts are
// only used when every one of them is translated (or is a name or a number), so a sentence
// is never left half in English. null when there's no translation.
function trWhole(key, d, depth, inner) {
  const cat = trCategory(key);
  if (cat != null) return cat;
  if (i18nBare(key)) return key;
  const hit = d.exact.get(key);
  if (hit != null) return hit;
  // A pattern counts first only when everything it took in is a name, a number or translated.
  const p = trPattern(key, d, depth, true);
  if (p != null) return p;
  if (depth > 3) return inner ? null : trPattern(key, d, depth, false);
  for (const sep of [" · ", " — ", ", ", "; "]) {
    if (!key.includes(sep)) continue;
    const parts = key.split(sep).map(x => x.trim());
    const out = parts.map(x => x ? trWhole(x, d, depth + 1, inner) : x);
    if (out.every(x => x != null)) return out.join(sep);
  }
  let m = key.match(/^([(\[«"“])(.*)([)\]»"”])$/);
  if (m) { const t = trWhole(m[2].trim(), d, depth + 1, inner); if (t != null) return m[1] + t + m[3]; }
  m = key.match(/^(.*?)([:.!?…]+)$/);
  if (m && m[1]) { const t = trWhole(m[1].trim(), d, depth + 1, inner); if (t != null) return t + m[2]; }
  m = key.match(/^([·•+−\-–⇄⟳⚑⚠✎📷🧾🗂●▲▼◀▶↳→:;,.\s]+)(.*)$/u);
  if (m && m[2]) { const t = trWhole(m[2], d, depth + 1, inner); if (t != null) return m[1] + t; }
  m = key.match(/^(.*?)(\s*[▾▴▲▼⟳↗→◀▶,;(\[]+)$/u);
  if (m && m[1]) { const t = trWhole(m[1], d, depth + 1, inner); if (t != null) return t + m[2]; }
  // Last (for a whole piece of text, not part of one): a pattern even if a name it took in
  // isn't known yet.
  return inner ? null : trPattern(key, d, depth, false);
}
// Checking the translations: with localStorage "hl-i18n-audit" set to "1", every piece of text
// shown without a translation is listed (offscreen, for a screen reader or an automated check).
const I18N_MISSES = new Set();
function i18nMissed(en) {
  // (on with localStorage "hl-i18n-audit" = "1", or "?i18naudit" in the page's address)
  let on = /[?&]i18naudit/.test(location.search);
  try { on = on || localStorage.getItem("hl-i18n-audit") === "1"; } catch (e) { }
  const k = norm(en);
  const d = I18N.dicts[LANG];
  if (!on || !k || i18nBare(k) || I18N_MISSES.has(k) || (d && d.values.has(k)) || /\d{1,2} de \w+\.? de \d{4}/.test(k)) return;
  I18N_MISSES.add(k);
  clearTimeout(i18nMissed.t);
  i18nMissed.t = setTimeout(() => {
    let box = document.getElementById("i18nAudit");
    if (!box) {
      box = document.createElement("div");
      box.id = "i18nAudit"; box.setAttribute("translate", "no"); box.setAttribute("aria-label", "Not translated");
      box.style.cssText = "position:absolute;left:-10000px;top:0;width:1px;height:1px;overflow:hidden";
      document.body.appendChild(box);
    }
    box.setAttribute("role", "note");
    box.setAttribute("aria-label", "MISSES: " + [...I18N_MISSES].join(" ‖ "));
  }, 300);
}
function trPattern(key, d, depth, strict) {
  const tryPats = list => {
    for (const p of list || []) {
      const m = key.match(p.re);
      if (m) {
        // "{}" takes the values in order; "{2}" a given one (a translation may leave some out
        // or change their order).
        let i = 1, gaps = 0, words = 0;
        const out = p.tx.replace(/\{(\d*)\}/g, (_, n) => {
          const v = m[n ? +n : i++] || "";
          // A value is a name or a number as it is, or words of its own ("later", ": then ...").
          const cv = trCategory(norm(v));
          if (cv != null) return v.match(/^\s*/)[0] + cv + v.match(/\s*$/)[0];
          if (!v.trim() || I18N_KEEP.has(norm(v))) return v;
          const t = (depth || 0) < 3 ? trWhole(norm(v), d, (depth || 0) + 1, true) : d.exact.get(norm(v));
          if (t == null && /[a-z]{2}/.test(v)) {
            // Left as it was: fine for what looks like a name ("Car Loan", "Northwind Payroll"),
            // not for English words ("the budget a paycheck counts...").
            if (/\b(the|a|an|of|to|in|is|are|and|or|for|with|its|as|your|you|this|that|be|on|at|from|by|it|not|each|when)\b/i
              .test(v)) words++; else gaps++;
          }
          return t != null ? v.match(/^\s*/)[0] + t + v.match(/\s*$/)[0] : v;
        });
        if (words || (strict && gaps)) continue;
        if (!gaps) return out;
        // (otherwise: the one leaving the fewest English words, and among those the longest)
        const own = p.tx.replace(/\{\d*\}/g, "").length;
        if (!best || gaps < best.gaps || (gaps === best.gaps && own > best.own)) best = { out, gaps, own };
      }
    }
    return best ? best.out : null;
  };
  let best = null;
  return tryPats(d.patterns.get(key.slice(0, 2))) || (key.length < 160 ? tryPats(d.loose) : null);
}
// Translated text keeps the spaces around the original (they separate it from bold words).
function trKeep(s, fixedChoice) {
  const t = tr(s, fixedChoice);
  if (t === s) return s;
  const lead = s.match(/^\s*/)[0], trail = s.match(/\s*$/)[0];
  return lead + t + trail;
}

// ---------- translating the page as it's drawn ----------
const I18N_ATTRS = ["title", "placeholder", "aria-label", "alt", "label"];
const i18nDone = new WeakMap();   // node -> the text it was given, so it isn't done twice
function skipEl(el) {
  for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
    if (e.getAttribute("translate") === "no" || e.tagName === "SCRIPT" || e.tagName === "STYLE" || e.tagName === "TEXTAREA") return true;
  }
  return false;
}
function trText(node) {
  const v = node.nodeValue;
  if (!v || i18nDone.get(node) === v || !/[A-Za-z]/.test(v)) return;
  if (skipEl(node.parentElement)) return;
  // A choice without its own value is sent as its text (keep sending the English); those
  // are the app's own fixed lists, never names.
  const p = node.parentElement;
  const fixed = p && p.tagName === "OPTION" && (!p.hasAttribute("value") || p.dataset.en === v.trim());
  const t = trKeep(v, fixed);
  i18nDone.set(node, t);
  if (t === v) return;
  if (p && p.tagName === "OPTION" && !p.hasAttribute("value")) { p.setAttribute("value", v.trim()); p.dataset.en = v.trim(); }
  node.nodeValue = t;
}
function trAttrs(el) {
  if (skipEl(el)) return;
  for (const a of I18N_ATTRS) {
    const v = el.getAttribute(a);
    if (v && /[A-Za-z]/.test(v)) { const t = tr(v); if (t !== v) el.setAttribute(a, t); }
  }
  if (el.tagName === "INPUT" && (el.type === "button" || el.type === "submit") && el.value) {
    const t = tr(el.value); if (t !== el.value) el.value = t;
  }
}
function trTree(root) {
  if (!i18nOn() || !root) return;
  if (root.nodeType === 3) { trText(root); return; }
  if (root.nodeType !== 1 && root.nodeType !== 11) return;
  if (root.nodeType === 1) trAttrs(root);
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    if (n.nodeType === 3) trText(n);
    else if (n.attributes.length) trAttrs(n);
  }
}
let i18nObserver = null;
function watchPage() {
  if (i18nObserver) i18nObserver.disconnect();
  i18nObserver = null;
  if (!i18nOn()) return;
  trTree(document.body);
  document.title = tr(document.title);
  i18nObserver = new MutationObserver(list => {
    for (const m of list) {
      if (m.type === "childList") m.addedNodes.forEach(trTree);
      else if (m.type === "characterData") trText(m.target);
      else if (m.type === "attributes") trAttrs(m.target);
    }
  });
  i18nObserver.observe(document.body, { subtree: true, childList: true, characterData: true,
    attributes: true, attributeFilter: I18N_ATTRS });
}

// The language for this person: their choice, else this browser's when it's one of these.
function pickLang(choice) {
  if (choice && LANGS.some(l => l[0] === choice)) return choice;
  const nav = (navigator.languages || [navigator.language || "en"]).map(x => String(x).slice(0, 2).toLowerCase());
  return nav.find(c => LANGS.some(l => l[0] === c)) || "en";
}
// Switch to a language, loading its dictionary first. Returns once the page is translated.
async function setLang(choice) {
  const code = pickLang(choice);
  const row = LANGS.find(l => l[0] === code);
  if (code !== "en" && !I18N.dicts[code]) {
    const load = src => new Promise(res => {
      const s = document.createElement("script");
      s.src = src; s.onload = res; s.onerror = res;
      document.head.appendChild(s);
    });
    await Promise.all([load(`/lang/${code}.js`), load(`/lang/help.${code}.js`)]);
  }
  const changed = code !== LANG;
  LANG = code; LOCALE = row[2];
  document.documentElement.lang = LOCALE;
  try { localStorage.setItem("hl-lang", choice || ""); } catch (e) { }
  i18nCategories();
  watchPage();
  return changed;
}

// An amount as typed in any common style: "1,234.56", "1.234,56", "1 234,56", "R$ 80". The
// last of "," and "." is the decimal mark when both appear; one alone is the decimal mark
// unless exactly three digits follow it (then it groups thousands). NaN when there's no number.
function parseAmount(v) {
  let s = String(v == null ? "" : v).replace(/[^\d,.\-]/g, "");
  if (!/\d/.test(s)) return NaN;
  if (s.includes(",") && s.includes(".")) {
    const dec = s.lastIndexOf(",") > s.lastIndexOf(".") ? "," : ".";
    s = s.split(dec === "," ? "." : ",").join("").replace(dec, ".");
  } else if (s.includes(",") || s.includes(".")) {
    const mark = s.includes(",") ? "," : ".";
    const parts = s.split(mark);
    s = parts.length > 2 || parts[parts.length - 1].length === 3 ? parts.join("") : parts.join(".");
  }
  return parseFloat(s);
}
