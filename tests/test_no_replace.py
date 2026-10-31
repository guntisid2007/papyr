"""Moving finished files into place never replaces another file: on this system's own disk, on real FAT32 and exFAT
volumes where macOS can mount them, and with several processes taking the same names at once."""
import multiprocessing
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from converter import ImageSettings, OutputFormat, convert_images
from utils.noreplace import rename_no_replace

pytestmark = pytest.mark.batch


def test_a_free_name_is_taken_in_one_move(tmp_path):
    (tmp_path / "a").write_bytes(b"mine")
    assert rename_no_replace(tmp_path / "a", tmp_path / "b") is True
    assert not (tmp_path / "a").exists() and (tmp_path / "b").read_bytes() == b"mine"


def test_a_taken_name_is_refused_and_both_files_stay(tmp_path):
    (tmp_path / "a").write_bytes(b"mine")
    (tmp_path / "b").write_bytes(b"theirs")
    with pytest.raises(FileExistsError):
        rename_no_replace(tmp_path / "a", tmp_path / "b")
    assert (tmp_path / "a").read_bytes() == b"mine" and (tmp_path / "b").read_bytes() == b"theirs"


@pytest.mark.skipif(sys.platform not in ("darwin", "win32") and not sys.platform.startswith("linux"),
                    reason="no atomic no-replace move is known for this system")
def test_this_system_has_an_atomic_no_replace_move(tmp_path):
    """macOS (APFS), Windows (NTFS), and Linux (ext4, tmpfs, btrfs, xfs) all support one on their usual disks. A
    False here means Papyr silently fell back to the slower copy on the system's own disk."""
    (tmp_path / "a").write_bytes(b"x")
    assert rename_no_replace(tmp_path / "a", tmp_path / "b") is True


def _listing(folder: Path) -> list[str]:
    """What is in folder, without the ._ files macOS itself adds beside each file on FAT and exFAT."""
    return sorted(p.name for p in folder.iterdir() if not p.name.startswith("._"))


def _check_race(results, out: Path, count: int) -> None:
    outputs = [Path(p) for _, written, _ in results for p in written]
    assert not [f for _, _, failures in results for f in failures]
    assert len(outputs) == len(set(outputs)) == count, outputs
    assert _listing(out) == sorted(p.name for p in outputs)
    for color, written, _ in results:
        expected = Image.new("RGB", (1, 1), color).getpixel((0, 0))
        for path in written:
            assert Image.open(path).convert("RGB").getpixel((5, 5)) == expected, f"{path} is not {color}"


def _png(path: Path, color) -> Path:
    Image.new("RGB", (32, 24), color).save(path)
    return path


def _convert_in_process(sources: list[str], out: str, queue) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    report = convert_images([Path(s) for s in sources], Path(out), ImageSettings(OutputFormat.PNG))
    color = Path(sources[0]).parent.name  # each worker's sources sit in a folder named after their colour
    queue.put((color, [str(p) for p in report.outputs], [(str(p), r) for p, r in report.failures]))


def test_processes_converting_the_same_names_at_once_never_replace_each_others_files(tmp_path):
    """Four Papyr processes write photo.png into one folder at the same moment, each from a different colour.
    Every output must survive under its own name with its own colour."""
    colors = ["red", "green", "blue", "yellow"]
    sources = []
    for color in colors:
        (tmp_path / color).mkdir()
        sources.append(_png(tmp_path / color / "photo.png", color))
    out = tmp_path / "out"
    out.mkdir()
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    workers = [context.Process(target=_convert_in_process, args=([str(s)] * 5, str(out), queue)) for s in sources]
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=120) for _ in workers]
    for worker in workers:
        worker.join(60)
    _check_race(results, out, 20)


_FILESYSTEMS = {"fat32": "MS-DOS FAT32", "exfat": "ExFAT"}


@pytest.fixture(scope="module", params=sorted(_FILESYSTEMS))
def removable_volume(request, tmp_path_factory):
    """A real FAT32 or exFAT volume, mounted from a disk image the way a USB stick is."""
    if sys.platform != "darwin" or not shutil.which("hdiutil"):
        pytest.skip("mounting FAT32 and exFAT disk images is done with macOS hdiutil")
    image = tmp_path_factory.mktemp("volumes") / f"{request.param}.dmg"
    created = subprocess.run(["hdiutil", "create", "-quiet", "-size", "40m", "-fs", _FILESYSTEMS[request.param],
                              "-volname", f"PAPYR{request.param.upper()}", "-ov", str(image)], capture_output=True)
    if created.returncode:
        pytest.skip(f"hdiutil could not create a {request.param} image: {created.stderr.decode()}")
    attached = subprocess.run(["hdiutil", "attach", "-nobrowse", "-noverify", str(image)], capture_output=True,
                              text=True)
    if attached.returncode:
        pytest.skip(f"hdiutil could not mount a {request.param} image: {attached.stderr}")
    mount = Path(attached.stdout.strip().splitlines()[-1].split("\t")[-1])
    try:
        yield request.param, mount
    finally:
        subprocess.run(["hdiutil", "detach", "-force", str(mount)], capture_output=True)


def test_a_removable_volume_gets_every_file_and_keeps_existing_ones(removable_volume, tmp_path):
    kind, mount = removable_volume
    out = mount / f"out-{tmp_path.name}"
    out.mkdir()
    (out / "page-2.png").write_bytes(b"the user's own file")
    frames = [Image.new("RGB", (24, 16), c) for c in ("red", "green", "blue")]
    frames[0].save(tmp_path / "page.tiff", save_all=True, append_images=frames[1:])
    (tmp_path / "page-2.tiff").write_bytes((tmp_path / "page.tiff").read_bytes())
    report = convert_images([tmp_path / "page.tiff", _png(tmp_path / "page-2.png", "red")], out,
                            ImageSettings(OutputFormat.PNG))
    assert not report.failures, f"{kind}: {report.failures}"
    assert [p.name for p in report.outputs] == ["page-page-1.png", "page-page-2.png", "page-page-3.png",
                                               "page-2 (1).png"], kind
    assert (out / "page-2.png").read_bytes() == b"the user's own file", kind
    assert not [p for p in out.iterdir() if ".papyr-" in p.name], kind


def test_a_removable_volume_refuses_to_move_onto_a_taken_name(removable_volume, tmp_path):
    kind, mount = removable_volume
    folder = mount / f"names-{tmp_path.name}"
    folder.mkdir()
    (folder / "a").write_bytes(b"mine")
    (folder / "b").write_bytes(b"theirs")
    with pytest.raises(FileExistsError):
        rename_no_replace(folder / "a", folder / "b")
    assert (folder / "b").read_bytes() == b"theirs", kind


def test_processes_racing_on_a_removable_volume_never_replace_each_others_files(removable_volume, tmp_path):
    """exFAT on macOS has neither an atomic no-replace move nor hard links, so this exercises the exclusive copy
    under real contention."""
    kind, mount = removable_volume
    out = mount / f"race-{tmp_path.name}"
    out.mkdir()
    colors = ["red", "blue", "green"]
    sources = []
    for color in colors:
        (tmp_path / color).mkdir()
        sources.append(_png(tmp_path / color / "photo.png", color))
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    workers = [context.Process(target=_convert_in_process, args=([str(s)] * 4, str(out), queue)) for s in sources]
    for worker in workers:
        worker.start()
    results = [queue.get(timeout=120) for _ in workers]
    for worker in workers:
        worker.join(60)
    _check_race(results, out, 12)
