# PyInstaller runtime hook: Tcl/Tk ZIPを展開
# spec側のruntime_hooksで指定され、標準rthookより先に実行される。
# tcl_tk_data.zipを_MEIPASS直下に展開し、_tcl_data/_tk_dataを作成。
# その後、標準のpyi_rth__tkinter.pyがTCL_LIBRARY/TK_LIBRARYを設定する。
import os
import sys
import zipfile

_meipass = getattr(sys, '_MEIPASS', None)
if _meipass:
    _zip_path = os.path.join(_meipass, 'tcl_tk_data.zip')
    _tcl_dir = os.path.join(_meipass, '_tcl_data')
    if os.path.isfile(_zip_path) and not os.path.isfile(os.path.join(_tcl_dir, 'init.tcl')):
        try:
            with zipfile.ZipFile(_zip_path, 'r') as zf:
                zf.extractall(_meipass)
        except Exception:
            pass

    # TCL_LIBRARY/TK_LIBRARYを直接設定（標準rthookのフォールバック）
    if os.path.isdir(_tcl_dir):
        os.environ['TCL_LIBRARY'] = _tcl_dir
    _tk_dir = os.path.join(_meipass, '_tk_data')
    if os.path.isdir(_tk_dir):
        os.environ['TK_LIBRARY'] = _tk_dir
