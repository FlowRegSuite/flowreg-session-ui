from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        print(f"Failed to import PySide6/Qt: {exc}", file=sys.stderr)
        return 1

    from .main_window import MainWindow
    from .message_dialogs import show_exception
    from .state import AppState

    app = QApplication.instance() or QApplication(sys.argv)

    try:
        window = MainWindow(AppState())
    except Exception as exc:
        try:
            show_exception(None, "Startup Error", exc)
        except Exception:
            print(f"Startup Error: {exc}", file=sys.stderr)
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
