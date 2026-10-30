"""Build small real PDFs by hand: text pages (so tests can check text survives), coloured pages (so tests can tell
pages apart after they become images), and encrypted files.

fixtures/twelve-pages.pdf is colored_pdf(path, TWELVE_COLORS), committed so the GIF tests read a real file.
"""
from pathlib import Path

TWELVE_COLORS = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180),
                 (70, 240, 240), (240, 50, 230), (128, 128, 0), (0, 0, 128), (128, 0, 0), (170, 255, 195)]


def text_pdf(path: Path, pages: list[str], size: tuple[int, int] = (300, 200)) -> Path:
    return _pdf(path, [(f"BT /F1 24 Tf 20 100 Td ({text}) Tj ET", size) for text in pages])


def colored_pdf(path: Path, colors: list[tuple[int, int, int]], sizes: list[tuple[int, int]] | None = None) -> Path:
    """One page per colour, filled edge to edge with it and labelled with its page number."""
    sizes = sizes or [(612, 792)] * len(colors)
    pages = []
    for number, (color, (width, height)) in enumerate(zip(colors, sizes), start=1):
        r, g, b = (c / 255 for c in color)
        pages.append((f"{r:.3f} {g:.3f} {b:.3f} rg 0 0 {width} {height} re f "
                      f"0 0 0 rg BT /F1 36 Tf 20 20 Td (Page {number}) Tj ET", (width, height)))
    return _pdf(path, pages)


def _pdf(path: Path, pages: list[tuple[str, tuple[int, int]]]) -> Path:
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text, size in pages:
        content = text.encode()
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content.decode()}\nendstream")
        content_id = len(objects)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {size[0]} {size[1]}] "
                       f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>")
        kids.append(f"{len(objects)} 0 R")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))
    return path


def encrypted_pdf(path: Path) -> Path:
    import pypdf
    source = text_pdf(path.with_name("plain-for-encryption.pdf"), ["secret"])
    writer = pypdf.PdfWriter(clone_from=source)
    writer.encrypt("pw", algorithm="RC4-128")
    with open(path, "wb") as stream:
        writer.write(stream)
    return path
