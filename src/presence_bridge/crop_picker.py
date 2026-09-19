from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from .models import CropRect


class CropCanvas(QWidget):
    changed = Signal()

    def __init__(self, image_path: str):
        super().__init__()
        self.image = QImage(image_path)
        if self.image.isNull():
            raise RuntimeError(f"Could not load screenshot: {image_path}")
        self.start = QPoint()
        self.end = QPoint()
        self.dragging = False
        self.selection = QRect()
        self.setMinimumSize(700, 420)
        self.setMouseTracking(True)

    def _image_draw_rect(self) -> QRect:
        available = self.rect()
        size = self.image.size()
        size.scale(available.size(), Qt.KeepAspectRatio)
        x = available.x() + (available.width() - size.width()) // 2
        y = available.y() + (available.height() - size.height()) // 2
        return QRect(x, y, size.width(), size.height())

    def _to_image(self, point: QPoint) -> QPoint:
        draw = self._image_draw_rect()
        if draw.width() <= 0 or draw.height() <= 0:
            return QPoint()
        x = (point.x() - draw.x()) * self.image.width() / draw.width()
        y = (point.y() - draw.y()) * self.image.height() / draw.height()
        return QPoint(
            max(0, min(self.image.width(), round(x))),
            max(0, min(self.image.height(), round(y))),
        )

    def crop_rect(self) -> CropRect:
        rect = self.selection.normalized()
        return CropRect(rect.x(), rect.y(), rect.width(), rect.height())

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.start = self._to_image(event.position().toPoint())
            self.end = self.start
            self.selection = QRect(self.start, self.end)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging:
            self.end = self._to_image(event.position().toPoint())
            self.selection = QRect(self.start, self.end).normalized()
            self.changed.emit()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.end = self._to_image(event.position().toPoint())
            self.selection = QRect(self.start, self.end).normalized()
            self.changed.emit()
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        draw = self._image_draw_rect()
        painter.drawImage(draw, self.image)

        painter.fillRect(draw, QColor(0, 0, 0, 120))

        selection = self.selection.normalized()
        if selection.width() > 1 and selection.height() > 1:
            sx = draw.width() / self.image.width()
            sy = draw.height() / self.image.height()
            visible = QRect(
                draw.x() + round(selection.x() * sx),
                draw.y() + round(selection.y() * sy),
                round(selection.width() * sx),
                round(selection.height() * sy),
            )
            painter.drawImage(visible, self.image, selection)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawRect(visible)


class CropPickerDialog(QDialog):
    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Discord artwork region")
        self.resize(1100, 720)
        layout = QVBoxLayout(self)
        self.help = QLabel(
            "Drag a rectangle over the part of the screenshot that should become "
            "Discord artwork. The saved coordinates are relative to this full desktop capture."
        )
        self.help.setWordWrap(True)
        layout.addWidget(self.help)

        self.canvas = CropCanvas(image_path)
        layout.addWidget(self.canvas, 1)

        self.coords = QLabel("No region selected")
        layout.addWidget(self.coords)
        self.canvas.changed.connect(self._update_coords)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._accept_if_valid)
        layout.addWidget(buttons)

    def _update_coords(self):
        crop = self.canvas.crop_rect()
        self.coords.setText(
            f"x={crop.x}, y={crop.y}, width={crop.width}, height={crop.height}"
        )

    def _accept_if_valid(self):
        if self.canvas.crop_rect().valid:
            self.accept()

    def selected_crop(self) -> CropRect:
        return self.canvas.crop_rect()
