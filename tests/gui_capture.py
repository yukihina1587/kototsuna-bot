"""WSLgでもテスト用のTkウィンドウだけを撮影する（任意のプレビュー用）。"""

import ctypes as ct
import sys
from ctypes.util import find_library

from PIL import Image, ImageGrab


def capture_window(root) -> Image.Image:
    root.update()
    width, height = root.winfo_width(), root.winfo_height()
    if sys.platform != "linux":
        x, y = root.winfo_rootx(), root.winfo_rooty()
        return ImageGrab.grab(bbox=(x, y, x + width, y + height))

    # WSLgではroot windowのGetImageが失敗するため、このウィンドウを直接読む。
    class XImage(ct.Structure):
        _fields_ = [(name, ct.c_int) for name in ("width", "height", "xoffset", "format")] + [
            ("data", ct.c_void_p),
        ] + [(name, ct.c_int) for name in (
            "byte_order", "bitmap_unit", "bitmap_bit_order", "bitmap_pad", "depth",
            "bytes_per_line", "bits_per_pixel",
        )] + [(name, ct.c_ulong) for name in ("red_mask", "green_mask", "blue_mask")]

    lib = ct.CDLL(find_library("X11"))
    lib.XOpenDisplay.argtypes, lib.XOpenDisplay.restype = [ct.c_char_p], ct.c_void_p
    lib.XGetImage.argtypes = [ct.c_void_p, ct.c_ulong, ct.c_int, ct.c_int,
                             ct.c_uint, ct.c_uint, ct.c_ulong, ct.c_int]
    lib.XGetImage.restype = ct.POINTER(XImage)
    lib.XDestroyImage.argtypes = [ct.POINTER(XImage)]
    lib.XCloseDisplay.argtypes = [ct.c_void_p]
    display = lib.XOpenDisplay(None)
    if not display:
        raise RuntimeError("テスト画面のディスプレイに接続できません")
    snapshot = None
    try:
        snapshot = lib.XGetImage(display, root.winfo_id(), 0, 0, width, height, ct.c_ulong(-1), 2)
        if not snapshot:
            raise RuntimeError("テスト画面を取得できません")
        frame = snapshot.contents
        if (frame.bits_per_pixel, frame.byte_order, frame.red_mask) != (32, 0, 0xFF0000):
            raise RuntimeError("プレビュー未対応のピクセル形式です")
        data = ct.string_at(frame.data, frame.bytes_per_line * height)
        return Image.frombytes("RGB", (width, height), data, "raw", "BGRX", frame.bytes_per_line)
    finally:
        if snapshot:
            lib.XDestroyImage(snapshot)
        lib.XCloseDisplay(display)
