"""Runtime hook: register numpy/OpenBLAS DLL directories for frozen builds."""
import os
import sys

_DLL_DIR_HANDLES = []


def _register_dll_dir(path: str) -> None:
    if not path or not os.path.isdir(path):
        return
    os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        handle = os.add_dll_directory(path)
        _DLL_DIR_HANDLES.append(handle)


if sys.platform == "win32" and getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    for _dll_dir in (
        os.path.join(_meipass, "numpy.libs"),
        _meipass,
        os.path.dirname(sys.executable),
    ):
        _register_dll_dir(_dll_dir)
