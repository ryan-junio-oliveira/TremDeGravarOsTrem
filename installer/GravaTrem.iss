; GravaTrem — script do instalador (Inno Setup 6).
; Gerado pelo pipeline: build.bat (nao edite a versao aqui; passe /DAppVersion=X.Y.Z).
#ifndef AppVersion
  #define AppVersion "0.0.1"
#endif

#define AppName "GravaTrem"
#define AppExe "GravaTrem.exe"
#define AppId "{{B6482141-31E5-4D7D-A76E-147AF7F110BA}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion={#AppVersion}
AppPublisher=Trem de Gravar os Trem
; AppPublisherURL: preencher com o repo oficial ao publicar a primeira release.
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=..\LICENSE
; O app tolera app.ini ausente (usa defaults e cria ao gravar);
; por isso nao instalamos config — cada usuario gera a sua.
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Bundle gerado pelo PyInstaller (build.bat): exe + _internal + lang.
Source: "..\dist\GravaTrem\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
