# PyInstaller runtime hook: AV隔離対策 + Tcl/Tk ZIP展開
import os
import sys
import zipfile
import shutil
import tempfile
import builtins
import io as _io
import zipimport

_meipass = getattr(sys, '_MEIPASS', None)
_builtin_open = builtins.open

# ── Phase 0: base_library.zip を安全な場所にコピー ──────
# Windows Defenderが_MEIxxxx内のbase_library.zipを遅延隔離すると
# Pythonのzipimportが機能停止する。AV対象外の%LOCALAPPDATA%にコピーし
# sys.path・path_importer_cache・zipimport内部キャッシュを全て差し替える。
_base_lib_relocated = False
_base_lib_diag = []

if _meipass:
    _base_lib_src = os.path.join(_meipass, 'base_library.zip')
    if os.path.isfile(_base_lib_src):
        try:
            _safe_dir = os.path.join(
                os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                'Kototsuna', 'runtime_cache'
            )
            os.makedirs(_safe_dir, exist_ok=True)
            _safe_base = os.path.join(_safe_dir, 'base_library.zip')
            shutil.copy2(_base_lib_src, _safe_base)

            # sys.pathの該当エントリを全て差し替え（大文字小文字無視）
            _replaced_count = 0
            for _i in range(len(sys.path)):
                if 'base_library.zip' in sys.path[_i].lower():
                    _base_lib_diag.append(f"syspath_old[{_i}]={sys.path[_i]}")
                    sys.path[_i] = _safe_base
                    _replaced_count += 1
            _base_lib_diag.append(f"syspath_replaced={_replaced_count}")

            # sys.path_importer_cacheからbase_library.zip参照を全削除
            _deleted_pic = 0
            for _key in list(sys.path_importer_cache.keys()):
                if 'base_library.zip' in str(_key).lower():
                    _base_lib_diag.append(f"pic_del={_key}")
                    del sys.path_importer_cache[_key]
                    _deleted_pic += 1
            _base_lib_diag.append(f"pic_deleted={_deleted_pic}")

            # zipimport._zip_directory_cacheからも全削除
            _deleted_zdc = 0
            if hasattr(zipimport, '_zip_directory_cache'):
                for _key in list(zipimport._zip_directory_cache.keys()):
                    if 'base_library.zip' in str(_key).lower():
                        _base_lib_diag.append(f"zdc_del={_key}")
                        del zipimport._zip_directory_cache[_key]
                        _deleted_zdc += 1
            _base_lib_diag.append(f"zdc_deleted={_deleted_zdc}")

            # 新パスのzipimporterを事前登録
            try:
                _new_importer = zipimport.zipimporter(_safe_base)
                sys.path_importer_cache[_safe_base] = _new_importer
                _base_lib_diag.append(f"new_importer=OK")
            except Exception as _e:
                _base_lib_diag.append(f"new_importer=FAIL:{_e}")

            _base_lib_relocated = True
        except Exception as _e:
            _base_lib_diag.append(f"error={_e}")

# ── Phase 1: customtkinterテーマファイルのプリキャッシュ ──
# rthook実行直後（隔離前）にテーマJSONを読み込みメモリキャッシュ。
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

    if _cached_files:
        def _safe_open(file, mode='r', *args, **kwargs):
            try:
                return _builtin_open(file, mode, *args, **kwargs)
            except (FileNotFoundError, PermissionError):
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
        _df.write(f"cwd={os.getcwd()}\n")
        _df.write(f"executable={sys.executable}\n")
        if _meipass:
            _df.write(f"base_lib_relocated={_base_lib_relocated}\n")
            for _d in _base_lib_diag:
                _df.write(f"  {_d}\n")
            # 現在のsys.pathでbase_library.zip関連エントリを表示
            for _i, _p in enumerate(sys.path):
                if 'base_library' in _p.lower():
                    _df.write(f"  syspath_now[{_i}]={_p}\n")
            # 現在のpath_importer_cacheでbase_library.zip関連を表示
            for _k in sys.path_importer_cache:
                if 'base_library' in str(_k).lower():
                    _df.write(f"  pic_now={_k} -> {type(sys.path_importer_cache[_k]).__name__}\n")
            _df.write(f"cached_files_count={len(_cached_files)}\n")
            for _k in _cached_files:
                _df.write(f"  cached: {_k}\n")
            _df.write(f"open_patched={'YES' if _cached_files else 'NO'}\n")
            _df.write(f"init_tcl_exists={os.path.isfile(os.path.join(_meipass, '_tcl_data', 'init.tcl'))}\n")
            _df.write(f"TCL_LIBRARY={os.environ.get('TCL_LIBRARY', '')}\n")
            _df.write(f"TK_LIBRARY={os.environ.get('TK_LIBRARY', '')}\n")
        else:
            _df.write("NOT FROZEN\n")
except Exception:
    pass
