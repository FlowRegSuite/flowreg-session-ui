from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .local_runner import LocalRunner
from .message_dialogs import show_error_text, show_exception, show_warning
from .state import AppState


class RunLocalTab(QWidget):
    def __init__(
        self,
        state: AppState,
        config_provider: Callable[[], Any | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._config_provider = config_provider
        self._runner = LocalRunner(self)

        self.run_all_button = QPushButton("Run All Stages", self)
        self.run_stage1_button = QPushButton("Run Stage1", self)
        self.run_stage2_button = QPushButton("Run Stage2", self)
        self.run_stage3_button = QPushButton("Run Stage3", self)

        self.run_all_button.clicked.connect(lambda: self._start_run("all"))
        self.run_stage1_button.clicked.connect(lambda: self._start_run("stage1"))
        self.run_stage2_button.clicked.connect(lambda: self._start_run("stage2"))
        self.run_stage3_button.clicked.connect(lambda: self._start_run("stage3"))

        self.resolved_paths_view = QPlainTextEdit(self)
        self.resolved_paths_view.setReadOnly(True)
        self.resolved_paths_view.setPlaceholderText("Resolved output paths will appear here.")

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.run_all_button)
        button_layout.addWidget(self.run_stage1_button)
        button_layout.addWidget(self.run_stage2_button)
        button_layout.addWidget(self.run_stage3_button)

        layout = QVBoxLayout(self)
        layout.addLayout(button_layout)
        layout.addWidget(self.resolved_paths_view)
        layout.addWidget(self.log_view)

        self._runner.log_emitted.connect(self._append_log)
        self._runner.run_started.connect(self._on_run_started)
        self._runner.run_finished.connect(self._on_run_finished)
        self._runner.run_failed.connect(self._on_run_failed)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.run_all_button.setEnabled(enabled)
        self.run_stage1_button.setEnabled(enabled)
        self.run_stage2_button.setEnabled(enabled)
        self.run_stage3_button.setEnabled(enabled)

    def _append_log(self, text: str) -> None:
        if not text:
            return
        self.log_view.appendPlainText(text)

    def _show_resolved_paths(self, config: Any) -> None:
        try:
            resolved = config.resolve_output_paths()
        except Exception as exc:
            self.resolved_paths_view.setPlainText(f"Failed to resolve output paths:\n{exc}")
            return
        self.resolved_paths_view.setPlainText(str(resolved))

    def _start_run(self, mode: str) -> None:
        config = self._config_provider()
        if config is None:
            return

        if self._runner.is_running():
            show_warning(self, "Busy", "A local run is already in progress.")
            return

        self._state.config = config
        self._show_resolved_paths(config)
        self._append_log(f"Starting local run mode: {mode}")

        try:
            self._runner.start(config, mode)
        except Exception as exc:
            show_exception(self, "Local Run Error", exc)

    def _on_run_started(self) -> None:
        self._set_buttons_enabled(False)

    def _on_run_finished(self, exit_code: int) -> None:
        self._set_buttons_enabled(True)
        if exit_code == 0:
            self._append_log("Local run finished successfully.")

    def _on_run_failed(self, message: str) -> None:
        self._append_log(message)
        show_error_text(self, "Local Run Failed", message)
