; SPDX-FileCopyrightText: 2026 Aymeric Malchrowicz
; SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
; Installateur Windows d'Orion (Inno Setup 6) : iscc /DVersion=0.1.0 packaging\windows\orion.iss
; Entrée : dist\Orion (python build_exe.py). Sortie : dist\Orion-Setup-<version>.exe
; Installation par utilisateur (aucun droit administrateur) ; les données vont dans %APPDATA%\Orion.

#ifndef Version
  #define Version "0.1.0"
#endif

[Setup]
AppId={{7C1E2A54-3F0B-4F5C-9C61-0B5E7A2D9F31}
AppName=Orion
AppVersion={#Version}
AppPublisher=MalchroSoft — Aymeric Malchrowicz
AppPublisherURL=https://github.com/malchrosoft/orion-assistant
DefaultDirName={localappdata}\Programs\Orion
DefaultGroupName=Orion
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\..\LICENSE
SetupIconFile=..\..\orion\data\logos\orion.ico
OutputDir=..\..\dist
OutputBaseFilename=Orion-Setup-{#Version}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Orion

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\..\dist\Orion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Orion"; Filename: "{app}\Orion.exe"
Name: "{group}\Panneau d'Orion"; Filename: "{app}\Orion.exe"; Parameters: "panneau"
Name: "{group}\Désinstaller Orion"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Orion"; Filename: "{app}\Orion.exe"; Tasks: bureau

[Run]
Filename: "{app}\Orion.exe"; Description: "Lancer Orion"; Flags: nowait postinstall skipifsilent
