# Security

MoneyThistle keeps a household's money records. This page says what it protects against, what it
doesn't, and how to report a problem.

## Reporting a problem

Please report security problems **privately**, not in a public issue: on GitHub, open the
repository's **Security** tab and choose **Report a vulnerability**. Say what you found, how to
see it happen, and which version. You'll get an answer, and a fixed release as soon as one is
ready. Credit is given in the changelog if you'd like it.

## Which versions get fixes

The newest release. Fixes come as a new release; every install can update to it (see "Updates" in
the README). Older versions don't get separate fixes.

## How MoneyThistle is meant to be used

On one computer, or a home server reached over the **home network (LAN) or a private VPN such
as Tailscale**, by the people in a household. **It must never be exposed to the public internet**
(no port forwarding, no public reverse proxy). It hasn't had a professional security review: it
was written largely by an AI from plain-language requests and tested by its maintainer, with an
automated test suite. Reviews and fixes are welcome.

## What it protects against

**People in the household seeing or changing what isn't theirs.**
- Everyone signs in with their own name and password. Passwords are stored only as salted
  PBKDF2-SHA256 hashes (200,000 rounds). Sign-in cookies are random, kept only as hashes on the
  server, HttpOnly and SameSite=Lax; a sign-in not kept on the device ends after an hour unused.
- Each environment is a separate money file. Every request is checked against the person's role
  there (owner, editor, viewer); a viewer can look but not change. An account shared into
  another environment shows only that account, and only what the share allows.
- An automated test (`test_every_route_keeps_environments_apart`) tries **every route** of the
  server as someone not signed in, someone signed in but not a member, someone holding one shared
  account, and a viewer. It checks each gets refused, that no answer ever contains a private
  account's details, and that nothing of it changes. It runs with every change.
- Administrators manage sign-ins and backups; changes are recorded in the change history, and
  most can be undone.

**Guessing passwords.** Each wrong password waits half a second, and after 10 wrong tries from
one address in 10 minutes, that address must wait. The count is kept in the people file, so
restarting doesn't reset it. "Forgot your password?" emails are limited to a few per address
every 15 minutes, and their links work once, for 30 minutes.

**Other websites acting through your browser** (cross-site request forgery). Every change must
carry a header that other websites' pages can't send, and the browser's own report of where the
request came from (Sec-Fetch-Site, or Origin) must be this server.

**Code slipped into a page** (cross-site scripting). What people type is escaped before it's
shown. As a backstop, the page carries a Content-Security-Policy that lets the browser run only
MoneyThistle's own script files, load only its own files, talk only to its own server, and refuse
being shown inside another site. Uploaded receipts must really be pictures or PDFs (checked by
their contents).

**Backups that leave the computer.** Backups can be encrypted with a backup password
(scrypt to make the key, ChaCha20 with HMAC-SHA256 to encrypt and check, standard library only).
The app's own updater checks each new Windows setup against the checksum published with it.

## What it doesn't protect against

- **Someone who can use the computer or server it runs on** (or its account), or read its data
  folder. The money files are ordinary SQLite files, not encrypted on disk; use the operating
  system's disk encryption and accounts. The backup password is kept on that computer so backups
  can run on their own.
- **Being on the internet.** See above: keep it on your home network or a private VPN.
- **Plain http on the home network.** Traffic between a browser and MoneyThistle isn't encrypted
  unless it goes through Tailscale (encrypted) or your own https proxy. Anyone able to listen on
  your home network could read it.
- **Two-step sign-in (2FA).** Not yet; it may come for administrators later.
- **A stolen or lost device with "Keep me signed in" ticked.** Sign it out from the app, or have
  an administrator reset that person's password (which signs them out everywhere).

## What it sends out

Nothing about you or your money. It asks GitHub once a day for the newest version number (it sends
only its own version; this can be turned off in Settings). Email notifications and Nextcloud
backups go only where an administrator sets them up. The coffee cup is a plain link; nothing is
sent to that site unless someone clicks it.
