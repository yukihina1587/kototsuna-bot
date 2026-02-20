# PyInstaller runtime hook: AV隔離対策 + Tcl/Tk ZIP展開
#
# !! 重要: Phase 0 はビルトイン/frozenモジュールのみ使用 !!
# os, sys, builtins, zipimport は CPython インタプリタに組み込まれており
# base_library.zip が存在しなくても import できる。
# zipfile, shutil, tempfile, io 等は base_library.zip 内にあるため、
# AV隔離時には import 自体が失敗しうる（ハイブリッド戦略で再試行）。
import os
import sys
import builtins
import zipimport

_meipass = getattr(sys, '_MEIPASS', None)
_builtin_open = builtins.open
_RTHOOK_VERSION = "1.3.1-rc4"

# ── Hybrid import strategy (Approach B) ──────────────────
# 通常時はここで標準ライブラリを読み込み、v1.3.0相当の初期化順序を維持する。
# AV隔離時は import 失敗を許容し、Phase 0 後に再試行する。
_has_stdlib = False
_io = None
zipfile = None
shutil = None
tempfile = None
_stdlib_import_error = None
try:
    import shutil
    import tempfile
    import io as _io
    import zipfile
    _has_stdlib = True
except Exception as _e:
    _stdlib_import_error = _e


def _prime_collections_abc_binding(diag):
    """collections.abc の親属性バインディングを明示的に確立する。"""
    try:
        __import__('_collections_abc')  # frozen module
        _collections_mod = __import__('collections', fromlist=['abc'])
        _abc_mod = __import__('collections.abc', fromlist=['Hashable'])
        if getattr(_collections_mod, 'abc', None) is not _abc_mod:
            setattr(_collections_mod, 'abc', _abc_mod)
        if not hasattr(_abc_mod, 'Hashable'):
            raise AttributeError('collections.abc.Hashable missing')
        diag.append("collections_abc=OK")
        return True
    except Exception as _e:
        diag.append(f"collections_abc=FAIL:{_e}")
        return False

