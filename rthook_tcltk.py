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
_RTHOOK_VERSION = "1.4.13"

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

# 前回のエラーファイルを削除（古いエラーがユーザーを混乱させるのを防止）
try:
    if os.path.isfile(_raw_err_path):
        os.unlink(_raw_err_path)
except OSError:
    pass

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

        # --- B: パス差し替え（常に実行） ---
        # AV隔離はrthook完了後に発生しうる（TOCTOU問題）ため、
        # _MEIからのコピー成否に関わらず常にsafe_baseへ切り替える。
        # collections.abc.Hashableの破壊は_prime_collections_abc_binding()で防止。

        if os.path.isfile(_safe_base):
            # --- B. 完全パス差し替え ---
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

            # B-5. base_library.zip内パッケージの__path__/__spec__を修正
            # import shutilがcollections等のパッケージを読み込む際に
            # __path__が旧_MEIパスで設定される。これを修正しないと
            # _prime_collections_abc_binding()等が旧パスのcacheを再生成する。
            _fixed_modules = 0
            for _mod in sys.modules.values():
                if _mod is None:
                    continue
                try:
                    if hasattr(_mod, '__path__'):
                        _new_paths = []
                        _changed = False
                        for _p in _mod.__path__:
                            if _old_base_path.lower() in _p.lower():
                                _new_paths.append(
                                    _p.lower().replace(
                                        _old_base_path.lower(),
                                        _safe_base
                                    ) if os.name != 'nt' else
                                    _p.replace(_old_base_path, _safe_base)
                                )
                                _changed = True
                            else:
                                _new_paths.append(_p)
                        if _changed:
                            _mod.__path__ = _new_paths
                            _fixed_modules += 1
                    if hasattr(_mod, '__spec__') and _mod.__spec__:
                        _spec = _mod.__spec__
                        if _spec.origin and _old_base_path.lower() in _spec.origin.lower():
                            _spec.origin = _spec.origin.replace(_old_base_path, _safe_base)
                        if _spec.submodule_search_locations:
                            _spec.submodule_search_locations = [
                                _p.replace(_old_base_path, _safe_base)
                                if _old_base_path.lower() in _p.lower() else _p
                                for _p in _spec.submodule_search_locations
                            ]
                except Exception:
                    pass
            _base_lib_diag.append(f"modules_fixed={_fixed_modules}")

            _base_lib_relocated = True

    except Exception as _e:
        _base_lib_diag.append(f"error={_e}")

