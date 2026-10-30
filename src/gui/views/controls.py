"""The command dock at the bottom of the window: the output format, the settings that format uses, where files
are saved, and Convert. While converting, the same dock shows real progress and Cancel."""
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QDoubleSpinBox, QHBoxLayout, QLineEdit, QMenu, QSizePolicy,
                               QSlider, QStackedWidget, QVBoxLayout, QWidget)

from converter import GifResolution, OutputFormat, PageSize
from utils.files import FolderProblem

from ..icons import Icon, paint_icon
from ..model import FRAME_MS_CHOICES, FRAME_MS_RANGE, MARGIN_RANGE, PAGE_SIZES, PDF_DPI_CHOICES, PLAYS_RANGE, Control, \
    Converting, GifMode, Options, QueueSummary, controls_for, plural, round_frame_ms
from ..theme import RADIUS_SURFACE, Type, current, font
from ..widgets import Button, Chip, ElidedLabel, Kind, Popover, Segment, Surface, Toggle, Track, label, shortcut_text

FEATURED = (OutputFormat.PDF, OutputFormat.JPEG, OutputFormat.PNG, OutputFormat.WEBP, OutputFormat.HEIC)
PAGE_DETAILS = {PageSize.A4: "210 × 297 mm", PageSize.LETTER: "8.5 × 11 in", PageSize.ORIGINAL: "Each image's own size"}
PAGE_NOTE = "Wide photos get landscape pages. PDFs keep their own pages and text."
QUALITY_NOTE = "Higher quality makes larger files."
DPI_NOTE = "For pages of PDFs and notebooks turned into images."
NAME_NOTE = "Pages follow the order of the list."
GIF_MODE_NOTE = "Combined frames follow the order of the list."
ANIMATION_NOTE = "Pages of different sizes are centred on one frame size."
KEEPS_ALPHA_NOTE = "Transparency is preserved."
LOSES_ALPHA_NOTE = "Transparent areas become white."


def display_path(path: Path) -> str:
    home = Path.home()
    if sys.platform == "win32" or not path.is_relative_to(home) or path == home:
        return str(path)
    return f"~/{path.relative_to(home).as_posix()}"


class FormatBar(Track):
    """The output format as a row of segments. Rarer formats sit behind the last segment's menu."""

    chosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Convert to")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self.buttons: dict[OutputFormat, Segment] = {}
        for fmt in FEATURED:
            button = Segment(fmt.label)
            button.setToolTip(f"Convert to {fmt.label}")
            button.clicked.connect(lambda _=False, f=fmt: self.chosen.emit(f))
            self._group.addButton(button)
            self.buttons[fmt] = button
            row.addWidget(button)
        self.more = Segment("More", menu=True)
        self.more.setToolTip("More formats")
        self.more.setAccessibleName("More formats")
        self._group.addButton(self.more)
        self.menu = QMenu(self)
        for fmt in OutputFormat:
            if fmt not in FEATURED:
                action = self.menu.addAction(fmt.label)
                action.setCheckable(True)
                action.setData(fmt)
                action.triggered.connect(lambda _=False, f=fmt: self.chosen.emit(f))
        self.more.clicked.connect(self._open_menu)
        row.addWidget(self.more)

    def _open_menu(self) -> None:
        self.show_format(self._current)  # a click checks the segment before the user has chosen anything
        self.menu.popup(self.more.mapToGlobal(self.more.rect().bottomLeft()))

    def show_format(self, fmt: OutputFormat) -> None:
        self._current = fmt
        featured = fmt in FEATURED
        (self.buttons[fmt] if featured else self.more).setChecked(True)
        self.more.set_text("More" if featured else fmt.label)
        self.more.setAccessibleName("More formats" if featured else f"{fmt.label}, more formats")
        for action in self.menu.actions():
            action.setChecked(action.data() is fmt)


