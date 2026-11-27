"use strict";
// MoneyThistle browser screens. Plain JavaScript, no outside libraries.

const S = { meta: null, cats: [], accounts: [], payees: [] };
const NEEDED_API = 7;  // matches API_VERSION in server.py
const STALE_MSG = "MoneyThistle was updated, but an older copy of its server is still running. " +
  "Restart MoneyThistle (or the Docker container) and reload this page.";
const NOT_ANSWERING = "MoneyThistle isn't answering. Restart it on the computer it runs on (close it and start it again; " +
  "with Docker: docker restart moneythistle), then reload this page.";
const PALETTE = ["#1f8a8a", "#1c4b8a", "#e08a2e", "#7b5ea7", "#c2352b", "#4c9a2a", "#d4b72c", "#5aa1d6",
  "#a0522d", "#8f9bb3", "#e46aa0", "#2f5d50"];

// ---------- helpers ----------
class NeedSignIn extends Error { }
async function api(method, url, body, share) {
  const opt = { method, headers: { "X-HomeLedger": "1" } };
  // Money data belongs to the environment chosen at the top of the page, or, while an
  // account shared into it is open, to that account's own environment (via the share).
  const sc = share || S.shareCtx;
  if (sc) {
    opt.headers["X-HomeLedger-Env"] = String(sc.env_id);
    if (sc.share_id) opt.headers["X-HomeLedger-Share"] = String(sc.share_id);   // { env_id } alone: another of my environments
  } else if (S.env) opt.headers["X-HomeLedger-Env"] = String(S.env);
  if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  // A server that stops answering says so, instead of leaving the page on "Loading…".
  // (Only for reading: sending a big photo on a slow connection may take longer.)
  let timer = null;
  if (method === "GET" && window.AbortController) {
    const ac = new AbortController(); opt.signal = ac.signal;
    timer = setTimeout(() => ac.abort(), 30000);
  }
  let r;
  try { r = await fetch(url, opt); }
  catch (e) {
    if (e && e.name === "AbortError") throw new Error(NOT_ANSWERING);
    throw new Error("Can't reach MoneyThistle. Is it running, and is this device on the same network?");
  } finally { clearTimeout(timer); }
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (r.ok && data && typeof data === "object" && url !== "/api/meta") keepFromAnswer(data);   // never translated
  if (r.status === 401 && url !== "/api/login") throw new NeedSignIn((data && data.error) || "Please sign in");
  if (!r.ok) {
    const err = new Error((data && data.error) || ("HTTP " + r.status));
    if (data && data.field) err.field = data.field;   // the form field it's about
    throw err;
  }
  return data;
}
function envRole() { const e = (S.me && S.me.envs || []).find(e => e.id === S.env); return e ? e.role : null; }
function canEdit() { return ["owner", "editor"].includes(envRole()); }
const GET = (u) => api("GET", u);
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
// Money: amounts are hundredths of their account's currency. `code` is a currency code
// (USD, BRL...) or anything with a .currency (an account, an entry); the main currency
// of this environment when left out. The main currency shows its short symbol ($), others
// the one that can't be mistaken for it (R$, CA$, €).
function homeCur() { return (S.money && S.money.home) || "USD"; }
const fmtCache = {};
function moneyFormat(code) {
  const key = LOCALE + "|" + code;
  if (!fmtCache[key]) {
    try {
      fmtCache[key] = new Intl.NumberFormat(LOCALE, { style: "currency", currency: code,
        currencyDisplay: code === homeCur() ? "narrowSymbol" : "symbol" });
    } catch (e) { fmtCache[key] = new Intl.NumberFormat(LOCALE, { style: "currency", currency: code }); }
  }
  return fmtCache[key];
}
function fmt(c, plain, code) {
  if (code && typeof code === "object") code = code.currency;
  code = code || homeCur();
  const n = (c || 0) / 100;
  let t = moneyFormat(code).format(n);
  // Someone's own symbol for the main currency (Settings, older choice) still applies.
  if (code === homeCur() && S.ui && S.ui.currency) t = (n < 0 ? "-" : "") + S.ui.currency + moneyFormat(code).formatToParts(Math.abs(n))
    .filter(p => p.type !== "currency" && p.type !== "literal").map(p => p.value).join("");
  if (plain) return t;
  return `<span class="${n < 0 ? "neg" : ""}">${t}</span>`;
}
// Money moving between accounts in two currencies: ask what arrived. The rate used last time
// for this pair (or the rough rate) fills it in as a guess. Resolves to the amount typed, or
// null when cancelled.
function lastRate(from, to) {
  try { const r = JSON.parse(localStorage.getItem("hl-rate-" + from + "-" + to) || "null"); return r > 0 ? r : null; } catch (e) { return null; }
}
function keepRate(from, to, sent, got) {
  const s = Math.abs(sent), g = Math.abs(parseAmount(got) * 100);
  if (s > 0 && g > 0) try { localStorage.setItem("hl-rate-" + from + "-" + to, String(g / s)); } catch (e) { }
}
function guessReceived(fromCur, toCur, cents) {
  let r = lastRate(fromCur, toCur);
  if (!r && S.money) {
    const rate = c => c === homeCur() ? 1 : parseFloat((S.money.rates || {})[c] || "0");
    if (rate(fromCur) && rate(toCur)) r = rate(fromCur) / rate(toCur);
  }
  return r ? dollars(Math.round(Math.abs(cents) * r)) : "";
}
function askReceived(from, to, cents) {
  return new Promise(resolve => {
    let answered = false;
    const p = dialog(tr("Two currencies"), `<p>${esc(from.name)} (${from.currency}) → ${esc(to.name)} (${to.currency})</p>
      <div class="form"><div><label>${esc(tr("Sent"))}</label><input class="num" disabled value="${esc(fmt(cents, true, from))}"></div>
      <div><label class="req">${esc(tr("Amount received"))} (${to.currency})</label><input name="received" class="num" placeholder="0.00" value="${guessReceived(from.currency, to.currency, cents)}"></div></div>
      <p class="small muted">${esc(tr("Check the amount that actually arrived: it's used as it is, with no exchange rate looked up."))}</p>`,
      [{ label: "Cancel" }, { label: "Save", cls: "primary", action: async root => {
        const v = q("[name=received]", root).value;
        if (!(parseAmount(v) > 0)) { const e = new Error(tr("Enter the amount received")); e.field = "received"; throw e; }
        keepRate(from.currency, to.currency, cents, v);
        answered = true; resolve(v);
      } }]);
    Promise.resolve(p).then(() => { if (!answered) resolve(null); });
  });
}
// A list of accounts' total, one amount per currency ("$1,200.00 · R$ 3.400,00").
function sumByCur(list) {
  const by = {};
  for (const a of list) { const c = a.currency || homeCur(); by[c] = (by[c] || 0) + (a.balance || 0); }
  const codes = Object.keys(by).sort((x, y) => (x !== homeCur()) - (y !== homeCur()) || x.localeCompare(y));
  if (!codes.length) return fmt(0);
  return codes.map(c => fmt(by[c], false, c)).join(" · ");
}
// Net worth: in the main currency; with other currencies, each one's own total too, and the
// combined figure marked approximate (rough rates) or saying which have no rate yet.
function netWorthHtml(d) {
  const m = d.money;
  const plain = `<div class="networth"><span>Net worth</span><span class="num">${fmt(d.net_worth)}</span></div>
      <div class="small muted" style="margin-top:4px;display:flex;justify-content:space-between"><span>Assets ${fmt(d.assets, true)}</span><span>Debts ${fmt(-d.debts, true)}</span></div>`;
  if (!m || m.currencies.length < 2) return plain;
  const rows = m.currencies.map(c => `<div class="acctrow small"><span>${esc(curName(c.currency))}</span><span class="num">${fmt(c.net_worth, false, c.currency)}</span></div>`).join("");
  const note = m.left_out.length
    ? `<a href="#/settings/look" class="small">${esc(tr("Not counted (no rough rate yet):"))} ${m.left_out.map(esc).join(", ")}</a>`
    : `<span class="small muted">${esc(tr("Approximate: other currencies at your rough rates"))}</span>`;
  return `<div class="networth"><span>Net worth${m.approximate ? " ≈" : ""}</span><span class="num">${fmt(d.net_worth)}</span></div>
      <div style="margin-top:4px">${note}</div>
      <div class="small muted" style="margin-top:4px;display:flex;justify-content:space-between"><span>Assets ${fmt(d.assets, true)}</span><span>Debts ${fmt(-d.debts, true)}</span></div>
      <details class="cur-split" open style="margin-top:6px"><summary class="small">${esc(tr("By currency"))}</summary>${rows}</details>`;
}
// A currency's name in the person's language ("Brazilian real"), and its code.
function curName(code) {
  try { return new Intl.DisplayNames([LOCALE], { type: "currency" }).of(code); } catch (e) { return code; }
}
function curOptions(selected) {
  const codes = (S.money && S.money.codes) || ["USD"];
  return codes.map(c => `<option value="${c}" ${c === selected ? "selected" : ""}>${esc(curName(c))} (${c})</option>`).join("");
}
// The other side of a transfer, when it's in another currency: "R$ 1.080,00 arrived".
function otherSide(t) {
  if (!t.transfer_currency || !t.currency || t.transfer_currency === t.currency || t.transfer_amount == null) return "";
  return ` <span class="pill" title="${esc(tr("The other account is in another currency"))}">${fmt(Math.abs(t.transfer_amount), true, t.transfer_currency)} ${t.amount < 0 ? tr("arrived") : tr("left")}</span>`;
}
function dollars(c) { return ((c || 0) / 100).toFixed(2); }
function todayISO() { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
function niceDate(iso) {
  if (!iso) return "";
  const style = (S.ui && S.ui.date_style) || "system";
  if (style === "iso") return iso;
  const d = new Date(iso + "T00:00:00");
  const [y, m, day] = iso.split("-");
  if (style === "eu") return `${day}.${m}.${y}`;
  if (style === "uk") return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  if (style === "us") return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return d.toLocaleDateString(LOCALE, { month: "short", day: "numeric", year: "numeric" });
}

// ---------- theme ----------
const ACCENTS = [["Blue", "#1c4b8a"], ["Teal", "#1f8a8a"], ["Green", "#2e7d4f"], ["Purple", "#6b4fa3"],
  ["Rose", "#b03a6b"], ["Red", "#b23a2e"], ["Orange", "#c46a1a"], ["Slate", "#475569"]];
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
function mix(a, b, t) { const x = hexToRgb(a), y = hexToRgb(b); return "#" + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, "0")).join(""); }
function applyTheme(ui) {
  ui = ui || {};
  const mode = ui.theme === "auto" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : (ui.theme || "light");
  const accent = /^#[0-9a-f]{6}$/i.test(ui.accent || "") ? ui.accent : "#1c4b8a";
  const root = document.documentElement;
  root.dataset.theme = mode;
  const dark = mode === "dark";
  const vars = {
    "--accent": dark ? mix(accent, "#ffffff", 0.15) : accent,
    "--navy": mix(accent, "#000000", dark ? 0.45 : 0.35),
    "--heading": dark ? mix(accent, "#ffffff", 0.55) : mix(accent, "#000000", 0.35),
    "--sel": dark ? mix(accent, "#18222f", 0.7) : mix(accent, "#ffffff", 0.87),
    "--focus": mix(accent, dark ? "#18222f" : "#ffffff", 0.5),
  };
  for (const [k, v] of Object.entries(vars)) root.style.setProperty(k, v);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = vars["--navy"];
  try { localStorage.setItem("hl-ui", JSON.stringify({ theme: ui.theme, accent })); } catch (e) { }
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (S.ui && S.ui.theme === "auto") applyTheme(S.ui); });
function monthName(ym) { const d = new Date(ym + "-01T00:00:00"); return d.toLocaleDateString(LOCALE, { month: "long", year: "numeric" }); }
function shortMonth(ym) { const d = new Date(ym + "-01T00:00:00"); return d.toLocaleDateString(LOCALE, { month: "short" }); }
function toast(msg, err) {
  const t = document.getElementById("toast");
  // While a dialog is open, the message goes inside it: anything else sits behind it.
  const d = document.getElementById("dlg");
  const home = d && d.open ? d : document.body;
  if (t.parentElement !== home) home.appendChild(t);
  t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(t._h); t._h = setTimeout(() => t.className = "", err ? 4500 : 2200);
}
// ---------- Simple or Everything (each person's choice) and "More options" folds ----------
// Simple folds extras away (and hides a few features most people never need); Everything
// shows it all. Each fold remembers, for each person, whether they opened or closed it.
function simpleMode() { return !S.ui || S.ui.detail !== "full"; }
function foldOpen(key) {
  const f = (S.ui && S.ui.folds) || {};
  return Object.prototype.hasOwnProperty.call(f, key) ? !!f[key] : !simpleMode();
}
function moreFold(key, inner, filled, label) {
  return `<details class="more-fold" data-fold="${key}" ${foldOpen(key) ? "open" : ""}>
    <summary>${esc(label || "More options")}${filled ? ' <span class="fold-hint" title="Something in here is filled in">● filled in</span>' : ""}</summary>
    <div class="more-body">${inner}</div></details>`;
}
let foldPending = {}, foldTimer = null;
function rememberFold(key, open) {
  if (!S.ui || foldOpen(key) === open) return;
  S.ui.folds = Object.assign({}, S.ui.folds, { [key]: open });
  foldPending[key] = open;
  clearTimeout(foldTimer);
  foldTimer = setTimeout(() => { const f = foldPending; foldPending = {}; api("PUT", "/api/settings", { folds: f }).catch(() => {}); }, 500);
}
// (toggle doesn't bubble: caught on its way down.)
document.addEventListener("toggle", e => {
  const d = e.target;
  // (data-auto: opened by the page itself, e.g. a paystub with several lines; not a choice)
  if (d && d.matches && d.matches("details.more-fold[data-fold]") && !d.dataset.auto) rememberFold(d.dataset.fold, d.open);
}, true);

// Where a page draws: the main area, or (inside Settings) the space under its sub-tabs.
function view() { return (S.viewTarget && S.viewTarget.isConnected && S.viewTarget) || document.getElementById("view"); }
function q(sel, root) { return (root || document).querySelector(sel); }
function qa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

async function loadBasics() {
  S.meta = await GET("/api/meta");
  if (q("#aboutVer") && S.meta.version) q("#aboutVer").textContent = " " + S.meta.version;
  S.stale = !S.meta.api_version || S.meta.api_version < NEEDED_API;
  // The screens were updated since this page opened: it's still running the old ones.
  if (!S.pageUi) S.pageUi = S.meta.ui_build;
  S.pageOld = !!(S.meta.ui_build && S.pageUi && S.meta.ui_build !== S.pageUi);
  if (S.meta.needs_setup) throw new NeedSignIn("setup");
  S.me = await GET("/api/me");
  // Pick the environment: the last one used here, if still allowed, else the first.
  const ids = S.me.envs.map(e => e.id);
  const saved = +localStorage.getItem("hl-env");
  S.env = ids.includes(S.env) ? S.env : (ids.includes(saved) ? saved : (ids[0] || null));
  const ui = GET("/api/settings").catch(() => ({ theme: "light", accent: "#1c4b8a", currency: "", date_style: "system", due_days: 14 }));
  if (S.env) {
    [S.cats, S.accounts, S.payees, S.ui, S.money] = await Promise.all([GET("/api/categories"), GET(S.shareCtx && S.shareCtx.forBills ? "/api/accounts?scope=bills" : "/api/accounts"), GET("/api/payees"), ui,
      GET("/api/money").catch(() => ({ home: "USD", rates: {}, codes: ["USD"] }))]);
  } else {
    S.cats = []; S.accounts = []; S.payees = []; S.ui = await ui; S.money = { home: "USD", rates: {}, codes: ["USD"] };
  }
  // Names people gave things stay as they are in every language.
  keepAsTyped([...(S.me.envs || []).map(e => e.name), S.me.user.display_name, S.me.user.username,
    ...S.accounts.map(a => a.name), ...S.cats.flatMap(c => [c.name, c.full_name]), ...S.payees.map(p => p.name)]);
  i18nCategories(S.cats, [...(S.me.envs || []).map(e => e.name), S.me.user.display_name, S.me.user.username,
    ...S.accounts.map(a => a.name), ...S.payees.map(p => p.name)]);
  await setLang(S.ui.lang);
  applyTheme(S.ui);
  drawTopBar();
  sampleBar();
  showAddresses();
}

// ---------- Start fresh ----------
// While an environment holds the made-up sample data, a bar on every page says so and offers to
// start fresh. Settings > Your data can start any environment fresh (its name typed to confirm).
function curEnv() { return ((S.me && S.me.envs) || []).find(e => e.id === S.env) || {}; }
function sampleBar() {
  const old = document.getElementById("sampleBar");
  if (old) old.remove();
  const env = curEnv();
  if (!env.sample_data) return;
  const bar = document.createElement("div");
  bar.id = "sampleBar"; bar.className = "samplebar noprint";
  bar.innerHTML = `<span>You're exploring sample data: made-up accounts and entries.</span>
    ${envRole() === "owner" ? `<button type="button" class="primary small" id="sampleFresh">Start fresh with my own money</button>`
      : `<span class="small">An owner of this environment can start it fresh.</span>`}`;
  document.getElementById("view").before(bar);
  if (q("#sampleFresh")) q("#sampleFresh").onclick = () => startFresh();
}
async function startFresh() {
  const env = curEnv();
  let done;
  if (env.sample_data) {
    done = await dialog("Start fresh", `<p>The sample data goes, and this environment is ready for your own accounts, as on the
      first day. Your sign-in and settings stay.</p>`,
      [{ label: "Cancel", value: false }, { label: "Start fresh", cls: "primary", action: async () => { await api("POST", `/api/envs/${env.id}/start-fresh`, {}); return true; } }]);
  } else {
    done = await dialog("Start fresh", `<p>This clears this environment back to a new start: every account, entry, scheduled
      item, budget amount, receipt and change to its categories. People, sign-ins, backup settings and your other environments
      stay as they are.</p>
      <p class="small muted"><span>A copy of what's there now is kept in MoneyThistle's data folder.</span>
        ${S.me.user.is_admin ? "<span>To be safe, make a backup first (Settings, Backups).</span>" : ""}</p>
      <div class="form"><div class="wide"><label class="req">Type the environment's name to confirm</label>
        <input name="confirm" autocomplete="off" spellcheck="false" placeholder="${esc(env.name)}"></div></div>`,
      [{ label: "Cancel", value: false }, { label: "Start fresh", cls: "danger", action: async root => {
        await api("POST", `/api/envs/${env.id}/start-fresh`, { confirm: q("[name=confirm]", root).value }); return true; } }]);
  }
  if (!done) return;
  toast("Started fresh");
  await loadBasics();
  location.hash = "#/home";
  render();
}

// ---------- the coffee cup: donations, never asked for ----------
// A small cup in the top bar and one quiet line at the bottom of the page (a different one
// each day), both a plain link to the maker's Buy Me a Coffee page: nothing is loaded from
// there unless someone clicks. Each person can hide them (Settings › Look); an administrator
// can hide them for everyone.
const COFFEE_URL = "https://buymeacoffee.com/itsmnlop";
const COFFEE_LINES = [
  "MoneyThistle is free and open source. If it helps, you can buy me a coffee.",
  "One less subscription to track in here. MoneyThistle is free, and a coffee is entirely optional.",
  "Built in my spare time and given away. If it earns its keep, a coffee is welcome.",
  "If MoneyThistle saves you a spreadsheet headache, consider buying me a coffee.",
  "MoneyThistle costs nothing to use. Coffee donations just help pay for the time that goes into it.",
  "For the record, I drink tea. Buy Me a Coffee is just what the service is called, and it still helps.",
  "No ads, no subscription, nothing about you sold. If that's worth a coffee, here's the jar.",
  "Your money stays on your computer. A coffee is the only thing that leaves, and only if you want.",
  "Balanced the books this month? A coffee is a fine way to celebrate. Entirely optional.",
  "Made by one person who also forgets to record receipts. Coffee welcome, never expected.",
];
const CUP_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V9z"/><path d="M16 10.5h1.5a2.5 2.5 0 0 1 0 5H16"/><path d="M8 3.5c-.6.8-.6 1.7 0 2.5M12 3.5c-.6.8-.6 1.7 0 2.5"/></svg>`;
function showCoffee() { return !!(S.me && !S.me.coffee_off && !(S.ui && S.ui.coffee === false)); }
function coffeeLine() {
  const d = new Date(), day = Math.floor((d.getTime() - d.getTimezoneOffset() * 60000) / 86400000);   // (a new one each local day)
  return COFFEE_LINES[day % COFFEE_LINES.length];
}
function drawCoffeeNote() {
  const el = q("#coffeeNote");
  if (!el) return;
  el.hidden = !showCoffee();
  el.innerHTML = el.hidden ? "" : `<a href="${COFFEE_URL}" target="_blank" rel="noopener noreferrer" title="Buy me a coffee (optional)">${CUP_ICON}<span>${esc(coffeeLine())}</span></a>`;
}

// Top bar: which environment, who is signed in.
function drawTopBar() {
  const bar = q("#envbar");
  drawCoffeeNote();
  if (!bar || !S.me) return;
  const role = envRole();
  // The environment picker: hidden in Simple while there's only one environment. The coffee
  // cup before it is the first thing to go when the bar gets narrow.
  bar.innerHTML = `${showCoffee() ? `<a class="coffee" href="${COFFEE_URL}" target="_blank" rel="noopener noreferrer" title="Buy me a coffee (optional)" aria-label="Buy me a coffee (optional)">${CUP_ICON}</a>` : ""}${S.me.envs.length > 1 || (S.me.envs.length && !simpleMode()) ? `<select id="envSel" title="Environment">${S.me.envs.map(e =>
      `<option value="${e.id}" ${e.id === S.env ? "selected" : ""}>${esc(e.name)}</option>`).join("")}</select>` : ""}
    ${role === "viewer" ? '<span class="pill">view only</span>' : ""}
    <span class="who">${esc(S.me.user.display_name || S.me.user.username)}</span>
    ${S.me.approvals_waiting ? `<a href="#/settings/people" class="pill amber" title="Connection requests waiting for you">${S.me.approvals_waiting} to approve</a>` : ""}
    <button class="small" id="signOut">Sign out</button>
    ${S.me.user.is_admin && S.meta && S.meta.can_shutdown ? `<button class="small" id="shutDown" title="Shut down MoneyThistle on this computer (it saves and backs up first)" aria-label="Shut down MoneyThistle">⏻ Shut down</button>` : ""}`;
  if (q("#shutDown")) q("#shutDown").onclick = shutDownApp;
  const sel = q("#envSel");
  if (sel) sel.onchange = async () => {
    S.env = +sel.value; localStorage.setItem("hl-env", S.env);
    await loadBasics(); render();
  };
  q("#signOut").onclick = async () => { await api("POST", "/api/logout"); S.me = null; S.env = null; drawCoffeeNote(); location.hash = "#/home"; renderSignIn(false); };
}

const TAGLINE = "A Slightly Better Money App";

// ---------- starting over from a backup ----------
// A whole backup file goes up as it is (it can be large); its password in a header.
async function uploadRestore(url, file, password) {
  const h = { "X-HomeLedger": "1", "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(file.name) };
  if (password) h["X-Backup-Password"] = btoa(unescape(encodeURIComponent(password)));
  const r = await fetch(url, { method: "POST", headers: h, body: file });
  let d = null;
  try { d = await r.json(); } catch (e) { d = null; }
  if (!r.ok) throw new Error((d && d.error) || ("HTTP " + r.status));
  return d;
}
function restoredNotice(r) {
  toast(`Restored. Sign in as before${r.people && r.people.length ? ` (${r.people.join(", ")})` : ""}.`);
  S.meta = null; S.me = null;
  setTimeout(() => { location.hash = "#/home"; location.reload(); }, 1500);
}
function wireStartFromBackup() {
  const err = m => { const e = q("#rsErr"); e.style.display = m ? "" : "none"; e.textContent = m || ""; };
  const busy = (btn, on, label) => { btn.disabled = on; if (label) btn.textContent = label; };
  q("#rsFileForm").onsubmit = async ev => {
    ev.preventDefault(); err("");
    const file = q("#rsFile").files[0];
    if (!file) { err("Choose the backup file first."); return; }
    const btn = q("#rsFileForm button");
    busy(btn, true, "Restoring…");
    try { restoredNotice(await uploadRestore("/api/setup/restore-upload", file, q("#rsFilePw").value)); }
    catch (e) { err(e.message); busy(btn, false, "Restore this file"); }
  };
  const dav = () => ({ url: q("#rsUrl").value.trim(), user: q("#rsUser").value.trim(), password: q("#rsPass").value });
  q("#rsDavForm").onsubmit = async ev => {
    ev.preventDefault(); err("");
    const btn = q("#rsDavForm button");
    busy(btn, true, "Looking…");
    try {
      const r = await api("POST", "/api/setup/webdav-list", dav());
      const list = r.backups || [];
      q("#rsDavList").innerHTML = list.length ? `<div class="small" style="margin:8px 0 4px">Pick one (newest first):</div>
        <div style="max-height:220px;overflow:auto;border:1px solid var(--line);border-radius:6px">${list.map((b, i) => `<label class="check" style="display:flex;padding:4px 8px;margin:0">
          <input type="radio" name="rsPick" value="${esc(b.name)}" ${i ? "" : "checked"}> ${esc(new Date(b.when).toLocaleString(LOCALE))}
          <span class="small muted" style="margin-left:6px">${b.kind === "auto" ? "after changes" : esc(b.kind)}${b.name.endsWith(".enc") ? " · 🔒" : ""}</span></label>`).join("")}</div>
        <div class="form" style="grid-template-columns:1fr;margin-top:8px">
          <div><label>Backup password <span class="muted">(for 🔒 encrypted ones)</span></label><input type="password" id="rsDavPw" autocomplete="off"></div>
          <div><button id="rsDavGo" class="primary" type="button">Restore the chosen backup</button></div></div>
        <div class="small muted">From then on, MoneyThistle keeps backing up to this same folder.</div>`
        : `<p class="small muted">No MoneyThistle backups in that folder.</p>`;
      if (q("#rsDavGo")) q("#rsDavGo").onclick = async () => {
        err("");
        const name = (qa("[name=rsPick]").find(x => x.checked) || {}).value;
        busy(q("#rsDavGo"), true, "Restoring…");
        try { restoredNotice(await api("POST", "/api/setup/restore-webdav", { ...dav(), name, backup_password: q("#rsDavPw").value })); }
        catch (e) { err(e.message); busy(q("#rsDavGo"), false, "Restore the chosen backup"); }
      };
    } catch (e) { err(e.message); }
    busy(btn, false, "Show its backups");
  };
}
function renderSignIn(setup) {
  q("#envbar").innerHTML = ""; q("#where").innerHTML = "";
  qa("#tabs a").forEach(a => a.classList.remove("on"));
  view().innerHTML = `<div class="card" style="max-width:420px;margin:50px auto">
    <div class="signin-brand"><img src="/brand/wordmark-450.png" srcset="/brand/wordmark-450.png 1x, /brand/wordmark-900.png 2x"
      alt="MoneyThistle: ${esc(TAGLINE)}" width="360"></div>
    <h2>${setup ? "Set up MoneyThistle" : "Sign in"}</h2>
    ${setup ? `<p class="small muted">Create the first sign-in. It becomes the administrator and owner of your existing money file.
      Others get their own sign-in under People &amp; access.</p>` : ""}
    <form id="signForm" class="form" style="grid-template-columns:1fr">
      ${setup ? `<div><label>Your name</label><input name="display_name" autocomplete="name"></div>` : ""}
      <div><label>User name</label><input name="username" autocomplete="username" required></div>
      <div><label>Password${setup ? " (8 or more characters)" : ""}</label><input type="password" name="password" autocomplete="${setup ? "new-password" : "current-password"}" required></div>
      ${setup ? `<div><label>Password again</label><input type="password" name="password2" autocomplete="new-password" required></div>` : ""}
      ${setup ? "" : `<div><label class="check" style="margin:0"><input type="checkbox" name="remember"> Keep me signed in on this device</label>
        <div class="small muted">For 30 days, also after the computer restarts. Leave it off on shared devices: you're then signed out when the browser closes, or after an hour without use.</div></div>`}
      ${setup && S.meta && S.meta.desktop_icon_offer ? `<div><label class="check" style="margin:0"><input type="checkbox" name="desktop_icon" checked> Put a MoneyThistle icon on the desktop</label>
        <div class="small muted">It's in the ${navigator.platform.startsWith("Win") ? "Start menu" : "applications menu"} either way. You can change this later in Settings.</div></div>` : ""}
      <div><button class="primary" type="submit">${setup ? "Create and sign in" : "Sign in"}</button></div>
      <div class="notice err" id="signErr" style="display:none;margin:0"></div>
    </form>
    ${setup ? "" : `<p class="small" style="margin:12px 0 0"><a href="#" id="forgotLink">Forgot your password?</a></p><div id="forgotBox"></div>`}</div>
    ${setup ? `<div class="card" style="max-width:420px;margin:-30px auto 50px">
      <details id="startFromBackup"><summary><b>Moving here from another computer or server?</b> Start from a backup instead</summary>
      <p class="small muted">Everything comes back as it was in the backup: accounts, entries, receipts, every environment and
        every sign-in (sign in with your usual user name and password afterwards). Encrypted backups need their backup password.</p>
      <div class="small"><b>A backup file</b> (money-….zip or .zip.enc, copied from Nextcloud or your backup folder)</div>
      <form id="rsFileForm" class="form" style="grid-template-columns:1fr;margin-top:4px">
        <div><input type="file" id="rsFile" accept=".zip,.enc,.db,.gz"></div>
        <div><label>Backup password <span class="muted">(if it's encrypted)</span></label><input type="password" id="rsFilePw" autocomplete="off"></div>
        <div><button type="submit">Restore this file</button></div></form>
      <div class="small" style="margin-top:14px"><b>Or straight from Nextcloud / WebDAV</b> (the backup folder MoneyThistle used)</div>
      <form id="rsDavForm" class="form" style="grid-template-columns:1fr;margin-top:4px">
        <div><label>Folder address</label><input id="rsUrl" placeholder="https://cloud.example.com/remote.php/dav/files/USER/Backups/MoneyThistle"></div>
        <div><label>User name</label><input id="rsUser" autocomplete="off"></div>
        <div><label>Password or app password</label><input type="password" id="rsPass" autocomplete="off"></div>
        <div><button type="submit">Show its backups</button></div></form>
      <div id="rsDavList"></div>
      <div class="notice err" id="rsErr" style="display:none;margin:8px 0 0"></div>
      </details></div>` : ""}`;
  const f = q("#signForm");
  f.querySelector("input").focus();
  if (setup) wireStartFromBackup();
  // Forgot the password: a link by email when mail is set up; otherwise who can help.
  if (q("#forgotLink")) q("#forgotLink").onclick = async e => {
    e.preventDefault();
    const meta = await GET("/api/meta").catch(() => ({}));
    const box = q("#forgotBox");
    const other = `An administrator can set a new password for you under People. Locked out as the only administrator?
      On the computer or server MoneyThistle runs on, run <code>python main.py --reset-password YOUR-USER-NAME</code>
      (with Docker: <code>docker exec -it moneythistle python main.py --reset-password YOUR-USER-NAME</code>).`;
    if (!meta.password_reset) { box.innerHTML = `<p class="small muted">Email isn't set up here, so MoneyThistle can't send a link. ${other}</p>`; return; }
    box.innerHTML = `<form id="forgotForm" class="form" style="grid-template-columns:1fr;margin-top:8px">
        <div><label>Your user name</label><input name="username" autocomplete="username" value="${esc(q("#signForm [name=username]").value)}" required></div>
        <div><button type="submit">Email me a link</button></div></form>
      <p class="small muted" id="forgotMsg">The link goes to the email address in your sign-in (People → Your sign-in). ${other}</p>`;
    q("#forgotForm [name=username]").focus();
    q("#forgotForm").onsubmit = async ev => {
      ev.preventDefault();
      try { const r = await api("POST", "/api/password/forgot", formData(ev.target)); q("#forgotMsg").innerHTML = `<b>${esc(r.message)}</b>`; ev.target.remove(); }
      catch (err) { q("#forgotMsg").textContent = err.message; }
    };
  };
  f.onsubmit = async e => {
    e.preventDefault();
    const d = formData(f);
    try {
      if (setup && d.password !== d.password2) throw new Error("The two passwords don't match");
      await api("POST", setup ? "/api/setup" : "/api/login", d);
      S.meta = null; await render();
    } catch (err) { q("#signErr").style.display = ""; q("#signErr").textContent = err.message; }
  };
}

// The page a "set a new password" email links to (#/reset/<token>): no sign-in needed.
async function renderReset(token) {
  q("#envbar").innerHTML = "";
  qa("#tabs a").forEach(a => a.classList.remove("on"));
  const card = inner => { view().innerHTML = `<div class="card" style="max-width:420px;margin:50px auto">
    <div class="signin-brand"><img src="/brand/wordmark-450.png" alt="MoneyThistle: ${esc(TAGLINE)}" width="360"></div>${inner}</div>`; };
  let who;
  try { who = await GET("/api/password/reset?token=" + encodeURIComponent(token || "")); }
  catch (e) { card(`<h2>Set a new password</h2><div class="notice err">${esc(e.message)}</div><p><a href="#/home">Go to sign in</a></p>`); return; }
  card(`<h2>Set a new password</h2><p class="small muted">For the sign-in <b>${esc(who.username)}</b>. Every device using it will be signed out.</p>
    <form id="resetForm" class="form" style="grid-template-columns:1fr">
      <div><label>New password (8 or more characters)</label><input type="password" name="password" autocomplete="new-password" required></div>
      <div><label>New password again</label><input type="password" name="password2" autocomplete="new-password" required></div>
      <div><button class="primary" type="submit">Set password</button></div>
      <div class="notice err" id="resetErr" style="display:none;margin:0"></div></form>`);
  q("#resetForm [name=password]").focus();
  q("#resetForm").onsubmit = async e => {
    e.preventDefault();
    const d = formData(e.target);
    try {
      if (d.password !== d.password2) throw new Error("The two passwords don't match");
      await api("POST", "/api/password/reset", { token, password: d.password });
      card(`<h2>Password changed</h2><p>Sign in as <b>${esc(who.username)}</b> with your new password.</p>
        <p><a class="btn primary" href="#/home">Sign in</a></p>`);
    } catch (err) { q("#resetErr").style.display = ""; q("#resetErr").textContent = err.message; }
  };
}

// Footer on every page: where this app can be opened (this browser and other devices).
function showAddresses() {
  const here = location.origin + "/";
  const list = [here].concat((S.meta && S.meta.addresses) || []);
  const seen = new Set(), urls = [];
  for (const u of list) { const k = u.replace(/\/?$/, "/"); if (!seen.has(k)) { seen.add(k); urls.push(k); } }
  // localhost / 127.0.0.1 only work on the computer MoneyThistle runs on; a phone needs
  // the computer's network (LAN) or Tailscale address.
  const local = u => /^https?:\/\/(localhost|127\.|\[::1\])/i.test(u);
  // What each address is: Tailscale (100.64.0.0/10), the home network (private
  // ranges), or this computer only.
  // The server lists the address it reaches the network through first; further private
  // addresses are usually virtual adapters (WSL, Hyper-V, VPNs) phones can't reach.
  let homeSeen = false;
  const custom = new Set((S.meta && S.meta.custom_addresses) || []);
  const kinds = new Map(urls.map(u => {
    let k = "network";
    const m = u.match(/^https?:\/\/(\d+)\.(\d+)\./);
    if (custom.has(u)) k = "your address";
    else if (local(u)) k = "this computer";
    else if (m && +m[1] === 100 && +m[2] >= 64 && +m[2] <= 127) k = "Tailscale";
    else if (m && (+m[1] === 10 || +m[1] === 192 && +m[2] === 168 || +m[1] === 172 && +m[2] >= 16 && +m[2] <= 31)) {
      k = homeSeen ? "other adapter" : "home network"; homeSeen = true;
    }
    return [u, k];
  }));
  const kind = u => kinds.get(u);
  // Virtual adapters (Docker, WSL, Hyper-V) aren't shown: phones can't reach them.
  // localhost only when there's nothing else: once a network, Tailscale or your own
  // address exists, those are the ones worth bookmarking.
  const hasNetwork = urls.some(u => !local(u) && kind(u) !== "other adapter");
  const shownUrls = urls.filter(u => kind(u) !== "other adapter" && !(hasNetwork && local(u)));
  urls.length = 0; urls.push(...shownUrls);
  const order = { "your address": 0, "home network": 1, "Tailscale": 2, "network": 3, "this computer": 4 };
  urls.sort((x, y) => order[kind(x)] - order[kind(y)]);
  q("#where").innerHTML = `<span><b>Address of this app:</b></span>` +
    urls.map(u => `<a href="${esc(u)}" title="${local(u) ? "Works only on this computer" : "Works from other devices on your network"}">${esc(u)}</a><span class="small muted">(${kind(u)})</span>`).join("") +
    `<span>· ${hasNetwork
      ? "bookmark the network address on your phone or other computers (home network or Tailscale only)"
      : "this address works only on this computer; for your phone, turn on \"Other devices\" in Settings (then restart), or run MoneyThistle on your server"}</span>` +
    `<span class="pubwarn" title="MoneyThistle has no protection against attacks from the internet">⚠ Never open it to the public internet: use it on your home network or through Tailscale.</span>`;
}

function catOptions(selected, opts) {
  opts = opts || {};
  const groups = { income: [], expense: [], none: [] };
  for (const c of S.cats) groups[c.kind] && groups[c.kind].push(c);
  let h = `<option value="">${opts.blank || "(no category)"}</option>`;
  const names = { income: "Income", expense: "Expense", none: "Other" };
  for (const k of ["expense", "income", "none"]) {
    if (opts.topOnly) { if (!groups[k].some(c => !c.parent_id)) continue; }
    h += `<optgroup label="${names[k]}">`;
    for (const c of groups[k]) {
      if (opts.topOnly && c.parent_id) continue;
      h += `<option value="${c.id}" ${c.id == selected ? "selected" : ""}>${c.parent_id ? "&nbsp;&nbsp;&nbsp;" : ""}${esc(c.parent_id && !opts.full ? catName(c) : catFull(c))}</option>`;
    }
    h += `</optgroup>`;
  }
  return h;
}
// A category's full name ("Bills : Electricity") in the person's language.
function catFull(c) {
  const p = c && c.parent_id && S.cats.find(x => x.id === c.parent_id);
  return p ? catName(p) + " : " + catName(c) : catName(c);
}
function acctOptions(selected, exclude, includeClosed) {
  return S.accounts.filter(a => a.id != exclude && (includeClosed || !a.closed || a.id == selected))
    .map(a => `<option value="${a.id}" ${a.id == selected ? "selected" : ""}>${esc(a.name)}</option>`).join("");
}
function groupAccounts(list) {
  const g = [["Banking", ["Checking", "Savings", "Cash"]], ["Credit cards & loans", ["Credit Card", "Line of Credit", "Loan", "Liability"]],
    ["Investments & property", ["Investment", "Retirement", "Asset", "Other"]]];
  return g.map(([name, types]) => [name, list.filter(a => types.includes(a.type))]).filter(x => x[1].length);
}

// ---------- dialog ----------
// A problem saving a dialog: the message shows in the dialog itself (a pop-up message
// would sit behind it), and the field it's about is outlined, opened and focused.
function dialogError(e) {
  const box = q("#dlgErr");
  if (!box) { toast(e.message || String(e), true); return; }
  qa("#dlgBody .invalid").forEach(x => x.classList.remove("invalid"));
  qa("#dlgBody .field-err").forEach(x => x.remove());
  box.textContent = e.message || String(e);
  box.hidden = false;
  const name = e.field;
  const el = name && (q(`#dlgBody [name="${name}"]`) || q(`#dlgBody [name="d_${name}"]`));
  if (el) {
    for (let p = el.parentElement; p; p = p.parentElement) if (p.tagName === "DETAILS") p.open = true;
    const shown = el._pick || el;   // a long list shows as its typing box
    shown.classList.add("invalid");
    // The message under the field too, where the eye is.
    const note = document.createElement("div");
    note.className = "field-err"; note.textContent = box.textContent;
    (el._pick ? el.parentElement : el).after(note);
    shown.scrollIntoView({ block: "center", behavior: "smooth" });
    setTimeout(() => shown.focus(), 50);
    const clear = () => { shown.classList.remove("invalid"); box.hidden = true; note.remove(); };
    shown.addEventListener("input", clear, { once: true });
    el.addEventListener("change", clear, { once: true });
  } else box.scrollIntoView({ block: "nearest" });
}
function dialog(title, body, buttons) {
  return new Promise(resolve => {
    const d = document.getElementById("dlg");
    q("#dlgTitle").textContent = title;
    q("#dlgBody").innerHTML = body;
    let err = q("#dlgErr");
    if (!err) {
      err = document.createElement("div");
      err.id = "dlgErr"; err.className = "dlg-err"; err.setAttribute("role", "alert");
      q("#dlgFoot").before(err);
    }
    err.hidden = true; err.textContent = "";
    const foot = q("#dlgFoot"); foot.innerHTML = "";
    for (const b of buttons) {
      const el = document.createElement("button");
      el.type = "button"; el.textContent = b.label; if (b.cls) el.className = b.cls;
      el.onclick = async () => {
        if (b.action) {
          err.hidden = true;
          try { const r = await b.action(q("#dlgBody")); if (r === false) return; resolve(r === undefined ? b.value : r); }
          catch (e) { dialogError(e); return; }
        } else resolve(b.value);
        d.close();
      };
      foot.appendChild(el);
    }
    d.onclose = () => resolve(null);
    // Closing without the buttons (the ✕, Escape, or a click outside the card): straight
    // away when nothing was changed; otherwise it asks whether to save first.
    let changed = false;
    const bodyEl = q("#dlgBody");
    const mark = e => { if (e.isTrusted) changed = true; };
    bodyEl.oninput = mark;
    bodyEl.onchange = mark;
    // (buttons inside it add, remove or move lines, or fill something in)
    bodyEl.onclick = e => { if (e.isTrusted && e.target.closest("button")) changed = true; };
    const leave = async () => {
      const save = q("#dlgFoot button.primary");
      if (!changed || !save) { resolve(null); d.close(); return; }
      const pick = await askSaveChanges();
      if (pick === "save") save.click();
      else if (pick === "discard") { resolve(null); d.close(); }
    };
    q("#dlgClose").onclick = leave;
    d.oncancel = e => { e.preventDefault(); leave(); };   // Escape
    d.onmousedown = e => { d._downOutside = e.target === d; };
    d.onclick = e => { if (e.target === d && d._downOutside) leave(); };   // the dimmed area around the card
    d.showModal();
    const first = q("input,select,textarea", bodyEl); if (first) first.focus();
  });
}
// "Save your changes?" over a dialog that's being closed: save, don't save, or keep editing.
function askSaveChanges(text) {
  return new Promise(resolve => {
    let a = document.getElementById("dlgAsk");
    if (!a) {
      a = document.createElement("dialog");
      a.id = "dlgAsk"; a.className = "ask";
      document.body.appendChild(a);
    }
    a.innerHTML = `<div class="dhead"><span>${esc(tr("Save your changes?"))}</span></div>
      <div class="dbody">${esc(tr(text || "You changed something here. Save it before closing?"))}</div>
      <div class="dfoot"><button type="button" data-pick="keep">${esc(tr("Keep editing"))}</button>
        <button type="button" data-pick="discard">${esc(tr("Don't save"))}</button>
        <button type="button" class="primary" data-pick="save">${esc(tr("Save"))}</button></div>`;
    let done = false;
    const finish = v => { if (done) return; done = true; a.close(); resolve(v); };
    qa("[data-pick]", a).forEach(b => b.onclick = () => finish(b.dataset.pick));
    a.oncancel = e => { e.preventDefault(); finish("keep"); };
    a.onclose = () => finish("keep");
    a.showModal();
    q("button.primary", a).focus();
  });
}
function formData(root) {
  const o = {};
  for (const el of qa("[name]", root)) {
    if (el.type === "radio") { if (el.checked) o[el.name] = el.value; continue; }  // only the chosen option
    o[el.name] = el.type === "checkbox" ? el.checked : el.value;
  }
  return o;
}
function confirmBox(text) {
  return dialog("Please confirm", `<p>${esc(text)}</p>`, [{ label: "Cancel", value: false }, { label: "Yes", cls: "primary", value: true }]);
}

// ---------- charts ----------
function donut(items, size) {
  size = size || 170;
  const total = items.reduce((s, i) => s + Math.max(0, i.value), 0);
  if (!total) return `<div class="empty">Nothing to show yet</div>`;
  const r = size / 2, ir = r * 0.58;
  let a = -Math.PI / 2, paths = "";
  items.forEach((it, i) => {
    const frac = Math.max(0, it.value) / total;
    if (frac <= 0) return;
    const a2 = a + frac * Math.PI * 2 - (frac >= 1 ? 0.0001 : 0);
    const large = a2 - a > Math.PI ? 1 : 0;
    const p = (ang, rad) => [r + rad * Math.cos(ang), r + rad * Math.sin(ang)];
    const [x1, y1] = p(a, r), [x2, y2] = p(a2, r), [x3, y3] = p(a2, ir), [x4, y4] = p(a, ir);
    paths += `<path d="M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2} L${x3},${y3} A${ir},${ir} 0 ${large} 0 ${x4},${y4} Z" fill="${it.color || PALETTE[i % PALETTE.length]}" data-id="${it.id || ""}"><title>${esc(it.label)}: ${fmt(it.value, true)}</title></path>`;
    a = a2;
  });
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" class="donut">${paths}
    <text x="${r}" y="${r - 4}" text-anchor="middle" font-size="11" fill="#64748b">Total</text>
    <text class="total" x="${r}" y="${r + 14}" text-anchor="middle" font-size="14" font-weight="600">${fmt(total, true)}</text></svg>`;
}
function legend(items, max) {
  const shown = items.slice(0, max || items.length);
  return `<ul class="legend">${shown.map((it, i) => `<li data-id="${it.id || ""}"><span class="sw" style="background:${it.color || PALETTE[i % PALETTE.length]}"></span>${esc(it.label)}<span class="num">${fmt(it.value)}</span></li>`).join("")}</ul>`;
}
function topItems(rows, n) {
  const items = rows.map(r => ({ id: r.id, label: r.name, value: r.total }));
  if (items.length <= n) return items;
  const rest = items.slice(n - 1).reduce((s, i) => s + i.value, 0);
  return items.slice(0, n - 1).concat([{ label: "Everything else", value: rest, color: "#b8c3d3" }]);
}
function barChart(rows, w, h) {
  w = w || 760; h = h || 240;
  const pad = { l: 64, r: 10, t: 12, b: 28 };
  const max = Math.max(1, ...rows.map(r => Math.max(r.income, r.spending)));
  const cw = (w - pad.l - pad.r) / rows.length, bw = Math.min(22, cw / 2.6);
  const y = v => pad.t + (h - pad.t - pad.b) * (1 - v / max);
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = max * i / 4, yy = y(v);
    g += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${yy}" y2="${yy}" stroke="#e6ecf4"/><text x="${pad.l - 6}" y="${yy + 4}" font-size="10" text-anchor="end" fill="#64748b">${fmt(Math.round(v / 100) * 100, true).replace(/\.00$/, "")}</text>`;
  }
  rows.forEach((r, i) => {
    const x = pad.l + i * cw + cw / 2;
    g += `<rect x="${x - bw - 1}" y="${y(r.income)}" width="${bw}" height="${y(0) - y(r.income)}" fill="#1f8a8a"><title>${monthName(r.month)} income ${fmt(r.income, true)}</title></rect>`;
    g += `<rect x="${x + 1}" y="${y(r.spending)}" width="${bw}" height="${y(0) - y(r.spending)}" fill="#e08a2e"><title>${monthName(r.month)} spending ${fmt(r.spending, true)}</title></rect>`;
    g += `<text x="${x}" y="${h - 9}" font-size="11" text-anchor="middle" fill="#64748b">${shortMonth(r.month)}</text>`;
  });
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" style="max-width:${w}px">${g}</svg>`;
}
function lineChart(rows, key, w, h) {
  w = w || 760; h = h || 240;
  const pad = { l: 74, r: 14, t: 12, b: 28 };
  const vals = rows.map(r => r[key]);
  let min = Math.min(0, ...vals), max = Math.max(1, ...vals);
  if (max === min) max = min + 1;
  const x = i => pad.l + (w - pad.l - pad.r) * (rows.length === 1 ? 0.5 : i / (rows.length - 1));
  const y = v => pad.t + (h - pad.t - pad.b) * (1 - (v - min) / (max - min));
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = min + (max - min) * i / 4, yy = y(v);
    g += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${yy}" y2="${yy}" stroke="#e6ecf4"/><text x="${pad.l - 6}" y="${yy + 4}" font-size="10" text-anchor="end" fill="#64748b">${fmt(Math.round(v / 100) * 100, true).replace(/\.00$/, "")}</text>`;
  }
  const pts = rows.map((r, i) => `${x(i)},${y(r[key])}`).join(" ");
  g += `<polyline points="${pad.l},${y(min)} ${pts} ${x(rows.length - 1)},${y(min)}" class="accent-area" stroke="none"/>`;
  g += `<polyline points="${pts}" fill="none" class="accent-line" stroke-width="2.5"/>`;
  rows.forEach((r, i) => {
    g += `<circle cx="${x(i)}" cy="${y(r[key])}" r="3.5" class="accent-fill"><title>${monthName(r.month)}: ${fmt(r[key], true)}</title></circle>`;
    g += `<text x="${x(i)}" y="${h - 9}" font-size="11" text-anchor="middle" fill="#64748b">${shortMonth(r.month)}</text>`;
  });
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" style="max-width:${w}px">${g}</svg>`;
}
function budgetBar(actual, budget, dayFrac) {
  const pct = budget > 0 ? Math.min(100, actual / budget * 100) : (actual > 0 ? 100 : 0);
  const cls = budget > 0 && actual > budget ? "over" : (budget > 0 && dayFrac != null && actual / budget > dayFrac + 0.1 ? "warn" : "");
  const mark = dayFrac != null && dayFrac > 0 && dayFrac < 1 ? `<span class="today" style="left:${dayFrac * 100}%"></span>` : "";
  return `<div class="bar"><div class="${cls}" style="width:${pct}%"></div>${mark}</div>`;
}

// ---------- header backup status ----------
async function refreshBackupState(st) {
  try {
    st = st || (await GET("/api/summary")).backup;
  } catch (e) { return; }
  const el = q("#backupState");
  if (!st) { el.innerHTML = ""; return; }
  let dot = "", text;
  if (st.last && !st.last.ok) { dot = "bad"; text = "Last backup failed"; }
  else if (st.last_ok) { text = "Backed up " + new Date(st.last_ok.at).toLocaleString(LOCALE, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); }
  else { dot = "warn"; text = "Not backed up yet"; }
  if (st.pending_changes && dot === "") dot = "warn";
  const tip = text + (st.pending_changes ? " · changes waiting for next backup" : "");
  el.innerHTML = `<a href="#/${S.me && S.me.user.is_admin ? "settings/backups" : "home"}" style="color:inherit" title="${esc(tip)}"><span class="dot ${dot}"></span><span class="bk">${esc(text)}${st.pending_changes ? "<br><span class='small'>changes waiting for next backup</span>" : ""}</span></a>`;
}

// ---------- forecast ----------
// A steady color per account in the forecast: by its place among all accounts listed,
// so ticking boxes on and off doesn't repaint the others.
const FC_COLORS = ["#1f8a8a", "#e08a2e", "#7b5ea7", "#1c74c4", "#4c9a2a", "#c2352b", "#d4a017", "#e46aa0",
  "#2f5d50", "#8a5a2b", "#5aa1d6", "#9a4dbb"];
function fcColor(f, id) {
  const i = f.accounts.findIndex(a => String(a.id) === String(id));
  return FC_COLORS[(i < 0 ? 0 : i) % FC_COLORS.length];
}

// Looking ahead: one line per chosen account (its own color) and, optionally, their
// total as a dashed line. An account that dips below zero gets a red marker at its
// lowest point; hovering any line shows its name.
function forecastChart(f, ids, opts) {
  opts = opts || {};
  const w = opts.w || 760, h = opts.h || 260;
  const pad = { l: 74, r: 14, t: 12, b: 28 };
  const accs = f.accounts.filter(a => ids.includes(String(a.id)));
  const n = f.days + 1;
  const total = Array.from({ length: n }, (_, i) => accs.reduce((s, a) => s + a.series[i], 0));
  const showTotal = opts.total !== false && accs.length > 1;
  const all = accs.flatMap(a => a.series).concat(showTotal ? total : []);
  let min = Math.min(0, ...all), max = Math.max(1, ...all);
  if (max === min) max = min + 1;
  const span = max - min; max += span * 0.04; min -= min < 0 ? span * 0.04 : 0;
  const x = i => pad.l + (w - pad.l - pad.r) * i / (n - 1);
  const y = v => pad.t + (h - pad.t - pad.b) * (1 - (v - min) / (max - min));
  let g = "";
  for (let i = 0; i <= 4; i++) {
    const v = min + (max - min) * i / 4, yy = y(v);
    g += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${yy}" y2="${yy}"/><text x="${pad.l - 6}" y="${yy + 4}" font-size="10" text-anchor="end">${fmt(Math.round(v / 100) * 100, true).replace(/\.00$/, "")}</text>`;
  }
  g += `<line x1="${pad.l}" x2="${w - pad.r}" y1="${y(0)}" y2="${y(0)}" style="stroke:${min < 0 ? "var(--red)" : "var(--muted)"};stroke-dasharray:4 3;stroke-opacity:.8"/>`;
  const start = new Date(f.start + "T00:00:00");
  const step = n > 120 ? 30 : (n > 45 ? 14 : 7);
  for (let i = 0; i < n; i += step) {
    const d = new Date(start); d.setDate(d.getDate() + i);
    g += `<text x="${x(i)}" y="${h - 9}" font-size="11" text-anchor="middle">${d.toLocaleDateString(LOCALE, { month: "short", day: "numeric" })}</text>`;
  }
  // Steps: a balance changes on the day something is paid or received.
  const stepPath = s => { let p = `M${x(0)},${y(s[0])}`; for (let i = 1; i < n; i++) p += ` H${x(i)} V${y(s[i])}`; return p; };
  if (showTotal) {
    g += `<path d="${stepPath(total)}" fill="none" style="stroke:var(--text);stroke-opacity:.55" stroke-width="2" stroke-dasharray="6 4"><title>Total of the selected accounts</title></path>`;
  }
  for (const a of accs) {
    const c = fcColor(f, a.id);
    g += `<path d="${stepPath(a.series)}" fill="none" stroke="${c}" stroke-width="2.4" stroke-linejoin="round"><title>${esc(a.name)}</title></path>`;
    const lo = a.series.indexOf(Math.min(...a.series));
    if (a.series[lo] < 0) {
      g += `<circle cx="${x(lo)}" cy="${y(a.series[lo])}" r="5" style="fill:var(--red);stroke:var(--card);stroke-width:1.5"><title>${esc(a.name)} goes below zero: lowest ${fmt(a.series[lo], true)}</title></circle>`;
    }
  }
  // A scheduled item picked in the list: a line on its day, a dot where it moves each
  // ticked account it touches, and its name and amount beside the line.
  if (opts.mark) {
    const m = opts.mark, day = Math.max(0, Math.min(n - 1, m.day)), xx = x(day);
    g += `<line x1="${xx}" x2="${xx}" y1="${pad.t}" y2="${h - pad.b}" style="stroke:var(--text);stroke-opacity:.75;stroke-width:1.5;stroke-dasharray:5 3"/>`;
    for (const a of accs) {
      if (!m.accounts.includes(String(a.id))) continue;
      g += `<circle cx="${xx}" cy="${y(a.series[day])}" r="5.5" style="fill:${fcColor(f, a.id)};stroke:var(--card);stroke-width:2"><title>${esc(a.name)} after this: ${fmt(a.series[day], true)}</title></circle>`;
    }
    const right = xx < pad.l + (w - pad.l - pad.r) * 0.62;
    g += `<text x="${right ? xx + 7 : xx - 7}" y="${pad.t + 12}" font-size="12" text-anchor="${right ? "start" : "end"}" style="fill:var(--text);paint-order:stroke;stroke:var(--card);stroke-width:4px;stroke-linejoin:round">${esc(m.label)}</text>`;
    if (m.note) g += `<text x="${right ? xx + 7 : xx - 7}" y="${pad.t + 27}" font-size="11" text-anchor="${right ? "start" : "end"}" style="paint-order:stroke;stroke:var(--card);stroke-width:4px">${esc(m.note)}</text>`;
  }
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" style="max-width:${w}px">${g}</svg>`;
}
const SPENDING_TYPES = ["Checking", "Savings", "Cash", "Credit Card", "Line of Credit"];

// Which accounts the forecast chart shows: the ones ticked under Reports → Looking
// ahead (remembered per environment), or by default the money accounts you spend from.
function forecastChoice(f) {
  const shown = f.accounts.filter(a => a.has_activity || SPENDING_TYPES.includes(a.type));
  const allIds = shown.filter(a => SPENDING_TYPES.includes(a.type) && !a.liability).map(a => String(a.id));
  const valid = new Set(shown.map(a => String(a.id)));
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("hl-forecast-" + (allEnvs ? "all" : S.env)) || "null"); } catch (e) { saved = null; }
  let chosen = (Array.isArray(saved) ? saved.map(String) : allIds).filter(id => valid.has(id));
  if (Array.isArray(saved) && saved.length && !chosen.length) chosen = allIds.slice();
  return { shown, allIds, chosen };
}

// ---------- HOME ----------
// Each person picks which cards their Home page shows, in which column and order.
const HOME_CARDS = { accounts: "Account list", due: "Bills & deposits due soon", recent: "Recent transactions",
  spending: "Where the money went this month", budget: "Budget", forecast: "Looking ahead" };
const HOME_DEFAULT = {
  cards: [{ id: "accounts", show: true, col: 1 }, { id: "due", show: true, col: 2 }, { id: "recent", show: true, col: 2 },
    { id: "spending", show: true, col: 3 }, { id: "budget", show: true, col: 3 }, { id: "forecast", show: true, col: 3 }],
  forecast_view: "table", forecast_days: 30, recent_count: 8, hide_zero: false, show_networth: true };
function homeLayout() {
  const h = (S.ui && S.ui.home) || {};
  const out = Object.assign(JSON.parse(JSON.stringify(HOME_DEFAULT)), h);
  out.cards = (h.cards || HOME_DEFAULT.cards).filter(c => HOME_CARDS[c.id]).map(c => Object.assign({}, c));
  for (const d of HOME_DEFAULT.cards) if (!out.cards.some(c => c.id === d.id)) out.cards.push(Object.assign({}, d));
  return out;
}
async function saveHome(home, extra) {
  S.ui = await api("PUT", "/api/settings", Object.assign({ home }, extra || {}));
}

function homeForecast(f, H) {
  const rows = f.accounts.filter(a => SPENDING_TYPES.includes(a.type) && a.has_activity);
  if (!rows.length) return "";
  const chart = H.forecast_view === "chart";
  const toggle = `<span class="seg" role="group" aria-label="Show as">
      <button class="small ${chart ? "" : "on"}" data-fview="table" aria-pressed="${!chart}">Balances</button><button class="small ${chart ? "on" : ""}" data-fview="chart" aria-pressed="${chart}">Chart</button></span>`;
  let inner;
  if (chart) {
    const { chosen, allIds } = forecastChoice(f);
    const ids = chosen.length ? chosen : allIds;
    const accs = f.accounts.filter(a => ids.includes(String(a.id)));
    inner = accs.length ? `<div id="homeFcChart" data-ids="${esc(JSON.stringify(ids))}"></div>
      <div class="small fc-legend" style="margin-top:4px">${accs.map(a => `<span style="display:inline-block;margin-right:10px"><span class="fc-swatch" style="background:${fcColor(f, a.id)}"></span>${esc(a.name)}${a.low < 0 ? ' <span class="pill red">below 0</span>' : ""}</span>`).join("")}${accs.length > 1 && localStorage.getItem("hl-forecast-total") !== "0" ? '<span style="display:inline-block"><span class="fc-swatch dashed"></span>Total</span>' : ""}</div>
      <p class="small muted" style="margin-bottom:0">Same accounts as Reports → Looking ahead; tick others there.</p>`
      : `<div class="empty">No accounts chosen for the chart</div>`;
  } else {
    inner = `<table><tr><th>Account</th><th class="num">Now</th><th class="num">Lowest</th><th class="num">In ${f.days} days</th></tr>
    ${rows.map(a => `<tr><td>${esc(a.name)}</td><td class="num">${fmt(a.now)}</td>
      <td class="num">${fmt(a.low)}<div class="small muted">${niceDate(a.low_date)}</div></td><td class="num">${fmt(a.end)}</td></tr>`).join("")}</table>
    <p class="small muted" style="margin-bottom:0">From your scheduled bills, deposits and transfers; bills whose amount varies count at their average.</p>`;
  }
  return `<div class="card" data-card="forecast"><div class="head"><h2>Looking ahead: ${f.days} days</h2><span style="display:flex;gap:10px;align-items:center">${toggle}<a href="#/reports" class="small" id="fcLink">Forecast</a></span></div>${inner}</div>`;
}

async function renderHome() {
  const H = homeLayout();
  const showing = id => H.cards.some(c => c.id === id && c.show);
  const dueDays = (S.ui && S.ui.due_days) || 14;
  const sc = scopeQS();
  const [d, fc, upd] = await Promise.all([GET(`/api/summary?days=${dueDays}&recent=${H.recent_count || 8}${sc}`),
    showing("forecast") ? GET("/api/forecast?days=" + (H.forecast_days || 30) + sc).catch(() => null) : Promise.resolve(null),
    S.me.user.is_admin ? GET("/api/updates").catch(() => null) : Promise.resolve(null)]);
  refreshBackupState(d.backup);
  if (!d.accounts.length && !(d.shared_accounts || []).length) {
    view().innerHTML = `<h1>Welcome</h1><div class="card" style="max-width:640px">
      <h2>Let's set up your money file</h2>
      <p>Start by adding the accounts you want to keep track of: a checking account, savings, credit cards, loans or cash.
      Then type in transactions, or bring them in from a CSV or QIF file your bank lets you download.</p>
      <div class="toolbar"><button class="primary" id="firstAcct">Add an account</button><button id="sample">Try it with sample data</button></div>
      <p class="small muted">Backups go to a folder by default. Add your Nextcloud (or any WebDAV) under Backups.</p></div>`;
    q("#firstAcct").onclick = () => editAccount(null);
    q("#sample").onclick = async () => { await api("POST", "/api/sample"); await loadBasics(); render(); };
    return;
  }
  const b = d.budget;
  const cardHtml = {
    accounts: () => {
      const groups = groupAccounts(d.accounts)
        .map(([name, list]) => [name, list, H.hide_zero ? list.filter(a => a.balance !== 0) : list])
        .filter(([, , vis]) => vis.length);
      return `<div class="card" data-card="accounts">
      <div class="head"><h2>Account list</h2><a href="#/accounts" class="small">Manage</a></div>
      ${groups.map(([name, list, vis]) => `<div class="acctgroup"><div class="gname">${esc(name)}</div>
        ${vis.map(a => `<a class="acctrow" href="#/accounts/${a.id}"${a.env_id && a.env_id !== S.env ? ` data-goenv="${a.env_id}" data-goacct="${a.id}"` : ""}><span>${esc(a.name)}${envTag(a)}</span><span class="num">${fmt(a.balance, false, a)}</span></a>`).join("")}
        <div class="acctrow small muted"><span>Total</span><span class="num">${sumByCur(list)}</span></div></div>`).join("")}
      ${sharedGroup(H.hide_zero ? (d.shared_accounts || []).filter(a => a.balance !== 0) : (d.shared_accounts || []))}
      ${H.show_networth ? netWorthHtml(d) : ""}
    </div>`;
    },
    due: () => `<div class="card" data-card="due">
        <div class="head"><h2>Bills &amp; deposits due in ${dueDays} days</h2><a href="#/bills" class="small">See all</a></div>
        ${d.upcoming.filter(u => u.first).length ? `<table>${d.upcoming.filter(u => u.first).slice(0, 7).map(u => `
          <tr class="${u.overdue ? "overdue " : ""}k-${kindOf(u)}"><td class="small">${u.overdue ? '<span class="pill red">Overdue</span>' : niceDate(u.date)}</td>
          <td>${kindSym(u)} ${esc(u.payee || (u.kind === "transfer" ? "Transfer" : ""))}${envTag(u)}${u.auto ? ' <span class="small" title="Happens automatically" aria-label="automatic">⟳</span>' : ""}<div class="small muted">${esc(u.account_name)}${u.kind === "transfer" || u.kind === "loan" ? " → " + esc(u.to_account_name) : ""}</div></td>
          <td class="num">${billAmount(u)}</td>
          <td class="num"><button class="small" data-enter="${u.id}" data-enterenv="${u.env_id || ""}">Enter</button></td></tr>`).join("")}</table>`
          : `<div class="empty">Nothing due in the next ${dueDays} days</div>`}
        ${(d.shared_upcoming || []).filter(u => u.first).length ? `<div class="gname small muted" style="margin:10px 0 2px;text-transform:uppercase;letter-spacing:.6px">Shared accounts</div>
          <table>${d.shared_upcoming.filter(u => u.first).slice(0, 5).map(u => `<tr class="${u.overdue ? "overdue " : ""}k-${kindOf(u)}">
            <td class="small">${u.overdue ? '<span class="pill red">Overdue</span>' : niceDate(u.date)}</td>
            <td>${kindSym(u)} ${esc(u.payee)}<div class="small muted">${esc(u.account_name)} · shared</div></td>
            <td class="num">${billAmount(u)}</td><td class="num"><a class="btn small" href="#/bills">${u.can_edit ? "Enter…" : "View"}</a></td></tr>`).join("")}</table>` : ""}
      </div>`,
    recent: () => `<div class="card" data-card="recent">
        <div class="head"><h2>Recent transactions</h2></div>
        ${d.recent.length ? `<table>${d.recent.map(t => `<tr class="click" data-acct="${t.account_id}" data-acctenv="${t.env_id || ""}"><td class="small muted">${niceDate(t.date)}</td>
          <td>${esc(t.payee)}${envTag(t)}<div class="small muted">${esc(t.category_label || t.account_name)}</div></td><td class="num">${fmt(t.amount, false, t)}</td></tr>`).join("")}</table>`
          : `<div class="empty">No transactions yet</div>`}
      </div>`,
    spending: () => {
      const spendItems = topItems(d.spending, 7);
      return `<div class="card" data-card="spending">
        <div class="head"><h2>Where the money went this month</h2><a href="#/reports" class="small">Reports</a></div>
        <div class="chartwrap">${donut(spendItems, 160)}<div style="flex:1">${legend(spendItems)}</div></div>
      </div>`;
    },
    budget: () => {
      const dayFrac = b.days_in_month ? b.day_of_month / b.days_in_month : null;
      const overspent = b.rows.filter(r => r.kind === "expense" && r.budget > 0 && r.actual > r.budget);
      return `<div class="card" data-card="budget">
        <div class="head"><h2>Budget for ${esc(monthName(b.month))}</h2><a href="#/budget" class="small">Budget</a></div>
        <div style="display:flex;justify-content:space-between" class="small"><span>${b.mode === "schedule" ? "Paid out" : "Spent"} ${fmt(b.expense_actual, true)}</span><span class="muted">of ${fmt(b.expense_budget, true)}${b.mode === "schedule" ? " scheduled" : ""}</span></div>
        ${budgetBar(b.expense_actual, b.expense_budget, dayFrac)}
        <div style="display:flex;justify-content:space-between;margin-top:10px" class="small"><span>Income ${fmt(b.income_actual, true)}</span><span class="muted">of ${fmt(b.income_budget, true)} expected</span></div>
        ${budgetBar(b.income_actual, b.income_budget, null)}
        ${overspent.length ? `<p class="small" style="margin-bottom:0"><span class="pill red">${b.mode === "schedule" ? "More than expected" : "Over budget"}</span> ${overspent.map(r => esc(r.name)).join(", ")}</p>`
          : `<p class="small muted" style="margin-bottom:0">${b.mode === "schedule" ? "Everything paid so far is within what was expected." : "Every budget category is on track."}</p>`}
      </div>`;
    },
    forecast: () => fc ? homeForecast(fc, H) : "",
  };
  // Columns in order; a column with nothing in it is left out, and a column holding
  // only the account list stays narrow.
  const cols = [1, 2, 3].map(n => H.cards.filter(c => c.show && c.col === n))
    .map(list => ({ list, html: list.map(c => cardHtml[c.id]()).join("") }))
    .filter(c => c.html.trim());
  const template = cols.map(c => c.list.length === 1 && c.list[0].id === "accounts" && cols.length > 1 ? "300px" : "minmax(0,1fr)").join(" ");
  view().innerHTML = `
  <div class="pagehead"><h1>${new Date().toLocaleDateString(LOCALE, { weekday: "long", month: "long", day: "numeric" })}</h1>
    <a class="btn small primary" href="#/quick" title="Enter a purchase, deposit or transfer">+ Quick add</a>
    ${scopeSwitch()}<button class="small" id="homeCustom" title="Choose which cards show here and where">Customize</button></div>
  ${scopeNote("changes are made in each item's own environment (choosing one switches there)")}
  ${updateNote(upd)}
  ${statementsDueNote(d.statements_due)}
  ${cols.length ? `<div class="grid home" style="--home-cols:${template}">${cols.map(c => `<div class="grid" style="align-content:start">${c.html}</div>`).join("")}</div>`
    : `<div class="card empty">Every card is hidden. <a href="#" id="homeCustom2">Customize</a> to show some again.</div>`}`;
  qa("[data-enter]").forEach(b => b.onclick = async () => {
    const env = +b.dataset.enterenv || S.env;
    const u = d.upcoming.find(x => x.id == b.dataset.enter && x.first && (x.env_id || S.env) === env);
    await goEnv(env);
    enterBill(+b.dataset.enter, u);
  });
  qa("[data-goenv]").forEach(a => a.onclick = async e => { e.preventDefault(); await goEnv(+a.dataset.goenv); location.hash = "#/accounts/" + a.dataset.goacct; });
  if (q("#fcLink")) q("#fcLink").onclick = () => { reportState.kind = "forecast"; };
  qa("tr[data-acct]").forEach(r => r.onclick = async () => { await goEnv(+r.dataset.acctenv); location.hash = "#/accounts/" + r.dataset.acct; });
  q("#homeCustom").onclick = () => customizeHome();
  wireStatementsDue();
  if (q("#homeUpd")) q("#homeUpd").onclick = () => updateNow(upd);
  if (q("#homeCustom2")) q("#homeCustom2").onclick = e => { e.preventDefault(); customizeHome(); };
  qa("[data-fview]").forEach(btn => btn.onclick = async () => {
    if (H.forecast_view === btn.dataset.fview) return;
    try { await saveHome(Object.assign({}, H, { forecast_view: btn.dataset.fview })); renderHome(); }
    catch (e) { toast(e.message, true); }
  });
  const fcBox = q("#homeFcChart");
  if (fcBox && fc) {
    const ids = JSON.parse(fcBox.dataset.ids);
    const w = Math.max(320, fcBox.clientWidth);
    fcBox.innerHTML = forecastChart(fc, ids, { w, h: 210, total: localStorage.getItem("hl-forecast-total") !== "0" });
  }
  // Came here from Settings → Customize Home.
  if (S.openCustomize) { S.openCustomize = false; customizeHome(); }
}

// The Customize window: show or hide each card, pick its column, move it up or down,
// and a few choices inside cards. Saved for the person signed in.
async function customizeHome() {
  let H = homeLayout();
  const colName = ["", "Left", "Middle", "Right"];
  const listHtml = () => `<table class="hc-list"><tr><th>Show</th><th>Card</th><th>Column</th><th class="num">Order</th></tr>
    ${H.cards.map((c, i) => `<tr><td><input type="checkbox" data-hshow="${i}" id="hs-${c.id}" ${c.show ? "checked" : ""}></td>
      <td><label for="hs-${c.id}">${esc(HOME_CARDS[c.id])}</label></td>
      <td><select data-hcol="${i}" aria-label="Column for ${esc(HOME_CARDS[c.id])}">${[1, 2, 3].map(n => `<option value="${n}" ${c.col === n ? "selected" : ""}>${colName[n]}</option>`).join("")}</select></td>
      <td class="num" style="white-space:nowrap"><button type="button" class="small" data-hup="${i}" ${i ? "" : "disabled"} title="Move up" aria-label="Move ${esc(HOME_CARDS[c.id])} up">↑</button>
        <button type="button" class="small" data-hdown="${i}" ${i < H.cards.length - 1 ? "" : "disabled"} title="Move down" aria-label="Move ${esc(HOME_CARDS[c.id])} down">↓</button></td></tr>`).join("")}</table>`;
  const body = `<p class="small muted" style="margin-top:0">Your choices only change your own Home page. Cards in the same column show top to bottom in this order; on a narrow screen the columns stack.</p>
    <div id="hcList">${listHtml()}</div>
    <div class="form" style="margin-top:14px">
      <div><label>Looking ahead shows</label><select id="hcFview"><option value="table" ${H.forecast_view === "table" ? "selected" : ""}>Balances</option><option value="chart" ${H.forecast_view === "chart" ? "selected" : ""}>Chart</option></select></div>
      <div><label>Looking ahead covers</label><select id="hcFdays">${[30, 60, 90].map(n => `<option value="${n}" ${H.forecast_days === n ? "selected" : ""}>${n} days</option>`).join("")}</select></div>
      <div><label>Bills due within</label><input id="hcDue" class="num" style="width:80px" value="${(S.ui && S.ui.due_days) || 14}"> <span class="small muted">days</span></div>
      <div><label>Recent transactions</label><select id="hcRecent">${[5, 8, 10, 15, 20].map(n => `<option ${H.recent_count === n ? "selected" : ""}>${n}</option>`).join("")}</select></div>
      <div class="wide"><label class="check"><input type="checkbox" id="hcZero" ${H.hide_zero ? "checked" : ""}> Hide accounts with a zero balance in the account list</label></div>
      <div class="wide"><label class="check"><input type="checkbox" id="hcNet" ${H.show_networth ? "checked" : ""}> Show net worth under the account list</label></div>
    </div>`;
  // Keep what was ticked before redrawing the list after a move.
  const readList = () => {
    qa("[data-hshow]").forEach(c => { H.cards[+c.dataset.hshow].show = c.checked; });
    qa("[data-hcol]").forEach(s => { H.cards[+s.dataset.hcol].col = +s.value; });
  };
  const wire = () => {
    const move = (i, j) => { readList(); const t = H.cards[i]; H.cards[i] = H.cards[j]; H.cards[j] = t; q("#hcList").innerHTML = listHtml(); wire(); };
    qa("[data-hup]").forEach(btn => btn.onclick = () => { const i = +btn.dataset.hup; move(i, i - 1); q(`[data-hup="${Math.max(0, i - 1)}"]`).focus(); });
    qa("[data-hdown]").forEach(btn => btn.onclick = () => { const i = +btn.dataset.hdown; move(i, i + 1); q(`[data-hdown="${Math.min(H.cards.length - 1, i + 1)}"]`).focus(); });
  };
  const p = dialog("Customize Home", body, [
    { label: "Standard layout", action: async () => {
      S.ui = await api("PUT", "/api/settings", { home: null });
      toast("Home page back to the standard layout"); renderHome(); return true;
    } },
    { label: "Cancel" },
    { label: "Save", cls: "primary", action: async () => {
      readList();
      const home = Object.assign({}, H, {
        forecast_view: q("#hcFview").value, forecast_days: +q("#hcFdays").value, recent_count: +q("#hcRecent").value,
        hide_zero: q("#hcZero").checked, show_networth: q("#hcNet").checked });
      await saveHome(home, { due_days: q("#hcDue").value });
      toast("Home page saved"); renderHome(); return true;
    } },
  ]);
  wire();
  return p;
}

// ---------- ACCOUNTS ----------
async function editAccount(acc) {
  if (acc && acc.has_loan) return editLoan(acc);
  const a = acc || { name: "", type: "Checking", opening_balance: 0, opening_date: todayISO() };
  const isLiab = t => (S.meta.liability_types || []).includes(t);
  // A card can be paid from an account in another environment you own (both yours: the
  // connection is made by itself).
  const xsrc = envRole() === "owner" && !S.shareCtx ? await Promise.all((S.me.envs || []).filter(e => e.role === "owner" && e.id !== S.env)
    .map(e => GET(`/api/envs/${e.id}/accounts`).then(list => ({ e, list: list.filter(x => !isLiab(x.type)) })).catch(() => ({ e, list: [] }))))
    .then(r => r.filter(x => x.list.length)) : [];
  const body = `<div class="form">
    <div class="wide"><label class="req">Account name</label><input name="name" value="${esc(a.name)}" required></div>
    <div><label>Type</label><select name="type">${S.meta.account_types.map(t => `<option ${t === a.type ? "selected" : ""}>${t}</option>`).join("")}</select></div>
    <div><label id="obLabel">Opening balance</label><input name="opening_balance" class="num" value="${dollars(isLiab(a.type) ? -a.opening_balance : a.opening_balance)}"></div>
    <div><label>As of</label><input type="date" name="opening_date" value="${esc(a.opening_date)}"></div>
    <div><label>Currency</label><select name="currency" title="The money this account is kept in">${curOptions(a.currency || homeCur())}</select></div>
    <div class="wide"><label>Notes</label><input name="notes" value="${esc(a.notes || "")}"></div>
    <div><label class="check"><input type="checkbox" name="favorite" ${a.favorite ? "checked" : ""}> Favorite (list first)</label></div>
    ${acc ? `<div><label class="check"><input type="checkbox" name="closed" ${a.closed ? "checked" : ""}> Account is closed</label></div>` : ""}
  </div><p class="small muted">For credit cards and loans, enter what you owe as a positive number. <span class="req-note"><b>*</b> must be filled in.</span></p>
  ${accountDetailsForm(a, xsrc)}`;
  const btns = [{ label: "Cancel" }];
  const ownedElsewhere = (S.me.envs || []).filter(e => e.role === "owner" && e.id !== S.env);
  // Moving accounts between environments: an Everything feature.
  if (acc && envRole() === "owner" && ownedElsewhere.length && !simpleMode()) btns.unshift({
    label: "Move to another environment…", action: async () => { setTimeout(() => moveAccountsDialog(acc.id), 0); return true; } });
  if (acc) btns.unshift({
    label: "Delete account", cls: "danger", action: async () => {
      if (!(await confirmBox(`Delete "${a.name}" and all of its transactions? Close it instead to keep its history.`))) return false;
      // (the question took the window over: what follows is said in toasts and questions of its own)
      try { await api("DELETE", "/api/accounts/" + a.id); }
      catch (e) {
        if (e.field !== "connected") { toast(e.message, true); return true; }
        if (!(await confirmBox(e.message + " Delete it anyway?"))) return true;
        try { await api("DELETE", `/api/accounts/${a.id}?end=1`); } catch (e2) { toast(e2.message, true); return true; }
      }
      await loadBasics(); location.hash = "#/accounts"; render(); toast("Account deleted"); return true;
    }
  });
  btns.push({
    label: acc ? "Save" : "Add account", cls: "primary", action: async (root) => {
      const f = formData(root);
      // Detail fields are named d_<field>: gathered into one "details" object.
      f.details = {};
      for (const k of Object.keys(f)) if (k.startsWith("d_")) { f.details[k.slice(2)] = f[k]; delete f[k]; }
      // "e<environment>:<account>": a card paid from an account in another environment.
      const pf = String(f.details.pay_from_account_id || "");
      if (pf.startsWith("e")) { const [e, x] = pf.slice(1).split(":"); f.details.pay_from_env_id = +e; f.details.pay_from_account_id = +x; }
      let ob = parseAmount(f.opening_balance) || 0;
      if (isLiab(f.type)) ob = -Math.abs(ob);
      f.opening_balance = ob.toFixed(2);
      const r = acc ? await api("PUT", "/api/accounts/" + a.id, f) : await api("POST", "/api/accounts", f);
      await loadBasics(); location.hash = "#/accounts/" + r.id; render(); toast("Account saved");
    }
  });
  const p = dialog(acc ? "Account details" : "New account", body, btns);
  const sel = q("#dlgBody select[name=type]");
  const upd = () => {
    q("#obLabel").textContent = isLiab(sel.value) ? "Amount owed" : "Opening balance";
    showDetailParts(sel.value);
    if (sel.value === "Loan" && (!acc || !acc.tx_count)) {
      // Loans get their own form: terms, payment split, schedule.
      const name = q("#dlgBody [name=name]").value;
      document.getElementById("dlg").close();
      setTimeout(() => editLoan(acc, name), 0);
    }
  };
  sel.onchange = upd; upd();
  wireDetailsForm();
  return p;
}

// Move accounts to another environment this person owns (e.g. Personal → Household),
// with everything that belongs to them. What will happen is shown before anything moves.
async function moveAccountsDialog(firstId) {
  const targets = (S.me.envs || []).filter(e => e.role === "owner" && e.id !== S.env);
  const here = (S.me.envs.find(e => e.id === S.env) || {}).name || "this environment";
  const accs = S.accounts.filter(a => !a._shared);
  const body = `<p>Move accounts from <b>${esc(here)}</b> to another environment you own, with all their transactions, scheduled items,
      categories and payees. Its members then see and own them; they leave ${esc(here)}.</p>
    <div class="form"><div class="wide"><label>Move to</label><select name="to">${targets.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join("")}</select></div></div>
    <div style="margin-top:10px"><b class="small">Accounts to move</b>
      <div class="movelist">${accs.map(a => `<label class="check"><input type="checkbox" data-macc="${a.id}" ${a.id === firstId ? "checked" : ""}> ${esc(a.name)} <span class="small muted">${esc(a.type)}</span></label>`).join("")}</div></div>
    <div id="movePlan" class="small" style="margin-top:10px"></div>`;
  let checked = null;
  const pick = root => ({ to: +q("[name=to]", root).value, accounts: qa("[data-macc]", root).filter(c => c.checked).map(c => +c.dataset.macc) });
  return dialog("Move to another environment", body, [{ label: "Cancel" }, { label: "Check what moves", cls: "primary", action: async root => {
    const want = pick(root);
    const key = JSON.stringify(want);
    if (checked !== key) {
      const pl = await api("POST", "/api/accounts/move/plan", want);
      checked = key;
      q("#movePlan", root).innerHTML = `<div class="notice" style="margin:0">
          <div>Moving to <b>${esc(pl.to_env_name)}</b>: ${pl.accounts.map(a => `<b>${esc(a.name)}</b> (${a.transactions} entries)`).join(", ")}${pl.bills ? `, with ${pl.bills} scheduled item${pl.bills === 1 ? "" : "s"}` : ""}.</div>
          ${pl.transfers_to_staying.length ? `<div style="margin-top:6px">Transfers to accounts staying in ${esc(here)} become transfers between environments (a connection is made for them):
            ${pl.transfers_to_staying.map(t => `${esc(t.moving)} ↔ ${esc(t.staying)} (${t.count})`).join(", ")}. If ${esc(pl.to_env_name)} should have those too, tick them above.</div>` : ""}
          ${pl.shares_ending ? `<div style="margin-top:6px">${pl.shares_ending} share${pl.shares_ending === 1 ? "" : "s"} into ${esc(pl.to_env_name)} end: the account lives there now.</div>` : ""}
          <div style="margin-top:6px">A backup is made first. Choose <b>Move now</b> to go ahead.</div></div>`;
      q("#dlgFoot button.primary").textContent = "Move now";
      qa("[data-macc], [name=to]", root).forEach(x => x.onchange = () => { checked = null; q("#movePlan", root).innerHTML = ""; q("#dlgFoot button.primary").textContent = "Check what moves"; });
      return false;
    }
    const btn = q("#dlgFoot button.primary"); btn.disabled = true; btn.textContent = "Moving…";
    try {
      const r = await api("POST", "/api/accounts/move", want);
      await loadBasics();
      toast(`Moved ${r.moved.join(", ")} to ${r.to}`);
      location.hash = "#/accounts"; render();
    } finally { btn.disabled = false; }
  } }]);
}

// Optional account details, as Moneydance keeps them: bank, numbers, website, rate;
// for credit cards the limit, statement and due days, a card payment kept on the
// schedule, and whether purchases on the card are tracked.
const CARD_TYPES = ["Credit Card", "Line of Credit"];
const BANK_TYPES = ["Checking", "Savings", "Money Market", "CD"];
// Accounts whose value moves with what they hold: "Update value" (investments are reminded monthly).
const VALUE_TYPES = ["Investment", "Retirement", "Asset"];
const VALUE_REMIND_TYPES = ["Investment", "Retirement"];
function accountDetailsForm(a, xsrc) {
  const d = a.details || {};
  const has = Object.keys(d).some(k => d[k] !== "" && d[k] !== false && d[k] != null);
  const payFrom = d.pay_from_account_id || (S.accounts.find(x => x.type === "Checking") || {}).id;
  const mode = d.pay_mode || "varies";
  const sources = S.accounts.filter(x => x.id !== a.id && !x.liability && !x.closed);
  // Folded in Simple (remembered per person); a hint says when something in it is filled in.
  return `<details class="acct-more more-fold" data-fold="account" ${foldOpen("account") ? "open" : ""}><summary>More details <span class="small muted">(optional)</span>${has ? ' <span class="fold-hint" title="Something in here is filled in">● filled in</span>' : ""}</summary>
    <div class="form" style="margin-top:8px">
      <div class="wide"><label>Bank or company</label><input name="d_institution" value="${esc(d.institution || "")}"></div>
      <div class="wide"><label>Website to sign in or pay</label><input name="d_website" type="url" inputmode="url" placeholder="https://www.example.com" value="${esc(d.website || "")}"></div>
      <div><label>Account number</label><input name="d_account_number" autocomplete="off" value="${esc(d.account_number || "")}"></div>
      <div class="d-bank"><label>Routing number</label><input name="d_routing_number" inputmode="numeric" maxlength="9" autocomplete="off" value="${esc(d.routing_number || "")}"></div>
      <div><label>Phone</label><input name="d_phone" type="tel" value="${esc(d.phone || "")}"></div>
      <div><label>Interest rate (%)</label><input name="d_interest_rate" class="num" value="${d.interest_rate != null ? esc(d.interest_rate) : ""}"></div>
      <div class="wide" style="grid-column:1/-1"><label>Contact or address</label><input name="d_contact" value="${esc(d.contact || "")}"></div>
    </div>
    <div class="d-value">
      <label class="check" style="margin-top:10px"><input type="checkbox" name="d_value_reminder" ${(d.value_reminder != null ? d.value_reminder : VALUE_REMIND_TYPES.includes(a.type || "")) ? "checked" : ""}>
        Remind me each month to update its value</label>
      <div class="small muted" style="margin-left:24px">Its value changes with what it holds, and MoneyThistle doesn't look values up: type it in from
        the statement or website with <b>Update value</b> in the account.</div>
    </div>
    <div class="d-hsa">
      <label class="check" style="margin-top:10px"><input type="checkbox" name="d_hsa" ${d.hsa ? "checked" : ""}> This is a Health Savings Account (HSA)</label>
      <div class="d-hsa-more" style="margin:4px 0 0 24px">
        <div class="small" style="margin-bottom:2px">Who puts money in?</div>
        <label class="check"><input type="radio" name="d_hsa_source" value="personal" ${(d.hsa_source || "personal") === "personal" ? "checked" : ""}> I do, from my own account, after tax (I deduct it on my return)</label>
        <label class="check"><input type="radio" name="d_hsa_source" value="employer" ${d.hsa_source === "employer" ? "checked" : ""}> My employer, or through payroll before tax (it's on my W-2)</label>
        <p class="small muted" style="margin:2px 0 0">The tax report (Reports → Taxes) lists money in and out of every HSA and adds them all up against the year's IRS limit.</p>
        <p class="small muted" style="margin:2px 0 0">Its type: <b>Savings</b> for an HSA kept as cash (spent with its card), <b>Investment</b> for one that's
          invested (then update its value now and then). One with both can be two accounts, each marked as an HSA.</p>
      </div>
    </div>
    <div class="d-card">
      <h3 style="margin:14px 0 4px">Credit card</h3>
      <div class="form">
        <div class="wide" style="grid-column:1/-1"><label>What is this card used for?</label>
          <select name="d_purpose_category_id">${catOptions(d.purpose_category_id, { full: true, blank: "Everything (general purpose)" })}</select>
          <div class="small muted" style="margin-top:2px">Pick a category if the card is only for one kind of spending (HSA-eligible care, giving, a business...): its purchases and statements go there unless you choose another, and a tax-related category puts them in the tax report.</div></div>
        <div><label>Credit limit</label><input name="d_credit_limit" class="num" value="${d.credit_limit ? dollars(d.credit_limit) : ""}"></div>
        <div><label>Statement closes on day</label><input name="d_statement_day" class="num" inputmode="numeric" placeholder="1-31" value="${esc(d.statement_day || "")}"></div>
        <div><label id="lblDueDay">Payment due on day</label><input name="d_due_day" class="num" inputmode="numeric" placeholder="1-31" value="${esc(d.due_day || "")}"></div>
      </div>
      <p class="small muted" style="margin:4px 0 0">For the last day of the month, enter <b>31</b>: shorter months use their last day (Feb 28 or 29, Apr 30...). The same goes for 29 and 30 in February.</p>
      <label class="check" style="margin-top:10px"><input type="checkbox" name="d_auto_pay" ${d.auto_pay ? "checked" : ""}> Keep the card payment on my Bills &amp; Deposits schedule, every month on the due day</label>
      <div class="d-autopay" style="margin:6px 0 0 24px">
        <div class="form">
          <div><label class="req">Pay from</label><select name="d_pay_from_account_id">${sources.length || (xsrc || []).length ? "" : `<option value="">(add a checking or savings account first)</option>`}${(xsrc || []).length
            ? `<optgroup label="${esc((S.me.envs.find(e => e.id === S.env) || {}).name || "")}">` : ""}${sources.map(x => `<option value="${x.id}" ${!d.pay_from_env_id && x.id == payFrom ? "selected" : ""}>${esc(x.name)}</option>`).join("")}${(xsrc || []).length ? "</optgroup>" : ""}
            ${(xsrc || []).map(({ e, list }) => `<optgroup label="${esc(e.name)}">${list.map(x => `<option value="e${e.id}:${x.id}" ${d.pay_from_env_id == e.id && x.id == d.pay_from_account_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</optgroup>`).join("")}</select>
            ${(xsrc || []).length ? `<div class="small muted" style="margin-top:2px">An account in another environment you own works too: the payment is kept there, and shows here as well.</div>` : ""}</div>
          <div><label id="lblPayAmt">Amount</label><input name="d_pay_amount" class="num" placeholder="0.00" value="${d.pay_amount ? dollars(d.pay_amount) : ""}"></div>
        </div>
        <label class="check"><input type="radio" name="d_pay_mode" value="varies" ${mode === "varies" ? "checked" : ""}> It varies: expect the average of what I've paid (the amount above until then)</label>
        <label class="check"><input type="radio" name="d_pay_mode" value="fixed" ${mode === "fixed" ? "checked" : ""}> The same amount each month (the amount above)</label>
        <label class="check"><input type="radio" name="d_pay_mode" value="full" ${mode === "full" ? "checked" : ""}> The full balance the card owes (best with purchases tracked)</label>
      </div>
      <div style="margin-top:10px"><b class="small">How do you keep this card?</b></div>
      <label class="check"><input type="radio" name="d_card_mode" value="statement" ${cardMode(d) === "statement" ? "checked" : ""}> I enter the statement balance each month</label>
      <p class="small muted" style="margin:0 0 4px 24px">One entry a month brings the card to what the statement says it owes; paying the card brings it back down. With the closing day filled in, Home reminds you once the statement has closed.</p>
      <label class="check"><input type="radio" name="d_card_mode" value="purchases" ${cardMode(d) === "purchases" ? "checked" : ""}> I enter each purchase</label>
      <p class="small muted" style="margin:0 0 0 24px">The scheduled-items Budget then shows this month's charges as pending (paid later, through the card payment) without counting them twice.</p>
    </div>
    <p class="small muted">Kept only in your MoneyThistle file and its backups. Account numbers show only their last four digits elsewhere.</p>
  </details>`;
}
function cardMode(d) { return (d && d.card_mode) || (d && d.track_purchases ? "purchases" : "statement"); }

// Enter a card's statement balance: one entry on the closing date that makes the card
// owe what the statement says (the month's purchases in one line).
async function statementDialog(acc, done) {
  const d = acc.details || {};
  const t = todayISO();
  let close = t;
  if (d.statement_day) {
    const [y, m] = t.split("-").map(Number), last = new Date(y, m, 0).getDate();
    const day = Math.min(d.statement_day, last);
    if (+t.slice(8) >= day) close = `${t.slice(0, 7)}-${String(day).padStart(2, "0")}`;
    else { const pm = new Date(y, m - 2, 1); const pl = new Date(pm.getFullYear(), pm.getMonth() + 1, 0).getDate();
      close = `${pm.getFullYear()}-${String(pm.getMonth() + 1).padStart(2, "0")}-${String(Math.min(d.statement_day, pl)).padStart(2, "0")}`; }
  }
  const last = d.last_statement;
  return dialog("Statement balance: " + acc.name, `<div class="form">
      <div><label>Statement closing date</label><input type="date" name="date" value="${close}"></div>
      <div><label>New balance on the statement</label><input name="balance" class="num" placeholder="0.00" required></div>
      <div class="wide" style="grid-column:1/-1"><label>Count the purchases as <span class="muted">(optional, for the category budget)</span></label>
        <select name="category_id">${catOptions(d.purpose_category_id || null, { full: true })}</select></div></div>
    <p class="small muted">MoneyThistle adds one entry on that date so the card owes exactly this amount then; payments after it bring it down.
      ${last ? `Last statement: ${niceDate(last.date)}, ${fmt(last.balance, true)}.` : ""} Entering a statement again for the same date replaces it.</p>`,
    [{ label: "Cancel" }, { label: "Save statement", cls: "primary", action: async root => {
      const f = formData(root);
      await api("POST", `/api/accounts/${acc.id}/statement`, f);
      toast("Statement saved"); await loadBasics(); if (done) done(); else render();
    } }]);
}

// Cards whose statement has closed but whose balance isn't entered yet.
function statementsDueNote(list) {
  if (!list || !list.length) return "";
  return `<div class="notice" style="margin-bottom:12px">${list.map(s => `<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:2px 0">
      ${s.kind === "value" ? `<span>📈 <b translate="no">${esc(s.name)}</b>${envTag(s)}: ${esc(tr(s.updated ? "value last updated" : "value not updated since"))} ${niceDate(s.last_date)}.</span>
      <button class="small primary" data-valacct="${s.account_id}" data-valenv="${s.env_id || ""}">Update value</button>` : `
      <span>🧾 The <b>${esc(s.name)}</b>${envTag(s)} statement closed ${niceDate(s.closing_date)}: enter its balance.</span>
      <button class="small primary" data-stmt="${s.account_id}" data-stmtenv="${s.env_id || ""}">Enter statement</button>`}
      ${/^https?:\/\//i.test(s.website || "") ? `<a class="btn small" href="${esc(s.website)}" target="_blank" rel="noopener noreferrer">See it online ↗</a>` : ""}</div>`).join("")}</div>`;
}
function wireStatementsDue() {
  qa("[data-valacct]").forEach(b => b.onclick = async () => {
    await goEnv(+b.dataset.valenv);
    const acc = S.accounts.find(a => a.id == b.dataset.valacct);
    if (acc) valueDialog(acc);
  });
  qa("[data-stmt]").forEach(b => b.onclick = async () => {
    await goEnv(+b.dataset.stmtenv);   // a card in another of my environments: go there first
    const acc = S.accounts.find(a => a.id == b.dataset.stmt);
    if (acc) statementDialog(acc);
  });
}
// An investment's value now, from its statement or website: the difference goes in as one
// "Change in Value" entry (left out of budgets and spending reports).
function valueDialog(acc) {
  const last = (acc.details || {}).last_value;
  return dialog("Update value: " + acc.name, `<p class="small muted" style="margin-top:0">From the statement or the website. MoneyThistle records
    the difference as a <b>Change in value</b> entry, left out of budgets and spending reports.</p>
    <div class="form"><div><label>Date</label><input type="date" name="date" value="${todayISO()}"></div>
    <div><label class="req">Value on that date</label><input name="value" class="num" inputmode="decimal" placeholder="0.00"></div></div>
    <p class="small muted">${esc(tr("Balance now"))}: <b>${fmt(acc.balance, true, acc)}</b>${last ? ` · ${esc(tr("last updated"))} ${niceDate(last.date)}` : ""}</p>`,
    [{ label: "Cancel" }, { label: "Update value", cls: "primary", action: async root => {
      const f = formData(root);
      if (!(parseAmount(f.value) >= 0)) { const e = new Error("Enter the value on that date"); e.field = "value"; throw e; }
      const r = await api("POST", `/api/accounts/${acc.id}/value`, f);
      toast(r.change ? `${tr("Value updated")}: ${fmt(r.change, true, acc)}` : tr("Value updated: no change"));
      await loadBasics(); render();
    } }]);
}
function showDetailParts(type) {
  const card = q("#dlgBody .d-card"), bank = q("#dlgBody .d-bank"), hsa = q("#dlgBody .d-hsa");
  if (card) card.style.display = CARD_TYPES.includes(type) ? "" : "none";
  if (bank) bank.style.display = BANK_TYPES.includes(type) ? "" : "none";
  if (hsa) hsa.style.display = (S.meta.liability_types || []).includes(type) ? "none" : "";
  const val = q("#dlgBody .d-value");
  if (val) {
    val.style.display = VALUE_TYPES.includes(type) ? "" : "none";
    // (a type chosen just now: its usual reminder setting)
    const cb = q("[name=d_value_reminder]", val);
    if (cb && !cb.dataset.touched) cb.checked = VALUE_REMIND_TYPES.includes(type);
    if (cb && !cb.dataset.wired) { cb.dataset.wired = 1; cb.addEventListener("change", () => { cb.dataset.touched = 1; }); }
  }
}
function wireDetailsForm() {
  const hsa = q("#dlgBody [name=d_hsa]"), hsaMore = q("#dlgBody .d-hsa-more");
  if (hsa) { const u = () => { hsaMore.style.display = hsa.checked ? "" : "none"; }; hsa.addEventListener("change", u); u(); }
  const ap = q("#dlgBody [name=d_auto_pay]"), box = q("#dlgBody .d-autopay");
  if (!ap) return;
  // Scheduling the payment needs the due day (and, for "the same amount", the amount):
  // those get the "must be filled in" mark while it's ticked.
  const upd = () => {
    box.style.display = ap.checked ? "" : "none";
    const fixed = (q("#dlgBody [name=d_pay_mode]:checked") || {}).value === "fixed";
    q("#lblDueDay").classList.toggle("req", ap.checked);
    q("#lblPayAmt").classList.toggle("req", ap.checked && fixed);
  };
  ap.addEventListener("change", upd);
  qa("#dlgBody [name=d_pay_mode]").forEach(r => r.addEventListener("change", upd));
  upd();
}
// One line of an account's details above its register: bank, number, website, rate,
// and for cards the credit left and the due day.
function ordinal(n) { const s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); }
function accountDetailsLine(acc) {
  const d = acc.details || {};
  const bits = [];
  if (d.hsa) bits.push(`<span class="pill green" title="Health Savings Account: in the tax report">HSA${d.hsa_source === "employer" ? " · employer" : ""}</span>`);
  const purpose = d.purpose_category_id && (S.cats || []).find(c => c.id == d.purpose_category_id);
  if (purpose) bits.push(`<span class="pill" title="This card is used only for this kind of spending">only ${esc(purpose.full_name)}</span>`);
  if (d.institution) bits.push(esc(d.institution));
  if (d.account_number) bits.push(`<span title="Account number (last four digits)">${esc(lastFour(d.account_number))}</span>`);
  if (d.interest_rate != null) bits.push(`${esc(d.interest_rate)}% interest`);
  if (d.credit_limit) bits.push(`limit ${fmt(d.credit_limit, true)} · <b>${fmt(Math.max(0, d.credit_limit + acc.balance), true)}</b> available`);
  // 31 is the last day of every month (shorter months use theirs).
  const onDay = n => n >= 31 ? "the last day of the month" : `the ${ordinal(n)}`;
  if (d.statement_day) bits.push(`statement closes on ${onDay(d.statement_day)}`);
  if (d.due_day) bits.push(`payment due on ${onDay(d.due_day)}`);
  if (d.phone) bits.push(`<a href="tel:${esc(d.phone.replace(/[^\d+]/g, ""))}">${esc(d.phone)}</a>`);
  if (/^https?:\/\//i.test(d.website || "")) bits.push(`<a href="${esc(d.website)}" target="_blank" rel="noopener noreferrer">${CARD_TYPES.includes(acc.type) ? "Pay or sign in online" : "Sign in online"} ↗</a>`);
  return bits.length ? `<div class="toolbar small muted" style="margin-top:-6px;flex-wrap:wrap">${bits.join(" · ")}</div>` : "";
}
// "••••1234": enough to recognise an account number without showing it all.
function lastFour(n) { const s = String(n || "").replace(/\s/g, ""); return s ? "••••" + s.slice(-4) : ""; }

// ---------- LOANS ----------
const PPY = [[12, "Monthly (12 a year)"], [26, "Every other week (26)"], [24, "Twice a month (24)"], [52, "Weekly (52)"],
  [4, "Every three months (4)"], [6, "Every other month (6)"], [2, "Twice a year (2)"], [1, "Yearly (1)"]];

async function editLoan(acc, presetName, preset) {
  await loadBasics();
  const info = acc && acc.has_loan ? await GET("/api/loans/" + acc.id) : null;
  // (preset: terms from the loan calculator)
  const L = info || Object.assign({ original_amount: 0, apr: "", payments_per_year: 12, num_payments: 360, first_payment: todayISO(),
    payment_mode: "calc", payment: 0, escrow: 0, escrow_category_id: null, escrow_account_id: null,
    interest_category_id: null, pay_from_account_id: (S.accounts.find(a => a.type === "Checking") || {}).id, payee: "" }, preset || {});
  const name = acc ? acc.name : (presetName || "");
  // An existing account getting loan terms (brought in from another program): its register stays.
  const converting = !!(acc && !info);
  const catId = full => (S.cats.find(c => c.full_name === full) || {}).id;
  const intCat = L.interest_category_id || (/mortgage|home|house/i.test(name) ? catId("Loan : Mortgage Interest") : catId("Loan : Loan Interest"));
  const escrowVal = L.escrow_account_id ? "a:" + L.escrow_account_id : (L.escrow_category_id ? "c:" + L.escrow_category_id : "");
  const others = S.accounts.filter(a => !acc || a.id !== acc.id);
  const body = `<div class="form">
    <div class="wide"><label>Loan name</label><input name="name" value="${esc(name)}" placeholder="Home mortgage"></div>
    <div class="wide"><label>Lender (payee on payments)</label><input name="payee" value="${esc(L.payee)}" placeholder="Name of the bank"></div>
    <div><label>Loan amount (principal)</label><input name="original_amount" class="num" value="${L.original_amount ? dollars(L.original_amount) : ""}" placeholder="0.00"></div>
    <div><label>Interest rate (APR %)</label><input name="apr" class="num" value="${esc(L.apr)}" placeholder="6.25"></div>
    <div><label>Payments per year</label><select name="payments_per_year">${PPY.map(([v, l]) => `<option value="${v}" ${v == L.payments_per_year ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    <div><label>Number of payments <span id="yrs" class="muted"></span></label><input name="num_payments" class="num" value="${L.num_payments}"></div>
    <div><label>First payment date</label><input type="date" name="first_payment" value="${esc(L.first_payment)}"></div>
    <div class="wide"><label>Interest category</label><select name="interest_category_id">${catOptions(intCat, { full: true })}</select></div>
    <div><label>Escrow per payment</label><input name="escrow" class="num" value="${dollars(L.escrow)}"></div>
    <div class="wide"><label>Escrow goes to</label><select name="escrow_to">
      <option value="">Nothing to track (the lender holds it)</option>
      <optgroup label="One of my accounts">${others.map(a => `<option value="a:${a.id}" ${escrowVal === "a:" + a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</optgroup>
      <optgroup label="A category">${S.cats.filter(c => c.kind === "expense").map(c => `<option value="c:${c.id}" ${escrowVal === "c:" + c.id ? "selected" : ""}>${esc(catFull(c))}</option>`).join("")}</optgroup>
    </select></div>
    <div class="wide" style="grid-column:1/-1"><label>Payment (principal + interest)</label>
      <label class="check"><input type="radio" name="payment_mode" value="calc" ${L.payment_mode !== "fixed" ? "checked" : ""}> Calculate it: <b id="calcPay" style="margin-left:4px">–</b></label>
      <label class="check"><input type="radio" name="payment_mode" value="fixed" ${L.payment_mode === "fixed" ? "checked" : ""}> Use this amount: <input name="payment" class="num" value="${L.payment ? dollars(L.payment) : ""}" style="margin-left:4px"></label></div>
    <div class="wide"><label>Pay from</label><select name="pay_from_account_id"><option value="">(I'll record payments myself)</option>
      ${S.accounts.filter(a => !acc || a.id !== acc.id).map(a => `<option value="${a.id}" ${a.id == L.pay_from_account_id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></div>
    <div><label>Balance owed now</label><input name="balance_now" class="num" placeholder="(calculated)"></div>
    ${autoFields(info && info.bill ? info.bill : {})}
  </div>
  <div class="notice" id="loanPrev" style="margin:12px 0 0">Fill in the amount, rate and number of payments.</div>
  ${converting ? `<p class="small muted" style="margin-bottom:0">Worked out from this account's register (${(preset && preset.found_payments) || 0} payments):
  check each one against a statement. A payment found there may include escrow; if so, put the escrow part in "Escrow per payment"
  and lower the payment. The register and its balance stay as they are; leave "Balance owed now" empty to keep it.</p>`
  : `<p class="small muted" style="margin-bottom:0">A loan that started a while ago: enter its original terms and first payment date; the balance owed now
  is worked out from the schedule. If your statement says something different, type that amount in "Balance owed now".
  ${info ? "Leave it empty to keep the current balance." : ""}</p>`}`;
  const btns = [{ label: "Cancel" }];
  if (info) btns.unshift({ label: "Delete loan", cls: "danger", action: async () => {
    if (!(await confirmBox(`Delete "${acc.name}" and its history? Payments already recorded in other accounts stay there.`))) return false;
    await api("DELETE", "/api/accounts/" + acc.id); await loadBasics(); location.hash = "#/accounts"; render(); } });
  const collect = root => {
    const f = formData(root);
    f.payment_mode = (qa("[name=payment_mode]", root).find(r => r.checked) || {}).value || "calc";
    f.escrow_account_id = f.escrow_to.startsWith("a:") ? f.escrow_to.slice(2) : null;
    f.escrow_category_id = f.escrow_to.startsWith("c:") ? f.escrow_to.slice(2) : null;
    f.type = "Loan";
    if (!f.balance_now) delete f.balance_now;
    return f;
  };
  btns.push({ label: acc ? "Save" : "Add loan", cls: "primary", action: async root => {
    const f = collect(root);
    const r = acc ? await api("PUT", "/api/loans/" + acc.id, f) : await api("POST", "/api/loans", f);
    // Automatic payment: kept on the loan's scheduled payment.
    const saved = await GET("/api/loans/" + r.id);
    if (saved.bill) await api("PUT", `/api/bills/${saved.bill.id}/auto`, { auto: f.auto, auto_enter: f.auto_enter });
    await loadBasics(); location.hash = "#/accounts/" + r.id; render(); toast("Loan saved");
  } });
  const p = dialog(converting ? "Set up loan details" : (acc ? "Loan details" : "New loan"), body, btns);
  const root = q("#dlgBody");
  wireAutoFields();
  let timer;
  const refresh = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const f = collect(root);
      const n = +f.num_payments, ppy = +f.payments_per_year;
      q("#yrs").textContent = n && ppy ? `(${(n / ppy).toFixed(n % ppy ? 1 : 0)} years)` : "";
      if (!f.original_amount || !f.num_payments) return;
      try {
        const pv = await api("POST", "/api/loans/preview", f);
        q("#calcPay").textContent = fmt(pv.payment, true);
        const escrow = pv.escrow || 0;
        q("#loanPrev").className = "notice ok";
        q("#loanPrev").innerHTML = `Each payment: <b>${fmt(pv.payment + escrow, true)}</b>
          (${fmt(pv.payment, true)} principal &amp; interest${escrow ? ` + ${fmt(escrow, true)} escrow` : ""}).
          ${converting && !f.balance_now ? `Owed now, from this account's register: <b>${fmt(Math.abs(acc.balance), true)}</b>.`
            : (pv.payments_made ? `${pv.payments_made} of ${pv.num_payments} payments already made; owed now about <b>${fmt(pv.balance_now, true)}</b>.` : `Owed: <b>${fmt(pv.balance_now, true)}</b>.`)}
          Next payment ${niceDate(pv.next_payment_date)}.`;
      } catch (e) { q("#loanPrev").className = "notice err"; q("#loanPrev").textContent = e.message; }
    }, 250);
  };
  qa("input,select", root).forEach(el => { el.addEventListener("input", refresh); el.addEventListener("change", refresh); });
  refresh();
  return p;
}

// Record a loan payment: principal, interest and escrow, editable, with the total.
async function payLoan(loanId, occ) {
  const L = await GET("/api/loans/" + loanId);
  const n = L.next;
  const from = occ ? occ.account_id : L.pay_from_account_id;
  const body = `<div class="form">
    <div class="wide"><label>Pay from</label><select name="account_id">${acctOptions(from, loanId)}</select></div>
    <div><label>Date</label><input type="date" name="date" value="${occ ? (occ.date || occ.next_date) : n.date}"></div>
    <div><label>Check / confirmation #</label><input name="number"></div>
  </div>
  <table style="margin-top:12px;max-width:420px">
    <tr><td>Principal <span class="small muted">(lowers what you owe)</span></td><td class="num"><input name="principal" class="num lp" value="${dollars(n.principal)}"></td></tr>
    <tr><td>Interest <span class="small muted">${esc(L.interest_category_name || "")}</span></td><td class="num"><input name="interest" class="num lp" value="${dollars(n.interest)}"></td></tr>
    <tr><td>Escrow <span class="small muted">${esc(L.escrow_account_name || L.escrow_category_name || (L.escrow ? "held by the lender" : ""))}</span></td><td class="num"><input name="escrow" class="num lp" value="${dollars(n.escrow)}"></td></tr>
    <tr><td><b>Total payment</b></td><td class="num"><b id="lpTotal"></b></td></tr>
  </table>
  <div class="form" style="margin-top:10px"><div class="wide" style="grid-column:1/-1"><label>Memo</label><input name="memo"></div></div>
  <p class="small muted">Owed before this payment: ${fmt(L.owed, true)}. Interest is the balance × ${esc(L.apr)}% ÷ ${L.payments_per_year}; change any amount to match your statement.</p>
  ${heldFilesHtml("lp")}`;
  const p = dialog("Loan payment: " + L.account.name, body, [{ label: "Cancel" }, { label: "Record payment", cls: "primary", action: async root => {
    const f = formData(root);
    const r = occ && occ.id ? await api("POST", `/api/bills/${occ.id}/enter`, f) : await api("POST", `/api/loans/${loanId}/pay`, f);
    const n = await held.send(r && (r.id || (r.ids && r.ids[0])));
    toast("Payment recorded" + filesNote(n)); await loadBasics(); render();
  } }]);
  const root = q("#dlgBody");
  const held = holdFiles("lp", root);
  dateHint(q("[name=date]", root));
  const total = () => {
    const sum = qa(".lp", root).reduce((s, i) => s + Math.round((parseAmount(i.value) || 0) * 100), 0);
    q("#lpTotal").textContent = fmt(sum, true, top);
  };
  qa(".lp", root).forEach(i => i.oninput = total); total();
  return p;
}

function loanCard(L) {
  const n = L.next;
  return `<div class="card" style="margin-bottom:12px"><div class="head"><h2>Loan</h2>
      <span><button class="small primary" id="loanPay">Make a payment</button> <button class="small" id="loanSched">Payment schedule</button> <button class="small" id="loanWhatIf" title="Try an extra payment or paying more often, and see when it would be paid off. Nothing is changed.">What if…</button></span></div>
    <div class="grid" style="grid-template-columns:repeat(4,1fr);gap:10px">
      <div><div class="small muted">Still owed</div><div class="big neg">${fmt(L.owed, true)}</div><div class="small muted">of ${fmt(L.original_amount, true)} borrowed</div></div>
      <div><div class="small muted">Next payment ${n.date ? niceDate(n.date) : ""}</div><div class="big">${fmt(n.total, true)}</div>
        <div class="small muted">${fmt(n.principal, true)} principal · ${fmt(n.interest, true)} interest${n.escrow ? ` · ${fmt(n.escrow, true)} escrow` : ""}</div></div>
      <div><div class="small muted">Rate and term</div><div class="big">${esc(L.apr)}%</div><div class="small muted">${L.num_payments} payments, ${L.payments_per_year} a year</div></div>
      <div><div class="small muted">Paid off</div><div class="big">${L.payoff_date ? niceDate(L.payoff_date) : (L.never_ends ? "never" : "–")}</div>
        <div class="small muted">${L.payments_left} payments left · ${fmt(L.total_interest_left, true)} interest to go</div></div>
    </div>
    ${L.never_ends ? `<div class="notice err" style="margin:10px 0 0">The payment doesn't cover the interest, so this loan would never be paid off. Check the payment amount.</div>` : ""}
    <div class="small muted" style="margin-top:8px">Interest paid so far (recorded here): ${fmt(L.interest_paid, true)} over ${L.payments_recorded} payments.
      ${L.pay_from_name ? `Payments come from ${esc(L.pay_from_name)} and show up under Bills &amp; Deposits.` : "No paying account set: record payments with <b>Make a payment</b>."}</div>
    <div id="schedWrap" style="display:none;margin-top:10px;max-height:340px;overflow:auto"><table>
      <tr><th>#</th><th>Date</th><th class="num">Principal</th><th class="num">Interest</th><th class="num">Payment</th><th class="num">Owed after</th></tr>
      ${L.schedule.map(r => `<tr><td class="small muted">${r.n}</td><td class="small">${niceDate(r.date)}</td><td class="num">${fmt(r.principal, true)}</td><td class="num">${fmt(r.interest, true)}</td><td class="num">${fmt(r.payment, true)}</td><td class="num">${fmt(r.balance, true)}</td></tr>`).join("")}
    </table></div></div>`;
}

// ---------- what if: other payments on a loan, and the loan calculator (nothing saved) ----------
const monthsBetween = (a, b) => (+b.slice(0, 4) - +a.slice(0, 4)) * 12 + (+b.slice(5, 7) - +a.slice(5, 7));
function ppyLabel(v) { return (PPY.find(p => p[0] == v) || [v, v + " a year"])[1]; }

function whatIfResult(r) {
  const a = r.now, b = r.then;
  const end = s => s.never_ends ? "never" : (s.payoff_date ? niceDate(s.payoff_date) : "–");
  let verdict = "";
  if (b.never_ends) verdict = `<div class="notice err">This payment doesn't cover the interest, so the loan would never be paid off.</div>`;
  else if (a.never_ends) verdict = `<div class="notice ok">With these payments it would be paid off ${niceDate(b.payoff_date)}.</div>`;
  else if (a.payoff_date && b.payoff_date) {
    const m = monthsBetween(b.payoff_date, a.payoff_date), less = a.interest - b.interest;
    const when = m > 0 ? `<b>${m} months sooner</b>${m >= 12 ? ` <span class="muted">(about ${(m / 12).toLocaleString(typeof LOCALE === "string" ? LOCALE : undefined, { maximumFractionDigits: 1 })} years)</span>` : ""}`
      : (m < 0 ? `<b>${-m} months later</b>` : `<b>Paid off the same month</b>`);
    const money = less > 0 ? `<b>${fmt(less, true)} less interest</b>` : (less < 0 ? `<b>${fmt(-less, true)} more interest</b>` : "");
    verdict = `<div class="notice${m > 0 || less > 0 ? " ok" : ""}">${when}${money ? " · " + money : ""}</div>`;
  }
  const row = (label, x, y) => `<tr><td>${label}</td><td class="num">${x}</td><td class="num"><b>${y}</b></td></tr>`;
  const extras = r.schedule.some(s => s.extra);
  return `${verdict}<table style="margin-top:10px;max-width:560px">
      <tr><th></th><th class="num">As now</th><th class="num">What if</th></tr>
      ${row("How often", esc(ppyLabel(a.payments_per_year)), esc(ppyLabel(b.payments_per_year)))}
      ${row("Each payment (principal + interest)", fmt(a.payment, true), fmt(b.payment, true))}
      ${row("Paid off", end(a), end(b))}
      ${row("Payments left", a.payments_left, b.payments_left)}
      ${row("Interest still to pay", fmt(a.interest, true), fmt(b.interest, true))}
      ${row("Total still to pay", fmt(a.total, true), fmt(b.total, true))}
    </table>
    ${b.extra_once_applied ? "" : `<p class="small muted">The one-time extra payment comes after the loan would already be paid off.</p>`}
    <p style="margin:8px 0 0"><button type="button" class="small" id="wiShow" aria-expanded="false">Show the payments</button></p>
    <div id="wiSched" hidden style="margin-top:8px;max-height:300px;overflow:auto"><table>
      <tr><th>#</th><th>Date</th><th class="num">Principal</th>${extras ? `<th class="num">Extra</th>` : ""}<th class="num">Interest</th><th class="num">Payment</th><th class="num">Owed after</th></tr>
      ${r.schedule.map(s => `<tr><td class="small muted">${s.n}</td><td class="small">${niceDate(s.date)}</td><td class="num">${fmt(s.principal, true)}</td>${extras ? `<td class="num">${s.extra ? fmt(s.extra, true) : ""}</td>` : ""}<td class="num">${fmt(s.interest, true)}</td><td class="num">${fmt(s.payment, true)}</td><td class="num">${fmt(s.balance, true)}</td></tr>`).join("")}
    </table></div>`;
}

// What if: the loan as it is against the same loan with an extra payment once, extra with
// every payment, or paying more often. Nothing is saved.
async function loanWhatIf(L) {
  const ppy = L.payments_per_year;
  const choices = [ppy, ...[12, 24, 26].filter(v => v !== ppy)];
  const body = `<p class="small muted" style="margin-top:0">Try other payments and see when this loan would be paid off and how much interest it would cost.
    Nothing here changes the loan or your schedule.</p>
    <div class="form">
      <div><label>Extra toward principal, once</label><input name="extra_once" class="num" placeholder="0.00"></div>
      <div><label>With the payment on</label><input type="date" name="extra_once_date" value="${esc(L.next.date || todayISO())}"></div>
      <div><label>Extra toward principal with every payment</label><input name="extra_each" class="num" placeholder="0.00"></div>
      <div></div>
      <div><label>How often you pay</label><select name="payments_per_year">${choices.map(v => `<option value="${v}">${esc(ppyLabel(v))}</option>`).join("")}</select></div>
      <div><label>Each payment (principal + interest)</label><input name="payment" class="num" value="${dollars(L.payment)}"></div>
    </div>
    <div id="wiOut" style="margin-top:12px"></div>
    <p class="small muted" style="margin-bottom:0">Principal and interest only; escrow isn't included. Interest is worked out as for this loan:
    what's owed × ${esc(L.apr)}% ÷ payments a year. Lenders differ: some don't take extra or more frequent payments, charge for them,
    or hold a half payment until the other half arrives. Ask yours before you change how you pay.</p>`;
  const p = dialog("What if: " + L.account.name, body, [{ label: "Close" }]);
  const root = q("#dlgBody");
  let timer;
  const refresh = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const f = formData(root);
      const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== "")).toString();
      const out = q("#wiOut", root);
      try {
        const r = await GET(`/api/loans/${L.account.id}/what-if?${qs}`);
        out.innerHTML = whatIfResult(r);
        // (left empty, the server suggests the payment for this "how often": see loans.converted_payment)
        const pay = q("[name=payment]", root);
        if (!pay.value.trim()) pay.value = dollars(r.then.payment);
        q("#wiShow", out).onclick = e => {
          const t = q("#wiSched", out), open = t.hidden;
          t.hidden = !open; e.target.setAttribute("aria-expanded", open);
          e.target.textContent = open ? "Hide the payments" : "Show the payments";
        };
      } catch (e) { out.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; }
    }, 250);
  };
  // A new "how often" starts from its usual payment (the server's suggestion), which can then be changed.
  q("[name=payments_per_year]", root).addEventListener("change", () => { q("[name=payment]", root).value = ""; });
  qa("input,select", root).forEach(el => { el.addEventListener("input", refresh); el.addEventListener("change", refresh); });
  refresh();
  return p;
}

// The loan calculator: the payment for a price, or the price a payment can buy. Nothing is
// saved; "Set up this loan…" starts a new loan from it.
async function loanCalculator() {
  const body = `<p class="small muted" style="margin-top:0">Work out a loan before you take it. Nothing is saved.</p>
    <div class="form">
      <div class="wide" style="grid-column:1/-1">
        <label class="check"><input type="radio" name="lc_mode" value="payment" checked> I know the price: what would the payment be?</label>
        <label class="check"><input type="radio" name="lc_mode" value="amount"> I know the payment I can afford: what price can I pay?</label></div>
      <div id="lcPrice"><label>Price or loan amount</label><input name="price" class="num" placeholder="0.00"></div>
      <div id="lcPay" style="display:none"><label>Payment I can afford</label><input name="payment" class="num" placeholder="0.00"></div>
      <div><label>Down payment or trade-in</label><input name="down" class="num" placeholder="0.00"></div>
      <div><label>Interest rate (APR %)</label><input name="apr" class="num" placeholder="6.5"></div>
      <div><label>Years</label><input name="years" class="num" value="5"></div>
      <div><label>Payments per year</label><select name="payments_per_year">${PPY.map(([v, l]) => `<option value="${v}" ${v === 12 ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    </div>
    <div id="lcOut" style="margin-top:12px"><div class="notice">Fill in the amounts, the rate and the years.</div></div>
    <p class="small muted" style="margin-bottom:0">An estimate: sales tax, fees and insurance aren't included, and lenders round a little differently.</p>`;
  let last = null;
  const btns = [{ label: "Close" }];
  if (canEdit() && !S.shareCtx) btns.unshift({ label: "Set up this loan…", action: () => {
    if (!last || !last.amount) { dialogError(new Error("Fill in the amounts first")); return false; }
    const r = last;
    setTimeout(() => editLoan(null, "", { original_amount: r.amount, apr: r.apr, payments_per_year: r.payments_per_year,
      num_payments: r.num_payments, payment_mode: "calc" }), 0);
  } });
  const p = dialog("Loan calculator", body, btns);
  const root = q("#dlgBody");
  const mode = () => (qa("[name=lc_mode]", root).find(r => r.checked) || {}).value || "payment";
  let timer;
  const refresh = () => {
    q("#lcPrice", root).style.display = mode() === "payment" ? "" : "none";
    q("#lcPay", root).style.display = mode() === "amount" ? "" : "none";
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const f = formData(root), m = mode();
      const out = q("#lcOut", root);
      if (!(m === "payment" ? f.price : f.payment) || !f.years) { last = null; return; }
      const qs = new URLSearchParams({ mode: m, price: f.price || "", payment: f.payment || "", down: f.down || "",
        apr: f.apr || "0", years: f.years, payments_per_year: f.payments_per_year }).toString();
      try {
        const r = last = await GET("/api/loans/calculate?" + qs);
        const line = (label, v, strong) => `<tr><td>${label}</td><td class="num">${strong ? `<b>${v}</b>` : v}</td></tr>`;
        out.innerHTML = `<table style="max-width:460px">
          ${line("Each payment", fmt(r.payment, true), m === "payment")}
          ${line("Number of payments", r.num_payments)}
          ${line("Loan amount", fmt(r.amount, true), m === "amount")}
          ${r.down ? line("Down payment or trade-in", fmt(r.down, true)) : ""}
          ${line("Price", fmt(r.price, true), m === "amount")}
          ${line("Interest over the loan", fmt(r.interest, true))}
          ${line("Total of the payments", fmt(r.total, true))}
        </table>`;
      } catch (e) { last = null; out.innerHTML = `<div class="notice err">${esc(e.message)}</div>`; }
    }, 250);
  };
  qa("input,select", root).forEach(el => { el.addEventListener("input", refresh); el.addEventListener("change", refresh); });
  refresh();
  return p;
}

// Registers list newest first by default; each person can choose oldest first, like a
// paper ledger.
function registerOrder(rows) {
  regOldestFirst = !!(S.ui && S.ui.register_order === "oldest");
  return regOldestFirst ? rows.slice().reverse() : rows;
}
// Where a register opens. Oldest first, entries are added at the bottom, so it opens at its
// end, where the newest are; newest first, at its top. Drawn again for the same register
// (after saving an entry), it stays where it was. Call before the register is drawn.
let regPlaceKey = null;
function regPlace(key) {
  key += "|" + (regOldestFirst ? "old" : "new");
  const r = q(".register");
  const was = r && regPlaceKey === key ? { top: r.scrollTop, win: window.scrollY } : null;
  regPlaceKey = key;
  requestAnimationFrame(() => {
    const reg = q(".register");
    if (!reg) return;
    if (was) { reg.scrollTop = was.top; window.scrollTo(0, was.win); return; }
    if (!regOldestFirst) return;
    if (reg.scrollHeight > reg.clientHeight + 2) reg.scrollTop = reg.scrollHeight;   // the register scrolls by itself
    else {   // (small screens: the page scrolls) the last entry in view
      const rows = qa("#reg tr").filter(tr => !tr.hidden);   // (folded parts of a split are hidden)
      const last = rows[rows.length - 1];
      if (last && last.getBoundingClientRect().bottom > window.innerHeight) last.scrollIntoView({ block: "end" });
    }
  });
}
function regOrderButton() {
  const oldest = S.ui && S.ui.register_order === "oldest";
  return `<button id="regOrder" title="Change the order of the register">${oldest ? "Oldest first ▼" : "Newest first ▲"}</button>`;
}
// One listener for the register's order button and ▲▼ arrows (capture phase, so a
// click on an arrow doesn't also open the entry).
document.addEventListener("click", async e => {
  const mv = e.target.closest && e.target.closest("[data-move]");
  const ord = e.target.closest && e.target.closest("#regOrder");
  if (!mv && !ord) return;
  e.stopPropagation(); e.preventDefault();
  try {
    if (mv) {
      const [id, dir] = mv.dataset.move.split(":");
      await api("POST", `/api/transactions/${id}/move`, { direction: dir });
    } else {
      S.ui = await api("PUT", "/api/settings", { register_order: S.ui.register_order === "oldest" ? "newest" : "oldest" });
    }
    render();
  } catch (err) { toast(err.message, true); }
}, true);

// Order within a day: arrows on entries that share their date with another, moving
// it up or down as shown (oldest-first: up = earlier; newest-first: up = later).
let regDayCount = {}, regOldestFirst = false;
function moveBtns(t) {
  if ((regDayCount[t.date] || 0) < 2) return "";
  const up = regOldestFirst ? "earlier" : "later", down = regOldestFirst ? "later" : "earlier";
  return `<span class="movebtns"><button type="button" class="tiny" data-move="${t.id}:${up}" title="Move up (${up} that day)" aria-label="Move up">▲</button><button type="button" class="tiny" data-move="${t.id}:${down}" title="Move down (${down} that day)" aria-label="Move down">▼</button></span>`;
}

// Split payments (paystubs, loan payments, splits) opened with ▸ in the register this session.
const REG_OPEN = new Set();
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-tog]");
  if (!b) return;
  e.stopPropagation(); e.preventDefault();   // (not a click on the row: that opens the payment)
  const gid = b.dataset.tog, open = !REG_OPEN.has(gid);
  if (open) REG_OPEN.add(gid); else REG_OPEN.delete(gid);
  qa(`tr[data-part="${gid}"]`).forEach(r => { r.hidden = !open; });
  b.setAttribute("aria-expanded", String(open));
  b.textContent = `${open ? "▾" : "▸"} ${qa(`tr[data-part="${gid}"]`).length} ${tr("parts")}`;
}, true);

// Register rows: lines of one split payment (same group) are shown together, as one line
// whose parts fold out.
function registerRows(rows) {
  // How many register lines (a split payment counts once) share each date.
  regDayCount = {};
  const seenGroup = new Set();
  for (const t of rows) {
    if (t.group_id) { if (seenGroup.has(t.group_id)) continue; seenGroup.add(t.group_id); }
    regDayCount[t.date] = (regDayCount[t.date] || 0) + 1;
  }
  const out = [];
  for (let i = 0; i < rows.length; i++) {
    const t = rows[i];
    if (!t.group_id) { out.push({ one: t }); continue; }
    const parts = [t];
    while (i + 1 < rows.length && rows[i + 1].group_id === t.group_id) parts.push(rows[++i]);
    out.push({ group: parts });
  }
  // Entries dated after today get a bar and a shade (like a paper register's pencilled-in lines).
  const today = todayISO();
  return out.map(r => {
    if (r.one) {
      const t = r.one;
      return `<tr class="click${t.date > today ? " future" : ""}"${t.date > today ? ' title="Dated after today"' : ""} data-id="${t.id}"><td class="status ${t.status}" data-st="${t.id}" title="Click: blank → cleared → reconciled">${t.status || "·"}</td>
        <td class="small">${niceDate(t.date)}${moveBtns(t)}</td><td class="small">${esc(t.number)}</td><td>${esc(t.payee)}${t.auto ? ' <span class="pill auto" title="Recorded automatically from an automatic scheduled item">⟳ auto</span>' : ""}${t.attachments ? ` <span class="clip" title="${t.attachments} receipt${t.attachments === 1 ? "" : "s"} or file${t.attachments === 1 ? "" : "s"} attached">${CLIP_ICON}${t.attachments > 1 ? t.attachments : ""}</span>` : ""}${payPills(t)}</td>
        <td class="small">${esc(t.category_label)}${otherSide(t)}</td><td class="small muted">${esc(t.memo)}</td>
        <td class="num">${t.amount < 0 ? fmt(-t.amount, true, t) : ""}</td><td class="num">${t.amount > 0 ? fmt(t.amount, true, t) : ""}</td>
        <td class="num">${t.running_balance == null ? "" : fmt(t.running_balance, false, t)}</td></tr>`;
    }
    const g = r.group, top = g[0], sum = g.reduce((s, t) => s + t.amount, 0);
    const label = p => p.memo.split(" · ")[0] || p.category_label || "Part";
    // A paystub: gross pay and how many taxes and deductions came out of it.
    const stub = g.some(p => p.paystub);
    const summary = stub
      ? `<span class="pill green">Paystub</span> gross ${fmt(g.filter(p => p.amount > 0).reduce((s, p) => s + p.amount, 0), true, top)} · ${g.filter(p => p.amount < 0).length} taxes &amp; deductions${payPills(g.find(p => p.pay_flag) || {})}`
      : `<span class="pill">Split</span> ${g.slice().reverse().map(p => esc(label(p))).join(" · ")}`;
    // One line; its parts fold out with ▸ (and stay open while the register is used).
    const open = REG_OPEN.has(String(top.group_id));
    return `<tr class="click${top.date > today ? " future" : ""}"${top.date > today ? ' title="Dated after today"' : ""} data-group="${top.group_id}"${stub ? ' data-paystub="1"' : ""}><td class="status ${top.status}" data-gst="${top.group_id}" title="Click: blank → cleared → reconciled">${top.status || "·"}</td>
        <td class="small">${niceDate(top.date)}${moveBtns(top)}</td><td class="small">${esc(top.number)}</td><td>${esc(top.payee)}${top.auto ? ' <span class="pill auto" title="Recorded automatically from an automatic scheduled item">⟳ auto</span>' : ""}
          <button type="button" class="tiny grp-tog" data-tog="${top.group_id}" aria-expanded="${open}" title="Show or hide its parts">${open ? "▾" : "▸"} ${g.length} parts</button></td>
        <td class="small">${summary}</td><td class="small muted"></td>
        <td class="num">${sum < 0 ? fmt(-sum, true, top) : ""}</td><td class="num">${sum > 0 ? fmt(sum, true, top) : ""}</td>
        <td class="num">${top.running_balance == null ? "" : fmt(top.running_balance, false, top)}</td></tr>` +
      g.slice().reverse().map(p => `<tr class="small muted grp-part${top.date > today ? " future" : ""}" data-part="${top.group_id}"${open ? "" : " hidden"}><td></td><td></td><td></td><td style="padding-left:22px">↳ ${esc(label(p))}</td>
        <td class="small">${esc(p.category_label || "(lender holds it)")}</td><td></td>
        <td class="num">${p.amount < 0 ? fmt(-p.amount, true, p) : ""}</td><td class="num">${p.amount > 0 ? fmt(p.amount, true, p) : ""}</td><td></td></tr>`).join("");
  }).join("");
}

// A paycheck in the register: "take-home only" entries, and a flag when less is filled in
// than is usual for that employer (until it's filled in, or marked complete as is).
function payPills(t) {
  let h = "";
  if (t.paycheck != null && !t.paystub) h += ` <span class="pill" title="A paycheck recorded with its take-home pay${t.paycheck === 2 ? " (marked complete as is)" : ""}">Paycheck</span>`;
  if (t.pay_flag) h += ` <span class="pill amber" title="Less is filled in than usual for this employer">⚑ ${esc(t.pay_flag)}</span>`;
  return h;
}

async function groupDialog(rows, gid, done, acc) {
  const g = rows.filter(t => t.group_id == gid);
  const total = g.reduce((s, t) => s + t.amount, 0);
  await dialog("Split payment: " + (g[0].payee || ""), `<p class="small muted">${niceDate(g[0].date)} · one payment made of ${g.length} parts</p>
    <table>${g.slice().reverse().map(p => `<tr><td>${esc(p.memo.split(" · ")[0])}</td><td class="small">${esc(p.category_label || "(lender holds it)")}</td><td class="num">${fmt(p.amount, false, p)}</td></tr>`).join("")}
    <tr><td><b>Total</b></td><td></td><td class="num"><b>${fmt(total)}</b></td></tr></table>
    <div class="form" style="margin-top:10px"><div><label>Date paid</label><input type="date" name="date" value="${esc(g[0].date)}"></div></div>
    <p class="small muted">Changing the date moves every part of the payment. To change the amounts, delete this payment and record it again.</p>`,
    [{ label: "Delete payment", cls: "danger", action: async () => {
      if (!(await confirmBox("Delete this whole payment (all parts, including the loan side)?"))) return false;
      await api("DELETE", "/api/transactions/group/" + gid); toast("Payment deleted"); done(); } },
     ...(acc && canEdit() && !acc._shared && !S.shareCtx ? [{ label: "Schedule…", action: () => {
      // One scheduled item for the whole payment (the server counts its total).
      setTimeout(() => scheduleFromEntry(acc, g[0]), 0);
     } }] : []),
     { label: "Close" },
     { label: "Save date", cls: "primary", action: async root => {
      const d = q("[name=date]", root).value;
      if (d === g[0].date) return true;
      const r = await api("PUT", "/api/transactions/group/" + gid, { date: d });
      toast("Payment moved to " + niceDate(d) + (r.next_date ? `; next scheduled payment now ${niceDate(r.next_date)}` : ""));
      done(); } }]);
}

// ---------- PAYSTUBS ----------
// A paycheck in full: each earning, each tax and deduction (to a category, or to one of
// your accounts such as a 401(k) or HSA), and the take-home pay that reached this
// account. A new one starts from the latest paystub (same employer, else this account).
function paystubTargets(side, selected, payAcct) {
  const sel = v => v === selected ? "selected" : "";
  if (side === "earn" || side === "add") {
    return `<option value="">${side === "add" ? "(no category)" : "(choose)"}</option>` + S.cats.filter(c => c.kind === "income")
      .map(c => `<option value="c:${c.id}" ${sel("c:" + c.id)}>${esc(catFull(c))}</option>`).join("");
  }
  const accs = S.accounts.filter(a => a.id != payAcct && (!a.closed || "a:" + a.id === selected));
  // Part of the take-home pay deposited into another account: only my accounts.
  if (side === "split") return `<option value="">(choose the account)</option>` +
    accs.filter(a => !a.liability || "a:" + a.id === selected).map(a => `<option value="a:${a.id}" ${sel("a:" + a.id)}>${esc(a.name)}</option>`).join("");
  return `<option value="">(choose)</option><optgroup label="Taxes and other deductions">` +
    S.cats.filter(c => c.kind === "expense").map(c => `<option value="c:${c.id}" ${sel("c:" + c.id)}>${esc(catFull(c))}</option>`).join("") +
    `</optgroup><optgroup label="Sent to one of my accounts (401(k), HSA, savings...)">` +
    (accs.length ? accs.map(a => `<option value="a:${a.id}" ${sel("a:" + a.id)}>${esc(a.name)}</option>`).join("")
      // (without the account it goes to, a 401(k) or HSA deduction goes to Savings & Investments)
      : `<option value="" disabled>No other accounts: use Savings & Investments for a 401(k) or HSA</option>`) + `</optgroup>`;
}
function defaultPaystubLines() {
  const cid = full => { const c = S.cats.find(x => x.full_name === full); return c ? "c:" + c.id : ""; };
  return [
    { side: "earn", label: "Gross pay", to: cid("Wages & Salary : Gross Pay"), amount: "" },
    { side: "deduct", label: "Federal income tax", to: cid("Taxes : Federal Income Tax"), amount: "" },
    { side: "deduct", label: "Social Security", to: cid("Taxes : Social Security Tax"), amount: "" },
    { side: "deduct", label: "Medicare", to: cid("Taxes : Medicare Tax"), amount: "" },
    { side: "deduct", label: "State income tax", to: cid("Taxes : State Income Tax"), amount: "" },
  ];
}
// The remainder line ("Other deductions", or "Taxes and deductions" on older paystubs) isn't
// typed: it's worked out from the rest.
const isOtherLine = ln => !!ln.other || ["taxes and deductions", "other deductions"].includes(String(ln.label || "").trim().toLowerCase());
function stubLinesFrom(p) {
  return p.lines.filter(ln => !isOtherLine(ln)).map(ln => ({ side: ln.side, label: ln.label, amount: dollars(ln.amount),
    to: ln.account_id ? "a:" + ln.account_id : (ln.category_id ? "c:" + ln.category_id : "") }));
}
// A paycheck with as much as is known:
//   take-home pay (required): with nothing else it's recorded as take-home only;
//   earnings (gross pay...): then Other deductions = gross + additions - take-home -
//   the deductions itemized below it, worked out as they're typed (never below $0);
//   added after taxes (a reimbursement): folded away until needed.
async function paystubDialog(acc, gid, done, start) {
  start = start || {};
  const existing = gid ? await GET("/api/paystubs/" + gid) : null;
  let from = null;
  if (!existing) {
    const qs = new URLSearchParams({ account: acc.id });
    if (start.employer) qs.set("employer", start.employer);
    if (start.bill_id) qs.set("bill", start.bill_id);
    from = (await GET("/api/paystubs/template?" + qs).catch(() => ({}))).template || null;
  }
  const knownNet = Number.isFinite(start.net) && start.net > 0 ? Math.round(start.net) : null;   // in cents
  let lines = existing ? stubLinesFrom(existing) : (from ? stubLinesFrom(from) : defaultPaystubLines());
  if (!lines.some(l => l.side === "earn")) lines.unshift(defaultPaystubLines()[0]);
  // (from a scheduled paycheck into more than one account: what reached each one this time)
  if (start.splits) lines = lines.filter(l => l.side !== "split").concat(start.splits.map(x =>
    ({ side: "split", label: "", to: "a:" + x.account_id, amount: dollars(x.amount) })));
  // Deposited into: what reached the account the pay goes into (its first line), and any
  // other accounts (the paystub's split lines). Take-home pay is their total. (A scheduled
  // paycheck's amount may be that total, or only what reaches its own account.)
  const fromDeposit = from ? (from.deposit != null ? from.deposit : from.net) : null;
  let mainStart = existing ? (existing.deposit != null ? existing.deposit : existing.net) : null;
  if (!existing) {
    if (knownNet != null) mainStart = !start.splits && from && fromDeposit !== from.net && knownNet === from.net ? fromDeposit : knownNet;
    else if (from) mainStart = fromDeposit;
  }
  let touched = false;   // lines typed into: a later employer change doesn't replace them
  const p = existing || {};
  const hasAdds = lines.some(l => l.side === "add");
  const detailsOpen = !!existing || !!from || hasAdds || foldOpen("paystub");
  const body = `<div class="form">
      <div class="wide"><label class="req">Employer (who paid you)</label><input name="employer" list="payeeList" autocomplete="off" value="${esc(p.employer || start.employer || (from && from.employer) || "")}"></div>
      <div><label class="req">Pay date</label><input type="date" name="date" value="${esc(p.date || start.date || todayISO())}"></div>
      <div class="wide"><label>Memo</label><input name="memo" value="${esc(p.memo || "")}" placeholder="optional, e.g. pay period"></div>
    </div>
    <div class="destbox">
      <div class="destline desthead"><label class="req">Deposited into</label><label class="req num">Amount</label><span></span></div>
      <div class="destline"><select name="account_id" aria-label="Deposited into">${acctOptions(p.account_id || acc.id)}</select>
        <input id="sNet" name="net" class="num" inputmode="decimal" placeholder="0.00" aria-label="Amount" value="${mainStart ? dollars(mainStart) : ""}"><span></span></div>
      <div id="stubSplit"></div>
      <div class="destfoot"><button type="button" class="small" data-addline="split" title="Pay split between accounts by direct deposit: enter what reached each one">+ Add an account</button>
        <span id="stubNetTotal"></span></div>
    </div>
    <div class="small muted" style="margin-top:3px">Enter what reached each account: the take-home pay is their total. Only have that? It's enough: add the paystub later from the register.</div>
    ${existing && existing.flag ? `<div class="notice" style="margin:8px 0 0">⚑ This paycheck: ${esc(existing.flag)} (compared with what's usual for ${esc(existing.employer)}).</div>` : ""}
    ${existing && (existing.flag || existing.complete) ? `<label class="check" style="margin:6px 0 0"><input type="checkbox" id="stubComplete" ${existing.complete ? "checked" : ""}> Complete as is: don't flag it</label>` : ""}
    ${from && !existing ? `<p class="small" style="margin:6px 0 0;color:var(--teal)">Started from your ${esc(niceDate(from.date))} paystub from ${esc(from.employer)}
      (take-home ${fmt(from.net, true)}): change only what's different this time.</p>` : ""}
    <details class="more-fold" id="stubMore" ${detailsOpen ? "open" : ""}><summary>Paystub details: gross pay and deductions <span class="muted">(optional)</span></summary><div class="more-body">
      <h3 style="margin:4px 0 4px">Earnings</h3>
      <div id="stubEarn"></div><button type="button" class="small" data-addline="earn">+ Add an earning</button>
      <span class="small muted" style="margin-left:6px">overtime, bonus, commission...</span>
      <h3 style="margin:14px 0 4px">Taxes and deductions</h3>
      <div id="stubDeduct"></div><button type="button" class="small" data-addline="deduct">+ Add a deduction</button>
      <span class="small muted" style="margin-left:6px">health insurance, 401(k), HSA, union dues...</span>
      <div class="stubline other-line" id="stubOther"></div>
      <div id="stubAddBox" style="margin-top:12px;${hasAdds ? "" : "display:none"}"><h3 style="margin:0 0 4px">Added after taxes</h3><div id="stubAdd"></div></div>
      <button type="button" class="small linkbtn" data-addline="add" title="Money in the take-home pay that isn't pay: an expense reimbursement, a refund">+ Something added after taxes</button>
    </div></details>
    <div class="stubsum" id="stubSum"></div>
    ${existing ? "" : heldFilesHtml("ps")}
    <p class="small muted">Deductions sent to one of your accounts (a 401(k), an HSA) show up there as money in. Lines left at 0 are skipped.
      Whatever isn't itemized is recorded as <b>Other deductions</b>. In the budget a paycheck counts as its take-home pay.</p>`;
  const btns = [{ label: "Cancel" }];
  if (existing) btns.unshift({ label: "Delete paystub", cls: "danger", action: async () => {
    if (!(await confirmBox("Delete this paystub and every entry it made (including money sent to other accounts)?"))) return false;
    await api("DELETE", "/api/paystubs/" + gid); toast("Paystub deleted"); await loadBasics(); done && done(); } });
  btns.push({ label: existing ? "Save paystub" : "Save", cls: "primary", action: async root => {
    read();
    const t = sums();
    const base = { employer: q("[name=employer]", root).value, date: q("[name=date]", root).value,
      account_id: +q("[name=account_id]", root).value, memo: q("[name=memo]", root).value };
    const err = (m) => { const e = new Error(m); e.field = "net"; return e; };
    const noAcct = lines.findIndex(l => l.side === "split" && cents(l.amount) && !l.to);
    if (noAcct >= 0) { const e = new Error("Choose the account that amount went into"); e.field = `line_${noAcct}_to`; throw e; }
    if (!t.gross) {
      // Take-home only: a paycheck deposit; the paystub can follow.
      if (!t.main) throw err("Enter how much reached the account");
      if (existing) throw new Error("A paystub keeps its gross pay. To keep only the take-home pay, delete this paystub and enter the deposit.");
      if (start.replace_tx) {
        const n = await held.send(start.replace_tx);
        if (n) { toast(`${n} file${n === 1 ? "" : "s"} attached`); await loadBasics(); done && done(); }
        return true;
      }
      const splits = [];
      lines.forEach((l, i) => { if (l.side === "split" && cents(l.amount)) splits.push({ line: i, account_id: +l.to.slice(2), amount: l.amount }); });
      const r = await api("POST", "/api/paychecks/net", { ...base, net: (t.main / 100).toFixed(2), bill_id: start.bill_id || null, splits });
      const n = await held.send(r.id);
      toast(`Paycheck recorded${filesNote(n)}: ${fmt(r.net, true)} take-home. Add the paystub details any time from the register.`);
      await loadBasics(); done && done(); return;
    }
    if (t.main < 0) throw err(`The other accounts come to ${fmt(-t.main, true)} more than the take-home pay.`);
    if (t.other < 0) throw err(`The deductions come to ${fmt(-t.other, true)} more than gross pay minus take-home pay. Check the amounts, or add what was added after taxes (a reimbursement).`);
    const send = lines.filter(ln => num(ln.amount)).map(ln => ({ side: ln.side, label: ln.label, amount: ln.amount,
      category_id: ln.to.startsWith("c:") ? +ln.to.slice(2) : null, account_id: ln.to.startsWith("a:") ? +ln.to.slice(2) : null }));
    if (t.other > 0) send.push({ side: "deduct", label: "Other deductions", amount: (t.other / 100).toFixed(2), other: true });
    const f = { ...base, lines: send };
    if (start.bill_id && !existing) f.bill_id = start.bill_id;
    if (start.replace_tx && !existing) f.replace_tx = start.replace_tx;
    const r = existing ? await api("PUT", "/api/paystubs/" + gid, f) : await api("POST", "/api/paystubs", f);
    const done2 = q("#stubComplete", root);
    if (done2 && done2.checked !== !!existing.complete) await api("POST", "/api/paychecks/complete", { kind: "stub", id: r.group_id, complete: done2.checked });
    const n = existing ? 0 : await held.send(r.ids && r.ids[0]);
    toast(`Paystub saved${filesNote(n)}: ${fmt(r.net, true)} take-home of ${fmt(r.gross, true)}${t.other ? ` (${fmt(t.other, true)} in other deductions)` : ""}`);
    await loadBasics(); done && done();
  } });
  const pr = dialog(existing ? "Paystub: " + (p.employer || "") : (start.replace_tx ? "Paystub details" : "Paycheck"), body, btns);
  const root = q("#dlgBody");
  if (!q("#payeeList")) root.insertAdjacentHTML("beforeend", `<datalist id="payeeList">${S.payees.map(x => `<option value="${esc(x.name)}">`).join("")}</datalist>`);
  const held = holdFiles("ps", root, start.files);
  const num = v => parseAmount(v) || 0;
  const cents = v => Math.round(Math.abs(num(v)) * 100);
  // Lines are drawn in order (earnings, deductions, additions); field names match what is
  // sent, so a refused line is pointed at.
  function read() {
    qa("[data-line]", root).forEach(r => {
      const ln = lines[+r.dataset.line];
      const lab = q("input.ln-label", r);
      if (lab) ln.label = lab.value;
      ln.to = q("select.ln-to", r).value; ln.amount = q("input.ln-amt", r).value;
    });
  }
  // Gross pay, additions, itemized deductions and take-home: Other deductions is the rest.
  function sums() {
    const sum = side => lines.filter(l => l.side === side).reduce((s, l) => s + cents(l.amount), 0);
    const gross = sum("earn"), add = sum("add"), ded = sum("deduct"), split = sum("split");
    let main = cents(q("#sNet", root).value), net = main + split;
    // nothing typed for the first account: everything is itemized, and it got the rest
    if (!main && gross) { net = gross + add - ded; main = net - split; }
    return { gross, add, ded, net, split, main, other: gross ? gross + add - ded - net : 0 };
  }
  function draw() {
    const order = { earn: 0, deduct: 1, add: 2, split: 3 };
    lines.sort((a, b) => order[a.side] - order[b.side]);
    const firstOf = (ln, i) => !lines.slice(0, i).some(l => l.side === ln.side);
    const lastOf = (ln, i) => !lines.slice(i + 1).some(l => l.side === ln.side);
    const row = (ln, i) => ln.side === "split" ? `<div class="destline" data-line="${i}">
        <select class="ln-to" name="line_${i}_to" aria-label="Deposited into">${paystubTargets("split", ln.to, +q("[name=account_id]", root).value)}</select>
        <input class="ln-amt num" name="line_${i}_amount" inputmode="decimal" placeholder="0.00" value="${esc(ln.amount)}" aria-label="Amount">
        <span class="ln-btns"><button type="button" class="tiny" data-delline="${i}" title="Remove this account" aria-label="Remove this account">✕</button></span></div>`
      : `<div class="stubline" data-line="${i}">
        <input class="ln-label" value="${esc(ln.label)}" placeholder="${ln.side === "earn" ? "Gross pay" : (ln.side === "add" ? "Reimbursement" : (ln.side === "split" ? "Direct deposit" : "What it's for"))}" aria-label="Line name">
        <select class="ln-to" name="line_${i}_to" aria-label="${ln.side === "deduct" ? "Where it goes" : (ln.side === "split" ? "Account it went into" : "Income category")}">${paystubTargets(ln.side, ln.to, +q("[name=account_id]", root).value)}</select>
        <input class="ln-amt num" name="line_${i}_amount" inputmode="decimal" placeholder="0.00" value="${esc(ln.amount)}" aria-label="Amount">
        <span class="ln-btns"><button type="button" class="tiny" data-moveline="${i}" data-dir="-1" ${firstOf(ln, i) ? "disabled" : ""} title="Move up (Alt+↑)" aria-label="Move this line up">▲</button><button type="button" class="tiny" data-moveline="${i}" data-dir="1" ${lastOf(ln, i) ? "disabled" : ""} title="Move down (Alt+↓)" aria-label="Move this line down">▼</button><button type="button" class="tiny" data-delline="${i}" title="Remove this line" aria-label="Remove this line">✕</button></span></div>`;
    // (lines move within their own part: earnings among earnings, deductions among deductions)
    for (const [side, box] of [["earn", "#stubEarn"], ["deduct", "#stubDeduct"], ["add", "#stubAdd"], ["split", "#stubSplit"]]) {
      q(box, root).innerHTML = lines.map((ln, i) => ln.side === side ? row(ln, i) : "").join("");
    }
    q("#stubAddBox", root).style.display = lines.some(l => l.side === "add") ? "" : "none";
    qa("[data-delline]", root).forEach(b => b.onclick = () => { read(); lines.splice(+b.dataset.delline, 1); touched = true; draw(); });
    // Lines in the paystub's own order, so typing from it goes line by line.
    const move = (i, dir, ...focusSels) => {
      read();
      const side = lines[i].side;
      let j = i + dir;
      while (j >= 0 && j < lines.length && lines[j].side !== side) j += dir;
      if (j < 0 || j >= lines.length) return;
      [lines[i], lines[j]] = [lines[j], lines[i]];
      touched = true; draw();
      const el = focusSels.map(f => q(`[data-line="${j}"] ${f}`, root)).find(Boolean);
      if (el) el.focus();
    };
    qa("[data-moveline]", root).forEach(b => b.onclick = () =>
      move(+b.dataset.moveline, +b.dataset.dir, `[data-moveline][data-dir="${b.dataset.dir}"]:not([disabled])`, ".ln-label"));
    qa("[data-line]", root).forEach(r => r.addEventListener("keydown", e => {
      if (!e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
      e.preventDefault();
      const cls = e.target.classList.contains("ln-amt") ? ".ln-amt" : (e.target.closest(".pick") ? ".pick-input" : ".ln-label");
      move(+r.dataset.line, e.key === "ArrowUp" ? -1 : 1, cls, ".ln-label");
    }));
    qa("[data-line] input, [data-line] select", root).forEach(x => {
      x.addEventListener("input", () => { touched = true; total(); });
      x.addEventListener("change", () => { touched = true; total(); });
    });
    total();
  }
  function total() {
    read();
    const t = sums();
    const into = (S.accounts.find(a => a.id == q("[name=account_id]", root).value) || {}).name || "";
    const btn = q("#dlgFoot button.primary");
    const oth = q("#stubOther", root);
    // Split between accounts: what's left for the account the pay goes into.
    // Into more than one account: the take-home pay is their total.
    const acctName = to => (S.accounts.find(a => "a:" + a.id === to) || {}).name || "(choose the account)";
    q("#stubNetTotal", root).innerHTML = t.split ? `Take-home pay (total) <b class="${t.main < 0 ? "neg" : ""}">${fmt(t.net, true)}</b>` : "";
    const into2 = t.split ? `<div class="small">→ <b class="${t.main < 0 ? "neg" : ""}">${fmt(t.main, true)}</b> into ${esc(into)}</div>` +
      lines.filter(l => l.side === "split" && cents(l.amount)).map(l => `<div class="small">→ <b>${fmt(cents(l.amount), true)}</b> into ${esc(acctName(l.to))}</div>`).join("") : "";
    if (!t.gross) {
      oth.innerHTML = `<span class="small muted">Other deductions: worked out once there's gross pay.</span>`;
      q("#stubSum", root).innerHTML = `<div class="stubnet">Take-home pay <b>${fmt(t.net, true)}</b>${t.split ? "" : ` <span class="small muted">into ${esc(into)}</span>`}</div>${into2}
        <div class="small muted">No gross pay: it's recorded as take-home pay only, marked as a paycheck so the details can be added later.</div>`;
      if (btn && !existing) btn.textContent = start.replace_tx ? "Close" : "Record take-home pay";
      return;
    }
    if (btn && !existing) btn.textContent = start.replace_tx ? "Save paystub details" : "Save paycheck";
    oth.innerHTML = t.other < 0
      ? `<span class="ln-label"><b>Other deductions</b></span><span class="neg"><b>${fmt(t.other, true)}</b></span>
         <div class="small" style="color:var(--red);flex-basis:100%">The deductions are ${fmt(-t.other, true)} more than gross pay minus take-home pay. Check the amounts, or add what was added after taxes.</div>`
      : `<span class="ln-label"><b>Other deductions</b> <span class="small muted">${t.other === 0 ? "(everything itemized)" : (t.ded ? "(what isn't itemized above)" : "(nothing itemized yet: that's fine)")}</span></span>
         <span class="num"><b>${fmt(t.other, true)}</b></span>`;
    q("#stubSum", root).innerHTML = `<div>Gross pay <b>${fmt(t.gross, true)}</b></div>
      ${t.add ? `<div>+ added after taxes <b>${fmt(t.add, true)}</b></div>` : ""}
      <div>− taxes and deductions <b>${fmt(t.ded + Math.max(0, t.other), true)}</b>${t.other > 0 && t.ded ? ` <span class="small muted">(${fmt(t.ded, true)} itemized)</span>` : ""}</div>
      <div class="stubnet ${t.other < 0 ? "neg" : ""}">= take-home pay <b>${fmt(t.net, true)}</b>${t.split ? "" : ` <span class="small muted">into ${esc(into)}</span>`}</div>${into2}`;
  }
  qa("[data-addline]", root).forEach(b => b.onclick = () => {
    read(); lines.push({ side: b.dataset.addline, label: "", to: "", amount: "" }); touched = true; draw();
    const box = { earn: "#stubEarn", deduct: "#stubDeduct", add: "#stubAdd", split: "#stubSplit" }[b.dataset.addline];
    const rows = qa(`${box} .ln-label`, root);
    if (rows.length) rows[rows.length - 1].focus();
  });
  q("#sNet", root).addEventListener("input", () => total());
  q("[name=account_id]", root).onchange = () => { read(); draw(); };
  // Opening or closing the details is remembered for this person.
  q("#stubMore", root).addEventListener("toggle", e => rememberFold("paystub", e.target.open));
  // A different employer: start from that employer's latest paystub, if any (only while
  // nothing has been typed into the lines yet).
  if (!existing) q("[name=employer]", root).addEventListener("change", async e => {
    if (touched) return;
    const t = (await GET("/api/paystubs/template?" + new URLSearchParams({ employer: e.target.value.trim() })).catch(() => ({}))).template;
    if (t && t.employer.toLowerCase() === e.target.value.trim().toLowerCase()) {
      lines = stubLinesFrom(t);
      if (!q("#sNet", root).value) q("#sNet", root).value = dollars(t.deposit != null ? t.deposit : t.net);
      q("#stubMore", root).open = true;
      draw();
    }
  });
  draw();
  return pr;
}

// A date after today counts in its own month: say so, so a payment already made
// isn't recorded for a later date (and a later month's budget) by mistake.
function dateHint(input) {
  if (!input) return;
  const h = document.createElement("div");
  h.className = "small muted"; h.style.marginTop = "3px";
  input.after(h);
  const upd = () => {
    const v = input.value, t = todayISO();
    if (!v || v <= t) { h.textContent = ""; return; }
    const later = v.slice(0, 7) !== t.slice(0, 7);
    h.textContent = `After today${later ? `, so it counts in ${monthName(v.slice(0, 7))}` : ""}. Already paid? Use the day it was paid.`;
    h.style.color = later ? "var(--out-text)" : "";
  };
  input.addEventListener("input", upd); input.addEventListener("change", upd); upd();
}

// Accounts shared into this environment from another one (they live there).
function sharedGroup(shared, activeSid) {
  if (!shared.length) return "";
  return `<div class="acctgroup"><div class="gname">Shared with this environment</div>
    ${shared.map(a => `<a class="acctrow ${a.share_id == activeSid ? "on" : ""}" href="#/accounts/s${a.share_id}" title="Shared by ${esc(a.shared_by)} from their ${esc(a.env_name)}${a.can_edit ? "" : " (view only)"}">
      <span>${esc(a.name)} <span class="small muted">· ${esc(a.shared_by || a.env_name)}</span></span><span class="num">${fmt(a.balance, false, a)}</span></a>`).join("")}</div>`;
}

// All my environments: the other environments' accounts, to open (which switches there).
async function otherEnvAccounts() {
  if (!reportScopeAll()) return [];
  return Promise.all(S.me.envs.filter(e => e.id !== S.env && scopeEnvs().includes(e.id)).map(e =>
    api("GET", "/api/accounts", undefined, { env_id: e.id }).then(list => ({ e, list: list.filter(a => !a.closed) })).catch(() => ({ e, list: [] }))));
}
function accountsList(id, shared, activeSid, others) {
  const all = reportScopeAll(), mine = new Set(scopeEnvs());
  if (all) shared = shared.filter(a => !mine.has(a.env_id));   // shown where they live instead
  const here = all ? (S.me.envs.find(e => e.id === S.env) || {}).name : "";
  return `<div class="card"><div class="head"><h2>Accounts${here ? ` <span class="small muted">· ${esc(here)}</span>` : ""}</h2><span><button class="small" id="newLoan">New loan</button> <button class="small primary" id="newAcct">New</button></span></div>
    ${groupAccounts(S.accounts).map(([name, l]) => `<div class="acctgroup"><div class="gname">${esc(name)}</div>
    ${l.map(a => `<a class="acctrow ${a.id == id ? "on" : ""} ${a.closed ? "closed" : ""}" href="#/accounts/${a.id}"><span>${esc(a.name)}</span><span class="num">${fmt(a.balance, false, a)}</span></a>`).join("")}</div>`).join("")
    || (shared.length ? "" : `<div class="empty">No accounts yet</div>`)}
    ${sharedGroup(shared, activeSid)}
    ${(others || []).filter(o => o.list.length).map(({ e, list }) => `<div class="acctgroup"><div class="gname">In ${esc(e.name)}</div>
      ${list.map(a => `<a class="acctrow" href="#/accounts/${a.id}" data-goenv="${e.id}" data-goacct="${a.id}" title="Opens it in ${esc(e.name)}"><span>${esc(a.name)}</span><span class="num">${fmt(a.balance, false, a)}</span></a>`).join("")}</div>`).join("")}
    <div class="small" style="margin-top:12px"><a href="#" id="loanCalc" title="Work out a payment, or what a payment can buy, before taking a loan">Loan calculator</a></div></div>`;
}

// An account shared into this environment: its register, read-only or with entering
// allowed, using the categories of the environment it lives in.
async function renderShared(sid) {
  if (S.shareCtx) { S.shareCtx = null; await loadBasics(); }
  const shared = await GET("/api/shares/incoming");
  const sh = shared.find(a => a.share_id === sid);
  if (!sh) { view().innerHTML = `<div class="notice err">That account isn't shared with this environment any more.</div>`; return; }
  const list = accountsList(null, shared, sid);
  S.shareCtx = { share_id: sid, env_id: sh.env_id };
  [S.accounts, S.cats, S.payees] = await Promise.all([GET("/api/accounts"), GET("/api/categories"), GET("/api/payees")]);
  S.xlinks = [];
  const acc = S.accounts.find(a => a.id === sh.id) || S.accounts[0];
  const rows = registerOrder(await GET("/api/transactions?account=" + acc.id));
  regPlace("sh" + sid);
  view().innerHTML = `<div class="grid side">${list}<div>
    <div class="toolbar"><h1 style="margin:0">${esc(acc.name)}</h1><span class="pill">${esc(acc.type)}</span>
      <span class="pill green">shared by ${esc(sh.shared_by)}</span>${sh.can_edit ? "" : '<span class="pill">view only</span>'}<span class="grow"></span>
      ${sh.can_edit ? '<button id="recon">Balance account</button>' : ""}</div>
    <div class="toolbar small"><span>Balance <b>${fmt(acc.balance, false, acc)}</b></span><span class="muted">Cleared ${fmt(acc.cleared_balance, true, acc)}</span>
      <span class="muted">This account lives in ${esc(sh.shared_by)}'s ${esc(sh.env_name)}; you see the same register and its categories.</span></div>
    <div class="card flush"><div class="register"><table id="reg">
      <tr><th class="status" title="Cleared / Reconciled">C</th><th>Date</th><th>Num</th><th>Payee</th><th>Category</th><th>Memo</th><th class="num">Payment</th><th class="num">Deposit</th><th class="num">Balance</th></tr>
      ${registerRows(rows)}
    </table>${rows.length ? "" : `<div class="empty">No transactions yet.</div>`}</div>
    <div class="entry" id="entry"></div></div></div></div>`;
  q("#newAcct").onclick = async () => { S.shareCtx = null; await loadBasics(); editAccount(null); };
  q("#newLoan").onclick = async () => { S.shareCtx = null; await loadBasics(); editLoan(null); };
  q("#loanCalc").onclick = e => { e.preventDefault(); loanCalculator(); };
  const again = () => renderSharedKeep(sid);
  if (q("#recon")) q("#recon").onclick = () => reconcile(acc);
  if (sh.can_edit) {
    qa("tr[data-id]").forEach(r => r.onclick = e => {
      if (e.target.dataset.st) return;
      const t = rows.find(x => x.id == r.dataset.id);
      if (t.transfer_id || t.xlink_id) { toast(`Transfers are changed in ${sh.env_name}`, true); return; }
      qa("tr.sel").forEach(x => x.classList.remove("sel")); r.classList.add("sel");
      entryForm(acc, t, again);
    });
    qa("[data-st]").forEach(c => c.onclick = async () => {
      const t = rows.find(x => x.id == c.dataset.st);
      await api("POST", `/api/transactions/${t.id}/status`, { status: { "": "C", "C": "R", "R": "" }[t.status || ""] });
      again();
    });
    entryForm(acc, null, again);
  } else {
    q("#entry").innerHTML = `<div class="small muted">Shared with this environment to view. Changes are made in ${esc(sh.env_name)}.</div>`;
  }
}
// Run a dialog (edit or record a bill) as the shared account's environment: its
// categories and the shared account; back to this environment afterwards.
async function withShare(sh, fn) {
  S.shareCtx = { share_id: sh.share_id, env_id: sh.env_id, forBills: true };
  try { await loadBasics(); return await fn(); }
  finally { S.shareCtx = null; await loadBasics().catch(() => { }); }
}

async function sharedBillsSection(days) {
  const shared = (await GET("/api/shares/incoming").catch(() => [])).filter(a => a.include_bills);
  if (!shared.length) return { html: "", wire: () => { } };
  const parts = await Promise.all(shared.map(sh => api("GET", "/api/bills?days=" + days, undefined, sh).then(d => ({ sh, d }))));
  const html = parts.map(({ sh, d }) => `<div class="card flush" style="margin-top:16px"><div style="padding:12px 14px 4px;display:flex;align-items:center;gap:10px">
      <h2 style="margin:0">${esc(sh.name)} <span class="small muted">· shared by ${esc(sh.shared_by)}</span></h2><span class="grow" style="flex:1"></span>
      ${sh.can_edit ? `<button class="small" data-snew="${sh.share_id}:bill">New bill</button> <button class="small" data-snew="${sh.share_id}:deposit">New deposit</button>` : '<span class="pill">view only</span>'}</div>
    <table><tr><th>Due</th><th>Payee</th><th>How often</th><th class="num">Amount</th><th></th></tr>
    ${d.upcoming.map(u => `<tr class="${u.overdue ? "overdue " : ""}k-${kindOf(u)}"><td class="small">${niceDate(u.date)} ${u.overdue ? '<span class="pill red">Overdue</span>' : ""}</td>
      <td>${esc(u.payee)} ${kindPill(u)}${autoPill(u)}<div class="small muted">${esc(u.category_label)}</div></td><td class="small">${esc(freqLabel(u))}</td><td class="num">${billAmount(u)}</td>
      <td class="num">${u.first && sh.can_edit ? `<button class="small primary" data-senter="${sh.share_id}:${u.id}">Enter</button> <button class="small" data-sskip="${sh.share_id}:${u.id}">Skip</button> <button class="small" data-sedit="${sh.share_id}:${u.id}">Change</button>` : (u.first ? "" : '<span class="small muted">later</span>')}</td></tr>`).join("")}
    </table>${d.upcoming.length ? "" : `<div class="empty">Nothing due in the next ${days} days${d.bills.length ? "" : " (no bills or deposits scheduled for this account)"}</div>`}</div>`).join("");
  const find = v => { const [sid, id] = v.split(":"); const p = parts.find(x => x.sh.share_id == sid); return { sh: p.sh, b: p.d.bills.find(b => b.id == id), occ: p.d.upcoming.find(u => u.id == id && u.first) }; };
  const wire = () => {
    qa("[data-snew]").forEach(b => b.onclick = () => { const [sid, kind] = b.dataset.snew.split(":"); const sh = shared.find(s => s.share_id == sid);
      withShare(sh, () => editBill(null, kind)); });
    qa("[data-sedit]").forEach(b => b.onclick = () => { const f = find(b.dataset.sedit); withShare(f.sh, () => editBill(f.b)); });
    qa("[data-senter]").forEach(b => b.onclick = () => { const f = find(b.dataset.senter); withShare(f.sh, () => enterBill(f.occ.id, f.occ)); });
    qa("[data-sskip]").forEach(b => b.onclick = async () => { const f = find(b.dataset.sskip);
      try { await api("POST", `/api/bills/${f.occ.id}/skip`, {}, f.sh); toast("Skipped to the next date"); render(); } catch (e) { toast(e.message, true); } });
  };
  return { html, wire };
}

async function renderSharedKeep(sid) { S.shareCtx = null; await loadBasics(); await renderShared(sid); }

async function renderAccounts(id, sub) {
  await loadBasics();
  const accs = S.accounts;
  const shared = await GET("/api/shares/incoming").catch(() => []);
  const list = accountsList(id, shared, null, await otherEnvAccounts());
  if (!id) {
    view().innerHTML = `<div class="pagehead"><h1>Accounts</h1>${scopeSwitch()}</div><div class="grid side">${list}<div class="card flush">
      <table><tr><th>Account</th><th>Type</th><th class="num">Transactions</th><th class="num">Cleared</th><th class="num">Balance</th></tr>
      ${accs.map(a => `<tr class="click" data-id="${a.id}"><td>${esc(a.name)} ${a.closed ? '<span class="pill">closed</span>' : ""}</td><td>${esc(a.type)}</td>
      <td class="num">${a.tx_count}</td><td class="num">${fmt(a.cleared_balance, false, a)}</td><td class="num">${fmt(a.balance, false, a)}</td></tr>`).join("")}</table>
      ${accs.length ? "" : `<div class="empty">Add your first account with <b>New</b>.</div>`}</div></div>`;
    q("#newAcct").onclick = () => editAccount(null);
  q("#newLoan").onclick = () => editLoan(null);
  q("#loanCalc").onclick = e => { e.preventDefault(); loanCalculator(); };
    qa("tr[data-id]").forEach(r => r.onclick = () => location.hash = "#/accounts/" + r.dataset.id);
    return;
  }
  const acc = accs.find(a => a.id == id);
  if (!acc) { location.hash = "#/accounts"; return; }
  const search = sub && sub.q || "";
  const rows = registerOrder(await GET(`/api/transactions?account=${id}${search ? "&q=" + encodeURIComponent(search) : ""}`));
  const loan = acc.has_loan ? await GET("/api/loans/" + id) : null;
  // Where money can go besides this environment's own accounts: approved connections,
  // and accounts shared into this environment with entering allowed.
  S.xlinks = await GET("/api/links/usable?account=" + id).catch(() => []);
  S.sharedXfer = shared.filter(a => a.can_edit && !a.closed);
  regPlace("acc" + id + "|" + search);
  view().innerHTML = `<div class="grid side">${list}<div>
    <div class="toolbar"><h1 style="margin:0">${esc(acc.name)}</h1><span class="pill">${esc(acc.type)}</span><span class="grow"></span>
      <input id="search" placeholder="Search payee, memo…" value="${esc(search)}" style="width:200px">
      <button id="editAcct">Account details</button>${CARD_TYPES.includes(acc.type) && cardMode(acc.details) === "statement" && !acc._shared ? '<button id="stmtBtn" title="Enter the balance from this card\'s statement">Enter statement</button>' : ""}${VALUE_TYPES.includes(acc.type) && !acc._shared ? '<button id="valBtn" title="Type in what it\'s worth now, from its statement or website">Update value</button>' : ""}<button id="recon">Balance account</button>
      <button id="import">Import file</button><a class="btn" href="/api/export.csv?account=${id}&env=${S.env}">Export CSV</a>${regOrderButton()}
      <button id="acctFiles" title="Receipts and papers kept with this account (not one entry): a purchase on a card, a warranty, a contract">${CLIP_ICON} Papers<span id="acctFilesN"></span></button></div>
    <div class="toolbar small"><span>Balance <b>${fmt(acc.balance, false, acc)}</b></span><span class="muted">Cleared ${fmt(acc.cleared_balance, true, acc)}</span>
      ${acc.reconciled_date ? `<span class="muted">Last balanced ${niceDate(acc.reconciled_date)} at ${fmt(acc.reconciled_balance, true)}</span>` : ""}</div>
    ${accountDetailsLine(acc)}
    ${loan ? loanCard(loan) : (acc.type === "Loan" && canEdit() && !acc._shared ? `<div class="notice" style="margin-bottom:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <span style="flex:1;min-width:240px">This loan has no payment details yet (an account brought in from another program starts this way).
      Add its rate and payment to see its payment schedule, payoff date and what-if payments. Its register and balance stay as they are.</span>
      <button class="small primary" id="loanSetup">Set up loan details…</button></div>` : "")}
    <div class="card flush"><div class="register"><table id="reg">
      <tr><th class="status" title="Cleared / Reconciled">C</th><th>Date</th><th>Num</th><th>Payee</th><th>Category</th><th>Memo</th><th class="num">Payment</th><th class="num">Deposit</th><th class="num">Balance</th></tr>
      ${registerRows(rows)}
    </table>${rows.length ? "" : `<div class="empty">No transactions${search ? " match" : " yet. Type one in below"}.</div>`}</div>
    <div class="entry" id="entry"></div></div></div></div>`;
  q("#newAcct").onclick = () => editAccount(null);
  q("#newLoan").onclick = () => editLoan(null);
  q("#loanCalc").onclick = e => { e.preventDefault(); loanCalculator(); };
  q("#editAcct").onclick = () => editAccount(acc);
  if (q("#stmtBtn")) q("#stmtBtn").onclick = () => statementDialog(acc);
  if (q("#valBtn")) q("#valBtn").onclick = () => valueDialog(acc);
  q("#recon").onclick = () => reconcile(acc);
  q("#import").onclick = () => importFile(acc);
  const filesCount = () => GET(`/api/accounts/${acc.id}/attachments`).then(l => {
    const n = q("#acctFilesN"); if (n) n.textContent = l.length ? ` (${l.length})` : "";
  }).catch(() => {});
  filesCount();
  q("#acctFiles").onclick = () => attachDialog({ acc }, filesCount);
  q("#search").onkeydown = e => { if (e.key === "Enter") renderAccounts(id, { q: e.target.value }); };
  qa("tr[data-id]").forEach(r => r.onclick = (e) => {
    if (e.target.dataset.st) return;
    qa("tr.sel").forEach(x => x.classList.remove("sel")); r.classList.add("sel");
    entryForm(acc, rows.find(t => t.id == r.dataset.id), () => renderAccounts(id, { q: search }));
  });
  qa("[data-st]").forEach(c => c.onclick = async () => {
    const t = rows.find(x => x.id == c.dataset.st);
    const next = { "": "C", "C": "R", "R": "" }[t.status || ""];
    await api("POST", `/api/transactions/${t.id}/status`, { status: next });
    renderAccounts(id, { q: search });
  });
  // A split payment: status applies to all its parts; clicking it shows the parts.
  qa("[data-gst]").forEach(c => c.onclick = async (e) => {
    e.stopPropagation();
    const g = rows.filter(x => x.group_id == c.dataset.gst);
    const next = { "": "C", "C": "R", "R": "" }[g[0].status || ""];
    for (const t of g) await api("POST", `/api/transactions/${t.id}/status`, { status: next });
    renderAccounts(id, { q: search });
  });
  qa("tr[data-group]").forEach(r => r.onclick = () => r.dataset.paystub
    ? paystubDialog(acc, +r.dataset.group, () => renderAccounts(id, { q: search }))
    : groupDialog(rows, r.dataset.group, () => renderAccounts(id, { q: search }), acc));
  if (q("#loanSetup")) q("#loanSetup").onclick = async () => editLoan(acc, null, await GET(`/api/loans/${acc.id}/suggest`));
  if (loan) {
    q("#loanPay").onclick = () => payLoan(acc.id, loan.bill ? { ...loan.bill, date: loan.bill.next_date } : null);
    q("#loanSched").onclick = () => { const w = q("#schedWrap"); w.style.display = w.style.display === "none" ? "" : "none"; };
    q("#loanWhatIf").onclick = () => loanWhatIf(loan);
  }
  if (canEdit()) entryForm(acc, null, () => renderAccounts(id, { q: search }));
}

// Category list for the register: transfers between your own accounts come first
// ("Transfer to Savings" / "Transfer from Savings"), then the normal categories.
function registerCatOptions(acc, kind, selected) {
  const others = S.accounts.filter(a => a.id !== acc.id && (!a.closed || ("x:" + a.id) === selected));
  let h = `<option value="">(no category)</option>`;
  if (others.length) {
    h += `<optgroup label="Transfer between my accounts">` + others.map(a =>
      `<option value="x:${a.id}" ${("x:" + a.id) === selected ? "selected" : ""}>${kind === "deposit" ? "Transfer from " : "Transfer to "}${esc(a.name)}</option>`).join("") + `</optgroup>`;
  }
  // Approved connections to accounts in other environments.
  const xl = S.xlinks || [];
  if (xl.length) {
    h += `<optgroup label="Transfer to another environment">` + xl.map(l =>
      `<option value="l:${l.link_id}" ${("l:" + l.link_id) === selected ? "selected" : ""}>${kind === "deposit" ? "Transfer from " : "Transfer to "}${esc(l.account_name)} (${esc(l.env_name)})</option>`).join("") + `</optgroup>`;
  }
  // Accounts shared into this environment with entering allowed (not yet connected).
  const sx = (S.sharedXfer || []).filter(a => !xl.some(l => l.env_id === a.env_id && l.account_id === a.id));
  if (sx.length) {
    h += `<optgroup label="Transfer with a shared account">` + sx.map(a =>
      `<option value="sh:${a.share_id}">${kind === "deposit" ? "Transfer from " : "Transfer to "}${esc(a.name)} (shared by ${esc(a.shared_by)})</option>`).join("") + `</optgroup>`;
  }
  return h + catOptions(selected, { full: true }).replace(/^<option value="">[^<]*<\/option>/, "");
}

// Paying a card: one tap fills in what's left on its last entered statement (the
// statement balance less payments made since it closed).
async function statementButton(cardId, box, onPick) {
  if (!box) return;
  box.innerHTML = "";
  const a = S.accounts.find(x => x.id == cardId);
  if (!a || !CARD_TYPES.includes(a.type)) return;
  const r = await GET(`/api/accounts/${cardId}/statement`).catch(() => null);
  const d = r && r.due;
  if (!d) return;
  if (d.left <= 0) { box.innerHTML = `<span class="small muted">The ${esc(niceDate(d.date))} statement is paid.</span>`; return; }
  box.innerHTML = `<button type="button" class="small stmtpick" title="Fill in the amount from the last statement">Pay the ${esc(niceDate(d.date))} statement: ${fmt(d.left, true)}${d.paid_since ? " (what's left)" : ""}</button>`;
  q("button", box).onclick = () => onPick(d.left);
}

// A trash can (delete), so it isn't mistaken for an ✕ that closes without saving.
const TRASH_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true" style="vertical-align:-2px" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>`;

const CLIP_ICON = `<svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" style="vertical-align:-2px" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.4 11.1l-8.5 8.5a6 6 0 0 1-8.5-8.5l8.5-8.5a4 4 0 0 1 5.7 5.7l-8.5 8.5a2 2 0 0 1-2.8-2.8l7.8-7.8"/></svg>`;

// ---------- receipts and other attached files ----------
// A phone offers its camera for "Take a photo"; any device can pick a photo or PDF.
const PHONE = window.matchMedia && matchMedia("(pointer: coarse)").matches;
function attachUrl(id, download) {
  const sc = S.shareCtx;
  return `/api/attachments/${id}?env=${sc ? sc.env_id : S.env}${sc && sc.share_id ? "&share=" + sc.share_id : ""}${download ? "&download=1" : ""}`;
}
function attachPickers(prefix) {
  return `${PHONE ? `<label class="btn small filepick" title="Use the camera">📷 Take a photo<input type="file" id="${prefix}_cam" accept="image/*" capture="environment" hidden></label>` : ""}
    <label class="btn small filepick" title="A photo or a PDF (up to 20 MB)">${CLIP_ICON} ${PHONE ? "Choose a photo or file" : "Add a receipt or file"}<input type="file" id="${prefix}_file" accept="image/*,application/pdf" multiple hidden></label>`;
}
function wirePickers(prefix, root, onFiles) {
  [prefix + "_cam", prefix + "_file"].forEach(i => {
    const inp = q("#" + i, root);
    if (inp) inp.onchange = () => { const fs = [...inp.files]; inp.value = ""; if (fs.length) onFiles(fs); };
  });
}
// Receipts, statements or a paystub picked in a dialog that makes an entry (recording a
// bill or deposit, a paycheck): held until the entry exists, then attached to it.
function heldFilesHtml(prefix) {
  return `<div class="entry-attach small" style="margin-top:10px">${attachPickers(prefix)}<span id="${prefix}_held" class="muted"></span></div>`;
}
function holdFiles(prefix, root, start) {
  let files = (start || []).slice();
  const show = () => {
    const el = q(`#${prefix}_held`, root);
    if (!el) return;
    el.innerHTML = files.length ? `${files.length} file${files.length === 1 ? "" : "s"} to attach when recorded (${files.map(f => esc(f.name || "photo")).join(", ")}) · <a href="#" data-unhold>clear</a>` : "";
    const u = q("[data-unhold]", el);
    if (u) u.onclick = e => { e.preventDefault(); files = []; show(); };
  };
  wirePickers(prefix, root, fs => { files = files.concat(fs); show(); });
  show();
  return {
    get count() { return files.length; },
    take() { const l = files; files = []; return l; },   // handed on to the next dialog
    // Attach the held files to the new entry; says how many went. A file that fails doesn't
    // undo the entry: the message says to add it from the register.
    async send(tid) {
      const list = files; files = [];
      if (!tid || !list.length) return 0;
      let sent = 0;
      for (const f of list) {
        try { await uploadAttachment(tid, f); sent++; }
        catch (e) { toast(`Recorded, but ${f.name || "a file"} wasn't attached (${e.message}). Add it from the register.`, true); }
      }
      return sent;
    },
  };
}
const filesNote = n => n ? ` with ${n} file${n === 1 ? "" : "s"}` : "";
// Photos are made smaller before sending (long side 2000 px, like a good scan): a
// phone's 4 MB picture becomes about 400 KB, which keeps backups small.
async function shrinkPhoto(file) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size < 500 * 1024 || !window.createImageBitmap) return file;
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height);
    g.drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise(r => c.toBlob(r, "image/jpeg", 0.85));
    return blob && blob.size < file.size ? blob : file;
  } catch (e) { return file; }   // a format this browser can't draw (HEIC...): sent as it is
}
// tid: an entry's id, or { account: id } for papers kept with an account. extra: note, doc_date.
async function uploadAttachment(tid, file, extra) {
  if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} is larger than 20 MB`);
  const blob = await shrinkPhoto(file);
  const data = await new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(",")[1] || "");
    fr.onerror = () => rej(new Error("Couldn't read " + file.name));
    fr.readAsDataURL(blob);
  });
  const name = file.name && file.name !== "image.jpg" ? file.name : `receipt-${todayISO()}.jpg`;
  const where = tid && tid.account ? `/api/accounts/${tid.account}` : `/api/transactions/${tid}`;
  return api("POST", `${where}/attachments`, { name, data, ...(extra || {}) });
}
function sizeText(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }
function attThumb(a) {
  return `<a href="${attachUrl(a.id)}" target="_blank" rel="noopener" class="att-thumb" title="Open ${esc(a.name)}">
    ${a.mime.startsWith("image/") && a.mime !== "image/heic" ? `<img src="${attachUrl(a.id)}" alt="${esc(a.name)}" loading="lazy">` : `<span class="att-doc">${a.mime === "application/pdf" ? "PDF" : "Photo"}</span>`}</a>`;
}
// Saving a file's note (or date) as it's typed: when the field is left.
function wireAttEdits(root, list) {
  qa("[data-attnote],[data-attdate]", root).forEach(inp => inp.onchange = async () => {
    const id = inp.dataset.attnote || inp.dataset.attdate;
    const body = inp.dataset.attnote ? { note: inp.value } : { doc_date: inp.value };
    try {
      const r = await api("PUT", `/api/attachments/${id}`, body);
      const a = list.find(x => x.id == id); if (a) Object.assign(a, r);
      inp.classList.add("saved"); setTimeout(() => inp.classList.remove("saved"), 900);
    } catch (e) { toast(e.message, true); }
  });
}
// The files of one entry ({ tx }) or the papers kept with an account ({ acc }).
async function attachDialog(target, done) {
  const { tx, acc } = target;
  const mayChange = canEdit() || !!(S.shareCtx && S.shareCtx.share_id);
  const base = tx ? `/api/transactions/${tx.id}` : `/api/accounts/${acc.id}`;
  let list = await GET(`${base}/attachments`);
  let note = "", when = todayISO();
  const draw = () => {
    const root = q("#dlgBody");
    root.innerHTML = (tx ? `<p class="small muted">${esc(niceDate(tx.date))} · ${esc(tx.payee || "")} · ${fmt(tx.amount, true)}</p>`
      : `<p class="small muted">Receipts and papers for <b>${esc(acc.name)}</b> that don't belong to one entry: an important purchase on the card, a warranty, a contract, a year-end statement.</p>`)
      + (mayChange ? `<div class="att-add">
          <div><label>Note or keywords <span class="muted">(optional, to find it later)</span></label><input id="ad_note" value="${esc(note)}" maxlength="500" placeholder="${tx ? "e.g. warranty 2 years, tax" : "e.g. Costco TV, warranty, serial 12345"}"></div>
          ${acc ? `<div><label>Date</label><input type="date" id="ad_date" value="${esc(when)}"></div>` : ""}
          <div class="att-pick">${attachPickers("ad")}<span class="small muted" id="ad_busy"></span></div></div>` : "")
      + (list.length ? `<div class="att-grid">${list.map(a => `<div class="att">${attThumb(a)}
          <div class="small att-name" title="${esc(a.name)}">${esc(a.name)}</div>
          ${mayChange ? `<input class="att-note" data-attnote="${a.id}" value="${esc(a.note || "")}" maxlength="500" placeholder="Add a note or keywords" aria-label="Note for ${esc(a.name)}">`
            : (a.note ? `<div class="small">${esc(a.note)}</div>` : "")}
          ${acc ? (mayChange ? `<input type="date" class="att-note" data-attdate="${a.id}" value="${esc(a.doc_date || "")}" aria-label="Date of ${esc(a.name)}">`
            : `<div class="small muted">${esc(niceDate(a.doc_date || a.added.slice(0, 10)))}</div>`) : ""}
          <div class="small muted">${sizeText(a.size)} · <a href="${attachUrl(a.id, true)}">Download</a>${mayChange ? ` · <a href="#" data-attdel="${a.id}" class="danger-link" title="Remove it">Remove</a>` : ""}</div>
        </div>`).join("")}</div>` : `<div class="empty">Nothing attached yet.${mayChange ? (tx ? " Add a photo of the receipt, or a PDF (an invoice, a statement)." : " Add a photo or a PDF.") : ""}</div>`);
    if (q("#ad_note", root)) q("#ad_note", root).oninput = e => { note = e.target.value; };
    if (q("#ad_date", root)) q("#ad_date", root).onchange = e => { when = e.target.value; };
    wirePickers("ad", root, async files => {
      const busy = q("#ad_busy", root);
      try {
        for (const [i, f] of files.entries()) {
          busy.textContent = `Sending ${files.length > 1 ? `${i + 1} of ${files.length}` : f.name}…`;
          list = (await uploadAttachment(tx ? tx.id : { account: acc.id }, f, { note, ...(acc ? { doc_date: when } : {}) })).attachments;
        }
        note = ""; if (tx) tx.attachments = list.length; draw();
      } catch (e) { busy.textContent = ""; dialogError(e); }
    });
    wireAttEdits(root, list);
    qa("[data-attdel]", root).forEach(b => b.onclick = async e => {
      e.preventDefault();
      const a = list.find(x => x.id == b.dataset.attdel);
      if (!confirm(`Remove ${a.name}?`)) return;
      try { list = (await api("DELETE", `/api/attachments/${a.id}`)).attachments; if (tx) tx.attachments = list.length; draw(); }
      catch (err) { dialogError(err); }
    });
  };
  const p = dialog(tx ? "Receipts and files" : `Papers: ${acc.name}`, "", [{ label: "Close" }]);
  draw();
  await p;
  if (done) done();
}

// ---------- Files: every receipt and paper, searchable ----------
const filesState = { q: "", account: "", from: "", to: "", sort: "date", dir: -1 };
async function renderFiles() {
  const st = filesState;
  const qs = new URLSearchParams();
  if (st.q) qs.set("q", st.q); if (st.account) qs.set("account", st.account);
  if (st.from) qs.set("from", st.from); if (st.to) qs.set("to", st.to);
  const r = await GET("/api/attachments?" + qs.toString());
  const key = { date: a => a.date || "", account: a => (a.account_name || "").toLowerCase(), name: a => (a.note || a.name).toLowerCase(),
    amount: a => a.amount == null ? -Infinity : Math.abs(a.amount) }[st.sort];
  const rows = r.files.slice().sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : b.id - a.id) * st.dir);
  const mayChange = canEdit();
  const y = new Date().getFullYear();
  const periods = [["", "", "Any time"], [`${y}-01-01`, `${y}-12-31`, "This year"], [`${y - 1}-01-01`, `${y - 1}-12-31`, "Last year"],
    [isoDaysAgo(30), "", "Last 30 days"], [isoDaysAgo(90), "", "Last 90 days"]];
  const th = (k, l, cls) => `<th class="${cls || ""} sortable" data-sort="${k}" title="Sort">${l}${st.sort === k ? (st.dir < 0 ? " ▾" : " ▴") : ""}</th>`;
  view().innerHTML = `<div class="pagehead"><h1>Files</h1></div>
    <p class="small muted" style="margin-top:-6px">Every receipt and paper kept in ${esc(envName())}: with entries, and with accounts (choose <b>Papers</b> on an account's page).</p>
    <div class="toolbar files-filter">
      <input id="f_q" type="search" placeholder="Search notes, keywords, payees, file names…" value="${esc(st.q)}" style="min-width:260px">
      <select id="f_acct"><option value="">All accounts</option>${r.accounts.map(a => `<option value="${a.id}" ${String(a.id) === String(st.account) ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select>
      <select id="f_period" aria-label="Time period">${periods.map(([f, t, l]) => `<option data-f="${f}" data-t="${t}" ${f === st.from && t === st.to ? "selected" : ""}>${l}</option>`).join("")}
        ${periods.some(([f, t]) => f === st.from && t === st.to) ? "" : `<option selected>Between these dates</option>`}</select>
      <label class="small">From <input type="date" id="f_from" value="${esc(st.from)}"></label>
      <label class="small">To <input type="date" id="f_to" value="${esc(st.to)}"></label>
      ${st.q || st.account || st.from || st.to ? `<a href="#" id="f_clear" class="small">Clear</a>` : ""}
    </div>
    <div class="card flush"><table class="files-table">
      <tr><th></th>${th("date", "Date")}${th("name", "File and note")}${th("account", "Account")}<th>Entry</th>${th("amount", "Amount", "num")}<th></th></tr>
      ${rows.map(a => `<tr>
        <td class="files-thumb">${attThumb(a)}</td>
        <td class="small" style="white-space:nowrap">${esc(niceDate(a.date))}</td>
        <td><div class="small att-name" title="${esc(a.name)}">${esc(a.name)}</div>
          ${mayChange ? `<input class="att-note" data-attnote="${a.id}" value="${esc(a.note || "")}" maxlength="500" placeholder="Add a note or keywords" aria-label="Note for ${esc(a.name)}">` : `<div class="small">${esc(a.note || "")}</div>`}</td>
        <td class="small"><a href="#/accounts/${a.account_id}">${esc(a.account_name)}</a></td>
        <td class="small">${a.transaction_id ? `${esc(a.payee || "")}${a.category_name ? `<div class="muted">${esc(a.category_name)}</div>` : ""}` : `<span class="muted">Kept with the account</span>`}</td>
        <td class="num small">${a.amount == null ? "" : fmt(a.amount, true)}</td>
        <td class="small" style="white-space:nowrap"><a href="${attachUrl(a.id)}" target="_blank" rel="noopener">Open</a> · <a href="${attachUrl(a.id, true)}">Download</a></td>
      </tr>`).join("")}
    </table>${rows.length ? "" : `<div class="empty">${st.q || st.account || st.from || st.to ? "Nothing matches." : "No files yet. Attach a receipt to an entry (Receipts), or keep papers with an account (Papers)."}</div>`}</div>
    <p class="small muted">${rows.length} file${rows.length === 1 ? "" : "s"}${rows.length >= 500 ? " (the newest 500: narrow the search to see others)" : ""}. Each word you type must appear in the note, the file name, the entry or the account.</p>`;
  const again = () => renderFiles();
  let t = null;
  q("#f_q").oninput = e => { clearTimeout(t); t = setTimeout(() => { st.q = e.target.value.trim(); again().then(() => { const i = q("#f_q"); i.focus(); i.setSelectionRange(i.value.length, i.value.length); }); }, 350); };
  q("#f_acct").onchange = e => { st.account = e.target.value; again(); };
  q("#f_period").onchange = e => { const o = e.target.selectedOptions[0]; if (o.dataset.f === undefined) return; st.from = o.dataset.f; st.to = o.dataset.t; again(); };
  q("#f_from").onchange = e => { st.from = e.target.value; again(); };
  q("#f_to").onchange = e => { st.to = e.target.value; again(); };
  if (q("#f_clear")) q("#f_clear").onclick = e => { e.preventDefault(); Object.assign(st, { q: "", account: "", from: "", to: "" }); again(); };
  qa("[data-sort]").forEach(h => h.onclick = () => { if (st.sort === h.dataset.sort) st.dir = -st.dir; else { st.sort = h.dataset.sort; st.dir = h.dataset.sort === "date" || h.dataset.sort === "amount" ? -1 : 1; } again(); });
  wireAttEdits(view(), r.files);
}
function isoDaysAgo(n) { const d = new Date(); d.setDate(d.getDate() - n); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
function envName() { return ((S.me && S.me.envs || []).find(e => e.id === S.env) || {}).name || "this environment"; }

// The entry line under a register. A transaction picked in the register is shown
// first, unchangeable, until "Edit transaction" is chosen: changes are on purpose.
function entryForm(acc, tx, done) {
  const el = q("#entry");
  let editing = !tx;
  let kind = tx ? (tx.amount > 0 ? "deposit" : "payment") : "payment";
  let catVal = tx ? (tx.xlink_id ? "l:" + tx.xlink_id : (tx.transfer_id ? "x:" + tx.transfer_account_id : String(tx.category_id || ""))) : "";
  // Receipts picked for a new entry are sent once it's entered.
  let pending = [];
  const pendingText = () => pending.length
    ? `${pending.length} file${pending.length === 1 ? "" : "s"} to attach when entered (${pending.map(f => esc(f.name || "photo")).join(", ")}) · <a href="#" id="e_unpend">clear</a>` : "";
  const draw = () => {
    const amt = tx ? Math.abs(tx.amount) : "";
    el.innerHTML = `<div class="kind">${[["payment", "Withdrawal"], ["deposit", "Deposit"]].map(([k, l]) =>
      `<button type="button" data-k="${k}" class="small ${kind === k ? "on" : ""}">${l}</button>`).join("")}
      ${!tx && !acc.liability && !acc._shared ? `<button type="button" class="small" id="e_stub" title="A paycheck in full: gross pay, each tax and deduction, and the take-home pay that reached this account">Paystub…</button>` : ""}
      <span class="small ${tx && editing ? "" : "muted"}" style="margin-left:8px;align-self:center">${!tx ? "New transaction" : editing ? "<b>Editing</b> this transaction" : "Viewing a transaction: choose <b>Edit transaction</b> to change it"}</span>
      <button type="button" class="small linkbtn" id="e_more" title="Number, memo and status"></button>
      <span class="small" id="e_hint" style="margin-left:12px;align-self:center;color:var(--teal)"></span>
      <span id="e_stmt" style="margin-left:10px;align-self:center"></span></div>
      <div class="row">
        <div><label>Date</label><input type="date" id="e_date" value="${tx ? tx.date : todayISO()}"></div>
        <div class="xtra"><label>Number</label><input id="e_num" value="${tx ? esc(tx.number) : ""}"></div>
        <div><label>${kind === "deposit" ? "From (payer)" : "Pay to"}</label><input id="e_payee" list="payeeList" value="${tx ? esc(tx.payee) : ""}" autocomplete="off"></div>
        <div><label>Category or transfer${canEdit() && !acc._shared ? ` <a href="#/settings/categories" class="small catedit" title="Add or change categories (Settings › Categories)">edit</a>` : ""}</label><select id="e_cat">${registerCatOptions(acc, kind, catVal)}</select></div>
        <div class="xtra"><label>Memo</label><input id="e_memo" value="${tx ? esc(tx.memo) : ""}"></div>
        <div><label>Amount</label><input id="e_amt" class="num" value="${amt === "" ? "" : dollars(amt)}" placeholder="0.00"></div>
        <div id="e_recvbox" style="display:none"><label id="e_recvlbl">Amount received</label><input id="e_recv" class="num" placeholder="0.00"
          value="${tx && tx.transfer_currency && tx.transfer_currency !== tx.currency && tx.transfer_amount != null ? dollars(Math.abs(tx.transfer_amount)) : ""}"></div>
        <div class="xtra"><label>Status</label><select id="e_st"><option value="">—</option><option value="C" ${tx && tx.status === "C" ? "selected" : ""}>Cleared</option><option value="R" ${tx && tx.status === "R" ? "selected" : ""}>Reconciled</option></select></div>
        <div style="display:flex;gap:6px">${!tx ? `<button class="primary" id="e_save">Enter</button>` : ""}</div>
      </div>${!tx ? `<div class="entry-attach small">${attachPickers("ea")}<span id="e_pending" class="muted">${pendingText()}</span></div>` : `<div class="entry-actions">${!editing
          ? `${tx.paycheck != null && canEdit() ? `<button id="e_paydet" title="Gross pay, taxes and deductions from the pay slip">Add paystub details</button>${tx.pay_flag
              ? `<button id="e_paydone" title="This paycheck won't get more detail: stop flagging it">Complete as is</button>`
              : (tx.paycheck === 2 ? `<button id="e_paydone" data-undo="1" title="Marked complete as is: flag it again if it's missing what's usual">Flag if incomplete</button>` : "")}` : ""}<button id="e_att" title="Photos of the receipt, PDFs">${CLIP_ICON} Receipts${tx.attachments ? ` (${tx.attachments})` : ""}</button>${canEdit() && !acc._shared && !S.shareCtx && !tx.xlink_id
            ? `<button id="e_sched" title="Make a scheduled bill, deposit or transfer from this entry (Bills &amp; Deposits)">Schedule…</button>` : ""}<button id="e_hist" title="Who entered and changed it, and when">History</button><button class="primary" id="e_edit" title="Change this transaction">✎ Edit transaction</button><button id="e_new" title="Close it and start a new transaction">Close</button>`
          : `<button class="primary" id="e_save">Save changes</button><button id="e_cancel" title="Leave it as it was (Esc)">Cancel</button>
             <button class="danger trash" id="e_del" title="Delete this transaction" aria-label="Delete this transaction">${TRASH_ICON} Delete</button>`}</div>`}<datalist id="payeeList">${S.payees.map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>`;
    const cat = q("#e_cat", el), payee = q("#e_payee", el), amtEl = q("#e_amt", el);
    // Number, memo and status: folded away in Simple until asked for (remembered).
    const more = () => {
      const open = foldOpen("entry");
      el.classList.toggle("compact", !open);
      const filled = tx && (tx.number || tx.memo || tx.status);
      q("#e_more", el).textContent = open ? "Fewer fields" : `More fields${filled ? " ●" : ""}`;
    };
    q("#e_more", el).onclick = () => { rememberFold("entry", !foldOpen("entry")); more(); };
    more();
    // Viewing: every field is locked until "Edit transaction".
    el.classList.toggle("viewing", !editing);
    if (!editing) qa(".row input, .row select, [data-k]", el).forEach(x => { x.disabled = true; });
    const hint = () => {
      const v = cat.value;
      const xl = v.startsWith("l:") ? (S.xlinks || []).find(l => l.link_id == v.slice(2)) : null;
      const other = v.startsWith("x:") ? S.accounts.find(a => a.id == v.slice(2))
        : (xl ? { name: `${xl.account_name} (${xl.env_name})` } : null);
      q("#e_hint", el).textContent = other && editing ? `A matching ${kind === "deposit" ? "withdrawal" : "deposit"} is added to ${other.name}'s register automatically.` : "";
      // Another currency on the other side: ask what arrived there (or left it).
      const twoCur = other && other.currency && acc.currency && other.currency !== acc.currency;
      q("#e_recvbox", el).style.display = twoCur ? "" : "none";
      if (twoCur) {
        q("#e_recvlbl", el).textContent = `${kind === "deposit" ? tr("Amount that left") : tr("Amount received")} (${other.currency})`;
        q("#e_hint", el).textContent = tr(`${acc.name} and ${other.name} are in different currencies: enter how much ${kind === "deposit" ? "left" : "arrived in"} ${other.name}.`);
        // Empty: a guess from the last rate used between these two (or the rough rate).
        q("#e_recv", el).onfocus = () => {
          const r = q("#e_recv", el), c = Math.round((parseAmount(amtEl.value) || 0) * 100);
          if (!r.value && c) r.value = guessReceived(acc.currency, other.currency, c);
        };
      }
      // A payment to a card (from here, or into this card from another account).
      const card = !tx && v.startsWith("x:") ? (kind === "payment" ? v.slice(2) : (CARD_TYPES.includes(acc.type) ? acc.id : null)) : null;
      statementButton(card, q("#e_stmt", el), left => { amtEl.value = dollars(left); amtEl.focus(); });
    };
    cat.onchange = () => { catVal = cat.value; hint(); };
    hint();
    if (q("#e_stub", el)) q("#e_stub", el).onclick = () => paystubDialog(acc, null, done, { employer: payee.value.trim(), date: q("#e_date", el).value });
    qa("[data-k]", el).forEach(b => b.onclick = () => {
      const keep = { payee: payee.value, amt: amtEl.value, memo: q("#e_memo", el).value, num: q("#e_num", el).value, date: q("#e_date", el).value };
      catVal = cat.value; kind = b.dataset.k; draw();
      q("#e_payee", el).value = keep.payee; q("#e_amt", el).value = keep.amt; q("#e_memo", el).value = keep.memo;
      q("#e_num", el).value = keep.num; q("#e_date", el).value = keep.date;
    });
    payee.onchange = () => {
      // Fill in what was used last time for this payee (like the original's automatic fill-in).
      const p = S.payees.find(x => x.name.toLowerCase() === payee.value.trim().toLowerCase());
      if (!p || tx) return;
      if (!cat.value && p.category_id) { cat.value = p.category_id; catVal = cat.value; }
      if (!amtEl.value && p.last_amount) {
        const keep = { payee: payee.value, amt: dollars(Math.abs(p.last_amount)) };
        kind = p.last_amount > 0 ? "deposit" : "payment"; draw();
        q("#e_payee", el).value = keep.payee; q("#e_amt", el).value = keep.amt;
      }
    };
    if (q("#e_save", el)) q("#e_save", el).onclick = async () => {
      const raw = parseAmount(q("#e_amt", el).value);
      if (!raw) { toast("Enter an amount", true); return; }
      const signed = Math.abs(raw) * (kind === "deposit" ? 1 : -1);
      const body = { account_id: acc.id, date: q("#e_date", el).value, number: q("#e_num", el).value, payee: q("#e_payee", el).value,
        memo: q("#e_memo", el).value, amount: signed.toFixed(2), status: q("#e_st", el).value };
      const v = q("#e_cat", el).value;
      if (v.startsWith("l:")) body.xlink_id = +v.slice(2);
      else if (v.startsWith("x:")) {
        body.transfer_account_id = +v.slice(2);
        // Between two currencies: what arrived (or left) on the other side.
        if (q("#e_recvbox", el).style.display !== "none") body.received = q("#e_recv", el).value;
      }
      else if (v.startsWith("sh:")) body.share_xfer = +v.slice(3);
      else body.category_id = v || null;
      let made = null;
      try {
        if (tx) await api("PUT", "/api/transactions/" + tx.id, body); else made = await api("POST", "/api/transactions", body);
        if (body.received) {
          const o = S.accounts.find(a => a.id == body.transfer_account_id);
          if (o) keepRate(acc.currency, o.currency, Math.round(Math.abs(signed) * 100), body.received);
        }
        const xl = body.xlink_id ? (S.xlinks || []).find(l => l.link_id == body.xlink_id) : null;
        const other = body.transfer_account_id ? S.accounts.find(a => a.id == body.transfer_account_id)
          : (xl ? { name: `${xl.account_name} (${xl.env_name})` } : null);
        let note = other ? `Entered here and in ${other.name}` : (tx ? "Saved" : "Entered");
        if (made && made.id && pending.length) {
          const files = pending; pending = [];
          q("#e_pending", el) && (q("#e_pending", el).textContent = "Sending receipts…");
          try { for (const f of files) await uploadAttachment(made.id, f); note += ` with ${files.length} receipt${files.length === 1 ? "" : "s"}`; }
          catch (e) { toast(`Entered, but a receipt wasn't attached: ${e.message}. Open the entry and choose Receipts to try again.`, true); done(); return; }
        }
        toast(note); done();
      } catch (e) { toast(e.message, true); }
    };
    wirePickers("ea", el, files => { pending = pending.concat(files); q("#e_pending", el).innerHTML = pendingText(); wireUnpend(); });
    const wireUnpend = () => { const u = q("#e_unpend", el); if (u) u.onclick = e => { e.preventDefault(); pending = []; q("#e_pending", el).innerHTML = ""; }; };
    wireUnpend();
    if (q("#e_att", el)) q("#e_att", el).onclick = () => attachDialog({ tx }, done);
    // A paycheck with only its take-home pay: its paystub can be added now.
    if (q("#e_paydet", el)) q("#e_paydet", el).onclick = () => paystubDialog(acc, null, done,
      { replace_tx: tx.id, employer: tx.payee, date: tx.date, net: Math.abs(tx.amount) });
    if (q("#e_paydone", el)) q("#e_paydone", el).onclick = async e => {
      const undo = !!e.target.dataset.undo;
      try { await api("POST", "/api/paychecks/complete", { kind: "tx", id: tx.id, complete: !undo }); toast(undo ? "It's flagged again when something's missing" : "Marked complete as is"); done(); }
      catch (err) { toast(err.message, true); }
    };
    if (q("#e_edit", el)) q("#e_edit", el).onclick = () => { editing = true; draw(); q("#e_payee", el).focus(); };
    if (q("#e_hist", el)) q("#e_hist", el).onclick = () => entryHistoryDialog("transaction", tx.id, done);
    if (q("#e_sched", el)) q("#e_sched", el).onclick = () => scheduleFromEntry(acc, tx);
    if (q("#e_new", el)) q("#e_new", el).onclick = () => {
      tx = null; editing = true; kind = "payment"; catVal = ""; qa("tr.sel").forEach(x => x.classList.remove("sel")); draw();
    };
    // Cancel: back to the transaction as saved, locked again.
    if (q("#e_cancel", el)) q("#e_cancel", el).onclick = () => {
      editing = false; kind = tx.amount > 0 ? "deposit" : "payment";
      catVal = tx.xlink_id ? "l:" + tx.xlink_id : (tx.transfer_id ? "x:" + tx.transfer_account_id : String(tx.category_id || ""));
      draw();
    };
    if (q("#e_del", el)) q("#e_del", el).onclick = async () => {
      if (await confirmBox(tx.transfer_id ? "Delete this transfer? The matching entry in the other account is deleted too." : "Delete this transaction?")) {
        await api("DELETE", "/api/transactions/" + tx.id); done();
      }
    };
    el.onkeydown = e => {
      if (e.key === "Enter" && e.target.tagName === "INPUT" && q("#e_save", el)) { e.preventDefault(); q("#e_save", el).click(); }
      if (e.key === "Escape" && q("#e_cancel", el)) { e.preventDefault(); q("#e_cancel", el).click(); }
    };
  };
  draw();
}

async function reconcile(acc) {
  const all = await GET(`/api/transactions?account=${acc.id}`);
  const rows = all.filter(t => t.status !== "R").reverse();
  // Starting point: the opening balance plus everything already reconciled.
  const start = acc.opening_balance + all.filter(t => t.status === "R").reduce((s, t) => s + t.amount, 0);
  const body = `<p class="small muted">Tick each transaction that appears on your statement. When the difference is zero, the account is balanced.</p>
    <div class="form"><div><label>Statement date</label><input type="date" name="statement_date" value="${todayISO()}"></div>
    <div><label>Statement ending balance</label><input name="statement_balance" class="num" value="${dollars(acc.cleared_balance)}"></div>
    <div><label>Starting balance</label><div style="padding:6px 0">${fmt(start)}</div></div>
    <div><label>Difference</label><div id="rdiff" class="big" style="font-size:18px">–</div></div></div>
    <div style="max-height:340px;overflow:auto;margin-top:10px"><table>
    <tr><th></th><th>Date</th><th>Payee</th><th class="num">Amount</th></tr>
    ${rows.map(t => `<tr><td><input type="checkbox" data-r="${t.id}" data-a="${t.amount}" ${t.status === "C" ? "checked" : ""}></td>
      <td class="small">${niceDate(t.date)}</td><td>${esc(t.payee)}<div class="small muted">${esc(t.category_label)}</div></td><td class="num">${fmt(t.amount, false, t)}</td></tr>`).join("")}
    </table>${rows.length ? "" : `<div class="empty">Everything here is already balanced.</div>`}</div>`;
  const p = dialog("Balance " + acc.name, body, [{ label: "Cancel" }, {
    label: "Finish", cls: "primary", action: async root => {
      const f = formData(root);
      const ids = qa("[data-r]", root).filter(c => c.checked).map(c => +c.dataset.r);
      const r = await api("POST", `/api/accounts/${acc.id}/reconcile`, { statement_balance: f.statement_balance, statement_date: f.statement_date, ids });
      toast(`Balanced: ${r.reconciled} transactions reconciled`); render();
    }
  }]);
  const recalc = () => {
    const root = q("#dlgBody");
    const target = Math.round(parseAmount(q("[name=statement_balance]", root).value || "0") * 100) || 0;
    const reconciledSum = start; // reconciled transactions are part of the starting balance
    const chosen = qa("[data-r]", root).filter(c => c.checked).reduce((s, c) => s + (+c.dataset.a), 0);
    const diff = target - (reconciledSum + chosen);
    q("#rdiff").innerHTML = fmt(diff); q("#rdiff").style.color = diff === 0 ? "var(--green)" : "";
  };
  qa("#dlgBody input").forEach(i => i.oninput = recalc);
  // The server works from the opening balance plus reconciled transactions.
  recalc();
  return p;
}

async function importFile(acc) {
  const body = `<p>Bring in transactions from a file you downloaded from your bank's website:</p>
    <ul class="small" style="margin:0 0 8px 18px;padding:0">
      <li><b>OFX, QFX or QBO</b> (often called "Quicken", "Money" or "QuickBooks" download): best, because each entry has the bank's own id, so nothing is ever imported twice.</li>
      <li><b>CSV</b> (a spreadsheet with Date and Amount columns, or Debit/Credit) and <b>QIF</b> also work.</li></ul>
    <p class="small muted">Next you'll see what would happen to each entry before anything is saved: new entries, entries matched to ones you already have (typed, entered from the schedule or recorded automatically: same amount within 4 days), and automatic entries whose estimate would take the bank's amount. You can change any of them.</p>
    <input type="file" id="impfile" accept=".ofx,.qfx,.qbo,.csv,.qif,.txt">`;
  return dialog("Import into " + acc.name, body, [{ label: "Cancel" }, {
    label: "Review", cls: "primary", action: async root => {
      const f = q("#impfile", root).files[0];
      if (!f) { toast("Choose a file", true); return false; }
      const text = await f.text();
      const pv = await api("POST", "/api/import", { account_id: acc.id, text, filename: f.name, preview: true });
      setTimeout(() => importReview(acc, f.name, text, pv), 0);
    }
  }]);
}

// Review an import before anything is saved: each row's planned action, which the
// person can change (a match or correction can become a new entry; anything can be skipped).
function importReview(acc, filename, text, pv) {
  const plan = pv.plan || [];
  const desc = it => it.action === "match" ? `Match to your entry: ${niceDate(it.target.date)} ${esc(it.target.payee)} ${fmt(it.target.amount, true)}`
    : it.action === "correct" ? `Update your automatic entry ${niceDate(it.target.date)} ${esc(it.target.payee)} from ${fmt(it.target.amount, true)} to ${fmt(it.amount, true)}`
    : it.action === "add" ? "Add as a new entry" : `Skip: ${esc(it.why || "already there")}`;
  const opts = it => it.action === "skip" ? null
    : [[it.action, it.action === "add" ? "Add" : (it.action === "match" ? "Match" : "Update")], ...(it.action !== "add" ? [["add", "Add as new"]] : []), ["skip", "Skip"]];
  const count = a => plan.filter(p => p.action === a).length;
  const body = `<p class="small">${count("add")} new · ${count("match")} matched · ${count("correct")} automatic entr${count("correct") === 1 ? "y" : "ies"} to update · ${count("skip")} already there</p>
    ${pv.file_account && acc.details && acc.details.account_number && !String(acc.details.account_number).endsWith(pv.file_account)
      ? `<p class="small"><span class="pill red">Check</span> This file is for an account ending ${esc(pv.file_account)}, but this account's number ends ${esc(lastFour(acc.details.account_number).slice(-4))}.</p>` : ""}
    <div style="max-height:52vh;overflow:auto"><table class="imp-review"><tr><th>Date</th><th>From the bank</th><th class="num">Amount</th><th>What happens</th></tr>
    ${plan.map(it => `<tr class="${it.action === "skip" ? "muted" : ""}"><td class="small" style="white-space:nowrap">${niceDate(it.date)}</td>
      <td>${esc(it.payee)}${it.memo ? `<div class="small muted">${esc(it.memo)}</div>` : ""}</td><td class="num">${fmt(it.amount, true)}</td>
      <td class="small">${desc(it)}${opts(it) ? `<div><select data-imp="${it.i}" aria-label="What to do with ${esc(it.payee)}">${opts(it).map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}</select></div>` : ""}</td></tr>`).join("")}
    </table></div>`;
  return dialog("Review import: " + filename, body, [{ label: "Cancel" }, {
    label: "Import these", cls: "primary", action: async root => {
      const choices = {};
      qa("[data-imp]", root).forEach(s => { choices[s.dataset.imp] = s.value; });
      const r = await api("POST", "/api/import", { account_id: acc.id, text, filename, choices });
      const parts = [`${r.added} added`];
      if (r.matched) parts.push(`${r.matched} matched to entries you had`);
      if (r.corrected) parts.push(`${r.corrected} automatic entr${r.corrected === 1 ? "y" : "ies"} updated to the bank's amount`);
      if (r.skipped) parts.push(`${r.skipped} already there`);
      let msg = `<p>${parts.join(" · ")}.</p>`;
      if (r.bank_balance != null) {
        const same = r.bank_balance === r.register_balance;
        msg += `<p>The bank's balance on ${niceDate(r.bank_balance_date)}: <b>${fmt(r.bank_balance, true)}</b>; this register on that day: <b>${fmt(r.register_balance, true)}</b>
          ${same ? '<span class="pill green">they match</span>' : '<span class="pill amber">they differ</span>'}</p>
          ${same ? "" : '<p class="small muted">A difference usually means something isn\'t entered yet, or the opening balance needs a look.</p>'}`;
      }
      if (r.file_account && acc.details && acc.details.account_number && !String(acc.details.account_number).endsWith(r.file_account))
        msg += `<p class="small"><span class="pill red">Check</span> The file is for an account ending ${esc(r.file_account)}, but this account's number ends ${esc(lastFour(acc.details.account_number).slice(-4))}.</p>`;
      setTimeout(() => dialog("Import finished", msg, [{ label: "OK", cls: "primary" }]).then(() => render()), 0);
    }
  }]);
}

// ---------- BILLS ----------
// ---------- a scheduled item from a register entry ----------
// After moving in from another program the schedule is empty: an entry in the register can
// start one. The server works it out (who, how much, the category and the account from the
// entry; how often and the next date from the same payee's other entries in this account),
// then the person checks it in the usual form.
async function scheduleFromEntry(acc, tx) {
  const g = await GET(`/api/transactions/${tx.id}/schedule-guess`);
  const a = g.already;
  if (a && !(await confirmBox(`${g.start.payee} is already scheduled (${freqLabel(a)}, next ${niceDate(a.next_date)}). Schedule another one?`))) return;
  return editBill(null, g.start.kind, g.start);
}

async function editBill(bill, kind, start) {
  await loadBasics();
  // Accounts shared into this environment for entering, with their bills: they can be
  // scheduled from here too (the item is kept with the shared account).
  const sharedOpts = S.shareCtx ? [] : (await GET("/api/shares/incoming").catch(() => [])).filter(a => a.can_edit && a.include_bills && !a.closed);
  const shOptions = sel => sharedOpts.length ? `<optgroup label="Shared with this environment">${sharedOpts.map(a =>
    `<option value="sh:${a.share_id}" ${sel === "sh:" + a.share_id ? "selected" : ""}>${esc(a.name)} (shared by ${esc(a.shared_by)})</option>`).join("")}</optgroup>` : "";
  // (start: a new item already filled in, e.g. from a register entry)
  const b = bill || Object.assign({ kind: kind || "bill", payee: "", amount: 0, estimate: 0, amount_mode: "fixed", average_count: 12,
    frequency: "Monthly", next_date: todayISO(), account_id: (S.accounts[0] || {}).id }, start || {});
  const xb = !!(bill && bill.x_link_id);   // transfer with another environment: its ends stay as they are
  const varies = b.amount_mode === "average";
  const est = b.estimate != null ? b.estimate : b.amount;
  const hist = b.history || [];
  const body = `<div class="form">
    <div><label>Type</label><select name="kind">${[["bill", "Bill (money out)"], ["deposit", "Deposit (money in)"], ["transfer", "Transfer"]].map(([k, l]) => `<option value="${k}" ${b.kind === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    <div class="wide"><label>Pay to / receive from</label><input name="payee" value="${esc(b.payee)}" list="pl"></div>
    <div class="wide paycheckf" style="grid-column:1/-1"><label class="check"><input type="checkbox" name="paycheck" ${b.paycheck ? "checked" : ""}> This is a paycheck</label>
      <div class="small muted" style="margin-left:24px">The amount is your take-home pay (what reaches the account). When it comes in, record just that, or add the paystub too: gross pay and deductions.</div></div>
    <div><label id="amtLabel">${varies ? "Starting estimate (optional)" : "Amount"}</label>
      <input name="amount" class="num" value="${est ? dollars(est) : ""}" placeholder="${varies ? "none yet" : "0.00"}">
      <div class="small muted" id="avgNote" style="margin-top:3px">${varies && hist.length ? `Average of the last ${hist.length}: <b>${fmt(b.amount, true)}</b> (${hist.map(h => fmt(h.amount, true)).join(", ")})` : (varies ? "Used until the first payment is recorded; after that the average takes over." : "")}</div></div>
    ${xb ? `<div class="wide" style="grid-column:1/-1"><label>Between</label><div style="padding:6px 0"><b>${esc(S.accounts.find(a => a.id === b.account_id)?.name || "")}</b>
        ${b.x_dir === "out" ? "→" : "←"} <b>${esc(b.to_account_name || "")}</b> <span class="small muted">(the accounts of a transfer with another environment can't be changed; delete it and schedule a new one instead)</span></div></div>`
      : `<div><label>Account</label><select name="account_id">${acctOptions(b.account_id)}${shOptions("")}</select></div>
    <div class="xfer"><label>To account</label><select name="to_account_id">${acctOptions(b.to_account_id, null)}${shOptions("")}</select></div>
    <div class="xcur" style="display:none"><label id="xcurLabel">Usually arrives</label><input name="received" class="num" placeholder="optional" value="${b.received ? dollars(b.received) : ""}">
      <div class="small muted">The two accounts are in different currencies: what usually arrives (you can change it each time).</div></div>
    <div class="splitf wide" style="grid-column:1/-1">
      <div id="billSplits"></div>
      <div class="destfoot"><button type="button" class="small" id="addSplit" title="Paid into more than one account (direct deposit split between accounts)">+ Add an account</button>
        <span id="splitTotal"></span></div></div>`}
    <div class="catf wide"><label>Category</label><select name="category_id">${catOptions(b.category_id, { full: true })}</select>
      <div class="small muted" id="budgetHint" style="margin-top:3px"></div></div>
    <div><label>How often</label><select name="frequency">${S.meta.frequencies.map(f => `<option ${f === b.frequency ? "selected" : ""}>${f}</option>`).join("")}</select></div>
    <div><label>Next date</label><input type="date" name="next_date" value="${b.next_date}"></div>
    <div class="wide" style="grid-column:1/-1">${moreFold("bill", `
      <div style="margin:4px 0 8px"><label>Is it usually the same amount each time?</label>
        <label class="check"><input type="radio" name="amount_mode" value="fixed" ${varies ? "" : "checked"}> Yes, it's the same each time</label>
        <label class="check"><input type="radio" name="amount_mode" value="average" ${varies ? "checked" : ""}> No, the amount varies: expect the average of the last
          <input name="average_count" class="num" style="width:56px" value="${b.average_count || 12}"> payments</label></div>
      <div class="lastday" style="margin-bottom:8px"><label class="check"><input type="checkbox" name="last_day" ${b.last_day ? "checked" : ""}>
        On the last day of the month</label><div class="small muted">For things like interest posted at month end: the 28th, 29th, 30th or 31st, whichever is last.</div></div>
      <div style="margin-bottom:8px"><label>Memo</label><input name="memo" style="width:100%" value="${esc(b.memo || "")}"></div>
      ${autoFields(b)}`, varies || b.last_day || b.memo || b.auto)}</div>
  </div><datalist id="pl">${S.payees.map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>`;
  const btns = [{ label: "Cancel" }];
  if (bill) btns.unshift({ label: "Delete", cls: "danger", action: async () => { if (!(await confirmBox("Delete this scheduled item?"))) return false; await api("DELETE", "/api/bills/" + b.id); render(); } });
  btns.push({ label: "Save", cls: "primary", action: async root => {
    const f = formData(root);
    // The other accounts a deposit goes into, each with its amount: set, or the average.
    readSplits();
    Object.keys(f).filter(k => k.startsWith("split_")).forEach(k => delete f[k]);
    if (!xb) f.splits = f.kind === "deposit" ? splits.filter(x => x.account_id || parseAmount(x.amount) > 0)
      .map(x => ({ id: x.id || null, account_id: +x.account_id || null, amount: x.amount, amount_mode: x.amount_mode })) : [];
    if (xb) { f.kind = "transfer"; delete f.account_id; delete f.to_account_id; }
    const from = String(f.account_id || ""), to = String(f.to_account_id || "");
    const shOf = v => v.startsWith("sh:") ? sharedOpts.find(a => a.share_id == v.slice(3)) : null;
    const sFrom = shOf(from), sTo = f.kind === "transfer" ? shOf(to) : null;
    if (sFrom || sTo) {
      // Kept with the shared account (its owner sees it too).
      const sh = sFrom || sTo;
      const body = { ...f };
      if (f.kind !== "transfer") body.account_id = sh.id;
      else if (sFrom && sTo) {
        if (sFrom.env_id !== sTo.env_id) throw new Error("Those two shared accounts belong to different people's environments");
        Object.assign(body, { account_id: sFrom.id, to_account_id: sTo.id });
      } else if (sFrom) Object.assign(body, { account_id: sFrom.id, to_account_id: "", x_account_id: +to, x_dir: "out" });
      else Object.assign(body, { account_id: sTo.id, to_account_id: "", x_account_id: +from, x_dir: "in" });
      delete body.splits;   // (one account only, there)
      await api("POST", "/api/bills", body, sh);
      if (bill && !bill._sh) await api("DELETE", "/api/bills/" + b.id);   // moved to the shared account
    } else if (bill) await api("PUT", "/api/bills/" + b.id, f); else await api("POST", "/api/bills", f);
    toast("Saved"); render();
  } });
  const p = dialog(bill ? "Change scheduled item" : "Schedule a bill or deposit", body, btns);
  const ks = q("#dlgBody [name=kind]");
  // Paid into more than one account: one line per other account, with its amount, set or
  // averaged from what it got before (the main account's is above).
  const splits = (b.splits || []).map(x => ({ id: x.id, account_id: x.account_id,
    amount: x.estimate ? dollars(x.estimate) : (x.amount_mode === "average" ? "" : dollars(x.amount)), amount_mode: x.amount_mode,
    avg: x.amount_mode === "average" && (x.history || []).length ? x.amount : null }));
  function readSplits() {
    qa("#billSplits [data-si]").forEach(r => {
      const x = splits[+r.dataset.si];
      x.account_id = q("select.sp-acct", r).value; x.amount = q("input.sp-amt", r).value; x.amount_mode = q("select.sp-mode", r).value;
    });
  }
  function drawSplits() {
    const main = (q("#dlgBody [name=account_id]") || {}).value;
    q("#billSplits").innerHTML = splits.length ? `<div class="destline desthead4"><label>Also deposited into</label><label class="num">Amount</label><label>Each time</label><span></span></div>` +
      splits.map((x, i) => `<div class="destline4" data-si="${i}">
        <select class="sp-acct" name="split_${i}_account" aria-label="Also deposited into"><option value="">(choose the account)</option>${S.accounts.filter(a => a.id != main && !a.liability && (!a.closed || a.id == x.account_id))
          .map(a => `<option value="${a.id}" ${a.id == x.account_id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select>
        <input class="sp-amt num" name="split_${i}_amount" inputmode="decimal" value="${esc(x.amount || "")}" placeholder="${x.amount_mode === "average" ? "estimate" : "0.00"}" aria-label="Amount"
          title="${x.amount_mode === "average" ? (x.avg != null ? tr("Average so far") + ": " + fmt(x.avg, true) : "Starting estimate, until the first one is recorded") : ""}">
        <select class="sp-mode" name="split_${i}_mode" aria-label="Each time"><option value="fixed" data-en="Set amount" ${x.amount_mode !== "average" ? "selected" : ""}>Set amount</option>
          <option value="average" data-en="Average" ${x.amount_mode === "average" ? "selected" : ""}>Average</option></select>
        <button type="button" class="tiny" data-delsplit="${i}" title="Remove this account" aria-label="Remove this account">✕</button></div>`).join("") : "";
    qa("#billSplits [data-delsplit]").forEach(bt => bt.onclick = () => { readSplits(); splits.splice(+bt.dataset.delsplit, 1); drawSplits(); });
    qa("#billSplits input, #billSplits select").forEach(x => { x.addEventListener("input", splitTotal); x.addEventListener("change", () => { readSplits(); drawSplits(); }); });
    splitTotal();
  }
  function splitTotal() {
    const box = q("#splitTotal"); if (!box) return;
    if (!splits.length) { box.textContent = ""; return; }
    let tot = Math.round((parseAmount(q("#dlgBody [name=amount]").value) || 0) * 100);
    qa("#billSplits [data-si]").forEach(r => {
      const x = splits[+r.dataset.si], v = Math.round((parseAmount(q("input.sp-amt", r).value) || 0) * 100);
      tot += v || (x.avg || 0);
    });
    box.innerHTML = `${esc(tr("Total"))} <b>${fmt(tot, true)}</b>`;
  }
  if (q("#addSplit")) {
    q("#addSplit").onclick = () => { readSplits(); splits.push({ account_id: "", amount: "", amount_mode: "fixed" }); drawSplits();
      const r = qa("#billSplits select.sp-acct"); if (r.length) r[r.length - 1].focus(); };
    q("#dlgBody [name=amount]").addEventListener("input", splitTotal);
    drawSplits();
  }
  if (xb) { ks.value = "transfer"; ks.disabled = true; }
  const upd = () => {
    const x = q("#dlgBody .xfer"); if (x) x.style.display = ks.value === "transfer" ? "" : "none";
    q("#dlgBody .catf").style.display = ks.value === "transfer" ? "none" : "";
    q("#dlgBody .paycheckf").style.display = ks.value === "deposit" ? "" : "none";
    const sp = q("#dlgBody .splitf"); if (sp) sp.style.display = ks.value === "deposit" ? "" : "none";
    // A transfer between two currencies: what usually arrives.
    const xc = q("#dlgBody .xcur");
    if (xc) {
      const fa = S.accounts.find(a => a.id == q("#dlgBody [name=account_id]").value);
      const ta = S.accounts.find(a => a.id == q("#dlgBody [name=to_account_id]").value);
      const two = ks.value === "transfer" && fa && ta && fa.currency !== ta.currency;
      xc.style.display = two ? "" : "none";
      if (two) q("#xcurLabel").textContent = `${tr("Usually arrives")} (${ta.currency})`;
      else q("#dlgBody [name=received]").value = "";
    }
    payLabel();
  };
  ["account_id", "to_account_id"].forEach(n => { const s = q(`#dlgBody [name=${n}]`); if (s) s.addEventListener("change", () => upd()); });
  const mainSel = q("#dlgBody [name=account_id]");
  if (mainSel && q("#billSplits")) mainSel.addEventListener("change", () => { readSplits(); drawSplits(); });
  // A paycheck's amount is its take-home pay (also as the average, when it varies).
  const payLabel = () => {
    const pc = q("#dlgBody [name=paycheck]").checked && ks.value === "deposit";
    const varies = (q("#dlgBody [name=amount_mode]:checked") || {}).value === "average";
    q("#amtLabel").textContent = varies ? (pc ? "Starting take-home estimate (optional)" : "Starting estimate (optional)") : (pc ? "Take-home pay" : "Amount");
  };
  q("#dlgBody [name=paycheck]").addEventListener("change", payLabel);
  // Says whether this item will count in the Budget's expected income or planned
  // spending: deposits need an income category, bills a spending one.
  const hint = () => {
    const h = q("#budgetHint"); if (!h) return;
    const k = ks.value, cid = +q("#dlgBody [name=category_id]").value;
    const c = S.cats.find(x => x.id === cid);
    const want = k === "deposit" ? "income" : "expense";
    const varies = (q("#dlgBody [name=amount_mode]:checked") || {}).value === "average";
    const noEst = varies && !(parseAmount(q("#dlgBody [name=amount]").value) > 0) && !hist.length;
    if (k === "transfer" || k === "loan") { h.textContent = ""; return; }
    if (c && c.kind === want) {
      h.textContent = `Counts toward ${k === "deposit" ? "expected income" : "planned spending"} in your Budget` +
        (noEst ? " once the first one is entered (or give a starting estimate)." : ".");
    } else {
      h.textContent = k === "deposit"
        ? "Pick an income category (for example Investment Income : Interest) to count it in your Budget's expected income."
        : "Pick a spending category to count it in your Budget's planned spending.";
    }
  };
  ks.onchange = () => { upd(); hint(); }; upd();
  wireAutoFields();
  // "Last day of the month" only makes sense for schedules counted in months; ticking it
  // moves the next date to the end of its month.
  const fq = q("#dlgBody [name=frequency]"), ld = q("#dlgBody [name=last_day]"), nd = q("#dlgBody [name=next_date]");
  const lastDayRow = () => { q("#dlgBody .lastday").style.display = MONTH_BASED.includes(fq.value) ? "" : "none"; };
  fq.addEventListener("change", lastDayRow); lastDayRow();
  ld.addEventListener("change", () => {
    if (!ld.checked || !nd.value) return;
    const [y, m] = nd.value.split("-").map(Number);
    nd.value = `${y}-${String(m).padStart(2, "0")}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`;
  });
  q("#dlgBody [name=category_id]").addEventListener("change", hint);
  q("#dlgBody [name=amount]").addEventListener("input", hint);
  qa("#dlgBody [name=amount_mode]").forEach(r => r.onchange = () => {
    const v = r.value === "average";
    payLabel();
    q("#avgNote").textContent = v ? "Used until the first payment is recorded; after that the average takes over." : "";
    hint();
  });
  hint();
  return p;
}

// Automatic items: they happen by themselves (autopay, automatic transfer, direct
// deposit). Marked with ⟳; optionally MoneyThistle records them on their date.
function autoFields(b) {
  return `<div class="wide auto-box" style="grid-column:1/-1">
    <label class="check"><input type="checkbox" name="auto" ${b.auto ? "checked" : ""}> It happens automatically <span class="small muted">(autopay, automatic transfer, direct deposit)</span></label>
    <label class="check" style="margin-left:24px"><input type="checkbox" name="auto_enter" ${b.auto_enter ? "checked" : ""}> Record it in the register for me on its date</label>
    <div class="small muted" style="margin-left:24px">Entered at the expected amount (an amount that varies uses its average); change it in the register if the real amount differs.</div></div>`;
}
function wireAutoFields() {
  const a = q("#dlgBody [name=auto]"), e = q("#dlgBody [name=auto_enter]");
  if (!a || !e) return;
  const upd = () => { e.disabled = !a.checked; if (!a.checked) e.checked = false; e.closest("label").style.opacity = a.checked ? "" : ".5"; };
  a.addEventListener("change", upd); upd();
}
function autoPill(b) {
  if (!b.auto) return "";
  return ` <span class="pill auto" title="${b.auto_enter ? "Happens automatically; MoneyThistle records it on its date" : "Happens automatically (you still record it)"}"><span aria-hidden="true">⟳</span> automatic${b.auto_enter ? ", recorded for you" : ""}</span>`;
}

// How often, saying so when it falls on the last day of the month.
const MONTH_BASED = ["Monthly", "Every other month", "Every three months", "Twice a year", "Yearly", "Every other year"];
function freqLabel(b) { return (b.frequency || "") + (b.last_day ? ", last day of the month" : ""); }

// Scheduled items at a glance: money in (green, +), money out (orange, −), moved
// between your own accounts (blue, ⇄), as a tag and a colored edge on the row. The
// symbols carry the meaning too, for anyone who can't tell the colors apart.
const KIND_LOOK = {
  in: { cls: "green", sym: "+", tip: "Money coming in" },
  out: { cls: "out", sym: "−", tip: "Money going out" },
  move: { cls: "move", sym: "⇄", tip: "Moving money between your accounts" },
};
function kindOf(b) { return b.kind === "deposit" ? "in" : (b.kind === "transfer" ? "move" : "out"); }
function kindPill(b, labelOverride) {
  const label = labelOverride || (b.kind === "loan" ? "loan payment" : b.kind);
  const k = KIND_LOOK[kindOf(b)];
  return `<span class="pill ${k.cls}" title="${k.tip}"><span class="ksym" aria-hidden="true">${k.sym}</span> ${esc(label)}</span>`;
}
// Just the symbol, for short lists (Home): same colors and meaning.
function kindSym(b) {
  const k = KIND_LOOK[kindOf(b)];
  return `<span class="pill ${k.cls} ksym-only" title="${k.tip}" aria-label="${k.tip}">${k.sym}</span>`;
}

// "≈" marks amounts that are an average of past payments, not a fixed amount.
function billAmount(b, signed) {
  if (b.splits && b.splits.length) {
    // (one account per line, each kept on its line)
    const part = (name, amt, avg) => `<div style="white-space:nowrap"><span translate="no">${esc(name)}</span> ${avg ? "≈ " : ""}${fmt(amt, true)}</div>`;
    return `${fmt(b.split_total)}<div class="small muted">${part(b.account_name, b.amount, b.amount_mode === "average")}${
      b.splits.map(x => part(x.account_name, x.amount, x.amount_mode === "average")).join("")}</div>`;
  }
  const v = b.kind === "deposit" || b.x_dir === "in" ? b.amount : -b.amount;
  if (b.amount_mode !== "average") return fmt(v);
  const n = (b.history || []).length;
  return `<span title="${n ? `Average of the last ${n} payment${n === 1 ? "" : "s"}` : "Starting estimate"}">≈ ${b.amount ? fmt(v) : '<span class="muted">?</span>'}</span>`;
}

async function enterBill(id, occ) {
  if (!occ) { const all = await GET("/api/bills"); occ = all.bills.find(b => b.id == id); }
  if (occ.kind === "loan") return payLoan(occ.loan_account_id, occ);
  const payAcc = S.accounts.find(a => a.id == occ.account_id);
  if (occ.kind === "deposit" && occ.paycheck && payAcc && !occ._sh && !occ._env) return enterPaycheck(id, occ, payAcc);
  // A card kept by statement balance: its statement can go in with the payment.
  const stmt = occ.card_account_id && occ.card_mode === "statement";
  // A transfer between accounts in two currencies: what arrived this time.
  const toAcc = occ.kind === "transfer" ? S.accounts.find(a => a.id == occ.to_account_id) : null;
  const twoCur = toAcc && payAcc && toAcc.currency !== payAcc.currency;
  const p = dialog("Record " + (occ.payee || "this item"), `<p>This adds the transaction to <b>${esc(occ.account_name)}</b> and moves the schedule to the next date.</p>
    ${twoCur ? `<div class="notice" style="margin:0 0 10px"><div class="form"><div><label class="req">${esc(tr("Amount received"))} (${toAcc.currency})</label>
      <input name="received" class="num" placeholder="0.00" value="${occ.received ? dollars(occ.received) : guessReceived(payAcc.currency, toAcc.currency, occ.amount || 0)}"></div></div>
      <div class="small muted" style="margin-top:4px">${esc(tr(`${payAcc.name} and ${toAcc.name} are in different currencies: enter what actually arrived in ${toAcc.name}.`))}</div></div>` : ""}
    ${stmt ? `<div class="notice" style="margin:0 0 10px"><div class="form">
      <div><label>Statement balance <span class="muted">(from this statement)</span></label><input name="statement_balance" class="num" placeholder="${occ.card_owed ? dollars(occ.card_owed) : "0.00"}"></div>
      <div><label>Statement closing date</label><input type="date" name="statement_date" value=""></div></div>
      <div class="small muted" style="margin-top:4px">Fill it in and the card first owes this amount (on the closing date${occ.statement_day ? `, the ${ordinal(occ.statement_day)}` : ", or the payment date when empty"}), then this payment brings it down. Leave it empty if you've already entered this statement${occ.last_statement ? ` (last one: ${niceDate(occ.last_statement.date)}, ${fmt(occ.last_statement.balance, true)})` : ""}.</div></div>` : ""}
    <div class="form"><div><label>Date</label><input type="date" name="date" value="${occ.date || occ.next_date}"></div>
    <div><label>${(occ.splits || []).length ? esc(tr("Into")) + ` <span translate="no">${esc(occ.account_name)}</span>` : "Amount" + (occ.amount_mode === "average" ? " this time" : "")}</label><input name="amount" class="num" value="${occ.amount ? dollars(occ.amount) : ""}" placeholder="0.00"></div>
    ${splitInputs(occ)}
    <div><label>Number</label><input name="number"></div></div>
    ${occ.amount_mode === "average" ? `<p class="small muted">This amount varies. ${(occ.history || []).length
      ? `Filled in with the average of the last ${occ.history.length} (${occ.history.map(h => fmt(h.amount, true)).join(", ")}).`
      : (occ.amount ? "Filled in with your starting estimate." : "")} Type what you actually paid; it goes into the average for next time.</p>` : ""}
    ${heldFilesHtml("ba")}`, [{ label: "Cancel" }, {
    label: "Record", cls: "primary", action: async root => {
      const f = formData(root);
      if (twoCur && !(parseAmount(f.received) > 0)) { const e = new Error(tr("Enter the amount received")); e.field = "received"; throw e; }
      takeSplits(f);
      const r = await api("POST", `/api/bills/${id}/enter`, f);
      if (twoCur) keepRate(payAcc.currency, toAcc.currency, Math.round((parseAmount(f.amount) || 0) * 100), f.received);
      const n = await held.send(r && r.id);
      toast("Recorded" + filesNote(n)); render();
    }
  }]);
  const held = holdFiles("ba", q("#dlgBody"));
  dateHint(q("#dlgBody [name=date]"));
  // A card payment: one tap for the last statement's balance.
  const payTo = occ.card_account_id || (occ.kind === "transfer" && !occ.x_link_id ? occ.to_account_id : null);
  if (payTo) {
    const amtIn = q("#dlgBody [name=amount]"), box = document.createElement("div");
    box.style.marginTop = "4px"; amtIn.parentNode.appendChild(box);
    statementButton(payTo, box, left => { amtIn.value = dollars(left); amtIn.dispatchEvent(new Event("input")); });
  }
  if (stmt) {
    // Paying the statement: the amount follows the statement balance until it's changed by hand.
    const sb = q("#dlgBody [name=statement_balance]"), amt = q("#dlgBody [name=amount]");
    let touched = false;
    amt.addEventListener("input", () => { touched = true; });
    sb.addEventListener("input", () => { if (!touched) amt.value = sb.value; });
  }
  return p;
}

// A deposit into more than one account: what reached each of the others this time (filled
// in with what's expected: its set amount or its average).
function splitInputs(occ) {
  return (occ.splits || []).map(x => `<div><label>${esc(tr("Into"))} <span translate="no">${esc(x.account_name)}</span></label>
    <input name="split_${x.id}" class="num" value="${x.amount ? dollars(x.amount) : ""}" placeholder="0.00"
      ${x.amount_mode === "average" ? `title="${esc(tr("Average so far"))}"` : ""}></div>`).join("");
}
function takeSplits(f) {
  const out = {};
  Object.keys(f).filter(k => /^split_\d+$/.test(k)).forEach(k => { out[k.slice(6)] = f[k]; delete f[k]; });
  if (Object.keys(out).length) f.splits = out;
  return out;
}

// A scheduled paycheck coming in: just the take-home pay (the paystub can follow later),
// or the paystub now (gross pay and deductions, started from the last one).
function enterPaycheck(id, occ, acc) {
  const date = occ.date || occ.next_date;
  const p = dialog("Paycheck from " + (occ.payee || "your employer"), `<p>Into <b>${esc(occ.account_name || acc.name)}</b>. The schedule then moves to the next payday.</p>
    <div class="form"><div><label>Pay date</label><input type="date" name="date" value="${esc(date)}"></div>
      <div><label>${(occ.splits || []).length ? esc(tr("Into")) + ` <span translate="no">${esc(occ.account_name || acc.name)}</span>` : "Take-home pay" + (occ.amount_mode === "average" ? " this time" : "")}</label><input name="amount" class="num" value="${occ.amount ? dollars(occ.amount) : ""}" placeholder="0.00"></div>
      ${splitInputs(occ)}</div>
    <p class="small muted">Only have what reached your bank? Record the take-home pay now; you can add the paystub details (gross pay, taxes and
      deductions) to the entry in the register any time.</p>
    ${heldFilesHtml("pc")}`,
    [{ label: "Cancel" },
     { label: "Fill in the paystub…", action: async root => {
       const f = formData(root);
       const cents = Math.round((parseAmount(f.amount) || 0) * 100);
       const files = held.take();
       const parts = takeSplits(f);
       const splits = (occ.splits || []).map(x => ({ account_id: x.account_id, amount: Math.round((parseAmount(parts[x.id]) || 0) * 100) })).filter(x => x.amount);
       setTimeout(() => paystubDialog(acc, null, () => render(), { bill_id: id, employer: occ.payee, date: f.date, net: cents || null, files,
         splits: (occ.splits || []).length ? splits : null }), 0);
     } },
     { label: "Record take-home only", cls: "primary", action: async root => {
       const f = formData(root);
       if (!(parseAmount(f.amount) > 0)) { const e = new Error("Enter the take-home pay"); e.field = "amount"; throw e; }
       const parts = takeSplits(f);
       const r = await api("POST", `/api/bills/${id}/enter`, { date: f.date, amount: f.amount, take_home: true, splits: parts });
       const n = await held.send(r && r.id);
       toast("Paycheck recorded: take-home pay" + filesNote(n)); render();
     } }]);
  const held = holdFiles("pc", q("#dlgBody"));
  return p;
}

// Bills & Deposits: "Coming up" (grouped by account) and "All scheduled items"
// (one sortable, filterable list). Accounts shared into this environment with their
// bills appear in both, marked as shared.
const billView = { days: +localStorage.getItem("hl-bill-days") || 31, q: "", kind: "", account: "", freq: "", sort: "next_date", dir: 1 };

async function loadBillData(days) {
  const own = await GET("/api/bills?days=" + days);
  // All my environments: the others' items too (each acted on in its own environment);
  // accounts shared between my environments then show once, where they live.
  const all = reportScopeAll();
  const mine = new Set(scopeEnvs());
  const others = all ? await Promise.all(S.me.envs.filter(e => e.id !== S.env && mine.has(e.id)).map(e =>
    api("GET", "/api/bills?days=" + days, undefined, { env_id: e.id }).then(d => ({ e, d })).catch(() => ({ e, d: { bills: [], upcoming: [], statements_due: [] } })))) : [];
  const shares = (await GET("/api/shares/incoming").catch(() => [])).filter(a => a.include_bills && !(all && mine.has(a.env_id)));
  const sharedData = await Promise.all(shares.map(sh => api("GET", "/api/bills?days=" + days, undefined, sh)
    .then(d => ({ sh, d })).catch(() => ({ sh, d: { bills: [], upcoming: [] } }))));
  const tag = (x, sh) => ({ ...x, _sh: sh || null, _key: sh ? "s" + sh.share_id : "a" + x.account_id,
    _acct: sh ? `${sh.name} · shared by ${sh.shared_by}` : x.account_name });
  // A transfer between two shared accounts comes back through both shares: keep it once,
  // under the account the money leaves from.
  const pickShared = list => {
    const best = new Map();
    for (const { sh, d } of sharedData) for (const x of d[list]) {
      const key = `${sh.env_id}:${x.id}:${x.date || ""}`;
      const prev = best.get(key);
      if (!prev || (x.account_id === sh.id && prev.sh.id !== prev.x.account_id)) best.set(key, { sh, x });
    }
    return [...best.values()].map(({ sh, x }) => tag(x, sh));
  };
  const here = all ? ((S.me.envs.find(e => e.id === S.env) || {}).name || "") : "";
  const tagEnv = (x, e) => ({ ...x, _env: e, env_id: e.id, env_name: e.name, _key: `e${e.id}-a${x.account_id}`, _acct: `${x.account_name} · ${e.name}` });
  const hereTag = x => all ? { ...tag(x), env_id: S.env, env_name: here, _acct: `${x.account_name} · ${here}` } : tag(x);
  // Items kept in another of my environments that pay an account here (a card here paid from
  // Household's checking): shown with that environment, acted on there.
  const rel = own.related || { bills: [], upcoming: [] };
  const related = list => rel[list].filter(x => !(all && mine.has(x.from_env.id)))
    .map(x => ({ ...tagEnv(x, x.from_env), _key: `e${x.from_env.id}-a${x.account_id}` }));
  return {
    bills: own.bills.map(hereTag).concat(related("bills"), pickShared("bills"), ...others.map(({ e, d }) => d.bills.map(b => tagEnv(b, e)))),
    upcoming: own.upcoming.map(hereTag).concat(related("upcoming"), pickShared("upcoming"), ...others.map(({ e, d }) => d.upcoming.map(u => tagEnv(u, e))))
      .sort((a, b) => (a.date > b.date) - (a.date < b.date)),
    statements_due: (own.statements_due || []).concat(...others.map(({ e, d }) => (d.statements_due || []).map(x => ({ ...x, env_id: e.id, env_name: e.name })))),
  };
}
// May this item be recorded or changed from here? (Shared ones only when every account
// it touches is shared with entering allowed.)
function billEditable(b) {
  if (b._env) return ["owner", "editor"].includes((S.me.envs.find(e => e.id === b._env.id) || {}).role);
  return canEdit() && (!b._sh || b.share_editable !== false && b._sh.can_edit);
}

// Open, record or skip an item, whether it's this environment's or a shared account's.
async function billOpen(b) {
  if (b._env) { await goEnv(b._env.id); b = { ...b, _env: null }; }
  if (b._sh) {
    if (!billEditable(b)) {
      toast(b._sh.can_edit ? `View only: it also moves money in an account ${b._sh.shared_by} hasn't shared with you for entering`
        : `View only: ${b._sh.shared_by} manages this one`, true);
      return;
    }
    if (b.kind === "loan") { toast(`Loan details are changed in ${b._sh.shared_by}'s environment; you can record its payments here`, true); return; }
    return withShare(b._sh, () => editBill(b));
  }
  if (b.kind === "loan") { const a = S.accounts.find(x => x.id == b.loan_account_id); if (a) return editLoan(a); }
  return editBill(b);
}
async function billEnter(u) {
  if (u._env) { await goEnv(u._env.id); u = { ...u, _env: null }; }
  return u._sh ? withShare(u._sh, () => enterBill(u.id, u)) : enterBill(u.id, u);
}
async function billSkip(u) {
  try { await api("POST", `/api/bills/${u.id}/skip`, {}, u._sh || (u._env ? { env_id: u._env.id } : undefined)); toast("Skipped to the next date"); render(); }
  catch (e) { toast(e.message, true); }
}
function billWhat(b) {
  if (b.card_account_id) return "Card payment to " + (b.to_account_name || "") + (b.pay_full ? " (full balance)" : "") + " · set in the card's details";
  if (b.kind === "transfer") return (b.x_dir === "in" ? "Transfer from " : "Transfer to ") + (b.to_account_name || "");
  if (b.kind === "loan") return "Loan payment: " + (b.to_account_name || "") + " (principal, interest, escrow)";
  return b.category_label || "";
}

async function renderBills(sub) {
  await loadBasics();
  const tab = sub === "all" ? "all" : "upcoming";
  const data = await loadBillData(tab === "all" ? 31 : billView.days);
  const canNew = canEdit();
  view().innerHTML = `<div class="pagehead"><h1>Bills &amp; Deposits</h1>${scopeSwitch()}</div>
  ${scopeNote("new items are added to " + esc((S.me.envs.find(e => e.id === S.env) || {}).name || "this environment"))}
  <div class="toolbar">
    <div class="subtabs"><a href="#/bills" class="${tab === "upcoming" ? "on" : ""}">Coming up</a><a href="#/bills/all" class="${tab === "all" ? "on" : ""}">All scheduled items <span class="pill">${data.bills.length}</span></a></div>
    <span class="grow"></span>
    ${canNew ? `<button class="primary" id="nb">New bill</button><button id="nd">New deposit</button><button id="nt">New transfer</button>` : ""}</div>
  ${S.accounts.length || data.bills.length ? "" : `<div class="notice">Add an account first, then schedule bills for it.</div>`}
  ${statementsDueNote(data.statements_due)}
  ${data.bills.length ? `<div class="small muted kind-legend">${kindPill({ kind: "deposit" })} money in
    ${kindPill({ kind: "bill" })} money out ${kindPill({ kind: "transfer" })} between your accounts</div>` : ""}
  <div id="billBody"></div>`;
  if (canNew) {
    q("#nb").onclick = () => editBill(null, "bill");
    q("#nd").onclick = () => editBill(null, "deposit");
    q("#nt").onclick = () => editBill(null, "transfer");
  }
  wireStatementsDue();
  if (tab === "upcoming") drawUpcoming(data); else drawAllBills(data);
}

function drawUpcoming(data) {
  const days = billView.days;
  // One card per account (own accounts first, then shared ones), in date order inside.
  const groups = new Map();
  for (const u of data.upcoming) {
    if (!groups.has(u._key)) groups.set(u._key, { name: u._acct, sh: u._sh, items: [] });
    groups.get(u._key).items.push(u);
  }
  const order = [...groups.values()].sort((a, b) => (!!a.sh - !!b.sh) || a.name.localeCompare(b.name));
  const total = g => g.items.reduce((s, u) => s + (u.kind === "deposit" ? u.amount : -u.amount), 0);
  q("#billBody").innerHTML = `<div class="toolbar small">Show the next
      ${[14, 31, 60, 90].map(n => `<button class="small ${days === n ? "primary" : ""}" data-days="${n}">${n} days</button>`).join("")}</div>
    <div class="grid bill-groups">${order.map(g => `<div class="card flush">
      <div style="padding:12px 14px 4px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <h2 style="margin:0">${esc(g.name)}</h2>${g.sh ? `<span class="pill plain">shared</span>${g.sh.can_edit ? "" : '<span class="pill">view only</span>'}` : ""}
        <span style="flex:1"></span><span class="small muted">net ${fmt(total(g))}</span></div>
      <div class="scrollx"><table>${g.items.map((u, i) => `<tr class="${u.overdue ? "overdue " : ""}k-${kindOf(u)}">
        <td class="small" style="white-space:nowrap">${niceDate(u.date)} ${u.overdue ? '<span class="pill red">Overdue</span>' : (u.date === todayISO() ? '<span class="pill amber">Today</span>' : "")}</td>
        <td class="click" data-open="${g.items === null ? "" : i}" data-g="${esc(u._key)}">${esc(u.payee || "Transfer")} ${kindPill(u)}${autoPill(u)}
          <div class="small muted">${esc(billWhat(u))}${u.frequency ? " · " + esc(freqLabel(u)) : ""}</div></td>
        <td class="num">${billAmount(u)}</td>
        <td class="num" style="white-space:nowrap">${u.first && /^https?:\/\//i.test(u.pay_url || "") ? `<a class="btn small" href="${esc(u.pay_url)}" target="_blank" rel="noopener noreferrer" title="Open the card's website to pay">Pay online ↗</a> ` : ""}${u.first && billEditable(u) ? `<button class="small primary" data-enter="${esc(u._key)}:${i}">Enter</button> <button class="small" data-skip="${esc(u._key)}:${i}">Skip</button>` : (u.first ? (u._sh ? '<span class="small muted" title="Recorded in its own environment">view only</span>' : "") : '<span class="small muted">later</span>')}</td></tr>`).join("")}
      </table></div></div>`).join("") || `<div class="card"><div class="empty">Nothing due in the next ${days} days.
        ${data.bills.length ? `<a href="#/bills/all">See all scheduled items</a>` : "Schedule a bill or deposit with the buttons above."}</div></div>`}</div>`;
  const pick = v => { const [key, i] = v.split(":"); return groups.get(key).items[+i]; };
  qa("[data-days]").forEach(b => b.onclick = () => { billView.days = +b.dataset.days; localStorage.setItem("hl-bill-days", billView.days); render(); });
  qa("[data-enter]").forEach(b => b.onclick = () => billEnter(pick(b.dataset.enter)));
  qa("[data-skip]").forEach(b => b.onclick = () => billSkip(pick(b.dataset.skip)));
  qa("[data-open]").forEach(c => c.onclick = () => billOpen(groups.get(c.dataset.g).items[+c.dataset.open]));
}

function drawAllBills(data) {
  const bills = data.bills;
  const accounts = [...new Map(bills.map(b => [b._key, b._acct])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const freqs = [...new Set(bills.map(b => b.frequency))];
  q("#billBody").innerHTML = `<div class="card">
    <div class="toolbar" style="margin:0">
      <input id="bq" placeholder="Search payee, category, memo…" value="${esc(billView.q)}" style="flex:1;min-width:160px">
      <select id="bkind"><option value="">All types</option>${["bill", "deposit", "transfer", "loan"].map(k => `<option value="${k}" ${billView.kind === k ? "selected" : ""}>${k === "loan" ? "Loan payments" : k[0].toUpperCase() + k.slice(1) + "s"}</option>`).join("")}<option value="auto" ${billView.kind === "auto" ? "selected" : ""}>⟳ Automatic</option></select>
      <select id="bacct"><option value="">All accounts</option>${accounts.map(([k, n]) => `<option value="${esc(k)}" ${billView.account === k ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
      <select id="bfreq"><option value="">Any frequency</option>${freqs.map(f => `<option ${billView.freq === f ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>
      <button class="small" id="bclear">Clear</button></div></div>
  <div class="card flush" style="margin-top:12px"><div class="scrollx" id="allTable"></div></div>`;
  const cols = [["payee", "Payee"], ["kind", "Type"], ["_acct", "Account"], ["frequency", "How often"], ["next_date", "Next"], ["amount", "Amount"]];
  const draw = () => {
    const s = billView, needle = s.q.trim().toLowerCase();
    let rows = bills.filter(b => (!s.kind || (s.kind === "auto" ? b.auto : b.kind === s.kind)) && (!s.account || b._key === s.account) && (!s.freq || b.frequency === s.freq) &&
      (!needle || [b.payee, b.category_label, b.memo, b._acct, b.to_account_name].some(x => (x || "").toLowerCase().includes(needle))));
    const val = b => s.sort === "amount" ? (b.kind === "deposit" ? b.amount : -b.amount) : String(b[s.sort] || "").toLowerCase();
    rows.sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * s.dir);
    q("#allTable").innerHTML = `<table><tr>${cols.map(([k, l]) => `<th class="sortable ${k === "amount" ? "num" : ""}" data-sort="${k}">${l}${s.sort === k ? (s.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr>
      ${rows.map((b, i) => `<tr class="click k-${kindOf(b)}" data-row="${i}"><td>${esc(b.payee || "Transfer")}<div class="small muted">${esc(billWhat(b))}</div></td>
        <td>${kindPill(b)}${autoPill(b)}${b.amount_mode === "average" ? ' <span class="pill" title="Amount varies: average of past payments">≈ avg</span>' : ""}</td>
        <td class="small">${esc(b._acct)}${b._sh ? ' <span class="pill plain">shared</span>' : ""}</td>
        <td class="small">${esc(freqLabel(b))}</td><td class="small" style="white-space:nowrap">${niceDate(b.next_date)}</td><td class="num">${billAmount(b)}</td></tr>`).join("")}</table>
      ${rows.length ? "" : `<div class="empty">${bills.length ? "Nothing matches these filters." : "No bills or deposits scheduled yet."}</div>`}
      <div class="small muted" style="padding:8px 12px">${rows.length} of ${bills.length} · click a column to sort, a row to change it</div>`;
    qa("[data-sort]").forEach(h => h.onclick = () => { const k = h.dataset.sort; billView.dir = billView.sort === k ? -billView.dir : 1; billView.sort = k; draw(); });
    qa("[data-row]").forEach(r => r.onclick = () => billOpen(rows[+r.dataset.row]));
  };
  q("#bq").oninput = e => { billView.q = e.target.value; draw(); };
  q("#bkind").onchange = e => { billView.kind = e.target.value; draw(); };
  q("#bacct").onchange = e => { billView.account = e.target.value; draw(); };
  q("#bfreq").onchange = e => { billView.freq = e.target.value; draw(); };
  q("#bclear").onclick = () => { Object.assign(billView, { q: "", kind: "", account: "", freq: "" }); drawAllBills(data); };
  draw();
}
// ---------- BUDGET ----------
let budgetMonth = null;
async function renderBudget() {
  await loadBasics();
  budgetMonth = budgetMonth || todayISO().slice(0, 7);
  const b = await GET("/api/budget?month=" + budgetMonth + scopeQS());
  if (b.mode === "schedule") return renderScheduleBudget(b);
  const ro = !!b.combined;   // all environments together: for looking; amounts are set in each one
  const dayFrac = b.days_in_month ? b.day_of_month / b.days_in_month : null;
  const section = (kind, title) => {
    const rows = b.rows.filter(r => r.kind === kind);
    return `<div class="card flush"><div style="padding:12px 14px 4px"><h2>${title}</h2></div><table>
      <tr><th>Category</th><th class="num">Each month</th><th class="num">Actual</th><th style="width:30%"></th><th class="num">${kind === "expense" ? "Left" : "To come"}</th><th></th></tr>
      ${rows.map(r => `<tr><td>${esc(r.name)}${r.loan ? '<div class="small muted">principal, interest and escrow together</div>' : ""}</td><td class="num">${r.loan || ro ? `<span title="${ro ? `Set in ${esc((r.envs || []).join(" and "))}` : "Set by the loan's payment schedule"}">${fmt(r.budget, true)}</span>` : `<input class="num" data-b="${r.category_id}" value="${r.typed ? dollars(r.typed) : ""}"
          placeholder="${r.scheduled ? dollars(r.scheduled) : "0.00"}" aria-label="Each month for ${esc(r.name)}"${r.scheduled ? ` title="Leave empty to expect what's scheduled: ${esc(fmt(r.scheduled, true))}"` : ""}>`}
        ${r.from_schedule ? `<div class="small muted">from schedule</div>` : (r.typed && r.scheduled ? `<div class="small muted">scheduled ${fmt(r.scheduled, true)}</div>` : "")}</td>
        <td class="num">${fmt(r.actual, true)}${r.shared ? `<div class="small muted" title="Part of this comes from accounts shared with you">incl. ${fmt(r.shared, true)} shared</div>` : ""}</td><td>${budgetBar(r.actual, r.budget, kind === "expense" ? dayFrac : null)}</td>
        <td class="num">${fmt(r.budget - r.actual)}</td><td>${r.loan || ro ? "" : `<button class="small" data-rm="${r.category_id}" title="Take out of the budget">✕</button>`}</td></tr>`).join("")}
      </table>${rows.length ? "" : `<div class="empty">No ${kind} categories in the budget</div>`}</div>`;
  };
  const inBudget = new Set(b.rows.map(r => r.category_id));
  view().innerHTML = `<div class="pagehead"><h1>Budget</h1>${scopeSwitch()}${budgetStyleToggle("categories")}</div>
  ${scopeNote("lines with the same category add up. To change amounts, switch to one environment")}
  <div class="toolbar"><button id="prev">◀</button><b style="min-width:150px;text-align:center">${esc(monthName(b.month))}</b><button id="next">▶</button>
    <span class="grow"></span>${ro ? "" : `<select id="addcat"><option value="">Add a category to the budget…</option>
    ${S.cats.filter(c => c.kind !== "none" && !inBudget.has(c.id)).map(c => `<option value="${c.id}">${esc(catFull(c))}</option>`).join("")}</select>
    <button class="primary" id="saveb">Save budget</button>`}</div>
  <div class="grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:16px">
    <div class="card"><div class="muted small">Expected income</div><div class="big">${fmt(b.income_budget)}</div><div class="small muted">received ${fmt(b.income_actual, true)}</div></div>
    <div class="card"><div class="muted small">Planned spending</div><div class="big">${fmt(b.expense_budget)}</div><div class="small muted">spent ${fmt(b.expense_actual, true)}</div></div>
    <div class="card"><div class="muted small">Left over (plan)</div><div class="big">${fmt(b.income_budget - b.expense_budget)}</div><div class="small muted">so far ${fmt(b.income_actual - b.expense_actual, true)}</div></div>
  </div>
  <p class="small muted" style="margin-top:-6px">A line left empty expects what your Bills &amp; Deposits schedule holds for the month, entered or still to come; type an amount to set your own.${b.includes_shared ? " Includes accounts shared with you, counted under your categories of the same name." : ""}</p>
  ${aheadNote(b)}
  <div class="grid">${section("expense", "Spending")}${section("income", "Income")}
  ${(b.shared_outside || []).length ? `<div class="card flush"><div style="padding:12px 14px 4px"><h2>From shared accounts, not in your budget</h2>
    <p class="small muted" style="margin:4px 0 0">These were received or spent this month in accounts shared with you, but have no line in your budget, so the totals above leave them out.</p></div>
    <table><tr><th>Category</th><th>Kind</th><th class="num">This month</th><th></th></tr>
    ${b.shared_outside.map(r => `<tr><td>${esc(r.name)}</td><td class="small">${r.kind === "income" ? "Income" : "Spending"}</td><td class="num">${fmt(r.actual, true)}</td>
      <td class="num">${r.category_id ? `<button class="small" data-addb="${r.category_id}">Add to budget</button>` : '<span class="small muted" title="Add a category with this name under Categories to count it">no category with this name</span>'}</td></tr>`).join("")}</table></div>` : ""}</div>`;
  const shift = n => { const d = new Date(budgetMonth + "-01T00:00:00"); d.setMonth(d.getMonth() + n); budgetMonth = d.toISOString().slice(0, 7); renderBudget(); };
  q("#prev").onclick = () => shift(-1); q("#next").onclick = () => shift(1);
  wireBudgetStyle();
  if (q("#saveb")) q("#saveb").onclick = async () => {
    const items = qa("[data-b]").map(i => ({ category_id: +i.dataset.b, amount: i.value || "0" }));
    await api("PUT", "/api/budget", { items }); toast("Budget saved"); renderBudget();
  };
  const addToBudget = async id => {
    const c = S.cats.find(x => x.id === id);
    if (!c) return;
    await dialog("Add " + c.full_name, `<label>How much each month?</label><input name="amount" class="num" value="0.00">
      ${c.parent_id ? `<p class="small muted">A subcategory with an amount gets its own line; its spending no longer counts toward ${esc(catName(S.cats.find(x => x.id === c.parent_id)) || c.parent_name)}.</p>` : ""}`,
      [{ label: "Cancel" }, { label: "Add", cls: "primary", action: async root => {
        await api("PUT", "/api/budget", { items: [{ category_id: id, amount: formData(root).amount || "0", in_budget: true }] });
      } }]);
    renderBudget();
  };
  if (q("#addcat")) q("#addcat").onchange = e => { if (+e.target.value) addToBudget(+e.target.value); };
  qa("[data-addb]").forEach(x => x.onclick = () => addToBudget(+x.dataset.addb));
  qa("[data-rm]").forEach(x => x.onclick = async () => { await api("PUT", "/api/budget", { items: [{ category_id: +x.dataset.rm, amount: "0", in_budget: false }] }); renderBudget(); });
}

// Two ways to budget, chosen by each person: by categories (every purchase sorted),
// or by scheduled items (your Bills & Deposits: paychecks in; bills, loan and card
// payments out), for people who don't track every purchase.
function budgetStyleToggle(mode) {
  return `<span class="seg" role="group" aria-label="Budget by">
    <button class="small ${mode === "schedule" ? "on" : ""}" data-bstyle="schedule" aria-pressed="${mode === "schedule"}" title="Paychecks in; bills, loan and card payments out, from your Bills & Deposits">Scheduled items</button><button class="small ${mode === "categories" ? "on" : ""}" data-bstyle="categories" aria-pressed="${mode === "categories"}" title="Every purchase sorted into categories, each with its own amount">Categories</button></span>`;
}
function wireBudgetStyle() {
  qa("[data-bstyle]").forEach(btn => btn.onclick = async () => {
    try {
      S.ui = await api("PUT", "/api/settings", { budget_mode: btn.dataset.bstyle });
      renderBudget();
    } catch (e) { toast(e.message, true); }
  });
}
function shiftBudgetMonth(n) {
  const [y, m] = budgetMonth.split("-").map(Number);
  const d = new Date(y, m - 1 + n, 1);
  budgetMonth = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  renderBudget();
}
// Payments already recorded with next month's date (entered early, or dated wrong):
// they count in their own month, so say where they went.
function aheadNote(b) {
  const a = b.entered_ahead || [];
  if (!a.length) return "";
  return `<div class="notice" style="margin:0 0 14px"><b>Already recorded for a later month.</b> These count in the month of their date, not in ${esc(monthName(b.month))}:
    <ul style="margin:6px 0 6px 18px;padding:0">${a.map(r => `<li>${esc(r.payee)} · <b>${niceDate(r.date)}</b> · ${fmt(r.amount, true)}${r.account_name ? ` · ${esc(r.account_name)}` : ""}${r.shared ? "" : ` · <a href="#/accounts/${r.account_id}">open register</a>`}</li>`).join("")}</ul>
    <span class="small">If one was really paid this month, open it in the register and change its date (for a loan payment, click it and use "Save date").</span></div>`;
}
// Cards whose purchases are entered: this month's charges are pending, paid later
// through the card payment (which is what "Going out" counts).
function cardChargesCard(b) {
  const c = b.card_charges || [];
  if (!c.length) return "";
  return `<div class="card flush"><div style="padding:12px 14px 4px"><h2>Charged on cards (pending)</h2>
      <p class="small muted" style="margin:4px 0 0">Purchases entered on cards this month. They leave your bank only when the card is paid, so they're not added to "Going out"; the card payment is.</p></div>
    <div class="scrollx"><table><tr><th>Card</th><th class="num">Charged this month</th><th class="num">Owed now</th><th class="num">Credit left</th><th>Next payment</th></tr>
    ${c.map(r => `<tr class="k-out"><td>${r.shared ? esc(r.name) : `<a href="#/accounts/${r.account_id}">${esc(r.name)}</a>`}</td>
      <td class="num">${fmt(r.charged, true)}<div class="small muted">${r.count} entr${r.count === 1 ? "y" : "ies"}${r.credits ? ` · ${fmt(r.credits, true)} refunded` : ""}</div></td>
      <td class="num">${fmt(r.owed, true)}</td><td class="num">${r.available == null ? '<span class="muted">—</span>' : fmt(r.available, true)}</td>
      <td class="small">${r.next_payment_date ? `${niceDate(r.next_payment_date)} · ${r.next_payment ? fmt(r.next_payment, true) : '<span class="muted">amount not set yet</span>'}` : (r.due_day ? `due on the ${ordinal(r.due_day)} (not scheduled)` : '<span class="muted">not scheduled</span>')}</td></tr>`).join("")}
    </table></div></div>`;
}
function renderScheduleBudget(b) {
  const dayFrac = b.days_in_month ? b.day_of_month / b.days_in_month : null;
  const section = (side, title, note) => {
    const rows = b.rows.filter(r => r.side === side);
    if (!rows.length && side === "move") return "";
    return `<div class="card flush"><div style="padding:12px 14px 4px"><h2>${title}</h2>${note ? `<p class="small muted" style="margin:4px 0 0">${note}</p>` : ""}</div>
      <div class="scrollx"><table><tr><th>Item</th><th class="num">This month</th><th class="num">${side === "in" ? "Received" : "Paid"}</th><th style="width:26%"></th><th class="num">Still to come</th></tr>
      ${rows.map(r => { const it = r.item_kind === "transfer" && r.side === "out" ? { kind: "bill" } : { kind: r.item_kind }; return `<tr class="k-${kindOf(it)}"><td>${esc(r.name)} ${kindPill(it, r.item_kind === "transfer" && r.side === "out" ? "payment" : null)}${autoPill(r)}${r.amount_mode === "average" ? ' <span class="pill" title="Amount varies: average of past payments">≈ avg</span>' : ""}
          <div class="small muted">${esc(r.account_name)}${r.to_account_name ? (r.x_dir === "in" ? " ← " : " → ") + esc(r.to_account_name) : ""} · ${esc(freqLabel(r))}</div></td>
        <td class="num">${fmt(r.expected, true)}<div class="small muted">${r.entered + r.to_come} time${r.entered + r.to_come === 1 ? "" : "s"}</div></td>
        <td class="num">${fmt(r.actual, true)}${r.entered ? `<div class="small muted">${r.entered} entered</div>` : ""}</td>
        <td>${budgetBar(r.actual, r.expected, side === "out" ? dayFrac : null)}</td>
        <td class="num">${fmt(Math.max(0, r.expected - r.actual), true)}${r.to_come ? `<div class="small muted">${r.to_come} to come</div>` : ""}</td></tr>`; }).join("")}
      </table></div>${rows.length ? "" : `<div class="empty">Nothing scheduled this month. <a href="#/bills">Add bills and deposits</a>.</div>`}</div>`;
  };
  view().innerHTML = `<div class="pagehead"><h1>Budget</h1>${scopeSwitch()}${budgetStyleToggle("schedule")}</div>
  ${scopeNote("each item shows its environment")}
  <div class="toolbar"><button id="prev" aria-label="Previous month">◀</button><b style="min-width:150px;text-align:center">${esc(monthName(b.month))}</b><button id="next" aria-label="Next month">▶</button>
    <span class="grow"></span><a class="btn" href="#/bills">Bills &amp; Deposits</a></div>
  <div class="grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:16px">
    <div class="card"><div class="muted small">Coming in</div><div class="big">${fmt(b.income_budget)}</div><div class="small muted">received ${fmt(b.income_actual, true)}</div></div>
    <div class="card"><div class="muted small">Going out</div><div class="big">${fmt(b.expense_budget)}</div><div class="small muted">paid ${fmt(b.expense_actual, true)}</div></div>
    <div class="card"><div class="muted small">Left over</div><div class="big">${fmt(b.income_budget - b.expense_budget)}</div><div class="small muted">so far ${fmt(b.income_actual - b.expense_actual, true)}${b.moved_budget ? ` · ${fmt(b.moved_budget, true)} moved to your other accounts` : ""}</div></div>
  </div>
  <p class="small muted" style="margin-top:-6px">Built from your Bills &amp; Deposits: what each item comes to this month, counting the ones already entered and those still to come.
    Card purchases aren't counted one by one; the card payment is. "Paid" counts what you enter from the schedule, and register entries with the same account and payee.</p>
  ${aheadNote(b)}
  <div class="grid">${section("in", "Coming in")}${section("out", "Going out", "Bills, loan payments and credit card payments.")}
    ${cardChargesCard(b)}
    ${section("move", "Moved between your accounts", "Transfers to savings and the like: not spending, so they're left out of the totals above.")}</div>`;
  q("#prev").onclick = () => shiftBudgetMonth(-1); q("#next").onclick = () => shiftBudgetMonth(1);
  wireBudgetStyle();
}

// ---------- REPORTS ----------
let reportState = { kind: "spending", range: "this-month" };
function rangeDates(r) {
  const t = new Date(); const y = t.getFullYear(), m = t.getMonth();
  const iso = d => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
  if (r === "this-month") return [iso(new Date(y, m, 1)), iso(t)];
  if (r === "last-month") return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))];
  if (r === "this-year") return [iso(new Date(y, 0, 1)), iso(t)];
  if (r === "last-year") return [iso(new Date(y - 1, 0, 1)), iso(new Date(y - 1, 11, 31))];
  return [iso(new Date(y, m - 11, 1)), iso(t)];
}
// Home, Accounts, Bills & Deposits, Budget and Reports can show the environment in view,
// or every environment you belong to (your private accounts in Personal plus the shared
// ones in Household, say). One choice for all of them, remembered per browser. Changes
// are still made in an item's own environment: acting on one switches there.
// Which environments to show together: the one in view, plus any others ticked (say
// Personal and Household, leaving Business out).
function scopeEnvs() {
  const mine = ((S.me && S.me.envs) || []).map(e => e.id);
  let picked = null;
  try { picked = JSON.parse(localStorage.getItem("hl-scope-envs") || "null"); } catch (e) { picked = null; }
  if (!Array.isArray(picked)) picked = localStorage.getItem("hl-report-scope") === "all" ? mine : [];   // the earlier one-or-all switch
  return [S.env].concat(mine.filter(id => id !== S.env && picked.includes(id)));
}
function reportScopeAll() { return scopeEnvs().length > 1; }
function scopeQS() { return reportScopeAll() ? "&scope=all&envs=" + scopeEnvs().join(",") : ""; }
function scopeNames() { const ids = scopeEnvs(); return S.me.envs.filter(e => ids.includes(e.id)).map(e => e.name); }
function scopeSwitch() {
  const envs = (S.me && S.me.envs) || [];
  if (envs.length < 2) return "";
  const ids = scopeEnvs();
  const label = ids.length === 1 ? `${scopeNames()[0]} only` : (ids.length === envs.length ? "All my environments" : scopeNames().join(" + "));
  setTimeout(() => {
    if (S.envpickOpen) { S.envpickOpen = false; const d = q(".envpick"); if (d) d.open = true; }
    const save = (list, keep) => { localStorage.setItem("hl-scope-envs", JSON.stringify(list)); localStorage.removeItem("hl-report-scope"); S.envpickOpen = keep; render(); };
    qa("[data-scopeenv]").forEach(c => c.onchange = () => save(qa("[data-scopeenv]").filter(x => x.checked).map(x => +x.dataset.scopeenv), true));
    qa("[data-scopeall]").forEach(b => b.onclick = e => { e.preventDefault(); save(b.dataset.scopeall === "all" ? envs.map(x => x.id) : []); });
  }, 0);
  return `<details class="envpick noprint"><summary class="btn small" title="Which environments to show together">🗂 ${esc(label)} ▾</summary>
      <div class="envpick-menu"><div class="small muted" style="margin-bottom:4px">Show together:</div>
      ${envs.map(e => `<label class="check"><input type="checkbox" data-scopeenv="${e.id}" ${ids.includes(e.id) ? "checked" : ""} ${e.id === S.env ? "disabled" : ""}>
        ${esc(e.name)}${e.id === S.env ? ' <span class="small muted">(in view)</span>' : ""}</label>`).join("")}
      <div class="small" style="margin-top:6px"><a href="#" data-scopeall="all">All</a> · <a href="#" data-scopeall="none">Only ${esc((envs.find(e => e.id === S.env) || {}).name || "this one")}</a></div></div></details>`;
}
function scopeNote(what) {
  if (!reportScopeAll()) return "";
  return `<p class="small muted" style="margin:-6px 0 10px">Showing ${esc(scopeNames().join(" + "))} together${what ? `: ${what}` : ""}.
    Accounts shared between them count once.</p>`;
}
// Open something that lives in another of my environments: switch there first.
async function goEnv(envId) {
  if (!envId || +envId === S.env) return;
  S.env = +envId; S.shareCtx = null; localStorage.setItem("hl-env", S.env);
  await loadBasics();
  drawTopBar();
  toast("Switched to " + ((S.me.envs.find(e => e.id === S.env) || {}).name || "that environment"));
}
function envTag(x) {
  return reportScopeAll() && x && x.env_name ? ` <span class="pill plain env-tag" title="In ${esc(x.env_name)}">${esc(x.env_name)}</span>` : "";
}
function reportsHead(tabs, st) {
  return `<div class="head" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap"><h1 style="margin-right:auto">Reports</h1>${scopeSwitch()}</div>
    ${scopeNote("")}
    <div class="toolbar noprint">${tabs.map(([k, l]) => `<button data-kind="${k}" class="${st.kind === k ? "primary" : ""}">${l}</button>`).join("")}</div>`;
}
async function renderReports() {
  const st = reportState;
  const allEnvs = reportScopeAll(), sc = scopeQS();
  const tabs = [["spending", "Where the money goes"], ["income", "Where the money comes from"], ["monthly", "Income vs. spending"], ["networth", "Net worth over time"], ["forecast", "Looking ahead"], ["tax", "Taxes"]];
  let body = "";
  if (st.kind === "tax") {
    view().innerHTML = `${reportsHead(tabs, st)}<div id="taxBody"></div>`;
    await renderTaxReport(q("#taxBody"));
  } else if (st.kind === "spending" || st.kind === "income") {
    const [from, to] = rangeDates(st.range);
    const rows = await GET(`/api/reports/spending?kind=${st.kind === "spending" ? "expense" : "income"}&from=${from}&to=${to}${sc}`);
    const items = topItems(rows, 10);
    body = `<div class="toolbar">${[["this-month", "This month"], ["last-month", "Last month"], ["this-year", "This year"], ["last-year", "Last year"], ["12", "Last 12 months"]]
      .map(([k, l]) => `<button class="small ${st.range === k ? "primary" : ""}" data-range="${k}">${l}</button>`).join("")}
      <span class="small muted">${niceDate(from)} – ${niceDate(to)}</span></div>
      <div class="grid cols2"><div class="card"><div class="chartwrap">${donut(items, 230)}<div style="flex:1">${legend(items)}</div></div></div>
      <div class="card flush"><table><tr><th>Category</th><th class="num">Total</th><th class="num">Share</th></tr>
      ${rows.map(r => `<tr class="${r.id || allEnvs ? "click" : ""}" ${r.id ? `data-cat="${r.id}"` : (allEnvs ? `data-catname="${esc(r.name)}"` : "")}><td>${esc(r.name)}${r.includes_shared ? ' <span class="pill green" title="Includes shared accounts">+ shared</span>' : ""}</td><td class="num">${fmt(r.total)}</td><td class="num">${(r.total / Math.max(1, rows.reduce((s, x) => s + x.total, 0)) * 100).toFixed(1)}%</td></tr>`).join("")}
      </table>${rows.length ? "" : `<div class="empty">No transactions in this period</div>`}</div></div><div id="drill"></div>`;
    view().innerHTML = `${reportsHead(tabs, st)}${body}`;
    qa("[data-cat], [data-catname]").forEach(r => r.onclick = async () => {
      const tx = r.dataset.cat ? await GET(`/api/transactions?category=${r.dataset.cat}&from=${from}&to=${to}`)
        : await GET(`/api/reports/entries?name=${encodeURIComponent(r.dataset.catname)}&kind=${st.kind === "spending" ? "expense" : "income"}&from=${from}&to=${to}`);
      q("#drill").innerHTML = `<div class="card flush" style="margin-top:16px"><div style="padding:12px 14px 4px"><h2>${esc(r.cells[0].textContent)}: ${tx.length} transactions</h2></div>
        <table><tr><th>Date</th><th>Account</th><th>Payee</th><th>Category</th><th class="num">Amount</th></tr>
        ${tx.map(t => `<tr><td class="small">${niceDate(t.date)}</td><td class="small">${esc(t.account_name)}</td><td>${esc(t.payee)}</td><td class="small">${esc(t.category_label)}</td><td class="num">${fmt(t.amount, false, t)}</td></tr>`).join("")}</table></div>`;
    });
  } else if (st.kind === "monthly") {
    const rows = await GET("/api/reports/monthly?months=12" + sc);
    body = `<div class="card"><div class="small" style="margin-bottom:6px"><span class="pill" style="background:#1f8a8a;color:#fff">Income</span> <span class="pill" style="background:#e08a2e;color:#fff">Spending</span></div>${barChart(rows)}</div>
      <div class="card flush" style="margin-top:16px"><table><tr><th>Month</th><th class="num">Income</th><th class="num">Spending</th><th class="num">Difference</th></tr>
      ${rows.slice().reverse().map(r => `<tr><td>${esc(monthName(r.month))}</td><td class="num">${fmt(r.income)}</td><td class="num">${fmt(r.spending)}</td><td class="num">${fmt(r.net)}</td></tr>`).join("")}</table></div>`;
    view().innerHTML = `${reportsHead(tabs, st)}${body}`;
  } else if (st.kind === "forecast") {
    const days = st.fdays || 90;
    const f = await GET("/api/forecast?days=" + days + sc);
    // The accounts list under the chart: spending accounts plus anything with scheduled
    // activity, each with a box that shows or hides its line. Which are ticked is
    // remembered per environment; ids that no longer match are dropped, and nothing
    // valid left means the default (the money accounts you spend from).
    const shown = f.accounts.filter(a => a.has_activity || SPENDING_TYPES.includes(a.type));
    const allIds = shown.filter(a => SPENDING_TYPES.includes(a.type) && !a.liability).map(a => String(a.id));
    const valid = new Set(shown.map(a => String(a.id)));
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem("hl-forecast-" + (allEnvs ? "all" : S.env)) || "null"); } catch (e) { saved = null; }
    let chosen = (Array.isArray(saved) ? saved.map(String) : allIds).filter(id => valid.has(id));
    if (Array.isArray(saved) && saved.length && !chosen.length) chosen = allIds.slice();
    let showTotal = localStorage.getItem("hl-forecast-total") !== "0";
    // A scheduled item picked in the list stays marked while you change the period.
    const evKey = e => [e.date, e.payee, e.account_id, e.amount].join("|");
    const fStart = new Date(f.start + "T00:00:00");
    const dayOf = d => Math.round((new Date(d + "T00:00:00") - fStart) / 864e5);
    let marked = f.events.find(e => evKey(e) === st.fmark) || null;
    body = `<div class="toolbar">${[30, 60, 90, 180, 365].map(n => `<button class="small ${days === n ? "primary" : ""}" data-fdays="${n}">${n} days</button>`).join("")}
        <span class="small muted">From today's balances plus every scheduled bill, deposit, transfer and loan payment. Bills whose amount varies count at their average (≈).</span></div>
      <div class="card" id="fcCard"><div class="small muted" style="margin-bottom:6px">Tick accounts in the list below to show their lines. Click a scheduled item to mark its day on the chart.
          <a href="#" id="fReset" style="margin-left:10px">Reset accounts</a><a href="#" id="fUnmark" style="margin-left:10px">Clear mark</a></div>
        <div id="fcChart"></div></div>
      <div class="grid cols2" style="margin-top:16px">
        <div class="card flush"><table class="fc-accts"><tr><th class="fc-tick"><input type="checkbox" id="fAll" title="Show all or none" aria-label="Show all accounts"></th><th>Account</th><th class="num">Now</th><th class="num">Lowest</th><th class="num">In ${days} days</th></tr>
          ${shown.map(a => `<tr><td class="fc-tick"><input type="checkbox" id="fa-${a.id}" data-facct="${a.id}"></td>
            <td><label for="fa-${a.id}"><span class="fc-swatch" style="background:${fcColor(f, a.id)}"></span>${esc(a.name)}</label>${a.low < 0 ? ' <span class="pill red" title="Goes below zero in this period">below 0</span>' : ""}</td>
            <td class="num">${fmt(a.now)}</td><td class="num">${fmt(a.low)}<div class="small muted">${niceDate(a.low_date)}</div></td><td class="num">${fmt(a.end)}</td></tr>`).join("")}
          <tr class="fc-total"><td class="fc-tick"><input type="checkbox" id="fTotal" title="Show the total as a dashed line"></td>
            <td><label for="fTotal"><span class="fc-swatch dashed"></span>Total of the ticked accounts</label></td>
            <td class="num" id="fTotNow"></td><td class="num" id="fTotLow"></td><td class="num" id="fTotEnd"></td></tr></table></div>
        <div class="card flush"><div style="max-height:420px;overflow:auto"><table><tr><th>Date</th><th>What</th><th>Account</th><th class="num">Amount</th></tr>
          ${f.events.map((e, i) => `<tr class="click" data-ev="${i}" title="Click to mark this day on the chart"><td class="small">${niceDate(e.date)}${e.overdue ? ' <span class="pill red">overdue</span>' : ""}</td><td>${esc(e.payee)}</td>
            <td class="small">${esc(e.account_name)}</td><td class="num">${e.estimated ? "≈ " : ""}${fmt(e.amount)}</td></tr>`).join("")}</table>
          ${f.events.length ? "" : `<div class="empty">Nothing scheduled. Add bills and deposits to see what's coming.</div>`}</div></div>
      </div>`;
    view().innerHTML = `${reportsHead(tabs, st)}${body}`;
    // Ticking, unticking and marking only redraw the chart and totals: nothing is fetched again.
    const draw = () => {
      qa("[data-facct]").forEach(c => { c.checked = chosen.includes(String(c.dataset.facct)); });
      const all = q("#fAll");
      all.checked = chosen.length === shown.length && shown.length > 0;
      all.indeterminate = chosen.length > 0 && chosen.length < shown.length;
      q("#fReset").hidden = chosen.length === allIds.length && allIds.every(id => chosen.includes(id));
      q("#fUnmark").hidden = !marked;
      let mark = null;
      if (marked) {
        const touched = [marked.account_id, marked.to_account_id].filter(v => v != null).map(String);
        mark = { day: dayOf(marked.date), accounts: touched,
          label: `${niceDate(marked.date)} · ${marked.payee} ${marked.estimated ? "≈ " : ""}${fmt(marked.amount, true)}`,
          note: touched.some(id => chosen.includes(id)) ? "" : `${marked.account_name} isn't ticked` };
      }
      q("#fcChart").innerHTML = chosen.length
        ? forecastChart(f, chosen, { total: showTotal, mark, w: Math.max(560, Math.min(1500, q("#fcCard").clientWidth - 32)) })
        : `<div class="empty">Tick an account in the list below to see its forecast.</div>`;
      const accs = f.accounts.filter(a => chosen.includes(String(a.id)));
      const tot = Array.from({ length: f.days + 1 }, (_, i) => accs.reduce((s, a) => s + a.series[i], 0));
      const nowTot = accs.reduce((s, a) => s + a.now, 0);
      let lo = 0; tot.forEach((v, i) => { if (v < tot[lo]) lo = i; });
      const loVal = nowTot < tot[lo] ? nowTot : tot[lo], loDay = nowTot < tot[lo] ? 0 : lo;
      const loDate = new Date(fStart); loDate.setDate(loDate.getDate() + loDay);
      q("#fTotNow").innerHTML = accs.length ? fmt(nowTot) : "";
      q("#fTotLow").innerHTML = accs.length ? `${fmt(loVal)}<div class="small muted">${niceDate(new Date(loDate.getTime() - loDate.getTimezoneOffset() * 60000).toISOString().slice(0, 10))}</div>` : "";
      q("#fTotEnd").innerHTML = accs.length ? fmt(tot[tot.length - 1]) : "";
      const tc = q("#fTotal");
      tc.checked = showTotal; tc.disabled = chosen.length < 2;
      tc.title = chosen.length < 2 ? "Tick two or more accounts to show their total" : "Show the total as a dashed line";
      qa("[data-ev]").forEach(r => {
        const e = f.events[+r.dataset.ev];
        r.classList.toggle("sel", e === marked);
        r.classList.toggle("fc-sameday", !!marked && e !== marked && e.date === marked.date);
      });
    };
    qa("[data-fdays]").forEach(b => b.onclick = () => { reportState.fdays = +b.dataset.fdays; renderReports(); });
    const keep = () => { localStorage.setItem("hl-forecast-" + (allEnvs ? "all" : S.env), JSON.stringify(chosen)); draw(); };
    // Toggle exactly the box that was clicked (ids are text: "3" or "s1" for a shared account).
    qa("[data-facct]").forEach(c => c.onchange = () => {
      const id = String(c.dataset.facct);
      chosen = c.checked ? Array.from(new Set(chosen.concat([id]))) : chosen.filter(x => x !== id);
      keep();
    });
    q("#fAll").onchange = e => { chosen = e.target.checked ? shown.map(a => String(a.id)) : []; keep(); };
    q("#fReset").onclick = e => { e.preventDefault(); localStorage.removeItem("hl-forecast-" + (allEnvs ? "all" : S.env)); chosen = allIds.slice(); draw(); };
    q("#fTotal").onchange = e => { showTotal = e.target.checked; localStorage.setItem("hl-forecast-total", showTotal ? "1" : "0"); draw(); };
    q("#fUnmark").onclick = e => { e.preventDefault(); marked = null; st.fmark = null; draw(); };
    qa("[data-ev]").forEach(r => r.onclick = () => {
      const e = f.events[+r.dataset.ev];
      marked = marked === e ? null : e;
      st.fmark = marked ? evKey(marked) : null;
      draw();
      // On a small screen the chart may be out of sight: bring it into view.
      const card = q("#fcCard").getBoundingClientRect();
      if (marked && (card.top < 0 || card.bottom > innerHeight)) q("#fcCard").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    draw();
  } else {
    const rows = await GET("/api/reports/networth?months=12" + sc);
    body = `<div class="card">${lineChart(rows, "net_worth")}</div>
      <div class="card flush" style="margin-top:16px"><table><tr><th>End of</th><th class="num">Net worth</th><th class="num">Change</th></tr>
      ${rows.map((r, i) => ({ r, ch: i ? r.net_worth - rows[i - 1].net_worth : null })).reverse().map(({ r, ch }) => `<tr><td>${esc(monthName(r.month))}</td><td class="num">${fmt(r.net_worth)}</td><td class="num">${ch == null ? "" : fmt(ch)}</td></tr>`).join("")}</table></div>`;
    view().innerHTML = `${reportsHead(tabs, st)}${body}`;
  }
  qa("[data-kind]").forEach(b => b.onclick = () => { reportState.kind = b.dataset.kind; renderReports(); });
  qa("[data-range]").forEach(b => b.onclick = () => { reportState.range = b.dataset.range; renderReports(); });
  helpLinkInTitle("reports");
}

// ---------- TAX REPORT ----------
// Everything in categories marked "Tax related" for one year, each entry listed, plus
// money in and out of Health Savings Accounts against the year's IRS limit (all HSAs
// together, employer money included). A summary to hand to a preparer, not tax advice.
function defaultTaxYear() {
  const t = new Date();
  return t.getMonth() < 4 ? t.getFullYear() - 1 : t.getFullYear();   // Jan-Apr: last year's taxes
}
function taxCsv(r) {
  const cell = v => { const s = String(v == null ? "" : v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const out = [["Section", "Category or account", "Date", "Payee", "Account", "Memo", "Amount"]];
  for (const [side, label] of [["income", "Income"], ["expense", "Deductions and expenses"]]) {
    for (const g of r[side]) {
      for (const i of g.items) out.push([label, g.name, i.date, i.payee, i.account_name, i.memo, dollars(i.amount)]);
      out.push([label, g.name + " (total)", "", "", "", "", dollars(g.total)]);
    }
  }
  for (const e of r.pay || []) {
    for (const d of e.earnings) out.push(["Pay: earnings", e.employer, "", d.label, d.goes_to, `${d.count} paystubs`, dollars(d.total)]);
    out.push(["Pay: gross", e.employer, "", "", "", "", dollars(e.gross)]);
    for (const d of e.deductions) out.push(["Pay: taxes and deductions", e.employer, "", d.label, d.goes_to, `${d.count} paystubs`, dollars(-d.total)]);
    out.push(["Pay: take-home", e.employer, "", "", e.accounts.join("; "), "", dollars(e.net)]);
  }
  for (const h of r.hsa) {
    for (const i of h.contributions) {
      const who = i.pretax ? "HSA contribution (pre-tax: employer or payroll)" : "HSA contribution (you, after tax)";
      out.push([who, h.name, i.date, i.from, h.name, i.counts_for !== +i.date.slice(0, 4) ? `counts for ${i.counts_for}` : i.memo, dollars(i.amount)]);
    }
    for (const i of h.withdrawals) out.push(["HSA withdrawal", h.name, i.date, i.to, h.name, i.memo, dollars(i.amount)]);
    if (h.earnings) out.push(["HSA interest and growth", h.name, "", "", h.name, "", dollars(h.earnings)]);
  }
  const t = r.hsa_totals;
  if (r.hsa.length) {
    out.push(["HSA totals", "Contributed by you (after tax)", "", "", "", "", dollars(t.personal)]);
    out.push(["HSA totals", "Contributed by employer (pre-tax)", "", "", "", "", dollars(t.employer)]);
    if (t.limit != null) out.push(["HSA totals", `IRS limit you entered for ${r.year}`, "", "", "", "", dollars(t.limit)]);
    out.push(["HSA totals", "Withdrawals", "", "", "", "", dollars(t.withdrawn)]);
  }
  return out.map(row => row.map(cell).join(",")).join("\r\n");
}
async function renderTaxReport(el) {
  const st = reportState;
  const y = st.taxYear || defaultTaxYear();
  const r = await GET("/api/reports/tax?year=" + y + scopeQS());
  const thisYear = new Date().getFullYear();
  const years = []; for (let i = thisYear; i >= thisYear - 6; i--) years.push(i);
  const edit = canEdit() && !S.shareCtx;
  const txRows = items => items.map(i => `<tr><td class="small">${niceDate(i.date)}</td><td>${esc(i.payee)}${i.memo ? `<div class="small muted">${esc(i.memo)}</div>` : ""}</td><td class="small">${esc(i.account_name)}</td><td class="num">${fmt(i.amount)}</td></tr>`).join("");
  const section = (title, groups, hint) => `<div class="card flush taxsec"><div style="padding:12px 14px 4px"><h2>${title}</h2><div class="small muted">${hint}</div></div>
    ${groups.length ? `<table><tr><th>Category</th><th class="num">Total</th></tr>
      ${groups.map((g, gi) => `<tr class="click" data-taxg="${title[0]}${gi}"><td><span class="taxcaret">▸</span> ${esc(g.name)} <span class="small muted">(${g.items.length})</span></td><td class="num">${fmt(g.total)}</td></tr>
        <tr class="taxitems" id="taxg-${title[0]}${gi}" hidden><td colspan="2" style="padding:0"><table class="inner"><tr><th>Date</th><th>Payee</th><th>Account</th><th class="num">Amount</th></tr>${txRows(g.items)}</table></td></tr>`).join("")}
      <tr class="fc-total"><td>Total</td><td class="num">${fmt(groups.reduce((s, g) => s + g.total, 0))}</td></tr></table>`
    : `<div class="empty">Nothing in a tax-related category in ${y}.</div>`}</div>`;
  const t = r.hsa_totals;
  const yearSel = (i, cls) => {
    const made = +i.date.slice(0, 4);
    if (!i.may_move || !edit) return i.counts_for !== made ? `<span class="pill">counts for ${i.counts_for}</span>` : "";
    return `<label class="small">counts for <select class="${cls}" data-taxyear="${i.id}">${[made - 1, made].map(v => `<option ${v === i.counts_for ? "selected" : ""}>${v}</option>`).join("")}</select></label>`;
  };
  const hsaAcct = h => `<div class="card flush taxsec"><div style="padding:12px 14px 4px"><h2>${esc(h.name)}</h2>
      <div class="small muted">${h.source === "employer" ? "Money put in by your employer or through payroll, before tax: it shows on your W-2 (box 12, code W), not as a deduction." : "Money you put in yourself, after tax: deductible on Form 8889."}</div></div>
    <table><tr><th>Date</th><th>Put in / taken out</th><th></th><th class="num">Amount</th></tr>
      ${h.contributions.map(i => `<tr><td class="small">${niceDate(i.date)}</td><td>In from ${esc(i.from || "?")}</td><td>${yearSel(i)}</td><td class="num">${fmt(i.amount)}</td></tr>`).join("")}
      ${h.next_year.map(i => `<tr class="muted"><td class="small">${niceDate(i.date)}</td><td>In from ${esc(i.from || "?")} <span class="small">(made early ${y + 1}: counts for ${y + 1} unless you say ${y})</span></td><td>${yearSel(i)}</td><td class="num">${fmt(i.amount)}</td></tr>`).join("")}
      ${h.earnings ? `<tr><td></td><td>Interest and growth <span class="small muted">(not a contribution)</span></td><td></td><td class="num">${fmt(h.earnings)}</td></tr>` : ""}
      ${h.withdrawals.map(i => `<tr><td class="small">${niceDate(i.date)}</td><td>Out to ${esc(i.to || "?")}</td><td></td><td class="num">${fmt(-i.amount)}</td></tr>`).join("")}
      ${h.contributions.length || h.withdrawals.length || h.earnings || h.next_year.length ? "" : `<tr><td colspan="4" class="empty">Nothing in or out in ${y}.</td></tr>`}
      <tr class="fc-total"><td></td><td>Contributions counted for ${y}</td><td></td><td class="num">${fmt(h.contributed)}</td></tr>
      <tr class="fc-total"><td></td><td>Withdrawals in ${y}</td><td></td><td class="num">${fmt(-h.withdrawn)}</td></tr></table>
    ${h.cards.map(c => `<div class="small" style="padding:8px 14px">${c.paid === c.charged ? '<span class="pill green">matches</span>' : '<span class="pill amber">check</span>'}
      Paid to ${esc(c.name)} from this HSA: <b>${fmt(c.paid, true)}</b>; charged on that card in ${y}: <b>${fmt(c.charged, true)}</b>.
      ${c.paid === c.charged ? "" : "A difference can be a statement not entered yet, a payment made in the next year for this year's charges, or spending on the card that wasn't for the HSA."}</div>`).join("")}</div>`;
  // Pay from paystubs: gross vs take-home per employer, and every tax and deduction.
  const payCard = e => {
    const ded = e.deductions.reduce((s, d) => s + d.total, 0);
    const pct = v => e.gross ? ` <span class="small muted">${(v / e.gross * 100).toFixed(1)}%</span>` : "";
    return `<div class="card flush taxsec"><div style="padding:12px 14px 4px"><h2>${esc(e.employer)}</h2>
        <div class="small muted">${e.paystubs} paystub${e.paystubs === 1 ? "" : "s"}, ${niceDate(e.first)} – ${niceDate(e.last)} · take-home pay into ${esc(e.accounts.join(", "))}</div></div>
      <table><tr><th>Earnings</th><th></th><th class="num">${y}</th></tr>
        ${e.earnings.map(d => `<tr><td>${esc(d.label)}</td><td class="small muted">${esc(d.goes_to)}</td><td class="num">${fmt(d.total)}</td></tr>`).join("")}
        <tr class="fc-total"><td>Gross pay</td><td></td><td class="num">${fmt(e.gross)}</td></tr>
        <tr><th>Taxes and deductions</th><th>Where it went</th><th></th></tr>
        ${e.deductions.map(d => `<tr><td>${esc(d.label)}</td><td class="small muted">${d.transfer ? "→ " : ""}${esc(d.goes_to)}</td><td class="num">${fmt(-d.total)}${pct(d.total)}</td></tr>`).join("")}
        <tr class="fc-total"><td>All taxes and deductions</td><td></td><td class="num">${fmt(-ded)}${pct(ded)}</td></tr>
        <tr class="fc-total"><td><b>Take-home pay</b></td><td></td><td class="num"><b>${fmt(e.net)}</b>${pct(e.net)}</td></tr></table>
      <div class="small muted" style="padding:8px 14px">Check these against your W-2: box 1 is usually gross pay less pre-tax deductions (401(k), HSA, health insurance), and boxes 2, 4 and 6 should match the federal income tax, Social Security and Medicare above.</div></div>`;
  };
  // Paychecks with less filled in than is usual for their employer (each links to its account).
  const pcs = (r.paychecks || []).filter(e => e.flagged.length || e.take_home_only);
  const paycheckCard = pcs.length ? `<div class="card taxsec noprint-soft"><h3 style="margin-top:0">Paychecks to check</h3>
    ${pcs.map(e => `<div style="margin-bottom:8px"><b>${esc(e.employer)}</b>: usually <i>${esc(e.usual_words)}</i>.
      ${e.flagged.length ? `<span class="pill amber">${e.flagged.length} of ${e.count} missing something</span>` : `<span class="pill green">all ${e.count} as usual</span>`}
      ${e.take_home_only && e.usual === "net" ? `<span class="small muted">(take-home pay only: gross pay and taxes aren't in this report for them)</span>` : ""}
      ${e.flagged.length ? `<ul class="small" style="margin:4px 0 0 18px;padding:0">${e.flagged.slice(0, 20).map(p =>
        `<li><a href="#/accounts/${p.account_id}">${esc(niceDate(p.date))}, ${fmt(p.net, true)}</a>: ${esc(p.flag)}</li>`).join("")}${e.flagged.length > 20 ? `<li>…and ${e.flagged.length - 20} more</li>` : ""}</ul>` : ""}</div>`).join("")}
    <div class="small muted">Open the entry in its register and choose <b>Add paystub details</b> (or open the paystub), or <b>Complete as is</b> when that's all it will have.</div></div>` : "";
  const pay = (r.pay && r.pay.length
    ? `<h2 class="taxhead">Pay (from paystubs)</h2>${r.pay.map(payCard).join("")}`
    : `<div class="card small muted taxsec">Want gross vs take-home pay here? Record paychecks as paystubs: in the account the pay goes into, choose <b>Paystub…</b> above the entry line. Each one after the first starts as a copy of the last.</div>`) + paycheckCard;
  const over = t.room != null && t.room < 0;
  const hsa = !r.hsa.length ? (r.has_hsa_accounts ? "" : `<div class="card small muted taxsec">Have a Health Savings Account? Open it under Accounts, choose <b>Details</b> and tick <b>This is a Health Savings Account (HSA)</b>; its contributions and withdrawals then show here.</div>`)
    : `<h2 class="taxhead">Health Savings Accounts (HSA)</h2>
    <div class="card taxsec"><div class="grid cols2"><div>
      <div class="setrow"><label>You put in (after tax)</label><div><b>${fmt(t.personal, true)}</b> <span class="small muted">deductible, Form 8889 line 2</span></div></div>
      <div class="setrow"><label>Employer / payroll (pre-tax)</label><div><b>${fmt(t.employer, true)}</b> <span class="small muted">on your W-2, box 12 code W</span></div></div>
      <div class="setrow"><label>All HSAs together</label><div><b>${fmt(t.total, true)}</b>${t.limit != null ? ` of ${fmt(t.limit, true)} ${over ? `<span class="pill red">${fmt(-t.room, true)} over the limit</span>` : `<span class="pill green">${fmt(t.room, true)} room left</span>`}` : ""}</div></div>
      <div class="setrow"><label>Withdrawals</label><div><b>${fmt(t.withdrawn, true)}</b> <span class="small muted">Form 8889 line 14a: keep receipts showing they paid for eligible care</span></div></div>
    </div><div>
      <div class="setrow"><label>IRS limit for ${y}</label><div>${edit ? `<input id="hsaLimit" class="small" style="width:9em" inputmode="decimal" value="${t.limit != null ? dollars(t.limit) : ""}" placeholder="e.g. 4400.00"> <button class="small" id="hsaLimitSave">Save</button>` : (t.limit != null ? fmt(t.limit, true) : "not entered")}
        <div class="small muted" style="margin-top:4px">The yearly maximum for <b>all</b> your HSAs together, employer money included: self-only or family coverage, plus the age-55 catch-up if it applies. The IRS sets it each year; your HSA provider lists it.</div></div></div>
    </div></div>${over ? `<div class="small" style="color:var(--red,#c0392b);margin-top:6px">More went in than the limit you entered. Ask your HSA provider about removing the excess before your tax filing deadline.</div>` : ""}</div>
    ${r.hsa.map(hsaAcct).join("")}`;
  el.innerHTML = `<div class="toolbar noprint"><label class="small">Tax year <select id="taxYear">${years.map(v => `<option ${v === y ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <button class="small" id="taxOpen">Show every entry</button><button class="small" id="taxCsv">Download spreadsheet (CSV)</button><button class="small" id="taxPrint">Print or save as PDF</button></div>
    <div class="printonly"><h2>Tax summary for ${y}</h2></div>
    ${(r.other_currencies || []).length ? `<div class="notice" style="margin:0 0 10px">Accounts in other currencies aren't in this report
      (<span translate="no">${r.other_currencies.map(a => `${esc(a.name)} ${esc(a.currency)}`).join(", ")}</span>): a tax return needs official exchange rates, so add those amounts yourself.</div>` : ""}
    <p class="small muted">Everything in categories marked <b>Tax related</b> (change that under Categories), January 1 – December 31, ${y}${r.income.concat(r.expense).some(g => g.items.some(i => i.shared)) || r.hsa.some(h => h.shared) ? ", accounts shared with you included" : ""}.
      A summary to check against your tax forms (W-2, 1099, 1098) or to give your tax preparer; it isn't tax advice.</p>
    ${section("Income", r.income, "Wages, interest, dividends and other income in tax-related categories.")}
    ${section("Deductions and expenses", r.expense, "Medical, charitable gifts, taxes paid, mortgage interest and other tax-related spending.")}
    ${pay}
    ${hsa}`;
  q("#taxYear").onchange = e => { reportState.taxYear = +e.target.value; renderReports(); };
  const openAll = open => qa(".taxitems").forEach(row => { row.hidden = !open; row.previousElementSibling.querySelector(".taxcaret").textContent = open ? "▾" : "▸"; });
  q("#taxOpen").onclick = () => { const anyClosed = qa(".taxitems").some(r => r.hidden); openAll(anyClosed); q("#taxOpen").textContent = anyClosed ? "Hide entries" : "Show every entry"; };
  qa("[data-taxg]").forEach(row => row.onclick = () => {
    const det = q("#taxg-" + row.dataset.taxg); det.hidden = !det.hidden;
    row.querySelector(".taxcaret").textContent = det.hidden ? "▸" : "▾";
  });
  q("#taxPrint").onclick = () => { openAll(true); window.print(); };
  q("#taxCsv").onclick = () => {
    const blob = new Blob([taxCsv(r)], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `MoneyThistle-taxes-${y}.csv`;
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  };
  if (q("#hsaLimitSave")) q("#hsaLimitSave").onclick = async () => {
    try { await api("PUT", "/api/tax/hsa-limit", { year: y, amount: q("#hsaLimit").value.trim() }); toast("Saved"); renderReports(); }
    catch (e) { toast(e.message, true); }
  };
  qa("[data-taxyear]").forEach(s => s.onchange = async () => {
    try { await api("PUT", `/api/transactions/${s.dataset.taxyear}/tax-year`, { tax_year: +s.value }); renderReports(); }
    catch (e) { toast(e.message, true); }
  });
}

// ---------- CATEGORIES ----------
async function editCategory(cat) {
  const c = cat || { name: "", kind: "expense", parent_id: null, tax_related: 0, in_budget: 0 };
  // A category has its own name (shown in any language it has no name for) and a name per
  // language. The own name is the English one unless it was typed in another language (it's
  // then the same as that language's name).
  const had = c.names || {};
  const enIsOwn = cat ? !had.en && !["fr", "es", "pt"].some(l => had[l] === c.name) : LANG === "en";
  const nameIn = l => l === "en" && enIsOwn ? c.name : (had[l] || "");
  const others = LANGS.filter(l => l[0] !== LANG);
  const body = `<div class="form"><div class="wide"><label>Name</label><input name="name" value="${esc(cat ? catName(c) : "")}"></div>
    <details class="wide"><summary>Name in other languages</summary>
      <p class="small muted" style="margin:6px 0">Shown to people who use MoneyThistle in that language. Left empty, they see the name above.</p>
      <div class="form">${others.map(([code, label]) => `<div><label translate="no">${esc(label)}</label><input name="name_${code}" value="${esc(nameIn(code))}" lang="${code}"></div>`).join("")}</div>
    </details>
    <div><label>Kind</label><select name="kind"><option value="expense" ${c.kind === "expense" ? "selected" : ""}>Expense</option><option value="income" ${c.kind === "income" ? "selected" : ""}>Income</option></select></div>
    <div class="wide"><label>Subcategory of</label><select name="parent_id">${catOptions(c.parent_id, { topOnly: true, blank: "(a main category)" })}</select></div>
    <div><label class="check"><input type="checkbox" name="tax_related" ${c.tax_related ? "checked" : ""}> Tax related</label></div>
    <div><label class="check"><input type="checkbox" name="in_budget" ${c.in_budget ? "checked" : ""}> Show in budget</label></div></div>`;
  const btns = [{ label: "Cancel" }];
  if (cat) btns.unshift({ label: "Delete", cls: "danger", action: async () => {
    if (!(await confirmBox(`Delete "${catFull(c)}"? ${c.used ? c.used + " transactions will have no category." : ""}`))) return false;
    await api("DELETE", "/api/categories/" + c.id); render(); } });
  btns.push({ label: "Save", cls: "primary", action: async root => {
    const f = formData(root); if (!f.parent_id) f.parent_id = null;
    let own = cat ? c.name : (f.name || "").trim();
    const names = {};
    for (const [code] of LANGS) {
      const v = String((code === LANG ? f.name : f["name_" + code]) || "").trim();
      delete f["name_" + code];
      if (code === "en" && enIsOwn) { if (v) own = v; continue; }
      // (a name the same as the own name isn't kept as a language's name of its own, unless
      // it was one already or the category is new in that language)
      names[code] = cat && !had[code] && v === own ? "" : v;
    }
    f.name = own; f.names = names;
    if (cat) await api("PUT", "/api/categories/" + c.id, f); else await api("POST", "/api/categories", f);
    toast("Saved"); render(); } });
  return dialog(cat ? "Change category" : "New category", body, btns);
}
async function renderCategories() {
  await loadBasics();
  const sect = (kind, title) => `<div class="card flush"><div style="padding:12px 14px 4px"><h2>${title}</h2></div><table class="cattree">
    <tr><th>Category</th><th>Tax</th><th>Budget</th><th class="num">Used</th></tr>
    ${S.cats.filter(c => c.kind === kind).map(c => `<tr class="click" data-c="${c.id}"><td class="${c.parent_id ? "sub" : ""}">${c.parent_id ? "" : "<b>"}${esc(catName(c))}${c.parent_id ? "" : "</b>"}</td>
      <td>${c.tax_related ? '<span class="pill amber">tax</span>' : ""}</td><td>${c.in_budget ? '<span class="pill">budget</span>' : ""}</td><td class="num small">${c.used || ""}</td></tr>`).join("")}</table></div>`;
  view().innerHTML = `<h1>Categories</h1><div class="toolbar"><button class="primary" id="nc">New category</button>
    <span class="small muted">Click a category to rename it, move it or delete it.</span></div>
    <div class="grid cols2">${sect("expense", "Expense categories")}<div class="grid" style="align-content:start">
      <div class="card"><h2>Transfers between my accounts</h2>
        <p class="small" style="margin-top:0">Moving money between your own accounts isn't income or spending, so it has its own entries at the top of every
        Category list: <b>Transfer to …</b> (on a withdrawal) and <b>Transfer from …</b> (on a deposit), one for each account.
        Pick one and the matching entry is added to the other account's register; changing or deleting one changes both.
        Reports and the budget leave transfers out.</p>
        ${S.accounts.length ? `<div class="small muted">Your accounts: ${S.accounts.map(a => esc(a.name)).join(", ")}</div>` : `<div class="small muted">Add accounts to transfer between them.</div>`}
      </div>
      ${sect("income", "Income categories")}</div></div>`;
  q("#nc").onclick = () => editCategory(null);
  qa("[data-c]").forEach(r => r.onclick = () => { const c = S.cats.find(x => x.id == r.dataset.c); if (c.kind !== "none") editCategory(c); });
}

// ---------- BACKUPS ----------
// Nextcloud's WebDAV address is https://SERVER/remote.php/dav/files/USER/FOLDER: made
// from the plain fields, and read back into them.
function ncAddress(server, user, folder) {
  server = server.replace(/\/+$/, "");
  if (!/^https?:\/\//i.test(server)) server = "https://" + server;
  const path = folder.split("/").filter(Boolean).map(encodeURIComponent).join("/");
  return `${server}/remote.php/dav/files/${encodeURIComponent(user)}/${path}`;
}
function ncParts(url) {
  const m = String(url || "").match(/^(https?:\/\/[^/]+(?:\/[^/]+)*?)\/remote\.php\/dav\/files\/([^/]+)\/(.+?)\/?$/i);
  if (!m) return { server: "", folder: "", user: "" };
  const dec = v => { try { return decodeURIComponent(v); } catch (e) { return v; } };
  return { server: m[1], user: dec(m[2]), folder: dec(m[3]) };
}
async function renderBackup() {
  const [s, list, log] = await Promise.all([GET("/api/backup/settings"), GET("/api/backup/list").catch(e => ({ backups: [], errors: [{ destination: "?", error: e.message }] })), GET("/api/backup/log")]);
  const locked = k => s.env_locked.includes(k) ? "disabled title='Set by the container (environment variable)'" : "";
  view().innerHTML = `<h1>Backups</h1>
  ${list.errors.map(e => `<div class="notice err">${esc(e.destination)}: ${esc(e.error)}</div>`).join("")}
  <div class="grid cols2">
    <div class="grid" style="align-content:start">
      <div class="card" data-guard="#saveS"><h2>Automatic backups</h2>
        <label class="check"><input type="checkbox" id="on_change" ${s.on_change ? "checked" : ""}> Back up after I make changes</label>
        <div class="small muted" style="margin:0 0 6px 24px">A few minutes after you change something, and when MoneyThistle stops. Older backups are kept by day, week and month.</div>
        ${moreFold("backup-rules", `
        <div class="small muted" style="margin:0 0 6px">After changes: once the app has been quiet for <input id="idle_minutes" class="num" style="width:56px" value="${s.idle_minutes}"> minutes.
          Keep the <input id="keep_change" class="num" style="width:56px" value="${s.keep_change}"> most recent of these.</div>
        <label class="check"><input type="checkbox" id="scheduled" ${s.scheduled ? "checked" : ""}> Also make a scheduled backup every <input id="interval_days" class="num" style="width:56px" value="${s.interval_days}"> days</label>
        <div class="small muted" style="margin:0 0 6px 24px">Keep the <input id="keep_scheduled" class="num" style="width:56px" value="${s.keep_scheduled}"> most recent scheduled backups.
          ${s.last_scheduled ? "Last one: " + niceDate(s.last_scheduled) + "." : "None made yet."}</div>
        <div style="margin:4px 0 8px"><b>Going back further</b>
          <div class="small muted" style="margin-top:2px">Also keep the last backup of each of the latest
            <input id="keep_daily" class="num" style="width:48px" value="${s.keep_daily}"> days,
            <input id="keep_weekly" class="num" style="width:48px" value="${s.keep_weekly}"> weeks and
            <input id="keep_monthly" class="num" style="width:48px" value="${s.keep_monthly}"> months (0 turns one off).
            So a mistake you only notice days or months later can still be undone from a backup made before it,
            even after a busy day of changes. Backups you make with <b>Back up now</b> are never cleared.</div></div>
        <label class="check"><input type="checkbox" id="compress" ${s.compress ? "checked" : ""}> Compress backup files</label>`, false, "When to back up and how many to keep")}
      </div>
      <div class="card" data-guard="#saveS"><h2>Encryption</h2>
        <label class="check"><input type="checkbox" id="encrypt" ${s.encrypt ? "checked" : ""}> Encrypt backups with a password</label>
        <div class="form" style="margin-left:24px"><div class="wide" style="grid-column:1/-1"><label>Backup password <span class="muted">(10 characters or more)</span></label>
          <input id="backup_password" type="password" autocomplete="new-password" placeholder="${s.backup_password_set ? "(saved, type to change)" : ""}"></div></div>
        <p class="small muted" style="margin-left:24px"><b>Write the password down somewhere safe</b>: restoring on another computer, or after losing this one, needs it, and nobody can recover it.</p>
        ${moreFold("backup-crypto", `<p class="small muted" style="margin:0">Each backup is locked with this password (scrypt + ChaCha20, with a tamper check), so a copy on Nextcloud or another server can't be read without it.
          MoneyThistle keeps the password to make backups on its own.
          Every backup is read back after it's saved (same SHA-256, decrypts, every file in it opens) before it counts as done.</p>`, false, "How it works")}
      </div>
      <div class="card" data-guard="#saveS"><h2>Where to keep them</h2>
        <label class="check"><input type="checkbox" id="webdav_enabled" ${s.webdav_enabled ? "checked" : ""}> Back up to Nextcloud</label>
        <div class="form" style="margin-left:24px">
          <div class="wide" style="grid-column:1/-1"><label>Your Nextcloud address</label><input id="nc_server" placeholder="https://cloud.example.com" value="${esc(ncParts(s.webdav_url).server)}" ${locked("WEBDAV_URL")}></div>
          <div><label>User name</label><input id="webdav_user" value="${esc(s.webdav_user)}" autocomplete="off" ${locked("WEBDAV_USER")}></div>
          <div><label>App password</label><input id="webdav_password" type="password" autocomplete="new-password" placeholder="${s.webdav_password_set ? "(saved, type to change)" : ""}" ${locked("WEBDAV_PASSWORD")}></div>
          <div class="wide" style="grid-column:1/-1"><label>Folder there</label><input id="nc_folder" placeholder="MoneyThistle" value="${esc(ncParts(s.webdav_url).folder)}" ${locked("WEBDAV_URL")}></div>
        </div>
        <p class="small muted" style="margin-left:24px">In Nextcloud, open <b>Settings → Security</b> and create an <b>app password</b> for MoneyThistle. The folder is made if it isn't there.</p>
        ${moreFold("backup-where", `
          <label class="check"><input type="checkbox" id="local_enabled" ${s.local_enabled ? "checked" : ""}> Also keep them in a folder</label>
          <div style="margin-left:24px"><input id="local_dir" style="width:100%" value="${esc(s.local_dir)}" ${locked("BACKUP_DIR")}>
            <div class="small muted">In Docker this is the <code>/backups</code> volume. Point it at a synced folder (Nextcloud, Dropbox, a NAS share) if you like.</div></div>
          <div style="margin-top:10px"><label>WebDAV folder address <span class="muted">(another WebDAV server, or a Nextcloud address of your own)</span></label>
            <input id="webdav_url" style="width:100%" value="${esc(s.webdav_url)}" placeholder="https://cloud.example.com/remote.php/dav/files/USERNAME/Backups/Money" ${locked("WEBDAV_URL")}>
            <div class="small muted">Filled in from the Nextcloud fields above. ownCloud, Synology, Box and other WebDAV services take their own address here.</div></div>`,
          s.local_enabled || (s.webdav_url && !ncParts(s.webdav_url).server), "Other places")}
      </div>
      <div class="toolbar"><button class="primary" id="saveS">Save settings</button><button id="now">Back up now</button>
        <button id="restoreFile" title="Put back a backup file you have (from Nextcloud, a USB stick, another computer)">Restore from a file…</button></div>
    </div>
    <div class="grid" style="align-content:start">
      <div class="card flush"><div style="padding:12px 14px 4px"><h2>Your backups</h2></div>
        <table><tr><th>Made</th><th>Kind</th><th title="Why it's kept: recent, or the last of its day, week or month">Kept as</th><th>Where</th><th class="num">Size</th><th></th></tr>
        ${list.backups.map(b => `<tr><td class="small">${new Date(b.when).toLocaleString(LOCALE)}</td><td><span class="pill ${b.kind === "scheduled" ? "green" : (b.kind === "manual" ? "amber" : "")}">${b.kind === "auto" ? "after changes" : b.kind}</span></td>
          <td class="small muted">${esc(b.kept_as || "")}</td>
          <td class="small">${b.destination === "webdav" ? "WebDAV" : "Folder"}</td><td class="num small">${b.size == null ? "" : (b.size / 1024).toFixed(0) + " KB"}</td>
          <td class="num" style="white-space:nowrap">${b.name.endsWith(".enc") ? '<span class="pill" title="Encrypted with the backup password">🔒</span> ' : ""}<button class="small" data-verify="${esc(b.name)}" data-dest="${b.destination}" title="Download it and check it opens">Verify</button>
            <button class="small" data-restore="${esc(b.name)}" data-dest="${b.destination}">Restore</button>
            <button class="small danger trash" data-bdel="${esc(b.name)}" data-dest="${b.destination}" data-when="${esc(b.when)}" data-kind="${esc(b.kind)}" title="Delete this backup" aria-label="Delete this backup">${TRASH_ICON}</button></td></tr>`).join("")}</table>
        ${list.backups.length ? "" : `<div class="empty">No backups yet. Click <b>Back up now</b> to make the first one.</div>`}</div>
      <div class="card flush"><div style="padding:12px 14px 4px"><h2>Recent backup activity</h2></div>
        <table>${log.map(l => `<tr><td class="small">${new Date(l.at).toLocaleString(LOCALE)}</td><td class="small">${esc(l.kind)} → ${esc(l.destination)}</td>
          <td>${l.ok ? '<span class="pill green">done</span>' : '<span class="pill red">failed</span>'}</td><td class="small muted">${esc(l.ok ? (String(l.message || "").includes("verified") ? "verified" + (String(l.message).includes("encrypted") ? " · encrypted" : "") : "") : l.message)}</td></tr>`).join("")}</table>
        ${log.length ? "" : `<div class="empty">Nothing yet</div>`}</div>
    </div>
  </div>`;
  const collect = () => {
    const o = {};
    for (const k of ["on_change", "scheduled", "compress", "local_enabled", "webdav_enabled", "encrypt"]) o[k] = q("#" + k).checked;
    if (q("#backup_password").value) o.backup_password = q("#backup_password").value;
    for (const k of ["idle_minutes", "keep_change", "interval_days", "keep_scheduled", "keep_daily", "keep_weekly", "keep_monthly"]) o[k] = q("#" + k).value;
    for (const k of ["local_dir", "webdav_url", "webdav_user"]) if (!q("#" + k).disabled) o[k] = q("#" + k).value;
    // The simple Nextcloud fields make the WebDAV address, only when they were changed (and
    // never over one typed by hand). Nextcloud's address names the account's own id, which can
    // differ from the sign-in name (an email address): an existing address keeps its id.
    const server = q("#nc_server").value.trim(), folder = q("#nc_folder").value.trim() || "MoneyThistle";
    const was = ncParts(s.webdav_url);
    const changed = !s.webdav_url || server !== was.server || folder !== was.folder;
    if (server && changed && !q("#webdav_url").disabled && q("#webdav_url").value === s.webdav_url) {
      o.webdav_url = ncAddress(server, was.user || q("#webdav_user").value.trim(), folder);
    }
    if (q("#webdav_password").value) o.webdav_password = q("#webdav_password").value;
    return o;
  };
  q("#saveS").onclick = async () => { try { await api("PUT", "/api/backup/settings", collect()); toast("Backup settings saved"); renderBackup(); } catch (e) { toast(e.message, true); } };
  q("#restoreFile").onclick = () => dialog("Restore from a file", `<p class="small">Everything goes back to how it was in that backup: every environment,
      entry, receipt and sign-in. Changes made since then are lost, so a safety copy of everything as it is now is saved in the backup folder first.</p>
    <div class="form" style="grid-template-columns:1fr"><div><label>Backup file</label><input type="file" id="rfFile" accept=".zip,.enc,.db,.gz"></div>
      <div><label>Backup password <span class="muted">(if it's encrypted with a different one than now)</span></label><input type="password" id="rfPw" autocomplete="off"></div></div>`,
    [{ label: "Cancel" }, { label: "Restore", cls: "danger", action: async root => {
      const file = q("#rfFile", root).files[0];
      if (!file) throw new Error("Choose the backup file first.");
      const r = await uploadRestore("/api/backup/restore-upload", file, q("#rfPw", root).value);
      toast(`Restored ${r.restored}`); setTimeout(() => location.reload(), 1200);
    } }]);
  q("#now").onclick = async () => {
    try {
      await api("PUT", "/api/backup/settings", collect());
      q("#now").disabled = true; q("#now").textContent = "Backing up…";
      const r = await api("POST", "/api/backup/now");
      const bad = r.results.filter(x => !x.ok);
      if (bad.length) toast(bad.map(x => x.destination + ": " + x.error).join("; "), true); else toast("Backup made");
    } catch (e) { toast(e.message, true); }
    renderBackup(); refreshBackupState();
  };
  // An encrypted backup made with another password (an older one, another computer)
  // asks for it; the saved password is tried first.
  const askPw = () => dialog("Backup password", `<p>This backup was locked with a different password. Type the password it was made with.</p>
    <input type="password" name="pw" autocomplete="off" style="width:100%">`, [{ label: "Cancel", value: null },
    { label: "Use it", cls: "primary", action: root => q("[name=pw]", root).value || null }]);
  const withPw = async (call) => {
    try { return await call(undefined); }
    catch (e) {
      if (!/password/i.test(e.message)) throw e;
      const pw = await askPw();
      if (!pw) throw e;
      return call(pw);
    }
  };
  qa("[data-verify]").forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = "Checking…";
    try {
      const r = await withPw(pw => api("POST", "/api/backup/verify", { name: b.dataset.verify, destination: b.dataset.dest, password: pw }));
      dialog("Backup checked", `<p><span class="pill green">opens correctly</span> ${esc(r.name)}</p>
        <p class="small">Downloaded ${(r.bytes / 1024).toFixed(0)} KB from ${r.destination === "webdav" ? "WebDAV" : "the folder"}${r.encrypted ? ", decrypted with the password," : ""} and every file in it read without errors.</p>
        <p class="small muted">SHA-256: <code style="word-break:break-all">${esc(r.sha256)}</code></p>`, [{ label: "OK", cls: "primary" }]);
    } catch (e) { toast(e.message, true); }
    b.disabled = false; b.textContent = "Verify";
  });
  qa("[data-bdel]").forEach(b => b.onclick = async () => {
    const where = b.dataset.dest === "webdav" ? "Nextcloud / WebDAV" : "the backup folder";
    const when = new Date(b.dataset.when).toLocaleString(LOCALE);
    const kind = b.dataset.kind === "manual" ? "Back up now copy" : (b.dataset.kind === "auto" ? "after-changes backup" : "scheduled backup");
    const others = list.backups.filter(x => x.destination === b.dataset.dest).length - 1;
    const ok = await dialog("Delete this backup?", `<p>The <b>${esc(kind)}</b> from <b>${esc(when)}</b> in ${esc(where)} is deleted for good:
        it can't be restored afterwards.</p>
      <p class="small muted">${others} other backup${others === 1 ? "" : "s"} stay${others === 1 ? "s" : ""} there. The newest one is a copy of everything as of ${esc(new Date(list.backups.filter(x => x.destination === b.dataset.dest)[0].when).toLocaleString(LOCALE))}.</p>
      <label class="check"><input type="checkbox" id="bdelSure"> Yes, delete this backup</label>`,
      [{ label: "Keep it", value: false }, { label: "Delete", cls: "danger", action: root => {
        if (!q("#bdelSure", root).checked) throw new Error("Tick \"Yes, delete this backup\" first.");
        return true;
      } }]);
    if (!ok) return;
    try { await api("POST", "/api/backup/delete", { name: b.dataset.bdel, destination: b.dataset.dest }); toast("Backup deleted"); renderBackup(); }
    catch (e) { toast(e.message, true); }
  });
  qa("[data-restore]").forEach(b => b.onclick = async () => {
    if (!(await confirmBox("Restore this backup? Everything you changed since it was made will be replaced. A copy of your current file is saved first."))) return;
    try { await withPw(pw => api("POST", "/api/backup/restore", { name: b.dataset.restore, destination: b.dataset.dest, password: pw })); toast("Restored"); await loadBasics(); location.hash = "#/home"; }
    catch (e) { toast(e.message, true); }
  });
}

// Notifications (administrators): a daily summary by email, Pushover, ntfy or Gotify.
async function notifyCard() {
  const n = await GET("/api/notify").catch(() => null);
  if (!n) return "";
  const v = (o, k) => esc(o[k] == null ? "" : o[k]);
  const secret = (ch, k, label) => `<div><label>${label}</label><input name="${ch}.${k}" type="password" autocomplete="off"
      placeholder="${n[ch][k + "_set"] ? "saved (leave empty to keep)" : ""}"></div>`;
  const head = (ch, title, note) => `<div class="nch" style="margin-top:12px;border-top:1px solid var(--line);padding-top:10px">
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><label class="check" style="margin:0"><input type="checkbox" name="${ch}.enabled" ${n[ch].enabled ? "checked" : ""}> <b>${title}</b></label>
      <span class="small muted" style="flex:1">${note}</span><button type="button" class="small" data-ntest="${ch}">Send test</button></div>`;
  const admin = n.is_admin_setup;
  const shared = !admin && n.shared_email_available;
  const useShared = shared && n.email.use_shared;
  return `<div class="card" id="notifyCard" data-guard="#saveNotify"><h2>Notifications${admin ? ' <span class="pill">administrators</span>' : ""}</h2>
    <p class="small muted" style="margin-top:0">Once a day MoneyThistle sends you a short summary, but only when there's something to say. ${admin
      ? "This setup is the administrators' and covers every environment; everyone else sets up their own here, for the environments they're in."
      : "It covers the environments you're in. Use your own services and credentials; they're kept for you alone."}</p>
    <div class="form">
      <div><label>Send at (hour, 0-23)</label><input name="hour" class="num" value="${n.hour}"></div>
      <div><label>Bills due within (days, 0 = off)</label><input name="due_days" class="num" value="${n.due_days}"></div>
      <div class="wide" style="grid-column:1/-1">
        ${[["overdue", "Overdue items"], ["statements", "Card statements to enter"], ["auto_recorded", "Automatic items recorded for you"],
          ["below_zero", "Accounts forecast to go below zero (next 14 days)"], ...(admin ? [["backups", "Backup problems"]] : [])]
          .map(([k, l]) => `<label class="check"><input type="checkbox" name="${k}" ${n[k] ? "checked" : ""}> ${l}</label>`).join("")}</div>
    </div>
    ${head("email", "Email", useShared ? "through the shared email server" : "through your mail provider's SMTP server")}
      ${shared ? `<div style="margin:4px 0 6px"><label class="check"><input type="radio" name="email.use_shared" value="1" ${useShared ? "checked" : ""}> Use the email server an administrator shared: just enter your address</label>
        <label class="check"><input type="radio" name="email.use_shared" value="" ${useShared ? "" : "checked"}> Use my own email server</label></div>` : ""}
      ${useShared ? `<div class="form"><div class="wide"><label>Send to</label><input name="email.to" value="${v(n.email, "to")}" placeholder="you@example.com"></div></div></div>` : `
      <div class="form"><div><label>SMTP server</label><input name="email.host" value="${v(n.email, "host")}" placeholder="smtp.example.com"></div>
        <div><label>Port</label><input name="email.port" class="num" value="${v(n.email, "port")}"></div>
        <div><label>Security</label><select name="email.security">${[["starttls", "STARTTLS (587)"], ["ssl", "SSL/TLS (465)"], ["none", "None (local relay only)"]]
          .map(([k, l]) => `<option value="${k}" ${n.email.security === k ? "selected" : ""}>${l}</option>`).join("")}</select></div>
        <div><label>User name</label><input name="email.username" autocomplete="off" value="${v(n.email, "username")}"></div>
        ${secret("email", "password", "Password (an app password is best)")}
        <div><label>From</label><input name="email.from" value="${v(n.email, "from")}" placeholder="moneythistle@example.com"></div>
        <div class="wide"><label>Send to</label><input name="email.to" value="${v(n.email, "to")}" placeholder="you@example.com"></div></div>
      ${admin ? `<label class="check" style="margin-top:6px"><input type="checkbox" name="share_email" ${n.share_email ? "checked" : ""}> Share this email server with everyone: they only enter their own address (your password stays hidden)</label>` : ""}</div>`}
    ${head("pushover", "Pushover", "pushover.net: create an application for its token")}
      <div class="form">${secret("pushover", "app_token", "Application token")}${secret("pushover", "user_key", "Your user key")}
        <div><label>Device <span class="muted">(optional)</span></label><input name="pushover.device" value="${v(n.pushover, "device")}"></div></div></div>
    ${head("ntfy", "ntfy", "ntfy.sh or your own server; pick a hard-to-guess topic")}
      <div class="form"><div><label>Server</label><input name="ntfy.server" value="${v(n.ntfy, "server")}"></div>
        <div><label>Topic</label><input name="ntfy.topic" value="${v(n.ntfy, "topic")}"></div>
        ${secret("ntfy", "token", "Access token (optional)")}</div></div>
    ${head("gotify", "Gotify", "your own Gotify server")}
      <div class="form"><div><label>Server</label><input name="gotify.server" value="${v(n.gotify, "server")}" placeholder="https://gotify.example.com"></div>
        ${secret("gotify", "token", "Application token")}</div></div>
    <div class="toolbar" style="margin-top:12px"><button class="primary" id="saveNotify">Save notifications</button><button id="previewNotify">Preview today's summary</button></div>
    <pre id="notifyPreview" class="small" style="white-space:pre-wrap;display:none;background:var(--surface2);padding:8px;border-radius:6px"></pre>
    <p class="small muted">Passwords and tokens are kept in MoneyThistle's data folder and its backups, and never shown again. The summary leaves out account numbers; it does include amounts and payee names.</p>
  </div>`;
}
function notifyForm() {
  const out = {};
  qa("#notifyCard [name]").forEach(el => {
    if (el.type === "radio" && !el.checked) return;   // only the chosen option
    const [a, b] = el.name.split(".");
    const val = el.type === "checkbox" ? el.checked : el.value;
    if (b) { out[a] = out[a] || {}; out[a][b] = val; } else out[a] = val;
  });
  return out;
}
document.addEventListener("change", async e => {
  // Shared email server or my own: save the choice and show its fields.
  if (!e.target || e.target.name !== "email.use_shared") return;
  try { await api("PUT", "/api/notify", notifyForm()); renderSettings(); } catch (err) { toast(err.message, true); }
});
document.addEventListener("click", async e => {
  const t = e.target;
  if (!t || !t.closest || !t.closest("#notifyCard")) return;
  try {
    if (t.id === "saveNotify") { await api("PUT", "/api/notify", notifyForm()); toast("Notifications saved"); renderSettings(); }
    else if (t.id === "previewNotify") {
      const r = await GET("/api/notify/preview");
      const pre = q("#notifyPreview"); pre.style.display = ""; pre.textContent = r.text || "Nothing to report today: no summary would be sent.";
    } else if (t.dataset && t.dataset.ntest) {
      await api("PUT", "/api/notify", notifyForm());   // test what's on screen
      const r = await api("POST", "/api/notify/test", { channel: t.dataset.ntest });
      toast(r.result === "ok" ? "Test sent: check " + t.dataset.ntest : "Couldn't send: " + r.result, r.result !== "ok");
    }
  } catch (err) { toast(err.message, true); }
});

// ---------- SETTINGS ----------
// ---------- SETTINGS: one row of sub-tabs (a drop-down list on phones) ----------
// Each has its own address (#/settings/backups...), so bookmarks and Help go straight there.
function settingsTabs() {
  const admin = S.me && S.me.user.is_admin;
  return [["look", "Look"], ["notifications", "Notifications"], ["people", "People & access"], ["categories", "Categories"],
    ...(admin ? [["backups", "Backups"]] : []), ["data", "Your data"], ...(admin ? [["computer", "This computer"]] : [])];
}
const SETTINGS_HELP = { look: "settings", notifications: "notifications", people: "people", categories: "taxes",
  backups: "backups", data: "history", computer: "startstop" };
async function renderSettings(sub) {
  await loadBasics();
  const tabs = settingsTabs();
  sub = sub || (location.hash.split("/")[1] === "settings" && location.hash.split("/")[2]) || "look";
  if (!tabs.some(([k]) => k === sub)) sub = "look";
  S.viewTarget = null;
  view().innerHTML = `<div class="pagehead"><h1>Settings</h1></div>
    <nav class="settabs noprint" aria-label="Settings sections">${tabs.map(([k, l]) =>
      `<a href="#/settings/${k}" class="${k === sub ? "on" : ""}" ${k === sub ? 'aria-current="page"' : ""}>${esc(l)}</a>`).join("")}</nav>
    <select class="settab-select noprint" aria-label="Settings section">${tabs.map(([k, l]) =>
      `<option value="${k}" ${k === sub ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>
    <div id="subview" class="subview"></div>`;
  q(".settab-select").onchange = e => { location.hash = "#/settings/" + e.target.value; };
  // The section draws itself into the space under the tabs.
  S.viewTarget = q("#subview");
  S.settingsSub = sub;
  if (sub === "people") await renderPeople();
  else if (sub === "categories") await renderCategories();
  else if (sub === "backups") await renderBackup();
  else if (sub === "notifications") {
    view().innerHTML = (await notifyCard()) || '<div class="card"><div class="empty">Notifications couldn\'t be loaded.</div></div>';
  } else if (sub === "data") renderDataTab();
  else if (sub === "computer") await renderComputerTab();
  else renderLookTab();
}
function renderDataTab() {
  view().innerHTML = `<div class="card" style="max-width:820px"><h2>Your data</h2>
    ${canEdit() ? `<div class="setrow"><label>Move in</label><div><button class="small" id="migrateBtn">Bring in everything from another program…</button>
      <div class="small muted" style="margin-top:3px">Microsoft Money, Quicken, Moneydance, YNAB, GnuCash, Mint and more: every account and its history from their export files.</div></div></div>` : ""}
    <div class="setrow"><label>Export</label><div><a class="btn small" href="/api/export.csv?env=${S.env}">Download all transactions (CSV)</a>
      <span class="small muted">for a spreadsheet, or another program</span></div></div>
    <div class="setrow"><label>History</label><div><a class="btn small" href="#/history">Change history</a> <span class="small muted">who added, changed or deleted what; undo</span></div></div>
    ${S.me.user.is_admin ? `<div class="setrow"><label>Backups</label><div><a class="btn small" href="#/settings/backups">Backups</a> <span class="small muted">automatic backups, Nextcloud / WebDAV, restore</span></div></div>` : ""}
    ${envRole() === "owner" ? `<div class="setrow"><label>Start fresh</label><div><button class="small danger" id="freshBtn">Start fresh…</button>
      <div class="small muted" style="margin-top:3px">${curEnv().sample_data ? "Remove the sample data and begin with your own accounts." :
        "Clear this environment back to a new start (its name typed to confirm). A copy of what's there now is kept."}</div></div></div>` : ""}
  </div>`;
  if (q("#migrateBtn")) q("#migrateBtn").onclick = () => migrateDialog();
  if (q("#freshBtn")) q("#freshBtn").onclick = () => startFresh();
}
async function renderComputerTab() {
  const [vcard, scard] = [await versionCard(), await startupCard()];
  view().innerHTML = `<div class="grid settings"><div class="grid" style="align-content:start">${vcard}</div>
    <div class="grid" style="align-content:start">${scard}</div></div>`;
  if (q("#restartBtn")) q("#restartBtn").onclick = restartApp;
  if (q("#shutBtn")) q("#shutBtn").onclick = shutDownApp;
  wireUpdatesRow();
  wireStartupCard();
}
function renderLookTab() {
  const ui = Object.assign({}, S.ui);
  const sample = "2026-11-15";
  const dateStyles = [["system", "Like this device"], ["us", "Nov 15, 2026"], ["uk", "15 Nov 2026"], ["eu", "15.11.2026"], ["iso", "2026-11-15"]];
  const isPreset = ACCENTS.some(([, c]) => c === ui.accent);
  const detail = simpleMode() ? "simple" : "full";
  view().innerHTML = `<p class="small muted" style="margin-top:0">Saved on the server, so every device that opens MoneyThistle looks the same.</p>
  <div class="card" style="margin-bottom:14px"><h2>How much MoneyThistle shows you</h2>
    <div class="choice detail-choice" id="detailChoice">
      <label class="${detail === "simple" ? "on" : ""}"><input type="radio" name="detail" value="simple" ${detail === "simple" ? "checked" : ""}>
        <span><b>Simple</b><br><span class="small muted">The everyday things. Extra fields and settings are folded under "More options", ready when you want them.</span></span></label>
      <label class="${detail === "full" ? "on" : ""}"><input type="radio" name="detail" value="full" ${detail === "full" ? "checked" : ""}>
        <span><b>Everything</b><br><span class="small muted">Every field and option open, plus moving accounts between environments.</span></span></label>
    </div>
    <p class="small muted" style="margin-bottom:0">Just for you (each person chooses their own). Whatever you open or close under "More options" is remembered, place by place.</p>
  </div>
  <div class="grid settings">
    <div class="grid" style="align-content:start">
    <div class="card" data-guard="#saveUi"><h2>Appearance</h2>
      <div class="setrow"><label>Theme</label><div class="choice" id="theme">
        ${[["light", "Light"], ["dark", "Dark"], ["auto", "Match this device"]].map(([k, l]) =>
          `<label class="${ui.theme === k ? "on" : ""}"><input type="radio" name="theme" value="${k}" ${ui.theme === k ? "checked" : ""}><span class="themeprev ${k}"><i></i></span>${l}</label>`).join("")}
      </div></div>
      <div class="setrow"><label>Accent color</label><div class="swatches" id="swatches">
        ${ACCENTS.map(([n, c]) => `<button type="button" class="swatch ${ui.accent === c ? "on" : ""}" data-c="${c}" title="${n}" style="background:${c}"></button>`).join("")}
        <input type="color" id="custom" value="${esc(ui.accent)}" title="Pick any color" class="${isPreset ? "" : "on"}">
        <span class="small muted" id="accentName">${esc((ACCENTS.find(([, c]) => c === ui.accent) || ["Custom"])[0])}</span>
      </div></div>
      <div class="preview"><div class="ph">Preview</div><div class="pb">
        <button class="primary small" type="button">Button</button><span class="pill">Label</span>
        <span class="pill green">Paid</span><span class="pill red">Overdue</span>
        <div style="flex:1">${budgetBar(60, 100, 0.5)}</div></div></div>
      <p class="small muted" style="margin-bottom:0">Changes show right away; click Save to keep them.</p>
    </div>
    <div class="card"><h2>Coffee cup</h2>
      <label class="check"><input type="checkbox" id="coffeeMine" ${S.ui.coffee !== false ? "checked" : ""} ${S.me.coffee_off ? "disabled" : ""}> Show the coffee cup and the line at the bottom of the page</label>
      ${S.me.user.is_admin ? `<label class="check" style="margin-top:6px"><input type="checkbox" id="coffeeAll" ${S.me.coffee_off ? "checked" : ""}> Hide them for everyone on this MoneyThistle</label>` : ""}
      <p class="small muted" style="margin-bottom:0">MoneyThistle is free. The cup links to the maker's Buy Me a Coffee page, for anyone who'd like to chip in;
      nothing is ever expected, and nothing is sent there unless you click. <span>${S.me.coffee_off ? "An administrator has hidden them for everyone." : "Just for you."}</span></p>
    </div></div>
    <div class="grid" style="align-content:start">
    <div class="card" data-guard="#saveUi"><h2>Language, money and dates</h2>
      <div class="setrow"><label for="lang">Language</label><div><select id="lang" translate="no">
        <option value="" ${!ui.lang ? "selected" : ""}>${esc(tr("Like this browser"))} (${esc(LANGS.find(l => l[0] === pickLang(""))[1])})</option>
        ${LANGS.map(([k, n]) => `<option value="${k}" ${ui.lang === k ? "selected" : ""}>${n}</option>`).join("")}</select>
        <div class="small muted" style="margin-top:3px">Just for you. French, Spanish and Portuguese were translated by AI and haven't been checked by a native speaker yet; anything not translated yet shows in English.</div></div></div>
      <div class="setrow"><label>Example</label><div><span class="small">${fmt(123456, true)} · ${esc(niceDate(sample))}</span>
        <input id="currency" type="hidden" value="${esc(ui.currency)}"></div></div>
      <div class="setrow"><label for="date_style">Date style</label><select id="date_style">
        ${dateStyles.map(([k, l]) => `<option value="${k}" ${ui.date_style === k ? "selected" : ""}>${k === "system" ? l + " (" + new Date(sample + "T00:00:00").toLocaleDateString(LOCALE, { month: "short", day: "numeric", year: "numeric" }) + ")" : l}</option>`).join("")}
      </select></div>
      <div class="setrow"><label for="due_days">"Due soon" on Home</label><div><input id="due_days" class="num" style="width:70px" value="${ui.due_days}"> <span class="small muted">days ahead</span></div></div>
      <div class="setrow"><label>Home page cards</label><div><a class="btn small" href="#/" id="goCustom">Customize Home…</a> <span class="small muted">show, hide and arrange</span></div></div>
    </div>
    <div class="toolbar" style="margin:0"><button class="primary" id="saveUi">Save settings</button><button id="resetUi">Back to defaults</button><span class="small muted">for Appearance and Language, money and dates</span></div>
    ${S.env ? currencyCard() : ""}
    </div>
  </div>`;
  wireCurrencyCard();

  const live = () => { applyTheme(ui); renderSettingsPreviewText(); };
  const renderSettingsPreviewText = () => {
    q("#accentName").textContent = (ACCENTS.find(([, c]) => c === ui.accent) || ["Custom"])[0];
  };
  qa("#theme input").forEach(r => r.onchange = () => {
    ui.theme = r.value; qa("#theme label").forEach(l => l.classList.toggle("on", l.contains(r))); live();
  });
  qa("#swatches .swatch").forEach(b => b.onclick = () => {
    ui.accent = b.dataset.c; qa("#swatches .swatch").forEach(x => x.classList.toggle("on", x === b));
    q("#custom").value = ui.accent; live();
  });
  q("#custom").oninput = e => { ui.accent = e.target.value; qa("#swatches .swatch").forEach(x => x.classList.remove("on")); live(); };
  q("#goCustom").onclick = () => { S.openCustomize = true; };
  q("#coffeeMine").onchange = async e => {
    try { S.ui = await api("PUT", "/api/settings", { coffee: e.target.checked }); drawTopBar(); toast(e.target.checked ? "Coffee cup shown" : "Coffee cup hidden"); }
    catch (err) { toast(err.message, true); }
  };
  if (q("#coffeeAll")) q("#coffeeAll").onchange = async e => {
    try {
      await api("PUT", "/api/admin/coffee", { off: e.target.checked });
      S.me.coffee_off = e.target.checked; drawTopBar(); renderSettings();
      toast(e.target.checked ? "Coffee cup hidden for everyone" : "Coffee cup shown again (each person can still hide it)");
    } catch (err) { toast(err.message, true); }
  };
  qa("#detailChoice input").forEach(r => r.onchange = async () => {
    try {
      S.ui = await api("PUT", "/api/settings", { detail: r.value });
      toast(r.value === "full" ? "Showing everything" : "Simple: extras folded away");
      drawTopBar(); renderSettings();
    } catch (e) { toast(e.message, true); }
  });
  q("#saveUi").onclick = async () => {
    try {
      const before = S.ui.lang || "";
      S.ui = await api("PUT", "/api/settings", { theme: ui.theme, accent: ui.accent, currency: q("#currency").value.trim(),
        date_style: q("#date_style").value, due_days: q("#due_days").value, lang: q("#lang").value });
      // Another language: the page starts again in it (English text already shown can't be
      // put back otherwise).
      if ((S.ui.lang || "") !== before) { try { localStorage.setItem("hl-lang", S.ui.lang || ""); } catch (e) { } location.reload(); return; }
      applyTheme(S.ui); toast("Settings saved"); renderSettings();
    } catch (e) { toast(e.message, true); }
  };
  q("#resetUi").onclick = async () => {
    UNSAVED.delete("#saveUi");
    S.ui = await api("PUT", "/api/settings", { theme: "light", accent: "#1c4b8a", currency: "", date_style: "system", due_days: 14 });
    applyTheme(S.ui); toast("Back to the default look"); renderSettings();
  };
}
// This environment's main currency (totals, the budget and the tax report are in it) and
// rough rates for the other currencies its accounts use. No exchange rates are looked up.
function currencyCard() {
  const m = S.money || { home: "USD", rates: {} };
  const envName = ((S.me.envs || []).find(e => e.id === S.env) || {}).name || "";
  const used = [...new Set(S.accounts.filter(a => !a._shared).map(a => a.currency).filter(c => c && c !== m.home))];
  const others = [...new Set([...used, ...Object.keys(m.rates)])].sort();
  const ro = canEdit() ? "" : "disabled";
  return `<div class="card" id="curCard" data-guard="#saveCur" style="margin-top:14px"><h2>Currencies</h2>
    <p class="small muted" style="margin-top:0">For everyone in <b translate="no">${esc(envName)}</b>. Each account has its own currency (in its details); totals, the budget and the tax report are in the main one.</p>
    <div class="setrow"><label for="homeCur">Main currency</label><div><select id="homeCur" ${ro}>${curOptions(m.home)}</select></div></div>
    ${others.length ? `<div class="setrow"><label>Rough rates</label><div>
      ${others.map(c => `<div style="margin-bottom:6px">1 ${c} ≈ <input class="num" data-rate="${c}" style="width:90px" value="${esc(m.rates[c] || "")}" placeholder="?" ${ro}> ${m.home}
        <span class="small muted">${esc(curName(c))}</span></div>`).join("")}
      <div class="small muted">Only for totals like net worth, which are then marked approximate. Leave one empty and that currency's accounts aren't counted in them.
        Transfers always use the amount that actually arrived.</div></div></div>`
      : `<p class="small muted">All your accounts are in ${esc(curName(m.home))}. Give an account another currency in its details and a rough rate can be set here.</p>`}
    ${canEdit() ? `<div class="toolbar" style="margin:0"><button class="small primary" id="saveCur">Save currencies</button></div>` : ""}
  </div>`;
}
function wireCurrencyCard() {
  const b = q("#saveCur");
  if (!b) return;
  b.onclick = async () => {
    const rates = {};
    qa("[data-rate]").forEach(i => { rates[i.dataset.rate] = i.value.trim(); });
    try {
      S.money = await api("PUT", "/api/money", { home: q("#homeCur").value, rates });
      for (const k of Object.keys(fmtCache)) delete fmtCache[k];
      toast("Currencies saved"); renderSettings();
    } catch (e) { toast(e.message, true); }
  };
}
// ---------- moving in from another program ----------
// One exported file with every account (QIF, or a CSV export from YNAB, Actual, Mint,
// Firefly III or GnuCash): a preview of each account first, then the person decides
// what happens to each, and everything is brought in.
const MIGRATE_HOWTO = [
  ["Microsoft Money", "File → Export, once for each account (Loose QIF is fine), then choose all the files together here."],
  ["Quicken", "File → Export → QIF File, with \"All accounts\" and Transactions, Account list and Category list ticked."],
  ["Moneydance, KMyMoney, HomeBank, Money Manager Ex, Banktivity", "Export to QIF, all accounts."],
  ["YNAB", "Account settings → Export budget data: use the Register CSV from the download."],
  ["GnuCash", "File → Export → Export Transactions to CSV (all accounts)."],
  ["Actual Budget, Mint, Firefly III", "Export all transactions as CSV."],
];
function bytesToBase64(buf) {
  const b = new Uint8Array(buf); let s = "";
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
}
async function migrateDialog() {
  let files = null, prev = null;
  const aliases = {};
  const intro = `<p>Bring in every account and its history from a file your old program exported. First you'll see what's in it;
      nothing changes until you choose <b>Bring it in</b>.</p>
    <details class="acct-more"><summary>How to export from your old program</summary>
      <ul class="small">${MIGRATE_HOWTO.map(([p, h]) => `<li><b>${esc(p)}:</b> ${esc(h)}</li>`).join("")}</ul>
      <p class="small muted">A CSV from any other program works too when it has Account, Date, Payee, Category and Amount columns.</p></details>
    <div style="margin:12px 0"><input type="file" id="migFile" accept=".qif,.csv,.txt" multiple>
      <div class="small muted">One file, or several chosen together (one per account).</div></div>
    <div id="migPrev"></div>
    <p class="small muted">Comes across: accounts, opening balances, categories, payees and every transaction with its splits, transfers and
      cleared marks. Doesn't: scheduled bills, budgets and investment holdings (set those up here afterwards). A backup is a good idea first.</p>`;
  const typeSel = (key, t) => `<select data-migtype="${esc(key)}">${S.meta.account_types.map(x => `<option ${x === t ? "selected" : ""}>${x}</option>`).join("")}</select>`;
  const draw = () => {
    if (!prev) return;
    const box = q("#migPrev");
    box.innerHTML = `<div class="notice" style="margin:0 0 8px">Found a <b>${esc(prev.format)}</b> file: ${prev.accounts.length} account${prev.accounts.length === 1 ? "" : "s"},
        ${prev.transactions} transactions${prev.new_categories.length ? `, ${prev.new_categories.length} categories to add` : ""}.
        ${Object.entries(prev.skipped || {}).map(([k, v]) => ` Not brought in: ${v} ${esc(k)}.`).join("")}
        ${(prev.skipped || {})["investment entries"] ? `<div class="small" style="margin-top:4px">Investment accounts come in with their transfers, dividends and interest; buys and sells aren't entries here. Check each account's type, and update an investment's value afterwards.</div>` : ""}</div>
      <div style="max-height:320px;overflow:auto"><table class="migtable"><tr><th>Account in the file</th><th>Bring it in as</th><th class="num">Entries</th><th class="num">Balance</th></tr>
      ${prev.accounts.map(a => `<tr><td><b>${esc(a.name)}</b><div class="small muted">${a.first ? niceDate(a.first) + " – " + niceDate(a.last) : ""}${a.transfers ? ` · ${a.transfers} transfers` : ""}${a.splits ? ` · ${a.splits} splits` : ""}</div></td>
        <td><select data-migto="${esc(a.key)}"><option value="new">A new account</option>
            ${S.accounts.map(x => `<option value="${x.id}" ${a.same_name_id === x.id ? "selected" : ""}>Into ${esc(x.name)}</option>`).join("")}
            <option value="skip">Leave it out</option></select>
          <div data-migtypebox="${esc(a.key)}" style="margin-top:4px">${typeSel(a.key, a.type)}</div></td>
        <td class="num">${a.count}</td><td class="num">${fmt(a.balance, false, a)}</td></tr>`).join("")}</table></div>
      ${prev.missing_transfer_accounts.length ? `<div class="notice" style="margin:10px 0 0"><b>Transfers to accounts not in ${files.length > 1 ? "these files" : "this file"}.</b>
          If one is an account above under another name (or its file isn't chosen yet), match it up so the transfers pair:
          ${prev.missing_transfer_accounts.map(m => `<div style="display:flex;gap:8px;align-items:center;margin-top:4px;flex-wrap:wrap">
            <span>"${esc(m.name)}" <span class="small muted">(${m.count})</span> is</span>
            <select data-alias="${esc(m.name)}"><option value="">not in these files: keep a note on each entry</option>
              ${prev.accounts.map(a => `<option value="${esc(a.key)}" ${aliases[m.name] === a.key ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></div>`).join("")}</div>` : ""}
      ${prev.new_categories.length ? `<details style="margin-top:8px"><summary class="small">Categories to add (${prev.new_categories.length})</summary>
        <div class="small muted">${prev.new_categories.map(esc).join(" · ")}</div></details>` : ""}
      <p class="small muted">Into an account you already have, entries already there aren't added twice. A transfer between two accounts in the file
        becomes one transfer; one to an account you leave out is kept as a plain entry with a note.</p>`;
    const sync = () => qa("[data-migto]", box).forEach(s => {
      q(`[data-migtypebox="${CSS.escape(s.dataset.migto)}"]`, box).style.display = s.value === "new" ? "" : "none";
    });
    qa("[data-migto]", box).forEach(s => s.addEventListener("change", sync));
    qa("[data-alias]", box).forEach(s => s.addEventListener("change", () => { aliases[s.dataset.alias] = s.value; }));
    sync();
  };
  const p = dialog("Move in from another program", intro, [{ label: "Cancel" }, { label: "Bring it in", cls: "primary", action: async root => {
    if (!prev) throw new Error("Choose the exported file first");
    const choices = {};
    qa("[data-migto]", root).forEach(s => {
      const k = s.dataset.migto;
      choices[k] = { to: s.value === "new" || s.value === "skip" ? s.value : +s.value,
        type: (q(`[data-migtype="${CSS.escape(k)}"]`, root) || {}).value };
    });
    const btn = q("#dlgFoot button.primary"); btn.disabled = true; btn.textContent = "Bringing it in…";
    try {
      const r = await api("POST", "/api/migrate", { files, choices, aliases });
      await loadBasics();
      toast(`Brought in ${r.added} entries${r.accounts ? ` into ${r.accounts} new account${r.accounts === 1 ? "" : "s"}` : ""}` +
        `${r.transfers ? `, ${r.transfers} transfers` : ""}${r.categories ? `, ${r.categories} categories` : ""}` +
        `${r.duplicates ? ` (${r.duplicates} already there)` : ""}`);
      location.hash = "#/accounts"; render();
    } finally { btn.disabled = false; btn.textContent = "Bring it in"; }
  } }]);
  q("#migFile").onchange = async e => {
    const picked = Array.from(e.target.files || []);
    files = null; prev = null; q("#migPrev").innerHTML = "";
    if (!picked.length) return;
    if (picked.reduce((s, f) => s + f.size, 0) > 30 * 1024 * 1024) { dialogError(new Error("Those files come to over 30 MB. Export fewer years at a time.")); return; }
    q("#migPrev").innerHTML = `<p class="small muted">Reading ${picked.length === 1 ? esc(picked[0].name) : picked.length + " files"}…</p>`;
    try {
      files = [];
      for (const f of picked) files.push({ filename: f.name, content: bytesToBase64(await f.arrayBuffer()) });
      prev = await api("POST", "/api/migrate/preview", { files });
      q("#dlgErr").hidden = true;
      draw();
    } catch (err) { q("#migPrev").innerHTML = ""; dialogError(err); }
  };
  return p;
}

// ---------- shutting down (copies on a computer) ----------
async function shutDownApp() {
  const st = await GET("/api/admin/startup").catch(() => ({}));
  const back = st.menu ? `MoneyThistle in the ${st.platform === "windows" ? "Start menu" : "applications menu"}${st.desktop ? " or on the desktop" : ""}` : "Start MoneyThistle in its folder";
  const ok = await confirmBox(`Shut down MoneyThistle? It saves and makes its backup first. Until it's started again, nobody can open it, on this computer or any other device. ` +
    `To start it again, use ${back}${st.always ? ", or restart the computer" : st.login ? ", or sign in to the computer again" : ""}.`);
  if (!ok) return;
  try { await api("POST", "/api/admin/shutdown"); } catch (e) { toast(e.message, true); return; }
  q("#envbar").innerHTML = ""; q("#backupState").innerHTML = "";
  view().innerHTML = `<div class="card" style="max-width:560px;margin:40px auto;text-align:center">
    <h2>MoneyThistle is shut down</h2><p class="muted" id="sdMsg">Saving and backing up…</p>
    <p class="small">To use it again, start it with ${esc(back)}${st.always ? " (or restart the computer)" : ""}. This page opens it again by itself once it's running.</p></div>`;
  let down = false;
  const tick = async () => {
    try {
      const r = await fetch("/healthz", { cache: "no-store" });
      if (r.ok && down) { location.reload(); return; }
    } catch (e) {
      if (!down) { down = true; const m = q("#sdMsg"); if (m) m.textContent = "Stopped. Your work is saved."; }
    }
    setTimeout(tick, down ? 3000 : 800);
  };
  setTimeout(tick, 800);
}

// Settings: shortcuts, starting with sign-in or with the computer, shutting down.
async function startupCard() {
  const st = await GET("/api/admin/startup").catch(() => null);
  if (!st) return "";
  if (st.in_docker) return `<div class="card"><h2>Starting and stopping</h2><p class="small muted">In Docker, the container starts with the server
    (its restart policy) and keeps MoneyThistle available. Stop it with <code>docker stop moneythistle</code>; closing the browser never stops it.</p></div>`;
  if (!st.supported) return `<div class="card"><h2>Starting and stopping</h2><p class="small muted">${esc(st.error || "This copy can't set up start-ups.")}</p></div>`;
  const how = st.always_how || {};
  // Windows' permission prompt shows on that computer's screen; the copy Windows started
  // can turn it off itself.
  const canAlways = st.local || st.running_from_task;
  const chk = (id, on, label, note, dis) => `<div class="setrow"><label></label><div>
    <label class="check" style="margin:0"><input type="checkbox" id="${id}" ${on ? "checked" : ""} ${dis ? "disabled" : ""}> ${label}</label>
    <div class="small muted" style="margin-top:2px">${note}</div></div></div>`;
  return `<div class="card" id="startupCard"><h2>Starting and stopping</h2>
    <p class="small muted" style="margin-top:-4px">MoneyThistle is a small server that the browser opens. Closing the browser tab doesn't stop it (phones and other
      computers may be using it); <b>⏻ Shut down</b> at the top does.</p>
    ${st.running_from_task ? `<p class="small"><span class="pill green">started with the computer</span> Windows started this copy when the computer turned on.
      ${st.always ? "" : " It no longer starts that way: it keeps running until you shut it down or restart the computer."}</p>` : ""}
    ${st.error ? `<p class="small notice">${esc(st.error)}</p>` : ""}
    ${`
    ${st.shortcuts_supported ? `<div class="setrow"><label>Icons</label><div>
      <div class="small">${st.menu ? '<span class="pill green">in the Start menu</span> ' : ""}<b>MoneyThistle</b> and <b>Stop MoneyThistle</b> are in the ${st.platform === "windows" ? "Start menu" : "applications menu"}${st.menu ? "" : " (added the next time it starts)"}. MoneyThistle opens it in the browser, starting it first if needed.</div>
      <label class="check" style="margin:6px 0 0"><input type="checkbox" id="suDesktop" ${st.desktop ? "checked" : ""}> Also put a MoneyThistle icon on the desktop</label></div></div>` : ""}
    <div class="setrow"><label>Start by itself</label><div>
      <label class="check" style="margin:0"><input type="radio" name="suWhen" value="none" ${!st.login && !st.always ? "checked" : ""} ${canAlways || !st.always ? "" : "disabled"}> Only when I start it (from its icon)</label>
      <label class="check" style="margin:6px 0 0"><input type="radio" name="suWhen" value="login" ${st.login && !st.always ? "checked" : ""} ${canAlways || !st.always ? "" : "disabled"}> When I sign in to this computer</label>
      <div class="small muted" style="margin:0 0 0 22px">Each time you sign in, it starts in the background (no window) and stays available until you sign out or shut it down. Nothing to start first.</div>
      ${how.kind === "button" ? `<label class="check" style="margin:6px 0 0"><input type="radio" name="suWhen" value="always" ${st.always ? "checked" : ""} ${canAlways ? "" : "disabled"}> When the computer starts, even if nobody signs in</label>
        <div class="small muted" style="margin:0 0 0 22px">Windows starts MoneyThistle every time this computer turns on, before anyone signs in, so a bookmark on your phone or another computer works whenever this computer is on. You don't start it yourself. Choosing this asks for Windows administrator permission once, on this computer's screen; it takes over from the next time the computer starts (this copy keeps running until then). Choosing another option later stops it starting with the computer.</div>
        ${canAlways ? "" : `<div class="notice" style="margin:6px 0 0 22px">To change how it starts, open MoneyThistle in a browser <b>on the computer it runs on</b>: Windows asks for permission there.</div>`}`
      : `<div style="margin-top:8px"><b>When the computer starts, even if nobody signs in</b>${st.always ? ' <span class="pill green">set up</span>' : ""}</div>
        <div class="small muted" style="margin:2px 0 4px">It then starts every time the computer turns on; you don't start it yourself. Paste this into a terminal on this computer (it asks for your password):</div>
        <pre class="cmdbox">${esc(how.text || "")}</pre><button class="small" id="suCopy">Copy</button>`}
    </div></div>`}
  </div>`;
}
function wireStartupCard() {
  const card = q("#startupCard");
  if (!card) return;
  const save = async (body, box, wait) => {
    box.disabled = true;
    if (wait) toast(wait);
    try { await api("PUT", "/api/admin/startup", body); toast("Saved"); }
    catch (e) { toast(e.message, true); }
    render();
  };
  if (q("#suDesktop")) q("#suDesktop").onchange = e => save({ desktop: e.target.checked }, e.target);
  // One choice: by hand, at sign-in, or with the computer (which makes sign-in unnecessary).
  const was = (qa("[name=suWhen]", card).find(r => r.checked) || {}).value;
  qa("[name=suWhen]", card).forEach(r => r.onchange = () => {
    const v = r.value;
    const body = { login: v === "login" };
    if (v === "always" || was === "always") body.always = v === "always";
    save(body, r, body.always !== undefined ? "Windows asks for permission on this computer's screen…" : null);
  });
  if (q("#suCopy")) q("#suCopy").onclick = () => { navigator.clipboard && navigator.clipboard.writeText(q(".cmdbox", card).textContent); toast("Copied"); };
}

// ---------- restart (apply updates) ----------
async function restartApp() {
  const v = await GET("/api/version").catch(() => ({}));
  const note = v.in_docker && !v.files_mounted
    ? "This container runs the files built into its image: a new version comes with a new image (Unraid: the Docker tab's update). Restart anyway?"
    : "MoneyThistle will save, make its after-changes backup if needed, and start again with the current files. This takes a few seconds.";
  if (!(await confirmBox(note))) return;
  try { await api("POST", "/api/admin/restart"); } catch (e) { toast(e.message, true); return; }
  view().innerHTML = `<div class="card" style="max-width:520px;margin:40px auto;text-align:center">
    <h2>Restarting MoneyThistle…</h2><p class="muted" id="rsMsg">Waiting for it to come back.</p></div>`;
  const before = v.running;
  const started = Date.now();
  let wentDown = false;
  const tick = async () => {
    try {
      const r = await fetch("/healthz", { cache: "no-store" });
      const b = r.headers.get("X-HomeLedger-Build");
      if (r.ok && (wentDown || (b && b !== before))) { location.reload(); return; }
    } catch (e) { wentDown = true; }
    if (Date.now() - started > 90000) {
      q("#rsMsg").innerHTML = "It hasn't come back yet. If it was started by Craft Anything's Play or a Docker container without a restart policy, start it again there, then reload this page.";
      return;
    }
    setTimeout(tick, 1000);
  };
  setTimeout(tick, 1200);
}

// ---------- new versions (see updates.py) ----------
// How this copy gets a new version: the Windows program installs it (one click, or by itself);
// Docker and Unraid update the container; a copy of the code is replaced by the new one.
function updateHowTo(u) {
  if (u.kind === "docker") return `<div class="small" style="margin-top:6px"><div>Unraid: the Docker tab shows "update ready" for MoneyThistle. Click it to update, or let an auto-update plugin do it.</div>
    <div>Docker Compose: <code translate="no">docker compose pull</code>, then <code translate="no">docker compose up -d</code>.</div></div>`;
  if (u.kind === "source") return `<div class="small" style="margin-top:6px">Get the new version from GitHub, put its files in place of this copy's, then restart.</div>`;
  return "";
}
async function updatesRow() {
  const u = await GET("/api/updates").catch(() => null);
  if (!u) return "";
  const state = u.available ? `<span class="pill amber">Version ${esc(u.latest)} is available</span>
      <a href="${esc(u.url)}" target="_blank" rel="noopener noreferrer">What's new ↗</a>`
    : (u.latest ? `<span class="pill green">up to date</span>` : "");
  return `<div class="setrow"><label>Updates</label><div>
    <div class="small" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${state}
      ${u.checked_at ? `<span class="muted">Checked ${esc(niceDate(u.checked_at.slice(0, 10)))}</span>` : ""}
      ${u.error ? `<span class="muted">GitHub couldn't be reached</span>` : ""}
      <button class="small" id="updCheck">Check now</button></div>
    ${u.can_install ? `<div style="margin-top:6px"><button class="primary small" id="updNow">Update now</button></div>` : (u.available ? updateHowTo(u) : "")}
    <label class="check" style="margin-top:6px"><input type="checkbox" id="updCheckOn" ${u.check ? "checked" : ""}> Check for new versions once a day</label>
    ${u.kind === "windows" ? `<label class="check"><input type="checkbox" id="updAuto" ${u.auto ? "checked" : ""} ${u.check ? "" : "disabled"}> Install new versions by itself</label>` : ""}
    <div class="small muted">Only the newest version number is asked of GitHub: nothing about you or your money is sent.</div>
  </div></div>`;
}
function wireUpdatesRow() {
  const save = async () => {
    try {
      await api("PUT", "/api/updates/settings", { check: q("#updCheckOn").checked, ...(q("#updAuto") ? { auto: q("#updAuto").checked } : {}) });
      toast("Saved"); render();
    } catch (e) { toast(e.message, true); }
  };
  if (q("#updCheckOn")) q("#updCheckOn").onchange = save;
  if (q("#updAuto")) q("#updAuto").onchange = save;
  if (q("#updCheck")) q("#updCheck").onclick = async () => {
    const u = await api("POST", "/api/updates/check");
    toast(u.error ? "GitHub couldn't be reached" : (u.available ? "A new version is available" : "MoneyThistle is up to date"));
    render();
  };
  if (q("#updNow")) q("#updNow").onclick = async () => updateNow(await GET("/api/updates"));
}
// Windows: download, check and install the new version; this page reloads when it's running.
async function updateNow(u) {
  if (!u || !u.can_install) { location.hash = "#/settings/computer"; return; }
  if (!(await confirmBox("Update MoneyThistle now? It saves, makes its backup, installs the new version and starts again by itself. This takes a minute or two."))) return;
  try { await api("POST", "/api/updates/install"); } catch (e) { toast(e.message, true); return; }
  view().innerHTML = `<div class="card" style="max-width:520px;margin:40px auto;text-align:center">
    <h2>Updating MoneyThistle…</h2><p class="muted" id="rsMsg">This page reloads by itself when the new version is running.</p></div>`;
  const started = Date.now();
  const tick = async () => {
    try {
      const r = await fetch("/api/meta", { cache: "no-store" });
      if (r.ok && (await r.json()).version === u.latest) { location.reload(); return; }
    } catch (e) { }
    if (Date.now() - started > 300000) {
      q("#rsMsg").textContent = tr("It's taking longer than expected. Open MoneyThistle from the Start menu, then reload this page.");
      return;
    }
    setTimeout(tick, 3000);
  };
  setTimeout(tick, 5000);
}
// Home, for administrators: a new version is out.
function updateNote(u) {
  if (!u || !u.available) return "";
  return `<div class="notice" style="margin-bottom:12px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
    <span>🎉 MoneyThistle ${esc(u.latest)} is available.</span>
    ${u.can_install ? `<button class="small primary" id="homeUpd">Update now</button>` : `<a class="btn small" href="#/settings/computer">How to update</a>`}
    <a class="btn small" href="${esc(u.url)}" target="_blank" rel="noopener noreferrer">What's new ↗</a></div>`;
}

async function versionCard() {
  const v = await GET("/api/version").catch(() => null);
  if (!v) return "";
  const w = v.where || {};
  const row = (l, val) => val ? `<div class="setrow"><label>${l}</label><div class="small" style="word-break:break-all">${val}</div></div>` : "";
  return `<div class="card"><h2>MoneyThistle on this computer</h2>
    ${w.mode ? row("Running as", `<b>${esc(w.mode)}</b>${w.host ? ` <span class="muted">on ${esc(w.host)}</span>` : ""}`) : ""}
    ${w.app_folder ? row("App files", `<code>${esc(w.app_folder)}</code>`) : ""}
    ${w.data_file ? row("Data folder", `<code>${esc(w.data_file)}</code>`) : ""}
    ${row("Local backups", w.backup_folder ? `<code>${esc(w.backup_folder)}</code>` : "")}
    ${w.log_file ? row("Log", `<code>${esc(w.log_file)}</code>`) : ""}
    ${row("Started", w.started ? `${esc(w.started)} <span class="muted">(process ${esc(w.process_id)})</span>` : "")}
    <div class="setrow"><label>Version</label><div class="small">${v.version ? `<b>${esc(v.version)}</b> · build ` : ""}<code>${esc(v.running || "?")}</code>
      ${v.update_waiting ? `<span class="pill amber">update waiting</span> <span class="muted">files: <code>${esc(v.files)}</code></span>` : ""}</div></div>
    ${v.is_admin ? await updatesRow() : ""}
    <div class="setrow"><label>Restart or shut down</label><div><button id="restartBtn" ${v.can_restart ? "" : "disabled"}>Restart MoneyThistle</button>
      ${v.is_admin && S.meta && S.meta.can_shutdown ? `<button id="shutBtn" title="Saves, makes its backup, and stops: nobody can open it until it's started again">⏻ Shut down</button>` : ""}
      ${v.can_restart ? "" : `<div class="small" style="margin-top:4px">${v.is_admin
        ? "This copy was started in a way that can't restart itself."
        : "Nothing to apply right now: everyone can restart when an update is waiting; at other times an administrator can."}</div>`}
      <div class="small muted" style="margin-top:4px">${v.in_docker
        ? (v.files_mounted ? "Copy the new app files to the server's app folder, then restart to use them."
          : "Restarts the app. New versions come with a new image: see Updates above.")
        : "Applies updated files: it saves, backs up if needed and starts again."}</div></div></div>
    ${v.is_admin ? await networkRow() : ""}
  </div>`;
}

// Desktop copies listen on this computer only unless an administrator lets other
// devices on the home network (or Tailscale) open it. Takes effect after a restart.
async function networkRow() {
  const n = await GET("/api/admin/network").catch(() => null);
  if (!n) return "";
  // Your own address: a name a reverse proxy (e.g. Nginx Proxy Manager) or your DNS
  // points at MoneyThistle, shown first at the bottom of every page.
  const own = `<div class="setrow"><label>Your own address</label><div>
    <div style="display:flex;gap:6px;flex-wrap:wrap" data-guard="#saveUrls"><input id="customUrls" style="flex:1;min-width:220px" placeholder="https://ledger.example.com" value="${esc((n.custom_urls || []).join(", "))}">
      <button class="small" id="saveUrls">Save address</button></div>
    <div class="small muted" style="margin-top:4px">If a reverse proxy such as Nginx Proxy Manager gives MoneyThistle an easier name, enter it here (several: separate with commas). It's shown first at the bottom of every page. MoneyThistle doesn't set up the proxy; keep it reachable only on your home network or Tailscale.</div></div></div>`;
  if (n.fixed) return `<div class="setrow"><label>Other devices</label><div class="small muted">${n.in_docker
    ? "Running in Docker: other devices reach it at the server's address and port."
    : "Set when MoneyThistle was started (--host); change it there."}</div></div>${own}`;
  return own + `<div class="setrow"><label>Other devices</label><div>
    <label class="check" style="margin:0"><input type="checkbox" id="lanToggle" ${n.listen_lan ? "checked" : ""}> Let phones and other computers on my home network (or Tailscale) open MoneyThistle</label>
    <div class="small" style="margin-top:4px">${n.listening_on_network ? '<span class="pill green">open to your network now</span>' : '<span class="pill">this computer only now</span>'}
      ${n.restart_needed ? ' <span class="pill amber">restart to apply</span>' : ""}</div>
    <div class="small muted" style="margin-top:4px">After restarting, use the network address shown at the bottom of the page. On Windows, allow Python through Windows Defender Firewall for <b>private</b> networks when asked (or in its settings if you said no before); otherwise other devices still can't connect.
      <b>Never open it to the public internet.</b></div></div></div>`;
}
document.addEventListener("click", async e => {
  if (!e.target || e.target.id !== "saveUrls") return;
  try {
    await api("PUT", "/api/admin/network", { custom_urls: q("#customUrls").value });
    S.meta = await GET("/api/meta"); showAddresses();
    toast("Address saved"); render();
  } catch (err) { toast(err.message, true); }
});
document.addEventListener("change", async e => {
  if (!e.target || e.target.id !== "lanToggle") return;
  try {
    const n = await api("PUT", "/api/admin/network", { listen_lan: e.target.checked });
    toast(n.restart_needed ? "Saved. Restart MoneyThistle to apply it." : "Saved");
    render();
  } catch (err) { toast(err.message, true); e.target.checked = !e.target.checked; }
});

async function updateBanner() {
  const v = await GET("/api/version").catch(() => null);
  if (!v || !v.update_waiting || !v.can_restart || q("#updNote")) return;
  view().insertAdjacentHTML("afterbegin", `<div class="notice" id="updNote" style="display:flex;align-items:center;gap:10px">
    <span style="flex:1">An update to MoneyThistle is ready. Restart to start using it.</span><button class="small primary" id="updBtn">Restart MoneyThistle</button></div>`);
  q("#updBtn").onclick = restartApp;
}

// Leaving Settings without saving puts the saved look back.
window.addEventListener("hashchange", () => { if (S.ui && !UNSAVED.has("#saveUi")) applyTheme(S.ui); });

// ---------- PEOPLE & ACCESS ----------
const ROLE_TEXT = { owner: "Owner: everything, plus members and connections", editor: "Editor: can enter and change", viewer: "Viewer: can look, not change" };
async function renderPeople(noEnv) {
  qa("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === "settings"));
  S.me = await GET("/api/me");
  drawTopBar();
  const me = S.me.user;
  const [links, envNames, users, shares, people] = await Promise.all([GET("/api/links"), GET("/api/env-names"),
    me.is_admin ? GET("/api/users") : Promise.resolve([]), GET("/api/shares"), GET("/api/people")]);
  const owned = S.me.envs.filter(e => e.role === "owner");
  const mailOn = !!(S.meta && S.meta.password_reset);   // (email is set up)
  const roleSel = (name, cur) => `<select name="${name}">${["owner", "editor", "viewer"].map(r => `<option value="${r}" ${r === cur ? "selected" : ""}>${r}</option>`).join("")}</select>`;
  const statusPill = s => ({ pending: '<span class="pill amber">waiting for approval</span>', active: '<span class="pill green">connected</span>',
    declined: '<span class="pill red">declined</span>', ended: '<span class="pill">ended</span>' }[s] || s);
  view().innerHTML = `<div class="pagehead"><h1>People &amp; access</h1><a class="btn small" href="#/history" title="Who added, changed or deleted what">Change history</a></div>
  ${noEnv ? `<div class="notice">You aren't in any environment yet. Create your own below, or ask someone to add you to theirs.</div>` : ""}
  <p class="small muted" style="margin-top:-6px">Each environment is a separate set of accounts. Only its members can see it:
    owners manage members and connections, editors enter and change things, viewers can only look.</p>
  <div class="grid cols2">
    <div class="grid" style="align-content:start">
      <div class="card"><div class="head"><h2>Environments</h2><button class="small primary" id="newEnv">New environment</button></div>
        ${S.me.envs.map(e => `<div class="card" style="margin:10px 0;padding:12px 14px;box-shadow:none">
          <div class="head"><h2 style="margin:0">${esc(e.name)} <span class="pill">${e.role}</span></h2>
            ${e.role === "owner" ? `<span><button class="small" data-rename="${e.id}">Rename</button> <button class="small danger" data-delenv="${e.id}">Delete</button></span>` : ""}</div>
          <table>${e.members.map(m => `<tr><td>${esc(m.display_name)} <span class="small muted">${esc(m.username)}</span></td>
            <td>${e.role === "owner" && m.id !== me.id ? `<select data-role="${e.id}:${esc(m.username)}">${["owner", "editor", "viewer"].map(r => `<option ${r === m.role ? "selected" : ""}>${r}</option>`).join("")}</select>` : `<span class="pill">${m.role}</span>`}</td>
            <td class="num">${e.role === "owner" && m.id !== me.id ? `<button class="small" data-unmember="${e.id}:${m.id}">Remove</button>` : ""}</td></tr>`).join("")}</table>
          ${e.role === "owner" ? `<form class="toolbar" data-addm="${e.id}" style="margin:8px 0 0"><input name="username" placeholder="user name" style="width:150px">
            ${roleSel("role", "editor")}<button class="small" type="submit">Add person</button></form>` : ""}
        </div>`).join("") || `<div class="empty">No environments yet</div>`}
        <p class="small muted" style="margin-bottom:0">${Object.values(ROLE_TEXT).join(" · ")}</p>
      </div>
      <div class="card"><h2>Your sign-in</h2>
        <form id="meForm" class="form" data-guard="#meForm button[type=submit]">
          <div class="wide"><label>Your name</label><input name="display_name" value="${esc(me.display_name)}"></div>
          <div class="wide"><label>Email <span class="muted">(for "forgot password" links)</span></label><input type="email" name="email" autocomplete="email" value="${esc(me.email || "")}" placeholder="you@example.com"></div>
          <div><label>Current password</label><input type="password" name="current_password" autocomplete="current-password"></div>
          <div><label>New password</label><input type="password" name="password" autocomplete="new-password"></div>
          <div><button class="small primary" type="submit">Save</button></div></form>
        <p class="small muted" style="margin-bottom:0">Signed in as <b>${esc(me.username)}</b>${me.is_admin ? " (administrator)" : ""}.</p></div>
      ${me.is_admin ? `<div class="card"><h2>People who can sign in</h2>
        <table>${users.map(u => `<tr><td>${esc(u.display_name)} <span class="small muted">${esc(u.username)}</span>
            <div class="small muted">${u.email ? esc(u.email) : "no email: can't get a \"forgot password\" link"}</div></td>
          <td>${u.is_admin ? '<span class="pill amber">administrator</span>' : ""}</td>
          <td class="num">${mailOn && u.email && u.id !== me.id ? `<button class="small" data-welcome="${u.id}" title="Their user name, where to open MoneyThistle, what they can see, and a link to choose a new password">Email a welcome</button> ` : ""}<button class="small" data-uemail="${u.id}">Email…</button> <button class="small" data-reset="${u.id}">Password…</button> ${u.id !== me.id ? `<button class="small" data-admin="${u.id}:${u.is_admin ? 0 : 1}">${u.is_admin ? "Not admin" : "Make admin"}</button> <button class="small danger" data-deluser="${u.id}">Delete</button>` : ""}</td></tr>`).join("")}</table>
        <form id="addUser" class="form" style="margin-top:10px">
          <div><label>Name</label><input name="display_name"></div><div><label>User name</label><input name="username"></div>
          <div><label>Starting password${mailOn ? ' <span class="muted">(not needed with a welcome)</span>' : ""}</label><input name="password" type="password" autocomplete="new-password"></div>
          <div><label>Email <span class="muted">(optional)</span></label><input name="email" type="email" autocomplete="off"></div>
          ${owned.length ? `<div><label>Add them to</label><select name="env_id"><option value="">(no environment yet)</option>${owned.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join("")}</select></div>
          <div><label>As</label>${roleSel("role", "editor")}</div>` : ""}
          ${mailOn ? `<div class="wide" style="grid-column:1/-1"><label class="check"><input type="checkbox" name="welcome" checked> Email them a welcome</label>
            <div class="small muted" style="margin-left:24px">Their user name, where to open MoneyThistle, what they can see, and a link to choose their own password (it works once, for 3 days).</div></div>`
            : `<div class="wide small muted" style="grid-column:1/-1">Set up email under Settings › Notifications to send new people a welcome with a link to choose their own password.</div>`}
          <div><label class="check"><input type="checkbox" name="is_admin"> Administrator</label></div>
          <div><label class="check" title="New people start Simple: extras folded under More options. They can change it in Settings › Look."><input type="checkbox" name="show_everything"> Show them everything</label></div>
          <div><button class="small primary" type="submit">Add person</button></div></form>
        <p class="small muted" style="margin-bottom:0">Administrators manage sign-ins, backups and restarts. Someone added sees no money until they're in an
          environment: choose one above, or an environment's owner adds them later.</p></div>` : ""}
    </div>
    <div class="grid" style="align-content:start">
      <div class="card"><div class="head"><h2>Connections between environments</h2>${owned.length ? '<button class="small primary" id="newLink">Connect an account</button>' : ""}</div>
        <p class="small muted" style="margin-top:0">A connection lets money move between one account here and one in another environment
          (for example personal checking ↔ business checking). An owner of one side asks; an owner of the other side approves and picks the account.
          Once connected, choose "Transfer to …" in either register and the other side is filled in automatically.</p>
        <table>${links.map(l => `<tr><td>${esc(l.account_a_name || "?")} <span class="small muted">(${esc(l.env_a_name)})</span>
            ↔ ${l.account_b_name ? esc(l.account_b_name) : '<span class="muted">to be chosen</span>'} <span class="small muted">(${esc(l.env_b_name)})</span>
            <div class="small muted">asked by ${esc(l.created_by_name || "?")} ${l.created ? "on " + niceDate(l.created.slice(0, 10)) : ""}${l.note ? " · " + esc(l.note) : ""}</div></td>
          <td>${statusPill(l.status)}</td>
          <td class="num">${l.can_approve ? `<button class="small primary" data-approve="${l.id}">Approve…</button> <button class="small" data-decline="${l.id}">Decline</button>`
            : (l.can_end ? `<button class="small" data-endlink="${l.id}">${l.status === "pending" ? "Cancel" : "End"}</button>` : "")}</td></tr>`).join("")}</table>
        ${links.length ? "" : `<div class="empty">No connections yet</div>`}
      </div>
      <div class="card"><div class="head"><h2>Shared accounts</h2>${owned.length ? '<button class="small primary" id="newShare">Share an account</button>' : ""}</div>
        <p class="small muted" style="margin-top:0">Show one account in another environment too, for example your checking account in your
          wife's personal environment. It stays one account with one register; the other environment sees it in its account list,
          either to look at or to enter transactions as well. An owner there approves it.</p>
        <table>${shares.map(s => `<tr><td><b>${esc(s.account_name || "?")}</b> <span class="small muted">(${esc(s.env_a_name)})</span> → ${s.target_name ? esc(s.target_name) + " · " : ""}${s.env_b_name ? esc(s.env_b_name) : '<span class="muted">not accepted yet</span>'}
            <div class="small muted">${s.access === "edit" ? "can view and enter transactions" : "view only"}${s.include_bills ? " · with its bills &amp; deposits" : ""} · asked by ${esc(s.created_by_name || "?")}${s.note ? " · " + esc(s.note) : ""}</div></td>
          <td>${statusPill(s.status)}</td>
          <td class="num">${s.can_approve ? `<button class="small primary" data-sapprove="${s.id}">Approve</button> <button class="small" data-sdecline="${s.id}">Decline</button>` : ""}
            ${s.i_own_a && ["pending", "active"].includes(s.status) ? `<button class="small" data-saccess="${s.id}:${s.access === "edit" ? "view" : "edit"}">${s.access === "edit" ? "Make view only" : "Allow entering"}</button> <button class="small" data-sbills="${s.id}:${s.include_bills ? 0 : 1}">${s.include_bills ? "Stop sharing bills" : "Share bills too"}</button>` : ""}
            ${s.can_end && !s.can_approve ? `<button class="small" data-send="${s.id}">${s.status === "pending" ? "Cancel" : "Stop sharing"}</button>` : ""}</td></tr>`).join("")}</table>
        ${shares.length ? "" : `<div class="empty">No shared accounts yet</div>`}
      </div>
    </div>
  </div>`;
  const again = async msg => { if (msg) toast(msg); await loadBasics().catch(() => {}); renderPeople(); };
  const run = async (fn, msg) => { try { await fn(); again(msg); } catch (e) { toast(e.message, true); } };
  q("#newEnv").onclick = () => dialog("New environment", `<label>Name</label><input name="name" placeholder="Business">
    <p class="small muted">You'll be its owner. It starts empty, with its own accounts, categories, bills and budget.</p>`,
    [{ label: "Cancel" }, { label: "Create", cls: "primary", action: async root => {
      const r = await api("POST", "/api/envs", formData(root)); S.env = r.id; localStorage.setItem("hl-env", r.id); again("Environment created");
    } }]);
  qa("[data-rename]").forEach(b => b.onclick = () => dialog("Rename environment", `<label>Name</label><input name="name" value="${esc(S.me.envs.find(e => e.id == b.dataset.rename).name)}">`,
    [{ label: "Cancel" }, { label: "Save", cls: "primary", action: async root => { await api("PUT", "/api/envs/" + b.dataset.rename, formData(root)); again("Renamed"); } }]));
  qa("[data-delenv]").forEach(b => b.onclick = async () => {
    if (await confirmBox("Delete this environment? It must have no accounts left.")) run(() => api("DELETE", "/api/envs/" + b.dataset.delenv), "Deleted");
  });
  qa("[data-role]").forEach(s => s.onchange = () => { const [env, user] = s.dataset.role.split(":"); run(() => api("PUT", `/api/envs/${env}/members`, { username: user, role: s.value }), "Saved"); });
  qa("[data-unmember]").forEach(b => b.onclick = async () => { const [env, uid] = b.dataset.unmember.split(":");
    if (await confirmBox("Remove this person from the environment? They won't see it any more.")) run(() => api("DELETE", `/api/envs/${env}/members/${uid}`), "Removed"); });
  qa("[data-addm]").forEach(f => f.onsubmit = e => { e.preventDefault(); run(() => api("PUT", `/api/envs/${f.dataset.addm}/members`, formData(f)), "Added"); });
  q("#meForm").onsubmit = e => { e.preventDefault(); const d = formData(e.target); if (!d.password) { delete d.password; delete d.current_password; }
    run(() => api("PUT", "/api/me", d), "Saved"); };
  if (q("#addUser")) q("#addUser").onsubmit = async e => {
    e.preventDefault();
    try {
      const r = await api("POST", "/api/users", formData(e.target));
      if (r.welcome_error || r.welcome_note) {
        await again();
        toast(r.welcome_error ? "Person added, but the welcome email couldn't be sent: " + r.welcome_error
          : "Person added and welcomed. " + r.welcome_note, true);
      } else again(r.welcome_sent_to ? `Person added; welcome sent to ${r.welcome_sent_to}` : "Person added");
    } catch (err) { toast(err.message, true); }
  };
  qa("[data-welcome]").forEach(b => b.onclick = async () => {
    try {
      const r = await api("POST", `/api/users/${b.dataset.welcome}/welcome`);
      toast(`Welcome sent to ${r.welcome_sent_to}` + (r.welcome_note ? ". " + r.welcome_note : ""), !!r.welcome_note);
    } catch (err) { toast(err.message, true); }
  });
  qa("[data-reset]").forEach(b => b.onclick = () => dialog("Set a new password", `<label>New password (8+ characters)</label><input type="password" name="password" autocomplete="new-password">
    <p class="small muted">They'll be signed out everywhere and use this password next time.</p>`,
    [{ label: "Cancel" }, { label: "Set password", cls: "primary", action: async root => { await api("PUT", "/api/users/" + b.dataset.reset, formData(root)); again("Password set"); } }]));
  qa("[data-uemail]").forEach(b => b.onclick = () => {
    const u = users.find(x => x.id == b.dataset.uemail);
    dialog("Email for " + (u.display_name || u.username), `<label>Email address</label><input type="email" name="email" value="${esc(u.email || "")}" placeholder="name@example.com">
      <p class="small muted">Where a "forgot password" link goes, and a note whenever their password changes. Leave it empty to remove it.</p>`,
      [{ label: "Cancel" }, { label: "Save", cls: "primary", action: async root => { await api("PUT", "/api/users/" + u.id, formData(root)); again("Saved"); } }]);
  });
  qa("[data-admin]").forEach(b => b.onclick = () => { const [id, v] = b.dataset.admin.split(":"); run(() => api("PUT", "/api/users/" + id, { is_admin: v === "1" }), "Saved"); });
  qa("[data-deluser]").forEach(b => b.onclick = async () => { if (await confirmBox("Delete this sign-in? Their environments stay with their other owners.")) run(() => api("DELETE", "/api/users/" + b.dataset.deluser), "Deleted"); });
  qa("[data-decline]").forEach(b => b.onclick = async () => { if (await confirmBox("Decline this connection request?")) run(() => api("POST", `/api/links/${b.dataset.decline}/decline`), "Declined"); });
  qa("[data-endlink]").forEach(b => b.onclick = async () => {
    if (await confirmBox("End this connection? Transfers already made stay in both registers, no longer tied together.")) run(() => api("POST", `/api/links/${b.dataset.endlink}/end`), "Ended");
  });
  qa("[data-approve]").forEach(b => b.onclick = async () => {
    const l = links.find(x => x.id == b.dataset.approve);
    const accts = await GET(`/api/envs/${l.env_b}/accounts`);
    dialog("Approve connection", `<p><b>${esc(l.account_a_name)}</b> (${esc(l.env_a_name)}) asks to connect with <b>${esc(l.env_b_name)}</b>.
      Once approved, people who can edit either side can move money between the two accounts.</p>
      <label>Connect it with</label><select name="account_id">${accts.map(a => `<option value="${a.id}" ${a.id === l.account_b ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select>`,
      [{ label: "Cancel" }, { label: "Approve", cls: "primary", action: async root => { await api("POST", `/api/links/${l.id}/approve`, formData(root)); again("Connected"); } }]);
  });
  qa("[data-sapprove]").forEach(b => b.onclick = () => {
    const s = shares.find(x => x.id == b.dataset.sapprove);
    const targets = owned.filter(e => e.id !== s.env_a);
    if (s.needs_env && !targets.length) { toast("Create an environment of your own first (New environment), then accept.", true); return; }
    dialog("Accept shared account", `<p><b>${esc(s.created_by_name || "Someone")}</b> shares <b>${esc(s.account_name)}</b> with you
      (${s.access === "edit" ? "view it and enter transactions" : "view only"})${s.include_bills ? ", together with its scheduled bills &amp; deposits" : ""}.</p>
      ${s.needs_env ? `<label>Show it in my environment</label><select name="env_id">${targets.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join("")}</select>
        <p class="small muted">Everyone in that environment will see it, and it counts in that environment's totals and reports.</p>`
        : `<p>It will show in <b>${esc(s.env_b_name)}</b>.</p>`}`,
      [{ label: "Cancel" }, { label: "Accept", cls: "primary", action: async root => { await api("POST", `/api/shares/${s.id}/approve`, formData(root)); again("Shared"); } }]);
  });
  qa("[data-sdecline]").forEach(b => b.onclick = async () => { if (await confirmBox("Decline this shared account?")) run(() => api("POST", `/api/shares/${b.dataset.sdecline}/decline`), "Declined"); });
  qa("[data-send]").forEach(b => b.onclick = async () => {
    if (await confirmBox("Stop sharing this account? It disappears from the other environment; nothing in it is deleted.")) run(() => api("POST", `/api/shares/${b.dataset.send}/end`), "Stopped");
  });
  qa("[data-saccess]").forEach(b => b.onclick = () => { const [id, a] = b.dataset.saccess.split(":"); run(() => api("PUT", "/api/shares/" + id, { access: a }), "Saved"); });
  if (q("#newShare")) q("#newShare").onclick = async () => {
    const body = `<div class="form" style="grid-template-columns:1fr 1fr">
      <div><label>From your environment</label><select name="env_id">${owned.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join("")}</select></div>
      <div><label>Account</label><select name="account_id"></select></div>
      <div><label>Share with</label><select name="to_user">${people.map(u => `<option value="${u.id}" ${u.id === me.id ? "" : ""}>${esc(u.display_name)} (${esc(u.username)})${u.id === me.id ? " - me, another of my environments" : ""}</option>`).join("")}</select></div>
      <div><label>They may</label><select name="access"><option value="edit">view it and enter transactions</option><option value="view">only view it</option></select></div>
      <div style="grid-column:1/-1"><label class="check"><input type="checkbox" name="include_bills" checked> Share related Bills &amp; Deposits</label><div class="small muted" style="margin-left:24px">Its scheduled bills and deposits show in the other environment too, and ones added there (when entering is allowed) show here.</div></div><div style="grid-column:1/-1"><label>Note for the other owner (optional)</label><input name="note" placeholder="Our joint checking"></div></div>
      <p class="small muted">They choose which of their environments it appears in when they accept, so you never pick from other people's environment names.</p>`;
    const p = dialog("Share an account", body, [{ label: "Cancel" }, { label: "Share", cls: "primary", action: async root => {
      await api("POST", "/api/shares", formData(root)); again("Shared (or waiting for approval)");
    } }]);
    const root = q("#dlgBody");
    const fill = async () => {
      const mine = q("[name=env_id]", root).value;
      const a = await GET(`/api/envs/${mine}/accounts`);
      q("[name=account_id]", root).innerHTML = a.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join("");
    };
    q("[name=env_id]", root).onchange = fill;
    fill();
    return p;
  };
  if (q("#newLink")) q("#newLink").onclick = async () => {
    const body = `<div class="form" style="grid-template-columns:1fr 1fr">
      <div><label>From your environment</label><select name="env_id">${owned.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join("")}</select></div>
      <div><label>Account</label><select name="account_id"></select></div>
      <div><label>To environment</label><select name="other_env_id">${envNames.map(e => `<option value="${e.id}">${esc(e.name)}</option>`).join("")}</select></div>
      <div><label>Account there</label><select name="other_account_id"></select></div>
      <div style="grid-column:1/-1"><label>Note for the other owner (optional)</label><input name="note" placeholder="For moving money into the business"></div></div>
      <p class="small muted">The other environment's owners have to approve it. If you can't see that environment, they pick the account when they approve.</p>`;
    const p = dialog("Connect an account", body, [{ label: "Cancel" }, { label: "Send request", cls: "primary", action: async root => {
      const d = formData(root); if (!d.other_account_id) delete d.other_account_id;
      await api("POST", "/api/links", d); again("Request sent");
    } }]);
    const root = q("#dlgBody");
    const fillMine = async () => {
      const a = await GET(`/api/envs/${q("[name=env_id]", root).value}/accounts`);
      q("[name=account_id]", root).innerHTML = a.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join("");
      const mine = q("[name=env_id]", root).value;
      qa("[name=other_env_id] option", root).forEach(o => o.disabled = o.value === mine);
      const sel = q("[name=other_env_id]", root);
      if (sel.value === mine) { const first = qa("option", sel).find(o => !o.disabled); if (first) sel.value = first.value; }
      fillOther();
    };
    const fillOther = async () => {
      const id = +q("[name=other_env_id]", root).value;
      const member = S.me.envs.some(e => e.id === id);
      const sel = q("[name=other_account_id]", root);
      if (!member) { sel.innerHTML = `<option value="">(their owner picks it)</option>`; sel.disabled = true; return; }
      const a = await GET(`/api/envs/${id}/accounts`);
      sel.disabled = false;
      sel.innerHTML = `<option value="">(let their owner pick)</option>` + a.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join("");
    };
    q("[name=env_id]", root).onchange = fillMine;
    q("[name=other_env_id]", root).onchange = fillOther;
    fillMine();
    return p;
  };
}

// ---------- router ----------
// ---------- QUICK ADD (made for phones) ----------
// One screen for entering a purchase, deposit or transfer with a thumb: big type
// buttons, a large amount field (the phone's number pad), the last account remembered,
// the category filled in from the payee, one tap to save (with Undo), and today's due
// items to record with one tap. Accounts shared with you for entering are included.
const quick = { kind: "out", last: [] };
async function renderQuick() {
  await loadBasics();
  const shares = (await GET("/api/shares/incoming").catch(() => [])).filter(a => a.can_edit && !a.closed);
  const due = await GET("/api/bills?days=0").catch(() => ({ upcoming: [] }));
  const today = todayISO();
  const dueNow = (due.upcoming || []).filter(u => u.first && u.date <= today);
  const own = S.accounts.filter(a => !a.closed);
  const saved = localStorage.getItem("hl-quick-acct-" + S.env);
  const acctVal = saved && (own.some(a => String(a.id) === saved) || shares.some(s => "sh:" + s.share_id === saved))
    ? saved : String((own.find(a => a.type === "Checking") || own[0] || {}).id || "");
  const k = quick.kind;
  view().innerHTML = `<div class="quick">
    <h1 style="margin-bottom:10px">Quick add</h1>
    <div class="qkinds" role="group" aria-label="What kind">
      ${[["out", "− Spent", "out"], ["in", "+ Received", "green"], ["move", "⇄ Transfer", "move"]].map(([v, l, c]) =>
        `<button type="button" class="qkind ${c} ${k === v ? "on" : ""}" data-qk="${v}" aria-pressed="${k === v}">${l}</button>`).join("")}
    </div>
    <label class="qlabel" for="qAmount">Amount</label>
    <div class="qamount"><span>${esc(moneyFormat(homeCur()).formatToParts(0).find(p => p.type === "currency")?.value || "$")}</span><input id="qAmount" inputmode="decimal" autocomplete="off" placeholder="0.00" enterkeyhint="next"></div>
    <label class="qlabel" for="qAcct">${k === "in" ? "Into" : "From"} account</label>
    <select id="qAcct" class="qbig">${own.map(a => `<option value="${a.id}" ${String(a.id) === acctVal ? "selected" : ""}>${esc(a.name)}</option>`).join("")}
      ${shares.length && k !== "move" ? `<optgroup label="Shared with you">${shares.map(s => `<option value="sh:${s.share_id}" ${"sh:" + s.share_id === acctVal ? "selected" : ""}>${esc(s.name)} (${esc(s.shared_by)})</option>`).join("")}</optgroup>` : ""}</select>
    ${k === "move" ? `<label class="qlabel" for="qTo">To account</label><select id="qTo" class="qbig">${own.filter(a => String(a.id) !== acctVal).map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join("")}</select><div id="qStmt" style="margin-top:8px"></div>`
      : `<label class="qlabel" for="qPayee">${k === "in" ? "From" : "Paid to"}</label>
         <input id="qPayee" class="qbig" list="qPayees" autocomplete="off" placeholder="${k === "in" ? "Who paid you" : "Store, person, bill…"}">
         <datalist id="qPayees">${S.payees.map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>
         <label class="qlabel" for="qCat">Category</label><select id="qCat" class="qbig"></select>`}
    <details class="qmore"><summary>Date, memo</summary>
      <div class="form" style="margin-top:6px"><div><label>Date</label><input type="date" id="qDate" value="${today}"></div>
      <div><label>Memo</label><input id="qMemo"></div></div></details>
    <button class="primary qsave" id="qSave" type="button">Save</button>
    <div id="qLast">${quick.last.length ? `<div class="small muted" style="margin-top:10px">Saved just now:</div>` + quick.last.map((l, i) => `<div class="qlast"><span>${esc(l.text)}</span><button class="small" data-qundo="${i}">Undo</button></div>`).join("") : ""}</div>
    ${dueNow.length ? `<h2 style="margin-top:22px">Due today</h2>
      ${dueNow.map(u => `<div class="qdue k-${kindOf(u)}"><div><b>${esc(u.payee || "Transfer")}</b> ${u.overdue ? '<span class="pill red">overdue</span>' : ""}<div class="small muted">${esc(u.account_name)} · ${billAmount(u)}</div></div>
        <button class="small primary" data-qenter="${u.id}">Record</button></div>`).join("")}` : ""}
  </div>`;
  // Categories: this environment's, or the shared account's own when one is chosen.
  let catsFor = S.cats;
  const shareOf = v => String(v).startsWith("sh:") ? shares.find(s => "sh:" + s.share_id === v) : null;
  const fillCats = async () => {
    const sel = q("#qCat"); if (!sel) return;
    const sh = shareOf(q("#qAcct").value);
    catsFor = sh ? await api("GET", "/api/categories", undefined, sh).catch(() => []) : S.cats;
    const want = k === "in" ? "income" : "expense";
    sel.innerHTML = `<option value="">(no category)</option>` + catsFor.filter(c => c.kind === want)
      .map(c => `<option value="${c.id}">${esc(catFull(c))}</option>`).join("");
  };
  await fillCats();
  q("#qAcct").onchange = async () => { localStorage.setItem("hl-quick-acct-" + S.env, q("#qAcct").value); if (k === "move") renderQuick(); else await fillCats(); };
  // A known payee brings its usual category (only from this environment's list).
  if (q("#qPayee")) q("#qPayee").addEventListener("change", () => {
    const p = S.payees.find(x => x.name.toLowerCase() === q("#qPayee").value.trim().toLowerCase());
    if (p && p.category_id && !shareOf(q("#qAcct").value) && q(`#qCat option[value="${p.category_id}"]`)) q("#qCat").value = String(p.category_id);
  });
  qa("[data-qk]").forEach(b => b.onclick = () => { quick.kind = b.dataset.qk; renderQuick(); });
  // Paying a card: one tap for its last statement's balance.
  if (q("#qTo")) {
    const pick = () => statementButton(q("#qTo").value, q("#qStmt"), left => { q("#qAmount").value = (left / 100).toFixed(2); });
    q("#qTo").addEventListener("change", pick); pick();
  }
  q("#qAmount").focus();
  q("#qSave").onclick = async () => {
    const amt = parseAmount(q("#qAmount").value);
    if (!(amt > 0)) { toast("Enter an amount", true); q("#qAmount").focus(); return; }
    const acct = q("#qAcct").value, sh = shareOf(acct);
    const body = { date: q("#qDate").value || today, memo: q("#qMemo").value.trim(),
      amount: (k === "in" ? "" : "-") + amt.toFixed(2), account_id: sh ? sh.id : +acct };
    let text;
    if (k === "move") {
      body.transfer_account_id = +q("#qTo").value;
      const from = S.accounts.find(a => a.id == body.account_id) || {}, to = S.accounts.find(a => a.id == body.transfer_account_id) || {};
      if (from.currency && to.currency && from.currency !== to.currency) {
        // Two currencies: what arrived on the other side.
        const got = await askReceived(from, to, Math.round(amt * 100));
        if (got == null) return;
        body.received = got;
      }
      text = `${fmt(Math.round(amt * 100), true, from)} to ${to.name || ""}`;
    } else {
      body.payee = q("#qPayee").value.trim();
      if (q("#qCat").value) body.category_id = +q("#qCat").value;
      text = `${k === "in" ? "+" : "−"}${fmt(Math.round(amt * 100), true)} ${body.payee}`;
    }
    q("#qSave").disabled = true;
    try {
      const r = await api("POST", "/api/transactions", body, sh || undefined);
      quick.last = [{ id: r.id, sh, text }].concat(quick.last).slice(0, 3);
      toast("Saved"); await loadBasics(); renderQuick();
    } catch (e) { toast(e.message, true); q("#qSave").disabled = false; }
  };
  q("#qAmount").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); (q("#qPayee") || q("#qSave")).focus(); } });
  qa("[data-qundo]").forEach(b => b.onclick = async () => {
    const l = quick.last[+b.dataset.qundo];
    try { await api("DELETE", "/api/transactions/" + l.id, undefined, l.sh || undefined); quick.last.splice(+b.dataset.qundo, 1); toast("Removed"); renderQuick(); }
    catch (e) { toast(e.message, true); }
  });
  qa("[data-qenter]").forEach(b => b.onclick = () => enterBill(+b.dataset.qenter, dueNow.find(u => u.id == b.dataset.qenter)).then(() => renderQuick()));
}

async function render() {
  const parts = (location.hash || "#/home").slice(2).split("/");
  const tab = parts[0] || "home";
  S.viewTarget = null;
  // People, Categories and Backups now live under Settings: old addresses still work.
  const moved = { people: "people", categories: "categories", backup: "backups", backups: "backups" };
  if (moved[tab]) { location.replace("#/settings/" + moved[tab]); return; }
  qa("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === tab));
  if (tab === "reset") { renderReset(parts.slice(1).join("/")); return; }
  try {
    // Leaving a shared account: back to this environment's own lists.
    if (S.shareCtx && !(tab === "accounts" && String(parts[1] || "").startsWith("s"))) {
      S.shareCtx = null; await loadBasics();
    }
    if (!S.meta || !S.me) await loadBasics();
    if (tab === "help") { renderHelp(parts[1]); return; }
    if (tab === "history") { await renderHistory(); return; }
    if (!S.env) { await renderPeople(true); return; }
    if (tab === "accounts" && String(parts[1] || "").startsWith("s")) await renderShared(+parts[1].slice(1));
    else if (tab === "accounts") await renderAccounts(parts[1] ? +parts[1] : null);
    else if (tab === "bills") await renderBills(parts[1]);
    else if (tab === "budget") await renderBudget();
    else if (tab === "reports") { if (parts[1]) reportState.kind = parts[1]; await renderReports(); }
    else if (tab === "files") await renderFiles();
    else if (tab === "settings") await renderSettings(parts[1]);
    else if (tab === "quick") await renderQuick();
    else await renderHome();
    document.body.classList.toggle("on-quick", tab === "quick");
    // Something in another of my environments (all-environments views): open it there.
    qa("[data-goenv]").forEach(a => a.onclick = async e => {
      e.preventDefault(); await goEnv(+a.dataset.goenv); location.hash = "#/accounts/" + a.dataset.goacct; render();
    });
    helpLinkInTitle(tab);
    maybeStartTour(tab);
    if (tab !== "home") refreshBackupState();
    if (tab !== "settings") updateBanner();
    if (S.stale && !q("#staleNote")) view().insertAdjacentHTML("afterbegin", `<div class="notice" id="staleNote">${esc(STALE_MSG)}</div>`);
    if (S.pageOld && !q("#reloadNote")) {
      view().insertAdjacentHTML("afterbegin", `<div class="notice" id="reloadNote" style="display:flex;align-items:center;gap:10px">
        <span style="flex:1">MoneyThistle was updated while this page was open. Reload it to use the new version.</span>
        <button class="small primary" id="reloadNow">Reload</button></div>`);
      q("#reloadNow").onclick = () => location.reload();   // (no inline handlers: the page's security policy allows only its own scripts)
    }
  } catch (e) {
    if (e instanceof NeedSignIn) {
      // Signed out: the language last used on this device, or this browser's.
      S.me = null; try { await setLang(localStorage.getItem("hl-lang") || ""); } catch (x) { }
      renderSignIn(e.message === "setup"); return;
    }
    const msg = e.message === "Not found" || S.stale ? STALE_MSG : e.message;
    view().innerHTML = `<div class="notice err">${esc(msg)}</div>`;
  }
}
// ---------- unsaved settings ----------
// A settings card with its own Save button carries data-guard="<that button>". Changing
// something in it marks it unsaved until that button is clicked; leaving the page then asks
// to save, not save, or keep editing (and reloading or closing the tab gets the browser's
// own warning).
const UNSAVED = new Set();
const markUnsaved = e => {
  if (!e.isTrusted || !e.target.closest) return;
  const c = e.target.closest("[data-guard]");
  if (c && c.closest("#view")) UNSAVED.add(c.dataset.guard);
};
document.addEventListener("input", markUnsaved, true);
document.addEventListener("change", markUnsaved, true);
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("button");
  if (b) for (const sel of [...UNSAVED]) if (b.matches(sel)) {
    UNSAVED.delete(sel);
    // (a save that was refused, with its error showing, still counts as unsaved)
    const t = document.getElementById("toast");
    t.className = "";
    setTimeout(() => { if (t.className.includes("err") && document.querySelector(sel)) UNSAVED.add(sel); }, 900);
  }
}, true);
document.addEventListener("submit", e => {
  for (const sel of [...UNSAVED]) if (e.target.querySelector(sel)) UNSAVED.delete(sel);
}, true);
window.addEventListener("beforeunload", e => { if (UNSAVED.size) { e.preventDefault(); e.returnValue = ""; } });
// Saving on the way out: each unsaved card's Save button, then a moment for the answers; a
// save that failed (its error shows) keeps the page open.
async function saveUnsaved() {
  const sels = [...UNSAVED], t = document.getElementById("toast");
  t.className = "";
  for (const sel of sels) { const b = q(sel); if (b) b.click(); }
  await new Promise(r => setTimeout(r, 900));
  if (t.className.includes("err")) { sels.forEach(x => UNSAVED.add(x)); return false; }
  return true;
}
let shownHash = location.hash, routeBusy = false;
window.addEventListener("hashchange", async () => {
  if (routeBusy) return;
  if (UNSAVED.size) {
    const to = location.hash;
    history.replaceState(null, "", shownHash || "#/");   // stay here while asking (no hashchange)
    routeBusy = true;
    const pick = await askSaveChanges("You changed settings here without saving. Save them before leaving?");
    routeBusy = false;
    if (pick === "keep") return;
    if (pick === "save" && !(await saveUnsaved())) return;
    UNSAVED.clear();
    if (S.ui) applyTheme(S.ui);          // (a look tried but not kept goes back)
    location.hash = to;
    return;
  }
  shownHash = location.hash;
  render();
});
// Narrow screens: the tabs fold into a Menu button; picking a tab closes it again.
(function () {
  const top = q("header.top"), btn = q("#menuBtn");
  const set = open => { top.classList.toggle("open", open); btn.setAttribute("aria-expanded", String(open)); };
  btn.onclick = () => set(!top.classList.contains("open"));
  qa("#tabs a").forEach(a => a.addEventListener("click", () => set(false)));
  window.addEventListener("hashchange", () => set(false));
  // The logo goes Home; already there, it closes the menu and refreshes the page.
  q("#brandHome").addEventListener("click", e => {
    set(false);
    if (location.hash === "#/") { e.preventDefault(); render(); }
  });
})();

// ---------- CHANGE HISTORY ----------
// Who added, changed or deleted what, when and where; entries and scheduled items can be
// undone (by someone who may change that environment).
const HIST_FIELDS = {
  transaction: [["date", "Date", v => niceDate(v)], ["payee", "Payee"], ["amount", "Amount", v => fmt(v, true)], ["_category", "Category"],
    ["_account", "Account"], ["memo", "Memo"], ["number", "Number"], ["status", "Status", v => ({ C: "cleared", R: "reconciled" }[v] || "not cleared")]],
  bill: [["payee", "Payee"], ["amount", "Amount", v => fmt(v, true)], ["frequency", "How often"], ["next_date", "Next", v => niceDate(v)],
    ["_account", "Account"], ["_to_account", "To"], ["_category", "Category"], ["active", "Active", v => v ? "yes" : "no"]],
  account: [["name", "Name"], ["type", "Type"], ["opening_balance", "Opening balance", v => fmt(v, true)], ["closed", "Closed", v => v ? "yes" : "no"]],
  category: [["name", "Name"], ["kind", "Kind"], ["tax_related", "Tax related", v => v ? "yes" : "no"]],
};
function historyDiff(c) {
  const f = HIST_FIELDS[c.kind];
  if (!f || c.action !== "change" && c.action !== "undo" || !c.before || !c.after) return "";
  const show = (fn, v) => v == null || v === "" ? "—" : esc(fn ? fn(v) : String(v));
  const diffs = f.filter(([k]) => String(c.before[k] ?? "") !== String(c.after[k] ?? ""))
    .map(([k, label, fn]) => `<li>${label}: <s>${show(fn, c.before[k])}</s> → <b>${show(fn, c.after[k])}</b></li>`);
  return diffs.length ? `<ul class="histdiff">${diffs.join("")}</ul>` : "";
}
function historyOps(ops) {
  return ops.map(o => `<div class="histop ${o.undone ? "undone" : ""}">
      <div class="histhead"><span class="small muted">${esc(niceDate(o.at.slice(0, 10)))} ${esc(o.at.slice(11, 16))}</span>
        <b>${esc(o.user)}</b>${reportScopeAll() || (S.me.envs || []).length > 1 ? ` <span class="pill plain">${esc(o.env_name)}</span>` : ""}
        ${o.undone ? '<span class="pill">undone</span>' : ""}
        <span style="flex:1"></span>${o.can_undo ? `<button class="small" data-undo="${esc(o.op)}" title="Put back how it was before this">Undo</button>` : ""}</div>
      ${o.changes.slice(0, 12).map(c => `<div class="histline k-${c.action}">${esc(c.summary)}${historyDiff(c)}</div>`).join("")}
      ${o.changes.length > 12 ? `<div class="small muted">and ${o.changes.length - 12} more</div>` : ""}</div>`).join("")
    || `<div class="empty">No changes recorded yet.</div>`;
}
function wireUndo(again) {
  qa("[data-undo]").forEach(b => b.onclick = async () => {
    if (!(await confirmBox("Undo this? Added entries are removed, changed ones go back to how they were, deleted ones come back."))) return;
    try { const r = await api("POST", "/api/history/undo", { op: b.dataset.undo }); toast(`Undone (${r.undone} change${r.undone === 1 ? "" : "s"})`); await loadBasics(); again(); }
    catch (e) { toast(e.message, true); }
  });
}
const histView = { env: "all", user: "", q: "", offset: 0 };
async function renderHistory() {
  qa("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === "people"));
  const envs = S.me.envs || [];
  const people = await GET("/api/people").catch(() => []);
  const qs = new URLSearchParams({ env: histView.env, offset: histView.offset });
  if (histView.user) qs.set("user", histView.user);
  if (histView.q) qs.set("q", histView.q);
  const data = await GET("/api/history?" + qs);
  view().innerHTML = `<div class="pagehead"><h1>Change history</h1></div>
    <p class="small muted" style="margin-top:-6px">Every entry, scheduled item, account, category and budget amount added, changed or deleted in your
      environments, with who did it and when (kept for a year, and in backups). Entries and scheduled items can be undone.</p>
    <div class="toolbar"><select id="hEnv"><option value="all">All my environments</option>${envs.map(e => `<option value="${e.id}" ${histView.env == e.id ? "selected" : ""}>${esc(e.name)}</option>`).join("")}</select>
      <select id="hUser"><option value="">Everyone</option>${people.map(p => `<option value="${p.id}" ${histView.user == p.id ? "selected" : ""}>${esc(p.display_name || p.username)}</option>`).join("")}</select>
      <input id="hQ" type="search" placeholder="Search (payee, account…)" value="${esc(histView.q)}" style="flex:1;min-width:180px;max-width:360px"></div>
    <div class="card">${historyOps(data.ops)}</div>
    <div class="toolbar">${histView.offset ? `<button id="hNewer">◀ Newer</button>` : ""}${data.more ? `<button id="hOlder">Older ▶</button>` : ""}</div>`;
  const again = () => renderHistory();
  q("#hEnv").onchange = e => { histView.env = e.target.value; histView.offset = 0; again(); };
  q("#hUser").onchange = e => { histView.user = e.target.value; histView.offset = 0; again(); };
  q("#hQ").onkeydown = e => { if (e.key === "Enter") { histView.q = e.target.value.trim(); histView.offset = 0; again(); } };
  if (q("#hOlder")) q("#hOlder").onclick = () => { histView.offset += 50; again(); };
  if (q("#hNewer")) q("#hNewer").onclick = () => { histView.offset = Math.max(0, histView.offset - 50); again(); };
  wireUndo(again);
}
async function entryHistoryDialog(kind, id, done) {
  const ops = await GET(`/api/history/${kind}/${id}`);
  const p = dialog(kind === "bill" ? "History of this scheduled item" : "History of this entry",
    `<div class="histbox">${historyOps(ops)}</div><p class="small muted">Oldest first. <a href="#/history">All changes</a></p>`, [{ label: "Close" }]);
  wireUndo(() => { document.getElementById("dlg").close(); if (done) done(); });
  return p;
}

// ---------- HELP ----------
// Guides, questions and answers, and what words mean (content in help.js), with a
// search box. #/help/<guide> opens one guide; each page's title has a "?" to its guide.
const HELP_FOR_TAB = { home: "start", accounts: "register", bills: "bills", budget: "budget", reports: "reports",
  categories: "taxes", backup: "backups", settings: "settings", people: "people", quick: "quick", history: "history", files: "receipts" };
// "Settings › Backups", "Reports", "Change history"...: what a Help guide's "Go to" link names.
function placeName(where) {
  const [tab, sub] = where.split("/");
  if (tab === "settings" && sub) {
    const t = [["look", "Look"], ["notifications", "Notifications"], ["people", "People & access"], ["categories", "Categories"],
      ["backups", "Backups"], ["data", "Your data"], ["computer", "This computer"]].find(([k]) => k === sub);
    return "Settings › " + (t ? t[1] : sub);
  }
  if (tab === "history") return "Change history";
  const a = q(`#tabs a[data-tab="${tab}"]`);
  return a ? a.textContent : tab;
}
function helpLinkInTitle(tab) {
  let id = HELP_FOR_TAB[tab];
  if (tab === "reports" && reportState.kind === "tax") id = "taxes";
  if (tab === "settings") id = SETTINGS_HELP[S.settingsSub] || "settings";
  const h = q("#view h1");
  if (!id || !h || q(".helplink", h) || typeof HELP === "undefined") return;
  const g = HELP.guides.find(x => x.id === id);
  h.insertAdjacentHTML("beforeend", ` <a class="helplink noprint" href="#/help/${id}" translate="no" title="${esc(tr("Help") + ": " + (g ? g.title : ""))}" aria-label="${esc(tr("Help") + ": " + (g ? g.title : ""))}">?</a>`);
}
function renderHelp(open) {
  qa("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === "help"));
  const guides = HELP.guides;
  view().innerHTML = `<h1>Help</h1>
    <div class="toolbar"><input type="search" id="helpQ" placeholder="Search help (e.g. statement, HSA, backup)" aria-label="Search help" style="flex:1;min-width:220px;max-width:460px">
      <button class="primary" id="helpTour">Take the tour</button></div>
    <div class="helpgrid">
      <nav class="card helpnav" aria-label="Guides"><h2>Guides</h2>${guides.map(g => `<a href="#/help/${g.id}" data-hid="${g.id}"${HELP.translated ? ' translate="no"' : ""}>${esc(g.title)}</a>`).join("")}
        <h2 style="margin-top:12px">More</h2><a href="#/help/faq" data-hid="faq">Questions and answers</a><a href="#/help/terms" data-hid="terms">What words mean</a></nav>
      <div id="helpBody"></div></div>`;
  const body = q("#helpBody");
  // Help already in the chosen language isn't looked up again piece by piece.
  const done = HELP.translated ? ' translate="no"' : "";
  const guideHtml = g => `<section class="card helpsec" id="help-${g.id}"><h2${done}>${esc(g.title)}</h2><div${done}>${g.body}</div>
      ${g.tab && g.tab !== "quick" ? `<p class="small"><a href="#/${g.tab}">Go to ${esc(placeName(g.tab))} →</a></p>` : ""}</section>`;
  const faqHtml = list => `<section class="card helpsec" id="help-faq"><h2>Questions and answers</h2>${list.map(f => `<details class="faq"><summary${done}>${esc(f.q)}</summary><div${done}>${f.a}</div></details>`).join("") || `<p class="muted">No questions match.</p>`}</section>`;
  const termsHtml = list => `<section class="card helpsec" id="help-terms"><h2>What words mean</h2><dl class="terms"${done}>${list.map(t => `<dt>${esc(t.term)}</dt><dd>${esc(t.def)}</dd>`).join("") || `<p class="muted">No words match.</p>`}</dl></section>`;
  const text = html => html.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").toLowerCase();
  const show = () => {
    const f = q("#helpQ").value.trim().toLowerCase();
    qa("[data-hid]").forEach(a => a.classList.toggle("on", !f && a.dataset.hid === (open || "start")));
    if (f) {
      // Searching: every guide, question and word containing the text.
      const g = guides.filter(x => text(x.title + " " + x.body).includes(f));
      const fq = HELP.faq.filter(x => text(x.q + " " + x.a).includes(f));
      const t = HELP.terms.filter(x => (x.term + " " + x.def).toLowerCase().includes(f));
      body.innerHTML = (g.length + fq.length + t.length)
        ? g.map(guideHtml).join("") + (fq.length ? faqHtml(fq) : "") + (t.length ? termsHtml(t) : "")
        : `<div class="card empty">Nothing in the help mentions "${esc(f)}". Try another word.</div>`;
      if (fq.length) qa("details.faq", body).forEach(d => { d.open = true; });
      return;
    }
    if (open === "faq") body.innerHTML = faqHtml(HELP.faq);
    else if (open === "terms") body.innerHTML = termsHtml(HELP.terms);
    else body.innerHTML = guideHtml(guides.find(x => x.id === open) || guides[0]);
  };
  q("#helpQ").addEventListener("input", show);
  q("#helpTour").onclick = () => startTour(true);
  show();
  window.scrollTo(0, 0);
}

// ---------- FIRST-RUN TOUR ----------
// A short look around, shown once to each person after they sign in (skip any time;
// replay from Help). Each step points at part of the page; on a phone the menu opens
// so the tabs can be pointed at.
const TOUR = [
  { title: "Welcome to MoneyThistle", text: "A quick look around: about a minute. Skip any time; you can take the tour again from Help." },
  { sel: '#tabs a[data-tab="accounts"]', title: "Accounts", text: "Your checking, savings, cards, loans and investments, each with its register. Type entries in, import a bank file, or record a whole paystub." },
  { sel: '#tabs a[data-tab="bills"]', title: "Bills & Deposits", text: "Everything that repeats: bills, paychecks, transfers, card and loan payments. Mark the automatic ones (⟳) and MoneyThistle can record them for you." },
  { sel: '#tabs a[data-tab="budget"]', title: "Budget", text: "Plan the month by category, or simply by your scheduled items, and see how it's going." },
  { sel: '#tabs a[data-tab="reports"]', title: "Reports", text: "Where the money goes and comes from, net worth, a forecast of your balances, and the year-end tax report." },
  { sel: '#tabs a[data-tab="files"]', title: "Files", text: "Receipts and papers you keep with entries and accounts, with notes and keywords: search them by account, words or time." },
  { sel: "#envbar", title: "Which environment", text: "Switch between the sets of accounts you're a member of here." },
  { sel: '#tabs a[data-tab="settings"]', title: "Settings", text: "The look, notifications, people and sharing, categories, backups to Nextcloud, moving in from another program, and (for administrators) how MoneyThistle starts on this computer. Each has its own tab inside Settings." },
  { sel: "#quickFab", title: "Quick add", text: "On a phone, this + button enters a transaction in a few taps." },
  { sel: '#tabs a[data-tab="help"]', title: "Help", text: "Guides, questions and answers, and what words mean. Every page's title has a ? that opens its guide. Keep MoneyThistle on your home network or Tailscale, never the open internet." },
];
let tourShown = false;
function maybeStartTour(tab) {
  if (tourShown || tab === "quick" || !S.ui || S.ui.tour_done || q(".tour") || document.getElementById("dlg").open) return;
  tourShown = true;
  setTimeout(() => startTour(false), 400);
}
function startTour(replay) {
  tourShown = true;
  if (q(".tour")) return;
  const top = q("header.top"), menuWasOpen = top.classList.contains("open");
  const narrow = getComputedStyle(q("#menuBtn")).display !== "none";
  if (narrow) top.classList.add("open");
  const wrap = document.createElement("div");
  wrap.className = "tour";
  wrap.innerHTML = `<div class="tour-spot" hidden></div><div class="tour-box" role="dialog" aria-modal="true" aria-labelledby="tourTitle" tabindex="-1"></div>`;
  document.body.appendChild(wrap);
  const spot = q(".tour-spot", wrap), box = q(".tour-box", wrap);
  const steps = TOUR.filter(s => !s.sel || (() => { const e = q(s.sel); return e && e.getClientRects().length; })());
  let i = 0;
  const finish = async () => {
    removeEventListener("resize", place); document.removeEventListener("keydown", keys, true);
    wrap.remove();
    if (narrow && !menuWasOpen) top.classList.remove("open");
    if (!S.ui || !S.ui.tour_done) {
      try { S.ui = await api("PUT", "/api/settings", { tour_done: true }); } catch (e) { /* asked again next time */ }
    }
  };
  function place() {
    const s = steps[i], el = s.sel ? q(s.sel) : null;
    const r = el ? el.getBoundingClientRect() : null;
    if (r && r.width) {
      spot.hidden = false;
      Object.assign(spot.style, { left: r.left - 6 + "px", top: r.top - 6 + "px", width: r.width + 12 + "px", height: r.height + 12 + "px" });
      const w = Math.min(360, innerWidth - 24);
      box.style.width = w + "px";
      box.style.left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 12)) + "px";
      const below = r.bottom + 14, h = box.offsetHeight || 170;
      box.style.top = (below + h < innerHeight - 8 ? below : Math.max(12, r.top - h - 14)) + "px";
      box.classList.remove("center");
    } else {
      spot.hidden = true;
      box.style.width = Math.min(420, innerWidth - 24) + "px";
      box.style.left = (innerWidth - Math.min(420, innerWidth - 24)) / 2 + "px";
      box.style.top = Math.max(24, innerHeight / 2 - 120) + "px";
      box.classList.add("center");
    }
  }
  function draw() {
    const s = steps[i], last = i === steps.length - 1;
    box.innerHTML = `<div class="tour-step small muted">${i + 1} of ${steps.length}</div>
      <h2 id="tourTitle">${esc(s.title)}</h2><p>${esc(s.text)}</p>
      <div class="tour-btns"><button type="button" class="link" data-t="skip">${last ? "" : "Skip the tour"}</button>
        <span style="flex:1"></span>${i ? `<button type="button" data-t="back">Back</button>` : ""}
        <button type="button" class="primary" data-t="next">${last ? "Done" : i ? "Next" : "Show me around"}</button></div>`;
    q('[data-t="skip"]', box).hidden = last;
    qa("[data-t]", box).forEach(b => b.onclick = () => {
      const t = b.dataset.t;
      if (t === "skip" || (t === "next" && last)) return finish();
      i += t === "next" ? 1 : -1; draw();
    });
    place();
    q('[data-t="next"]', box).focus();
  }
  function keys(e) {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(); }
    else if (e.key === "ArrowRight" && i < steps.length - 1) { i++; draw(); }
    else if (e.key === "ArrowLeft" && i > 0) { i--; draw(); }
  }
  addEventListener("resize", place);
  document.addEventListener("keydown", keys, true);
  draw();
}

// ---------- type-to-filter lists ----------
// Long drop-down lists (categories, or anything over 15 choices) get a box you type
// into: the list narrows to the choices containing what you typed ("health" shows
// Healthcare and its subcategories, and Insurance : Health). The real <select> stays
// in the page, hidden, so forms and code read and set it as before.
const PICK_MIN = 15;
function pickWanted(sel) {
  return !sel._pick && !sel.multiple && !sel.dataset.native && !sel.closest(".envbar") &&
    (sel.querySelector("optgroup") || sel.options.length > PICK_MIN);
}
function enhanceSelect(sel) {
  const wrap = document.createElement("span");
  wrap.className = "pick";
  const inp = document.createElement("input");
  inp.type = "text"; inp.autocomplete = "off"; inp.spellcheck = false;
  // Only the look-alike classes come along (size), so code finding the list by its
  // class still finds the list, not this box.
  inp.className = ["pick-input"].concat(Array.from(sel.classList).filter(c => ["small", "qbig", "num"].includes(c))).join(" ");
  inp.setAttribute("role", "combobox"); inp.setAttribute("aria-autocomplete", "list"); inp.setAttribute("aria-expanded", "false");
  const lab = sel.getAttribute("aria-label") || (sel.labels && sel.labels[0] && sel.labels[0].textContent.trim()) ||
    (sel.closest("div") && sel.closest("div").querySelector("label") && sel.closest("div").querySelector("label").textContent.trim()) || "";
  if (lab) inp.setAttribute("aria-label", lab);
  inp.title = "Type to narrow the list";
  // Same width as the list it replaces: a percentage stays one, a drawn width is kept.
  const cw = getComputedStyle(sel).width;
  if (/%$/.test(cw)) wrap.style.width = cw;
  else if (sel.offsetWidth) wrap.style.width = (sel.parentElement && sel.offsetWidth >= sel.parentElement.clientWidth - 4) ? "100%" : sel.offsetWidth + "px";
  for (const k of ["width", "maxWidth", "minWidth"]) if (sel.style[k]) wrap.style[k] = sel.style[k];
  sel.parentNode.insertBefore(wrap, sel);
  wrap.appendChild(inp); wrap.appendChild(sel);
  sel.classList.add("pick-native");
  sel.tabIndex = -1;
  const list = document.createElement("div");
  list.className = "pick-list"; list.setAttribute("role", "listbox"); list.hidden = true;
  list.id = "pick-" + Math.random().toString(36).slice(2, 9);
  inp.setAttribute("aria-controls", list.id);

  // The choices, with each subcategory's main category (indented options follow theirs).
  const items = () => {
    const out = []; let top = "";
    Array.from(sel.options).forEach((o, i) => {
      const raw = o.textContent.replace(/\u00a0/g, " ");
      const sub = /^\s/.test(raw), name = raw.trim();
      if (!sub) top = name;
      const group = o.parentElement && o.parentElement.tagName === "OPTGROUP" ? o.parentElement.label : "";
      out.push({ i, o, name, sub, full: sub && !name.includes(" : ") ? `${top} : ${name}` : name, group });
    });
    return out;
  };
  const label = () => {
    const it = items()[sel.selectedIndex];
    if (!it) return "";
    if (it.o.value === "") { inp.placeholder = it.name; return ""; }
    return it.full;
  };
  const sync = () => {
    if (document.activeElement !== inp || list.hidden) inp.value = label();
    inp.disabled = sel.disabled;
    wrap.style.display = (sel.hidden || sel.style.display === "none") ? "none" : "";
  };
  let shown = [], hl = -1, typed = "";
  const mark = (text, f) => {
    if (!f) return esc(text);
    const k = text.toLowerCase().indexOf(f);
    return k < 0 ? esc(text) : esc(text.slice(0, k)) + "<mark>" + esc(text.slice(k, k + f.length)) + "</mark>" + esc(text.slice(k + f.length));
  };
  const render = () => {
    const f = typed.trim().toLowerCase();
    const all = items();
    if (f) {
      const rank = it => { const n = it.name.toLowerCase(), u = it.full.toLowerCase();
        return n.startsWith(f) || u.startsWith(f) ? 0 : new RegExp("(^|[\\s:/&(-])" + f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).test(u) ? 1 : 2; };
      shown = all.filter(it => it.o.value !== "" && it.full.toLowerCase().includes(f))
        .map(it => [rank(it), it]).sort((a, b) => a[0] - b[0] || a[1].i - b[1].i).map(x => x[1]);
    } else shown = all;
    if (hl >= shown.length || hl < 0) hl = f ? shown.findIndex(it => !it.o.disabled) : shown.findIndex(it => it.i === sel.selectedIndex);
    let lastGroup = null, h = "";
    shown.forEach((it, k) => {
      if (!f && it.group && it.group !== lastGroup) { h += `<div class="pick-group">${esc(it.group)}</div>`; lastGroup = it.group; }
      h += `<div class="pick-opt${!f && it.sub ? " sub" : ""}${k === hl ? " hl" : ""}${it.i === sel.selectedIndex ? " cur" : ""}${it.o.disabled ? " dis" : ""}" role="option" data-k="${k}" aria-selected="${k === hl}">${mark(f ? it.full : it.name, f)}</div>`;
    });
    list.innerHTML = h || `<div class="pick-empty">Nothing matches "${esc(typed)}"</div>`;
    const cur = list.querySelector(".hl");
    if (cur) cur.scrollIntoView({ block: "nearest" });
  };
  const place = () => {
    const r = inp.getBoundingClientRect();
    const below = innerHeight - r.bottom - 8, above = r.top - 8;
    const up = below < 180 && above > below;
    const room = Math.max(120, Math.min(340, up ? above : below));
    list.style.left = Math.max(4, Math.min(r.left, innerWidth - Math.max(r.width, 240) - 4)) + "px";
    list.style.minWidth = r.width + "px";
    list.style.maxHeight = room + "px";
    list.style.top = up ? "" : (r.bottom + 2) + "px";
    list.style.bottom = up ? (innerHeight - r.top + 2) + "px" : "";
  };
  // Scrolling the page (or resizing) moves the list along; scrolling inside the list doesn't.
  const onMove = e => { if (!(e.target instanceof Node && list.contains(e.target))) place(); };
  const open = () => {
    if (!list.hidden || inp.disabled) return;
    (inp.closest("dialog") || document.body).appendChild(list);
    list.hidden = false; inp.setAttribute("aria-expanded", "true");
    typed = ""; hl = -1; render(); place();
    addEventListener("scroll", onMove, true); addEventListener("resize", onMove);
  };
  const close = () => {
    if (list.hidden) return;
    list.hidden = true; inp.setAttribute("aria-expanded", "false");
    removeEventListener("scroll", onMove, true); removeEventListener("resize", onMove);
    list.remove(); typed = ""; inp.value = label();
  };
  const choose = it => {
    if (!it || it.o.disabled) return;
    const before = sel.value;
    sel.selectedIndex = it.i;
    close();
    if (sel.value !== before) { sel.dispatchEvent(new Event("input", { bubbles: true })); sel.dispatchEvent(new Event("change", { bubbles: true })); }
  };
  inp.addEventListener("mousedown", () => { if (list.hidden) setTimeout(() => { open(); inp.select(); }, 0); });
  inp.addEventListener("focus", () => inp.select());
  inp.addEventListener("input", () => { open(); typed = inp.value; hl = -1; render(); });
  inp.addEventListener("keydown", e => {
    const step = d => { if (list.hidden) { open(); return; } let k = hl;
      do { k += d; } while (k >= 0 && k < shown.length && shown[k].o.disabled);
      if (k >= 0 && k < shown.length) { hl = k; render(); } };
    if (e.key === "ArrowDown") { e.preventDefault(); step(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); step(-1); }
    else if (e.key === "Enter") { if (!list.hidden) { e.preventDefault(); e.stopPropagation(); if (hl >= 0) choose(shown[hl]); else close(); } }
    else if (e.key === "Escape") { if (!list.hidden) { e.preventDefault(); e.stopPropagation(); close(); } }
    else if (e.key === "Tab") { if (!list.hidden && typed && hl >= 0) choose(shown[hl]); else close(); }
  });
  inp.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== inp) close(); }, 120));
  list.addEventListener("mousedown", e => {
    e.preventDefault();   // keep the typing box focused
    const row = e.target.closest(".pick-opt");
    if (row) choose(shown[+row.dataset.k]);
  });
  // Code that sets the list's value (a payee's usual category...) updates the box too.
  for (const prop of ["value", "selectedIndex"]) {
    const d = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, prop);
    Object.defineProperty(sel, prop, { configurable: true, get() { return d.get.call(sel); }, set(v) { d.set.call(sel, v); sync(); } });
  }
  sel.focus = () => inp.focus();
  new MutationObserver(sync).observe(sel, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "style", "hidden"] });
  sel.addEventListener("change", sync);
  sel._pick = inp;
  sync();
}
function enhanceSelects(root) {
  if (root.tagName === "SELECT") { if (pickWanted(root)) enhanceSelect(root); return; }
  if (root.querySelectorAll) root.querySelectorAll("select").forEach(s => { if (pickWanted(s)) enhanceSelect(s); });
}
new MutationObserver(muts => {
  for (const m of muts) for (const n of m.addedNodes) if (n.nodeType === 1 && !n.classList.contains("pick-list")) enhanceSelects(n);
}).observe(document.body, { childList: true, subtree: true });
// A label pointing at an enhanced list puts the cursor in its typing box.
document.addEventListener("click", e => {
  const l = e.target.closest && e.target.closest("label[for]");
  const s = l && document.getElementById(l.htmlFor);
  if (s && s._pick) { e.preventDefault(); s._pick.focus(); }
});
// The environments picker stays open while ticking, and closes with the first click
// anywhere else (or Esc).
document.addEventListener("click", e => {
  qa("details.envpick[open]").forEach(d => { if (!d.contains(e.target)) { d.open = false; S.envpickOpen = false; } });
}, true);
document.addEventListener("keydown", e => {
  if (e.key === "Escape") qa("details.envpick[open]").forEach(d => { d.open = false; d.querySelector("summary").focus(); });
});

render();
setInterval(() => refreshBackupState(), 60000);
