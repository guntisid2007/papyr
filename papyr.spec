# PyInstaller spec. Build with: pyinstaller papyr.spec
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

APP_NAME = "Papyr"
VERSION = "2.0.0"
icon = "assets/icon.icns" if sys.platform == "darwin" else "assets/icon.ico"

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=collect_dynamic_libs("pillow_heif"),
    datas=[("assets/icon.png", "assets")],
    hiddenimports=["pillow_heif"],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtSql",
              "PySide6.QtTest", "PySide6.QtOpenGL", "PySide6.QtPdf", "PySide6.QtSvg"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP_NAME, icon=icon,
          console=False, upx=False, target_arch=None)
coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME, upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier="io.github.guntisid2007.papyr",
        version=VERSION,
        info_plist={
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.4",
            "NSRequiresAquaSystemAppearance": False,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Image or PDF",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["public.heic", "public.heif", "public.jpeg", "public.png", "org.webmproject.webp",
                                       "public.avif", "public.tiff", "com.microsoft.bmp", "com.compuserve.gif",
                                       "com.adobe.pdf"],
            }],
        },
    )