# ── Phase 0.5: 全バイナリプリキャッシュ（AV隔離前にコピー） ──
# _MEI内の全.pyd/.so/.dllファイルをruntime_cacheに退避。
# base_library.zipと同じ戦略: AV隔離より先にコピーし、常にsafe copyを使用。
# .pyd/.so → _pyd_safe_map登録（Python importフォールバック用）
# .dll → ディレクトリ構造ごとコピー（os.add_dll_directoryフォールバック用）
# !! builtins.open(rb/wb)のみ使用（stdlib不要） !!
_pyd_cache_diag = []
_pyd_safe_map = {}  # fullname → safe_path（Phase 0.5bのfinderが使用）
_dll_cached = 0
_data_cached = 0
if _meipass and _safe_dir:
    # ── 重要データファイルを最優先でコピー（os.walkループより前） ──
    # os.walkによるバイナリコピーは時間がかかるため、その間にAVが
    # tcl_tk_data.zipやテーマJSONを隔離する。先にこれらを退避する。
    _critical_files = [
        'tcl_tk_data.zip',
        os.path.join('customtkinter', 'assets', 'themes', 'blue.json'),
        os.path.join('customtkinter', 'assets', 'themes', 'green.json'),
        os.path.join('assets', 'icon.png'),
        os.path.join('assets', 'icon_fullsize.ico'),
    ]
    for _crit_rel in _critical_files:
        _crit_src = os.path.join(_meipass, _crit_rel)
        _crit_dst = os.path.join(_safe_dir, _crit_rel)
        try:
            os.makedirs(os.path.dirname(_crit_dst), exist_ok=True)
            with _builtin_open(_crit_src, 'rb') as _fin:
                _crit_data = _fin.read()
            with _builtin_open(_crit_dst, 'wb') as _fout:
                _fout.write(_crit_data)
            del _crit_data
            _data_cached += 1
        except (FileNotFoundError, PermissionError, OSError):
            pass
    _pyd_cache_diag.append(f"data_cached={_data_cached}")

    _pyd_cache_root = os.path.join(_safe_dir, 'pyd_cache')
    _copy_skipped = 0
    for _walk_dir, _, _walk_files in os.walk(_meipass):
        _rel_dir = os.path.relpath(_walk_dir, _meipass)
        for _fname in _walk_files:
            _is_pyd = _fname.endswith('.pyd') or _fname.endswith('.so')
            _is_dll = _fname.endswith('.dll')
            if not (_is_pyd or _is_dll):
                continue

            _pyd_src = os.path.join(_walk_dir, _fname)
            _safe_subdir = _pyd_cache_root if _rel_dir == '.' else os.path.join(_pyd_cache_root, _rel_dir)
            _pyd_dst = os.path.join(_safe_subdir, _fname)

            # サイズが同じなら再コピー不要（2回目以降の起動を高速化）
            try:
                _src_size = os.path.getsize(_pyd_src)
                if os.path.isfile(_pyd_dst) and os.path.getsize(_pyd_dst) == _src_size:
                    if _is_pyd:
                        _mod_base = _fname.split('.')[0]
                        _fullname = _mod_base if _rel_dir == '.' else _rel_dir.replace(os.sep, '.') + '.' + _mod_base
                        _pyd_safe_map[_fullname] = _pyd_dst
                    else:
                        _dll_cached += 1
                    _copy_skipped += 1
                    continue
            except OSError:
                pass

            try:
                os.makedirs(_safe_subdir, exist_ok=True)
                with _builtin_open(_pyd_src, 'rb') as _fin:
                    _pyd_data = _fin.read()
                with _builtin_open(_pyd_dst, 'wb') as _fout:
                    _fout.write(_pyd_data)
                del _pyd_data
                if _is_pyd:
                    _mod_base = _fname.split('.')[0]
                    _fullname = _mod_base if _rel_dir == '.' else _rel_dir.replace(os.sep, '.') + '.' + _mod_base
                    _pyd_safe_map[_fullname] = _pyd_dst
                else:
                    _dll_cached += 1
            except (FileNotFoundError, PermissionError, OSError):
                if _is_pyd and os.path.isfile(_pyd_dst):
                    _mod_base = _fname.split('.')[0]
                    _fullname = _mod_base if _rel_dir == '.' else _rel_dir.replace(os.sep, '.') + '.' + _mod_base
                    _pyd_safe_map[_fullname] = _pyd_dst
                elif _is_dll and os.path.isfile(_pyd_dst):
                    _dll_cached += 1
    _pyd_cache_diag.append(f"pyd_cached={len(_pyd_safe_map)}")
    _pyd_cache_diag.append(f"dll_cached={_dll_cached}")
    _pyd_cache_diag.append(f"copy_skipped={_copy_skipped}")

    # _pyd_cache_rootをDLL検索パスに追加（トップレベルDLLの解決用）
    # _tkinter.pydがpyd_cache/から読まれる際、tcl86t.dll等の依存DLLも
    # pyd_cache/にあるためここをDLL検索パスに追加する必要がある
    if os.name == 'nt' and hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(_pyd_cache_root)
            _pyd_cache_diag.append("pyd_cache_dll_dir=YES")
        except OSError:
            _pyd_cache_diag.append("pyd_cache_dll_dir=FAIL")

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

# ── 最終キャッシュ掃除 ──
# _prime_collections_abc_binding()等がcollections.abcをimportする際に
# 旧_MEIパスのキャッシュエントリが再生成される場合がある。最終掃除で除去。
if _meipass and _safe_base and _base_lib_relocated:
    _final_cleaned = 0
    _old_mei_lower = os.path.join(_meipass, 'base_library.zip').lower()
    for _key in list(sys.path_importer_cache.keys()):
        if _old_mei_lower in str(_key).lower():
            # 旧パスのエントリをsafe_baseの同等エントリに差し替え
            _suffix = ''
            _key_str = str(_key)
            _bl_idx = _key_str.lower().find('base_library.zip')
            if _bl_idx >= 0:
                _suffix = _key_str[_bl_idx + len('base_library.zip'):]
            _new_key = _safe_base + _suffix
            try:
                _new_imp = zipimport.zipimporter(_new_key)
                sys.path_importer_cache[_new_key] = _new_imp
            except Exception:
                pass
            del sys.path_importer_cache[_key]
            _final_cleaned += 1
    # zipimport._zip_directory_cacheも再掃除
    if hasattr(zipimport, '_zip_directory_cache'):
        for _key in list(zipimport._zip_directory_cache.keys()):
            if _old_mei_lower in str(_key).lower():
                del zipimport._zip_directory_cache[_key]
                _final_cleaned += 1
    _base_lib_diag.append(f"final_cache_cleaned={_final_cleaned}")

