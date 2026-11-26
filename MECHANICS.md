# Mechanics sheet

What was read from the original (Money Plus Deluxe "Sunset" installer) and how this rebuild uses it.
The target file is an IExpress installer; the program files sit in its `CABINET` resource
(evidence ev_7b7054d3…). They were unpacked to a temporary folder and read there.

## Backups (mnyob99.dll)

| Rule | Value in the original | Where | This rebuild |
|---|---|---|---|
| Back up when the program closes | on by default | `FUN_242a8afc` 0x242a8afc (field 0 = 1) | "Back up after I make changes": runs once the app has been idle after a change (default 5 min, **estimated**, a server never "closes") and when the container stops (SIGTERM) |
| Copies kept of close-time backups | 3 | 0x242a8afc (field 4 = 3) | `keep_change` = 3 |
| Compress backup files | on | 0x242a8afc (fields 3 and 9 = 1) | gzip, on by default |
| Scheduled backup | on | 0x242a8afc (field 5 = 1 unless feature set 10 == 5) | `scheduled` = on |
| Days between scheduled backups | 14 | 0x242a8afc (field 6 = 0xE) | `interval_days` = 14 |
| Allowed range for days | 1..99 | `FUN_242a92b5` 0x242a92b5 (`GetBarneyInt(L"BackupFDInterval",…,1,99)`) and obres.dll message "Please enter a number between 1 and 99." | same, same wording |
| Copies kept of scheduled backups | 3 (range 1..99) | 0x242a8afc (field 10 = 3); obres.dll message for 1..99 | `keep_scheduled` = 3 |
| Last scheduled backup | "never" at start | 0x242a8afc (`SetState(…,2)`) | `last_scheduled` = null |
| Days since last scheduled backup | -1 when never, 0 when today, else today − last | `FUN_242a3f17` 0x242a3f17 | `days_since_scheduled()` |
| Order when it runs | close-time backup first, then scheduled if days == -1 or days ≥ interval; then stamp today | `BackupOnDemand` 0x242a83db | `BackupManager.due()` / `run()` |
| Older backups kept | none beyond the 3 + 3 above | — | **Added on request** (not in the original): also the last backup of each of the latest `keep_daily` = 7 days, `keep_weekly` = 4 weeks and `keep_monthly` = 12 months that have one (`keep_plan()`); 0 turns a tier off. Three busy-day backups can no longer push out yesterday's. Manual backups are never deleted. |

Destinations: the original wrote to a hard-drive path or floppy. This rebuild writes to a folder
(Docker volume `/backups`) and/or a WebDAV folder (Nextcloud, ownCloud, Synology, Box…), as asked.
Restore makes a safety copy of the current file first (the original warned that changes since the
backup are lost: obres.dll "If you restore this backup file, you'll lose any changes…").

## Categories (obres.dll category table, "Espresso Comment: Income and Expense Categories")

Flags in the table: `-` subcategory, `*` tax related, `+` added to the default budget,
`?n` tax form line, `&` short-list category. The US entries (international placeholders left out)
are in `moneyapp/defaults.py` with their tax and budget flags. "Not an Expense" is kept as a special
category that reports leave out.

## Account types (obres.dll 0x32a47188…)

Asset, Cash, Checking, Credit Card, Investment, Liability, Line of Credit, Loan, Other, Retirement,
Savings. Credit Card, Line of Credit, Liability and Loan count as debts (balance stored negative).
Investment accounts here hold a balance only; the original's security tracking and quotes are left
out (they needed the online services).

## Bill frequencies (obres.dll "End of Frequency listing")

Daily, Weekly, Every other week, Twice a month, Every four weeks, Monthly, Every other month,
Every three months, Twice a year, Yearly, Every other year, Only once.
"Twice a month" = two dates 15 days apart (anchor day and anchor ± 15) — **estimated**, the exact
rule was not decompiled. Monthly-type schedules keep their original day and clamp to the month end.

**Schedule… from a register entry** (MoneyThistle's own, for after moving in): the frequency is
guessed from the median gap between the same payee's entries in that account, same direction (last
12 gaps): ≤3 days Daily, ≤10 Weekly, ≤18 Every other week (or Twice a month when every gap isn't
14 and the recent days of the month repeat), 28 every time Every four weeks, ≤45 Monthly, ≤75 Every
other month, ≤120 Every three months, ≤250 Twice a year, ≤500 Yearly, longer Every other year.
"Last day of the month" when the last 6 all fell on a month end. The next date is the first after
today. Amounts differing among the last 6 make it vary, at their average. A split payment counts
once, at its total, in its biggest part's category; entries shaped like the one opened (single or
split) are used when there are at least two. Worked out by the server (`store.guess_frequency`,
`Store.schedule_from_entry`); the next dates use the same rule as every scheduled item.

## Loan what-if and calculator (MoneyThistle's own; nothing is saved)

