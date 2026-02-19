[![PyPI - Version](https://img.shields.io/pypi/v/pyflowreg-session-gui)](https://pypi.org/project/pyflowreg-session-gui/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pyflowreg-session-gui)](https://pypi.org/project/pyflowreg-session-gui/)
[![PyPI - License](https://img.shields.io/pypi/l/pyflowreg-session-gui)](LICENSE)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/pyflowreg-session-gui)](https://pypistats.org/packages/pyflowreg-session-gui)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/pyflowreg-session-gui?period=total&units=INTERNATIONAL_SYSTEM&left_color=BLACK&right_color=GREEN&left_text=all+time+downloads)](https://pepy.tech/projects/pyflowreg)[![GitHub Actions](https://github.com/FlowRegSuite/pyflowreg-session-gui/actions/workflows/pypi-release.yml/badge.svg)](https://github.com/FlowRegSuite/pyflowreg-session-gui/actions/workflows/pypi-release.yml)

## 🚧 Under Development

This project is still in an **alpha stage**. Expect rapid changes, incomplete features, and possible breaking updates between releases.

- The API may evolve as we stabilize core functionality.
- Documentation and examples are incomplete.
- Feedback and bug reports are especially valuable at this stage.

# <img src="https://raw.githubusercontent.com/FlowRegSuite/pyflowreg/refs/heads/main/img/flowreglogo.png" alt="FlowReg logo" height="64"> pyflowreg-session-gui

Qt (PySide6) desktop application to configure and run PyFlowReg session mode locally or on a remote Slurm cluster through SSH.

## Installation (Mamba)

### Prerequisites

- `mamba` (Miniforge/conda-forge recommended)
- Python `3.10+` (examples below use `3.11`)
- System `ssh` and `rsync` available in `PATH`
- For remote Slurm submission: working SSH alias (default `deigo`)

### 1) Create and activate environment

```bash
mamba create -n flowreg_gui python=3.11 pip -y
mamba activate flowreg_gui
```

If `mamba activate` is not available in your current shell, activate via conda:

```bash
conda activate flowreg_gui
```

### 2) Install the GUI

From the repository root:

```bash
python -m pip install -U pip
python -m pip install -e .
```

For development tools (`ruff`, `pytest`):

```bash
python -m pip install -e .[dev]
```

### 3) Verify installation

```bash
python -c "import pyflowreg_session_gui; print(pyflowreg_session_gui.__version__)"
```

## Start The GUI

Preferred entrypoint:

```bash
pyflowreg-session-gui
```

Alternative:

```bash
python -m pyflowreg_session_gui.app
```

## Remote Slurm Setup (GUI Tab: "Run Remote (slurm)")

Before using remote actions in the GUI, run this once in a terminal to ensure host key/auth are configured:

```bash
ssh -o StrictHostKeyChecking=accept-new deigo "echo connected"
```

If host key changed:

```bash
ssh-keygen -R deigo
ssh -o StrictHostKeyChecking=accept-new deigo "echo connected"
```

Then in the GUI:

- Set `SSH host alias` (default `deigo`)
- Set `Remote base dir`
- Use `Test SSH` before `Upload Config` / `Submit`
