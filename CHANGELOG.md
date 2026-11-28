# Changelog

What changed in each release of MoneyThistle. Versions follow MAJOR.MINOR.PATCH: a new MAJOR
can need you to do something when updating, MINOR adds features, PATCH fixes things.

## 1.0.8 (2026-11-28)

From the second team review (v1.0.7):

- **Card payments are bills too:** any scheduled payment into a credit card shows both tags (bill
  and transfer) in the bill's color, and **Pay this bill ↗** opens the card's own website, however it
  was scheduled: through the card's details or as a plain transfer, from another environment too.
  (Payments from another environment showed no link, or the paying bank's site.)
- **Reordering is a real mode:** while a 🔒 is open, the items rest: no entry opens, the C/R mark and
  the stars don't change, only the handles (▲ ▼ on a phone) move things. In a register the handles
  get a column of their own at the edge. Lock again, press Escape or leave the page to end it.
- **Accounts:** one **New** button with a short list: banking account, credit card, loan, investment
  or retirement account, property.
- **Register:** a split payment (a loan payment, a split) opens in the entry line like every other
  entry; **Open payment** shows its parts and date. The green Paystub tag no longer jumps to Home.
- **A dialog left by clicking a tab** now goes on to that tab after it's closed or saved (it stayed
  on the page before).
- **Pushover for the family:** an administrator can share their Pushover; everyone else picks only
  their own device (Find devices lists them from Pushover). Their own Pushover still works too. The
  administrators' summary covers the environments an administrator is in: someone's own environment
  stays theirs.
- **Files:** an Environment choice, including All my environments.
- **Home:** with all environments shown, accounts are grouped under each environment's name; Recent
  transactions shows one line per transaction (a paystub, a split or a transfer is one line).
- **Budget:** payments entered early for a later month are a one-line note that opens, not a block.
- **Settings → Look:** Back to defaults sits at the bottom of the left column, under what it resets.
- The sign-in page no longer logs an error in the browser's console.

## 1.0.7 (2026-11-27)

- **Looking ahead remembers your accounts everywhere:** which accounts it shows, and whether it
  shows their total, are kept with your sign-in (per environment), so another browser or your phone
  shows the same. A choice made earlier in a browser carries over the first time.
- Home's Looking ahead card now follows that choice too (it always showed the usual accounts).
- Scheduled items: the amount, the account(s) and "To the card" line up side by side again (a note
  under the amount pushed the other fields down). Fixed once for every form (bills, deposits,
  paychecks, transfers, loans, settings): fields now line up from the top everywhere.
- **Bills & Deposits, Coming up:**
  - **Show automatic (N)**, ticked by default: untick it to hide autopay and direct deposits and see
    only what needs you. N counts them for the days shown; the choice follows you to every browser.
  - **Pay this bill ↗** opens where a bill is paid (a new *Website to pay it* field under More
    options; card and loan payments use the card's or loan's website). Deposits and transfers get
    **View account ↗**, to the account's website.
  - The account cards fill balanced columns, busiest account first, instead of rows that left a
    big empty space beside a long card. One column on a phone.
  - Later occurrences of an item no longer say "later": only the earliest has Enter and Skip.
  - Enter and Skip stack instead of being cut off at the edge of a narrow card.
- **A dialog belongs to its page:** leaving a page (a tab, Back) with a dialog open closes it, or
  asks once to save it when something in it was changed. It used to stay on top of the next page
  and block it.
