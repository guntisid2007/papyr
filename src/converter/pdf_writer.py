"""Minimal streaming PDF writer: one image per page, written as each page arrives."""

from dataclasses import dataclass
from typing import BinaryIO

from .layout import Placement


@dataclass(frozen=True)
class EncodedImage:
    data: bytes
    filter: str
    width: int
    height: int
    color_space: str


def _num(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


class PdfWriter:
    def __init__(self, stream: BinaryIO):
        self._stream = stream
        self._offsets: dict[int, int] = {}
        self._page_ids: list[int] = []
        self._next_id = 3  # 1 is the catalog, 2 the page tree
        stream.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")

    def _write_object(self, obj_id: int, body: bytes, stream_data: bytes | None = None) -> None:
        self._offsets[obj_id] = self._stream.tell()
        self._stream.write(f"{obj_id} 0 obj\n".encode() + body)
        if stream_data is not None:
            self._stream.write(b"\nstream\n" + stream_data + b"\nendstream")
        self._stream.write(b"\nendobj\n")

    def _allocate(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def add_page(self, image: EncodedImage, placement: Placement) -> None:
        image_id, content_id, page_id = self._allocate(), self._allocate(), self._allocate()
        self._write_object(image_id, (
            f"<< /Type /XObject /Subtype /Image /Width {image.width} /Height {image.height}"
            f" /ColorSpace /{image.color_space} /BitsPerComponent 8 /Filter /{image.filter}"
            f" /Length {len(image.data)} >>").encode(), image.data)
        content = (f"q {_num(placement.width)} 0 0 {_num(placement.height)} "
                   f"{_num(placement.x)} {_num(placement.y)} cm /Im0 Do Q").encode()
        self._write_object(content_id, f"<< /Length {len(content)} >>".encode(), content)
        self._write_object(page_id, (
            f"<< /Type /Page /Parent 2 0 R"
            f" /MediaBox [0 0 {_num(placement.page_width)} {_num(placement.page_height)}]"
            f" /Resources << /XObject << /Im0 {image_id} 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode())
        self._page_ids.append(page_id)

    @property
    def page_count(self) -> int:
        return len(self._page_ids)

    def close(self) -> None:
        if not self._page_ids:
            raise ValueError("A PDF needs at least one page")
        kids = " ".join(f"{i} 0 R" for i in self._page_ids)
        self._write_object(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(self._page_ids)} >>".encode())
        self._write_object(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        info_id = self._allocate()
        self._write_object(info_id, b"<< /Producer (HEIC to PDF) >>")

        xref_offset = self._stream.tell()
        lines = [f"xref\n0 {self._next_id}\n", "0000000000 65535 f \n"]
        lines += [f"{self._offsets[i]:010d} 00000 n \n" for i in range(1, self._next_id)]
        lines.append(f"trailer\n<< /Size {self._next_id} /Root 1 0 R /Info {info_id} 0 R >>\n"
                     f"startxref\n{xref_offset}\n%%EOF\n")
        self._stream.write("".join(lines).encode())
