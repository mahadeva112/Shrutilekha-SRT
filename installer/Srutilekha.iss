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
Source: "THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion
[Icons]
Name: "{group}\Srutilekha"; Filename: "{app}\Srutilekha.exe"
[InstallDelete]
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Srutilekha.lua"; Check: UsePythonLauncher
Type: files; Name: "{userappdata}\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility\Srutilekha.py"; Check: UseLuaLauncher
[Dirs]
Name: "{localappdata}\Srutilekha\logs"
[Run]
Filename: "{app}\Srutilekha.exe"; Description: "Open Srutilekha and enter your API key"; Flags: nowait postinstall skipifsilent
[Code]
var ResolvePage: TInputOptionWizardPage;
function UsePythonLauncher: Boolean;
begin
  Result := ResolvePage.SelectedValueIndex = 1;
end;
function UseLuaLauncher: Boolean;
begin
  Result := not UsePythonLauncher;
end;
procedure InitializeWizard;
var MS, LS: Cardinal; DefaultPython: Boolean;
begin
  DefaultPython := False;
  if GetVersionNumbers(ExpandConstant('{pf}\Blackmagic Design\DaVinci Resolve\Resolve.exe'), MS, LS) then
    DefaultPython := MS >= ((21 shl 16) + 1);
  ResolvePage := CreateInputOptionPage(wpSelectDir, 'DaVinci Resolve version',
    'Choose the scripting host for your installed Resolve version',
    'Setup will add Srutilekha to Workspace > Scripts. Restart Resolve after installation.', True, False);
  ResolvePage.Add('Resolve 21.0 or earlier (Lua launcher)');
  ResolvePage.Add('Resolve 21.1 or newer (Python launcher)');
  if DefaultPython then ResolvePage.SelectedValueIndex := 1
  else ResolvePage.SelectedValueIndex := 0;
end;
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    if not SaveStringToFile(GetEnv('USERPROFILE') + '\.audio_to_srt_path', UTF8Encode(ExpandConstant('{app}')) + #13#10, False) then
      RaiseException('Could not save the Resolve installation path.');
end;
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var SavedPath: AnsiString;
begin
  if CurUninstallStep = usPostUninstall then
    if LoadStringFromFile(GetEnv('USERPROFILE') + '\.audio_to_srt_path', SavedPath) then
      if CompareText(Trim(UTF8Decode(SavedPath)), ExpandConstant('{app}')) = 0 then
        DeleteFile(GetEnv('USERPROFILE') + '\.audio_to_srt_path');
end;
