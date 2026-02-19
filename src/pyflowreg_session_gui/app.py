from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .message_dialogs import show_exception
from .state import AppState


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    try:
        window = MainWindow(AppState())
    except Exception as exc:
        show_exception(None, "Startup Error", exc)
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
