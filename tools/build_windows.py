"""Build MoneyThistle-Setup.exe: one file someone double-clicks to install MoneyThistle on
Windows, with its own private copy of Python inside (nothing else to install first).

    python tools/build_windows.py            -> dist/MoneyThistle-Setup-<version>.exe

How it's made (no outside tools: the Python running this script and Windows' own IExpress):
  1. runtime/  a trimmed copy of this Python: python.exe, pythonw.exe, its DLLs and the
     standard library compiled into python3XX.zip, isolated by a ._pth file (it never
     looks at other Pythons or their packages).
  2. app/      main.py and moneyapp/ (no tests, data, screenshots or Docker files).
  3. payload.zip of both, plus installer/install.ps1 and uninstall.ps1.
  4. IExpress packs payload.zip and install.ps1 into a self-extracting .exe that asks
     "Install MoneyThistle on this computer?" and runs install.ps1.
"""

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the app folder
BUILD = os.path.join(HERE, "build", "windows")
DIST = os.path.join(HERE, "dist")
sys.path.insert(0, HERE)

# Standard-library parts MoneyThistle never uses (tests, GUI toolkits, installers...).
SKIP_LIB = {"site-packages", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3",
            "pydoc_data", "venv", "__pycache__", "unittest", "distutils", "msilib"}
SKIP_DLL = ("_test", "_tkinter", "tcl", "tk86", "_msi", "_ctypes_test", "py.ico", "pyc.ico", "pyd.ico")


def version():
    from moneyapp import version as v
    return v.VERSION


