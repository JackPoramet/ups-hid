; ══════════════════════════════════════════════════════════════
; UPS Monitor — Inno Setup Installer Script
; สร้างตัวติดตั้ง .exe พร้อม Uninstaller สำหรับ Windows
;
; ต้องการ:
;   - Inno Setup 6.x  https://jrsoftware.org/isinfo.php
;   - dist\UPS-Monitor.exe (สร้างจาก PyInstaller ก่อน)
;
; Build:
;   iscc windows\installer\installer.iss
;
; Output:
;   windows\installer\Output\UPS-Monitor-Setup.exe
; ══════════════════════════════════════════════════════════════

#define AppName        "ENEREX UPS Monitor"
#define AppVersion     "1.0.0"
#define AppPublisher   "ENEREX"
#define AppURL         "https://github.com/JackPoramet/ups-hid"
#define AppExeName     "ENEREX-UPS-Monitor.exe"
#define AppDescription "ENEREX UPS Monitor — Windows System Tray Service"

[Setup]
; ── Identity ───────────────────────────────────────────────────
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; ── Install Location ───────────────────────────────────────────
DefaultDirName={commonpf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; ── Output ─────────────────────────────────────────────────────
OutputDir=Output
OutputBaseFilename=ENEREX-UPS-Monitor-Setup
SetupIconFile=..\assets\ups_icon.ico

; ── Compression ────────────────────────────────────────────────
Compression=lzma2/ultra64
SolidCompression=yes

; ── Windows version requirement ────────────────────────────────
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; ── Privileges ─────────────────────────────────────────────────
; บังคับเรียกสิทธิ์ Administrator (UAC Prompt) เสมอ (Windows จะแสดงโล่ UAC เมื่อรันตัวติดตั้ง)
PrivilegesRequired=admin

; ── Wizard style ───────────────────────────────────────────────
WizardStyle=modern
WizardSizePercent=100

; ── Uninstall ──────────────────────────────────────────────────
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Desktop shortcut (optional - checked by default)
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

; Windows Startup (optional - checked by default)
Name: "startup"; Description: "Start UPS Monitor with Windows"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; ── Main executable ─────────────────────────────────────────────
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcut
Name: "{group}\{#AppName}";        FileName: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; FileName: "{uninstallexe}"

; Desktop shortcut (optional — ขึ้นอยู่กับ task ที่เลือก)
Name: "{autodesktop}\{#AppName}"; FileName: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Windows Startup — ลงทะเบียนให้เปิดพร้อม Windows (ถ้า user เลือก task "startup")
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
; เปิดโปรแกรมหลังติดตั้งเสร็จ (optional)
Filename: "{app}\{#AppExeName}"; Description: "เปิด {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; หยุดโปรแกรมก่อนถอนการติดตั้ง
Filename: "taskkill"; Parameters: "/f /im {#AppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
; ลบ config files ที่ app สร้างขึ้น (AppData)
; Note: ลบเฉพาะถ้า user ยืนยัน — Inno Setup ไม่บังคับ
Type: filesandordirs; Name: "{userappdata}\UPS-Monitor\logs"