# ── Phase -1: 堅牢なエラーハンドラ（osモジュールのみ使用） ──────
# traceback, io 等に依存しない最小限のエラー出力。
# Phase 0 より前に設置することで、あらゆるクラッシュをキャプチャ可能。
# エラーログ・診断ログをexeの隣に出力（ユーザーが見つけやすい）
# 書き込み不可の場合は%TEMP%にフォールバック
_err_dir = ''
if hasattr(sys, 'executable') and sys.executable:
    _candidate = os.path.dirname(sys.executable)
    try:
        _test_path = os.path.join(_candidate, '.kototsuna_write_test')
        _fd = os.open(_test_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        os.close(_fd)
        os.unlink(_test_path)
        _err_dir = _candidate
    except OSError:
        pass
if not _err_dir:
    _err_dir = os.environ.get('TEMP', os.environ.get('TMP', '.'))
_raw_err_path = os.path.join(_err_dir, 'kototsuna_error.txt')

def _raw_excepthook(exc_type, exc_value, exc_tb):
    """osモジュールのみで動作する堅牢なexcepthook"""
    try:
        # まずraw方式で書き込み（絶対に失敗しない方法）
        _lines = []
        _lines.append(f"rthook_version={_RTHOOK_VERSION}")
        _lines.append(f"meipass={_meipass}")
        _lines.append(f"exc_type={exc_type}")
        _lines.append(f"exc_value={exc_value}")

        # tracebackをフレームから手動構築（traceback moduleに依存しない）
        _tb = exc_tb
        _lines.append("traceback:")
        while _tb is not None:
            _frame = _tb.tb_frame
            _lineno = _tb.tb_lineno
            _code = _frame.f_code
            _filename = _code.co_filename
            _name = _code.co_name
            _lines.append(f"  File \"{_filename}\", line {_lineno}, in {_name}")
            _tb = _tb.tb_next

        _text = '\n'.join(_lines) + '\n'
        # os.open/os.write はCレベル実装のため base_library.zip 不要
        _fd = os.open(_raw_err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        os.write(_fd, _text.encode('utf-8', errors='replace'))
        os.close(_fd)
    except Exception:
        pass

    # デフォルトのexcepthookも試行（stderrに出力）
    try:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    except Exception:
        pass

sys.excepthook = _raw_excepthook

# ── Phase 0: base_library.zip を安全な場所にコピー ──────
# Windows Defenderが_MEIxxxx内のbase_library.zipを遅延隔離すると
# Pythonのzipimportが機能停止する。
#
# !! このフェーズは os, sys, builtins, zipimport のみ使用 !!
# shutil.copy2 → builtins.open(rb/wb) で代替
# tempfile.gettempdir → os.environ.get('TEMP') で代替
#
# 対策2層:
#   A. プリステージング: 前回成功時の安全コピーを即座に使う（AV隔離より先に動ける）
#   B. 完全パス差し替え: sys.path と importer cache を安全コピーへ切り替え
_base_lib_relocated = False
_base_lib_diag = []
_safe_base = None
if _has_stdlib:
    _base_lib_diag.append("early_stdlib_import=OK")
elif _stdlib_import_error is not None:
    _base_lib_diag.append(f"early_stdlib_import=FAIL:{_stdlib_import_error}")

if _meipass:
    _safe_dir = os.path.join(
        os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
        'Kototsuna', 'runtime_cache'
    )
    _safe_base = os.path.join(_safe_dir, 'base_library.zip')
    _base_lib_src = os.path.join(_meipass, 'base_library.zip')
    _old_base_path = _base_lib_src  # 旧パス（差し替え対象）

    try:
        os.makedirs(_safe_dir, exist_ok=True)

        # --- A. プリステージング: 安全コピーの確保 ---
        # TOCTOU対策: isfile()チェックなしで直接コピーを試行。
        # AV隔離はisfile()→open()の間に発生しうるため、try/exceptで処理。
        _copied = False
        try:
            with _builtin_open(_base_lib_src, 'rb') as _fin:
                _data = _fin.read()
            with _builtin_open(_safe_base, 'wb') as _fout:
                _fout.write(_data)
            del _data
            _copied = True
            _base_lib_diag.append("action=copied_from_mei")
        except (FileNotFoundError, PermissionError, OSError) as _copy_err:
            _base_lib_diag.append(f"mei_copy_failed={_copy_err}")
            # _MEIからのコピー失敗 → runtime_cacheの既存キャッシュを使用
            if os.path.isfile(_safe_base):
                _base_lib_diag.append("action=using_prestaged_copy")
            else:
                _base_lib_diag.append("action=NO_SOURCE_AVAILABLE")

        # --- B: パス差し替えはAV隔離時のみ実行 ---
        # _MEIからのコピーが成功した場合（_copied=True）はバックアップのみ。
        # sys.pathやモジュール__path__を差し替えると、既ロードモジュールの
        # 内部状態が壊れる（例: collections.abc.Hashable消失）。
        # AV隔離でコピー失敗した場合のみフル差し替えを行う。
        _need_relocation = not _copied

        if os.path.isfile(_safe_base):
            if _need_relocation:
                # --- B. 完全パス差し替え（AV隔離時のみ） ---
                # B-1. sys.path
                _replaced_count = 0
                for _i in range(len(sys.path)):
                    if 'base_library.zip' in sys.path[_i].lower():
                        _base_lib_diag.append(f"syspath_old[{_i}]={sys.path[_i]}")
                        sys.path[_i] = _safe_base
                        _replaced_count += 1
                _base_lib_diag.append(f"syspath_replaced={_replaced_count}")

                # B-2. sys.path_importer_cache: 旧エントリ削除 + 新エントリ登録
                _deleted_pic = 0
                _old_subpaths = []
                for _key in list(sys.path_importer_cache.keys()):
                    if 'base_library.zip' in str(_key).lower():
                        _old_subpaths.append(_key)
                        del sys.path_importer_cache[_key]
                        _deleted_pic += 1
                _base_lib_diag.append(f"pic_deleted={_deleted_pic}")

                # B-3. zipimport._zip_directory_cache
                _deleted_zdc = 0
                if hasattr(zipimport, '_zip_directory_cache'):
                    for _key in list(zipimport._zip_directory_cache.keys()):
                        if 'base_library.zip' in str(_key).lower():
                            del zipimport._zip_directory_cache[_key]
                            _deleted_zdc += 1
                _base_lib_diag.append(f"zdc_deleted={_deleted_zdc}")

                # B-4. 新パスのzipimporterを登録
                try:
                    _new_importer = zipimport.zipimporter(_safe_base)
                    sys.path_importer_cache[_safe_base] = _new_importer
                    _base_lib_diag.append("new_importer=OK")
                    for _old_key in _old_subpaths:
                        _old_key_str = str(_old_key)
                        _suffix = ''
                        _bl_idx = _old_key_str.lower().find('base_library.zip')
                        if _bl_idx >= 0:
                            _suffix = _old_key_str[_bl_idx + len('base_library.zip'):]
                        if _suffix:
                            _new_subpath = _safe_base + _suffix
                            try:
                                _sub_importer = zipimport.zipimporter(_new_subpath)
                                sys.path_importer_cache[_new_subpath] = _sub_importer
                            except Exception:
                                pass
                except Exception as _e:
                    _base_lib_diag.append(f"new_importer=FAIL:{_e}")

                _base_lib_diag.append("modules_fixed=SKIPPED")
            else:
                _base_lib_diag.append("relocation=SKIPPED(mei_ok)")

            _base_lib_diag.append("meta_path_finder=DISABLED")

            _base_lib_relocated = True

    except Exception as _e:
        _base_lib_diag.append(f"error={_e}")

# ── Phase 0 完了: 以降は safe_base を使って標準ライブラリ再試行可能 ──
if not _has_stdlib:
    try:
        import shutil
        import tempfile
        import io as _io
        import zipfile
        _has_stdlib = True
        _base_lib_diag.append("post_phase0_stdlib_import=OK")
    except Exception as _e:
        _base_lib_diag.append(f"post_phase0_stdlib_import=FAIL:{_e}")
        _io = None
        zipfile = None
        shutil = None
        tempfile = None
else:
    _base_lib_diag.append("post_phase0_stdlib_import=SKIPPED(already_ok)")

# typing(functools経由)より先に collections.abc 親属性を保証
_prime_collections_abc_binding(_base_lib_diag)

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

    if _cached_files and _io is not None:
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
if _meipass and zipfile is not None:
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
_diag_path = os.path.join(_err_dir, 'kototsuna_rthook_diag.txt')
try:
    with _builtin_open(_diag_path, 'w', encoding='utf-8') as _df:
        _df.write(f"rthook_version={_RTHOOK_VERSION}\n")
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
            _df.write(f"safe_base={_safe_base}\n")
            _df.write(f"safe_base_exists={os.path.isfile(_safe_base) if _safe_base else 'N/A'}\n")
            _df.write(f"meta_path_count={len(sys.meta_path)}\n")
            _df.write(f"meta_path[0]={type(sys.meta_path[0]).__name__ if sys.meta_path else 'EMPTY'}\n")
            _df.write(f"init_tcl_exists={os.path.isfile(os.path.join(_meipass, '_tcl_data', 'init.tcl'))}\n")
            _df.write(f"TCL_LIBRARY={os.environ.get('TCL_LIBRARY', '')}\n")
            _df.write(f"TK_LIBRARY={os.environ.get('TK_LIBRARY', '')}\n")
        else:
            _df.write("NOT FROZEN\n")
except Exception:
    pass