def build_runtime(dest):
    base = sys.base_prefix
    tag = f"python{sys.version_info.major}{sys.version_info.minor}"
    os.makedirs(dest)
    for f in ("python.exe", "pythonw.exe", "python3.dll", f"{tag}.dll", "vcruntime140.dll", "vcruntime140_1.dll",
              "LICENSE.txt"):
        if os.path.exists(os.path.join(base, f)):
            shutil.copy2(os.path.join(base, f), os.path.join(dest, "PYTHON-LICENSE.txt" if f == "LICENSE.txt" else f))
    for f in os.listdir(os.path.join(base, "DLLs")):
        if f.endswith((".pyd", ".dll")) and not f.startswith(SKIP_DLL):
            shutil.copy2(os.path.join(base, "DLLs", f), os.path.join(dest, f))
    # The standard library, compiled, in one zip (fast to start, nothing to tamper with).
    lib = os.path.join(base, "Lib")
    from importlib._bootstrap_external import _code_to_timestamp_pyc
    with zipfile.ZipFile(os.path.join(dest, f"{tag}.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(lib):
            dirs[:] = [d for d in dirs if d not in SKIP_LIB]
            for f in files:
                if not f.endswith(".py"):
                    continue
                src = os.path.join(root, f)
                rel = os.path.relpath(src, lib).replace(os.sep, "/")
                # Compiled in memory (a temporary file per module upsets virus scanners).
                with open(src, "rb") as fh:
                    source = fh.read()
                try:
                    code = compile(source, rel, "exec", dont_inherit=True)
                except SyntaxError:
                    continue
                st = os.stat(src)
                z.writestr(rel[:-3] + ".pyc", bytes(_code_to_timestamp_pyc(code, st.st_mtime, st.st_size)))
    # Isolated: only its own library and MoneyThistle's folder, never site-packages.
    with open(os.path.join(dest, f"{tag}._pth"), "w", encoding="utf-8") as f:
        f.write(f"{tag}.zip\n.\n..\\app\n")


def copy_app(dest):
    os.makedirs(dest)
    shutil.copy2(os.path.join(HERE, "main.py"), dest)
    for extra in ("README.md", "MECHANICS.md"):
        if os.path.exists(os.path.join(HERE, extra)):
            shutil.copy2(os.path.join(HERE, extra), dest)
    shutil.copytree(os.path.join(HERE, "moneyapp"), os.path.join(dest, "moneyapp"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def make_icon(stage):
    from moneyapp import autostart
    p = autostart.icon_path(stage)   # made from the app's own pictures
    if p and os.path.basename(p) != "moneythistle.ico":
        shutil.move(p, os.path.join(stage, "moneythistle.ico"))


SED = """[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles
[Strings]
InstallPrompt=Install MoneyThistle on this computer? It takes about a minute, needs nothing else, and your money data stays on this computer.
DisplayLicense=
FinishMessage=
TargetName={target}
FriendlyName=MoneyThistle
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File install.ps1
PostInstallCmd=<None>
AdminQuietInstCmd=powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File install.ps1 -Quiet
UserQuietInstCmd=powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File install.ps1 -Quiet
FILE0="install.ps1"
FILE1="payload.zip"
FILE2="setup-info.json"
[SourceFiles]
SourceFiles0={source}\\
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
"""


def main():
    if os.name != "nt":
        sys.exit("Build the Windows installer on Windows (it uses Windows' IExpress).")
    ver = version()
    if os.path.isdir(BUILD):
        shutil.rmtree(BUILD)
    stage = os.path.join(BUILD, "MoneyThistle")
    pack = os.path.join(BUILD, "package")
    os.makedirs(pack)
    print("Python runtime...")
    build_runtime(os.path.join(stage, "runtime"))
    print("App files...")
    copy_app(os.path.join(stage, "app"))
    make_icon(stage)
    for f in ("LICENSE", "CHANGELOG.md"):
        if os.path.exists(os.path.join(HERE, f)):
            shutil.copy2(os.path.join(HERE, f), stage)
    with open(os.path.join(stage, "VERSION.txt"), "w", encoding="utf-8") as f:
        f.write(ver + "\n")
    os.makedirs(DIST, exist_ok=True)
    iscc = find_iscc()
    if iscc and "--iexpress" not in sys.argv:
        # The branded installer: MoneyThistle's icon, name and version, a short wizard, an uninstaller.
        print("Packing with Inno Setup...")
        r = subprocess.run([iscc, "/Q", f"/DVersion={ver}", f"/DStage={stage}", f"/DOutDir={DIST}",
                            os.path.join(HERE, "installer", "MoneyThistle.iss")], capture_output=True, text=True)
        target = os.path.join(DIST, f"MoneyThistle-Setup-{ver}.exe")
        if r.returncode != 0 or not os.path.exists(target):
            sys.exit(f"Inno Setup failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        return done(target)
    print("Inno Setup not found (it makes the branded installer): making the plain one with IExpress.")
    shutil.copy2(os.path.join(HERE, "installer", "uninstall.ps1"), stage)
    print("Payload...")
    with zipfile.ZipFile(os.path.join(pack, "payload.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(stage):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, stage))
    shutil.copy2(os.path.join(HERE, "installer", "install.ps1"), pack)
    with open(os.path.join(pack, "setup-info.json"), "w", encoding="utf-8") as f:
        json.dump({"version": ver}, f)
    os.makedirs(DIST, exist_ok=True)
    target = os.path.join(DIST, f"MoneyThistle-Setup-{ver}.exe")
    # IExpress can't cope with spaces in paths: it works in a plain temporary folder.
    work = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "moneythistle-setup-build")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(pack, os.path.join(work, "src"))
    out = os.path.join(work, "MoneyThistle-Setup.exe")
    sed = os.path.join(work, "setup.sed")
    with open(sed, "w", encoding="mbcs") as f:
        f.write(SED.format(target=out, source=os.path.join(work, "src")))
    print("Packing with IExpress...")
    r = subprocess.run([os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "iexpress.exe"),
                        "/N", "/Q", sed], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        sys.exit(f"IExpress failed ({r.returncode}): {r.stdout} {r.stderr}")
    shutil.move(out, target)
    shutil.rmtree(work, ignore_errors=True)
    return done(target)


def done(target):
    if "--keep" not in sys.argv:
        shutil.rmtree(BUILD, ignore_errors=True)   # (--keep leaves build/windows for a look inside)
    print(f"Done: {target} ({os.path.getsize(target) / 1048576:.1f} MB)")
    return target


def find_iscc():
    """Inno Setup's compiler: ISCC from the environment, PATH, or where it installs."""
    if os.environ.get("ISCC") and os.path.exists(os.environ["ISCC"]):
        return os.environ["ISCC"]
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return found
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        p = os.path.join(base, "Programs" if base == os.environ.get("LOCALAPPDATA") else "", "Inno Setup 6", "ISCC.exe")
        if base and os.path.exists(p):
            return p
    return None


if __name__ == "__main__":
    main()
