# PyInstaller runtime hook: ファイルプリキャッシュ + Tcl/Tk ZIP展開
import os
import sys
import zipfile
import tempfile
import builtins
import io as _io

_meipass = getattr(sys, '_MEIPASS', None)
_builtin_open = builtins.open

# ── Phase 1: AV隔離対策 ─────────────────────────────────
# Windows Defenderが%TEMP%に展開されたファイルを遅延隔離するため、
# rthook実行直後（隔離前）にcustomtkinterテーマファイルを読み込みキャッシュ。
# 後続のimportでFileNotFoundErrorが発生した場合、キャッシュから提供する。
_cached_files = {}

if _meipass:
    for _rel in [
        os.path.join('customtkinter', 'assets', 'themes', 'blue.json'),
        os.path.join('customtkinter', 'assets', 'themes', 'green.json'),
    ]:
        _abs = os.path.join(_meipass, _rel)
        if os.path.isfile(_abs):
            try:
                with _builtin_open(_abs, 'r', encoding='utf-8') as _f:
                    _cached_files[os.path.normpath(_abs)] = _f.read()
            except Exception:
                pass

    # FileNotFoundError/PermissionError時にキャッシュからフォールバックするラッパー
    if _cached_files:
        def _safe_open(file, mode='r', *args, **kwargs):
            try:
                return _builtin_open(file, mode, *args, **kwargs)
            except (FileNotFoundError, PermissionError) as _exc:
                _norm = os.path.normpath(str(file))
                if _norm in _cached_files and 'r' in str(mode) and 'b' not in str(mode):
                    return _io.StringIO(_cached_files[_norm])
                raise

        builtins.open = _safe_open

# ── Phase 2: Tcl/Tk ZIP展開 ─────────────────────────────
if _meipass:
    _zip_path = os.path.join(_meipass, 'tcl_tk_data.zip')
    _tcl_dir = os.path.join(_meipass, '_tcl_data')
    _tk_dir = os.path.join(_meipass, '_tk_data')

    if os.path.isfile(_zip_path):
        try:
            with zipfile.ZipFile(_zip_path, 'r') as zf:
                zf.extractall(_meipass)
        except Exception:
            pass

    if os.path.isdir(_tcl_dir):
        os.environ['TCL_LIBRARY'] = _tcl_dir
    if os.path.isdir(_tk_dir):
        os.environ['TK_LIBRARY'] = _tk_dir

# ── Phase 3: 診断出力 ───────────────────────────────────
_diag_path = os.path.join(tempfile.gettempdir(), 'kototsuna_rthook_diag.txt')
try:
    with _builtin_open(_diag_path, 'w', encoding='utf-8') as _df:
        _df.write(f"meipass={_meipass}\n")
        _df.write(f"frozen={getattr(sys, 'frozen', False)}\n")
        if _meipass:
            _df.write(f"cached_files_count={len(_cached_files)}\n")
            for _k in _cached_files:
                _df.write(f"  cached: {_k}\n")
            _df.write(f"open_patched={'YES' if _cached_files else 'NO'}\n")
            _ctk_blue = os.path.join(_meipass, 'customtkinter', 'assets', 'themes', 'blue.json')
            _df.write(f"ctk_blue_json_exists={os.path.isfile(_ctk_blue)}\n")
            _tcl_dir_chk = os.path.join(_meipass, '_tcl_data')
            _df.write(f"init_tcl_exists={os.path.isfile(os.path.join(_tcl_dir_chk, 'init.tcl'))}\n")
            _df.write(f"TCL_LIBRARY={os.environ.get('TCL_LIBRARY', '')}\n")
            _df.write(f"TK_LIBRARY={os.environ.get('TK_LIBRARY', '')}\n")
        else:
            _df.write("NOT FROZEN\n")
except Exception:
    pass
