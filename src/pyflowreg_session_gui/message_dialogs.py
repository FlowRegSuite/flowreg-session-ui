from __future__ import annotations

import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget

SELECTABLE_TEXT_FLAGS = Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard


def show_copyable_message(
    parent: QWidget | None,
    title: str,
    message: str,
    *,
    icon: QMessageBox.Icon = QMessageBox.Information,
    details: str | None = None,
) -> None:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(message)
    box.setTextFormat(Qt.PlainText)
    box.setTextInteractionFlags(SELECTABLE_TEXT_FLAGS)
    if details:
        box.setDetailedText(details)
    box.exec()


def show_info(parent: QWidget | None, title: str, message: str) -> None:
    show_copyable_message(parent, title, message, icon=QMessageBox.Information)


def show_warning(parent: QWidget | None, title: str, message: str) -> None:
    show_copyable_message(parent, title, message, icon=QMessageBox.Warning)


def show_exception(
    parent: QWidget | None,
    title: str,
    error: BaseException,
    *,
    details: str | None = None,
) -> None:
    traceback_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    show_copyable_message(
        parent,
        title,
        str(error) or error.__class__.__name__,
        icon=QMessageBox.Critical,
        details=details or traceback_text,
    )


def show_error_text(
    parent: QWidget | None, title: str, message: str, details: str | None = None
) -> None:
    show_copyable_message(
        parent,
        title,
        message,
        icon=QMessageBox.Critical,
        details=details,
    )
