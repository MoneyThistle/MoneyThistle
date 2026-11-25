"""MoneyThistle: a simple personal money manager you open in a web browser.

Run:  python main.py                (then open http://localhost:8080)
      python main.py --demo         (fill a new file with sample data)
      python main.py --screenshot shot.png
"""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from moneyapp.backup import BackupManager  # noqa: E402
from moneyapp.demo import load_sample  # noqa: E402
from moneyapp.server import App, companion_host, make_server  # noqa: E402
from moneyapp.system import System  # noqa: E402
from moneyapp.updates import Updater  # noqa: E402
from moneyapp.version import build_id  # noqa: E402


def build(data_dir):
    """The people/environments registry, backups and the web app. The returned
    `store` is the first environment's money file (Personal)."""
    os.makedirs(data_dir, exist_ok=True)
    system = System(data_dir)
    if not system.has_users() and os.environ.get("APP_PASSWORD"):
        # Docker setups may name the first administrator in the environment.
        try:
            system.create_user(os.environ.get("APP_USERNAME", "admin"), os.environ["APP_PASSWORD"], "", True)
        except Exception as e:
            print(f"Couldn't create the first administrator from APP_USERNAME/APP_PASSWORD ({e}); "
                  "create it in the browser instead.", file=sys.stderr)
    backups = BackupManager(system, os.path.join(data_dir, "backups"), os.path.join(data_dir, "settings.json"))
    first = system.q1("SELECT id FROM environments ORDER BY id LIMIT 1")["id"]
    app = App(system, backups)
    app.updates = Updater(data_dir)
    return system, system.store(first), backups, app


def find_browser():
    cands = [os.environ.get("BROWSER", "")]
    for name in ("msedge", "chrome", "chromium", "chromium-browser", "google-chrome", "microsoft-edge"):
        cands.append(shutil.which(name) or "")
    pf = [os.environ.get(k, "") for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for base in pf:
        if base:
            cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    cands += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def screenshot(out_path, page="home", theme=None, accent=None, width=1280, height=860):
    """Start the app with sample data, let a hidden browser draw the home page,
    save the picture and exit. Nothing takes focus: the browser runs headless."""
    browser = find_browser()
    if not browser:
        print("No Chrome or Edge found for --screenshot (set BROWSER to one).", file=sys.stderr)
        return 2
    tmp = tempfile.mkdtemp(prefix="moneythistle-shot-")
    try:
        system, store, backups, app = build(os.path.join(tmp, "data"))
        load_sample(store)
        store.set_setting("sample_data", False)   # (pictures of the app, without the sample-data bar)
        uid = system.users()[0]["id"] if system.has_users() else \
            system.create_user("demo", "demo-password", "Sam Sample", True)
        app.auto_user_id = uid  # the picture is taken as this (sample) person
        ui = dict(system.ui_settings(uid), tour_done=True)   # the picture shows the page, not the tour
        if theme or accent:
            ui.update(theme=theme or "light", accent=accent or "#1c4b8a")
        system.save_ui_settings(uid, ui)
        system.dirty_since = None
        httpd = make_server(app, "127.0.0.1", 0)
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        out_path = os.path.abspath(out_path)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        if os.path.exists(out_path):
            os.remove(out_path)
        cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check", "--disable-extensions", "--mute-audio",
               f"--user-data-dir={os.path.join(tmp, 'profile')}", f"--window-size={width},{height}",
               "--virtual-time-budget=8000", f"--screenshot={out_path}",
               f"http://127.0.0.1:{port}/#/{page}"]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            cmd.insert(1, "--no-sandbox")
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        except subprocess.TimeoutExpired:
            pass
        httpd.shutdown()
        system.close()
        if not os.path.isfile(out_path):
            print("The browser did not save a picture.", file=sys.stderr)
            return 1
        print(f"Saved {out_path}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def lan_addresses():
    """This computer's network addresses (best effort, no traffic is sent). The one it
    reaches the network through comes first; a computer still connecting to Wi-Fi has
    only virtual adapters (WSL, Hyper-V), so the list is looked up again later."""
    import socket
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


# How a running copy names itself; copies from before the rename said "HomeLedger".
SERVER_NAMES = ("MoneyThistle", "HomeLedger")


def already_running(url):
    try:
        with urllib.request.urlopen(url + "healthz", timeout=1.5) as r:
            return r.status == 200 and r.headers.get("Server", "").startswith(SERVER_NAMES)
    except Exception:
        return False


BUILD = build_id()


def user_data_dir():
    """The usual place for an app's own files in this person's account:
    Windows %APPDATA%\\MoneyThistle, macOS ~/Library/Application Support/MoneyThistle,
    Linux ~/.local/share/moneythistle (or $XDG_DATA_HOME)."""
    home = os.path.expanduser("~")
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "MoneyThistle")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "MoneyThistle")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share"), "moneythistle")


