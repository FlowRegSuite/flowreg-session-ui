from __future__ import annotations

import json
import types
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Callable, Literal, Union, get_args, get_origin

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .message_dialogs import show_exception, show_info
from .model_utils import MISSING, build_model, iter_model_fields, model_to_dict

EXCLUDED_SESSION_FIELDS = {"scheduler", "flow_backend"}

IMPORTANT_OF_OPTIONS_KEYS = [
    "quality_setting",
    "buffer_size",
    "save_w",
    "save_valid_idx",
    "save_meta_info",
    "save_valid_mask",
    "alpha",
    "levels",
    "min_level",
    "eta",
    "iterations",
    "a_smooth",
    "a_data",
    "bin_size",
    "update_reference",
    "n_references",
    "min_frames_per_reference",
    "cc_initialization",
    "cc_up",
    "channel_normalization",
    "interpolation_method",
    "constancy_assumption",
    "backend_params",
]

FALLBACK_FLOW_OPTIONS_TEMPLATE: dict[str, Any] = {
    "quality_setting": "balanced",
    "buffer_size": 1000,
    "save_w": False,
    "save_valid_idx": True,
    "save_meta_info": True,
    "backend_params": {},
}


@dataclass
class _EditorBinding:
    getter: Callable[[], Any]
    setter: Callable[[Any], None]
    resetter: Callable[[], None]
    default: Any


def _is_pydantic_undefined(value: Any) -> bool:
    return value is Ellipsis or type(value).__name__ in {"PydanticUndefinedType", "UndefinedType"}


def _extract_field_default(field: Any) -> Any:
    default = getattr(field, "default", MISSING)
    if default is not MISSING and not _is_pydantic_undefined(default):
        return default

    default_factory = getattr(field, "default_factory", None)
    if callable(default_factory):
        try:
            return default_factory()
        except Exception:
            return MISSING

    return MISSING


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_json_compatible(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_compatible(v) for v in value]
    if hasattr(value, "tolist"):
        try:
            return value.tolist()
        except Exception:
            return value
    return value


@lru_cache(maxsize=1)
def get_flow_options_template() -> dict[str, Any]:
    template = dict(FALLBACK_FLOW_OPTIONS_TEMPLATE)

    try:
        from pyflowreg.motion_correction.OF_options import OFOptions

        raw_fields = getattr(OFOptions, "model_fields", None)
        if raw_fields is None:
            raw_fields = getattr(OFOptions, "__fields__", None)

        if isinstance(raw_fields, dict):
            discovered: dict[str, Any] = {}
            for key in IMPORTANT_OF_OPTIONS_KEYS:
                field = raw_fields.get(key)
                if field is None:
                    continue

                default = _extract_field_default(field)
                if default is MISSING:
                    continue

                discovered[key] = _to_json_compatible(default)

            if discovered:
                template = discovered
    except Exception:
        pass

    # Explicitly keep flow_backend out of inline flow_options and SessionConfig form.
    template.pop("flow_backend", None)
    return template