# ── Phase 0.5b: 汎用C拡張safe import finder ──────────────────
# _pyd_safe_mapに登録された全Cエクステンションをruntime_cacheから読み込む。
# sys.meta_pathの先頭に挿入し、TOCTOU回避（常にsafe copyを使用）。
_pyd_finder_installed = False
if _pyd_safe_map:
    try:
        import importlib.util

        class _SafePydFinder:
            """AV隔離時にruntime_cacheからC拡張をロードする汎用finder"""

            def find_spec(self, fullname, path, target=None):
                _safe_path = _pyd_safe_map.get(fullname)
                if _safe_path and os.path.isfile(_safe_path):
                    return importlib.util.spec_from_file_location(
                        fullname, _safe_path
                    )
                return None

        sys.meta_path.insert(0, _SafePydFinder())
        _pyd_finder_installed = True
        _pyd_cache_diag.append("finder=installed")
    except Exception as _finder_err:
        _pyd_cache_diag.append(f"finder=FAIL:{_finder_err}")

# ── Phase 0.5c: os.add_dll_directory パッチ ──────────────────
# pygameなどのパッケージはos.add_dll_directory(pkg_dir)でDLL検索パスを登録する。
# AV隔離で_MEI内のパッケージディレクトリが消失するとFileNotFoundErrorになる。
# runtime_cache/pyd_cache/の同等パスにフォールバックする。
_dll_dir_patched = False
if os.name == 'nt' and hasattr(os, 'add_dll_directory') and _meipass and _safe_dir:
    _orig_add_dll_dir = os.add_dll_directory
    _pyd_cache_root_ref = os.path.join(_safe_dir, 'pyd_cache')

    def _safe_add_dll_directory(path):
        try:
            return _orig_add_dll_dir(path)
        except (FileNotFoundError, OSError):
            # _MEI配下のパスならruntime_cacheの同等パスを試行
            try:
                _rel = os.path.relpath(path, _meipass)
                if not _rel.startswith('..'):
                    _cache_path = os.path.join(_pyd_cache_root_ref, _rel)
                    if os.path.isdir(_cache_path):
                        return _orig_add_dll_dir(_cache_path)
            except (ValueError, OSError):
                pass
            raise

    os.add_dll_directory = _safe_add_dll_directory
    _dll_dir_patched = True
    _pyd_cache_diag.append("dll_dir_patched=YES")

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
        _content = None
        # _MEIから読み込み試行
        if os.path.isfile(_abs):
            try:
                with _builtin_open(_abs, 'r', encoding='utf-8') as _f:
                    _content = _f.read()
            except Exception:
                pass
        # _MEI失敗時はruntime_cacheからフォールバック
        if _content is None and _safe_dir:
            _cache_abs = os.path.join(_safe_dir, _rel)
            if os.path.isfile(_cache_abs):
                try:
                    with _builtin_open(_cache_abs, 'r', encoding='utf-8') as _f:
                        _content = _f.read()
                except Exception:
                    pass
        if _content is not None:
            _cached_files[os.path.normpath(_abs)] = _content

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
# AV隔離対策: _MEI展開後もAVがファイルを隔離するため、runtime_cacheにも展開し
# TCL_LIBRARY/TK_LIBRARYをruntime_cacheに向ける（TOCTOU回避）
if _meipass and zipfile is not None:
    _zip_path = os.path.join(_meipass, 'tcl_tk_data.zip')
    # AV隔離で_MEIのZIPが消失した場合、runtime_cacheのコピーを使用
    if not os.path.isfile(_zip_path) and _safe_dir:
        _zip_path_cache = os.path.join(_safe_dir, 'tcl_tk_data.zip')
        if os.path.isfile(_zip_path_cache):
            _zip_path = _zip_path_cache

    if os.path.isfile(_zip_path):
        # _MEIにも展開（PyInstallerの他のrthookとの互換性）
        try:
            with zipfile.ZipFile(_zip_path, 'r') as zf:
                zf.extractall(_meipass)
        except Exception:
            pass
        # runtime_cacheにも展開（AV隔離に対する安全コピー）
        if _safe_dir:
            try:
                with zipfile.ZipFile(_zip_path, 'r') as zf:
                    zf.extractall(_safe_dir)
            except Exception:
                pass

    # TCL_LIBRARY/TK_LIBRARYの設定:
    # runtime_cacheの展開先を優先（AV隔離耐性あり）、なければ_MEIを使用
    _tcl_dir_safe = os.path.join(_safe_dir, '_tcl_data') if _safe_dir else None
    _tk_dir_safe = os.path.join(_safe_dir, '_tk_data') if _safe_dir else None
    _tcl_dir_mei = os.path.join(_meipass, '_tcl_data')
    _tk_dir_mei = os.path.join(_meipass, '_tk_data')

    if _tcl_dir_safe and os.path.isdir(_tcl_dir_safe):
        os.environ['TCL_LIBRARY'] = _tcl_dir_safe
    elif os.path.isdir(_tcl_dir_mei):
        os.environ['TCL_LIBRARY'] = _tcl_dir_mei
    if _tk_dir_safe and os.path.isdir(_tk_dir_safe):
        os.environ['TK_LIBRARY'] = _tk_dir_safe
    elif os.path.isdir(_tk_dir_mei):
        os.environ['TK_LIBRARY'] = _tk_dir_mei

    # ── Phase 2.1: pyi_rth__tkinter.py 対策 ──────────────────
    # PyInstallerの組み込みランタイムフック pyi_rth__tkinter.py は:
    #   1. os.path.isdir(_MEI/_tcl_data) をチェック → なければFileNotFoundError
    #   2. os.environ['TCL_LIBRARY'] = _MEI/_tcl_data に上書き
    # AV隔離で_MEI/_tcl_dataが消失すると①でクラッシュし、
    # 消失しなくても②で我々のruntime_cacheパスが上書きされる。
    # 両方を防ぐ: isdir偽装 + 環境変数書き込みブロック
    _orig_isdir = os.path.isdir
    _fake_tcl_dirs = frozenset([
        os.path.normpath(os.path.join(_meipass, '_tcl_data')),
        os.path.normpath(os.path.join(_meipass, '_tk_data')),
    ])

    def _safe_isdir_for_tcl(path):
        if os.path.normpath(path) in _fake_tcl_dirs:
            return True
        return _orig_isdir(path)

    os.path.isdir = _safe_isdir_for_tcl

    _orig_env_setitem = os.environ.__class__.__setitem__
    _protected_env_keys = frozenset(['TCL_LIBRARY', 'TK_LIBRARY'])

    def _protected_env_set(self, key, value):
        if key in _protected_env_keys:
            return
        _orig_env_setitem(self, key, value)

    os.environ.__class__.__setitem__ = _protected_env_set