- **Settings:** each section that holds settings has one **Save** and **Discard changes** bar at its
  top and bottom, greyed out until something changes (the section's name gets a dot meanwhile).
  Leaving with unsaved changes names the section. Your data and This computer, which are actions,
  have none.
- **Accounts:** ☆ star an account to make it a favorite (first in its group). Unlock 🔒 the list to
  drag accounts into your own order (▲ ▼ on a phone). Favorites and order are each person's own.
  "New" is now "New account".
- **One way to reorder, everywhere:** the Accounts list, a register's entries on the same day and
  a paystub's lines all use the same 🔒: locked by default (no handles, nothing moves by accident),
  open it to drag by the handle, or use ▲ ▼ on a phone. Alt+↑ ↓ still moves paystub lines.
- **A paycheck with its paystub** opens in the entry line like any entry, with Receipts (keep the pay
  slip's PDF there); the paystub opens from its Paystub tag or the Paystub button.
- **Averages:** a scheduled item shows "Average of the last N: $X"; click the amount for the amounts
  and dates it comes from.
- **Balance and Cleared:** one ? beside them opens a new Help guide on what each means and when a
  gap between them is worth a look.
- **Move in** says which files it reads before you choose one, and calls an OFX bank download what
  it is (it said "This CSV has no Account column").
- **Home's Looking ahead** is a 30-day glance ("Looking ahead: next 30 days"); longer ranges are in
  Reports. The tour now opens each page it describes, from first sign-in and from Help alike.
- The sample data comes with a sample receipt and a sample statement, so Files has something to show.
- French, Spanish and Portuguese: "Cleared" in the register was translated as "erased"; fixed.

## 1.0.6 (2026-11-27)

- **A card's payment can be changed in either place:** open it in Bills & Deposits to change which
  account pays it, the amount or the date (across environments too), and the card's details follow;
  change the card's details and the payment follows. A payment left behind when a card or its paying
  account was moved between environments no longer stays stuck on the old account: the card takes
  it back the next time its details are saved, and stops any other copy.
- Renaming an account or an environment updates the names shown on transfers between environments.
- **Restart in Docker and Unraid:** Settings → This computer → Restart MoneyThistle stopped the
  container, which stayed stopped (the page showed 502) until it was started from the Docker tab.
  It now starts again by itself, in the same container.
- Reminders: a new choice, **Automatic items coming due too** (Settings → Notifications), for those
  who want autopay and direct deposits in the daily summary as well. Off unless ticked, as in 1.0.5.
- Narrow screens: rows of buttons wrap instead of running past the edge of their card (the people
  list, among others), long email addresses break, small tags stay whole, card headings put their
  buttons under the title when needed, and money columns can wrap on phones. The People page's
  introduction no longer slides under its Change history button.

## 1.0.5 (2026-11-26)

- **Welcome email** for new people (when email is set up): who added them, their user name, the
  addresses to open MoneyThistle at, what they can see, and a link to choose their own password
  (once, for 3 days), so no starting password is needed. Adding a person can also put them in one
  of your environments right away, and **Email a welcome** in the people list sends it again.
- **Settings ask before losing changes:** leaving a Settings page (another section, another page)
  with changes not yet saved asks to save, not save, or keep editing; reloading or closing the tab
  gets the browser's own warning.
- **Deleting an account works when it's connected or shared:** it used to refuse without showing
  why. Now it says so and offers to end the connection or sharing and delete it. Entries on the other
  side of its transfers stay and keep saying where the money went ("Transfer to Visa (deleted)",
  or "Transfer to Visa (Personal)" in another environment).
- **A card paid from another environment's account:** a card's **Pay from** also lists accounts in
  other environments you own. The payment is kept where the money leaves (say Household's checking),
  connected by itself, and shows on the card's side too: its Bills & Deposits and Home, to record or
  change from either. It counts in the budget of the environment the money leaves, once.
- **Reminders only for what needs you:** the daily summary leaves out automatic items (autopay,
  direct deposit) and includes the bills of accounts shared with you, each item once.
- **Clear ended connections:** connections and shared accounts that ended or were declined no
  longer pile up: **Clear them** (People & access) removes them from the lists. Entries made through
  them stay as they are.
- **Emails look like MoneyThistle:** the wordmark on the navy band, the message on a card, links you
  can click and a button for the password link (plain text still goes along for every email app).

## 1.0.4 (2026-11-26)

- A loan or mortgage brought in from another program (a plain loan account, without a rate or
  payment) now says so in its register and offers **Set up loan details…**, filled in from its own
  payments: rate, lender, payment, how often and the paying account. Then it has its Loan card,
  payment schedule, **Make a payment** and **What if…**; its register and balance stay as they are.
- Saving a loan's details no longer clears the account's notes, favorite or closed mark.
- In a register, entries dated after today have a bar on the left and a soft shade (amber in the
  light look, grey in the dark), so the past and the future are easy to tell apart.
- Behind the scenes: **Schedule…** (from a register entry) and the payment a loan's **What if…**
  suggests for another "how often" are now worked out only by the server, so each rule lives in one
  place. Nothing changes on screen.

## 1.0.3 (2026-11-25)

Security hardening (see the new SECURITY.md):

- Changes are refused unless the browser says they come from MoneyThistle's own page (on top of
  the header other websites can't send).
- The page carries a Content-Security-Policy: the browser runs only MoneyThistle's own scripts,
  loads only its own files and won't show it inside another site.
- The limit on wrong passwords (10 per address in 10 minutes) now lasts through a restart.
- A new automated test tries every one of the server's routes as someone signed out, someone
  outside the environment, someone with one shared account and a viewer, and checks nothing
  private is shown or changed.
- SECURITY.md: what MoneyThistle protects against, what it doesn't, and how to report a problem
  privately.

## 1.0.2 (2026-11-25)

- A small coffee cup in the top bar and one quiet line at the bottom of the page (a different one
  each day) link to the maker's Buy Me a Coffee page, for anyone who'd like to chip in. Nothing is
  sent there unless you click. Each person can hide them in Settings → Look; an administrator can
  hide them for everyone.
- Fewer antivirus warnings on Windows: MoneyThistle no longer starts hidden PowerShell when it
  starts. It asks Windows directly where the Start menu and desktop are and makes shortcuts with
  Windows' own shortcut maker, and a copy installed by the setup leaves its Start menu entries and
  desktop icon to the setup. (Code signing, the full fix, is still to come: see docs/PUBLISHING.md.)

## 1.0.1 (2026-11-25)

- Registers listed oldest first open at their end, where the newest entries are; after saving an
  entry the register stays where it was.
- **Schedule…** on an open register entry starts a new scheduled bill, deposit or transfer from it:
  payee, account, category and amount filled in, with how often and the next date guessed from the
  same payee's other entries. Handy for setting up the schedule again after moving in from another
  program.
- **What if…** on a loan: try a one-time extra payment toward principal, extra with every payment,
  or paying twice a month or every other week, and see when it would be paid off and the interest
  it would cost, next to how it is now. Nothing is saved.
- **Loan calculator** (under the account list): the payment for a price, or the price a payment
  you can afford can buy, with a down payment or trade-in; **Set up this loan…** starts a new loan
  from it.

## 1.0.0 (2026-11-24)

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
- Paystubs and split payments show as one line in the register, their parts a click away (▸).
  Every window closes with ✕, Escape or a click beside it, asking to save when something changed.
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
