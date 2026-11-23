"""点 Git Credential Manager 的 “Sign in with your browser”。

为什么需要：git push 走 GCM 会弹一个原生窗口，命令行没法点它，只能模拟鼠标。
窗口是固定布局（Browser / Device / Token 三个页签 + 两个按钮），
“Sign in with your browser” 在窗口内约 (52%, 45%) 的位置。

用法：python _click_gcm.py            # 只报告窗口位置
      python _click_gcm.py --go       # 真的点
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # 按物理像素，避免坐标被缩放
except Exception:
    pass

u = ctypes.windll.user32
TITLE = "Connect to GitHub"


def find_window():
    hits = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        n = u.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            u.GetWindowTextW(hwnd, buf, n + 1)
            if TITLE.lower() in buf.value.lower():
                hits.append((hwnd, buf.value))
        return True

    u.EnumWindows(cb, 0)
    return hits


def rect(hwnd):
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def click(x, y):
    u.SetCursorPos(int(x), int(y))
    time.sleep(0.15)
    u.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
    time.sleep(0.05)
    u.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP


def main():
    hits = find_window()
    if not hits:
        print("没找到窗口：%r（GCM 可能已经关掉或还没弹）" % TITLE)
        return 1
    for hwnd, title in hits:
        x, y, w, h = rect(hwnd)
        print("窗口 %r hwnd=%d 位置=(%d,%d) 尺寸=%dx%d" % (title, hwnd, x, y, w, h))
        # 按钮相对位置（实测：窗口 525x452 时蓝按钮中心在 (50%, 56.6%)）
        bx, by = x + w * 0.50, y + h * 0.566
        print("目标按钮 ≈ (%d, %d)" % (bx, by))
        if "--go" in sys.argv:
            u.ShowWindow(hwnd, 9)          # SW_RESTORE
            u.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            click(bx, by)
            print("已点击")
    return 0


if __name__ == "__main__":
    sys.exit(main())