class PathPickerWidget(QWidget):
    def __init__(self, pick_directory: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pick_directory = pick_directory

        self.line_edit = QLineEdit(self)
        self.browse_button = QPushButton("Browse", self)
        self.browse_button.clicked.connect(self._browse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.line_edit)
        layout.addWidget(self.browse_button)

    def _browse(self) -> None:
        if self._pick_directory:
            selected = QFileDialog.getExistingDirectory(self, "Select directory")
            if selected:
                self.line_edit.setText(selected)
            return

        selected, _ = QFileDialog.getOpenFileName(self, "Select file")
        if selected:
            self.line_edit.setText(selected)


class FlowOptionsDialog(QDialog):
    def __init__(self, template: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._template = dict(template)

        self.setWindowTitle("Flow Options")
        self.resize(720, 500)

        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("Inline JSON", userData="inline")
        self.mode_combo.addItem("JSON file path", userData="file")

        self.inline_editor = QPlainTextEdit(self)
        self.inline_editor.setPlaceholderText(json.dumps(self._template, indent=2))

        self.file_picker = PathPickerWidget(pick_directory=False, parent=self)

        self.stacked = QStackedWidget(self)
        self.stacked.addWidget(self.inline_editor)
        self.stacked.addWidget(self.file_picker)

        template_button = QPushButton("Insert Recommended Template", self)
        template_button.clicked.connect(self._insert_template)

        validate_button = QPushButton("Validate JSON", self)
        validate_button.clicked.connect(self._validate_inline_json)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(template_button)
        controls_layout.addWidget(validate_button)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Mode", self.mode_combo)
        form.addRow("Value", self.stacked)
        layout.addLayout(form)
        layout.addLayout(controls_layout)
        layout.addWidget(self.buttons)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._on_mode_changed(0)

    def _on_mode_changed(self, _index: int) -> None:
        mode = self.mode_combo.currentData()
        self.stacked.setCurrentIndex(0 if mode == "inline" else 1)

    def _parse_inline_json(self) -> dict[str, Any]:
        text = self.inline_editor.toPlainText().strip()
        if not text:
            return {}

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid flow_options JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Inline flow_options JSON must be an object.")
        return parsed

    def _insert_template(self) -> None:
        merged = dict(self._template)
        try:
            existing = self._parse_inline_json()
        except Exception:
            existing = {}
        merged.update(existing)
        self.mode_combo.setCurrentIndex(0)
        self.inline_editor.setPlainText(json.dumps(merged, indent=2))

    def _validate_inline_json(self) -> None:
        try:
            parsed = self._parse_inline_json()
        except Exception as exc:
            show_exception(self, "JSON Error", exc)
            return

        show_info(self, "JSON", f"JSON is valid ({len(parsed)} key(s)).")

    def get_value(self) -> dict[str, Any] | str:
        mode = self.mode_combo.currentData()
        if mode == "inline":
            return self._parse_inline_json()
        return self.file_picker.line_edit.text().strip()

    def set_value(self, value: Any) -> None:
        if isinstance(value, dict):
            self.mode_combo.setCurrentIndex(0)
            self.inline_editor.setPlainText(json.dumps(value, indent=2))
            return

        if value in (None, ""):
            self.mode_combo.setCurrentIndex(0)
            self.inline_editor.setPlainText("{}")
            self.file_picker.line_edit.clear()
            return

        self.mode_combo.setCurrentIndex(1)
        self.file_picker.line_edit.setText(str(value))

    def accept(self) -> None:
        try:
            self.get_value()
        except Exception as exc:
            show_exception(self, "Flow Options Error", exc)
            return
        super().accept()


class FlowOptionsEditor(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._template = get_flow_options_template()
        self._value: dict[str, Any] | str = {}

        self.summary = QLabel(self)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        edit_button = QPushButton("Open Editor", self)
        clear_button = QPushButton("Clear", self)

        edit_button.clicked.connect(self._open_editor)
        clear_button.clicked.connect(self.reset)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.summary, stretch=1)
        layout.addWidget(edit_button)
        layout.addWidget(clear_button)

        self._refresh_summary()

    def _has_inline_value(self) -> bool:
        return isinstance(self._value, dict) and bool(self._value)

    def _refresh_summary(self) -> None:
        value = self._value
        if isinstance(value, dict):
            if not value:
                template_keys = ", ".join(list(self._template.keys())[:5])
                suffix = "..." if len(self._template) > 5 else ""
                self.summary.setText(
                    "No flow_options configured; template available"
                    f" ({len(self._template)} key(s): {template_keys}{suffix})"
                )
                return

            keys = list(value.keys())
            preview = ", ".join(keys[:4])
            if len(keys) > 4:
                preview += ", ..."
            suffix = f" [{preview}]" if preview else ""
            self.summary.setText(f"Inline flow_options dict with {len(keys)} key(s){suffix}")
            return

        if value:
            self.summary.setText(f"Flow options JSON file: {value}")
            return

        self.summary.setText("No flow_options configured")

    def _open_editor(self) -> None:
        dialog = FlowOptionsDialog(self._template, self)

        if self._has_inline_value() or isinstance(self._value, str):
            dialog.set_value(self._value)
        else:
            dialog.set_value(self._template)

        if dialog.exec() != QDialog.Accepted:
            return

        self._value = dialog.get_value()
        self._refresh_summary()

    def get_value(self) -> dict[str, Any] | str:
        return self._value

    def set_value(self, value: Any) -> None:
        if isinstance(value, dict):
            self._value = dict(value)
        elif value in (None, ""):
            self._value = {}
        else:
            self._value = str(value)
        self._refresh_summary()

    def reset(self) -> None:
        self._value = {}
        self._refresh_summary()


def _strip_annotated(annotation: Any) -> Any:
    while get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if not args:
            break
        annotation = args[0]
    return annotation


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    annotation = _strip_annotated(annotation)
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [_strip_annotated(arg) for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def _annotation_has_type(annotation: Any, target: type[Any]) -> bool:
    base, _ = _unwrap_optional(annotation)
    if base is target:
        return True

    origin = get_origin(base)
    if origin is target:
        return True
    if origin in (Union, types.UnionType):
        return any(_annotation_has_type(arg, target) for arg in get_args(base))

    return False


class SessionConfigForm(QWidget):
    def __init__(self, session_config_cls: type[Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session_config_cls = session_config_cls
        self._bindings: dict[str, _EditorBinding] = {}
        self._hidden_defaults: dict[str, Any] = {}
        self._hidden_values: dict[str, Any] = {}

        form_layout = QFormLayout(self)
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        for field_spec in iter_model_fields(session_config_cls):
            if field_spec.name in EXCLUDED_SESSION_FIELDS:
                self._hidden_defaults[field_spec.name] = field_spec.default
                if field_spec.default is not MISSING:
                    self._hidden_values[field_spec.name] = field_spec.default
                continue

            binding, widget = self._create_editor(
                field_spec.name, field_spec.annotation, field_spec.default
            )
            self._bindings[field_spec.name] = binding
            form_layout.addRow(field_spec.name, widget)

    def _create_editor(
        self, field_name: str, annotation: Any, default: Any
    ) -> tuple[_EditorBinding, QWidget]:
        base_annotation, optional = _unwrap_optional(annotation)

        if field_name == "flow_options":
            editor = FlowOptionsEditor(self)
            binding = _EditorBinding(
                getter=editor.get_value,
                setter=editor.set_value,
                resetter=editor.reset,
                default=default,
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if field_name in {"root", "output_root", "final_results", "center"}:
            editor = PathPickerWidget(pick_directory=field_name != "center", parent=self)

            def getter() -> Any:
                text = editor.line_edit.text().strip()
                if optional and not text:
                    return None
                return text

            def setter(value: Any) -> None:
                editor.line_edit.setText("" if value is None else str(value))

            def resetter() -> None:
                editor.line_edit.clear()

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if base_annotation is bool:
            editor = QCheckBox(self)

            def getter() -> bool:
                return editor.isChecked()

            def setter(value: Any) -> None:
                editor.setChecked(bool(value))

            def resetter() -> None:
                editor.setChecked(False)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if base_annotation is int:
            editor = QSpinBox(self)
            editor.setRange(-1_000_000_000, 1_000_000_000)

            def getter() -> int:
                return int(editor.value())

            def setter(value: Any) -> None:
                editor.setValue(int(value))

            def resetter() -> None:
                editor.setValue(0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if base_annotation is float:
            editor = QDoubleSpinBox(self)
            editor.setRange(-1_000_000_000.0, 1_000_000_000.0)
            editor.setDecimals(6)

            def getter() -> float:
                return float(editor.value())

            def setter(value: Any) -> None:
                editor.setValue(float(value))

            def resetter() -> None:
                editor.setValue(0.0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        if get_origin(base_annotation) is Literal:
            options = list(get_args(base_annotation))
            editor = QComboBox(self)
            for option in options:
                editor.addItem(str(option), userData=option)

            def getter() -> Any:
                return editor.currentData()

            def setter(value: Any) -> None:
                for index in range(editor.count()):
                    if editor.itemData(index) == value:
                        editor.setCurrentIndex(index)
                        return

            def resetter() -> None:
                if editor.count() > 0:
                    editor.setCurrentIndex(0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if isinstance(base_annotation, type) and issubclass(base_annotation, Enum):
            enum_values = list(base_annotation)
            editor = QComboBox(self)
            for enum_value in enum_values:
                editor.addItem(str(enum_value.value), userData=enum_value)

            def getter() -> Any:
                return editor.currentData()

            def setter(value: Any) -> None:
                for index in range(editor.count()):
                    if editor.itemData(index) == value:
                        editor.setCurrentIndex(index)
                        return

            def resetter() -> None:
                if editor.count() > 0:
                    editor.setCurrentIndex(0)

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if base_annotation is dict or _annotation_has_type(base_annotation, dict):
            editor = QPlainTextEdit(self)
            editor.setPlaceholderText('{"key": "value"}')

            def getter() -> Any:
                text = editor.toPlainText().strip()
                if not text:
                    return {} if not optional else None
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON for '{field_name}': {exc}") from exc
                if not isinstance(parsed, dict):
                    raise ValueError(f"Field '{field_name}' expects a JSON object.")
                return parsed

            def setter(value: Any) -> None:
                if value is None:
                    editor.setPlainText("")
                else:
                    editor.setPlainText(json.dumps(value, indent=2))

            def resetter() -> None:
                editor.setPlainText("{}" if not optional else "")

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            else:
                binding.resetter()
            return binding, editor

        if base_annotation in {str, Path} or _annotation_has_type(base_annotation, Path):
            editor = QLineEdit(self)

            def getter() -> Any:
                text = editor.text().strip()
                if optional and not text:
                    return None
                return text

            def setter(value: Any) -> None:
                editor.setText("" if value is None else str(value))

            def resetter() -> None:
                editor.clear()

            binding = _EditorBinding(
                getter=getter, setter=setter, resetter=resetter, default=default
            )
            if default is not MISSING:
                binding.setter(default)
            return binding, editor

        editor = QLineEdit(self)

        def getter() -> str:
            return editor.text().strip()

        def setter(value: Any) -> None:
            editor.setText("" if value is None else str(value))

        def resetter() -> None:
            editor.clear()

        binding = _EditorBinding(getter=getter, setter=setter, resetter=resetter, default=default)
        if default is not MISSING:
            binding.setter(default)
        return binding, editor

    def get_form_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for name, binding in self._bindings.items():
            data[name] = binding.getter()

        data.update(self._hidden_values)
        return data

    def set_form_data(self, values: dict[str, Any]) -> None:
        for name, value in values.items():
            if name in self._hidden_defaults:
                self._hidden_values[name] = value
                continue

            binding = self._bindings.get(name)
            if binding is None:
                continue
            binding.setter(value)

    def set_from_config(self, config: Any) -> None:
        self.set_form_data(model_to_dict(config))

    def reset_to_defaults(self) -> None:
        for binding in self._bindings.values():
            if binding.default is MISSING:
                binding.resetter()
            else:
                binding.setter(binding.default)

        for field_name, default in self._hidden_defaults.items():
            if default is MISSING:
                self._hidden_values.pop(field_name, None)
            else:
                self._hidden_values[field_name] = default

    def to_session_config(self) -> Any:
        return build_model(self._session_config_cls, self.get_form_data())
