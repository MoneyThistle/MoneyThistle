# Changelog

What changed in each release of MoneyThistle. Versions follow MAJOR.MINOR.PATCH: a new MAJOR
can need you to do something when updating, MINOR adds features, PATCH fixes things.

## 1.0.0 (2026-11-22)

The first release: a simpler, self-hosted successor to Microsoft Money Plus Sunset, opened in a web
browser, with no bank connections.

### Money
- Accounts of every kind (checking, savings, cards, loans with amortization, investments as balances)
  with registers, running balances, reconciling ("Balance account") and card statements.
- Bills & Deposits: everything that repeats, including the last day of the month; automatic items
  MoneyThistle records for you; amounts that vary counted at their average.
- Budget by category or by your schedule; reports on spending, income, net worth, a forecast of
  your balances, and a year-end tax report with HSA limits and paystubs (gross pay, taxes and
  deductions).
- Several environments (Personal, Household, Business…) with their own members, shared accounts,
  transfers between them, moving accounts between them, and views of chosen environments together.
- Receipts and papers: photos (also from a phone's camera) and PDFs kept with entries or accounts,
  with notes and keywords, searchable in Files; also added while recording a bill, deposit, loan
  payment or paycheck, and kept when a paycheck's paystub details are added later.
- Change history with undo.
- Bringing data in: OFX/QFX/QBO, CSV and QIF files, and moving in from Microsoft Money, Quicken,
  YNAB, Mint, GnuCash, Actual and Firefly III exports.

### Safety
- Everyone signs in with their own user name and password; "Keep me signed in on this device" or
  sign-ins that end with the browser or after an hour unused; password reset by email or the
  command line.
- Automatic backups to a folder and to Nextcloud or any WebDAV server, optionally encrypted, each
  read back and checked; kept by day, week and month; restore from the Backups page, from a file,
  or onto a new computer or server from the first-run page.

### Running it
- Windows: a setup file with its own private Python (nothing else to install), Start menu entry,
  optional desktop icon, and start at sign-in or with the computer; Shut down from the page.
- Docker, Docker Compose and Unraid; macOS and Linux with Python 3.10+.
- Daily summaries by email, Pushover, ntfy or Gotify. Light and dark looks, in-app tour and Help.
- Paychecks with as much as you know: take-home pay only, or the full paystub, now or later; scheduled
  deposits can be paychecks; paychecks with less than usual for their employer are flagged.
  Whatever a paystub doesn't itemize is kept as "Other deductions" (flagged only for employers whose
  paystubs are usually fully itemized), and money added after taxes (reimbursements) has its own lines.
  Insurance has subcategories for what paystubs commonly take out: Accident, Dental, Disability, Legal
  Plan and Vision, and a new Savings & Investments category (Retirement Plan, HSA/FSA) for paycheck
  savings sent to an account you don't keep in MoneyThistle (added once to existing files).
  A paycheck's direct deposit can be split between accounts (a set amount into one, the rest into another).
  Paystub lines can be moved up and down to follow the paystub's own order.
  A scheduled deposit can go into more than one account, each with a set amount or its average.
- Start fresh: while sample data is in use, every page offers to start fresh with one click; an owner
  can start any environment fresh under Settings, Your data (its name typed to confirm; a copy is kept).
- Investment, retirement and asset accounts: Update value records what they're worth now as one
  "Change in value" entry (left out of budgets and spending reports); investments are reminded monthly.
- Updates: MoneyThistle checks GitHub once a day for a newer version (only its version number is
  sent). Windows installs it with one click, or by itself; Docker and Unraid update the container
  from the published image (ghcr.io/moneythistle/moneythistle), with `latest` or a pinned version.
- Unraid: a template that installs from the published image; nothing to copy to the server.
- Moving in from Moneydance: its "All accounts" QIF now brings in every account (it was read as one).
  Investment and retirement accounts (a Roth IRA, a 401(k)) come in with their transfers, dividends
  and interest (buys and sells aren't entries). Types follow the account's name, not the firm's: an HSA
  comes in as Savings (marked as an HSA for the tax report), a cash management account as Checking,
  a mortgage as a Loan.
- Languages: English, French (Canada), Spanish (Latin America) and Portuguese (Brazil), chosen by each
  person, with dates and amounts in that language's style: every screen, message, Help guide and the
  About page (AI translations, not yet checked by native speakers). Names you typed (environments,
  accounts, payees) are never translated; categories have a name per language (the starting ones come
  with all four, and any category can be given its own in its details). Amounts can be typed as 1,234.56 or 1.234,56.
- Currencies: each account in its own currency (the Americas and the euro); transfers between two
  currencies record the amount that arrived; totals per currency, and together at rough rates you set.
- Simple or Everything, chosen by each person (new sign-ins start Simple): extras fold under
  "More options", remembered place by place.
