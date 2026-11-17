; Inno Setup 6 script for the NeonPine Companion Windows installer.
; Built by packaging/build.py --installer (which passes AppVersion, SourceDir and OutputDir), e.g.
;   ISCC /DAppVersion=1.0.0 /DSourceDir=..\..\dist\NeonPine Companion /DOutputDir=..\..\dist neonpine-companion.iss
; Installs per user by default (no admin prompt); the user can choose "all users" in the first dialog.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\NeonPine Companion"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist"
#endif
#ifndef IconFile
  #define IconFile "..\..\build\neonpine-companion.ico"
#endif

#define AppName "NeonPine Companion"
#define AppExe "NeonPine Companion.exe"

[Setup]
AppId={{6F3B2C1E-8A4D-4E57-9B0C-2D1F7A5E9C31}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=NeonPine
AppPublisherURL=https://github.com/lukmatuska/NeonPine
AppSupportURL=https://github.com/lukmatuska/NeonPine
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=NeonPine-Companion-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Closes a running Companion (tray included) before files are replaced or removed
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start with Windows (in the tray)"; GroupDescription: "Startup:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Leftovers of an older version's bundled files (e.g. a previous firmware image or Qt plugins)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Same value the app writes from App > "Start with the computer", so the checkbox there stays in sync.
; It is per user (HKCU) even for an all-users install, like the app's own setting.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --tray"; Tasks: autostart; Flags: uninsdeletevalue
; Removes the value on uninstall even when it was set from inside the app and not by this installer
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "{#AppName}"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Settings and saved animations live in %APPDATA%\neonpine-companion and are kept on purpose
Type: filesandordirs; Name: "{app}"
