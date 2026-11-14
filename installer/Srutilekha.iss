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
var ResolvePage: TInputOptionWizardPage;
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
