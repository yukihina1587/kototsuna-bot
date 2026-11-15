#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppSourceDir
  #define AppSourceDir "dist\Kototsuna"
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
MinVersion=10.0

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Remove _internal/ completely before installing new files.
; This prevents stale .pyd/.dll files (e.g. old PIL/_imaging.pyd) from
; persisting across updates and causing version mismatch errors.
Type: filesandordirs; Name: "{app}\_internal"
; Remove runtime_cache/ (pyd cache) to force rthook to re-copy all .pyd files.
; rthook skips copy when file sizes match, so stale cached versions persist
; across updates when new/old .pyd files happen to have identical sizes.
Type: filesandordirs; Name: "{app}\runtime_cache"

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\icon_fullsize.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "build\prerequisites\MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[Icons]
Name: "{group}\ことつな！"; Filename: "{app}\Kototsuna.exe"; IconFilename: "{app}\icon_fullsize.ico"; IconIndex: 0
Name: "{group}\ことつな！ 従来画面"; Filename: "{app}\Kototsuna.exe"; Parameters: "--legacy-ui"; IconFilename: "{app}\icon_fullsize.ico"; IconIndex: 0
Name: "{group}\ことつな！をアンインストール"; Filename: "{uninstallexe}"
Name: "{userdesktop}\ことつな！"; Filename: "{app}\Kototsuna.exe"; Tasks: desktopicon; IconFilename: "{app}\icon_fullsize.ico"; IconIndex: 0

[Run]
Filename: "{app}\Kototsuna.exe"; Description: "{cm:LaunchProgram,ことつな！}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2Installed: Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := (RegQueryStringValue(HKLM32, Key, 'pv', Version) and
    (Version <> '') and (Version <> '0.0.0.0'));
  if not Result then
    Result := (RegQueryStringValue(HKCU, Key, 'pv', Version) and
      (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if WebView2Installed then
  begin
    Log('WebView2 Runtime is already installed.');
    exit;
  end;
  { Check prerequisites before replacing the existing installation. }
  ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'),
      '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    Log('WebView2 installer could not be started.');
  if not WebView2Installed then
    Result := 'WebView2 Runtimeをインストールできませんでした。インターネット接続を確認して再実行してください。既存のことつな！は変更していません。';
end;
