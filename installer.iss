[Setup]
AppName=Legal Agent Assistant
AppVersion=1.0.0
DefaultDirName={autopf}\LegalAgentAssistant
DefaultGroupName=Legal Agent Assistant
OutputBaseFilename=LegalAgentAssistantInstaller
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Files]
Source: "dist\LegalAgentAssistant\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "installers\post_install.ps1"; DestDir: "{app}\installers"; Flags: ignoreversion
Source: "installers\OllamaSetup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: FileExists(ExpandConstant('{src}\\installers\\OllamaSetup.exe'))

[Icons]
Name: "{group}\Legal Agent Assistant"; Filename: "{app}\LegalAgentAssistant.exe"
Name: "{autodesktop}\Legal Agent Assistant"; Filename: "{app}\LegalAgentAssistant.exe"

[Run]
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/S"; Flags: runhidden waituntilterminated; Check: (not IsOllamaInstalled) and FileExists(ExpandConstant('{tmp}\\OllamaSetup.exe'))
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\installers\post_install.ps1"""; Flags: runhidden waituntilterminated
Filename: "{app}\LegalAgentAssistant.exe"; Description: "Khoi dong Legal Agent Assistant"; Flags: nowait postinstall skipifsilent

[Code]
function IsOllamaInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{pf}\\Ollama\\ollama.exe')) or
            FileExists(ExpandConstant('{pf32}\\Ollama\\ollama.exe'));
end;
