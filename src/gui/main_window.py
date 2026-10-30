from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QSettings, QStandardPaths, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QIcon, QImage, QKeySequence
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from converter import (INPUT_EXTENSIONS, ConversionReport, OutputFormat, convert_images, convert_individual,
                       convert_merged, is_supported)
from utils.app_info import APP_NAME, __version__
from utils.errors import friendly_error
from utils.filenames import sanitize_pdf_name
from utils.files import FolderProblem, collect_images, folder_problem
from utils.resources import asset_path
from utils.reveal import REVEAL_LABEL, reveal

from .file_queue import FileQueue, FileState, summary_text
from .save_animation import SaveAnimation
from .settings_panel import SettingsPanel
from .widgets import ElidedLabel, EmptyState, dropped_paths, secondary_label
from .workers import ConversionWorker, ThumbnailLoader

FILE_FILTER = "Images, PDFs, and notebooks ({})".format(" ".join(f"*{ext}" for ext in sorted(INPUT_EXTENSIONS)))
THUMBNAIL_SIZE = 112
SUBTITLE = "Convert photos, PDFs, and Jupyter notebooks to PDF, JPEG, PNG, WebP, and more."
ORDER_HINT = "Drag to reorder. Pages follow this order."
UNSUPPORTED = "this file format isn't supported."
CONVERT_SHORTCUTS = (QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter"))
DETAILS_LIMIT = 15


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


@dataclass
class Run:
    """One conversion. The report arrives when it finishes, and the run is kept until the queue changes."""

    sources: list[Path]
    combined: bool
    report: ConversionReport | None = None


def outcome(run: Run) -> tuple[str, str]:
    """The status line for a finished run, and its kind: "success", "error", or "" for neutral."""
    report = run.report
    if report.cancelled:
        kept = f" {plural(len(report.outputs), 'finished file')} kept." if report.outputs else ""
        return f"Conversion cancelled.{kept}", ""
    if report.outputs and not report.failures:
        if run.combined:
            return f"✓ Saved {report.outputs[0].name}", "success"
        return f"✓ {plural(len(run.sources), 'file')} converted successfully", "success"
    if report.outputs:
        rest = f"The rest were saved in {report.outputs[0].name}." if run.combined else \
            "The remaining files were saved."
        return f"Conversion failed for {plural(len(report.failures), 'file')}. {rest}", "error"
    reasons = {friendly_error(raw) for _, raw in report.failures}
    if len(reasons) == 1:
        return f"Conversion failed. {reasons.pop()}", "error"
    return "Conversion failed. None of the files could be converted.", "error"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(760, 520)
        self.resize(1000, 660)
        self.setAcceptDrops(True)
        self._settings = QSettings()
        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._run: Run | None = None
        self._output_dir = Path.home()
        self._thumbnails = ThumbnailLoader(THUMBNAIL_SIZE, self)
        self._thumbnails.loaded.connect(self._on_thumbnail)
        self._thumbnails.failed.connect(self._on_thumbnail_failed)

        root = QWidget()
        root.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # clicking empty space leaves text fields
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        content = QVBoxLayout()
        content.setContentsMargins(20, 16, 20, 16)
        content.setSpacing(14)
        layout.addLayout(content, 1)
        content.addWidget(self._build_header())
        body = QHBoxLayout()
        body.setSpacing(14)
        content.addLayout(body, 1)
        body.addWidget(self._build_workspace(), 1)
        self._panel = SettingsPanel()
        self._panel.changed.connect(self._refresh)
        self._panel.destination.changeRequested.connect(self._choose_output_dir)
        body.addWidget(self._panel)
        layout.addWidget(self._build_action_bar())
        self.setCentralWidget(root)
        self._build_menus()
        self._restore_settings()
        self._set_tab_order()
        QApplication.instance().focusChanged.connect(self._update_actions)
        self._refresh()
        root.setFocus()  # nothing shows a focus ring until the keyboard is used

    # Layout

    def _build_header(self) -> QWidget:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(QIcon(str(asset_path("icon.png"))).pixmap(32, 32))
        row.addWidget(icon)
        text = QVBoxLayout()
        text.setSpacing(0)
        row.addLayout(text, 1)
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel(SUBTITLE)
        subtitle.setObjectName("Subtitle")
        text.addWidget(title)
        text.addWidget(subtitle)
        return header

    def _build_workspace(self) -> QWidget:
        self._workspace = QFrame()
        self._workspace.setObjectName("Workspace")
        frame = QVBoxLayout(self._workspace)
        frame.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        frame.addWidget(self._stack)

        self._empty = EmptyState()
        self._empty.browseFiles.connect(self._browse_files)
        self._empty.browseFolder.connect(self._browse_folder)
        self._stack.addWidget(self._empty)

        page = QFrame()
        page.setObjectName("Card")
        column = QVBoxLayout(page)
        column.setContentsMargins(12, 12, 12, 10)
        column.setSpacing(6)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 0, 0, 0)
        toolbar.setSpacing(8)
        column.addLayout(toolbar)
        self._summary_label = ElidedLabel()
        self._summary_label.setObjectName("Section")
        toolbar.addWidget(self._summary_label, 1)
        self._add_files_button = QPushButton("Add Files…")
        self._add_files_button.setToolTip("Add photos, PDFs, or notebooks")
        self._add_files_button.clicked.connect(self._browse_files)
        self._add_folder_button = QPushButton("Add Folder…")
        self._add_folder_button.setToolTip("Add every supported file in a folder")
        self._add_folder_button.clicked.connect(self._browse_folder)
        self._clear_button = QPushButton("Clear All")
        self._clear_button.setToolTip("Remove every file from the list")
        self._clear_button.clicked.connect(self._clear)
        for button in (self._add_files_button, self._add_folder_button, self._clear_button):
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            toolbar.addWidget(button)

        self._queue = FileQueue()
        self._queue.changed.connect(self._on_queue_changed)
        self._queue.itemSelectionChanged.connect(self._update_actions)
        column.addWidget(self._queue, 1)
        self._order_hint = secondary_label(ORDER_HINT)
        self._order_hint.setContentsMargins(4, 0, 0, 0)
        column.addWidget(self._order_hint)
        self._stack.addWidget(page)
        return self._workspace

    def _build_action_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("ActionBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 12, 20, 14)
        row.setSpacing(10)
        status_column = QVBoxLayout()
        status_column.setSpacing(6)
        status_column.addSpacing(10)  # balances the progress bar's reserved space so the status line is centred
        row.addLayout(status_column, 1)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_column.addLayout(status_row)
        self._status = ElidedLabel()
        self._status.setObjectName("Status")
        self._details_button = QPushButton("Details…")
        self._details_button.setObjectName("Link")
        self._details_button.setToolTip("See why each file wasn't converted")
        self._details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._details_button.clicked.connect(self._show_details)
        self._details_button.hide()
        status_row.addWidget(self._status)
        status_row.addWidget(self._details_button)
        status_row.addStretch()
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setAccessibleName("Conversion progress")
        policy = self._progress.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self._progress.setSizePolicy(policy)
        self._progress.hide()
        status_column.addWidget(self._progress)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setToolTip("Stop after the current file. Finished files are kept.")
        self._cancel_button.clicked.connect(self._cancel)
        self._cancel_button.hide()
        self._reveal_button = QPushButton(REVEAL_LABEL)
        self._reveal_button.setToolTip("Show the converted files")
        self._reveal_button.clicked.connect(self._reveal_output)
        self._reveal_button.hide()
        self._convert_button = QPushButton()
        self._convert_button.setObjectName("Primary")
        self._convert_button.setMinimumWidth(150)
        self._convert_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._convert_button.clicked.connect(self._convert)
        for button in (self._cancel_button, self._reveal_button, self._convert_button):
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
        return bar

    def _action(self, menu, text: str, slot, shortcuts=(), tip: str = "") -> QAction:
        action = QAction(text, self)
        action.setShortcuts([QKeySequence(s) for s in shortcuts])
        action.setStatusTip(tip)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        self._add_files_action = self._action(file_menu, "Add Files…", self._browse_files,
                                              [QKeySequence.StandardKey.Open])
        self._add_folder_action = self._action(file_menu, "Add Folder…", self._browse_folder, ["Ctrl+Shift+O"])
        file_menu.addSeparator()
        self._convert_action = self._action(file_menu, "Convert", self._convert, CONVERT_SHORTCUTS)
        self._reveal_action = self._action(file_menu, REVEAL_LABEL, self._reveal_output)
        file_menu.addSeparator()
        self._close_action = self._action(file_menu, "Close Window", self.close, [QKeySequence.StandardKey.Close])
        self._quit_action = self._action(file_menu, "Quit", QApplication.quit, [QKeySequence.StandardKey.Quit])
        self._quit_action.setMenuRole(QAction.MenuRole.QuitRole)

        edit_menu = bar.addMenu("&Edit")
        self._select_all_action = self._action(edit_menu, "Select All", self._select_all,
                                               [QKeySequence.StandardKey.SelectAll])
        self._remove_action = self._action(edit_menu, "Remove Selected", self._remove_selected,
                                           [QKeySequence(Qt.Key.Key_Backspace), QKeySequence(Qt.Key.Key_Delete)])
        # Only while the list has focus, so Backspace in the PDF name field still deletes text.
        self._remove_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._queue.addAction(self._remove_action)
        edit_menu.addSeparator()
        self._move_up_action = self._action(edit_menu, "Move Up", partial(self._queue.move_selected, -1),
                                            ["Ctrl+Alt+Up"])
        self._move_down_action = self._action(edit_menu, "Move Down", partial(self._queue.move_selected, 1),
                                              ["Ctrl+Alt+Down"])
        edit_menu.addSeparator()
        self._clear_action = self._action(edit_menu, "Clear All", self._clear)

        help_menu = bar.addMenu("&Help")
        self._about_action = self._action(help_menu, f"About {APP_NAME}", self._about)
        self._about_action.setMenuRole(QAction.MenuRole.AboutRole)

    def _set_tab_order(self) -> None:
        chain = [self._empty.browse_button, self._empty.folder_button, self._add_files_button,
                 self._add_folder_button, self._clear_button, self._queue, *self._panel.focus_chain(),
                 self._details_button, self._cancel_button, self._reveal_button, self._convert_button]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    # State

    @property
    def _converting(self) -> bool:
        return self._thread is not None

    def output_dir(self) -> Path:
        return self._output_dir

    def set_output_dir(self, folder: Path) -> None:
        self._output_dir = folder
        self._settings.setValue("output_dir", str(folder))
        self._refresh()

    def _convert_blocker(self, count: int, problem: FolderProblem | None) -> str | None:
        """Why Convert can't run right now, or None when it can."""
        if self._converting:
            return "A conversion is in progress."
        if not count:
            return "Add files to convert."
        if problem:
            return problem.explanation
        return None

    def _refresh(self) -> None:
        summary = self._queue.summary()
        busy = self._converting
        self._stack.setCurrentIndex(1 if summary.count else 0)
        self._summary_label.setText(summary_text(summary))
        self._panel.update_for(summary, busy)
        problem = folder_problem(self._output_dir)
        self._panel.show_destination(self._output_dir, problem.short if problem else None)
        fmt = self._panel.output_format()
        self._convert_button.setText(f"Convert to {fmt.label}")
        blocker = self._convert_blocker(summary.count, problem)
        self._convert_button.setEnabled(blocker is None)
        shortcut = CONVERT_SHORTCUTS[0].toString(QKeySequence.SequenceFormat.NativeText)
        self._convert_button.setToolTip(blocker or f"Convert {plural(summary.count, 'file')} to {fmt.label} "
                                                   f"({shortcut})")
        self._order_hint.setVisible(self._panel.combine())
        self._queue.setEnabled(not busy)
        for button in (self._add_files_button, self._add_folder_button, self._clear_button,
                       self._empty.browse_button, self._empty.folder_button):
            button.setEnabled(not busy)
        self._update_actions()

    def _update_actions(self, *_) -> None:
        busy = self._converting
        count = self._queue.count()
        selected = bool(self._queue.selectedItems()) and not busy
        self._add_files_action.setEnabled(not busy)
        self._add_folder_action.setEnabled(not busy)
        self._convert_action.setEnabled(self._convert_button.isEnabled())
        self._reveal_action.setEnabled(bool(self._run and self._run.report and self._run.report.outputs))
        self._remove_action.setEnabled(selected and self._queue.hasFocus())
        self._move_up_action.setEnabled(selected and count > 1)
        self._move_down_action.setEnabled(selected and count > 1)
        self._clear_action.setEnabled(count > 0 and not busy)

    def _restore_settings(self) -> None:
        documents = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
                         or Path.home())
        saved = Path(str(self._settings.value("output_dir", documents)))
        self._output_dir = saved if saved.is_dir() else documents if documents.is_dir() else Path.home()
        self._panel.restore(self._settings)

    def _save_settings(self) -> None:
        self._settings.setValue("output_dir", str(self._output_dir))
        self._panel.save(self._settings)

    def _set_status(self, text: str, kind: str = "") -> None:
        self._status.setText(text)
        self._status.setProperty("kind", kind)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def _forget_run(self) -> None:
        self._run = None
        self._set_status("")
        self._details_button.hide()
        self._reveal_button.hide()

    # Adding and removing files

    def add_paths(self, paths: list[Path]) -> None:
        if self._converting:
            return
        unsupported = sum(1 for p in paths if p.is_file() and not is_supported(p))
        found = collect_images(paths)
        existing = {p.resolve() for p in self._queue.paths()}
        new = [p for p in found if p.resolve() not in existing]
        self._queue.add_files(new)
        for path in new:
            self._thumbnails.request(path)

        skipped = f"{plural(unsupported, 'file')} skipped — {UNSUPPORTED}" if unsupported else ""
        if new:
            self._set_status(" ".join(filter(None, [f"Added {plural(len(new), 'file')}.", skipped])))
        elif found:
            self._set_status(" ".join(filter(None, ["Those files are already in the list.", skipped])))
        elif unsupported:
            self._set_status(skipped, "error")
        elif paths:
            self._set_status("No supported files found there.", "error")

    def _on_queue_changed(self) -> None:
        self._forget_run()
        self._refresh()

    def _on_thumbnail(self, path: str, image: QImage) -> None:
        self._queue.set_thumbnail(path, image)

    def _on_thumbnail_failed(self, path: str, error: str) -> None:
        self._queue.mark(path, FileState.UNREADABLE, friendly_error(error))
        self._refresh()

    def _remove_selected(self) -> None:
        self._queue.remove_selected()

    def _select_all(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QAbstractSpinBox)):
            focus.selectAll()
            return
        self._queue.selectAll()
        self._queue.setFocus()

    def _clear(self) -> None:
        self._queue.clear()

    def _browse_files(self) -> None:
        start = str(self._settings.value("input_dir", Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Choose Files", start, FILE_FILTER)
        if files:
            self._settings.setValue("input_dir", str(Path(files[0]).parent))
            self.add_paths([Path(f) for f in files])

    def _browse_folder(self) -> None:
        start = str(self._settings.value("input_dir", Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Choose a Folder", start)
        if folder:
            self._settings.setValue("input_dir", folder)
            self.add_paths([Path(folder)])

    def _choose_output_dir(self) -> None:
        start = self._output_dir if self._output_dir.is_dir() else Path.home()
        folder = QFileDialog.getExistingDirectory(self, "Choose Where to Save", str(start))
        if folder:
            self.set_output_dir(Path(folder))

    # Dropping files anywhere on the window

    def _set_dragging(self, dragging: bool) -> None:
        self._workspace.setProperty("dragging", dragging)
        self._workspace.style().unpolish(self._workspace)
        self._workspace.style().polish(self._workspace)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and not self._converting:
            event.acceptProposedAction()
            self._set_dragging(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls() and not self._converting:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._set_dragging(False)

    def dropEvent(self, event) -> None:
        self._set_dragging(False)
        event.acceptProposedAction()
        self.add_paths(dropped_paths(event))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._refresh()  # the Save to folder may have been renamed or removed while Papyr was in the background

    # Conversion

    def _convert(self) -> None:
        if self._converting:
            return
        sources = self._queue.paths()
        problem = folder_problem(self._output_dir)
        if problem:
            self._set_status(problem.explanation, "error")
        if problem or not sources:
            self._refresh()
            return
        self._save_settings()
        fmt = self._panel.output_format()
        combined = self._panel.combine()
        if fmt is not OutputFormat.PDF:
            job = partial(convert_images, sources, self._output_dir, self._panel.image_settings())
        elif combined:
            merged_path = self._output_dir / sanitize_pdf_name(self._panel.merged_name() or "Combined", "Combined")
            if merged_path.exists() and QMessageBox.question(
                    self, "Replace File?", f"“{merged_path.name}” already exists in this folder. Replace it?"
            ) != QMessageBox.StandardButton.Yes:
                return
            job = partial(convert_merged, sources, merged_path, self._panel.pdf_settings())
        else:
            job = partial(convert_individual, sources, self._output_dir, self._panel.pdf_settings())
        self._start(ConversionWorker(job), Run(sources, combined))

    def _start(self, worker: ConversionWorker, run: Run) -> None:
        self._forget_run()
        self._run = run
        self._queue.reset_failures()
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._progress.setRange(0, len(run.sources))
        self._progress.setValue(0)
        self._progress.show()
        self._cancel_button.show()
        self._cancel_button.setEnabled(True)
        self._set_status("Starting…")
        self._thread.start()
        self._refresh()

    def _cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self._cancel_button.setEnabled(False)
            self._set_status("Cancelling…")

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self._progress.setValue(done)
        if done < total:
            self._set_status(f"Converting {done + 1} of {total} — {name}")

    def _on_finished(self, report: ConversionReport) -> None:
        self._thread = None
        self._worker = None
        self._progress.hide()
        self._cancel_button.hide()
        run = self._run
        run.report = report
        queued = {str(source) for source in run.sources}
        for path, raw in report.failures:
            if str(path) in queued:
                self._queue.mark(str(path), FileState.FAILED, friendly_error(raw))
        self._set_status(*outcome(run))
        self._details_button.setVisible(bool(report.failures))
        self._reveal_button.setVisible(bool(report.outputs))
        if report.outputs and not report.cancelled:
            QTimer.singleShot(0, self, partial(self._play_save_animation, len(report.outputs)))
        self._refresh()

    def _show_details(self) -> None:
        failures = self._run.report.failures
        lines = [f"• {path.name}: {friendly_error(raw)}" for path, raw in failures[:DETAILS_LIMIT]]
        if len(failures) > DETAILS_LIMIT:
            lines.append(f"…and {len(failures) - DETAILS_LIMIT} more.")
        box = QMessageBox(QMessageBox.Icon.Warning, "Conversion Details",
                          f"{plural(len(failures), 'file')} couldn't be converted.",
                          QMessageBox.StandardButton.Ok, self)
        box.setInformativeText("\n".join(lines))
        box.setDetailedText("\n".join(f"{path}: {raw}" for path, raw in failures))
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.open()

    def _reveal_output(self) -> None:
        if self._run and self._run.report and self._run.report.outputs:
            reveal(self._run.report.outputs[0])

    def _about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME} {__version__}</b><p>A free, offline converter for photos, PDFs, "
                          f"and Jupyter notebooks.</p><p>Your files never leave this computer.</p>")

    def _save_animation_endpoints(self) -> tuple[QPointF, QPointF]:
        canvas = self.centralWidget()
        start = self._stack.mapTo(canvas, self._stack.rect().center())
        target = self._reveal_button.mapTo(canvas, self._reveal_button.rect().center())
        return QPointF(start), QPointF(target) - QPointF(self._reveal_button.width() / 2 + 52, 0)

    def _play_save_animation(self, count: int) -> SaveAnimation:
        animation = SaveAnimation(self.centralWidget(), self._save_animation_endpoints, count)
        animation.start()
        return animation

    def closeEvent(self, event) -> None:
        self._save_settings()
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()  # the worker stops at the next image; destroying a running QThread aborts
        self._thumbnails.shutdown()
        super().closeEvent(event)
