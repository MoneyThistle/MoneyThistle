"""Starting MoneyThistle without a terminal, for copies running on a computer (not Docker).

Three choices, each made in Settings by an administrator:

- shortcuts: "MoneyThistle" in the Start menu (always, made at start), which starts it
  if it isn't running and opens it in the browser, plus "Stop MoneyThistle"; a desktop
  icon when chosen while setting up, or in Settings;
- at sign-in: it starts when the person signs in to the computer (no admin rights
  needed: the Startup folder, a macOS login item, a Linux desktop autostart entry);
- always: it starts with the computer, before anyone signs in, so phones and other
  computers can reach it whenever the computer is on. That needs the computer's
  administrator once: on Windows a scheduled task (Windows asks for permission), on
  macOS and Linux a command to paste.

Closing the browser tab never stops MoneyThistle: it's a small server, and other
devices may be using it. The Shut down button (or "Stop MoneyThistle") stops it.
"""

import getpass
import json
import os
import re
import struct
import subprocess
import sys

from .store import ApiError

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the app folder
MAIN = os.path.join(HERE, "main.py")
STATIC = os.path.join(HERE, "moneyapp", "static")
TASK = "MoneyThistle"
NO_WINDOW = 0x08000000   # CREATE_NO_WINDOW


def platform():
    if os.name == "nt":
        return "windows"
    return "mac" if sys.platform == "darwin" else "linux"


def pythonw():
    """The Python that runs without a console window (Windows), else this one."""
    exe = sys.executable
    if os.name == "nt":
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(w):
            return w
    return exe


def service_account():
    """Running as Windows' own account (started with the computer): per-person
    shortcuts would land in that account's folders, not the person's."""
    try:
        user = getpass.getuser()
    except Exception:
        return False
    return os.name == "nt" and (user.upper() == "SYSTEM" or user.endswith("$"))


def _ps(script, env=None):
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                       text=True, timeout=60, env=e, creationflags=NO_WINDOW if os.name == "nt" else 0)
    if r.returncode != 0:
        raise ApiError("Windows refused: " + (r.stderr.strip().splitlines() or ["unknown error"])[-1][:300])
    return r.stdout


_folders = {}


def win_folders():
    """Startup, Start menu programs and desktop folders of this person (the desktop may
    have moved into OneDrive)."""
    if not _folders:
        out = _ps("[pscustomobject]@{startup=[Environment]::GetFolderPath('Startup');"
                  "programs=[Environment]::GetFolderPath('Programs');"
                  "desktop=[Environment]::GetFolderPath('Desktop')} | ConvertTo-Json -Compress")
        _folders.update(json.loads(out))
    return _folders


def icon_path(data_dir):
    """A Windows icon made from the app's own pictures (kept in the data folder)."""
    p = os.path.join(data_dir, "moneythistle.ico")
    if os.path.exists(p):
        return p
    pngs = []
    for name in ("favicon-32.png", os.path.join("brand", "logo-64.png"), os.path.join("brand", "logo-128.png"),
                 "icon-192.png"):
        try:
            with open(os.path.join(STATIC, name), "rb") as f:
                data = f.read()
            w, h = struct.unpack(">II", data[16:24])
            if data[:8] == b"\x89PNG\r\n\x1a\n" and w <= 256 and h <= 256:
                pngs.append((w, h, data))
        except OSError:
            pass
    if not pngs:
        return ""
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for w, h, data in pngs:
        entries += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    with open(p, "wb") as f:
        f.write(head + entries + blobs)
    return p


def _win_shortcut(lnk, args, data_dir, desc):
    os.makedirs(os.path.dirname(lnk), exist_ok=True)
    _ps("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:MT_LNK);$s.TargetPath=$env:MT_TARGET;"
        "$s.Arguments=$env:MT_ARGS;$s.WorkingDirectory=$env:MT_DIR;$s.Description=$env:MT_DESC;"
        "if($env:MT_ICON){$s.IconLocation=$env:MT_ICON};$s.Save()",
        {"MT_LNK": lnk, "MT_TARGET": pythonw(), "MT_ARGS": subprocess.list2cmdline([MAIN] + args), "MT_DIR": HERE,
         "MT_DESC": desc, "MT_ICON": icon_path(data_dir)})


