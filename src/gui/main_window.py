from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidgetItem, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton, QRadioButton, QStackedWidget,
                               QStyle, QVBoxLayout, QWidget)

from converter import SUPPORTED_EXTENSIONS, ConversionReport, PageSize, PdfSettings
from utils.filenames import sanitize_pdf_name
from utils.files import collect_images, human_size
from utils.resources import asset_path

from .widgets import DropZone, ImageList
from .workers import ConversionWorker, ThumbnailLoader

FILE_FILTER = "Images ({})".format(" ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)))
THUMBNAIL_SIZE = 112


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HEIC to PDF")
        self.setMinimumSize(880, 580)
        self.resize(1040, 680)
        self._settings = QSettings()
        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._last_output: Path | None = None
        self._thumbnails = ThumbnailLoader(THUMBNAIL_SIZE, self)
        self._thumbnails.loaded.connect(self._on_thumbnail)
        self._thumbnails.failed.connect(self._on_thumbnail_failed)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(16)
        layout.addWidget(self._build_header())
        body = QHBoxLayout()
        body.setSpacing(16)
        layout.addLayout(body, 1)
        body.addWidget(self._build_workspace(), 1)
        body.addWidget(self._build_settings())
        layout.addWidget(self._build_actions())
        self.setCentralWidget(root)
        self._restore_settings()
        self._refresh()

    # Layout

    def _build_header(self) -> QWidget:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        icon = QLabel()
        icon.setPixmap(QIcon(str(asset_path("icon.png"))).pixmap(44, 44))
        row.addWidget(icon)
        text = QVBoxLayout()
        row.addLayout(text, 1)
        text.setSpacing(0)
        title = QLabel("HEIC to PDF")
        title.setObjectName("Title")
        subtitle = QLabel("Turn iPhone photos and other images into PDFs. Everything stays on this computer.")
        subtitle.setObjectName("Muted")
        text.addWidget(title)
        text.addWidget(subtitle)
        return header

    def _build_workspace(self) -> QWidget:
        self._stack = QStackedWidget()
        self._drop_zone = DropZone()
        self._drop_zone.filesDropped.connect(self.add_paths)
        self._drop_zone.browseFiles.connect(self._browse_files)
        self._drop_zone.browseFolder.connect(self._browse_folder)
        self._stack.addWidget(self._drop_zone)

        list_page = QFrame()
        list_page.setObjectName("Card")
        column = QVBoxLayout(list_page)
        column.setContentsMargins(12, 12, 12, 12)
        toolbar = QHBoxLayout()
        column.addLayout(toolbar)
        self._count_label = QLabel()
        self._count_label.setObjectName("Strong")
        toolbar.addWidget(self._count_label)
        toolbar.addStretch()
        self._list_buttons = []
        for text, tip, slot in [("Add Files…", "Add images", self._browse_files),
                                ("Add Folder…", "Add every image in a folder", self._browse_folder),
                                ("↑", "Move selected up", lambda: self._list.move_selected(-1)),
                                ("↓", "Move selected down", lambda: self._list.move_selected(1)),
                                ("Remove", "Remove selected (Delete)", lambda: self._list.remove_selected()),
                                ("Clear All", "Remove every image", self._clear)]:
            button = QPushButton(text)
            button.setToolTip(tip)
            button.clicked.connect(slot)
            toolbar.addWidget(button)
            self._list_buttons.append(button)
        self._up_button, self._down_button, self._remove_button = self._list_buttons[2:5]
        self._list = ImageList()
        self._list.filesDropped.connect(self.add_paths)
        self._list.itemSelectionChanged.connect(self._refresh)
        self._list.model().rowsRemoved.connect(self._refresh)
        self._list.model().rowsInserted.connect(self._refresh)
        column.addWidget(self._list, 1)
        hint = QLabel("Drag rows to reorder. In a combined PDF, pages follow this order.")
        hint.setObjectName("Muted")
        column.addWidget(hint)
        self._stack.addWidget(list_page)
        return self._stack

    def _build_settings(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setFixedWidth(300)
        column = QVBoxLayout(panel)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(10)

        heading = QLabel("Output")
        heading.setObjectName("Strong")
        column.addWidget(heading)
        self._individual = QRadioButton("One PDF per image")
        self._merged = QRadioButton("Combine into one PDF")
        self._mode_group = QButtonGroup(self)
        for button in (self._individual, self._merged):
            self._mode_group.addButton(button)
            column.addWidget(button)
        self._individual.setChecked(True)
        self._mode_group.buttonToggled.connect(self._refresh)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Combined")
        self._name_label = QLabel("PDF name")
        column.addWidget(self._name_label)
        column.addWidget(self._name_edit)

        column.addSpacing(6)
        page_heading = QLabel("Page")
        page_heading.setObjectName("Strong")
        column.addWidget(page_heading)
        form = QFormLayout()
        column.addLayout(form)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._page_combo = QComboBox()
        for size in PageSize:
            self._page_combo.addItem(size.label, size)
        self._page_combo.setCurrentIndex(self._page_combo.findData(PageSize.A4))
        form.addRow("Size", self._page_combo)
        self._margin = QDoubleSpinBox()
        self._margin.setRange(0, 50)
        self._margin.setDecimals(0)
        self._margin.setSuffix(" mm")
        self._margin.setValue(10)
        form.addRow("Margins", self._margin)
        orientation = QLabel("Pages turn landscape automatically for wide photos. "
                             "Images are scaled to fit without stretching.")
        orientation.setObjectName("Muted")
        orientation.setWordWrap(True)
        column.addWidget(orientation)

        column.addSpacing(6)
        save_heading = QLabel("Save to")
        save_heading.setObjectName("Strong")
        column.addWidget(save_heading)
        self._output_label = QLabel()
        self._output_label.setObjectName("Path")
        self._output_label.setWordWrap(True)
        self._output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self._output_label)
        choose = QPushButton("Choose Folder…")
        choose.clicked.connect(self._choose_output_dir)
        column.addWidget(choose)
        column.addStretch()
        self._settings_widgets = [self._individual, self._merged, self._name_edit, self._page_combo,
                                  self._margin, choose]
        return panel

    def _build_actions(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        status_column = QVBoxLayout()
        row.addLayout(status_column, 1)
        status_column.setSpacing(4)
        self._status = QLabel()
        self._status.setObjectName("Status")
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self._progress.hide()
        status_column.addWidget(self._status)
        status_column.addWidget(self._progress)
        self._open_button = QPushButton("Show in Folder")
        self._open_button.clicked.connect(self._open_output)
        self._open_button.hide()
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self._cancel)
        self._cancel_button.hide()
        self._convert_button = QPushButton("Convert to PDF")
        self._convert_button.setObjectName("Primary")
        self._convert_button.setDefault(True)
        self._convert_button.clicked.connect(self._convert)
        for button in (self._open_button, self._cancel_button, self._convert_button):
            row.addWidget(button)
        return bar

    # State

    @property
    def _converting(self) -> bool:
        return self._thread is not None

    def _output_dir(self) -> Path:
        return Path(self._output_label.text())

    def _pdf_settings(self) -> PdfSettings:
        return PdfSettings(self._page_combo.currentData(), self._margin.value())

    def _refresh(self) -> None:
        count = self._list.count()
        self._stack.setCurrentIndex(1 if count else 0)
        self._count_label.setText(f"{count} image{'s' if count != 1 else ''}")
        has_selection = bool(self._list.selectedItems())
        for button in self._list_buttons:
            button.setEnabled(not self._converting)
        for button in (self._up_button, self._down_button, self._remove_button):
            button.setEnabled(has_selection and not self._converting)
        merged = self._merged.isChecked()
        self._name_label.setVisible(merged)
        self._name_edit.setVisible(merged)
        for widget in self._settings_widgets:
            widget.setEnabled(not self._converting)
        self._list.setEnabled(not self._converting)
        self._drop_zone.setEnabled(not self._converting)
        self._convert_button.setEnabled(count > 0 and not self._converting)

    def _restore_settings(self) -> None:
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        saved = Path(str(self._settings.value("output_dir", documents or Path.home())))
        self._output_label.setText(str(saved if saved.is_dir() else Path.home()))
        (self._merged if self._settings.value("mode") == "merged" else self._individual).setChecked(True)
        index = self._page_combo.findText(str(self._settings.value("page_size", PageSize.A4.label)))
        if index >= 0:
            self._page_combo.setCurrentIndex(index)
        self._margin.setValue(float(self._settings.value("margin_mm", 10)))
        self._name_edit.setText(str(self._settings.value("merged_name", "")))

    def _save_settings(self) -> None:
        self._settings.setValue("output_dir", str(self._output_dir()))
        self._settings.setValue("mode", "merged" if self._merged.isChecked() else "individual")
        self._settings.setValue("page_size", self._page_combo.currentText())
        self._settings.setValue("margin_mm", self._margin.value())
        self._settings.setValue("merged_name", self._name_edit.text())

    def _set_status(self, text: str, kind: str = "") -> None:
        self._status.setText(text)
        self._status.setProperty("kind", kind)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    # Adding and removing images

    def add_paths(self, paths: list[Path]) -> None:
        if self._converting:
            return
        existing = {p.resolve() for p in self._list.paths()}
        found = collect_images(paths)
        added = 0
        for path in found:
            if path.resolve() in existing:
                continue
            item = QListWidgetItem(f"{path.name}\n{human_size(path.stat().st_size)}")
            item.setData(ImageList.PATH_ROLE, str(path))
            item.setToolTip(str(path))
            item.setIcon(QIcon(self._placeholder()))
            self._list.addItem(item)
            self._thumbnails.request(path)
            added += 1
        if added:
            self._set_status(f"Added {added} image{'s' if added != 1 else ''}.")
        elif found:
            self._set_status("Those images are already in the list.")
        elif paths:
            self._set_status("No HEIC, HEIF, JPEG, or PNG images found there.", "error")
        self._open_button.hide()
        self._refresh()

    def _placeholder(self) -> QPixmap:
        pixmap = QPixmap(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        return pixmap

    def _items_for(self, path: str) -> list[QListWidgetItem]:
        return [self._list.item(i) for i in range(self._list.count())
                if self._list.item(i).data(ImageList.PATH_ROLE) == path]

    def _on_thumbnail(self, path: str, image: QImage) -> None:
        for item in self._items_for(path):
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    def _on_thumbnail_failed(self, path: str, error: str) -> None:
        for item in self._items_for(path):
            item.setText(f"{Path(path).name}\n⚠ {error}")
            item.setForeground(Qt.GlobalColor.red)
            item.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning))

    def _clear(self) -> None:
        self._list.clear()
        self._set_status("")
        self._open_button.hide()
        self._refresh()

    def _browse_files(self) -> None:
        start = str(self._settings.value("input_dir", Path.home()))
        files, _ = QFileDialog.getOpenFileNames(self, "Choose Images", start, FILE_FILTER)
        if files:
            self._settings.setValue("input_dir", str(Path(files[0]).parent))
            self.add_paths([Path(f) for f in files])

    def _browse_folder(self) -> None:
        start = str(self._settings.value("input_dir", Path.home()))
        folder = QFileDialog.getExistingDirectory(self, "Choose a Folder of Images", start)
        if folder:
            self._settings.setValue("input_dir", folder)
            self.add_paths([Path(folder)])

    def _choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Where to Save PDFs", str(self._output_dir()))
        if folder:
            self._output_label.setText(folder)
            self._settings.setValue("output_dir", folder)

    # Conversion

    def _convert(self) -> None:
        sources = self._list.paths()
        output_dir = self._output_dir()
        if not sources:
            return
        if not output_dir.is_dir():
            QMessageBox.warning(self, "Folder Not Found",
                                f"The folder {output_dir} no longer exists. Choose another folder.")
            return
        self._save_settings()
        if self._merged.isChecked():
            merged_path = output_dir / sanitize_pdf_name(self._name_edit.text() or "Combined", "Combined")
            if merged_path.exists() and QMessageBox.question(
                    self, "Replace File?", f"“{merged_path.name}” already exists in this folder. Replace it?"
            ) != QMessageBox.StandardButton.Yes:
                return
            worker = ConversionWorker(sources, self._pdf_settings(), merged_path=merged_path)
        else:
            worker = ConversionWorker(sources, self._pdf_settings(), output_dir=output_dir)
        self._start(worker)

    def _start(self, worker: ConversionWorker) -> None:
        self._thread = QThread(self)
        self._worker = worker
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._progress.setRange(0, len(self._list.paths()))
        self._progress.setValue(0)
        self._progress.show()
        self._open_button.hide()
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
            self._set_status(f"Converting {done + 1} of {total}: {name}")

    def _on_finished(self, report: ConversionReport) -> None:
        self._thread = None
        self._worker = None
        self._progress.hide()
        self._cancel_button.hide()
        self._refresh()

        if report.outputs:
            self._last_output = report.outputs[0]
            self._open_button.show()
        if report.cancelled:
            kept = f" {len(report.outputs)} PDF{'s' if len(report.outputs) != 1 else ''} were kept." \
                if report.outputs else ""
            self._set_status(f"Conversion cancelled.{kept}")
        elif report.outputs and not report.failures:
            done = (f"Saved {report.outputs[0].name}" if len(report.outputs) == 1
                    else f"Created {len(report.outputs)} PDFs")
            self._set_status(f"✓ {done} in {report.outputs[0].parent.name or report.outputs[0].parent}.",
                             "success")
        elif report.outputs:
            self._set_status(f"Finished with {len(report.failures)} problem"
                             f"{'s' if len(report.failures) != 1 else ''}.", "error")
        else:
            self._set_status("Conversion failed.", "error")
        if report.failures:
            lines = "\n".join(f"• {path.name}: {error}" for path, error in report.failures[:12])
            more = f"\n…and {len(report.failures) - 12} more." if len(report.failures) > 12 else ""
            QMessageBox.warning(self, "Some Files Were Not Converted", f"{lines}{more}")

    def _open_output(self) -> None:
        if self._last_output is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_output.parent)))

    def closeEvent(self, event) -> None:
        self._save_settings()
        if self._worker is not None:
            self._worker.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(10000)
        self._thumbnails.shutdown()
        super().closeEvent(event)
