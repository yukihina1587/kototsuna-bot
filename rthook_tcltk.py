# -*- coding: utf-8 -*-
"""PyInstaller runtime hook: Tcl/Tk init.tcl / tk.tcl パス設定

このフックは main.py より前に実行され、
TCL_LIBRARY / TK_LIBRARY 環境変数を正しいパスに設定する。
PyInstaller 6.x の TclTkInfo が配置する先と、
spec で手動追加した _tcl_data/_tk_data の両方を探索する。
"""
import os
import sys

if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS

    # --- TCL_LIBRARY ---
    _candidates = [
        os.path.join(_base, '_tcl_data'),
        os.path.join(_base, 'tcl'),
        os.path.join(_base, 'tcl8.6'),
        os.path.join(_base, 'tcl', 'tcl8.6'),
        os.path.join(_base, 'lib', 'tcl8.6'),
        os.path.join(_base, 'lib', 'tcl'),
    ]

    for _c in _candidates:
        if os.path.isfile(os.path.join(_c, 'init.tcl')):
            os.environ['TCL_LIBRARY'] = _c
            break
    else:
        # Recursive fallback
        for _r, _d, _f in os.walk(_base):
            if 'init.tcl' in _f:
                os.environ['TCL_LIBRARY'] = _r
                break

    # --- TK_LIBRARY ---
    _tk_candidates = [
        os.path.join(_base, '_tk_data'),
        os.path.join(_base, 'tk'),
        os.path.join(_base, 'tk8.6'),
        os.path.join(_base, 'tcl', 'tk8.6'),
        os.path.join(_base, 'lib', 'tk8.6'),
        os.path.join(_base, 'lib', 'tk'),
    ]

    for _c in _tk_candidates:
        if os.path.isfile(os.path.join(_c, 'tk.tcl')):
            os.environ['TK_LIBRARY'] = _c
            break
    else:
        for _r, _d, _f in os.walk(_base):
            if 'tk.tcl' in _f:
                os.environ['TK_LIBRARY'] = _r
                break
