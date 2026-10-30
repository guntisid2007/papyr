"""The result of a finished run: what was saved and where, and what failed and why."""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget

from converter import OutputFormat
from utils.reveal import REVEAL_LABEL

from ..icons import Icon, paint_icon
from ..model import Outcome, RunResult, plural
from ..theme import Type, current
from ..views.controls import display_path
from ..widgets import Button, ElidedLabel, Glyph, Kind, Surface, label

ROW = 30
VISIBLE_ROWS = 5
_BADGE = {Outcome.SUCCESS: (Icon.CHECK, "success", "success_wash"),
          Outcome.PARTIAL: (Icon.WARNING, "warning", "warning_wash"),
          Outcome.FAILED: (Icon.WARNING, "danger", "danger_wash")}


def headline(result: RunResult) -> tuple[str, str]:
    """The title and the line under it, in plain words, for this result."""
    files = plural(len(result.sources), "file")
    where = display_path(result.destination)
    kind = "PDF" if result.format is OutputFormat.PDF else f"{result.format.label} file"
    saved = plural(len(result.outputs), kind)
    match result.outcome:
        case Outcome.SUCCESS if result.merged:
            return f"Saved “{result.outputs[0].name}”", f"{files} merged into one PDF in {where}"
        case Outcome.SUCCESS:
            return f"{files} converted", f"{saved} saved to {where}"
        case Outcome.PARTIAL if result.merged:
            failed = plural(len(result.failed_sources), "file")
            return (f"Saved “{result.outputs[0].name}” without {failed}",
                    f"{result.converted_count} of {files} merged. The rest couldn't be read.")
        case Outcome.PARTIAL:
            return (f"{result.converted_count} of {files} converted",
                    f"{saved} saved to {where}. {plural(len(result.failed_sources), 'file')} couldn't be converted.")
        case _:
            reasons = {failure.reason for failure in result.failures}
            return "Nothing was converted", reasons.pop() if len(reasons) == 1 else "None of the files could be converted."


class StatusBadge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 60)
        self._outcome = Outcome.SUCCESS

    def set_outcome(self, outcome: Outcome) -> None:
        self._outcome = outcome
        self.setAccessibleName(outcome.name.title())
        self.update()

    def paintEvent(self, event) -> None:
        theme = current()
        icon, color, wash = _BADGE[self._outcome]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(getattr(theme, wash))
        painter.drawEllipse(QRectF(self.rect()))
        paint_icon(painter, icon, QRectF(self.rect()).adjusted(17, 17, -17, -17), getattr(theme, color), 2.2)


class FailureList(QListWidget):
    """Every file that failed, with its reason. The raw error is in the tooltip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Files that couldn't be converted")
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)

    def show_failures(self, result: RunResult) -> None:
        self.clear()
        for failure in result.failures:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(10, 0, 10, 0)
            line.setSpacing(8)
            line.addWidget(Glyph(Icon.WARNING, 13, "danger"), 0, Qt.AlignmentFlag.AlignVCenter)
            name = ElidedLabel(failure.path.name, Type.BODY_MEDIUM, Qt.TextElideMode.ElideMiddle)
            name.setMaximumWidth(220)
            line.addWidget(name)
            reason = ElidedLabel(failure.reason, Type.CAPTION)
            reason.setProperty("tone", "secondary")
            line.addWidget(reason, 1)
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, ROW))
            item.setToolTip(f"{failure.path}\n{failure.detail}")
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{failure.path.name}: {failure.reason}")
            self.addItem(item)
            self.setItemWidget(item, row)
        self.setFixedHeight(min(self.count(), VISIBLE_ROWS) * ROW + 4)


class DoneView(QWidget):
    revealRequested = Signal()
    retryRequested = Signal()
    convertMore = Signal()
    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 16)
        outer.setSpacing(0)
        top = QHBoxLayout()
        self.back_button = Button("Back to Files", Icon.ARROW_LEFT, Kind.GHOST, height=28)
        self.back_button.setToolTip("Return to the same files, for example to convert them to another format")
        self.back_button.clicked.connect(self.backRequested)
        top.addWidget(self.back_button)
        top.addStretch()
        outer.addLayout(top)
        outer.addStretch(2)

        center = QHBoxLayout()
        center.addStretch(1)
        body = QWidget()
        body.setMaximumWidth(540)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        center.addWidget(body, 10)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(3)

        column = QVBoxLayout(body)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.badge = StatusBadge()
        column.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addSpacing(16)
        self.title = label("", Type.TITLE, wrap=True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.title)
        column.addSpacing(6)
        self.subtitle = label("", Type.BODY, "secondary", wrap=True)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self.subtitle)
        column.addSpacing(18)

        self.failures_card = Surface(12, "surface")
        card = QVBoxLayout(self.failures_card)
        card.setContentsMargins(4, 10, 4, 4)
        card.setSpacing(4)
        self.failures_heading = label("", Type.LABEL, "secondary")
        self.failures_heading.setContentsMargins(10, 0, 0, 0)
        card.addWidget(self.failures_heading)
        self.failures = FailureList()
        card.addWidget(self.failures)
        column.addWidget(self.failures_card)
        column.addSpacing(18)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch()
        self.retry_button = Button("Retry Failed", Icon.RETRY, height=32)
        self.retry_button.setToolTip("Put only the files that failed back in the list")
        self.retry_button.clicked.connect(self.retryRequested)
        self.more_button = Button("Convert More", Icon.PLUS, height=32)
        self.more_button.setToolTip("Start again with an empty list")
        self.more_button.clicked.connect(self.convertMore)
        self.reveal_button = Button(REVEAL_LABEL, Icon.REVEAL, Kind.PRIMARY, height=32)
        self.reveal_button.setToolTip("Show the converted files")
        self.reveal_button.clicked.connect(self.revealRequested)
        for button in (self.retry_button, self.more_button, self.reveal_button):
            actions.addWidget(button)
        actions.addStretch()
        column.addLayout(actions)

    def show_result(self, result: RunResult, retryable: bool) -> None:
        self.badge.set_outcome(result.outcome)
        title, subtitle = headline(result)
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.failures_card.setVisible(bool(result.failures))
        if result.failures:
            self.failures_heading.setText("NOT CONVERTED")
            self.failures.show_failures(result)
        self.reveal_button.setVisible(bool(result.outputs))
        self.retry_button.setVisible(bool(result.failed_sources))
        self.retry_button.setEnabled(retryable)
        if not retryable and result.failed_sources:
            self.retry_button.setToolTip("The files that failed were moved or deleted")
