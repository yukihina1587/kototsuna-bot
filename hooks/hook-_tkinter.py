# Override PyInstaller's standard hook-_tkinter.py
# Tcl/Tk data files are explicitly collected in Kototsuna.spec (file-by-file).
# The standard post-graph hook interferes with our explicit collection,
# causing _tcl_data directory to exist but be empty at runtime.
#
# The standard RUNTIME hook (pyi_rth__tkinter.py) is NOT affected by this
# override and will still set TCL_LIBRARY/TK_LIBRARY at startup.
