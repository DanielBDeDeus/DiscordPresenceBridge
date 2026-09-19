from __future__ import annotations

import copy
import os
from pathlib import Path
import subprocess
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .config import cache_dir, config_path, load_config, save_config
from .crop_picker import CropPickerDialog
from .engine import matching_rule, resolve_text_payload
from .models import AppConfig, Rule
from .platforms import get_platform_backend
from .processes import list_processes


class ProcessDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose running application")
        self.resize(650, 560)
        layout = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter running processes…")
        layout.addWidget(self.filter)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.items = list_processes()
        self.filter.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        needle = self.filter.text().casefold()
        self.list.clear()
        seen = set()
        for proc in self.items:
            key = (proc.name, proc.exe)
            if key in seen:
                continue
            seen.add(key)
            text = f"{proc.name}    {proc.exe}"
            if needle and needle not in text.casefold():
                continue
            item = QListWidgetItem(text)
            item.setData(256, proc)
            self.list.addItem(item)

    def selected_process(self):
        item = self.list.currentItem()
        return item.data(256) if item else None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Discord Presence Bridge")
        self.resize(1220, 820)
        self.platform = get_platform_backend()
        self.config = load_config()
        self.current_rule: Rule | None = None
        self._loading = False

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)

        settings = QGroupBox("Global settings")
        sform = QFormLayout(settings)
        self.app_id = QLineEdit(self.config.discord_application_id)
        self.app_id.setPlaceholderText("Discord Application ID")
        sform.addRow("Discord Application ID", self.app_id)

        self.poll = QSpinBox()
        self.poll.setRange(1, 60)
        self.poll.setValue(round(self.config.update_interval_seconds))
        self.poll.setSuffix(" s")
        sform.addRow("Text/process refresh", self.poll)

        self.image_poll = QSpinBox()
        self.image_poll.setRange(5, 600)
        self.image_poll.setValue(round(self.config.image_update_seconds))
        self.image_poll.setSuffix(" s")
        sform.addRow("Live crop refresh", self.image_poll)

        self.public_relay = QCheckBox(
            "Allow local artwork (screen crops/app icons) through a temporary public HTTPS relay"
        )
        self.public_relay.setChecked(self.config.allow_public_crop_relay)
        sform.addRow("", self.public_relay)
        outer.addWidget(settings)

        splitter = QSplitter()
        outer.addWidget(splitter, 1)

        left = QWidget()
        lbox = QVBoxLayout(left)
        self.rules = QListWidget()
        lbox.addWidget(self.rules, 1)
        row = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.dup_btn = QPushButton("Duplicate")
        self.delete_btn = QPushButton("Delete")
        row.addWidget(self.add_btn)
        row.addWidget(self.dup_btn)
        row.addWidget(self.delete_btn)
        lbox.addLayout(row)
        splitter.addWidget(left)

        right = QWidget()
        rbox = QVBoxLayout(right)

        formbox = QGroupBox("Selected activity rule")
        form = QFormLayout(formbox)

        self.enabled = QCheckBox()
        form.addRow("Enabled", self.enabled)

        self.label = QLineEdit()
        form.addRow("Rule label", self.label)

        self.priority = QSpinBox()
        self.priority.setRange(0, 9999)
        form.addRow("Priority (lower wins)", self.priority)

        prow = QHBoxLayout()
        self.process_match = QLineEdit()
        self.pick_process = QPushButton("Choose running app…")
        prow.addWidget(self.process_match, 1)
        prow.addWidget(self.pick_process)
        form.addRow("Process contains", prow)

        self.activity_type = QComboBox()
        self.activity_type.addItems(["playing", "watching", "listening", "competing"])
        form.addRow("Activity type", self.activity_type)

        self.activity_name = QLineEdit()
        form.addRow("Activity name", self.activity_name)

        self.details = QLineEdit()
        form.addRow("Details", self.details)

        self.state = QLineEdit()
        form.addRow("State", self.state)

        self.media_only = QCheckBox("Only publish while MPRIS media reports Playing")
        form.addRow("", self.media_only)

        self.large_mode = QComboBox()
        self.large_mode.addItem("None", "none")
        self.large_mode.addItem("Static asset key / HTTPS URL", "static")
        self.large_mode.addItem("Current MPRIS media artwork", "media_art")
        self.large_mode.addItem("Automatic application icon (via HTTPS relay)", "app_icon")
        self.large_mode.addItem("Selected live screen region", "screen_crop")
        form.addRow("Large image source", self.large_mode)

        self.large_value = QLineEdit()
        self.large_value.setPlaceholderText("asset key, HTTPS URL, or template")
        form.addRow("Large image value", self.large_value)

        croprow = QHBoxLayout()
        self.crop_label = QLabel("No crop selected")
        self.pick_crop = QPushButton("Select screen region…")
        croprow.addWidget(self.crop_label, 1)
        croprow.addWidget(self.pick_crop)
        form.addRow("Screen crop", croprow)

        self.large_text = QLineEdit()
        form.addRow("Large image hover text", self.large_text)

        self.small_mode = QComboBox()
        self.small_mode.addItem("None", "none")
        self.small_mode.addItem("Static asset key / HTTPS URL", "static")
        self.small_mode.addItem("Current MPRIS media artwork", "media_art")
        self.small_mode.addItem("Automatic application icon (via HTTPS relay)", "app_icon")
        form.addRow("Small image source", self.small_mode)

        self.small_value = QLineEdit()
        form.addRow("Small image value", self.small_value)

        self.small_text = QLineEdit()
        form.addRow("Small image hover text", self.small_text)

        rbox.addWidget(formbox)

        help_text = QLabel(
            "Template variables: {process.name}, {process.exe}, {process.pid}, "
            "{media.title}, {media.artist}, {media.album}, {media.art_url}, "
            "{media.player}, {window.title}, {window.app_id}"
        )
        help_text.setWordWrap(True)
        rbox.addWidget(help_text)

        preview_box = QGroupBox("Current resolved preview")
        pv = QVBoxLayout(preview_box)
        self.preview = QLabel("No matching rule")
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(100)
        pv.addWidget(self.preview)
        rbox.addWidget(preview_box)

        splitter.addWidget(right)
        splitter.setSizes([310, 880])

        bottom = QHBoxLayout()
        self.save_btn = QPushButton("Save configuration")
        self.restart_btn = QPushButton("Save + restart background service")
        self.logs_btn = QPushButton("Open recent service log")
        bottom.addWidget(self.save_btn)
        bottom.addWidget(self.restart_btn)
        bottom.addWidget(self.logs_btn)
        outer.addLayout(bottom)

        self.status = QLabel(f"Config: {config_path()}")
        outer.addWidget(self.status)

        self.add_btn.clicked.connect(self.add_rule)
        self.dup_btn.clicked.connect(self.duplicate_rule)
        self.delete_btn.clicked.connect(self.delete_rule)
        self.rules.currentRowChanged.connect(self.select_rule)
        self.pick_process.clicked.connect(self.choose_process)
        self.pick_crop.clicked.connect(self.choose_crop)
        self.save_btn.clicked.connect(self.save_all)
        self.restart_btn.clicked.connect(self.save_restart)
        self.logs_btn.clicked.connect(self.show_logs)

        for widget in (
            self.enabled,
            self.label,
            self.priority,
            self.process_match,
            self.activity_type,
            self.activity_name,
            self.details,
            self.state,
            self.media_only,
            self.large_mode,
            self.large_value,
            self.large_text,
            self.small_mode,
            self.small_value,
            self.small_text,
        ):
            signal = getattr(widget, "textChanged", None)
            if signal:
                signal.connect(self.write_form_to_rule)
            signal = getattr(widget, "valueChanged", None)
            if signal:
                signal.connect(self.write_form_to_rule)
            signal = getattr(widget, "stateChanged", None)
            if signal:
                signal.connect(self.write_form_to_rule)
            signal = getattr(widget, "currentIndexChanged", None)
            if signal:
                signal.connect(self.write_form_to_rule)

        self.refresh_rule_list()
        if self.config.rules:
            self.rules.setCurrentRow(0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_preview)
        self.timer.start(4000)
        self.update_preview()

    def refresh_rule_list(self):
        current_id = self.current_rule.id if self.current_rule else None
        self.rules.clear()
        target = -1
        for index, rule in enumerate(self.config.rules):
            prefix = "● " if rule.enabled else "○ "
            item = QListWidgetItem(prefix + rule.label)
            item.setData(256, rule.id)
            self.rules.addItem(item)
            if rule.id == current_id:
                target = index
        if target >= 0:
            self.rules.setCurrentRow(target)

    def select_rule(self, row: int):
        self.write_form_to_rule()
        if row < 0 or row >= len(self.config.rules):
            self.current_rule = None
            return
        self.current_rule = self.config.rules[row]
        self.load_rule()

    def _set_combo_data(self, combo, value):
        index = combo.findData(value)
        if index < 0:
            index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def load_rule(self):
        if not self.current_rule:
            return
        r = self.current_rule
        self._loading = True
        self.enabled.setChecked(r.enabled)
        self.label.setText(r.label)
        self.priority.setValue(r.priority)
        self.process_match.setText(r.process_match)
        self.activity_type.setCurrentText(r.activity_type)
        self.activity_name.setText(r.activity_name)
        self.details.setText(r.details_template)
        self.state.setText(r.state_template)
        self.media_only.setChecked(r.only_when_media_playing)
        self._set_combo_data(self.large_mode, r.large_image_mode)
        self.large_value.setText(r.large_image_value)
        self.large_text.setText(r.large_text_template)
        self._set_combo_data(self.small_mode, r.small_image_mode)
        self.small_value.setText(r.small_image_value)
        self.small_text.setText(r.small_text_template)
        self.update_crop_label()
        self._loading = False

    def write_form_to_rule(self, *_):
        if self._loading or not self.current_rule:
            return
        r = self.current_rule
        r.enabled = self.enabled.isChecked()
        r.label = self.label.text() or "Unnamed rule"
        r.priority = self.priority.value()
        r.process_match = self.process_match.text()
        r.activity_type = self.activity_type.currentText()
        r.activity_name = self.activity_name.text()
        r.details_template = self.details.text()
        r.state_template = self.state.text()
        r.only_when_media_playing = self.media_only.isChecked()
        r.large_image_mode = self.large_mode.currentData()
        r.large_image_value = self.large_value.text()
        r.large_text_template = self.large_text.text()
        r.small_image_mode = self.small_mode.currentData()
        r.small_image_value = self.small_value.text()
        r.small_text_template = self.small_text.text()
        row = self.rules.currentRow()
        if row >= 0:
            self.rules.item(row).setText(("● " if r.enabled else "○ ") + r.label)

    def add_rule(self):
        self.write_form_to_rule()
        rule = Rule(label=f"Rule {len(self.config.rules) + 1}")
        self.config.rules.append(rule)
        self.current_rule = rule
        self.refresh_rule_list()
        self.rules.setCurrentRow(len(self.config.rules) - 1)

    def duplicate_rule(self):
        if not self.current_rule:
            return
        clone = copy.deepcopy(self.current_rule)
        clone.id = Rule().id
        clone.label += " copy"
        self.config.rules.append(clone)
        self.current_rule = clone
        self.refresh_rule_list()
        self.rules.setCurrentRow(len(self.config.rules) - 1)

    def delete_rule(self):
        row = self.rules.currentRow()
        if row < 0:
            return
        self.config.rules.pop(row)
        self.current_rule = None
        self.refresh_rule_list()
        if self.config.rules:
            self.rules.setCurrentRow(min(row, len(self.config.rules) - 1))

    def choose_process(self):
        dialog = ProcessDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        proc = dialog.selected_process()
        if not proc:
            return
        self.process_match.setText(proc.name)
        if self.current_rule and self.current_rule.label.startswith("Rule "):
            self.label.setText(proc.name)

    def update_crop_label(self):
        if not self.current_rule or not self.current_rule.crop.valid:
            self.crop_label.setText("No crop selected")
            return
        c = self.current_rule.crop
        self.crop_label.setText(f"{c.width}×{c.height} at ({c.x}, {c.y})")

    def choose_crop(self):
        if not self.current_rule:
            return
        shot = cache_dir() / "crop-picker-fullscreen.png"
        try:
            self.hide()
            QApplication.processEvents()
            time.sleep(0.35)
            self.platform.capture_fullscreen(shot)
        except Exception as exc:
            self.show()
            QMessageBox.critical(self, "Capture failed", str(exc))
            return
        finally:
            self.show()

        picker = CropPickerDialog(str(shot), self)
        if picker.exec() == QDialog.Accepted:
            self.current_rule.crop = picker.selected_crop()
            self.large_mode.setCurrentIndex(self.large_mode.findData("screen_crop"))
            self.update_crop_label()

    def pull_global_fields(self):
        self.write_form_to_rule()
        self.config.discord_application_id = self.app_id.text().strip()
        self.config.update_interval_seconds = float(self.poll.value())
        self.config.image_update_seconds = float(self.image_poll.value())
        self.config.allow_public_crop_relay = self.public_relay.isChecked()

    def save_all(self):
        self.pull_global_fields()
        save_config(self.config)
        self.status.setText(f"Saved: {config_path()}")

    def save_restart(self):
        self.save_all()
        if os.name != "posix":
            QMessageBox.information(
                self,
                "Saved",
                "Windows autostart/service support is the next platform milestone.",
            )
            return
        cp = subprocess.run(
            ["systemctl", "--user", "restart", "discord-presence-bridge.service"],
            text=True,
            capture_output=True,
            check=False,
        )
        if cp.returncode == 0:
            self.status.setText("Saved and restarted background service")
        else:
            QMessageBox.critical(
                self,
                "Service restart failed",
                (cp.stderr or cp.stdout or "unknown systemctl failure").strip(),
            )

    def show_logs(self):
        if os.name != "posix":
            return
        cp = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                "discord-presence-bridge.service",
                "-n",
                "80",
                "--no-pager",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        box = QMessageBox(self)
        box.setWindowTitle("Discord Presence Bridge — recent service log")
        box.setText("Recent daemon output")
        box.setDetailedText(cp.stdout or cp.stderr or "No log output yet.")
        box.exec()

    def update_preview(self):
        self.write_form_to_rule()
        rule, process = matching_rule(self.config)
        if not rule or not process:
            self.preview.setText("No configured rule currently matches a running process.")
            return
        try:
            payload, media = resolve_text_payload(rule, process, self.platform)
        except Exception as exc:
            self.preview.setText(f"Preview error: {exc}")
            return
        if payload is None:
            self.preview.setText(
                f"{rule.label} matches {process.name}, but its media-playing condition is false."
            )
            return
        crop_note = ""
        if rule.large_image_mode == "screen_crop":
            crop_note = "\nLarge image: selected live screen crop"
        elif payload.large_image:
            crop_note = f"\nLarge image: {payload.large_image}"
        self.preview.setText(
            f"{payload.activity_type.title()} — {payload.name}\n"
            f"{payload.details}\n"
            f"{payload.state}"
            f"{crop_note}"
        )


def run_gui() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Discord Presence Bridge")
    window = MainWindow()
    window.show()
    return app.exec()