- **What if…** starts from what is owed now and the next payment date, with the loan's own
  interest rule (balance × APR ÷ payments a year, to the cent). A one-time extra goes to principal
  with the first payment on or after its date; "extra with every payment" goes with each one.
  Switching how often: the same amount a year (payment × old ÷ new payments a year), except
  monthly → every other week, which pays half the monthly payment 26 times a year (one extra
  monthly payment a year). The payment can be changed by hand. Escrow is left out.
- "Months sooner" = months between the two payoff dates.
- **Loan calculator**: payments = years × payments a year (rounded, 1–1200). Price → payment: the
  loan is the price less the down payment, payment by the amortization formula. Payment →
  price: loan = payment × (1 − (1 + r)^−n) ÷ r (payment × n at 0%), rounded down to the cent;
  price = loan + down payment. Interest is summed over the schedule.

## Other rules

- A file holds at most 63 accounts in the original (obres.dll message). Not enforced here.
- Payee fill-in: the last category and amount used with a payee are offered again (the original's
  automatic fill-in idea; exact rules **estimated**).
- Reconcile ("Balance account"): starting balance = opening balance + reconciled transactions;
  finishing requires the difference to be zero (**estimated** from the original's workflow text).
- Budget: follows the original's simple "Essential Budget", which leaves out transfers, loan
  payments, one-time expenses and savings goals (obres.dll 0x32a16388, evidence ev_edf8904d…).
  Monthly amount per category; a main category's actual includes subcategories that have no budget
  line of their own (that roll-up is **estimated**).
- Reports leave out transfers and "Not an Expense" (**estimated**).
- Paychecks (the person's design, not the original's): take-home pay alone is enough. With gross
  pay, Other deductions = gross + added after taxes − take-home − itemized deductions; it can't be
  below $0. An employer's usual level comes from its latest 6 paychecks (take-home only / gross and
  take-home / itemized). Flags: usually itemized → "$X not itemized" and usual deductions missing;
  usually gross → only a missing gross pay; usually take-home only → never. "Complete as is" stops a flag.
- Currencies (the person's design): each account keeps its own currency (USD default; Americas + EUR).
  A transfer between two currencies stores what left and what arrived; no exchange rates are fetched.
  Totals across currencies use rough rates typed in (1 unit ≈ rate × main currency), rounded to the
  cent, marked approximate; a currency without a rate is left out of combined totals. The tax report
  covers main-currency accounts only.
- Category names per language (the person's design): a category is one category with an own name
  and an optional name in each of English, French, Spanish and Portuguese; screens show the name in the
  person's language, else the own name. The starting categories get all names once; entries are never
  rewritten (they point at the category).
- Paycheck savings (the person's point): a 401(k)/HSA deduction goes to that account when it's kept
  in MoneyThistle, else to the expense category Savings & Investments (Retirement Plan, HSA/FSA).
- Split direct deposit (the person's design): a paycheck lists each account it was deposited into with
  the amount that landed there; take-home pay is their total (paystub or take-home only). The budget
  counts the whole take-home pay, the schedule and its history what reached the scheduled account.
- Start fresh (the person's request): an environment's money file is set aside (renamed
  "<file>.before-reset-<date-time>", never deleted) and a new one with the starting categories takes its
  place; its links, shares and change history end; the main currency is kept. Sample data: one click;
  otherwise the environment's name typed. Owners only.
- QIF accounts: entries right after an account header belong to that account, even when the file never
  clears AutoSwitch (Moneydance). Investment accounts (QIF Invst/Port) are always kept. Their
  investment-format entries become cash entries: dividends, interest and capital gains (also reinvested)
  as income (Investment Income categories), XIn/XOut/ContribX/BuyX/SellX as money in/out (transfers when
  another account is named), MiscExp/MargInt as spending; buys, sells and share moves are skipped. An
  account with none starts at the first transfer naming it. Types come from words in the name, never
  the firm (HSA -> Savings, cash management -> Checking, Roth/IRA/401(k) -> Retirement, mortgage -> Loan).
- Investment values (the person's design): no lookups and no special entry type. Update value makes one
  entry on the date (value - balance that day) in the "Change in Value" category (kind none: no budget,
  no spending/income reports; net worth follows); the same date again replaces it. Investment and
  retirement accounts are reminded when 30+ days old (opt out per account; assets opt in).
- HSA account type: any non-debt type with "This is an HSA" ticked. Savings for one kept as cash,
  Investment for one that's invested (value updates apply); one with both can be two accounts. Imports
  guess it from the name ("HSA", "Health Savings") and mark it.
- W-2 (the person's decision): not entered; the tax report's Pay section adds up the paystubs to be
  compared with it (box 1 vs gross less pre-tax deductions; boxes 2, 4, 6 vs the taxes).
- Scheduled split deposits: each other account is a linked scheduled deposit (own amount, set or
  average of its own history), on the main one's dates, entered and skipped with it, listed with it.
- Typed amounts: the last of "," and "." is the decimal mark when both appear; one alone is the decimal
  mark unless exactly three digits follow (then it groups thousands).
- Bank connectivity (OFX/online services) is left out on purpose. Files can be imported instead:
  CSV and QIF.
