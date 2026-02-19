from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMainWindow, QTabWidget

from .config_tab import ConfigTab
from .pyflowreg_api import get_session_config_class
from .run_local_tab import RunLocalTab
from .run_remote_tab import RunRemoteTab
from .state import AppState


class MainWindow(QMainWindow):
    def __init__(self, state: AppState, parent: QMainWindow | None = None) -> None:
        super().__init__(parent)
        self._state = state

        self.setWindowTitle("PyFlowReg Session GUI")
        self.resize(1200, 800)

        session_config_cls = get_session_config_class()

        self.config_tab = ConfigTab(state, session_config_cls, self)
        self.local_tab = RunLocalTab(state, self._get_current_config, self)
        self.remote_tab = RunRemoteTab(state, self._get_current_config, self)

        tabs = QTabWidget(self)
        tabs.addTab(self.config_tab, "Config")
        tabs.addTab(self.local_tab, "Run Local")
        tabs.addTab(self.remote_tab, "Run Remote (slurm)")

        self.setCentralWidget(tabs)

    def _get_current_config(self) -> Any | None:
        return self.config_tab.get_validated_config(show_dialog=True)