class Choice(QAbstractButton):
    """One option in a popover list: a name, a detail, and a check when chosen."""

    def __init__(self, text: str, detail: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setAccessibleName(text)
        self.setAccessibleDescription(detail)
        self._detail = detail
        self.setCheckable(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(font(Type.BODY_MEDIUM))
        detail = QFontMetrics(font(Type.CAPTION)).horizontalAdvance(self._detail)
        return QSize(max(metrics.horizontalAdvance(self.text()), 72) + detail + 64, 30)

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self.isChecked() or self.underMouse() or self.hasFocus():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.selected if self.isChecked() else theme.hover)
            painter.drawRoundedRect(rect, 7, 7)
        painter.setFont(font(Type.BODY_MEDIUM))
        painter.setPen(theme.accent_text if self.isChecked() else theme.text)
        name_width = max(QFontMetrics(font(Type.BODY_MEDIUM)).horizontalAdvance(self.text()), 72)
        painter.drawText(rect.adjusted(10, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, self.text())
        painter.setFont(font(Type.CAPTION))
        painter.setPen(theme.text_secondary)
        painter.drawText(rect.adjusted(10 + name_width + 14, 0, -28, 0), Qt.AlignmentFlag.AlignVCenter, self._detail)
        if self.isChecked():
            paint_icon(painter, Icon.CHECK, QRectF(rect.right() - 24, rect.center().y() - 7, 14, 14),
                       theme.accent_text, 1.8)


def merged_name_label(options: Options) -> str:
    return "Combined GIF name" if options.format is OutputFormat.GIF else "Merged PDF name"


def _section(text: str):
    return label(text.upper(), Type.LABEL, "secondary")


def _note(text: str = ""):
    note = label(text, Type.CAPTION, "secondary", wrap=True)
    note.setMaximumWidth(260)
    return note


class PagePopover(Popover):
    """Page size and margins, the two settings that lay out each PDF page."""

    def __init__(self, parent, on_page, on_margin):
        super().__init__(parent)
        self.body.addWidget(_section("Page size"))
        group = QButtonGroup(self)
        self.choices: dict[PageSize, Choice] = {}
        for size in PAGE_SIZES:
            choice = Choice(size.label, PAGE_DETAILS[size])
            choice.clicked.connect(lambda _=False, s=size: on_page(s))
            group.addButton(choice)
            self.choices[size] = choice
            self.body.addWidget(choice)
        self.body.addSpacing(4)
        self.body.addWidget(_section("Margins"))
        row = QHBoxLayout()
        row.setSpacing(6)
        self.margin = QDoubleSpinBox()
        self.margin.setAccessibleName("Margins")
        self.margin.setRange(*MARGIN_RANGE)
        self.margin.setDecimals(0)
        self.margin.setSuffix(" mm")
        self.margin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.margin.setFixedWidth(88)
        self.margin.valueChanged.connect(on_margin)
        self.minus = Button("−", height=28)
        self.minus.setToolTip("Smaller margins")
        self.minus.setAccessibleName("Smaller margins")
        self.minus.clicked.connect(lambda: self.margin.stepDown())
        self.plus = Button("", Icon.PLUS, height=28)
        self.plus.setToolTip("Larger margins")
        self.plus.setAccessibleName("Larger margins")
        self.plus.clicked.connect(lambda: self.margin.stepUp())
        for widget in (self.minus, self.margin, self.plus):
            row.addWidget(widget)
        row.addStretch()
        self.body.addLayout(row)
        self.body.addWidget(_note(PAGE_NOTE))

    def show_options(self, options: Options, queue: QueueSummary) -> None:
        self.choices[options.page_size].setChecked(True)
        self.margin.blockSignals(True)
        self.margin.setValue(options.margin_mm)
        self.margin.blockSignals(False)


class QualityPopover(Popover):
    def __init__(self, parent, on_quality):
        super().__init__(parent)
        top = QHBoxLayout()
        top.addWidget(_section("Quality"))
        top.addStretch()
        self.value = label("", Type.BODY_STRONG)
        top.addWidget(self.value)
        self.body.addLayout(top)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setPageStep(10)
        self.slider.setAccessibleName("Quality")
        self.slider.setMinimumWidth(220)
        self.slider.valueChanged.connect(lambda value: self.value.setText(f"{value}%"))
        self.slider.valueChanged.connect(on_quality)
        self.body.addWidget(self.slider)
        self.note = _note(QUALITY_NOTE)
        self.body.addWidget(self.note)

    def show_options(self, options: Options, queue: QueueSummary) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(options.quality)
        self.slider.blockSignals(False)
        self.value.setText(f"{options.quality}%")


class ResolutionPopover(Popover):
    def __init__(self, parent, on_dpi):
        super().__init__(parent)
        self.body.addWidget(_section("PDF page resolution"))
        group = QButtonGroup(self)
        self.choices: dict[int, Choice] = {}
        for dpi in PDF_DPI_CHOICES:
            choice = Choice(f"{dpi} DPI", {100: "Smallest files", 300: "Sharpest"}.get(dpi, ""))
            choice.clicked.connect(lambda _=False, d=dpi: on_dpi(d))
            group.addButton(choice)
            self.choices[dpi] = choice
            self.body.addWidget(choice)
        self.body.addWidget(_note(DPI_NOTE))

    def show_options(self, options: Options, queue: QueueSummary) -> None:
        self.choices[options.pdf_dpi].setChecked(True)


class NamePopover(Popover):
    def __init__(self, parent, on_name):
        super().__init__(parent)
        self.title = _section("Merged PDF name")
        self.body.addWidget(self.title)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Combined")
        self.edit.setAccessibleName("Merged PDF name")
        self.edit.setAcceptDrops(False)  # dropped files go to the window and get added
        self.edit.setMinimumWidth(200)
        self.edit.textEdited.connect(on_name)
        self.edit.returnPressed.connect(self.close)
        row.addWidget(self.edit)
        self.extension = label(".pdf", Type.BODY, "secondary")
        row.addWidget(self.extension)
        self.body.addLayout(row)
        self.body.addWidget(_note(NAME_NOTE))

    def show_options(self, options: Options, queue: QueueSummary) -> None:
        name = merged_name_label(options)
        self.title.setText(name.upper())
        self.edit.setAccessibleName(name)
        self.extension.setText(".gif" if options.format is OutputFormat.GIF else ".pdf")
        if self.edit.text() != options.merged_name:
            self.edit.setText(options.merged_name)


def _number(range_: tuple[int, int], suffix: str, name: str, on_value) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setAccessibleName(name)
    spin.setRange(*range_)
    spin.setDecimals(0)
    spin.setSuffix(suffix)
    spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    spin.setFixedWidth(96)
    spin.setKeyboardTracking(False)  # report the number once it is typed, not after every digit
    spin.valueChanged.connect(lambda value: on_value(int(value)))
    return spin


def _set_quietly(spin: QDoubleSpinBox, value: int) -> None:
    spin.blockSignals(True)
    spin.setValue(value)
    spin.blockSignals(False)


def frame_ms_text(ms: int) -> str:
    return f"{ms / 1000:g} s" if ms % 100 == 0 else f"{ms} ms"


def plays_text(plays: int) -> str:
    return {0: "Loops", 1: "Plays once"}.get(plays, f"Plays {plays}×")


class GifModePopover(Popover):
    """Whether pages and files become animations or still GIFs."""

    def __init__(self, parent, on_mode):
        super().__init__(parent)
        self.body.addWidget(_section("Animation"))
        group = QButtonGroup(self)
        self.choices: dict[GifMode, Choice] = {}
        for mode in GifMode:
            choice = Choice(mode.label, mode.detail)
            choice.clicked.connect(lambda _=False, m=mode: on_mode(m))
            group.addButton(choice)
            self.choices[mode] = choice
            self.body.addWidget(choice)
        self.body.addWidget(_note(GIF_MODE_NOTE))

    def show_options(self, options: Options, queue: QueueSummary) -> None:
        self.choices[GifMode.COMBINE].setEnabled(queue.count >= 2)
        self.choices[options.gif_mode].setChecked(True)


class AnimationPopover(Popover):
    """How long each frame shows, how many times the animation plays, and how large its frames are."""

    def __init__(self, parent, on_frame_ms, on_plays, on_resolution):
        super().__init__(parent)
        self.body.addWidget(_section("Frame duration"))
        self.durations: dict[int, Choice] = {}
        for ms in FRAME_MS_CHOICES:
            choice = Choice(f"{ms} ms", {1000: "Default"}.get(ms, ""))
            choice.clicked.connect(lambda _=False, m=ms: on_frame_ms(m))
            self.durations[ms] = choice
            self.body.addWidget(choice)
        self.custom_ms = _number(FRAME_MS_RANGE, " ms", "Custom frame duration",
                                 lambda ms: on_frame_ms(round_frame_ms(ms)))
        self.custom_ms.setSingleStep(10)
        self.custom_ms_choice = Choice("Custom")
        self.custom_ms_choice.clicked.connect(lambda: on_frame_ms(round_frame_ms(self.custom_ms.value())))
        self.body.addLayout(self._row(self.custom_ms_choice, self.custom_ms))

        self.body.addSpacing(4)
        self.body.addWidget(_section("Looping"))
        self.loop_forever = Choice("Loop forever", "Default")
        self.loop_forever.clicked.connect(lambda: on_plays(0))
        self.play_once = Choice("Play once")
        self.play_once.clicked.connect(lambda: on_plays(1))
        for choice in (self.loop_forever, self.play_once):
            self.body.addWidget(choice)
        self.custom_plays = _number(PLAYS_RANGE, " times", "Number of plays", on_plays)
        self.custom_plays_choice = Choice("Play")
        self.custom_plays_choice.clicked.connect(lambda: on_plays(int(self.custom_plays.value())))
        self.body.addLayout(self._row(self.custom_plays_choice, self.custom_plays))

        self.body.addSpacing(4)
        self.body.addWidget(_section("Frame size"))
        group = QButtonGroup(self)
        self.sizes: dict[GifResolution, Choice] = {}
        for resolution in GifResolution:
            choice = Choice(resolution.label, f"Up to {resolution.long_side} px")
            choice.clicked.connect(lambda _=False, r=resolution: on_resolution(r))
            group.addButton(choice)
            self.sizes[resolution] = choice
            self.body.addWidget(choice)
        self.body.addWidget(_note(ANIMATION_NOTE))

    @staticmethod
    def _row(choice: Choice, spin: QDoubleSpinBox) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(choice, 1)
        row.addWidget(spin)
        return row

    def show_options(self, options: Options, queue: QueueSummary) -> None:
        for ms, choice in self.durations.items():
            choice.setChecked(ms == options.frame_ms)
        self.custom_ms_choice.setChecked(options.frame_ms not in FRAME_MS_CHOICES)
        _set_quietly(self.custom_ms, options.frame_ms)
        self.loop_forever.setChecked(options.plays == 0)
        self.play_once.setChecked(options.plays == 1)
        self.custom_plays_choice.setChecked(options.plays >= PLAYS_RANGE[0])
        _set_quietly(self.custom_plays, max(options.plays, PLAYS_RANGE[0]))
        self.sizes[options.gif_resolution].setChecked(True)


class DestinationChip(Chip):
    """Where converted files go. A click opens the system folder picker."""

    def __init__(self, parent=None):
        super().__init__("", Icon.FOLDER, menu=False, parent=parent)
        self.problem: FolderProblem | None = None

    def show_folder(self, folder: Path, problem: FolderProblem | None) -> None:
        self.problem = problem
        self._icon = Icon.WARNING if problem else Icon.FOLDER
        self.set_value(problem.short if problem else display_path(folder))
        self.setToolTip(f"{folder}\n{problem.explanation}" if problem else f"Save to {folder}\nClick to change")
        self.setAccessibleName(f"Save to {folder}" + (f". {problem.short}" if problem else ""))

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(min(hint.width(), 280), hint.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(96, self._height)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.problem is not None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            theme = current()
            painter.setPen(theme.warning)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)


class ProgressBar(QWidget):
    """A slim bar that fills as files finish."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Conversion progress")
        self.setFixedHeight(6)
        self._fraction = 0.0

    def set_fraction(self, fraction: float) -> None:
        self._fraction = min(max(fraction, 0.0), 1.0)
        self.update()

    def fraction(self) -> float:
        return self._fraction

    def paintEvent(self, event) -> None:
        theme = current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.control)
        rect = QRectF(self.rect())
        painter.drawRoundedRect(rect, 3, 3)
        if self._fraction > 0:
            painter.setBrush(theme.accent)
            painter.drawRoundedRect(QRectF(rect.left(), rect.top(), max(rect.width() * self._fraction, 6),
                                           rect.height()), 3, 3)


class Dock(Surface):
    """Everything you act with, in one raised panel. It edits a copy of Options and reports each change."""

    edited = Signal(object)  # Options
    convertRequested = Signal()
    cancelRequested = Signal()
    destinationRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(RADIUS_SURFACE, "raised", parent=parent)
        self.setObjectName("Dock")
        self._options = Options()
        self._queue = QueueSummary()
        self._pages = QStackedWidget()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.addWidget(self._pages)
        self._pages.addWidget(self._build_controls())
        self._pages.addWidget(self._build_progress())

    def _build_controls(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        self.options_row = QWidget()
        options = QHBoxLayout(self.options_row)
        options.setContentsMargins(0, 0, 0, 0)
        options.setSpacing(8)
        self.merge = Toggle("Merge into one PDF")
        self.merge.setToolTip("Put every file into one PDF, in list order")
        self.merge.toggled.connect(lambda on: self._edit(merge=on))
        self.name_chip = Chip("", Icon.DOCUMENT)
        self.name_chip.setAccessibleName("Merged PDF name")
        self.name_chip.setToolTip("Name the merged PDF")
        self.page_chip = Chip("Page")
        self.page_chip.setToolTip("Page size and margins")
        self.quality_chip = Chip("Quality")
        self.quality_chip.setToolTip("Image quality")
        self.dpi_chip = Chip("PDF pages")
        self.dpi_chip.setToolTip("Resolution of images made from PDF and notebook pages")
        self.gif_mode_chip = Chip()
        self.gif_mode_chip.setAccessibleName("GIF animation")
        self.gif_mode_chip.setToolTip("Animate pages, combine files, or save still GIFs")
        self.animation_chip = Chip("Frames")
        self.animation_chip.setToolTip("Frame duration, looping, and frame size")
        self.note = ElidedLabel(style=Type.CAPTION)
        self.note.setProperty("tone", "secondary")
        self.note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)  # chips keep their room
        self._chips: dict[Control, QWidget] = {Control.MERGE: self.merge, Control.MERGED_NAME: self.name_chip,
                                               Control.PAGE_SIZE: self.page_chip, Control.MARGINS: self.page_chip,
                                               Control.QUALITY: self.quality_chip, Control.PDF_DPI: self.dpi_chip,
                                               Control.GIF_MODE: self.gif_mode_chip,
                                               Control.FRAME_MS: self.animation_chip, Control.PLAYS: self.animation_chip,
                                               Control.GIF_RESOLUTION: self.animation_chip}
        for widget in (self.merge, self.gif_mode_chip, self.name_chip, self.page_chip, self.quality_chip,
                       self.animation_chip, self.dpi_chip):
            options.addWidget(widget)
        options.addWidget(self.note, 1)
        options.addStretch(0)  # takes the spare room only while the note is hidden
        self.destination = DestinationChip()
        self.destination.clicked.connect(self.destinationRequested)
        options.addWidget(self.destination)
        column.addWidget(self.options_row)

        self.page_popover = PagePopover(self, lambda size: self._edit(page_size=size),
                                        lambda mm: self._edit(margin_mm=mm))
        self.quality_popover = QualityPopover(self, lambda value: self._edit(quality=value))
        self.dpi_popover = ResolutionPopover(self, lambda dpi: self._edit(pdf_dpi=dpi))
        self.name_popover = NamePopover(self, lambda text: self._edit(merged_name=text))
        self.gif_mode_popover = GifModePopover(self, lambda mode: self._edit(gif_mode=mode))
        self.animation_popover = AnimationPopover(self, lambda ms: self._edit(frame_ms=ms),
                                                  lambda plays: self._edit(plays=plays),
                                                  lambda resolution: self._edit(gif_resolution=resolution))
        self._popovers = ((self.page_chip, self.page_popover), (self.quality_chip, self.quality_popover),
                          (self.dpi_chip, self.dpi_popover), (self.name_chip, self.name_popover),
                          (self.gif_mode_chip, self.gif_mode_popover), (self.animation_chip, self.animation_popover))
        for chip, popover in self._popovers:
            chip.clicked.connect(lambda _=False, c=chip, p=popover: self._open(p, c))

        self.action_row = QHBoxLayout()
        self.action_row.setSpacing(10)
        self.caption = label("Convert to", Type.BODY, "secondary")
        self.action_row.addWidget(self.caption)
        self.formats = FormatBar()
        self.formats.chosen.connect(lambda fmt: self._edit(format=fmt))
        self.action_row.addWidget(self.formats)
        self.action_row.addStretch(1)
        self.convert_button = Button("Convert", kind=Kind.PRIMARY, hint=shortcut_text("Ctrl+Return"), height=32)
        self.convert_button.clicked.connect(self.convertRequested)
        self.action_row.addWidget(self.convert_button)
        column.addLayout(self.action_row)
        return page

    def _build_progress(self) -> QWidget:
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.progress_title = label("", Type.BODY_STRONG)
        self.progress_file = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self.progress_file.setProperty("tone", "secondary")
        self.progress_remaining = label("", Type.BODY, "secondary")
        top.addWidget(self.progress_title)
        top.addWidget(self.progress_file, 1)
        top.addWidget(self.progress_remaining)
        column.addLayout(top)
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.progress = ProgressBar()
        bottom.addWidget(self.progress, 1, Qt.AlignmentFlag.AlignVCenter)
        self.cancel_button = Button("Cancel", kind=Kind.SECONDARY, hint="esc", height=32)
        self.cancel_button.setToolTip("Stop after the current file. Finished files are kept.")
        self.cancel_button.clicked.connect(self.cancelRequested)
        bottom.addWidget(self.cancel_button)
        column.addLayout(bottom)
        return page

    def _open(self, popover: Popover, chip: QWidget) -> None:
        popover.show_options(self._options, self._queue)
        popover.open_at(chip)

    def _edit(self, **changes) -> None:
        options = self._options.with_(**changes)
        if options != self._options:
            self._options = options
            self.edited.emit(options)

    # What the window tells it

    def show_welcome(self, options: Options) -> None:
        self._show(options, QueueSummary(), compact=True)

    def show_workspace(self, options: Options, queue: QueueSummary, blocker: str | None) -> None:
        self._show(options, queue, compact=False)
        self.convert_button.set_text(f"Convert to {options.format.label}")
        self.convert_button.setEnabled(blocker is None)
        files = plural(queue.count, "file")
        self.convert_button.setToolTip(blocker or f"Convert {files} to {options.format.label} "
                                                  f"({shortcut_text('Ctrl+Return')})")

    def _show(self, options: Options, queue: QueueSummary, compact: bool) -> None:
        self._options, self._queue = options, queue
        self._pages.setCurrentIndex(0)
        shown = {self._chips[control] for control in controls_for(options, queue)}
        for widget in set(self._chips.values()):
            widget.setVisible(widget in shown)
        self.merge.blockSignals(True)
        self.merge.setChecked(options.merge)
        self.merge.blockSignals(False)
        self.name_chip.set_value(options.merged_file_name())
        self.name_chip.setAccessibleName(merged_name_label(options))
        self.name_chip.setToolTip(f"Name the {'combined GIF' if options.format is OutputFormat.GIF else 'merged PDF'}")
        self.gif_mode_chip.set_value(options.gif_mode.short)
        self.animation_chip.set_value(f"{frame_ms_text(options.frame_ms)} · {plays_text(options.plays)}")
        self.animation_chip.setToolTip(f"Frame duration, looping, and frame size ({options.gif_resolution.label})")
        page = "Original" if options.page_size is PageSize.ORIGINAL else options.page_size.label
        self.page_chip.set_value(f"{page} · {options.margin_mm:g} mm")
        self.quality_chip.set_value(f"{options.quality}%")
        self.dpi_chip.set_value(f"{options.pdf_dpi} DPI")
        if options.format is not OutputFormat.PDF:
            self.note.setText(KEEPS_ALPHA_NOTE if options.format.keeps_alpha else LOSES_ALPHA_NOTE)
        self.note.setVisible(options.format is not OutputFormat.PDF)
        for _, popover in self._popovers:
            if popover.isVisible():
                popover.show_options(options, queue)
        self.formats.show_format(options.format)
        self.options_row.setVisible(not compact)
        self.caption.setVisible(compact)
        self.convert_button.setVisible(not compact)
        self._place_destination(self.action_row if compact else self.options_row.layout())

    def _place_destination(self, row: QHBoxLayout) -> None:
        """On the welcome screen the dock is one line, so the folder sits beside the formats."""
        if row.indexOf(self.destination) >= 0:
            return
        for other in (self.action_row, self.options_row.layout()):
            other.removeWidget(self.destination)
        row.addWidget(self.destination)

    def show_progress(self, state: Converting) -> None:
        self._pages.setCurrentIndex(1)
        if state.cancelling:
            self.progress_title.setText("Cancelling…")
            self.progress_file.setText("Finishing the current file")
        else:
            current_number = min(state.done + 1, state.total)
            self.progress_title.setText(f"Converting {current_number} of {state.total}")
            self.progress_file.setText(state.current)
        self.progress_remaining.setText(f"{state.done} done · {state.remaining} left")
        self.progress.set_fraction(state.done / state.total if state.total else 0)
        self.cancel_button.setEnabled(not state.cancelling)

    def focus_chain(self) -> list[QWidget]:
        return [self.merge, self.gif_mode_chip, self.name_chip, self.page_chip, self.quality_chip,
                self.animation_chip, self.dpi_chip, self.destination,
                *self.formats.buttons.values(), self.formats.more, self.convert_button]

    def options(self) -> Options:
        return self._options

    def set_destination(self, folder: Path, problem: FolderProblem | None) -> None:
        self.destination.show_folder(folder, problem)

