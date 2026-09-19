from __future__ import annotations

import copy
import os
import subprocess
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .config import cache_dir, config_path, load_config, save_config
from .crop_picker import CropPickerDialog
from .engine import matching_rule, resolve_text_payload
from .models import Rule
from .platforms import get_platform_backend
from .processes import list_processes, list_user_app_processes


APP_STYLE = """
QMainWindow {
    background: palette(window);
}
QWidget {
    font-size: 14px;
}
QFrame#card {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 12px;
}
QFrame#sidebar {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 12px;
}
QLineEdit, QComboBox, QSpinBox {
    min-height: 34px;
    padding-left: 8px;
    padding-right: 8px;
    border: 1px solid palette(mid);
    border-radius: 8px;
    background: palette(base);
}
QPushButton {
    min-height: 34px;
    padding-left: 13px;
    padding-right: 13px;
    border-radius: 8px;
}
QPushButton#primaryButton {
    min-height: 42px;
    font-weight: 600;
}
QPushButton#dangerButton {
    font-weight: 600;
}
QListWidget {
    border: none;
    background: transparent;
    outline: none;
}
QListWidget::item {
    padding: 10px 8px;
    border-radius: 8px;
}
QListWidget::item:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}
QLabel#sectionTitle {
    font-size: 17px;
    font-weight: 600;
}
QLabel#pageTitle {
    font-size: 24px;
    font-weight: 700;
}
QLabel#muted {
    color: palette(mid);
}
"""


def _card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(11)

    title_label = QLabel(title)
    title_label.setObjectName("sectionTitle")
    layout.addWidget(title_label)

    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("muted")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

    return frame, layout


