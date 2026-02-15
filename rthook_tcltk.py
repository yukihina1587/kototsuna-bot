# PyInstaller runtime hook: Tcl/Tk ZIPを展開
# spec側のruntime_hooksで指定され、標準rthookより先に実行される。
# tcl_tk_data.zipを_MEIPASS直下に展開し、_tcl_data/_tk_dataを作成。
import os
import sys
import zipfile
import tempfile

_meipass = getattr(sys, '_MEIPASS', None)

# 詳細診断をファイルに出力
_diag_path = os.path.join(tempfile.gettempdir(), 'kototsuna_rthook_diag.txt')
try:
    with open(_diag_path, 'w', encoding='utf-8') as _df:
        _df.write(f"meipass={_meipass}\n")
        _df.write(f"frozen={getattr(sys, 'frozen', False)}\n")

        if _meipass:
            _zip_path = os.path.join(_meipass, 'tcl_tk_data.zip')
            _tcl_dir = os.path.join(_meipass, '_tcl_data')
            _tk_dir = os.path.join(_meipass, '_tk_data')

            _df.write(f"zip_path={_zip_path}\n")
            _df.write(f"zip_exists={os.path.isfile(_zip_path)}\n")
            if os.path.isfile(_zip_path):
                _df.write(f"zip_size={os.path.getsize(_zip_path)}\n")

            # _MEIPASS直下のファイル一覧（最上位のみ）
            _df.write("meipass_root_entries=\n")
            try:
                for entry in sorted(os.listdir(_meipass))[:50]:
                    full = os.path.join(_meipass, entry)
                    kind = 'DIR' if os.path.isdir(full) else f'FILE({os.path.getsize(full)})'
                    _df.write(f"  {entry} [{kind}]\n")
            except Exception as e:
                _df.write(f"  ERROR: {e}\n")

            # _tcl_dataディレクトリの中身
            _df.write(f"tcl_dir_exists={os.path.isdir(_tcl_dir)}\n")
            if os.path.isdir(_tcl_dir):
                _df.write("tcl_dir_contents=\n")
                try:
                    for entry in sorted(os.listdir(_tcl_dir))[:20]:
                        _df.write(f"  {entry}\n")
                except Exception as e:
                    _df.write(f"  ERROR: {e}\n")

            # ZIP展開を試行
            if os.path.isfile(_zip_path):
                _df.write("zip_extraction=attempting\n")
                try:
                    with zipfile.ZipFile(_zip_path, 'r') as zf:
                        _df.write(f"zip_namelist_count={len(zf.namelist())}\n")
                        _df.write(f"zip_first_5={zf.namelist()[:5]}\n")
                        zf.extractall(_meipass)
                    _df.write("zip_extraction=success\n")
                except Exception as e:
                    _df.write(f"zip_extraction=FAILED: {e}\n")

                # 展開後の確認
                init_tcl = os.path.join(_tcl_dir, 'init.tcl')
                _df.write(f"init_tcl_after_extract={os.path.isfile(init_tcl)}\n")
            else:
                _df.write("zip_extraction=skipped (zip not found)\n")

            # TCL_LIBRARY/TK_LIBRARYを設定
            if os.path.isdir(_tcl_dir):
                os.environ['TCL_LIBRARY'] = _tcl_dir
                _df.write(f"set_TCL_LIBRARY={_tcl_dir}\n")
            if os.path.isdir(_tk_dir):
                os.environ['TK_LIBRARY'] = _tk_dir
                _df.write(f"set_TK_LIBRARY={_tk_dir}\n")
        else:
            _df.write("NOT FROZEN - skipping\n")
except Exception:
    # 診断ファイル書き込み自体が失敗してもアプリ起動を妨げない
    # ただしZIP展開は↓で再試行
    pass

# 診断書き込みに失敗してもZIP展開は実行（フォールバック）
if _meipass:
    _zip_path = os.path.join(_meipass, 'tcl_tk_data.zip')
    _tcl_dir = os.path.join(_meipass, '_tcl_data')
    _tk_dir = os.path.join(_meipass, '_tk_data')
    if os.path.isfile(_zip_path) and not os.path.isfile(os.path.join(_tcl_dir, 'init.tcl')):
        try:
            with zipfile.ZipFile(_zip_path, 'r') as zf:
                zf.extractall(_meipass)
        except Exception:
            pass
    if os.path.isdir(_tcl_dir):
        os.environ['TCL_LIBRARY'] = _tcl_dir
    if os.path.isdir(_tk_dir):
        os.environ['TK_LIBRARY'] = _tk_dir
