from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .config_form import SessionConfigForm
from .config_io import load_config_from_file, save_config_to_yaml
from .message_dialogs import show_exception, show_info
from .state import AppState


class ConfigTab(QWidget):
    config_updated = Signal(object)

    def __init__(
        self, state: AppState, session_config_cls: type[Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._session_config_cls = session_config_cls

        self.form = SessionConfigForm(session_config_cls, self)

        self.loaded_path_label = QLabel("No config file loaded", self)

        load_button = QPushButton("Load Config", self)
        save_button = QPushButton("Save Config", self)
        validate_button = QPushButton("Validate", self)
        reset_button = QPushButton("Reset to Defaults", self)

        load_button.clicked.connect(self._load_config)
        save_button.clicked.connect(self._save_config)
        validate_button.clicked.connect(self._validate_config)
        reset_button.clicked.connect(self._reset_defaults)

        button_layout = QHBoxLayout()
        button_layout.addWidget(load_button)
        button_layout.addWidget(save_button)
        button_layout.addWidget(validate_button)
        button_layout.addWidget(reset_button)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)

        layout = QVBoxLayout(self)
        layout.addWidget(self.loaded_path_label)
        layout.addLayout(button_layout)
        layout.addWidget(scroll)

    def get_validated_config(self, show_dialog: bool = False) -> Any | None:
        try:
            config = self.form.to_session_config()
        except Exception as exc:
            if show_dialog:
                show_exception(self, "Validation Error", exc)
            return None

        self._state.config = config
        self.config_updated.emit(config)
        return config

    def _load_config(self) -> None:
        path_text, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session Config",
            str(self._state.config_path or ""),
            "Config Files (*.yaml *.yml *.toml);;All Files (*)",
        )
        if not path_text:
            return

        path = Path(path_text)
        try:
            config = load_config_from_file(path, session_config_cls=self._session_config_cls)
        except Exception as exc:
            show_exception(self, "Load Error", exc)
            return

        self.form.set_from_config(config)
        self._state.config = config
        self._state.config_path = path
        self.loaded_path_label.setText(f"Loaded: {path}")
        self.config_updated.emit(config)

    def _save_config(self) -> None:
        config = self.get_validated_config(show_dialog=True)
        if config is None:
            return

        default_path = self._state.config_path or Path("session_config.yaml")
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session Config",
            str(default_path),
            "YAML (*.yaml *.yml)",
        )
        if not path_text:
            return

        path = Path(path_text)
        try:
            save_config_to_yaml(config, path, prefer_relative=True)
        except Exception as exc:
            show_exception(self, "Save Error", exc)
            return

        self._state.config_path = path
        self.loaded_path_label.setText(f"Saved: {path}")

    def _validate_config(self) -> None:
        config = self.get_validated_config(show_dialog=True)
        if config is None:
            return
        show_info(self, "Validation", "SessionConfig is valid.")

    def _reset_defaults(self) -> None:
        self.form.reset_to_defaults()
        self._state.config = None
        self.loaded_path_label.setText("No config file loaded")
