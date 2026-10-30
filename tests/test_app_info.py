import re
import sys
from pathlib import Path

from converter import INPUT_EXTENSIONS
from utils.app_info import __version__
from utils.reveal import reveal_command

ROOT = Path(__file__).resolve().parent.parent


def macos_bundle(monkeypatch) -> dict:
    """Run papyr.spec as PyInstaller does on macOS, with the build steps stubbed, and return BUNDLE's arguments."""
    class Step:
        pure = scripts = binaries = datas = []

        def __init__(self, *args, **kwargs):
            pass

    bundle: dict = {}
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = ROOT / "papyr.spec"
    exec(compile(spec.read_text(), str(spec), "exec"),
         {"SPECPATH": str(ROOT), "Analysis": Step, "PYZ": Step, "EXE": Step, "COLLECT": Step,
          "BUNDLE": lambda *args, **kwargs: bundle.update(kwargs)})
    return bundle


def test_one_version_everywhere(monkeypatch):
    pyproject = re.search(r'^version = "(.+)"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE).group(1)
    plist = macos_bundle(monkeypatch)["info_plist"]
    assert __version__ == "2.1.0"
    assert pyproject == plist["CFBundleShortVersionString"] == plist["CFBundleVersion"] == __version__


def test_finder_can_open_every_input_type_without_papyr_becoming_the_default(monkeypatch):
    plist = macos_bundle(monkeypatch)["info_plist"]
    [document_type] = plist["CFBundleDocumentTypes"]
    assert document_type["CFBundleTypeRole"] == "Viewer"
    assert document_type["LSHandlerRank"] == "Alternate"
    assert {"public.image", "com.adobe.pdf", "public.heic", "public.heif", "public.avif",
            "public.folder"} <= set(document_type["LSItemContentTypes"])
    assert {f".{ext}" for ext in document_type["CFBundleTypeExtensions"]} == INPUT_EXTENSIONS
    notebook_types = {t["UTTypeIdentifier"]: t for t in plist["UTImportedTypeDeclarations"]}
    assert "org.jupyter.ipynb" in document_type["LSItemContentTypes"]
    assert notebook_types["org.jupyter.ipynb"]["UTTypeTagSpecification"]["public.filename-extension"] == ["ipynb"]


def test_reveal_selects_the_file_in_the_platform_file_manager():
    path = Path("/Users/me/Documents/Trip Photos.pdf")
    assert reveal_command(path, "darwin") == ["open", "-R", str(path)]
    assert reveal_command(path, "win32") == ["explorer", f"/select,{path}"]
    assert reveal_command(path, "linux") is None
