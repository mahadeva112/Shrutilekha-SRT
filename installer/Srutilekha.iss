#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
[Setup]
AppId={{0B88D427-1A18-45BD-A516-C576567354F4}
AppName=Srutilekha
AppVersion={#AppVersion}
AppPublisher=mahadeva112
AppPublisherURL=https://github.com/mahadeva112/Shrutilekha-SRT
DefaultDirName={localappdata}\Programs\Srutilekha
DefaultGroupName=Srutilekha
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\release
OutputBaseFilename=Srutilekha-Setup-{#AppVersion}
SetupIconFile=..\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\Srutilekha.exe
LicenseFile=THIRD-PARTY-NOTICES.txt
[Files]
Source: "..\dist\Srutilekha\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\audio_to_srt.py"; DestDir: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"; DestName: "Srutilekha.py"; Flags: ignoreversion; Check: UsePythonLauncher
Source: "..\build\Srutilekha.lua"; DestDir: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility"; DestName: "Srutilekha.lua"; Flags: ignoreversion; Check: UseLuaLauncher
Source: "..\resolve_bridge.lua"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\Srutilekha"; Filename: "{app}\Srutilekha.exe"
[InstallDelete]
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Srutilekha.lua"; Check: UsePythonLauncher
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Srutilekha.py"; Check: UseLuaLauncher
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Srutilekha.py"; Check: UseBridgeLauncher
[Dirs]
Name: "{localappdata}\Srutilekha\logs"
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Srutilekha"; ValueData: """{app}\Srutilekha.exe"" --tray"; Flags: uninsdeletevalue; Check: EnableTrayStartup
[Run]
Filename: "{app}\Srutilekha.exe"; Parameters: "--tray"; Flags: nowait runhidden; Check: UseBridgeLauncher
Filename: "{app}\Srutilekha.exe"; Description: "Open Srutilekha and enter your API key"; Flags: nowait postinstall skipifsilent
[Code]
// Every Srutilekha window is drawn by Microsoft Edge WebView2 (the Evergreen
// runtime). Windows 11 ships it; a PC without it gets it from Microsoft's
// bootstrapper before any file is installed. web_ui.py checks the same keys.
const
  WebView2Client = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  WebView2Bootstrapper = 'https://go.microsoft.com/fwlink/p/?LinkId=2124703';
var ResolvePage: TInputOptionWizardPage;
    WebView2Page: TDownloadWizardPage;
function WebView2Found(RootKey: Integer; SubKey: String): Boolean;
var Version: String;
begin
  Result := RegQueryStringValue(RootKey, SubKey, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0');
end;
function WebView2Installed: Boolean;
begin
  // Per machine (the 32-bit registry view on 64-bit Windows) or per user.
  Result := WebView2Found(HKLM32, 'SOFTWARE\' + WebView2Client) or
            WebView2Found(HKLM64, 'SOFTWARE\' + WebView2Client) or
            WebView2Found(HKCU, 'Software\' + WebView2Client);
end;
function InstallWebView2: Boolean;
var Code: Integer;
begin
  Result := True;
  if WebView2Installed then
    Exit;
  WebView2Page.Clear;
  WebView2Page.Add(WebView2Bootstrapper, 'MicrosoftEdgeWebview2Setup.exe', '');
  WebView2Page.Show;
  try
    try
      WebView2Page.Download;
      WebView2Page.SetText('Installing Microsoft Edge WebView2...',
        'Srutilekha draws its windows with WebView2. This can take a minute.');
      WebView2Page.ProgressBar.Style := npbstMarquee;
      // Not elevated, the bootstrapper installs WebView2 for this Windows user.
      if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '',
                  SW_HIDE, ewWaitUntilTerminated, Code) then
        RaiseException('The WebView2 installer did not start: ' + SysErrorMessage(Code));
      if not WebView2Installed then
        RaiseException(Format('The WebView2 installer finished (code %d), but WebView2 is still missing.', [Code]));
      Log('Microsoft Edge WebView2 installed.');
    except
      Result := False;
      if not WebView2Page.AbortedByUser then
        SuppressibleMsgBox('Srutilekha needs Microsoft Edge WebView2, and Setup could not add it yet.' + #13#10#13#10 +
          GetExceptionMessage + #13#10#13#10 +
          'Check the internet connection and click Install to try again, or install the WebView2 Runtime from ' +
          WebView2Bootstrapper + ' and then run this Setup again.', mbError, MB_OK, IDOK);
    end;
  finally
    WebView2Page.ProgressBar.Style := npbstNormal;
    WebView2Page.Hide;
  end;
end;
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  // Also called on silent installs; False there ends Setup before installing.
  Result := True;
  if CurPageID = wpReady then
    Result := InstallWebView2;
end;
function UsePythonLauncher: Boolean;
begin
  Result := ResolvePage.SelectedValueIndex = 2;
end;
function UseLuaLauncher: Boolean;
begin
  Result := ResolvePage.SelectedValueIndex = 0;
end;
function UseBridgeLauncher: Boolean;
begin
  Result := ResolvePage.SelectedValueIndex = 1;
end;
function EnableTrayStartup: Boolean;
begin
  Result := UseBridgeLauncher and not FileExists(ExpandConstant('{localappdata}\Srutilekha\tray-startup-disabled.flag'));
end;
procedure InitializeWizard;
var MS, LS: Cardinal; DefaultBridge: Boolean;
begin
  DefaultBridge := False;
  if GetVersionNumbers(ExpandConstant('{pf}\Blackmagic Design\DaVinci Resolve\Resolve.exe'), MS, LS) then
    DefaultBridge := MS >= ((21 shl 16) + 1);
  ResolvePage := CreateInputOptionPage(wpSelectDir, 'DaVinci Resolve version',
    'Choose the scripting host for your installed Resolve version',
    'Setup will add Srutilekha to Workspace > Scripts. Restart Resolve after installation.', True, False);
  ResolvePage.Add('Resolve 21.0 or earlier (Lua launcher)');
  ResolvePage.Add('Resolve 21.1 or newer, Free or Studio (Lua bridge + desktop app)');
  ResolvePage.Add('Resolve 21.1 or newer, Studio ONLY (Python menu launcher)');
  if DefaultBridge then ResolvePage.SelectedValueIndex := 1
  else ResolvePage.SelectedValueIndex := 0;
  WebView2Page := CreateDownloadPage('Microsoft Edge WebView2',
    'Srutilekha needs WebView2 for its windows. Setup is adding it from Microsoft.', nil);
end;
procedure CurStepChanged(CurStep: TSetupStep);
var BridgeText: AnsiString; Text, Mailbox, ScriptPath: String;
begin
  if CurStep = ssPostInstall then
  begin
    if UseBridgeLauncher then
    begin
      Mailbox := ExpandConstant('{localappdata}\Srutilekha\resolve-bridge');
      ForceDirectories(Mailbox);
      if not LoadStringFromFile(ExpandConstant('{app}\resolve_bridge.lua'), BridgeText) then
        RaiseException('Could not read the Resolve bridge.');
      Text := UTF8Decode(BridgeText);
      StringChangeEx(Mailbox, '\', '\\', True);
      StringChangeEx(Text, '__SRUTILEKHA_MAILBOX__', Mailbox, True);
      ScriptPath := ExpandConstant('{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Srutilekha.lua');
      ForceDirectories(ExtractFileDir(ScriptPath));
      if not SaveStringToFile(ScriptPath, UTF8Encode(Text), False) then
        RaiseException('Could not install the Resolve Lua bridge.');
      SaveStringToFile(ExpandConstant('{app}\installed-bridge.lua'), UTF8Encode(Text), False);
    end;
    if not SaveStringToFile(GetEnv('USERPROFILE') + '\.audio_to_srt_path', UTF8Encode(ExpandConstant('{app}')) + #13#10, False) then
      RaiseException('Could not save the Resolve installation path.');
  end;
end;
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var SavedPath, InstalledBridge, CurrentBridge: AnsiString; ScriptPath: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    ScriptPath := ExpandConstant('{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Srutilekha.lua');
    if LoadStringFromFile(ExpandConstant('{app}\installed-bridge.lua'), InstalledBridge) and
       LoadStringFromFile(ScriptPath, CurrentBridge) then
      if InstalledBridge = CurrentBridge then DeleteFile(ScriptPath);
    DeleteFile(ExpandConstant('{app}\installed-bridge.lua'));
  end;
  if CurUninstallStep = usPostUninstall then
    if LoadStringFromFile(GetEnv('USERPROFILE') + '\.audio_to_srt_path', SavedPath) then
      if CompareText(Trim(UTF8Decode(SavedPath)), ExpandConstant('{app}')) = 0 then
        DeleteFile(GetEnv('USERPROFILE') + '\.audio_to_srt_path');
end;
