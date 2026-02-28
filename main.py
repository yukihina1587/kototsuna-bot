import sys
import io
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# --- 多重起動防止 (Windows Named Mutex) ---
if sys.platform == "win32":
    import ctypes
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "KototsunaAppMutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)

# PyInstaller GUIモードでのクラッシュログ記録（console=Falseではトレースバックが見えないため）
# rthookで設置済みのraw excepthookを上書きし、可能ならtraceback moduleで詳細出力する。
# 失敗時はraw方式（osモジュールのみ）にフォールバック。
if getattr(sys, 'frozen', False):
    def _kototsuna_excepthook(exc_type, exc_value, exc_tb):
        # exeの隣にエラーログを出力（ユーザーが見つけやすい）
        _exe_dir = os.path.dirname(sys.executable) if hasattr(sys, 'executable') and sys.executable else ''
        if _exe_dir:
            try:
                _test = os.path.join(_exe_dir, '.kototsuna_write_test')
                _tfd = os.open(_test, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                os.close(_tfd)
                os.unlink(_test)
            except OSError:
                _exe_dir = ''
        _err_path = os.path.join(
            _exe_dir or os.environ.get('TEMP', os.environ.get('TMP', '.')),
            'kototsuna_error.txt'
        )
        _written = False
        # 方法1: traceback module使用（詳細なトレースバック）
        try:
            import traceback
            with open(_err_path, 'w', encoding='utf-8') as f:
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
            _written = True
        except Exception:
            pass
        # 方法2: raw方式フォールバック（osモジュールのみ、base_library.zip不要）
        if not _written:
            try:
                _lines = [f"exc_type={exc_type}", f"exc_value={exc_value}", "traceback:"]
                _tb = exc_tb
                while _tb is not None:
                    _frame = _tb.tb_frame
                    _code = _frame.f_code
                    _lines.append(f"  File \"{_code.co_filename}\", line {_tb.tb_lineno}, in {_code.co_name}")
                    _tb = _tb.tb_next
                _text = '\n'.join(_lines) + '\n'
                _fd = os.open(_err_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                os.write(_fd, _text.encode('utf-8', errors='replace'))
                os.close(_fd)
            except Exception:
                pass
        # stderrへの出力も試行
        try:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
        except Exception:
            pass
    sys.excepthook = _kototsuna_excepthook

# PyInstaller: 旧_MEIPASSのSSL証明書パスを現在の_MEIPASSに修正
# アップデート後の再起動で旧パスが環境変数に残り、TLSエラーになる対策
if getattr(sys, 'frozen', False):
    _meipass = getattr(sys, '_MEIPASS', '')
    if _meipass:
        _cert = os.path.join(_meipass, 'certifi', 'cacert.pem')
        if os.path.exists(_cert):
            os.environ['SSL_CERT_FILE'] = _cert
            os.environ['REQUESTS_CA_BUNDLE'] = _cert

# コンソールウィンドウを非表示（console=True + hide-early のバックアップ）
if sys.platform == "win32" and getattr(sys, 'frozen', False):
    try:
        import ctypes
        _hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if _hwnd:
            ctypes.windll.user32.ShowWindow(_hwnd, 0)  # SW_HIDE
    except Exception:
        pass

# PyInstallerでの相対パス解決用にsrcをパスへ追加
BASE_DIR = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

def configure_tcl_tk_paths() -> None:
    """PyInstaller onefile環境でTcl/Tkパスを補正する。"""
    tcl_candidates = [
        os.path.join(BASE_DIR, "_tcl_data"),
        os.path.join(BASE_DIR, "_tcl_data", "tcl8.6"),
        os.path.join(BASE_DIR, "_internal", "_tcl_data"),
        os.path.join(BASE_DIR, "_internal", "_tcl_data", "tcl8.6"),
        os.path.join(BASE_DIR, "tcl", "tcl8.6"),
    ]
    tk_candidates = [
        os.path.join(BASE_DIR, "_tk_data"),
        os.path.join(BASE_DIR, "_tk_data", "tk8.6"),
        os.path.join(BASE_DIR, "_internal", "_tk_data"),
        os.path.join(BASE_DIR, "_internal", "_tk_data", "tk8.6"),
        os.path.join(BASE_DIR, "tcl", "tk8.6"),
    ]

    def _pick_with_file(candidates, filename):
        for path in candidates:
            if os.path.isfile(os.path.join(path, filename)):
                return path
        return ""

    tcl_path = _pick_with_file(tcl_candidates, "init.tcl")
    tk_path = _pick_with_file(tk_candidates, "tk.tcl")

    if not tcl_path or not tk_path:
        for root, dirs, files in os.walk(BASE_DIR):
            if not tcl_path and "init.tcl" in files:
                tcl_path = root
            if not tk_path and "tk.tcl" in files:
                tk_path = root
            if tcl_path and tk_path:
                break

    if tcl_path:
        os.environ["TCL_LIBRARY"] = tcl_path
    if tk_path:
        os.environ["TK_LIBRARY"] = tk_path


configure_tcl_tk_paths()

# PyInstaller GUIモード(console=False)ではstdout/stderrがNoneになる
# customtkinter等がwrite()を試みるとAttributeErrorになるため、devnullにリダイレクト
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import tkinter as tk
from dotenv import load_dotenv

# ロガーを最初にインポート（他のモジュールより先に初期化）
from src.logger import logger  # noqa: E402

import customtkinter as ctk  # noqa: E402
import src.overlay_server  # noqa: E402
import src.voice_listener  # noqa: E402
import src.translator      # noqa: E402
from src.gui import KototsunaApp  # noqa: E402

# .envの読み込み
load_dotenv()

# Windows環境での文字化け対策
# 注意: --windowed (GUIモード) で起動した場合、sys.stdout は None になるためチェックが必要
if sys.platform == "win32":
    if sys.stdout is not None:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    if sys.stderr is not None:
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def create_splash_screen():
    """起動時のスプラッシュスクリーンを作成"""
    splash = tk.Toplevel()
    splash.title("ことつな！")
    splash.overrideredirect(True)  # ウィンドウ枠を非表示

    # 画面中央に配置
    window_width = 400
    window_height = 400
    screen_width = splash.winfo_screenwidth()
    screen_height = splash.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    splash.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # 背景色
    splash.configure(bg="#0C1424")

    # アイコン画像を表示
    try:
        from PIL import Image, ImageTk
        icon_path = os.path.join(BASE_DIR, "assets", "icon.png")
        # AV隔離で_MEIのアイコンが消失した場合、runtime_cacheからフォールバック
        if not os.path.exists(icon_path):
            _rc = os.environ.get('KOTOTSUNA_RUNTIME_CACHE', '')
            if _rc:
                icon_path = os.path.join(_rc, "assets", "icon.png")
        if os.path.exists(icon_path):
            # PILで画像を開いてリサイズ
            pil_image = Image.open(icon_path)
            # 元の画像のアスペクト比を保持して250x250にリサイズ
            pil_image.thumbnail((250, 250), Image.Resampling.LANCZOS)
            icon_image = ImageTk.PhotoImage(pil_image)

            icon_label = tk.Label(splash, image=icon_image, bg="#0C1424")
            icon_label.image = icon_image  # type: ignore[attr-defined]  # 参照を保持
            icon_label.pack(pady=40)
    except Exception as e:
        logger.warning(f"スプラッシュスクリーンのアイコン読み込みエラー: {e}")

    # ローディングテキスト
    loading_label = tk.Label(
        splash,
        text="読み込み中...",
        font=("Segoe UI", 16),
        fg="#9BAEC6",
        bg="#0C1424"
    )
    loading_label.pack(pady=20)

    # アプリ名
    app_name_label = tk.Label(
        splash,
        text="ことつな！",
        font=("Segoe UI", 24, "bold"),
        fg="#22C55E",
        bg="#0C1424"
    )
    app_name_label.pack(pady=10)

    splash.update()
    return splash

def on_closing():
    """ウィンドウを閉じる際のクリーンアップ処理"""
    try:
        # アプリケーションのリソースを解放
        app.cleanup_resources()
    except Exception as e:
        logger.error(f"クリーンアップ中のエラー: {e}", exc_info=True)
    finally:
        # ウィンドウを破棄
        root.destroy()

if __name__ == '__main__':
    # 前回アップデート後のクリーンアップ
    if "--cleanup" in sys.argv:
        import time
        time.sleep(2)
        from src.updater import cleanup_old_exe
        cleanup_old_exe()

    # メインウィンドウを作成（非表示）
    try:
        root = ctk.CTk()
    except Exception:
        raise
    root.withdraw()  # 最初は非表示

    # スプラッシュスクリーンを表示
    splash = create_splash_screen()

    # メインアプリを初期化
    def init_app():
        global app
        try:
            app = KototsunaApp(root)
            # ウィンドウを閉じる際のプロトコルを設定
            root.protocol("WM_DELETE_WINDOW", on_closing)
            # スプラッシュスクリーンを閉じる
            splash.destroy()
            # メインウィンドウを表示
            root.deiconify()
        except Exception as e:
            logger.critical(f"アプリケーション初期化エラー: {e}", exc_info=True)
            splash.destroy()
            root.destroy()

    # スプラッシュ描画後にメインアプリを初期化
    root.after(100, init_app)
    root.mainloop()