def _desktop_entry(path, name, args, comment):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmd = " ".join(_sh(x) for x in [sys.executable, MAIN] + args)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"[Desktop Entry]\nType=Application\nName={name}\nComment={comment}\nExec={cmd}\n"
                f"Icon={os.path.join(STATIC, 'icon-192.png')}\nTerminal=false\nCategories=Office;Finance;\n")


def _sh(s):
    return "'" + str(s).replace("'", "'\\''") + "'" if any(c in str(s) for c in " '\"$\\") else str(s)


class Autostart:
    def __init__(self, data_dir, launch_args):
        self.data_dir = os.path.abspath(data_dir)
        self.args = list(launch_args)        # --data ..., and --port/--host when they were given

    # ----- where things go ----------------------------------------------------------
    def _folders(self):
        """This person's Startup, Start menu and desktop folders. A copy started with the
        computer runs as Windows' own account, so it uses the ones the person's own copy
        noted (or, failing that, the profile its data folder lives in)."""
        if not service_account():
            return win_folders()
        f = self._load().get("folders")
        if f:
            return f
        m = re.match(r"^([A-Za-z]:\\Users\\[^\\]+)", self.data_dir) or re.match(r"^([A-Za-z]:\\Users\\[^\\]+)", MAIN)
        if not m:
            raise ApiError("Open MoneyThistle once from its Start menu icon (signed in as yourself) first.")
        prof = m.group(1)
        start = os.path.join(prof, "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs")
        desk = next((d for d in (os.path.join(prof, "OneDrive", "Desktop"), os.path.join(prof, "Desktop"))
                     if os.path.isdir(d)), os.path.join(prof, "Desktop"))
        return {"startup": os.path.join(start, "Startup"), "programs": start, "desktop": desk}

    def _load(self):
        try:
            with open(self._marker(), encoding="utf-8-sig") as f:   # (older copies wrote a BOM)
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, **kw):
        v = self._load()
        v.update(kw)
        with open(self._marker(), "w", encoding="utf-8") as f:
            json.dump(v, f)

    def _paths(self):
        home = os.path.expanduser("~")
        if platform() == "windows":
            f = self._folders()
            return {"login": os.path.join(f["startup"], "MoneyThistle.lnk"),
                    "menu": os.path.join(f["programs"], "MoneyThistle", "MoneyThistle.lnk"),
                    "menu_stop": os.path.join(f["programs"], "MoneyThistle", "Stop MoneyThistle.lnk"),
                    "desktop": os.path.join(f["desktop"], "MoneyThistle.lnk")}
        if platform() == "mac":
            return {"login": os.path.join(home, "Library", "LaunchAgents", "app.moneythistle.plist")}
        cfg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
        share = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
        return {"login": os.path.join(cfg, "autostart", "moneythistle.desktop"),
                "menu": os.path.join(share, "applications", "moneythistle.desktop"),
                "menu_stop": os.path.join(share, "applications", "moneythistle-stop.desktop"),
                "desktop": os.path.join(home, "Desktop", "moneythistle.desktop")}

    def _marker(self):
        return os.path.join(self.data_dir, "autostart.json")

    def status(self):
        out = {"platform": platform(), "service_account": service_account(), "always": False, "login": False,
               "menu": False, "desktop": False, "shortcuts_supported": platform() != "mac", "error": None}
        out["always"] = bool(self._load().get("always"))
        if out["service_account"]:
            # Running now because Windows started it with the computer (until that's turned off).
            out["running_from_task"] = True
            out["always"] = self._load().get("always") is not False
        try:
            p = self._paths()
            out["login"] = os.path.exists(p["login"])
            out["menu"] = bool(p.get("menu")) and os.path.exists(p["menu"])
            out["desktop"] = bool(p.get("desktop")) and os.path.exists(p["desktop"])
        except Exception as e:
            out["error"] = str(e)
        out["always_how"] = self.always_instructions()
        return out

    # ----- start menu and desktop ---------------------------------------------------
    def _shortcuts_ok(self):
        if platform() == "mac":
            raise ApiError("On a Mac, keep the address as a bookmark, or add the page to the Dock from Safari "
                           "(File, Add to Dock).")

    def ensure_menu(self):
        """The Start menu (or applications menu) entries, made on every start when missing:
        "MoneyThistle" opens it (starting it first if needed), "Stop MoneyThistle" stops it.
        Updated when the app or data folder moved."""
        self._shortcuts_ok()
        p = self._paths()
        if platform() == "windows":
            _win_shortcut(p["menu"], self.args, self.data_dir, "Open MoneyThistle (starts it if needed)")
            _win_shortcut(p["menu_stop"], ["--stop"] + self.args, self.data_dir,
                          "Stop MoneyThistle (it saves and backs up first)")
        else:
            _desktop_entry(p["menu"], "MoneyThistle", self.args, "Open MoneyThistle (starts it if needed)")
            _desktop_entry(p["menu_stop"], "Stop MoneyThistle", ["--stop"] + self.args, "Stop MoneyThistle")
        self._remember()

    def _remember(self):
        """What the shortcuts were last made for, so a moved folder makes them again."""
        try:
            with open(os.path.join(self.data_dir, "shortcuts.json"), "w", encoding="utf-8") as f:
                json.dump({"main": MAIN, "python": pythonw(), "args": self.args}, f)
            if platform() == "windows" and not service_account():
                self._save(folders=win_folders())   # for a copy Windows starts with the computer
        except OSError:
            pass

    def menu_current(self):
        try:
            with open(os.path.join(self.data_dir, "shortcuts.json"), encoding="utf-8") as f:
                was = json.load(f)
            return was == {"main": MAIN, "python": pythonw(), "args": self.args} and os.path.exists(self._paths()["menu"])
        except (OSError, ValueError):
            return False

    def set_desktop(self, on):
        """A MoneyThistle icon on the desktop (chosen when it's set up, or in Settings)."""
        self._shortcuts_ok()
        p = self._paths()
        if not on:
            if os.path.exists(p["desktop"]):
                os.remove(p["desktop"])
        elif platform() == "windows":
            _win_shortcut(p["desktop"], self.args, self.data_dir, "Open MoneyThistle (starts it if needed)")
        else:
            _desktop_entry(p["desktop"], "MoneyThistle", self.args, "Open MoneyThistle (starts it if needed)")
            os.chmod(p["desktop"], 0o755)
        return self.status()

    # ----- at sign-in ---------------------------------------------------------------
    def set_login(self, on):
        p = self._paths()["login"]
        if not on:
            if os.path.exists(p):
                os.remove(p)
            return self.status()
        args = ["--no-browser"] + self.args
        if platform() == "windows":
            _win_shortcut(p, args, self.data_dir, "Start MoneyThistle when I sign in")
        elif platform() == "mac":
            os.makedirs(os.path.dirname(p), exist_ok=True)
            items = "".join(f"<string>{_xml(a)}</string>" for a in [sys.executable, MAIN] + args)
            with open(p, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
                        f"<key>Label</key><string>app.moneythistle</string><key>ProgramArguments</key><array>{items}</array>"
                        f"<key>WorkingDirectory</key><string>{_xml(HERE)}</string>"
                        "<key>RunAtLoad</key><true/></dict></plist>\n")
        else:
            _desktop_entry(p, "MoneyThistle", args, "Start MoneyThistle when I sign in")
        return self.status()

    # ----- always, with the computer ------------------------------------------------
    def _service_script(self):
        """Windows: a script that registers (or removes) the start-with-Windows task. It
        runs as administrator, after Windows asks the person."""
        cmd = subprocess.list2cmdline([MAIN, "--no-browser"] + self.args)
        marker = self._marker()   # MoneyThistle notes the choice itself once this succeeds
        q = lambda s: "'" + str(s).replace("'", "''") + "'"
        return f"""# MoneyThistle: start with Windows (before anyone signs in) or stop doing that.
param([switch]$Remove)
$ErrorActionPreference = 'Stop'
try {{
  if ($Remove) {{
    Unregister-ScheduledTask -TaskName '{TASK}' -Confirm:$false -ErrorAction SilentlyContinue
  }} else {{
    $a = New-ScheduledTaskAction -Execute {q(pythonw())} -Argument {q(cmd)} -WorkingDirectory {q(HERE)}
    $t = New-ScheduledTaskTrigger -AtStartup
    $p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    # No time limit (the default stops a task after 3 days); start again if it stops by itself.
    $s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries `
         -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName '{TASK}' -Action $a -Trigger $t -Principal $p -Settings $s `
      -Description 'MoneyThistle, available to this computer and your home network whenever it is on' -Force | Out-Null
  }}
}} catch {{
  Set-Content -LiteralPath {q(marker + ".error")} -Value ($_ | Out-String) -Encoding UTF8
  exit 1
}}
"""

    def always_instructions(self):
        """What to do on this kind of computer (shown in Settings)."""
        if platform() == "windows":
            return {"kind": "button"}
        args = " ".join(_sh(x) for x in [sys.executable, MAIN, "--no-browser"] + self.args)
        if platform() == "mac":
            return {"kind": "command", "text": (
                f"sudo tee /Library/LaunchDaemons/app.moneythistle.plist >/dev/null <<'EOF'\n"
                '<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict>'
                "<key>Label</key><string>app.moneythistle</string><key>UserName</key>"
                f"<string>{_xml(getpass.getuser())}</string><key>ProgramArguments</key><array>"
                + "".join(f"<string>{_xml(a)}</string>" for a in [sys.executable, MAIN, "--no-browser"] + self.args)
                + "</array><key>RunAtLoad</key><true/><key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>"
                "</dict></plist>\nEOF\nsudo launchctl load -w /Library/LaunchDaemons/app.moneythistle.plist")}
        return {"kind": "command", "text": (
            "sudo tee /etc/systemd/system/moneythistle.service >/dev/null <<'EOF'\n[Unit]\nDescription=MoneyThistle\n"
            f"After=network-online.target\n\n[Service]\nUser={getpass.getuser()}\nWorkingDirectory={HERE}\n"
            f"ExecStart={args}\nRestart=on-failure\n\n[Install]\nWantedBy=multi-user.target\nEOF\n"
            "sudo systemctl daemon-reload && sudo systemctl enable --now moneythistle")}

    def set_always(self, on, local_request):
        """Windows: ask Windows to run the script as administrator (it shows its permission
        prompt on this computer's screen, so only from a browser on this computer)."""
        if platform() != "windows":
            raise ApiError("Run the command shown in a terminal on this computer.")
        # The copy Windows started already has the rights (no prompt); it keeps running until
        # it's shut down or the computer restarts. Any other copy asks Windows, on its screen.
        if not service_account() and not local_request:
            raise ApiError("Do this from a browser on the computer MoneyThistle runs on: Windows asks there "
                           "for permission.")
        path = os.path.join(self.data_dir, "start-with-windows.ps1")
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(self._service_script())
        err = self._marker() + ".error"
        if os.path.exists(err):
            os.remove(err)
        arg = f"-NoProfile -ExecutionPolicy Bypass -File \"{path}\"" + ("" if on else " -Remove")
        try:
            if service_account():
                _ps("Start-Process powershell -Wait -WindowStyle Hidden -ArgumentList $env:MT_A", {"MT_A": arg})
            else:
                _ps("Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList $env:MT_A",
                    {"MT_A": arg})
        except ApiError:
            raise ApiError("Windows didn't give permission (or the request was cancelled), so nothing changed.")
        if os.path.exists(err):
            with open(err, encoding="utf-8-sig", errors="replace") as f:
                msg = f.read().strip().splitlines()
            raise ApiError("Windows couldn't set it up: " + (msg[0] if msg else "unknown error")[:300])
        if service_account():
            self._save(always=bool(on))
        else:
            self._save(always=bool(on), folders=win_folders())
        return self.status()


def _xml(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
