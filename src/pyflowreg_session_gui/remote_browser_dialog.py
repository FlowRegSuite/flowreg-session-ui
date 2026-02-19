from __future__ import annotations

from pathlib import PurePosixPath
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .message_dialogs import show_exception
from .remote_runner import RemoteDirectoryListing

PATH_ROLE = Qt.UserRole + 1
LOADED_ROLE = Qt.UserRole + 2


class RemoteDirectoryBrowserDialog(QDialog):
    def __init__(
        self,
        fetch_listing: Callable[[str], RemoteDirectoryListing],
        start_dir: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fetch_listing = fetch_listing
        self._selected_path = ""

        self.setWindowTitle("Select Remote Directory")
        self.resize(760, 520)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Remote directory"])
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)

        self.path_edit = QLineEdit(self)
        self.jump_button = QPushButton("Jump", self)
        self.refresh_button = QPushButton("Refresh", self)
        self.jump_button.clicked.connect(self._on_jump)
        self.refresh_button.clicked.connect(self._on_refresh)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Path", self))
        path_row.addWidget(self.path_edit, stretch=1)
        path_row.addWidget(self.jump_button)
        path_row.addWidget(self.refresh_button)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(path_row)
        layout.addWidget(self.tree)
        layout.addWidget(self.buttons)

        self._load_root(start_dir.strip() or "~")

    def selected_path(self) -> str:
        return self._selected_path

    def _make_item(self, path: str, *, loaded: bool = False) -> QTreeWidgetItem:
        name = PurePosixPath(path).name or path
        item = QTreeWidgetItem([name])
        item.setToolTip(0, path)
        item.setData(0, PATH_ROLE, path)
        item.setData(0, LOADED_ROLE, loaded)
        if not loaded:
            item.addChild(QTreeWidgetItem([""]))
        return item

    def _set_children(self, item: QTreeWidgetItem, children: list[str]) -> None:
        item.takeChildren()
        for child_path in children:
            item.addChild(self._make_item(child_path, loaded=False))
        item.setData(0, LOADED_ROLE, True)

    def _load_root(self, path: str) -> None:
        listing = self._fetch_listing(path)
        root_item = self._make_item(listing.path, loaded=True)
        self._set_children(root_item, listing.children)

        self.tree.clear()
        self.tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
        self.tree.setCurrentItem(root_item)
        self.path_edit.setText(listing.path)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        loaded = bool(item.data(0, LOADED_ROLE))
        if loaded:
            return

        path = str(item.data(0, PATH_ROLE) or "")
        if not path:
            return

        try:
            listing = self._fetch_listing(path)
        except Exception as exc:
            show_exception(self, "Remote Directory Listing Error", exc)
            return
        self._set_children(item, listing.children)

    def _on_current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            return
        path = str(current.data(0, PATH_ROLE) or "")
        if path:
            self.path_edit.setText(path)

    def _on_jump(self) -> None:
        requested = self.path_edit.text().strip()
        if not requested:
            return
        try:
            self._load_root(requested)
        except Exception as exc:
            show_exception(self, "Remote Directory Listing Error", exc)

    def _on_refresh(self) -> None:
        requested = self.path_edit.text().strip()
        if not requested:
            current = self.tree.currentItem()
            requested = str(current.data(0, PATH_ROLE) or "") if current else ""
        if not requested:
            requested = "~"
        try:
            self._load_root(requested)
        except Exception as exc:
            show_exception(self, "Remote Directory Listing Error", exc)

    def accept(self) -> None:
        current = self.tree.currentItem()
        selected = str(current.data(0, PATH_ROLE) or "") if current else ""
        if not selected:
            selected = self.path_edit.text().strip()
        self._selected_path = selected
        super().accept()
