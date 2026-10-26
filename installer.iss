; Inno Setup 6 – biên dịch bằng ISCC.exe installer.iss (sau khi chạy: py build.py --dir)
; Cài bản dạng thư mục: không phải giải nén mỗi lần mở → mở nhanh gấp đôi bản 1 file.
[Setup]
AppName=PDF-Read Pro
AppVersion=1.6.1
DefaultDirName={localappdata}\Programs\PDFReadPro
DefaultGroupName=PDF-Read Pro
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Setup_PDFReadPro_1.6.1
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\PDFReadPro.exe

[Files]
Source: "dist\PDFReadPro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF-Read Pro"; Filename: "{app}\PDFReadPro.exe"
Name: "{autodesktop}\PDF-Read Pro"; Filename: "{app}\PDFReadPro.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài màn hình"

[Run]
Filename: "{app}\PDFReadPro.exe"; Description: "Mở PDF-Read Pro"; Flags: nowait postinstall skipifsilent
