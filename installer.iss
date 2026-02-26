#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{B8A3C5E1-7F42-4D8E-9A1B-3C5D7E9F1234}
AppName=ことつな！
AppVersion={#AppVersion}
AppPublisher=yukihina1587
DefaultDirName={localappdata}\Kototsuna
DefaultGroupName=ことつな！
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=Kototsuna_Setup
SetupIconFile=assets\icon_fullsize.ico
UninstallDisplayIcon={app}\Kototsuna.exe
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Kototsuna\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ことつな！"; Filename: "{app}\Kototsuna.exe"
Name: "{group}\ことつな！をアンインストール"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ことつな！"; Filename: "{app}\Kototsuna.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Kototsuna.exe"; Description: "{cm:LaunchProgram,ことつな！}"; Flags: nowait postinstall skipifsilent
