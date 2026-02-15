"""PyInstaller runtime hook: normalize Tcl/Tk library paths."""

import os
import sys


def _find_tcl_dir(base: str) -> str:
    candidates = [
        os.path.join(base, "_tcl_data"),
        os.path.join(base, "_internal", "_tcl_data"),
        os.path.join(base, "tcl", "tcl8.6"),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, "init.tcl")):
            return path
    return ""


def _find_tk_dir(base: str) -> str:
    candidates = [
        os.path.join(base, "_tk_data"),
        os.path.join(base, "_internal", "_tk_data"),
        os.path.join(base, "tcl", "tk8.6"),
    ]
    for path in candidates:
        if os.path.isfile(os.path.join(path, "tk.tcl")):
            return path
    return ""


def _configure_tk() -> None:
    base = getattr(sys, "_MEIPASS", "")
    if not base:
        return

    tcl_dir = _find_tcl_dir(base)
    tk_dir = _find_tk_dir(base)

    if tcl_dir:
        os.environ["TCL_LIBRARY"] = tcl_dir
    if tk_dir:
        os.environ["TK_LIBRARY"] = tk_dir


_configure_tk()
