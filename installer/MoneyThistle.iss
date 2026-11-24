; MoneyThistle installer for Windows (Inno Setup 6). Built by tools/build_windows.py, which
; passes /DVersion=, /DStage= (runtime\, app\, moneythistle.ico, LICENSE) and /DOutDir=.
; Installs for the person only (no administrator rights): the program in
; %LOCALAPPDATA%\Programs\MoneyThistle; money data stays in %APPDATA%\MoneyThistle.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6F3C9B2E-4D71-4C55-9A0E-2B7E8D5F1A43}
AppName=MoneyThistle
AppVersion={#Version}
AppVerName=MoneyThistle {#Version}
AppPublisher=MoneyThistle contributors
AppComments=A Slightly Better Money App
AppCopyright=MoneyThistle contributors, AGPL-3.0
VersionInfoDescription=MoneyThistle Setup
VersionInfoProductName=MoneyThistle
VersionInfoVersion={#Version}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\MoneyThistle
DisableDirPage=yes
DefaultGroupName=MoneyThistle
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=no
OutputDir={#OutDir}
OutputBaseFilename=MoneyThistle-Setup-{#Version}
SetupIconFile={#Stage}\moneythistle.ico
UninstallDisplayIcon={app}\moneythistle.ico
UninstallDisplayName=MoneyThistle
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Messages]
WelcomeLabel2=This installs MoneyThistle {#Version} on this computer.%n%nIt needs nothing else, and your money data stays on this computer. MoneyThistle opens in your web browser.
FinishedLabel=MoneyThistle is installed. Open it any time from the Start menu.

[Tasks]
Name: "desktopicon"; Description: "Put a MoneyThistle icon on the desktop"; Flags: checkedonce

[InstallDelete]
; An update replaces the program files completely (your data lives elsewhere).
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\app"

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MoneyThistle"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\moneythistle.ico"; Comment: "Open MoneyThistle (starts it if needed)"
Name: "{group}\Stop MoneyThistle"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"" --stop"; WorkingDir: "{app}\app"; IconFilename: "{app}\moneythistle.ico"; Comment: "Stop MoneyThistle (it saves and backs up first)"
Name: "{userdesktop}\MoneyThistle"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\moneythistle.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"""; WorkingDir: "{app}\app"; Description: "Open MoneyThistle now"; Flags: nowait postinstall skipifsilent
; An update MoneyThistle installed itself (/VERYSILENT /AUTOSTART=1): start it again, without a
; new browser tab (the open page reloads by itself when it's back).
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app\main.py"" --no-browser"; WorkingDir: "{app}\app"; Flags: nowait; Check: StartAfterUpdate

[UninstallRun]
; Stop it first (it saves and makes its backup).
Filename: "{app}\runtime\python.exe"; Parameters: """{app}\app\main.py"" --stop"; WorkingDir: "{app}\app"; Flags: runhidden waituntilterminated; RunOnceId: "StopMoneyThistle"

[UninstallDelete]
; Made later by MoneyThistle itself (Settings): desktop icon, start at sign-in, caches.
Type: files; Name: "{userdesktop}\MoneyThistle.lnk"
Type: files; Name: "{userstartup}\MoneyThistle.lnk"
Type: filesandordirs; Name: "{group}"
Type: filesandordirs; Name: "{app}"

[Code]
function StartAfterUpdate: Boolean;
begin
  Result := ExpandConstant('{param:AUTOSTART|0}') = '1';
end;

// An update: ask the running copy to stop (it backs up first) before files are replaced.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\runtime\python.exe')) then
    Exec(ExpandConstant('{app}\runtime\python.exe'), '"' + ExpandConstant('{app}\app\main.py') + '" --stop',
         ExpandConstant('{app}\app'), SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var Code: Integer; Data: String;
begin
  if CurUninstallStep = usUninstall then begin
    // Started with the computer (set up as administrator in Settings): removing that asks too.
    if Exec('schtasks.exe', '/Query /TN MoneyThistle', '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0) then
      ShellExec('runas', 'schtasks.exe', '/Delete /TN MoneyThistle /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
  if CurUninstallStep = usPostUninstall then begin
    Data := ExpandConstant('{userappdata}\MoneyThistle');
    if DirExists(Data) and not UninstallSilent then
      if MsgBox('MoneyThistle is removed.' + #13#10#13#10 + 'Also delete your money data on this computer?' + #13#10 + Data + #13#10#13#10 +
                'Choose No to keep it: installing MoneyThistle again picks it up. Backups on Nextcloud are never touched.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Data, True, True, True);
  end;
end;
