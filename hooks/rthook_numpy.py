"""Runtime hook: add numpy.libs to DLL search path for frozen builds.

numpy 2.x on Windows uses delvewheel to load OpenBLAS from numpy.libs/.
In a PyInstaller frozen environment, delvewheel's __init__.py loader
doesn't work because the path calculation is wrong. We fix this by
explicitly adding numpy.libs/ to the DLL search directories before
numpy is imported.
"""
import os
import sys

if sys.platform == "win32" and getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _numpy_libs = os.path.join(_meipass, "numpy.libs")
    if os.path.isdir(_numpy_libs):
        os.add_dll_directory(_numpy_libs)
        os.environ["PATH"] = _numpy_libs + os.pathsep + os.environ.get("PATH", "")