def default_data_dir():
    """Where the money files live when --data isn't given. DATA_DIR wins (Docker sets
    /data). A copy that already keeps its files in a data folder beside the program (as
    every copy did before) goes on using it; a fresh install uses the person's own
    app-data folder, so replacing or deleting the program folder never touches them."""
    if os.environ.get("DATA_DIR"):
        return os.environ["DATA_DIR"]
    here = os.path.dirname(os.path.abspath(__file__))
    for folder in (os.path.join(os.getcwd(), "data"), os.path.join(here, "data")):
        if any(os.path.exists(os.path.join(folder, f)) for f in ("system.db", "money.db")):
            return folder
    return user_data_dir()


def network_settings(data_dir):
    """The Settings choice of where MoneyThistle listens (data/network.json)."""
    try:
        with open(os.path.join(data_dir, "network.json"), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


def restart_self():
    """Start a fresh copy of this program with the same settings (it loads the
    files as they are now, so updates take effect), detached like --background
    when there's no console, then let this one finish."""
    argv = [a for a in sys.argv[1:] if a not in ("--background", "--demo")]
    # Older copies passed "--host 127.0.0.1" along; drop it so the Settings choice of
    # where to listen takes effect on restart.
    for i in range(len(argv) - 1):
        if argv[i] == "--host" and argv[i + 1] == "127.0.0.1":
            del argv[i:i + 2]
            break
    if "--no-browser" not in argv:
        argv.append("--no-browser")
    cmd = [sys.executable, os.path.abspath(__file__)] + argv
    kw = {"cwd": os.path.dirname(os.path.abspath(__file__)), "close_fds": True}
    headless = sys.stdout is None or os.path.basename(sys.executable).lower().startswith("pythonw")
    if headless:
        kw.update(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name == "nt":
        flags = 0x00000200  # CREATE_NEW_PROCESS_GROUP
        if headless:
            flags |= 0x00000008  # DETACHED_PROCESS
        try:
            subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kw)  # try to leave any job
        except OSError:
            subprocess.Popen(cmd, creationflags=flags, **kw)
    else:
        subprocess.Popen(cmd, start_new_session=headless, **kw)


def probe(url):
    """None when no MoneyThistle answers there; else its version ('' for old versions)."""
    try:
        with urllib.request.urlopen(url + "healthz", timeout=1.5) as r:
            if r.status != 200 or not r.headers.get("Server", "").startswith(SERVER_NAMES):
                return None
            return r.headers.get("X-HomeLedger-Build", "")
    except Exception:
        return None


def write_control_token(data_dir):
    """A secret the next start uses to ask this copy to stop (custom header, so
    web pages can't send it)."""
    import secrets
    token = secrets.token_hex(16)
    path = os.path.join(data_dir, ".control-token")
    try:
        with open(path, "w") as f:
            f.write(token)
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


def _listening_pid(port):
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[3].upper() == "LISTENING" and parts[1].rsplit(":", 1)[-1] == str(port):
                    return int(parts[4])
        else:
            out = subprocess.run(["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"], capture_output=True,
                                 text=True, timeout=10).stdout.split()
            return int(out[0]) if out else None
    except Exception:
        return None
    return None


def stop_old_copy(url, port, data_dir):
    """Ask the older copy to stop (it backs up first); force it only if it has no
    way to be asked (versions before this one)."""
    def wait_gone(seconds):
        end = time.time() + seconds
        while time.time() < end:
            if probe(url) is None:
                return True
            time.sleep(0.3)
        return False
    try:
        with open(os.path.join(data_dir, ".control-token")) as f:
            token = f.read().strip()
        req = urllib.request.Request(url + "api/admin/stop", method="POST", data=b"{}",
                                     headers={"X-HomeLedger-Control": token})
        urllib.request.urlopen(req, timeout=5).read()
        if wait_gone(60):
            return True
    except Exception:
        pass
    pid = _listening_pid(port)
    if pid and pid != os.getpid():
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        return wait_gone(10)
    return False


def drop_privileges(paths):
    """In a container started as root (Unraid style), hand the data folders to
    PUID:PGID (Unraid's nobody:users = 99:100 by default) and run as that user."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    uid = int(os.environ.get("PUID", "99"))
    gid = int(os.environ.get("PGID", "100"))
    try:
        os.umask(int(os.environ.get("UMASK", "002"), 8))
    except ValueError:
        pass
    if uid == 0:
        return
    for p in paths:
        if not p:
            continue
        os.makedirs(p, exist_ok=True)
        for root, dirs, files in os.walk(p):
            for name in [root] + [os.path.join(root, n) for n in dirs + files]:
                try:
                    os.chown(name, uid, gid)
                except OSError:
                    pass
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    os.environ["HOME"] = "/tmp"


LOG_PATH = None


def say(msg, err=False):
    """Print (when there is a console) and append to data/moneythistle.log."""
    stream = sys.stderr if err else sys.stdout
    if stream is not None:
        try:
            print(msg, file=stream, flush=True)
        except (OSError, ValueError):
            pass  # console went away; the log still has it
    if LOG_PATH:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{os.getpid()}] {msg}\n")
        except OSError:
            pass


def recover(args):
    """The way back in that needs no email: on the computer or server itself (being able
    to run this there is the proof it's yours), list the sign-ins or set a new password.
    Works while MoneyThistle is running; that person is signed out everywhere."""
    import getpass
    from moneyapp.store import ApiError
    if not os.path.isfile(os.path.join(args.data, "system.db")):
        print(f"No MoneyThistle data in {args.data}. Give the right folder with --data.", file=sys.stderr)
        return 2
    system = System(args.data)
    try:
        users = system.users()
        if args.list_users:
            print(f"Sign-ins in {args.data}:")
            for u in users:
                print(f"  {u['username']:<24} {u['display_name']}{'  (administrator)' if u['is_admin'] else ''}"
                      f"{'  email: ' + u['email'] if u.get('email') else ''}")
            return 0
        u = next((x for x in users if x["username"].lower() == args.reset_password.strip().lower()), None)
        if not u:
            print(f"There's no sign-in called \"{args.reset_password}\". These exist: "
                  + ", ".join(x["username"] for x in users), file=sys.stderr)
            return 1
        pw = os.environ.get("MONEYTHISTLE_NEW_PASSWORD")
        if not pw:
            if not sys.stdin or not sys.stdin.isatty():
                print("Run this in a terminal (with docker exec, add -it) so it can ask for the new password.",
                      file=sys.stderr)
                return 2
            pw = getpass.getpass(f"New password for {u['username']} (8+ characters, not shown): ")
            if pw != getpass.getpass("Type it again: "):
                print("The two didn't match; nothing was changed.", file=sys.stderr)
                return 1
        try:
            system.set_password(u["id"], pw)
        except ApiError as e:
            print(f"{e}; nothing was changed.", file=sys.stderr)
            return 1
        print(f"New password set for {u['username']}. They're signed out everywhere; sign in with the new one.")
        return 0
    finally:
        system.close()


def carry_old_log(data_dir):
    """Before the rename the log was home-ledger.log: move its lines into
    moneythistle.log (in front of anything already there) and remove it. Runs at start
    and again once an older copy has stopped, since that copy still writes the old name."""
    old = os.path.join(data_dir, "home-ledger.log")
    if not LOG_PATH or not os.path.isfile(old):
        return
    try:
        if not os.path.exists(LOG_PATH):
            os.replace(old, LOG_PATH)
            return
        with open(old, "rb") as f:
            head = f.read()
        with open(LOG_PATH, "rb") as f:
            tail = f.read()
        tmp = LOG_PATH + ".tmp"
        with open(tmp, "wb") as f:
            f.write(head + (b"" if not head or head.endswith(b"\n") else b"\n") + tail)
        os.replace(tmp, LOG_PATH)
        os.remove(old)
    except OSError:
        pass


def restore_file(args):
    """python main.py --restore FILE: put a backup back (a new computer, a rebuilt server).
    Refused while MoneyThistle runs on this data folder's port, so nothing is overwritten
    under it."""
    from moneyapp import crypt
    from moneyapp.store import ApiError
    port_url = f"http://127.0.0.1:{args.port}/"
    if probe(port_url) is not None:
        print(f"MoneyThistle is running (port {args.port}). Stop it first (python main.py --stop), "
              "or restore in the browser: Backups, Restore from a file.", file=sys.stderr)
        return 1
    try:
        with open(args.restore, "rb") as f:
            blob = f.read()
    except OSError as e:
        print(f"Can't read {args.restore}: {e}", file=sys.stderr)
        return 1
    password = os.environ.get("BACKUP_PASSWORD") or None
    if crypt.is_encrypted(blob) and not password:
        import getpass
        password = getpass.getpass("Backup password: ")
    system, _store, backups, _app = build(args.data)
    try:
        r = backups.restore_blob(blob, password, "file", os.path.basename(args.restore))
    except ApiError as e:
        print(f"Not restored: {e}", file=sys.stderr)
        return 1
    finally:
        system.close()
    print(f"Restored {os.path.basename(args.restore)} into {os.path.abspath(args.data)}.")
    print(f"Sign-ins in it: {', '.join(r['people']) or '(none)'}. Start MoneyThistle and sign in as before.")
    print("Then check Backups: set up Nextcloud/WebDAV again (its password isn't in backups).")
    return 0


def ensure_menu(data_dir, launch_args):
    """MoneyThistle in the Start menu (or applications menu), made at start when it's
    missing or points at a folder the app no longer lives in. Never in the way of starting."""
    from moneyapp import autostart
    if autostart.platform() == "mac" or autostart.service_account() or os.environ.get("NO_SHORTCUTS") \
            or autostart.installed_by_setup():   # (the setup made them)
        return
    try:
        a = autostart.Autostart(data_dir, launch_args)
        if not a.menu_current():
            a.ensure_menu()
            say("Added MoneyThistle to the Start menu." if os.name == "nt" else "Added MoneyThistle to the applications menu.")
    except Exception as e:
        say(f"Couldn't add MoneyThistle to the menu ({e}); start it with 'Start MoneyThistle' instead.")


def start_in_background(args, url, probe_url):
    """Start a copy that keeps running on its own (no console, not tied to the
    window or program that started it), wait until it answers, open the browser."""
    py = sys.executable
    if os.name == "nt":
        w = os.path.join(os.path.dirname(py), "pythonw.exe")
        if os.path.isfile(w):
            py = w
    # The address is passed on only when it was asked for; otherwise the copy reads the
    # Settings choice itself (so a restart picks up a changed choice).
    cmd = [py, os.path.abspath(__file__), "--no-browser"] + (["--host", args.host] if args.host_given else []) + \
        ["--port", str(args.port), "--data", os.path.abspath(args.data)]
    if args.demo:
        cmd.append("--demo")
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
          "cwd": os.path.dirname(os.path.abspath(__file__)), "close_fds": True}
    if os.name == "nt":
        base = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(cmd, creationflags=base | 0x01000000, **kw)  # + CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            subprocess.Popen(cmd, creationflags=base, **kw)
    else:
        subprocess.Popen(cmd, start_new_session=True, **kw)
    end = time.time() + 30
    while time.time() < end:
        if probe(probe_url) == BUILD:
            say(f"MoneyThistle is running in the background: {url}")
            say("Stop it with: python main.py --stop   (or the 'Stop MoneyThistle' shortcut)")
            if not args.no_browser and not os.environ.get("NO_BROWSER"):
                webbrowser.open(url)
            return 0
        time.sleep(0.4)
    say(f"MoneyThistle did not start; see {LOG_PATH}", err=True)
    return 1


def main():
    global LOG_PATH
    ap = argparse.ArgumentParser(description="MoneyThistle money manager")
    # Where it listens: --host or HOST if given; otherwise the Settings choice "let
    # other devices on my network open it" (0.0.0.0), else this computer only.
    ap.add_argument("--host", default=os.environ.get("HOST") or None)
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    ap.add_argument("--data", default=default_data_dir())
    ap.add_argument("--demo", action="store_true", help="fill an empty money file with sample data")
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser tab on start")
    ap.add_argument("--background", action="store_true",
                    help="keep running on its own after this command (and the window) closes")
    ap.add_argument("--stop", action="store_true", help="stop a running copy (it backs up first)")
    ap.add_argument("--reset-password", metavar="USER",
                    help="locked out? set a new password for this sign-in (run it on the computer or server "
                         "MoneyThistle runs on; in Docker: docker exec -it moneythistle python main.py "
                         "--reset-password USER)")
    ap.add_argument("--list-users", action="store_true", help="list the sign-ins (user names) and exit")
    ap.add_argument("--restore", metavar="BACKUP_FILE",
                    help="put back everything from a backup file (money-....zip or .zip.enc), then exit; "
                         "stop MoneyThistle first. Asks for the backup password if it's encrypted "
                         "(or set BACKUP_PASSWORD)")
    ap.add_argument("--screenshot", metavar="FILE.png", help="save a picture of the home page and exit")
    ap.add_argument("--page", default="home", help="page for --screenshot (home, accounts, bills, budget, reports, settings)")
    ap.add_argument("--theme", choices=["light", "dark"], help="theme for --screenshot")
    ap.add_argument("--accent", help="accent color for --screenshot, like #1f8a8a")
    ap.add_argument("--width", type=int, default=1280, help="window width for --screenshot")
    ap.add_argument("--height", type=int, default=860, help="window height for --screenshot")
    args = ap.parse_args()

    if args.screenshot:
        return screenshot(args.screenshot, args.page, args.theme, args.accent, args.width, args.height)
    if args.reset_password or args.list_users:
        return recover(args)
    if args.restore:
        return restore_file(args)

    try:
        os.makedirs(args.data, exist_ok=True)
        LOG_PATH = os.path.join(args.data, "moneythistle.log")
        carry_old_log(args.data)
    except OSError:
        LOG_PATH = None
    args.host_given = args.host is not None
    if not args.host_given:
        args.host = "0.0.0.0" if network_settings(args.data).get("listen_lan") else "127.0.0.1"

    shown = "localhost" if args.host in ("0.0.0.0", "::", "127.0.0.1") else args.host
    url = f"http://{shown}:{args.port}/"
    # Checks use the plain IPv4 address: an older copy may only listen there.
    probe_url = f"http://127.0.0.1:{args.port}/" if shown == "localhost" else url
    open_tab = not args.no_browser and not os.environ.get("NO_BROWSER") and not os.path.exists("/.dockerenv")

    if args.stop:
        if probe(probe_url) is None:
            say("MoneyThistle isn't running.")
            return 0
        ok = stop_old_copy(probe_url, args.port, args.data)
        carry_old_log(args.data)
        say("MoneyThistle stopped." if ok else "Could not stop MoneyThistle.", err=not ok)
        return 0 if ok else 1

    # Already running (for example started earlier)? If it's this same version, just
    # show it in the browser. If it's an older version, replace it: an old server
    # with new screens answers "Not found" to everything the screens ask for.
    running = probe(probe_url)
    if running is not None:
        if running == BUILD:
            say(f"MoneyThistle is already running: {url}")
            if open_tab:
                webbrowser.open(url)
            return 0
        say("An older copy of MoneyThistle is running on this port; replacing it with this version...")
        if not stop_old_copy(probe_url, args.port, args.data):
            say(f"Could not stop the older copy on port {args.port}. Close it, or start with --port 8081.", err=True)
            return 1
        carry_old_log(args.data)

    if args.background:
        return start_in_background(args, url, probe_url)

    drop_privileges([args.data, os.environ.get("BACKUP_DIR", "")])
    system, store, backups, app = build(args.data)
    app.build_id = BUILD
    app.started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    app.control_token = write_control_token(args.data)
    if system.has_users():
        say("Everyone signs in with their own user name and password.")
    else:
        say("First start: open the address below and create the first (administrator) sign-in. "
            "Do that before anyone else can reach it.")
    if args.demo and load_sample(store):
        say("Loaded sample data.")
    try:
        httpd = make_server(app, args.host, args.port)
    except OSError as e:
        system.close()
        say(f"Port {args.port} is taken by another program ({e}). Try --port 8081.", err=True)
        return 1
    # Also listen on the IPv6 form of the same address, so http://localhost works
    # in every browser (some try ::1 first). Best effort: IPv4 alone still works.
    extra = None
    other = companion_host(args.host)
    if other:
        try:
            extra = make_server(app, other, args.port)
            threading.Thread(target=extra.serve_forever, daemon=True).start()
        except OSError:
            extra = None
    backups.start()
    app.updates.start()   # once a day: is there a newer version? (see updates.py)

    reason = {"why": "the server loop ended", "restart": False}
    in_docker = os.path.exists("/.dockerenv")

    def stop(why, restart=False):
        reason["why"] = why
        reason["restart"] = restart
        threading.Thread(target=httpd.shutdown, daemon=True).start()
        if extra:
            threading.Thread(target=extra.shutdown, daemon=True).start()
    app.request_stop = lambda why="a stop request (python main.py --stop, or a newer copy starting)": stop(why)
    # How shortcuts and start-ups start this same copy again: its data folder, and the
    # port and address when they were given.
    app.launch_args = ["--data", os.path.abspath(args.data)] + \
        (["--port", str(args.port)] if args.port != 8080 else []) + (["--host", args.host] if args.host_given else [])
    if not os.path.exists("/.dockerenv"):
        threading.Thread(target=ensure_menu, args=(args.data, app.launch_args), daemon=True).start()
    app.request_restart = lambda: stop("the Restart button", restart=True)
    app.listen_host = args.host
    app.host_fixed = args.host_given   # set by --host / HOST: the Settings choice doesn't apply
    app.in_docker = in_docker
    signal.signal(signal.SIGTERM, lambda *_: stop("the system or Docker asked it to stop (SIGTERM)"))
    signal.signal(signal.SIGINT, lambda *_: stop("Ctrl+C or its window closing (SIGINT)"))
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *_: stop("its window closing (SIGBREAK)"))
    in_docker = os.path.exists("/.dockerenv")
    # Addresses to show: worked out at every start (never handed on to a restarted
    # copy). APP_URLS, when set by the person (Docker), is shown as given; a list of
    # only this-computer addresses is what older copies left behind, so it's ignored.
    given = [x.strip() for x in os.environ.get("APP_URLS", "").split(",") if x.strip()]
    if given and all(re.match(r"^https?://(localhost|127\.|\[::1\])", u, re.I) for u in given):
        given = []
    def find():
        found = [url]
        if not in_docker and args.host in ("0.0.0.0", "::"):
            found += [f"http://{ip}:{args.port}/" for ip in lan_addresses()]
        return found
    app.urls = given or ([] if in_docker else find())
    if not given and not in_docker:
        app.find_urls = find   # looked up again later: the network may connect after it starts
    say(f"MoneyThistle {BUILD} is running on port {args.port}.")
    for u in app.urls or [url]:
        say(f"  Open: {u}")
    if in_docker and not given:
        say(f"  (inside Docker: open http://YOUR-SERVER:{os.environ.get('PUBLIC_PORT', args.port)}/ "
            "using the port you published)")
    if open_tab:
        # The app has no window of its own: it lives in a browser tab.
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except BaseException as e:  # log anything that brings it down
        reason["why"] = f"an error: {e!r}"
        raise
    finally:
        backups.stop.set()
        say(f"Stopping because of {reason['why']}; running the after-changes backup if needed...")
        backups.on_shutdown()
        system.close()
        httpd.server_close()
        if extra:
            extra.server_close()
        say("Stopped.")
    if reason["restart"]:
        if in_docker:
            # The container's restart policy starts it again (with the app files as
            # they are now when /app is mounted from the server).
            say("Restarting: the container will start it again.")
            return 0
        say("Restarting with the current files...")
        restart_self()
    return 0


if __name__ == "__main__":
    sys.exit(main())
