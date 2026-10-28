#ifndef AppVersion
#define AppVersion "0.2.0"
#endif
[Setup]
AppId={{F95C9AEA-F823-46D2-A108-DA84C52D92A4}
AppName=FileOrganizer
AppVersion={#AppVersion}
AppPublisher=FileOrganizer
DefaultDirName={localappdata}\Programs\FileOrganizer
DefaultGroupName=FileOrganizer
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19041
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=FileOrganizer-Setup-{#AppVersion}-Windows-x64
UninstallDisplayIcon={app}\FileOrganizer.exe
CloseApplications=yes
RestartApplications=no
[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; Flags: unchecked
[Files]
Source: "..\dist\FileOrganizer.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs
[Icons]
Name: "{group}\FileOrganizer"; Filename: "{app}\FileOrganizer.exe"
Name: "{userdesktop}\FileOrganizer"; Filename: "{app}\FileOrganizer.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\FileOrganizer.exe"; Description: "Ouvrir FileOrganizer"; Flags: nowait postinstall skipifsilent
; No UninstallDelete section: config, index and personal archives are never removed.
