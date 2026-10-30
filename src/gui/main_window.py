"""Papyr's window. It is always in one AppState (Welcome, Workspace, Converting, or Done), and set_state() is the
only place that decides what the window shows and which actions are available."""
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from PySide6.QtCore import QEvent, QSettings, QStandardPaths, Qt, QThread
from PySide6.QtGui import QAction, QImage, QKeySequence
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QFileDialog, QLineEdit, QMainWindow, QMessageBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from converter import INPUT_EXTENSIONS, ConversionReport, OutputFormat, is_supported
from utils.app_info import APP_NAME, __version__
from utils.errors import friendly_error
from utils.files import collect_images, folder_problem
from utils.reveal import REVEAL_LABEL, reveal

from .model import AppState, Converting, Done, Options, RunResult, Welcome, Workspace, plan_job, plural
from .views.controls import Dock
from .views.done import DoneView
from .views.welcome import WelcomeView
from .views.workspace import WorkspaceView
from .widgets import DropOverlay, crossfade, dropped_paths
from .workers import ConversionWorker, ThumbnailLoader

FILE_FILTER = "Images, PDFs, and notebooks ({})".format(" ".join(f"*{ext}" for ext in sorted(INPUT_EXTENSIONS)))
THUMBNAIL_SIZE = 96
UNSUPPORTED = "this format isn't supported"
CONVERT_SHORTCUTS = (QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter"))
CANCEL_SHORTCUTS = (QKeySequence(Qt.Key.Key_Escape), QKeySequence("Ctrl+."))
DEFAULT_SIZE = (760, 560)
MINIMUM_SIZE = (640, 480)


@dataclass(frozen=True)
class RunSpec:
    """What a running conversion was asked to do, kept to describe its result."""

    sources: list[Path]
    format: OutputFormat
    merged: bool
    destination: Path


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(*MINIMUM_SIZE)
        self.resize(*DEFAULT_SIZE)
        self.setAcceptDrops(True)
        self._settings = QSettings()
        self._options = Options.load(self._settings)
        self._output_dir = self._saved_output_dir()
        self._state: AppState = Welcome()
        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._run: RunSpec | None = None
        self._thumbnails = ThumbnailLoader(THUMBNAIL_SIZE, self)
        self._thumbnails.loaded.connect(self._on_thumbnail)
        self._thumbnails.failed.connect(self._on_thumbnail_failed)

        self._canvas = QWidget()
        self._canvas.setObjectName("Canvas")
        self._canvas.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # clicking empty space leaves text fields
        column = QVBoxLayout(self._canvas)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self._pages = QStackedWidget()
        column.addWidget(self._pages, 1)

        self.welcome = WelcomeView()
        self.welcome.browseFiles.connect(self._browse_files)
        self.welcome.browseFolder.connect(self._browse_folder)
        self.workspace = WorkspaceView()
        self.workspace.addFiles.connect(self._browse_files)
        self.workspace.addFolder.connect(self._browse_folder)
        self.workspace.clearAll.connect(self._clear)
        self.workspace.banner.revealRequested.connect(self._reveal_output)
        self.workspace.banner.dismissed.connect(lambda: self.set_state(Workspace()))
        self.queue = self.workspace.queue
        self.queue.changed.connect(self._on_queue_changed)
        self.queue.itemSelectionChanged.connect(self._update_actions)
        self.queue.focusMoved.connect(self._update_actions)
        self.done = DoneView()
        self.done.revealRequested.connect(self._reveal_output)
        self.done.retryRequested.connect(self._retry_failed)
        self.done.convertMore.connect(self._clear)
        self.done.backRequested.connect(lambda: self.set_state(Workspace()))
        for page in (self.welcome, self.workspace, self.done):
            self._pages.addWidget(page)

        self.dock = Dock()
        self.dock.edited.connect(self._on_options)
        self.dock.convertRequested.connect(self._convert)
        self.dock.cancelRequested.connect(self._cancel)
        self.dock.destinationRequested.connect(self._choose_output_dir)
        dock_margin = QVBoxLayout()
        dock_margin.setContentsMargins(12, 8, 12, 12)
        dock_margin.addWidget(self.dock)
        column.addLayout(dock_margin)
        self._drop_overlay = DropOverlay(self._canvas)
        self.setCentralWidget(self._canvas)

        self._build_menus()
        self._set_tab_order()
        self.set_state(Welcome())
        self._canvas.setFocus()  # nothing shows a focus ring until the keyboard is used

    # The state machine

    def state(self) -> AppState:
        return self._state

    def set_state(self, state: AppState) -> None:
        page = {Welcome: self.welcome, Workspace: self.workspace, Converting: self.workspace,
                Done: self.done}[type(state)]
        if page is not self._pages.currentWidget() or type(state) is not type(self._state):
            crossfade(self._canvas)
        self._state = state
        self._pages.setCurrentWidget(page)
        self._render()

    def _render(self) -> None:
        state, queue, options = self._state, self.queue.summary(), self._options
        problem = folder_problem(self._output_dir)
        self.dock.set_destination(self._output_dir, problem)
        self.dock.setVisible(not isinstance(state, Done))
        match state:
            case Welcome(notice=notice, error=error):
                self.welcome.show_notice(notice, error)
                self.dock.show_welcome(options)
            case Workspace():
                self.workspace.show_queue(queue, options.merges(queue), busy=False)
                self.workspace.banner.show_notice(state)
                self.dock.show_workspace(options, queue, self._convert_blocker(queue.count, problem))
            case Converting():
                self.workspace.show_queue(queue, options.merges(queue), busy=True)
                self.workspace.banner.hide()
                self.queue.show_active(state.done)
                self.dock.show_progress(state)
            case Done(result=result):
                self.done.show_result(result, retryable=any(p.is_file() for p in result.failed_sources))
        self._update_actions()

    def _update_actions(self, *_) -> None:
        state = self._state
        editing = isinstance(state, Workspace)
        selected = editing and bool(self.queue.selectedItems())
        self._add_files_action.setEnabled(not isinstance(state, Converting))
        self._add_folder_action.setEnabled(not isinstance(state, Converting))
        self._convert_action.setEnabled(editing and self.dock.convert_button.isEnabled())
        self._cancel_action.setEnabled(isinstance(state, Converting) and not state.cancelling)
        self._reveal_action.setEnabled(bool(self._revealable()))
        self._select_all_action.setEnabled(editing)
        self._remove_action.setEnabled(selected and self.queue.hasFocus())
        self._move_up_action.setEnabled(selected and self.queue.count() > 1)
        self._move_down_action.setEnabled(selected and self.queue.count() > 1)
        self._clear_action.setEnabled(editing)

    def _convert_blocker(self, count: int, problem) -> str | None:
        """Why Convert can't run right now, or None when it can."""
        if not count:
            return "Add files to convert."
        return problem.explanation if problem else None

    def _revealable(self) -> list[Path]:
        match self._state:
            case Done(result=result):
                return list(result.outputs)
            case Workspace(kept=kept):
                return list(kept)
        return []

    # Menus and keyboard

    def _action(self, menu, text: str, slot, shortcuts=()) -> QAction:
        action = QAction(text, self)
        action.setShortcuts([QKeySequence(s) for s in shortcuts])
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
        self._cancel_action = self._action(file_menu, "Cancel Conversion", self._cancel, CANCEL_SHORTCUTS)
        self._reveal_action = self._action(file_menu, REVEAL_LABEL, self._reveal_output)
        file_menu.addSeparator()
        self._close_action = self._action(file_menu, "Close Window", self.close, [QKeySequence.StandardKey.Close])
        self._quit_action = self._action(file_menu, "Quit", QApplication.quit, [QKeySequence.StandardKey.Quit])
        self._quit_action.setMenuRole(QAction.MenuRole.QuitRole)

        edit_menu = bar.addMenu("&Edit")
        self._select_all_action = self._action(edit_menu, "Select All", self._select_all,
                                               [QKeySequence.StandardKey.SelectAll])
        self._remove_action = self._action(edit_menu, "Remove Selected", self.queue.remove_selected,
                                           [QKeySequence(Qt.Key.Key_Backspace), QKeySequence(Qt.Key.Key_Delete)])
        # Only while the list has focus, so Backspace in a text field still deletes text.
        self._remove_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.queue.addAction(self._remove_action)
        edit_menu.addSeparator()
        self._move_up_action = self._action(edit_menu, "Move Up", partial(self.queue.move_selected, -1),
                                            ["Ctrl+Alt+Up"])
        self._move_down_action = self._action(edit_menu, "Move Down", partial(self.queue.move_selected, 1),
                                              ["Ctrl+Alt+Down"])
        edit_menu.addSeparator()
        self._clear_action = self._action(edit_menu, "Clear All", self._clear)

        help_menu = bar.addMenu("&Help")
        self._about_action = self._action(help_menu, f"About {APP_NAME}", self._about)
        self._about_action.setMenuRole(QAction.MenuRole.AboutRole)

    def _set_tab_order(self) -> None:
        chain = [self.welcome.browse_button, self.welcome.folder_button, self.workspace.add_files_button,
                 self.workspace.add_folder_button, self.workspace.clear_button, self.queue,
                 *self.dock.focus_chain(), self.dock.cancel_button, self.done.back_button, self.done.failures,
                 self.done.retry_button, self.done.more_button, self.done.reveal_button]
        for first, second in zip(chain, chain[1:]):
            QWidget.setTabOrder(first, second)

    def _select_all(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QAbstractSpinBox)):
            focus.selectAll()
            return
        self.queue.selectAll()
        self.queue.setFocus()

    # Settings and the Save to folder

    def _saved_output_dir(self) -> Path:
        documents = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
                         or Path.home())
        saved = Path(str(self._settings.value("output_dir", documents)))
        return saved if saved.is_dir() else documents if documents.is_dir() else Path.home()

    def options(self) -> Options:
        return self._options

    def _on_options(self, options: Options) -> None:
        self._options = options
        options.save(self._settings)
        self._render()

    def output_dir(self) -> Path:
        return self._output_dir

    def set_output_dir(self, folder: Path) -> None:
        self._output_dir = folder
        self._settings.setValue("output_dir", str(folder))
        self._render()

    def _choose_output_dir(self) -> None:
        start = self._output_dir if self._output_dir.is_dir() else Path.home()
        folder = QFileDialog.getExistingDirectory(self, "Choose Where to Save", str(start))
        if folder:
            self.set_output_dir(Path(folder))

    # Adding and removing files

    def add_paths(self, paths: list[Path]) -> None:
        """Files from a dialog, a drop, Finder, or the command line. After a finished run they start a new batch."""
        if isinstance(self._state, Converting):
            return
        unsupported = sum(1 for p in paths if p.is_file() and not is_supported(p))
        found = collect_images(paths)
        fresh = isinstance(self._state, Done)
        existing = set() if fresh else {p.resolve() for p in self.queue.paths()}
        new = [p for p in found if p.resolve() not in existing]
        if fresh and new:
            self.queue.replace_files(new)
        else:
            self.queue.add_files(new)
        for path in new:
            self._thumbnails.request(path)

        skipped = f"{plural(unsupported, 'file')} skipped because {UNSUPPORTED}." if unsupported else ""
        if new:
            notice, error = skipped, False
        elif found:
            notice, error = " ".join(filter(None, ["Those files are already in the list.", skipped])), False
        elif unsupported:
            notice, error = skipped, True
        elif paths:
            notice, error = "No supported files found there.", True
        else:
            return
        if self.queue.count():
            self.set_state(Workspace(notice, error))
        elif notice:
            self.set_state(Welcome(notice, error))

    def _on_queue_changed(self) -> None:
        if isinstance(self._state, Converting):
            return
        self.set_state(Workspace() if self.queue.count() else Welcome())

    def _on_thumbnail(self, path: str, image: QImage) -> None:
        self.queue.set_thumbnail(path, image)

    def _on_thumbnail_failed(self, path: str, error: str) -> None:
        self.queue.mark_unreadable(path, friendly_error(error))
        self._render()

    def _clear(self) -> None:
        self.queue.clear()

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

    # Dropping files anywhere on the window

    def _show_drop_target(self, shown: bool) -> None:
        if isinstance(self._state, Welcome):
            self.welcome.tile.set_active(shown)
        elif shown:
            self._drop_overlay.show_message("Drop to start a new batch" if isinstance(self._state, Done)
                                            else "Drop to add to the list")
        if not shown:
            self._drop_overlay.hide()
            self.welcome.tile.set_active(False)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and not isinstance(self._state, Converting):
            event.acceptProposedAction()
            self._show_drop_target(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls() and not isinstance(self._state, Converting):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._show_drop_target(False)

    def dropEvent(self, event) -> None:
        self._show_drop_target(False)
        event.acceptProposedAction()
        self.add_paths(dropped_paths(event))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._render()  # the Save to folder may have been renamed or removed while Papyr was in the background

    # Converting

    def _convert(self) -> None:
        if not isinstance(self._state, Workspace):
            return
        queue = self.queue.summary()
        problem = folder_problem(self._output_dir)
        if problem:
            self.set_state(Workspace(problem.explanation, True))
            return
        if not queue.count:
            return
        sources = self.queue.paths()
        merged = self._options.merges(queue)
        if merged:
            target = self._output_dir / self._options.merged_file_name()
            if target.exists() and QMessageBox.question(
                    self, "Replace File?", f"“{target.name}” already exists in this folder. Replace it?"
            ) != QMessageBox.StandardButton.Yes:
                return
        self._run = RunSpec(sources, self._options.format, merged, self._output_dir)
        self._start(ConversionWorker(plan_job(self._options, queue, sources, self._output_dir)), len(sources))

    def _start(self, worker: ConversionWorker, total: int) -> None:
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self.set_state(Converting(total))
        self._thread.start()

    def is_converting(self) -> bool:
        return isinstance(self._state, Converting)

    def _cancel(self) -> None:
        if isinstance(self._state, Converting) and self._worker is not None:
            self._worker.cancel()
            self.set_state(replace(self._state, cancelling=True))

    def _on_progress(self, done: int, total: int, name: str) -> None:
        if isinstance(self._state, Converting):
            self.set_state(replace(self._state, done=done, total=total, current=name if done < total else ""))

    def _on_finished(self, report: ConversionReport) -> None:
        self._thread = None
        self._worker = None
        run = self._run
        result = RunResult.from_report(report, run.sources, run.format, run.merged, run.destination)
        if report.cancelled:
            kept = f" {plural(len(report.outputs), 'finished file')} kept." if report.outputs else ""
            self.set_state(Workspace(f"Conversion cancelled.{kept}", False, tuple(report.outputs)))
        else:
            self.set_state(Done(result))

    def _retry_failed(self) -> None:
        if not isinstance(self._state, Done):
            return
        failed = self._state.result.failed_sources
        present = [path for path in failed if path.is_file()]
        if not present:
            return
        self.queue.replace_files(present)
        for path in present:
            self._thumbnails.request(path)
        missing = len(failed) - len(present)
        if missing:
            self.set_state(Workspace(f"{plural(missing, 'file')} that failed could not be found and "
                                     f"{'was' if missing == 1 else 'were'} left out.", True))

    def _reveal_output(self) -> None:
        targets = self._revealable()
        if targets:
            reveal(targets[0])

    def _about(self) -> None:
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<b>{APP_NAME} {__version__}</b><p>A free, offline converter for photos, PDFs, "
                          f"and Jupyter notebooks.</p><p>Your files never leave this computer.</p>")

    def closeEvent(self, event) -> None:
        self._settings.setValue("output_dir", str(self._output_dir))
        self._options.save(self._settings)
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()  # the worker stops at the next image; destroying a running QThread aborts
        self._thumbnails.shutdown()
        super().closeEvent(event)
