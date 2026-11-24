// Quick check of the translation matcher outside a browser: node tests/i18n_check.js [lang] [text...]
// Prints each text with its translation and how long it all took.
"use strict";
const fs = require("fs");
const path = require("path");
const here = path.join(__dirname, "..", "moneyapp", "static");
global.document = { documentElement: {}, head: { appendChild() { } }, body: {}, getElementById() { return null } };
global.location = { search: "" };
global.localStorage = { getItem() { return null }, setItem() { } };
global.navigator = { languages: ["en"] };
const lang = process.argv[2] || "pt";
const locale = { pt: "pt-BR", fr: "fr-CA", es: "es-419" }[lang];
const src = fs.readFileSync(path.join(here, "i18n.js"), "utf8") +
  "\n;global.I18N = I18N; global.tr = tr; global.keepAsTyped = keepAsTyped; global.i18nCategories = i18nCategories; LANG = " + JSON.stringify(lang) +
  "; LOCALE = " + JSON.stringify(locale) + ";";
(0, eval)(src);
(0, eval)(fs.readFileSync(path.join(here, "lang", lang + ".js"), "utf8"));
keepAsTyped(["Household", "Investment Income : Interest", "Chase Checking 1234", "Bills", "Bills : Electricity", "Savings"]);
// Categories with a name per language; an account spelled like a category keeps its name.
i18nCategories([{ id: 1, name: "Bills", full_name: "Bills", names: { pt: "Contas", fr: "Factures", es: "Facturas" } },
  { id: 2, name: "Electricity", parent_id: 1, full_name: "Bills : Electricity", names: { pt: "Eletricidade", fr: "Électricité", es: "Electricidad" } },
  { id: 3, name: "Savings", full_name: "Savings", names: {} }], ["Household", "Savings"]);
const catChecks = { "Bills": 1, "Bills : Electricity": 1, "Transfer to Bills": 1, "Transfer to Savings": 1, "Savings": 0, "Bills · Monthly": 1 };
for (const [s, changes] of Object.entries(catChecks)) {
  const t = tr(s);
  console.log("category", JSON.stringify(s), "=>", JSON.stringify(t), (t !== s) === !!changes ? "ok" : "WRONG");
}
const texts = process.argv.slice(3).length ? process.argv.slice(3) : [
  "Paid out $ 4.030,52", "2 times", "1 entered", "Investment Income : Interest · Monthly, last day of the month",
  "(your address)", "Every other week", "Show the next", "connected", "Like this device (15 de nov. de 2026)",
  "In 30 days", "of $ 2.950,57 scheduled", "Household", "x".repeat(300) + " a b c d e f g",
  "gross $ 3.450,00 · 8 taxes & deductions", "Subir (later nesse dia)", "Move up (later that day)",
  "$ 295,97 principal · $ 59,60 interest", "0 files. Each word you type must appear in the note, the file name, the entry or the account.",
  "Showing Personal + Household together: changes are made in each item's own environment (choosing one switches there). Accounts shared between them count once.",
  "asked by Alex on 21 de nov. de 2026", "Date ▾", "Loan payment: Car Loan (principal, interest, escrow) · Monthly",
  "Card payment to HSA Visa (full balance) · set in the card's details · Monthly", "Chase Checking 1234 · Household · Every other week",
  "Started from your 23 de nov. de 2026 paystub from Northwind Payroll (take-home $ 2.100,00): change only what's different this time.",
  ". In the budget a paycheck counts as its take-home pay.", "into Everyday Checking", "Gross pay", "Other deductions",
  "Backed up 22 de nov., 22:27", "Help: Primeiros passos", "Accounts in other currencies aren't in this report (",
  "→ to Work 401(k)", "e.g. 4400.00", "From account", "dezembro de 2025 income $ 0,00", "received $ 9.025,04", "so far -$ 925,36 · $ 4.678,69 moved to your other accounts",
];
const t0 = Date.now();
let bad = 0;
for (const s of texts) {
  const t = tr(s);
  if (t === s && /[a-z]{3}/.test(s) && s !== "Household") bad++;
  console.log(JSON.stringify(s.slice(0, 70)), "=>", JSON.stringify(String(t).slice(0, 90)));
}
console.log("ms", Date.now() - t0, "untranslated", bad);
