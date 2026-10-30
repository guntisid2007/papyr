"""The sidebar: the output format, only the settings that apply to it and to the queued files, and where to save."""
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QSlider, QVBoxLayout,
                               QWidget)

from converter import ImageSettings, OutputFormat, PageSize, PdfSettings

from .file_queue import QueueSummary
from .widgets import ComboBox, DestinationPicker, SpinBox, secondary_label, section_label

PDF_DPI_CHOICES = (100, 150, 200, 300)
PAGE_SIZES = (PageSize.A4, PageSize.LETTER, PageSize.ORIGINAL)
PAGE_HINT = ("Wide photos get landscape pages. Images are scaled to fit without stretching. "
             "PDFs keep their own pages and text.")
DPI_HINT = "Sets the resolution of images made from PDF pages."
KEEPS_ALPHA_NOTE = "Transparency is preserved."
LOSES_ALPHA_NOTE = "Transparent areas become white."


def _group() -> tuple[QWidget, QVBoxLayout]:
    widget = QWidget()
    column = QVBoxLayout(widget)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(6)
    return widget, column


class SettingsPanel(QFrame):
    changed = Signal()  # the format or the combine choice changed

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedWidth(300)
        self._summary = QueueSummary()
        self._busy = False
        column = QVBoxLayout(self)
        column.setContentsMargins(16, 16, 16, 16)
        column.setSpacing(8)

        column.addWidget(section_label("Convert to"))
        self.format_combo = ComboBox()
        self.format_combo.setAccessibleName("Convert to")
        for fmt in OutputFormat:
            self.format_combo.addItem(fmt.label, fmt)
        self.format_combo.currentIndexChanged.connect(self._on_changed)
        column.addWidget(self.format_combo)
        column.addSpacing(12)
        self.options_heading = section_label("")
        column.addWidget(self.options_heading)
        column.addWidget(self._build_pdf_options())
        column.addWidget(self._build_image_options())
        column.addStretch(1)
        column.addWidget(section_label("Save to"))
        self.destination = DestinationPicker()
        column.addWidget(self.destination)
        self._inputs = [self.format_combo, self.combine_check, self.name_edit, self.page_combo, self.margin_spin,
                        self.quality_slider, self.dpi_combo, self.destination.change_button]

    def _build_pdf_options(self) -> QWidget:
        self.pdf_options, column = _group()
        self.combine_check = QCheckBox("Combine into one PDF")
        self.combine_check.setToolTip("Put every file into one PDF, in list order")
        self.combine_check.toggled.connect(self._on_changed)
        column.addWidget(self.combine_check)
        self.name_row, name_column = _group()
        name_column.setContentsMargins(0, 4, 0, 0)
        name_column.setSpacing(4)
        name_label = QLabel("PDF name")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Combined")
        self.name_edit.setAccessibleName("PDF name")
        self.name_edit.setAcceptDrops(False)  # dropped files go to the window and get added
        name_label.setBuddy(self.name_edit)
        name_column.addWidget(name_label)
        name_column.addWidget(self.name_edit)
        column.addWidget(self.name_row)
        column.addSpacing(2)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        column.addLayout(form)
        self.page_combo = ComboBox()
        self.page_combo.setAccessibleName("Page size")
        for size in PAGE_SIZES:
            self.page_combo.addItem(size.label, size)
        form.addRow("Page size", self.page_combo)
        self.margin_spin = SpinBox()
        self.margin_spin.setAccessibleName("Margins")
        self.margin_spin.setRange(0, 50)
        self.margin_spin.setDecimals(0)
        self.margin_spin.setSuffix(" mm")
        self.margin_spin.setValue(10)
        self.margin_spin.lineEdit().setAcceptDrops(False)
        form.addRow("Margins", self.margin_spin)
        column.addSpacing(2)
        column.addWidget(secondary_label(PAGE_HINT))
        return self.pdf_options

    def _build_image_options(self) -> QWidget:
        self.image_options, column = _group()
        column.setSpacing(10)

        self.quality_row, quality_column = _group()
        quality_column.setSpacing(2)
        top = QHBoxLayout()
        quality_column.addLayout(top)
        quality_label = QLabel("Quality")
        self.quality_value = QLabel()
        top.addWidget(quality_label)
        top.addStretch()
        top.addWidget(self.quality_value)
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setPageStep(10)
        self.quality_slider.setAccessibleName("Quality")
        self.quality_slider.setToolTip("Higher quality makes larger files")
        self.quality_slider.valueChanged.connect(lambda value: self.quality_value.setText(f"{value}%"))
        self.quality_slider.setValue(90)
        quality_label.setBuddy(self.quality_slider)
        quality_column.addWidget(self.quality_slider)
        column.addWidget(self.quality_row)

        self.dpi_row, dpi_column = _group()
        dpi_column.setSpacing(4)
        dpi_label = QLabel("PDF page resolution")
        self.dpi_combo = ComboBox()
        self.dpi_combo.setAccessibleName("PDF page resolution")
        for dpi in PDF_DPI_CHOICES:
            self.dpi_combo.addItem(f"{dpi} DPI", dpi)
        self.dpi_combo.setCurrentIndex(self.dpi_combo.findData(200))
        dpi_label.setBuddy(self.dpi_combo)
        dpi_column.addWidget(dpi_label)
        dpi_column.addWidget(self.dpi_combo)
        dpi_column.addWidget(secondary_label(DPI_HINT))
        column.addWidget(self.dpi_row)

        self.alpha_note = secondary_label()
        column.addWidget(self.alpha_note)
        return self.image_options

    # What the window reads

    def output_format(self) -> OutputFormat:
        return self.format_combo.currentData()

    def combine(self) -> bool:
        """Combine into one PDF. With fewer than two files there is nothing to combine, so each gets its own."""
        return (self.output_format() is OutputFormat.PDF and self._summary.count >= 2
                and self.combine_check.isChecked())

    def merged_name(self) -> str:
        return self.name_edit.text()

    def pdf_settings(self) -> PdfSettings:
        return PdfSettings(self.page_combo.currentData(), self.margin_spin.value())

    def image_settings(self) -> ImageSettings:
        return ImageSettings(self.output_format(), self.quality_slider.value(), self.dpi_combo.currentData())

    def focus_chain(self) -> list[QWidget]:
        return list(self._inputs)

    # What the window tells it

    def update_for(self, summary: QueueSummary, busy: bool) -> None:
        self._summary = summary
        self._busy = busy
        fmt = self.output_format()
        to_pdf = fmt is OutputFormat.PDF
        self.options_heading.setText(f"{fmt.label} options")
        self.pdf_options.setVisible(to_pdf)
        self.image_options.setVisible(not to_pdf)
        self.combine_check.setVisible(summary.count >= 2)
        self.name_row.setVisible(self.combine())
        self.quality_row.setVisible(fmt.has_quality)
        self.dpi_row.setVisible(summary.has_document)
        self.alpha_note.setText(KEEPS_ALPHA_NOTE if fmt.keeps_alpha else LOSES_ALPHA_NOTE)
        for widget in self._inputs:
            widget.setEnabled(not busy)

    def show_destination(self, folder: Path, problem: str | None) -> None:
        self.destination.show_folder(folder, problem)

    def _on_changed(self) -> None:
        self.update_for(self._summary, self._busy)
        self.changed.emit()

    # Remembered between launches

    def restore(self, settings: QSettings) -> None:
        self.combine_check.setChecked(settings.value("mode") == "merged")
        saved_format = OutputFormat.__members__.get(str(settings.value("output_format", "PDF")), OutputFormat.PDF)
        self.format_combo.setCurrentIndex(self.format_combo.findData(saved_format))
        self.quality_slider.setValue(int(settings.value("quality", 90)))
        dpi_index = self.dpi_combo.findData(int(settings.value("pdf_dpi", 200)))
        if dpi_index >= 0:
            self.dpi_combo.setCurrentIndex(dpi_index)
        page_index = self.page_combo.findText(str(settings.value("page_size", PageSize.A4.label)))
        if page_index >= 0:
            self.page_combo.setCurrentIndex(page_index)
        self.margin_spin.setValue(float(settings.value("margin_mm", 10)))
        self.name_edit.setText(str(settings.value("merged_name", "")))

    def save(self, settings: QSettings) -> None:
        settings.setValue("mode", "merged" if self.combine_check.isChecked() else "individual")
        settings.setValue("page_size", self.page_combo.currentText())
        settings.setValue("margin_mm", self.margin_spin.value())
        settings.setValue("merged_name", self.name_edit.text())
        settings.setValue("output_format", self.output_format().name)
        settings.setValue("quality", self.quality_slider.value())
        settings.setValue("pdf_dpi", self.dpi_combo.currentData())
