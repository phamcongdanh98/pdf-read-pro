r"""Đóng gói PDF-Read Pro.
    py build.py         → dist\PDFReadPro.exe          (1 file, portable – mỗi lần mở phải giải nén)
    py build.py --dir   → dist\PDFReadPro\PDFReadPro.exe (thư mục, mở nhanh hơn – dùng cho bộ cài installer.iss)

Exe onefile giải nén toàn bộ nội dung mỗi lần mở → càng gọn càng mở nhanh. Ngoài --exclude-module, bản build
lọc bỏ DLL / plugin Qt mà app không dùng (app chỉ dùng QtCore, QtGui, QtWidgets) – xem DROP_* bên dưới.

Giảm báo nhầm virus (VirusTotal: vài phần mềm diệt virus dùng AI/heuristic hay nghi exe PyInstaller 1 file):
- gắn thông tin phiên bản (Version Info: tên sản phẩm, mô tả, bản quyền) – exe "vô danh" bị nghi nhiều hơn;
- không nén UPX;
- --dir còn tạo dist\PDFReadPro_<phiên bản>_portable.zip (bản thư mục: không tự giải nén vào %TEMP% → ít bị nghi
  hơn bản 1 file) – nên dùng bản này / bộ cài để phát cho người khác."""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(ROOT, "assets", "app.ico")
BUILD = os.path.join(ROOT, "build")
sys.path.insert(0, ROOT)
from pdfread_pro.paths import APP_NAME, APP_VERSION  # noqa: E402

AUTHOR = "Danh Pham"
VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('042a04b0', [
      StringStruct('CompanyName', {author!r}),
      StringStruct('FileDescription', {name!r} + ' - Đọc, kiểm tra và xử lý PDF hồ sơ số hoá'),
      StringStruct('FileVersion', {ver!r}),
      StringStruct('InternalName', 'PDFReadPro'),
      StringStruct('LegalCopyright', '© 2026 ' + {author!r}),
      StringStruct('OriginalFilename', 'PDFReadPro.exe'),
      StringStruct('ProductName', {name!r}),
      StringStruct('ProductVersion', {ver!r})])]),
    VarFileInfo([VarStruct('Translation', [0x042a, 1200])])
  ]
)
"""

EXCLUDE_MODULES = [
    "tkinter", "matplotlib", "numpy", "lxml", "PIL._avif", "PIL.AvifImagePlugin",
    "PySide6.QtNetwork", "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtPdf", "PySide6.QtOpenGL", "PySide6.QtSvg",
]
# Plugin Qt kéo theo Qt6Quick / Qt6Qml / Qt6Network / Qt6Pdf (bàn phím ảo, đọc ảnh PDF, TLS, cảm ứng, mạng)
# và chính các DLL đó; opengl32sw = bộ vẽ OpenGL phần mềm (widget không cần); bản dịch Qt (app không dùng).
DROP_PREFIX = (
    "PySide6/plugins/platforminputcontexts/", "PySide6/plugins/tls/", "PySide6/plugins/networkinformation/",
    "PySide6/plugins/generic/", "PySide6/plugins/imageformats/qpdf", "PySide6/plugins/platforms/qdirect2d",
    "PySide6/plugins/platforms/qminimal", "PySide6/translations/",
    "PySide6/opengl32sw", "PySide6/Qt6Quick", "PySide6/Qt6Qml", "PySide6/Qt6Network", "PySide6/Qt6Pdf",
    "PySide6/Qt6OpenGL", "PySide6/Qt6VirtualKeyboard", "PySide6/QtNetwork",
    "libcrypto-3-x64", "libssl-3-x64",                     # OpenSSL của plugin TLS Qt (Python dùng libcrypto-3.dll)
)

SPEC = r'''# -*- mode: python -*-  (sinh tự động bởi build.py)
DROP = {drop!r}

def keep(entry):
    name = entry[0].replace("\\", "/")
    return not name.startswith(DROP)

_wd, _wb, _wh = collect_all("winrt")                       # Windows OCR: tự đọc số trang
a = Analysis([{main!r}], pathex=[{root!r}], binaries=_wb,
             datas=[({icon!r}, "assets"), ({data!r}, "pdfread_pro/data")] + _wd,
             hiddenimports=["pikepdf", "pymupdf"] + _wh,
             excludes={excludes!r}, noarchive=False)
a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]
pyz = PYZ(a.pure)
if {onedir!r}:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PDFReadPro", icon={icon!r}, console=False, upx=False,
              version={version!r})
    coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="PDFReadPro")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="PDFReadPro", icon={icon!r},
              console=False, upx=False, runtime_tmpdir=None, version={version!r})
'''


def make_icon():
    from PIL import Image, ImageDraw, ImageFont
    os.makedirs(os.path.dirname(ICON), exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, 248, 248), radius=48, fill=(37, 99, 235, 255))
    d.rounded_rectangle((56, 36, 200, 220), radius=14, fill=(255, 255, 255, 255))
    d.polygon([(160, 36), (200, 76), (160, 76)], fill=(203, 213, 225, 255))
    try:
        font = ImageFont.truetype("arialbd.ttf", 56)
    except OSError:
        font = ImageFont.load_default()
    d.text((128, 130), "PDF", fill=(220, 38, 38, 255), font=font, anchor="mm")
    d.ellipse((150, 150, 240, 240), fill=(22, 163, 74, 255), outline=(255, 255, 255, 255), width=8)   # dấu ✔ kiểm tra
    d.line([(172, 196), (190, 214), (220, 176)], fill=(255, 255, 255, 255), width=14, joint="curve")
    img.save(ICON, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")    # console cp1252 không in được chữ có dấu
    make_icon()
    os.makedirs(BUILD, exist_ok=True)
    spec = os.path.join(BUILD, "PDFReadPro.spec")
    version = os.path.join(BUILD, "version_info.txt")
    nums = tuple(int(x) for x in APP_VERSION.split(".")) + (0,) * (4 - len(APP_VERSION.split(".")))
    with open(version, "w", encoding="utf-8") as fh:
        fh.write(VERSION_INFO.format(t=nums, ver=APP_VERSION, name=APP_NAME, author=AUTHOR))
    onedir = "--dir" in sys.argv
    with open(spec, "w", encoding="utf-8") as fh:
        fh.write("from PyInstaller.utils.hooks import collect_all\n" + SPEC.format(
            drop=DROP_PREFIX, main=os.path.join(ROOT, "main.py"), root=ROOT, icon=ICON,
            data=os.path.join(ROOT, "pdfread_pro", "data"), excludes=EXCLUDE_MODULES, onedir=onedir,
            version=version))
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--distpath", os.path.join(ROOT, "dist"), "--workpath", BUILD, spec]
    rc = subprocess.call(cmd, cwd=ROOT)
    if rc == 0 and onedir:
        base = os.path.join(ROOT, "dist", f"PDFReadPro_{APP_VERSION}_portable")
        shutil.make_archive(base, "zip", os.path.join(ROOT, "dist"), "PDFReadPro")
        print("Đã tạo", base + ".zip")
    sys.exit(rc)


if __name__ == "__main__":
    main()
