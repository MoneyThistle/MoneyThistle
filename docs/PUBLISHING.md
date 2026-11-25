# Publishing MoneyThistle: how it reaches people

A plain-language guide for whoever publishes MoneyThistle: what the pieces are, how they fit
together, what to set up once, and the steps for each new version.

## The pieces

**The repository** (github.com/MoneyThistle/MoneyThistle) holds the source code: every file and
the history of every change ("commits"). Pushing sends new commits from a computer to it.

**Versions** are numbers like `1.4.2`, written MAJOR.MINOR.PATCH:

- **PATCH** (1.4.**2**): fixes only.
- **MINOR** (1.**4**.0): new features; nothing to do when updating.
- **MAJOR** (**2**.0.0): someone may have to do something when updating (rare: avoid it).

The number lives in `moneyapp/version.py` (`VERSION`), and `CHANGELOG.md` says what changed in each
one, in plain words.

**A tag** is a name stuck on one commit, such as `v1.4.2`. Pushing a tag is what says "this commit
is version 1.4.2: publish it".

**GitHub Actions** are robots that run on GitHub's computers. MoneyThistle has two:

- **tests** runs on every push: all the tests on Windows and Linux, with Python 3.10 and 3.12, and
  builds the container image to check that it starts. A failure sends you an email. Fix it with
  another push; the next green run is what counts.
- **release** runs when a version tag is pushed. It builds the Windows setup and the container
  image and publishes both.

**A release** is the download page for one version (github.com/MoneyThistle/MoneyThistle/releases).
It holds the notes (this version's section of `CHANGELOG.md`), the Windows setup
`MoneyThistle-Setup-1.4.2.exe`, and its checksum file `….exe.sha256`. A checksum is a fingerprint:
if one byte of the download differs, the fingerprint differs, so the app's updater refuses to
install it.

**Code signing** puts the publisher's verified name on the Windows setup. Without it, Windows
shows "Windows protected your PC" (people then choose More info → Run anyway). SignPath Foundation
signs open-source projects for free. Once they approve the project, the release robot sends each
setup to them for signing; the steps are in the comments at the top of
`.github/workflows/release.yml`.

**The container image** is MoneyThistle packed with everything it needs to run on Docker: Python,
the app, the settings. The release robot builds it for both kinds of server processor (Intel/AMD
and ARM) and publishes it to the **GitHub Container Registry** (ghcr.io), GitHub's shelf for
images, as `ghcr.io/moneythistle/moneythistle`. Each release puts several **image tags** on it:

| Tag | Means | Who uses it |
|---|---|---|
| `latest` | always the newest release | most people: they get every update |
| `1` | the newest 1.x.x | people who want features but no breaking changes |
| `1.4` | the newest 1.4.x | people who want fixes only |
| `1.4.2` | exactly that version, forever | people who pin a version |

**An Unraid template** (`unraid/moneythistle.xml`) is the form Unraid shows when adding a
container: the image to use, the port, the folders, the settings, with sensible defaults. Filling
it in and clicking Apply downloads the image and starts it: nothing is copied by hand.
**Community Applications** (the *Apps* tab in Unraid) is the app store that lists templates; once
MoneyThistle is listed there, people search for it and click Install.

## How each kind of install gets updates

MoneyThistle asks GitHub once a day for the newest release's number (`moneyapp/updates.py`). It
sends only its own version number. Then:

- **Windows** (installed by the setup): administrators see "MoneyThistle 1.4.2 is available" on
  Home and in Settings → This computer, with **Update now**. That downloads the setup, checks its
  checksum, and runs it quietly. The setup stops MoneyThistle (which backs up first), replaces the
  program and starts it again, and the open page reloads. With *Install new versions by itself*
  ticked, it does this without the click.
- **Unraid**: Unraid itself checks the image. With `:latest`, the Docker tab shows *update ready*
  after a release; one click updates it. Auto-update plugins (from Community Applications) can do
  it unattended. Changing the template's Repository to `…:1.4.2` pins that version. MoneyThistle
  also says a new version is out, and how to update.
- **Docker Compose**: `docker compose pull && docker compose up -d`. Tools like Watchtower can do it
  automatically.
- **macOS and Linux from the source**: the person replaces the files; the app says a new version is
  out and links to it.

Updating a container never touches the data: it lives in the mapped folders (`/data`,
`/backups`), outside the image.

## Once only

1. **After the first release**, open the organization's **Packages** on GitHub, then
   **moneythistle** → **Package settings**, and make it **Public** if it isn't. Until it's public,
   nobody outside the organization can download the image: Unraid then ends with *No such
   container: MoneyThistle* (the download was *denied*), and Docker says *denied* or *unauthorized*.

The Unraid template asks only for what the container needs (the port, the two folders, the time
zone). Everything else is set up in the app, so keep it that way when changing the template.
2. **Code signing**: apply at https://signpath.org/apply. Once approved, add the repository secret
   `SIGNPATH_API_TOKEN` and the variables `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG` and
   `SIGNPATH_POLICY_SLUG` (Settings → Secrets and variables → Actions).
3. **Community Applications**: CA lists templates from public repositories. This repository already
   holds the template (`unraid/moneythistle.xml`). Getting listed usually means a support thread for
   MoneyThistle on the Unraid forums (the template's *Support* link can then point there) and
   submitting the repository through Community Applications' own submission process, described on
   the Unraid forums. Until then, people add the template with the one-line command in `README.md`.

## Publishing a new version

1. Make sure the latest push is green (the **tests** robot).
2. In `CHANGELOG.md`, give the new version its section, `## 1.4.2 (2026-12-15)`, saying in plain
   words what changed.
3. Set `VERSION = "1.4.2"` in `moneyapp/version.py`.
4. Commit and push those two changes.
5. Tag and push the tag:

   ```
   git tag v1.4.2
   git push origin v1.4.2
   ```

6. Watch **Actions → release** on GitHub (about 10 minutes). When both jobs are green:
   - the release page has the setup and its `.sha256` file;
   - the package shows the tags `1.4.2`, `1.4`, `1` and `latest`.
7. Within a day, every install that checks for updates sees it.

The first release (v1.0.0) is also the first run of the release robot, so watch it closely. If a
job fails, read its log on GitHub, fix the cause, and run it again: delete the release and the tag
it made (`git push --delete origin v1.0.0`, `git tag -d v1.0.0`), then tag again.

## If a release is bad

Don't delete a published version people may already have. Fix the problem and publish the next
PATCH version (1.4.3): everyone on `latest` and on Windows updates to it. Someone who needs to step
back right away can pin the previous version in Unraid (`…:1.4.1`) or run the previous setup from
its release page. Their data is untouched either way.
