import sys
import io
import os
import tempfile
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.*=false'  # Qt DPI警告を抑制

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


def write_tcl_diagnostic(note: str) -> None:
    """Tcl/Tk関連の診断情報をTempへ書き出す。"""
    try:
        report_path = os.path.join(tempfile.gettempdir(), "kototsuna_tcl_diag.txt")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"note={note}\n")
            f.write(f"frozen={getattr(sys, 'frozen', False)}\n")
            f.write(f"base_dir={BASE_DIR}\n")
            f.write(f"TCL_LIBRARY={os.environ.get('TCL_LIBRARY', '')}\n")
            f.write(f"TK_LIBRARY={os.environ.get('TK_LIBRARY', '')}\n")
            f.write("found_init_tcl=\n")
            for root, dirs, files in os.walk(BASE_DIR):
                if "init.tcl" in files:
                    f.write(f"  {os.path.join(root, 'init.tcl')}\n")
            f.write("found_tk_tcl=\n")
            for root, dirs, files in os.walk(BASE_DIR):
                if "tk.tcl" in files:
                    f.write(f"  {os.path.join(root, 'tk.tcl')}\n")
    except Exception:
        pass


configure_tcl_tk_paths()
write_tcl_diagnostic("startup")

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
        write_tcl_diagnostic("ctk_init_failed")
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

    # 少し遅延してメインアプリを初期化（スプラッシュが表示されるように）
    root.after(500, init_app)
    root.mainloop()
