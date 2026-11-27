// MoneyThistle's in-app help: guides, frequently asked questions and definitions.
// Shown by the Help page (app.js renderHelp); plain data so it's easy to keep current.
// Bodies are trusted HTML written here (never anything a person typed).
"use strict";
const HELP = {
  guides: [
    { id: "about", title: "About MoneyThistle", body: `
      <p><b>Why it exists.</b> For years, Microsoft Money Plus Sunset was the last of a good thing: a free, offline
      money program that kept everything on your own computer. Microsoft stopped making Money long ago, and the Sunset
      edition only grows older. MoneyThistle began as one household's wish to keep that way of doing things, made simpler:
      the same accounts, registers, bills, budget and reports, running at home (on a computer, a home server or in Docker),
      opened in any web browser on the family's computers and phones, with no bank connections, and with automatic backups
      to Nextcloud or similar places. It's meant to be something anyone in the family can use, not only the person who set it up.</p>
      <p>It was built after studying how Money Plus Sunset behaves (its categories, account types, bill schedules and backup
      rules) and then written anew; it contains none of Microsoft's code.</p>
      <p><b>How it was made: "vibe coded".</b> To be clear and upfront: MoneyThistle was written by an AI. Nearly all of its code,
      its screens, this Help and its automated tests were produced by Anthropic's Claude, from plain-language requests. Its
      human maintainer decided what it should do and how it should feel, used and tested every feature, reported what was
      wrong, and asked again until it worked. The maintainer has not reviewed the code line by line.</p>
      <p><b>What that means for you.</b> MoneyThistle has a suite of automated tests and real everyday use behind it, but it has
      had no professional code review or security audit. So:</p>
      <ul>
        <li>Keep backups (MoneyThistle makes them by itself; check now and then that they verify).</li>
        <li>Keep it on your home network or Tailscale, never open to the public internet.</li>
        <li>Check important numbers against your bank and card statements, as you would with any money program.</li>
        <li>If you can read code: reviews, bug reports and fixes are very welcome.</li>
      </ul>
      <p><b>Free software.</b> MoneyThistle is free and open source under the GNU AGPL-3.0, and comes with no warranty. You may use,
      change and share it; a changed version you offer to others, also as a website, must share its changes too. The link at
      the bottom of every page downloads the source code of exactly this copy. It takes no data from you and sends nothing
      anywhere except where you tell it to (your backups and notifications).</p>` },
    { id: "start", title: "Getting started", tab: "home", body: `
      <p>MoneyThistle keeps your household's money in one place: accounts and their registers, bills and
      deposits on a schedule, a monthly budget, reports and automatic backups. There's no bank connection:
      you type entries in, or bring them in from a file your bank lets you download.</p>
      <ol>
        <li><b>Add your accounts</b> (Accounts → New): checking, savings, credit cards, loans, investments.
          Enter each one's balance as of a date, and for cards and loans, what you owe.</li>
        <li><b>Put regular bills and paychecks on the schedule</b> (Bills &amp; Deposits) so Home can show
          what's coming and the budget knows what to expect.</li>
        <li><b>Enter what happens</b> in each account's register, or with <a href="#/help/quick">Quick add</a>
          on your phone.</li>
        <li><b>Turn on backups</b> (Backups): a folder, and ideally Nextcloud or another WebDAV server too.</li>
      </ol>
      <p>Customize Home with <b>Customize</b> on the Home page. Replay the tour any time from this Help page.</p>` },
    { id: "register", title: "Accounts and the register", tab: "accounts", body: `
      <p>Each account has a <b>register</b>: every entry with its date, payee, category, amount and the
      running balance. Type a new one into the line at the bottom: choose <b>Withdrawal</b> or
      <b>Deposit</b>, then fill in the payee; MoneyThistle remembers each payee's usual category and amount.</p>
      <ul>
        <li><b>Change an entry:</b> click it in the register. It shows in the line at the bottom, locked; choose
          <b>Edit transaction</b>, change it, then <b>Save changes</b> (or <b>Cancel</b>). The trash can deletes it.</li>
        <li><b>Paystubs and split payments</b> show as one line; <i>▸ parts</i> on it shows each part (taxes,
          deductions, principal and interest), and clicking the line opens it. Close any window with ✕, Escape or a click
          beside it: when something was changed, it asks whether to save first.</li>
        <li><b>Transfers:</b> as the category, pick "Transfer to …" another account. The matching entry is
          added to the other account by itself.</li>
        <li><b>Split entries</b> (a loan payment, a paystub) show as one line with their parts beneath.</li>
        <li><b>Dated after today:</b> entries for days still to come have a bar on the left and a soft shade, so the past and the future are easy to tell apart.</li>
        <li><b>Order:</b> "Newest first" switches the order. Entries on the same day can be moved with ▲ ▼.</li>
        <li><b>Cleared and reconciled:</b> click the status column to mark an entry cleared (C) or reconciled (R).
          <b>Balance account</b> walks you through matching a statement.</li>
        <li><b>Account details</b> keep the bank, account number, website, phone and interest rate, and for
          cards the limit and statement days.</li>
      </ul>` },
    { id: "cards", title: "Credit cards", tab: "accounts", body: `
      <p>Each card is kept one of two ways (Account details → <i>How do you keep this card?</i>):</p>
      <ul>
        <li><b>Statement balance:</b> once a month you enter the balance from the statement; one entry brings the
          card to what it owes. With the closing day filled in, Home reminds you when a statement has closed.</li>
        <li><b>Each purchase:</b> you enter every charge. The scheduled-items budget shows this month's charges
          as pending, paid later through the card payment, so nothing counts twice.</li>
      </ul>
      <p><b>Paying a card:</b> a transfer from checking to the card. A button offers the last statement's balance
      (less what's been paid since). Tick <i>Keep the card payment on my schedule</i> to have the payment on
      Bills &amp; Deposits every month on the due day.</p>
      <p><b>A card for one kind of spending</b> (HSA-eligible care, giving, a business): choose it under
      <i>What is this card used for?</i>. Its charges and statements then go to that category by themselves.</p>
      <p><b>Last day of the month:</b> enter 31 for the closing or due day. Shorter months use their last day;
      29 and 30 work the same way in February.</p>` },
    { id: "receipts", title: "Receipts and other files", tab: "files", body: `
      <p>Keep a photo of the receipt, or a PDF (an invoice, a warranty, a medical bill for your HSA), with the entry it belongs to.</p>
      <ul>
        <li><b>On a phone:</b> under a new entry, <b>📷 Take a photo</b> opens the camera; the photo is attached when you
          press Enter. <b>Choose a photo or file</b> picks one you already have.</li>
        <li><b>Later:</b> pick the entry in the register and choose <b>Receipts</b> to add more, open, download or remove them.
          Entries with something attached show a paper clip.</li>
        <li><b>Papers kept with an account:</b> on a card you only enter statements and payments for, there's no entry for
          the TV you bought. Choose <b>Papers</b> on the account's page to keep the receipt, warranty or contract with the
          account itself, with the date it's from.</li>
        <li><b>Notes and keywords:</b> give any file a short note ("TV, warranty 2 years, serial 12345") when adding it,
          or later under it. Everything you type is saved when you leave the box.</li>
        <li><b>Files</b> (in the menu) lists every receipt and paper in this environment, newest first. Search by any words
          in the note, file name, payee or account; narrow it to one account or a time period; click a column to sort.</li>
        <li>Photos are made smaller before they're sent (about 400 KB instead of several MB); a PDF can be up to 20 MB.</li>
        <li>The files are kept in the data folder and go into every backup, including Nextcloud.</li>
        <li>Deleting an entry sets its files aside for 60 days, so undoing the delete (History) brings them back.</li>
      </ul>` },
    { id: "paystubs", title: "Paychecks and paystubs", tab: "accounts", body: `
      <p>Record a paycheck with as much as you know. <b>Take-home pay</b> (what reached your bank) is enough; gross pay and
      deductions from the pay slip can come now or later. In the account the pay goes into, choose <b>Paystub…</b> above the
      entry line. Only take-home pay is required.</p>
      <ul>
        <li><b>Other deductions:</b> once you add the gross pay, whatever isn't itemized (gross pay minus take-home pay minus
          the deductions you typed) is shown and saved as <b>Other deductions</b>. Itemize as much or as little as you like; at $0
          everything is itemized. If the deductions come to more than gross minus take-home, the paystub can't be saved until the
          amounts add up.</li>
        <li><b>Added after taxes:</b> money in the take-home pay that isn't pay (an expense reimbursement, a refund). Add it under
          <b>+ Something added after taxes</b> so it doesn't hide a deduction.</li>
        <li><b>Scheduled paychecks:</b> in Bills &amp; Deposits, tick <b>This is a paycheck</b> on the deposit (its amount is the
          take-home pay, or its average). When it's due, <b>Enter</b> offers <b>Record take-home only</b> or <b>Fill in the paystub</b>.</li>
        <li><b>Adding details later:</b> a paycheck recorded with only its take-home pay is marked <b>Paycheck</b> in the register;
          open it and choose <b>Add paystub details</b>.</li>
        <li><b>What's missing is flagged:</b> MoneyThistle learns what's usual for each employer (take-home only, gross and take-home,
          or every tax and deduction) from its latest paychecks. A paycheck with less than usual shows <b>⚑</b> in the register
          (<i>missing gross pay</i>, <i>missing: Medicare</i>, or <i>$220.00 not itemized</i> when that employer's paychecks are
          usually fully itemized), and the year-end tax report lists them under <b>Paychecks to check</b>.
          If gross and take-home is your usual, Other deductions are never flagged; if take-home only is your usual, nothing is.
          <b>Complete as is</b> stops the flag for one that won't get more detail.</li>
        <li>Each tax or deduction goes to a category (Federal Income Tax, Insurance : Health…) or to one of your
          accounts (a 401(k), an HSA), where it shows up as money in. Don't keep that account in MoneyThistle? Use <b>Savings &amp; Investments</b>
          (Retirement Plan, HSA/FSA) instead. Each new paystub starts as a copy of the last one;
          move lines with ▲ ▼ (or Alt+↑ ↓) to match your paystub's order.</li>
        <li><b>Paid into more than one account</b> ($250 into savings, $3,210.14 into checking): under <i>Deposited into</i>,
          choose <i>+ Add an account</i> and enter what reached each one. The take-home pay is their total. Works with
          take-home pay only too. A scheduled paycheck's amount can be the total or what reaches its own account. A scheduled deposit can list more than one account too (Bills &amp; Deposits, <i>+ Add an account</i>), each with a
          set amount or the average of what it got before; they're recorded together.</li>
        <li>In the budget a paycheck counts as its take-home pay. Reports show every line, and the year-end
          tax report shows gross vs take-home pay for each employer.</li>
      </ul>` },
    { id: "bills", title: "Bills & Deposits (the schedule)", tab: "bills", body: `
      <p>Everything that repeats: bills, paychecks, transfers to savings, loan and card payments. Each item has
      an account, an amount and how often it happens, from daily to yearly (or only once). A monthly item can
      fall on the <b>last day of the month</b>.</p>
      <ul>
        <li><b>Enter</b> records the next one in the register (you can change the amount and date first);
          <b>Skip</b> moves past one that didn't happen. A receipt, statement or paystub can go with it:
          choose <b>Add a receipt or file</b> (or <b>Take a photo</b> on a phone) before recording.</li>
        <li><b>Amount varies:</b> the schedule expects the average of the last ones entered.</li>
        <li><b>Automatic ⟳:</b> mark items that happen by themselves (autopay, direct deposit). Choose
          <i>record it for me</i> and MoneyThistle enters each one on its date, marked ⟳ in the register.</li>
        <li>Home lists what's due soon; Reports → Looking ahead uses the schedule to forecast balances.</li>
      </ul>
      <p>Colors and symbols: money in is green <b>+</b>, money out is orange <b>−</b>, moves between your own
      accounts are blue <b>⇄</b>.</p>` },
    { id: "budget", title: "The budget", tab: "budget", body: `
      <p>Two styles; switch with the buttons at the top of the Budget page:</p>
      <ul>
        <li><b>By category:</b> each category in the budget gets a monthly amount. Leave one at 0 and it expects
          what your schedule holds for it that month. Spending shows against each line as you go.</li>
        <li><b>By scheduled items:</b> for people who don't track categories. Each bill, deposit and transfer on
          the schedule is a line: what's expected this month and what's been entered.</li>
      </ul>
      <p>Loan payments count whole (principal, interest and escrow together). Paystubs count at their take-home
      pay. Something entered early with next month's date counts in next month; the budget points it out.</p>` },
    { id: "reports", title: "Reports", tab: "reports", body: `
      <ul>
        <li><b>Where the money goes / comes from:</b> totals by category for a period. Click one to see its entries.</li>
        <li><b>Income vs. spending:</b> month by month for the last year.</li>
        <li><b>Net worth over time:</b> everything you have less everything you owe, month by month.</li>
        <li><b>Looking ahead:</b> each account's balance day by day from today, using your schedule. Tick
          accounts to draw them; click a scheduled item to mark its day.</li>
        <li><b>Taxes:</b> see <a href="#/help/taxes">the year-end tax report</a>.</li>
      </ul>
      <p>Accounts shared into this environment are included.</p>` },
    { id: "taxes", title: "The year-end tax report", tab: "reports", body: `
      <p>Reports → <b>Taxes</b> gathers everything in categories marked <b>Tax related</b> (set that under
      Categories) for one calendar year, each entry listed: income, then deductions and expenses. Download it as
      a spreadsheet or print it (or save it as a PDF) for your tax preparer.</p>
      <ul>
        <li><b>Pay:</b> with paystubs entered, gross vs take-home pay for each employer and every tax and deduction.
          There's no W-2 to type in: compare these totals with the W-2 your employer sends.</li>
        <li><b>Health Savings Accounts:</b> mark an account as an HSA in its details and say who puts money in.
          The report adds up your own after-tax contributions (deductible) and pre-tax ones (employer or
          payroll, on your W-2) across <i>all</i> your HSAs, compares them with the yearly limit you enter, and
          lists withdrawals. Your own contributions made January 1 – April 15 can count for the year before.</li>
      </ul>
      <p>It's a summary to check against your tax forms, not tax advice.</p>` },
    { id: "import", title: "Importing from your bank", tab: "accounts", body: `
      <p>In an account's register, choose <b>Import file</b> and pick a file downloaded from your bank's website:
      <b>OFX, QFX or QBO</b> (best: they carry the bank's own ids), <b>CSV</b> (a spreadsheet with Date and Amount
      columns, or Debit/Credit) or <b>QIF</b>.</p>
      <p>Before anything is added you see a review: entries that match one you already have (same amount within
      a few days) are matched rather than added twice; exact duplicates are skipped; you decide the rest.
      Importing the same OFX file twice adds nothing.</p>` },
    { id: "move-in", title: "Moving in from another program", tab: "settings", body: `
      <p>Settings → <b>Bring in everything from another program…</b> brings in every account and its history at once.</p>
      <ul>
        <li><b>Microsoft Money:</b> File → Export, once for each account (Loose QIF is fine). Choose all the files together;
          each account takes its real name from its opening balance, and transfers between them pair up.</li>
        <li><b>Quicken, Moneydance, KMyMoney, HomeBank, Money Manager Ex, Banktivity:</b> export everything to one QIF file.</li>
        <li><b>YNAB, GnuCash, Actual Budget, Mint, Firefly III:</b> their CSV export of all transactions. Any other CSV works
          when it has Account, Date, Payee, Category and Amount columns.</li>
      </ul>
      <p>You see what's in the file first: each account with its entries, dates and balance, and the categories it would add. For each
      account choose a new account, one you already have, or leave it out. Nothing changes until <b>Bring it in</b>.</p>
      <p>Comes across: accounts, opening balances, categories, payees and every transaction with its splits, transfers and cleared marks.
      Doesn't: scheduled bills, budgets and investment holdings. Entries already in an account you choose aren't added twice.
      Make a backup first; a single account's bank download still goes through <a href="#/help/import">Import file</a>.</p>
      <p>To set up your schedule again, open a register and click a bill, paycheck or transfer that repeats, then <b>Schedule…</b>.
      It fills in a new scheduled item from that entry: the payee, account, category and amount, and how often and the next
      date from the same payee's other entries in that account (an amount that changes is set to vary, at its average).
      Check it and save.</p>
      <p>A loan or mortgage comes across as a plain loan account, without its rate and payment. Open it and choose
      <b>Set up loan details…</b>: they're filled in from its payments (check them against a statement), and then it has its
      payment schedule, payoff date and <b>What if…</b>. Its register and balance stay as they are.</p>` },
    { id: "history", title: "Change history and undo", tab: "history", body: `
      <p>MoneyThistle records every entry, scheduled item, account, category and budget amount that's added, changed or
      deleted: who did it, when, in which environment, and how it looked before and after. It's kept for a year and is
      part of every backup.</p>
      <ul>
        <li><b>Everything:</b> People → <b>Change history</b> (or Settings → Your data). Filter by environment or person, or search.</li>
        <li><b>One entry:</b> click it in the register, then <b>History</b>.</li>
        <li><b>Undo:</b> changes to entries and scheduled items can be undone by anyone who may change that environment:
          an added entry goes, a changed one goes back to how it was, a deleted one comes back (a transfer with both its sides).
          If it was changed again afterwards, undo the later change first. For anything else, restore a backup.</li>
      </ul>` },
    { id: "allenvs", title: "Seeing several environments together", tab: "home", body: `
      <p>With accounts in more than one environment (private ones in Personal, shared ones in Household), Home, Accounts,
      Bills &amp; Deposits, Budget and Reports have an <b>Environments</b> picker at the top. Tick the ones to see together,
      say Personal and Household but not Business. The one you're in is always included. <b>All</b> ticks every one;
      <b>Only</b> followed by the current name clears the rest. The choice is the same on every page and remembered in this browser.</p>
      <ul>
        <li>Everything adds up across the ticked environments; each item shows which one it's in. An account shared between
          two of them counts once, and transfers between them aren't spending.</li>
        <li>Changes are still made in an item's own environment: entering a bill, opening an account or a statement from
          another environment switches to it.</li>
        <li>The combined budget is for looking: lines with the same category add up. Budget amounts are set in each environment.</li>
      </ul>` },
    { id: "signin", title: "Signing in and forgotten passwords", tab: "settings/people", body: `
      <p>Everyone has their own sign-in. Change your name, email or password under <b>People → Your sign-in</b>.</p>
      <ul>
        <li><b>Keep me signed in on this device:</b> ticked when signing in, you stay signed in for 30 days, also after the computer
          restarts. Left off (best on shared devices), you're signed out when the browser closes, or after an hour without use.
          <b>Sign out</b> ends it at once.</li>
        <li><b>Forgot your password?</b> On the sign-in page choose <i>Forgot your password?</i>. If your sign-in has an email address
          and an administrator set up email (Settings → Notifications), MoneyThistle emails you a link to choose a new one. The link
          works once, for 30 minutes, from your home network or Tailscale.</li>
        <li><b>No email?</b> Any administrator can set a new password for you under People.</li>
        <li><b>The only administrator, locked out:</b> on the computer or server MoneyThistle runs on, run
          <code>python main.py --reset-password YOUR-USER-NAME</code> in its folder (with Docker:
          <code>docker exec -it moneythistle python main.py --reset-password YOUR-USER-NAME</code>).
          <code>--list-users</code> shows the user names.</li>
      </ul>
      <p>Whenever a password changes, every device using it is signed out, and the person gets an email about it (when they have an address).</p>` },
    { id: "quick", title: "Quick add on your phone", tab: "quick", body: `
      <p>On a phone, the round <b>+</b> button (or the address <code>#/quick</code>) opens a screen made for one
      thumb: choose money out, money in or a move, type the amount, the payee and the account, and save.
      What's due today can be entered from there too.</p>
      <p>Add MoneyThistle to your phone's home screen (in the browser's share or menu: <i>Add to Home Screen</i>)
      and it opens like an app. The phone needs to reach MoneyThistle: on your home network, or through Tailscale.</p>` },
    { id: "people", title: "People, environments and sharing", tab: "settings/people", body: `
      <ul>
        <li><b>People:</b> everyone signs in with their own user name and password. Administrators add sign-ins
          and reset passwords.</li>
        <li><b>Welcome email:</b> with email set up (Settings › Notifications), adding someone can email them a welcome:
          who added them, their user name, the addresses to open MoneyThistle at, what they can see, and a link to choose their
          own password (it works once, for 3 days), so you don't have to make one up. <b>Email a welcome</b> in the list sends it again.</li>
        <li><b>A card paid from another environment:</b> in a card's details, <b>Pay from</b> also lists accounts in other
          environments you own. The payment is kept where the money leaves (say Household's checking), connected by itself,
          and shows on the card's Bills &amp; Deposits and Home too, to record or change from either side.</li>
        <li><b>Environments</b> are separate sets of accounts (Personal, Business, In-laws…). Only members see one.
          Owners add members as owner, editor (can change things) or viewer (can only look). Switch at the top right.</li>
        <li><b>Shared accounts:</b> show one account in another environment too (your checking in your spouse's
          environment): one register, one balance, seen in both, optionally with its bills and deposits.</li>
        <li><b>Connections</b> let you move money between environments: "Transfer to …" fills in the other side.</li>
        <li><b>Moving accounts:</b> to give accounts a new home (say, from your Personal environment to a Household one you
          both own), open the account, choose <b>Account details → Move to another environment…</b>, tick every account to
          move together, and check what will happen before it does. Everything comes along: transactions, scheduled items,
          categories and payees. Transfers to accounts that stay behind become transfers between environments. A backup is
          made first.</li>
      </ul>` },
    { id: "backups", title: "Backups", tab: "settings/backups", body: `
      <p>MoneyThistle backs up by itself: after changes, and on a schedule. Each backup holds everything: all
      environments and sign-ins.</p>
      <ul>
        <li><b>Where:</b> a folder, and Nextcloud or any WebDAV server (use a Nextcloud <i>app password</i>). The
          backup folder there is created if it doesn't exist.</li>
        <li><b>Checked:</b> after each upload the copy is downloaded again and compared; a bad copy is deleted.
          <b>Verify</b> checks any backup on demand.</li>
        <li><b>Encryption:</b> with a backup password, backups can't be read without it. Keep that password safe:
          <b>a lost password can't be recovered</b>, and neither can its backups.</li>
        <li><b>How far back:</b> the newest few after-change backups, plus the last backup of each of the latest 7 days,
          4 weeks and 12 months. A busy day of changes can't push out yesterday's backup, so a mistake found later can
          still be undone. <b>Back up now</b> copies are kept until you delete them. The list says why each one is kept.</li>
        <li><b>Restore</b> any backup from the Backups page. It puts back everything as it was then (a safety copy of
          now is made first). For one entry or scheduled item changed by mistake, <b>Change history → Undo</b> is quicker
          and leaves everything else as it is.</li>
      </ul>` },
    { id: "startover", title: "Starting over from a backup (new computer or server)", tab: "settings/backups", body: `
      <p>The computer died, was stolen, or you're moving MoneyThistle to a server. All you need is a backup: one on Nextcloud,
      or a backup file (<code>money-…zip</code>, or <code>.zip.enc</code> when encrypted) and, if it's encrypted, <b>its backup password</b>.</p>
      <ol>
        <li><b>Install MoneyThistle</b> on the new computer or server, the same way as the first time: on a computer, put the
          MoneyThistle folder somewhere and double-click <b>Start MoneyThistle</b> (Python 3.10 or newer is needed); on a server,
          Docker Compose or the Unraid install script. Don't create a sign-in yet.</li>
        <li><b>Open it in the browser.</b> A new install shows <i>Set up MoneyThistle</i>. Under it, open
          <b>Moving here from another computer or server? Start from a backup instead</b>.</li>
        <li><b>Choose the backup:</b> either pick the backup file and type its password, or enter your Nextcloud backup folder's
          address, user name and app password, choose <b>Show its backups</b>, pick one (the newest is first) and restore it.</li>
        <li><b>Sign in</b> with your usual user name and password. Everything is back: every environment, account, entry,
          receipt, change history and sign-in.</li>
        <li><b>Check Settings and Backups.</b> These belong to the computer, not the backup, so set them again: the Nextcloud
          connection if you restored from a file (from Nextcloud it's set up for you), notifications, "Other devices", and how
          MoneyThistle starts. The backup password you typed is kept for new backups.</li>
      </ol>
      <ul>
        <li><b>On a server without a browser at hand:</b> stop MoneyThistle, then run
          <code>python main.py --restore money-….zip.enc</code> in its folder (it asks for the backup password), and start it again.</li>
        <li><b>Already running and set up?</b> An administrator uses <b>Backups → Restore from a file…</b> (or <b>Restore</b> next to a
          backup in the list). A safety copy of everything as it is now is saved first.</li>
        <li><b>Practise once:</b> restoring onto a spare computer or a test container is the only sure proof your backups work.
          <b>Verify</b> on the Backups page checks a backup opens without changing anything.</li>
      </ul>` },
    { id: "simple", title: "Simple or Everything", tab: "settings/look", body: `
      <p>Each person chooses how much MoneyThistle shows them, in <b>Settings → Look</b>. New sign-ins start <b>Simple</b>.</p>
      <ul>
        <li><b>Simple</b> shows the everyday things. Extras are folded under <b>More options</b> (or <b>More fields</b>), ready when
          you want them: an entry's number, memo and status; a paystub's separate taxes and deductions (Simple asks for gross pay and
          the total taken out); an account's bank details, rates and card days; a scheduled item's varying amount, automatic recording
          and last-day-of-month; backup timing and other places to keep backups. Moving accounts between environments is left out,
          and the environment list at the top only shows when there's more than one.</li>
        <li><b>Everything</b> opens all of it.</li>
        <li>Whatever you open or close is remembered for you, place by place: open a paystub's taxes once, and they stay open there.</li>
        <li>Nothing is ever hidden that affects whether your numbers are right, and a fold says <b>● filled in</b> when something inside it
          has a value.</li>
      </ul>` },
    { id: "notifications", title: "Notifications", tab: "settings/notifications", body: `
      <p>The daily summary reminds you of what needs you: items that aren't automatic, coming due or late, in every
      environment you're in and every account shared with you, each once. Automatic ones (autopay, direct deposit) aren't
      in it unless you tick <i>Automatic items coming due too</i>: they happen by themselves.</p>
      <p>Settings → Notifications sends a daily summary (what's due, what was recorded automatically, backup
      problems) by email, Pushover, ntfy or Gotify. Each person sets up their own; email can use the shared mail
      settings an administrator entered, or the person's own.</p>` },
    { id: "startstop", title: "Starting and stopping MoneyThistle", tab: "settings/computer", body: `
      <p>MoneyThistle is a small server; your browser only shows it. <b>Closing the browser tab doesn't stop it</b>, because phones
      and other computers may be using it. On a computer (not Docker), an administrator chooses in <b>Settings → This computer</b>:</p>
      <ul>
        <li><b>Start menu:</b> MoneyThistle puts itself there the first time it starts: <b>MoneyThistle</b> opens it in the browser,
          starting it first if it isn't running, and <b>Stop MoneyThistle</b> stops it. A desktop icon is offered when you set it up,
          and in Settings.</li>
        <li><b>When I sign in to this computer:</b> it starts by itself in the background each time you sign in.</li>
        <li><b>When the computer starts, even if nobody signs in:</b> Windows starts it every time the computer turns on, so a bookmark on
          your phone always works while the computer is on; you never start it yourself. Choosing it asks for Windows administrator
          permission once, so choose it in a browser on that computer. To stop that, pick one of the other choices (no permission
          needed then); MoneyThistle keeps running until you shut it down or restart the computer. On a Mac or Linux, paste the
          command shown into a terminal.</li>
        <li><b>⏻ Shut down</b> (top of the page, administrators): saves, makes its backup and stops. Nobody can open it until it's
          started again from its icon (or the computer restarts, if it starts with the computer).</li>
        <li><b>Docker:</b> the container starts with the server and keeps it running; stop it with <code>docker stop moneythistle</code>.</li>
      </ul>` },
    { id: "settings", title: "Settings and updates", tab: "settings", body: `
      <ul>
        <li><b>Look:</b> light or dark, accent color, date style, and your <b>language</b>: English, French (Canada), Spanish
          (Latin America) or Portuguese (Brazil). Dates and amounts then follow that language's style. The translations were
          made by AI and haven't been checked by a native speaker yet. Names you typed (accounts, payees, environments)
          always show exactly as you typed them. Categories can have a name in each language (in a category's details,
          under <i>Name in other languages</i>); the starting categories come with all of them, and a category without
          one shows its own name.</li>
        <li><b>Currencies:</b> each account has its own currency (in its details): the Americas' currencies and the euro.
          A transfer between two currencies asks for the amount that actually arrived; no exchange rates are looked up.
          Under Look, <b>Currencies</b> sets the main one (totals, the budget and the tax report are in it) and optional
          rough rates for the others: net worth and reports count other currencies at those rates, marked approximate, and
          leave out a currency with no rate. The tax report keeps to the main currency.</li>
        <li><b>Other devices:</b> a copy running on a computer listens to that computer only, unless you allow
          other devices on your home network (then restart). Addresses to open it are at the bottom of every page.</li>
        <li><b>Updates:</b> MoneyThistle asks GitHub once a day whether a newer version is out (only its version
          number is sent; turn it off under Settings → This computer). On Windows, <b>Update now</b> installs it and
          starts again, or tick <i>Install new versions by itself</i>. On Unraid, the Docker tab's <i>update ready</i>
          updates the container; with Docker Compose, pull and start it again. Your data is kept.</li>
        <li><b>Where things are:</b> the app files, data folder, backups and log are listed under Settings.</li>
      </ul>` },
    { id: "safety", title: "Keeping it safe", tab: "settings", body: `
      <p><b>Never expose MoneyThistle to the public internet</b> (no port forwarding, no public reverse proxy).
      Use it on your home network or through a private VPN such as Tailscale. It has sign-in, but it isn't built
      or tested to withstand attacks from the internet, and nobody can guarantee a publicly exposed copy is safe.</p>
      <p>Use a strong password for each sign-in, keep backups in more than one place, and encrypt the ones that
      leave your home.</p>` },
  ],
  faq: [
    { q: "Does MoneyThistle connect to my bank?", a: `No. You type entries in, or import a file you downloaded from your bank (OFX, QFX, QBO, CSV or QIF). Nothing goes to a bank or anyone else.` },
    { q: "Why isn't something showing in this month's budget?", a: `Check its date: something entered for a later month counts in that month (the budget lists items entered ahead). Also check its category is in the budget, and for transfers, that they're payments (to a card or loan) rather than moves between your own accounts.` },
    { q: "What's the difference between a bill and a transfer?", a: `A bill is money leaving to someone else (orange −). A transfer moves money between your own accounts (blue ⇄); a transfer that pays a credit card or loan counts as spending in the scheduled-items budget.` },
    { q: "Should I enter each card purchase or just the statement?", a: `Either works. Statement balance is quicker: one entry a month. Entering purchases gives you spending by category as it happens. Choose per card in its Account details; see <a href="#/help/cards">Credit cards</a>.` },
    { q: "A transaction recorded itself. Why?", a: `It's an automatic item on Bills &amp; Deposits with "record it for me" on. Those are marked ⟳ in the register. Turn it off on the item if you'd rather enter it yourself.` },
    { q: "How do I fix a mistake in the register?", a: `Click the entry, choose <b>Edit transaction</b>, change it and choose <b>Save changes</b>. To remove it, use the trash can while editing.` },
    { q: "Can my spouse and I share accounts?", a: `Yes. Give each person their own sign-in (People), then share an account into their environment, or make them a member of yours. See <a href="#/help/people">People, environments and sharing</a>.` },
    { q: "Can I use it on my phone?", a: `Yes, in the phone's browser, on your home network or over Tailscale. Quick add (the + button) is made for phones. See <a href="#/help/quick">Quick add</a>.` },
    { q: "Where is my data kept?", a: `In the data folder listed under Settings → This computer: on a computer, your own app-data folder; in Docker or on Unraid, the data folder you mapped. Backups go where you set them up in Settings → Backups.` },
    { q: "I forgot my backup encryption password.", a: `Encrypted backups can't be opened without it, by design. Your money file itself isn't affected: set a new password in Settings → Backups and make a fresh backup right away.` },
    { q: "How do I restore a backup?", a: `Settings → Backups → pick the backup → Restore. MoneyThistle makes a safety copy of what you have first.` },
    { q: "Does restoring a backup also put back the old version of MoneyThistle?", a: `No: a restore brings back your data (accounts, entries, receipts, people), never the program. The MoneyThistle you have keeps running and reads the older data. A backup made by a <i>newer</i> MoneyThistle than yours is refused until you update, so nothing gets lost or mixed up.` },
    { q: "Is it safe to open MoneyThistle from the internet?", a: `No: keep it on your home network or Tailscale. See <a href="#/help/safety">Keeping it safe</a>.` },
    { q: "I forgot my password.", a: `Use <i>Forgot your password?</i> on the sign-in page, ask an administrator, or see <a href="#/help/signin">Signing in and forgotten passwords</a> for the way back in that works without email.` },
    { q: "Can I bring my history over from Microsoft Money or Quicken?", a: `Yes: every account, category and transaction. See <a href="#/help/move-in">Moving in from another program</a>.` },
    { q: "How do I see the tour again?", a: `Choose <b>Take the tour</b> at the top of this Help page.` },
    { q: "How do I remove the sample data, or start over?", a: `While sample data is in use, a bar at the top of every page offers
      <b>Start fresh with my own money</b>. Any time later, an owner can start an environment fresh under Settings → Your data
      (its name typed to confirm): accounts, entries, the schedule, the budget and receipts go; people, sign-ins, backup settings
      and other environments stay, and a copy of what was there is kept in MoneyThistle's data folder.` },
    { q: "How do I keep an investment's value current?", a: `MoneyThistle doesn't look values up. Open the account and choose
      <b>Update value</b>, then type what it's worth from its statement or website: the difference goes in as one
      <i>Change in value</i> entry, left out of budgets and spending reports. Investment and retirement accounts are reminded
      about monthly (beside the card statements); turn that off, or on for an asset such as a house, in the account's details.` },
    { q: "Can I see what an extra payment would do to my loan?", a: `Yes. Open the loan's account and choose <b>What if…</b> on its Loan card.
      Try an extra payment toward principal once (with the payment on a date you pick), extra with every payment, or paying
      twice a month or every other week instead of monthly. It shows when the loan would be paid off and the interest it would
      cost, next to how it is now. Nothing is saved; ask your lender before you change how you pay. To work out a loan you
      don't have yet, such as how much car a monthly payment can buy, use <b>Loan calculator</b> under the account list on the
      Accounts page; <b>Set up this loan…</b> starts a new loan from it.` },
    { q: "What's the coffee cup?", a: `MoneyThistle is free. The small cup at the top and the line at the bottom of the page link to its maker's
      Buy Me a Coffee page, for anyone who'd like to chip in; nothing is ever expected, and nothing is sent there unless you
      click. To hide them for yourself, untick them in Settings → Look → Coffee cup; an administrator can hide them for
      everyone there too.` },
  ],
  terms: [
    { term: "Account", def: "Somewhere money is kept or owed: checking, savings, a credit card, a loan, an investment." },
    { term: "Register", def: "An account's list of entries with a running balance, like a checkbook." },
    { term: "Transaction (entry)", def: "One line in a register: money in or out on a date." },
    { term: "Payee", def: "Who you paid or who paid you." },
    { term: "Category", def: "What money was for (Groceries, Rent) or where it came from (Wages). Main categories can have subcategories." },
    { term: "Tax related", def: "A category whose entries go into the year-end tax report. Set it under Categories." },
    { term: "Transfer (move)", def: "Money moving between two of your own accounts: one entry in each register, kept together." },
    { term: "Split", def: "One payment made of parts in different categories or accounts, such as a loan payment (principal, interest, escrow) or a paystub." },
    { term: "Cleared (C)", def: "Your bank has processed the entry." },
    { term: "Reconciled (R)", def: "The entry was matched against a statement with Balance account." },
    { term: "Scheduled item", def: "A bill, deposit, transfer or payment on Bills & Deposits that repeats." },
    { term: "Automatic ⟳", def: "A scheduled item that happens by itself; with 'record it for me', MoneyThistle enters it on its date." },
    { term: "Statement balance", def: "What a card's statement says you owe on its closing date." },
    { term: "Closing day / due day", def: "The day a card's statement closes, and the day its payment is due. 31 means the last day of the month." },
    { term: "Gross pay", def: "Pay before taxes and deductions." },
    { term: "Take-home (net) pay", def: "What reaches your account after taxes and deductions." },
    { term: "Pre-tax deduction", def: "Taken from pay before income tax, such as a 401(k), an HSA through payroll or health insurance. It lowers taxable wages (W-2 box 1)." },
    { term: "HSA", def: "Health Savings Account: money for medical costs with tax advantages, up to a yearly limit across all your HSAs." },
    { term: "Environment", def: "A separate set of accounts (Personal, Business…) that only its members see." },
    { term: "Shared account", def: "An account shown in another environment too: one register and balance seen in both." },
    { term: "Net worth", def: "Everything you have minus everything you owe." },
    { term: "Forecast", def: "Balances projected forward from today using your schedule (Reports → Looking ahead)." },
    { term: "WebDAV", def: "A standard way to store files on a server; Nextcloud speaks it. Used for backups." },
    { term: "Tailscale", def: "A private network between your own devices, so a phone away from home can reach MoneyThistle without exposing it to the internet." },
  ],
};
