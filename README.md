# MoneyThistle

<img src="moneyapp/static/brand/wordmark-900.png" alt="MoneyThistle: A Slightly Better Money App" width="450">

*A Slightly Better Money App*

A simple personal money manager that runs in Docker and opens in your web browser.
Accounts, a check register, categories, scheduled bills and deposits, a monthly budget, reports,
and automatic backups to a folder and/or Nextcloud (or any WebDAV server). No bank connection:
type transactions in, or import CSV/QIF files your bank lets you download.

**What it's for:** household money, shared between the people in a home, and at most a very
simple sole proprietorship kept in its own environment. It is not business bookkeeping: no
invoices, receivables or payables, sales tax, payroll or double-entry books. It aims to do what it
does well rather than everything.

**How it was made:** MoneyThistle is "vibe coded". Nearly all of its code, screens, help and tests were
written by an AI (Anthropic's Claude) from plain-language requests; its human maintainer decided what it
should do, used and tested every feature, and has not reviewed the code line by line. It has automated
tests and everyday use behind it, but no professional code review or security audit: keep backups, keep
it off the public internet, and reviews and fixes are welcome. (In the app: Help → About MoneyThistle.)

Free and open source under the **GNU AGPL-3.0** (see `LICENSE`): use it, change it and share it;
if you offer a changed version to others, including as a hosted website, share your changes too.
What changed in each version: `CHANGELOG.md`.

**Name and logo:** the code is free to change and share, but the MoneyThistle name, logo and
wordmark identify this project. A changed version you share should have its own name and look,
so nobody mistakes it for MoneyThistle (saying it's "based on MoneyThistle" is welcome).

## Keep it off the public internet

**Never expose MoneyThistle to the public internet** (no port forwarding on your router, no public
reverse proxy). Use it only on your home network (LAN) or through a private VPN such as Tailscale.
It has sign-in, but it is not built or tested to withstand attacks from the internet, and nobody
can guarantee that a publicly exposed copy is safe. Securing such a setup is beyond what this
project takes responsibility for.

The `localhost` / `127.0.0.1` address works only on the computer MoneyThistle runs on. A phone or
another computer needs the server's network address (for example `http://192.168.1.20:8080/`) or
its Tailscale name.

## Install on Unraid

The image isn't on Docker Hub, so the server builds it once from this folder.

1. Copy this whole folder to the server, for example to
   `\\TOWER\appdata\moneythistle\src` (that is `/mnt/user/appdata/moneythistle/src`).
2. In the Unraid web page click the terminal icon (`>_`) and run:

   ```
   bash /mnt/user/appdata/moneythistle/src/unraid/install.sh
   ```

   It asks for a password for the web page, builds the image, and starts the container.
3. Open `http://TOWER:8080` from any device on your network, or over Tailscale with the
   server's Tailscale name or IP (the script prints both), e.g. `http://tower.your-tailnet.ts.net:8080`.

The container then shows in the **Docker** tab as `moneythistle` (WebUI link included) and starts
with the array. Your money file is in `/mnt/user/appdata/moneythistle/data`, local backups in
`/mnt/user/appdata/moneythistle/backups`, owned by `nobody:users` like other Unraid apps.

To update: copy the newer folder over `src`, then in the app open **Settings → Restart MoneyThistle**
(a notice also appears on every page when an update is waiting). The container reads its files from
`src`, so a restart is enough; your data is kept. Running the install script again also works
(and is needed once, for containers installed before this button existed).
Options: `PORT=8090 TZ=Europe/Berlin APP_PASSWORD='…' bash …/install.sh`.

The Unraid template (`unraid/moneythistle.xml`) is installed for you so you can edit settings
(port, folders, password, time zone, WebDAV) from the Docker tab. Don't press "force update" there:
the image is local, so rebuild with the script instead.

Installed it before the rename, as `home-ledger`? Copy the new version to the server (for example
to `/mnt/user/appdata/moneythistle/src`) and run its `install.sh`: it stops and removes the old
`home-ledger` container and its Docker-tab entry, keeps your sign-in password, and goes on using your
money file in `/mnt/user/appdata/home-ledger/data` (nothing is moved). With Docker Compose, double-click
**Update Docker container**: it replaces the old `home-ledger` container the same way.

### Locked out?

On the sign-in page, *Forgot your password?* emails a one-time link (30 minutes) when the sign-in has an
email address and an administrator has set up email under Settings → Notifications. Any administrator can
also set a new password under People. If you're the only administrator and can't get in, run this on the
computer or server MoneyThistle runs on (being able to do that proves it's yours):

```
python main.py --reset-password YOUR-USER-NAME                       # in the MoneyThistle folder
docker exec -it moneythistle python main.py --reset-password YOUR-USER-NAME   # Docker / Unraid
python main.py --list-users                                           # the user names
```

### Moving in from another program

Settings → *Bring in everything from another program…* reads QIF exports (Microsoft Money: one file per
account, chosen together; Quicken, Moneydance, KMyMoney, HomeBank, Money Manager Ex, Banktivity: one file)
and CSV exports from YNAB, GnuCash, Actual Budget, Mint and Firefly III (or any CSV with an Account column).
You see a preview and choose, per account, a new account, an existing one or to leave it out. Accounts,
opening balances, categories, payees, splits, transfers and cleared marks come across; scheduled bills,
budgets and investment holdings don't.

### People, sign-in and environments

Everyone signs in with their own user name and password. On the very first start you create the
first sign-in in the browser (or give it as `APP_USERNAME` / `APP_PASSWORD`); it becomes the
administrator and the owner of your existing money file, now called the "Personal" environment.

- **People** (administrators): add sign-ins, reset passwords, make someone an administrator.
- **Environments**: separate sets of accounts (Personal, Business, In-laws...). Only members see
  one. Owners add members as owner, editor (can change things) or viewer (can only look).
- **Shared accounts**: show one account in another environment too (for example your checking in
  your spouse's personal environment): one register, one balance, seen in both. View only, or
  entering transactions as well; optionally with its bills & deposits ("Share related Bills &
  Deposits"), so bills added on either side show on both. An owner of the other side approves.
- **Connections**: to move money between environments (personal checking -> business checking),
  an owner of one side asks and an owner of the other side approves and picks the account. Then
  "Transfer to ..." in either register fills in the other side. Either owner can end it.

Backups hold everything (all environments and sign-ins) in one zip. Over plain `http` on your own
network and Tailscale (which is encrypted) this is fine; don't forward the port to the internet.

## Backups to Nextcloud

In the app open **Backups**, tick *Nextcloud or another WebDAV server* and fill in:

- Folder address: `https://YOUR-CLOUD/remote.php/dav/files/YOUR-USER/Backups/Money`
- User name: your Nextcloud user
- Password: an **app password** (Nextcloud → Settings → Security → Create new app password)

Or set `WEBDAV_URL`, `WEBDAV_USER` and `WEBDAV_PASSWORD` on the container.
If Nextcloud runs on the same Unraid server, use its LAN address (e.g. `http://TOWER:8666/...`)
or its usual https address.

Defaults follow the original program: back up after changes (keep 3), a scheduled backup every
14 days (keep 3), compressed. On top of those, the last backup of each of the latest 7 days,
4 weeks and 12 months is kept. Any backup can be restored from the Backups page.

## Starting over from a backup (lost computer, new server)

1. Install MoneyThistle as usual (folder + **Start MoneyThistle**, Docker Compose or the Unraid
   script). Don't create a sign-in.
2. Open it: under *Set up MoneyThistle* choose **Start from a backup instead**, then pick a backup
   file (`money-….zip` / `.zip.enc` + its backup password) or enter your Nextcloud backup folder and
   choose one of its backups.
3. Sign in as before. Set again what belongs to the computer: notifications, other devices, start-up
   (and the Nextcloud connection if you restored from a file).

Without a browser: stop MoneyThistle, run `python main.py --restore money-….zip.enc` (it asks for
the backup password, or set `BACKUP_PASSWORD`), then start it.

## Install on a Windows computer (nothing else needed)

Double-click **MoneyThistle-Setup-….exe** and answer *Yes*. It brings its own private copy of Python
(it never touches another one), installs for you only (no administrator rights), adds MoneyThistle
to the Start menu and to *Settings → Apps → Installed apps* (with Uninstall), and opens it in the
browser to set up. To update, run a newer setup: it stops MoneyThistle (which backs up first),
replaces the program and starts it again. Your money data is never touched by installing,
updating or uninstalling (uninstall asks whether to delete it, and suggests No).

Windows may say *"Windows protected your PC"* the first time, because the setup isn't signed with
a paid code-signing certificate: choose **More info → Run anyway**.

Making the setup file (on Windows, with Python 3.10+): `python tools/build_windows.py`
→ `dist/MoneyThistle-Setup-<version>.exe`. It uses the Python running it (trimmed, about 12 MB in
all) and the free Inno Setup 6 for the branded installer; without Inno Setup it makes a plainer
one with Windows' own IExpress.

## Releasing (GitHub)

0. Once: create the repository on GitHub *empty*: no README, license or .gitignore (this folder
   already has them; `LICENSE` is the GNU AGPL-3.0, which GitHub recognises once it's pushed).
1. Raise `VERSION` in `moneyapp/version.py` and add a `## <version>` section to `CHANGELOG.md`.
2. Push a tag `v<version>` (e.g. `v1.0.1`). The *release* workflow tests, builds the Windows setup,
   has it signed (once SignPath Foundation's free open-source signing is set up: see the comments
   in `.github/workflows/release.yml`) and publishes a GitHub release with the setup and its SHA-256.

The *tests* workflow runs the tests on Windows and Linux for every change.

## Other ways to run it

Docker Compose (any machine): `docker compose up -d --build`, then `http://SERVER:8080`.
Run the same command after changes to rebuild and restart (on Windows: double-click
**Update Docker container**).
Edit `APP_PASSWORD` in `docker-compose.yml` first.

Without Docker on Windows: double-click **Start MoneyThistle** in this folder. It runs in the
background (no window to keep open), opens http://localhost:8080, and keeps running until you
double-click **Stop MoneyThistle** or restart the computer. If it ever stops on its own,
`moneythistle.log` in the data folder says why (older copies wrote `home-ledger.log`; its lines
move into the new file on the next start).

Where your files go (Settings shows the exact folders):

| Install | App files | Money data, log and local backups |
|---|---|---|
| Windows | wherever you put the MoneyThistle folder | `%APPDATA%\MoneyThistle` (e.g. `C:\Users\you\AppData\Roaming\MoneyThistle`) |
| macOS | wherever you put the folder | `~/Library/Application Support/MoneyThistle` |
| Linux | wherever you put the folder | `~/.local/share/moneythistle` |
| Docker Compose | this folder | `./data` and `./backups` beside `docker-compose.yml` |
| Unraid | `/mnt/user/appdata/moneythistle/src` | `/mnt/user/appdata/moneythistle/data` and `.../backups` |

Keeping the data outside the program folder means replacing or deleting the program never
touches your money files. A copy that already has a `data` folder beside the program (from
before this change) keeps using it. `--data FOLDER` (or `DATA_DIR`) picks any other folder.

Without Docker (Python 3.10+, nothing else to install):

```
python main.py --background   # keeps running after the window closes
python main.py --stop         # stops it (backs up first)
python main.py            # runs while this window stays open; opens http://localhost:8080
python main.py --demo     # start with sample data
python -m unittest discover -s tests
```
