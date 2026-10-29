"""Build small real PDFs by hand: text pages (so tests can check text survives) and encrypted files."""
from pathlib import Path


def text_pdf(path: Path, pages: list[str], size: tuple[int, int] = (300, 200)) -> Path:
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        content = f"BT /F1 24 Tf 20 100 Td ({text}) Tj ET".encode()
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
