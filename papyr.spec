# PyInstaller spec. Build with: pyinstaller papyr.spec
import os
import sys

from PyInstaller.utils.hooks import collect_dynamic_libs

sys.path.insert(0, os.path.join(SPECPATH, "src"))
from utils.app_info import APP_NAME, __version__ as VERSION  # noqa: E402

# Every file type Papyr reads, so Finder offers it in "Open With" and accepts drops on the Dock icon.
# Rank Alternate keeps Papyr from ever becoming the default app for these files.
INPUT_EXTENSIONS = ["avif", "bmp", "gif", "heic", "heif", "ipynb", "jpeg", "jpg", "pdf", "png", "tif", "tiff", "webp"]
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
                "CFBundleTypeName": "Images, PDFs, and notebooks",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["public.image", "com.adobe.pdf", "public.heic", "public.heif", "public.avif",
                                       "public.folder", "org.jupyter.ipynb"],
                "CFBundleTypeExtensions": INPUT_EXTENSIONS,
            }],
            # macOS ignores CFBundleTypeExtensions once LSItemContentTypes is set, and has no built-in type for
            # notebooks, so declare one to make .ipynb files match.
            "UTImportedTypeDeclarations": [{
                "UTTypeIdentifier": "org.jupyter.ipynb",
                "UTTypeDescription": "Jupyter Notebook",
                "UTTypeConformsTo": ["public.json"],
                "UTTypeTagSpecification": {"public.filename-extension": ["ipynb"]},
            }],
        },
    )