# ── Phase 2.5: 古い_MEIディレクトリの自動削除 ──────────────
# PyInstaller onefileモードはクラッシュ時に_MEI*を削除しないため残骸が蓄積する。
# 2箇所をチェック:
#   1. _MEI親ディレクトリ（%TEMP%）: 現在の_MEI以外の古い残骸
#   2. exe隣（Desktop等）: 旧バージョン(runtime_tmpdir='.')時代の残骸
_mei_cleaned = 0
if _meipass and shutil is not None:
    _mei_current = os.path.basename(_meipass)
    _cleanup_dirs = set()
    _cleanup_dirs.add(os.path.dirname(_meipass))
    if hasattr(sys, 'executable') and sys.executable:
        _cleanup_dirs.add(os.path.dirname(sys.executable))
    for _cleanup_dir in _cleanup_dirs:
        try:
            for _entry in os.listdir(_cleanup_dir):
                if _entry.startswith('_MEI') and _entry != _mei_current:
                    _old_mei = os.path.join(_cleanup_dir, _entry)
                    if os.path.isdir(_old_mei):
                        try:
                            shutil.rmtree(_old_mei)
                            _mei_cleaned += 1
                        except OSError:
                            pass
        except OSError:
            pass

# ── runtime_cacheパスをアプリに公開 ──────────────────────
# main.py/gui.pyがAV隔離時にruntime_cacheからアセットを読めるようにする
if _meipass and _safe_dir:
    os.environ['KOTOTSUNA_RUNTIME_CACHE'] = _safe_dir

# ── Phase 3: 診断出力 ───────────────────────────────────
_diag_dir = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'Kototsuna') if _meipass else _err_dir
_diag_path = os.path.join(_diag_dir, 'kototsuna_rthook_diag.txt')
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
            _df.write(f"pyd_cache_count={len(_pyd_cache_diag)}\n")
            for _d in _pyd_cache_diag:
                _df.write(f"  {_d}\n")
            _df.write(f"pyd_finder_installed={_pyd_finder_installed}\n")
            _df.write(f"pyd_safe_map_size={len(_pyd_safe_map)}\n")
            _df.write(f"mei_cleaned={_mei_cleaned}\n")
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