class ProcessDialog(QDialog):
    def __init__(self, platform, parent=None):
        super().__init__(parent)
        self.platform = platform
        self.setWindowTitle("Choose an app")
        self.resize(620, 650)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Choose a running app")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "By default, this shows the windows KDE says belong in your taskbar. "
            "That includes Steam games and other apps that do not have a normal launcher entry."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Search running apps")
        layout.addWidget(self.filter)

        picker_options = QHBoxLayout()
        self.show_background = QCheckBox("Show background and system processes")
        self.refresh_apps = QPushButton("Refresh")
        picker_options.addWidget(self.show_background)
        picker_options.addStretch(1)
        picker_options.addWidget(self.refresh_apps)
        layout.addLayout(picker_options)

        self.list = QListWidget()
        self.list.setSpacing(2)
        layout.addWidget(self.list, 1)

        self.empty = QLabel("")
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("Use this app")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.filter.textChanged.connect(self.refresh)
        self.show_background.stateChanged.connect(self.reload_items)
        self.refresh_apps.clicked.connect(self.reload_items)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._cached_items = []
        self._using_fallback = False
        self.reload_items()

    def reload_items(self, *_):
        self._using_fallback = False
        if self.show_background.isChecked():
            self._cached_items = list_processes()
        else:
            try:
                self._cached_items = self.platform.taskbar_processes()
            except Exception:
                self._cached_items = []

            if not self._cached_items:
                # Keep the old desktop-launcher heuristic as a fallback for
                # non-KDE desktops or a temporary KWin D-Bus failure.
                self._cached_items = list_user_app_processes()
                self._using_fallback = True

        self.refresh()

    def _items(self):
        return self._cached_items

    def refresh(self, *_):
        needle = self.filter.text().casefold().strip()
        self.list.clear()

        items = self._items()
        for proc in items:
            searchable = (
                f"{proc.display} {proc.name} {proc.exe} "
                f"{proc.window_title} {proc.app_id}"
            ).casefold()
            if needle and needle not in searchable:
                continue

            item = QListWidgetItem(proc.display)
            item.setData(Qt.UserRole, proc)

            tooltip = [proc.exe or "Executable path unavailable", f"PID {proc.pid}"]
            if proc.window_title and proc.window_title != proc.display:
                tooltip.append(f"Window: {proc.window_title}")
            if proc.app_id:
                tooltip.append(f"App ID: {proc.app_id}")
            item.setToolTip("\n".join(tooltip))

            self.list.addItem(item)

        if self.list.count():
            if self._using_fallback and not self.show_background.isChecked():
                self.empty.setText(
                    "KDE taskbar detection was unavailable, so this list is using "
                    "the launcher-based fallback."
                )
            else:
                self.empty.setText("")
            self.list.setCurrentRow(0)
        elif self.show_background.isChecked():
            self.empty.setText("No running process matches your search.")
        else:
            self.empty.setText(
                "No taskbar app matched. Press Refresh if you just opened it, or enable "
                "“Show background and system processes” for unusual headless apps."
            )

    def selected_process(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Discord Presence Bridge")
        self.resize(1180, 820)
        self.setStyleSheet(APP_STYLE)

        self.platform = get_platform_backend()
        self.config = load_config()
        self.current_rule: Rule | None = None
        self._loading = False

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("Discord Presence Bridge")
        title.setObjectName("pageTitle")
        heading.addWidget(title)
        subtitle = QLabel("Choose what your friends see on Discord when you use an app.")
        subtitle.setObjectName("muted")
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)

        self.save_apply_btn = QPushButton("Save & Apply")
        self.save_apply_btn.setObjectName("primaryButton")
        header.addWidget(self.save_apply_btn)
        outer.addLayout(header)

        connection_card, connection = _card(
            "Discord connection",
            "Paste the Application ID from your Discord Developer Portal app once. "
            "You can leave everything else alone for the first test.",
        )
        app_row = QHBoxLayout()
        self.app_id = QLineEdit(self.config.discord_application_id)
        self.app_id.setPlaceholderText("Discord Application ID")
        app_row.addWidget(self.app_id, 1)
        self.connection_status = QLabel("")
        self.connection_status.setObjectName("muted")
        app_row.addWidget(self.connection_status)
        connection.addLayout(app_row)
        outer.addWidget(connection_card)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        lbox = QVBoxLayout(sidebar)
        lbox.setContentsMargins(14, 14, 14, 14)
        lbox.setSpacing(10)

        sidebar_title = QLabel("Activities")
        sidebar_title.setObjectName("sectionTitle")
        lbox.addWidget(sidebar_title)

        sidebar_help = QLabel("Each activity is a rule for one app.")
        sidebar_help.setObjectName("muted")
        sidebar_help.setWordWrap(True)
        lbox.addWidget(sidebar_help)

        self.rules = QListWidget()
        self.rules.setSpacing(2)
        lbox.addWidget(self.rules, 1)

        self.add_btn = QPushButton("+ New activity")
        self.add_btn.setObjectName("primaryButton")
        lbox.addWidget(self.add_btn)

        small_actions = QHBoxLayout()
        self.dup_btn = QPushButton("Copy")
        self.delete_btn = QPushButton("Remove")
        self.delete_btn.setObjectName("dangerButton")
        small_actions.addWidget(self.dup_btn)
        small_actions.addWidget(self.delete_btn)
        lbox.addLayout(small_actions)

        splitter.addWidget(sidebar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        editor_host = QWidget()
        self.editor_layout = QVBoxLayout(editor_host)
        self.editor_layout.setContentsMargins(8, 0, 8, 8)
        self.editor_layout.setSpacing(12)
        scroll.setWidget(editor_host)
        splitter.addWidget(scroll)
        splitter.setSizes([285, 850])

        self._build_trigger_card()
        self._build_text_card()
        self._build_artwork_card()
        self._build_preview_card()
        self._build_advanced_card()
        self.editor_layout.addStretch(1)

        footer = QHBoxLayout()
        self.logs_btn = QPushButton("View service log")
        self.save_only_btn = QPushButton("Save without restarting")
        footer.addWidget(self.logs_btn)
        footer.addStretch(1)
        footer.addWidget(self.save_only_btn)

        self.status = QLabel(f"Config: {config_path()}")
        self.status.setObjectName("muted")
        footer.addWidget(self.status)
        outer.addLayout(footer)

        self.add_btn.clicked.connect(self.add_rule)
        self.dup_btn.clicked.connect(self.duplicate_rule)
        self.delete_btn.clicked.connect(self.delete_rule)
        self.rules.currentRowChanged.connect(self.select_rule)
        self.pick_process.clicked.connect(self.choose_process)
        self.pick_crop.clicked.connect(self.choose_crop)
        self.save_only_btn.clicked.connect(self.save_all)
        self.save_apply_btn.clicked.connect(self.save_restart)
        self.logs_btn.clicked.connect(self.show_logs)
        self.app_id.textChanged.connect(self.update_connection_status)
        self.large_mode.currentIndexChanged.connect(self.update_artwork_visibility)
        self.small_mode.currentIndexChanged.connect(self.update_artwork_visibility)

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
        else:
            self.add_rule()

        self.update_artwork_visibility()
        self.update_connection_status()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_preview)
        self.timer.start(4000)
        self.update_preview()

    def _build_trigger_card(self):
        card, layout = _card(
            "1. Choose the app",
            "This activity turns on while the selected app is running.",
        )

        self.enabled = QCheckBox("Activity enabled")
        layout.addWidget(self.enabled)

        row = QHBoxLayout()
        self.process_match = QLineEdit()
        self.process_match.setPlaceholderText("No app selected")
        self.pick_process = QPushButton("Choose running app")
        row.addWidget(self.process_match, 1)
        row.addWidget(self.pick_process)
        layout.addLayout(row)

        note = QLabel(
            "The picker follows KDE's taskbar list, so Steam games should appear here too."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.editor_layout.addWidget(card)

    def _build_text_card(self):
        card, layout = _card(
            "2. Choose what Discord says",
            "The first three lines are the useful part. You can type normal text or use "
            "dynamic values such as {media.title}.",
        )

        form = QFormLayout()
        form.setSpacing(10)

        self.activity_type = QComboBox()
        self.activity_type.addItem("Playing", "playing")
        self.activity_type.addItem("Watching", "watching")
        self.activity_type.addItem("Listening", "listening")
        self.activity_type.addItem("Competing", "competing")
        form.addRow("Action", self.activity_type)

        self.activity_name = QLineEdit()
        self.activity_name.setPlaceholderText("Example: Firefox")
        form.addRow("Main line", self.activity_name)

        self.details = QLineEdit()
        self.details.setPlaceholderText("Example: Watching {media.title}")
        form.addRow("Second line", self.details)

        self.state = QLineEdit()
        self.state.setPlaceholderText("Example: {media.artist}")
        form.addRow("Third line", self.state)

        layout.addLayout(form)

        token_help = QLabel(
            "Dynamic values:  {media.title}  {media.artist}  {window.title}  {process.name}"
        )
        token_help.setObjectName("muted")
        token_help.setWordWrap(True)
        layout.addWidget(token_help)

        self.media_only = QCheckBox("Only show this activity while media is actually playing")
        layout.addWidget(self.media_only)

        self.editor_layout.addWidget(card)

    def _build_artwork_card(self):
        card, layout = _card(
            "3. Choose the picture",
            "Use a media thumbnail, the app icon, a fixed image, or drag-select part of your screen.",
        )

        form = QFormLayout()
        form.setSpacing(10)

        self.large_mode = QComboBox()
        self.large_mode.addItem("No main picture", "none")
        self.large_mode.addItem("Media thumbnail / album art", "media_art")
        self.large_mode.addItem("App icon", "app_icon")
        self.large_mode.addItem("Fixed image or Discord asset", "static")
        self.large_mode.addItem("Capture part of my screen", "screen_crop")
        form.addRow("Main picture", self.large_mode)

        self.large_value_label = QLabel("Image / asset")
        self.large_value = QLineEdit()
        self.large_value.setPlaceholderText("HTTPS URL or Discord asset key")
        form.addRow(self.large_value_label, self.large_value)

        self.crop_label_title = QLabel("Screen area")
        crop_widget = QWidget()
        croprow = QHBoxLayout(crop_widget)
        croprow.setContentsMargins(0, 0, 0, 0)
        self.crop_label = QLabel("No area selected")
        self.crop_label.setObjectName("muted")
        self.pick_crop = QPushButton("Select area")
        croprow.addWidget(self.crop_label, 1)
        croprow.addWidget(self.pick_crop)
        form.addRow(self.crop_label_title, crop_widget)
        self.crop_widget = crop_widget

        self.small_mode = QComboBox()
        self.small_mode.addItem("No corner icon", "none")
        self.small_mode.addItem("Media thumbnail / album art", "media_art")
        self.small_mode.addItem("App icon", "app_icon")
        self.small_mode.addItem("Fixed image or Discord asset", "static")
        form.addRow("Corner icon", self.small_mode)

        self.small_value_label = QLabel("Corner image / asset")
        self.small_value = QLineEdit()
        self.small_value.setPlaceholderText("HTTPS URL or Discord asset key")
        form.addRow(self.small_value_label, self.small_value)

        layout.addLayout(form)

        self.public_relay = QCheckBox(
            "Allow local pictures (app icons / screen crops) to use a temporary public image link"
        )
        self.public_relay.setChecked(self.config.allow_public_crop_relay)
        layout.addWidget(self.public_relay)

        relay_note = QLabel(
            "Needed only for local images. Media artwork that already has an HTTPS URL does not "
            "need this. Screen crops are never shared unless this option is enabled."
        )
        relay_note.setObjectName("muted")
        relay_note.setWordWrap(True)
        layout.addWidget(relay_note)

        self.editor_layout.addWidget(card)

    def _build_preview_card(self):
        card, layout = _card(
            "Preview",
            "Resolved using what is running on your PC right now.",
        )
        self.preview = QLabel("No matching activity yet.")
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(80)
        layout.addWidget(self.preview)
        self.editor_layout.addWidget(card)

    def _build_advanced_card(self):
        card, layout = _card(
            "Advanced settings",
            "You normally do not need these. They are here for rule ordering, hover text, "
            "and refresh timing.",
        )

        self.advanced_toggle = QPushButton("Show advanced settings")
        self.advanced_toggle.setCheckable(True)
        layout.addWidget(self.advanced_toggle)

        self.advanced_body = QWidget()
        form = QFormLayout(self.advanced_body)

        self.label = QLineEdit()
        form.addRow("Rule nickname", self.label)

        self.priority = QSpinBox()
        self.priority.setRange(0, 9999)
        form.addRow("Rule priority", self.priority)

        self.large_text = QLineEdit()
        form.addRow("Main picture hover text", self.large_text)

        self.small_text = QLineEdit()
        form.addRow("Corner icon hover text", self.small_text)

        self.poll = QSpinBox()
        self.poll.setRange(1, 60)
        self.poll.setValue(round(self.config.update_interval_seconds))
        self.poll.setSuffix(" s")
        form.addRow("Activity refresh", self.poll)

        self.image_poll = QSpinBox()
        self.image_poll.setRange(5, 600)
        self.image_poll.setValue(round(self.config.image_update_seconds))
        self.image_poll.setSuffix(" s")
        form.addRow("Screen image refresh", self.image_poll)

        layout.addWidget(self.advanced_body)
        self.advanced_body.setVisible(False)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)

        self.editor_layout.addWidget(card)

    def _toggle_advanced(self, checked: bool):
        self.advanced_body.setVisible(checked)
        self.advanced_toggle.setText(
            "Hide advanced settings" if checked else "Show advanced settings"
        )

    def update_connection_status(self):
        if self.app_id.text().strip():
            self.connection_status.setText("Application ID set")
        else:
            self.connection_status.setText("Not configured yet")

    def update_artwork_visibility(self, *_):
        large_mode = self.large_mode.currentData()
        small_mode = self.small_mode.currentData()

        show_large_value = large_mode == "static"
        self.large_value.setVisible(show_large_value)
        self.large_value_label.setVisible(show_large_value)

        show_crop = large_mode == "screen_crop"
        self.crop_widget.setVisible(show_crop)
        self.crop_label_title.setVisible(show_crop)

        show_small_value = small_mode == "static"
        self.small_value.setVisible(show_small_value)
        self.small_value_label.setVisible(show_small_value)

    def refresh_rule_list(self):
        current_id = self.current_rule.id if self.current_rule else None
        self.rules.clear()
        target = -1
        for index, rule in enumerate(self.config.rules):
            prefix = "✓ " if rule.enabled else "○ "
            item = QListWidgetItem(prefix + rule.label)
            item.setData(Qt.UserRole, rule.id)
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
        self._set_combo_data(self.activity_type, r.activity_type)
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
        self.update_artwork_visibility()
        self._loading = False

    def write_form_to_rule(self, *_):
        if self._loading or not self.current_rule:
            return

        r = self.current_rule
        r.enabled = self.enabled.isChecked()
        r.label = self.label.text() or r.process_match or "Unnamed activity"
        r.priority = self.priority.value()
        r.process_match = self.process_match.text()
        r.activity_type = self.activity_type.currentData() or "playing"
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
        if row >= 0 and self.rules.item(row):
            self.rules.item(row).setText(("✓ " if r.enabled else "○ ") + r.label)

    def add_rule(self):
        self.write_form_to_rule()
        rule = Rule(label=f"Activity {len(self.config.rules) + 1}")
        self.config.rules.append(rule)
        self.current_rule = None
        self.refresh_rule_list()
        self.rules.setCurrentRow(len(self.config.rules) - 1)

    def duplicate_rule(self):
        if not self.current_rule:
            return
        clone = copy.deepcopy(self.current_rule)
        clone.id = Rule().id
        clone.label += " copy"
        self.config.rules.append(clone)
        self.current_rule = None
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
        else:
            self.add_rule()

    def choose_process(self):
        dialog = ProcessDialog(self.platform, self)
        if dialog.exec() != QDialog.Accepted:
            return

        proc = dialog.selected_process()
        if not proc:
            return

        self.process_match.setText(proc.name)

        if self.current_rule:
            generic_names = {
                f"Activity {self.rules.currentRow() + 1}",
                "Unnamed activity",
            }
            if self.current_rule.label in generic_names or self.current_rule.label.startswith("Activity "):
                self.label.setText(proc.display)

        if not self.activity_name.text().strip():
            self.activity_name.setText(proc.display)

    def update_crop_label(self):
        if not self.current_rule or not self.current_rule.crop.valid:
            self.crop_label.setText("No area selected")
            return
        c = self.current_rule.crop
        self.crop_label.setText(f"{c.width} × {c.height} pixels")

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
            QMessageBox.critical(self, "Screen capture failed", str(exc))
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
        self.update_connection_status()

    def save_all(self):
        self.pull_global_fields()
        save_config(self.config)
        self.status.setText("Saved")

    def save_restart(self):
        self.save_all()
        if os.name != "posix":
            QMessageBox.information(
                self,
                "Saved",
                "Windows autostart support is the next platform milestone.",
            )
            return

        service = "discord-presence-bridge.service"

        subprocess.run(
            ["systemctl", "--user", "reset-failed", service],
            text=True,
            capture_output=True,
            check=False,
        )

        cp = subprocess.run(
            ["systemctl", "--user", "restart", service],
            text=True,
            capture_output=True,
            check=False,
        )

        active = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", service],
            text=True,
            capture_output=True,
            check=False,
        )

        if cp.returncode == 0 and active.returncode == 0:
            self.status.setText("Saved and applied")
            return

        log = subprocess.run(
            [
                "journalctl",
                "--user",
                "-u",
                service,
                "-n",
                "60",
                "--no-pager",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        reason = (cp.stderr or cp.stdout or "The background service did not stay running.").strip()
        details = (log.stdout or log.stderr or "No service log was available.").strip()

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Could not apply settings")
        box.setText(reason)
        box.setInformativeText(
            "The app cleared systemd's failed/start-limit state and tried again. "
            "Open the detailed section below for the daemon log."
        )
        box.setDetailedText(details)
        box.exec()

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
        box.setWindowTitle("Discord Presence Bridge — service log")
        box.setText("Recent background-service output")
        box.setDetailedText(cp.stdout or cp.stderr or "No log output yet.")
        box.exec()

    def update_preview(self):
        self.write_form_to_rule()
        rule, process = matching_rule(self.config)
        if not rule or not process:
            self.preview.setText("Open one of your configured apps to see its resolved preview.")
            return

        try:
            payload, _media = resolve_text_payload(rule, process, self.platform)
        except Exception as exc:
            self.preview.setText(f"Preview error: {exc}")
            return

        if payload is None:
            self.preview.setText(
                f"{rule.label} is open, but the “media must be playing” option is not active yet."
            )
            return

        lines = [f"{payload.activity_type.title()} · {payload.name}"]
        if payload.details:
            lines.append(payload.details)
        if payload.state:
            lines.append(payload.state)

        if rule.large_image_mode == "screen_crop":
            lines.append("Picture: selected screen area")
        elif rule.large_image_mode == "app_icon":
            lines.append("Picture: app icon")
        elif rule.large_image_mode == "media_art":
            lines.append("Picture: media artwork")

        self.preview.setText("\n".join(lines))


def run_gui() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Discord Presence Bridge")
    window = MainWindow()
    window.show()
    return app.exec()
