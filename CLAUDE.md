# MoneyThistle: notes for Claude (and any other coding agent)

MoneyThistle is a self-hosted personal finance app (a "slightly better" Microsoft Money Plus
Sunset). It runs on this computer, a home server, Docker or Unraid. It has no bank connections and
must never be exposed to the public internet. The person who owns it doesn't code: explain
changes in plain words, and discuss before building when they ask to discuss.

## Philosophy

Do fewer things, well. Before adding a feature, check whether an existing screen already covers
it. Keep the screens simple by default (the "Simple" view folds extras under "More options").

## Layout

- `main.py`: starts the server and opens the browser; `--screenshot FILE.png` saves a picture of
  the home page and exits; `--data DIR` uses another data folder; `--port N`.
- `moneyapp/`: Python standard library only, no third-party packages.
  - `server.py`: the HTTP server and every `/api/...` route (`r(method, regex, fn, scope, share=)`).
  - `store.py`: one SQLite file per environment: accounts, transactions, categories, bills
    (scheduled items), budget, reports, currencies. Schema changes go in `_migrate` (add columns
    with `ALTER TABLE`, never drop data).
  - `system.py`: `system.db`: people, sign-in, environments, shares, automatic entries.
  - `paystubs.py`, `loans.py`, `backup.py`, `notify.py`, `migrate.py` (QIF/CSV/OFX import),
    `moveacct.py`, `attachments.py`, `currencies.py`, `defaults.py` (starting categories),
    `updates.py` (the daily check for a new version on GitHub; one-click update on Windows).
  - `static/`: the single-page app in plain JavaScript: `app.js` (screens), `i18n.js`
    (languages), `help.js` (Help, FAQ, terms, About), `lang/*.js` (translations), `style.css`.
- `tests/test_app.py`: the unit tests; `tests/i18n_check.js`: the translation matcher (node).
- `tools/`: `build_windows.py` (the Windows installer), `i18n_extract.py` / `i18n_build.py`
  (translations), brand and icon makers.
- `MECHANICS.md` and `mechanics.json`: the rules the app follows (amounts, dates, budgets, paychecks,
  currencies, languages). Keep them current when a rule changes.
- `CHANGELOG.md`: what changed, in plain words, per version.

## Commands

    python -W ignore -m unittest discover -s tests     # all tests (set NO_SHORTCUTS=1 on Windows)
    node --check moneyapp/static/app.js                # quick syntax check after editing the screens
    node tests/i18n_check.js pt                        # the translation matcher in Portuguese (fr, es too)
    python tools/i18n_build.py                         # rebuild lang/*.js and category_names.py
    python tools/build_windows.py                      # dist/MoneyThistle-Setup-<version>.exe
    python main.py --port 8199 --data <test folder> --no-browser   # a test copy to try things in

Run the tests after every change and add a test for each new behaviour (`tests/test_app.py`).

## Data safety

- Never open, change or delete the person's real data folder (`data/`, or wherever their install
  keeps it). Try things on a test copy in a folder of its own.
- Never commit data, backups, settings files or test copies (`.gitignore` already leaves them out).
- Commit or push only when the person asks.

## Languages

The screens are written in English; `i18n.js` translates text as it appears, from `lang/<code>.js`
(English text -> translation, `{}` for values). Names people type (accounts, payees, environments)
are never translated; categories have a name per language (`category_names` table). To add text:
write it in English in `app.js`, then add its French, Spanish and Portuguese in
`tools/i18n/extra.txt` (`@English|French|Spanish|Portuguese`) and run `tools/i18n_build.py`.
Help is translated as whole guides in `lang/help.<code>.js`: change all four when Help changes.
Open a page with `?i18naudit` to list text shown without a translation.

## Releasing

See `docs/PUBLISHING.md`: raise `VERSION` in `moneyapp/version.py`, add a `CHANGELOG.md`
section, push a tag `v<version>`. The release workflow tests, builds and signs (once SignPath is
set up) the Windows setup, publishes it with its `.sha256` (the in-app updater checks it), and
publishes the container image `ghcr.io/moneythistle/moneythistle` (tags `x.y.z`, `x.y`, `x`,
`latest`) that the Unraid template (`unraid/moneythistle.xml`) and `docker-compose.yml` use.
Screenshots in `docs/screenshots/` are made with `python main.py --screenshot FILE --page PAGE`.
