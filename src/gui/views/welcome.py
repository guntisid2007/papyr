"""The first screen: who Papyr is, what it does, and where to drop files."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ..icons import Icon, paint_mark
from ..theme import Type, current
from ..widgets import Button, Glyph, Kind, label, set_tone

TAGLINE = "Convert photos, PDFs, and notebooks to PDF or any image format."
FORMATS_LINE = "HEIC · JPEG · PNG · WebP · AVIF · TIFF · GIF · BMP · PDF · Jupyter notebooks"
PRIVACY_LINE = "Everything stays on this Mac. Nothing is uploaded."


class Mark(QWidget):
    def __init__(self, size: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAccessibleName("Papyr")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        paint_mark(painter, QRectF(self.rect()), current())


class DropTile(QWidget):
    """A dashed target that lights up while files are dragged over the window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def set_active(self, active: bool) -> None:
        self.active = active
        self.update()

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(theme.accent if self.active else theme.border_strong, 1.5, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.setBrush(theme.accent_wash if self.active else theme.surface)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 16, 16)


class WelcomeView(QWidget):
    browseFiles = Signal()
    browseFolder = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 20, 32, 12)
        outer.setSpacing(0)
        outer.addStretch(3)

        mark = Mark(56)
        outer.addWidget(mark, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addSpacing(14)
        title = label("Papyr", Type.DISPLAY)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)
        outer.addSpacing(4)
        tagline = label(TAGLINE, Type.BODY, "secondary", wrap=True)
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(tagline)
        outer.addStretch(2)

        row = QHBoxLayout()
        row.addStretch(1)
        self.tile = DropTile()
        self.tile.setMaximumWidth(500)
        self.tile.setMinimumWidth(360)
        row.addWidget(self.tile, 8)
        row.addStretch(1)
        outer.addLayout(row)
        column = QVBoxLayout(self.tile)
        column.setContentsMargins(24, 22, 24, 20)
        column.setSpacing(0)
        heading = label("Drop files or folders here", Type.HEADLINE)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(heading)
        column.addSpacing(14)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch()
        self.browse_button = Button("Browse Files…", Icon.PLUS, Kind.PRIMARY, height=32)
        self.browse_button.setToolTip("Choose photos, PDFs, or notebooks to convert (⌘O)")
        self.browse_button.clicked.connect(self.browseFiles)
        self.folder_button = Button("Add Folder…", Icon.FOLDER, height=32)
        self.folder_button.setToolTip("Add every supported file in a folder (⇧⌘O)")
        self.folder_button.clicked.connect(self.browseFolder)
        buttons.addWidget(self.browse_button)
        buttons.addWidget(self.folder_button)
        buttons.addStretch()
        column.addLayout(buttons)
        column.addSpacing(14)
        formats = label(FORMATS_LINE, Type.CAPTION, "secondary", wrap=True)
        formats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(formats)

        outer.addSpacing(10)
        self.notice = label("", Type.CAPTION, "danger", wrap=True)
        self.notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.notice.hide()
        outer.addWidget(self.notice)
        outer.addSpacing(4)
        privacy = QHBoxLayout()
        privacy.setSpacing(6)
        privacy.addStretch()
        privacy.addWidget(Glyph(Icon.LOCK, 13), 0, Qt.AlignmentFlag.AlignVCenter)
        privacy.addWidget(label(PRIVACY_LINE, Type.CAPTION, "secondary"))
        privacy.addStretch()
        outer.addLayout(privacy)
        outer.addStretch(3)

    def show_notice(self, notice: str, error: bool) -> None:
        self.notice.setText(notice)
        set_tone(self.notice, "danger" if error else "secondary")
        self.notice.setVisible(bool(notice))
