"""CP-IDE 桌面版入口。

打包成 exe 之后双击即可运行：本地起一个 Flask 服务器，再用内嵌窗口
（Microsoft Edge WebView2）打开 IDE 界面；关掉窗口即退出整个程序，
不需要另外开控制台，也不需要在浏览器里手动敲地址。

在没有 WebView2 的机器上会自动退回到 Edge 的「应用模式」窗口，
再不行就退回系统默认浏览器 + 一个极简的控制面板。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request

APP_TITLE = "CP-IDE · 竞赛编程 IDE"
PREFERRED_PORT = 5000
PORT_SPAN = 60


# --------------------------------------------------------------------------- #
#  端口与服务器
# --------------------------------------------------------------------------- #
def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_port(start: int = PREFERRED_PORT, span: int = PORT_SPAN) -> int:
    """挑一个没被占用的本地端口。"""
    for port in range(start, start + span):
        if _port_is_free(port):
            return port
    raise RuntimeError("本机 %d-%d 端口都被占用，无法启动服务器" % (start, start + span - 1))


def wait_until_ready(port: int, timeout: float = 40.0) -> bool:
    """等服务器真正能响应了再开窗口，避免出现白屏。"""
    url = "http://127.0.0.1:%d/api/toolchain" % port
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def start_server(port: int) -> threading.Thread:
    """在后台线程里跑 Flask 服务器。"""
    from app import app

    thread = threading.Thread(
        target=app.run,
        kwargs=dict(
            host="127.0.0.1",
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False,
        ),
        daemon=True,
        name="cpide-server",
    )
    thread.start()
    return thread


# --------------------------------------------------------------------------- #
#  三种开窗口的方式
# --------------------------------------------------------------------------- #
def open_embedded_window(url: str) -> bool:
    """首选：用 WebView2 开一个真正的内嵌窗口。"""
    try:
        import webview
    except Exception:
        return False
    try:
        # 窗口标题就固定这几个字；版本与构建时间在「设置 → 外观 → 关于」里看
        title = APP_TITLE
        webview.create_window(
            title,
            url,
            width=1500,
            height=940,
            min_size=(1024, 640),
            confirm_close=False,
        )
        # private_mode=True 时 WebView2 用的是临时目录，关掉窗口浏览器里的
        # localStorage（草稿、设置）会全部消失；固定 storage_path 之后才会保留。
        storage = os.path.join(os.environ.get("LOCALAPPDATA", "."), "CP-IDE", "webview")
        try:
            os.makedirs(storage, exist_ok=True)
        except OSError:
            storage = None
        webview.start(private_mode=False, storage_path=storage)
        return True
    except Exception as exc:  # pragma: no cover - 取决于运行环境
        _log("内嵌窗口启动失败：%s" % exc)
        return False


def find_edge() -> str:
    """找系统里的 msedge.exe。"""
    candidates = [
        os.path.join(
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
        os.path.join(
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Microsoft", "Edge", "Application", "msedge.exe",
        ),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ""


def open_edge_app_window(url: str) -> bool:
    """退路一：用 Edge 的「应用模式」开一个没有浏览器边框的窗口。"""
    edge = find_edge()
    if not edge:
        return False
    profile = os.path.join(os.environ.get("TEMP", "."), "cpide-edge-profile")
    try:
        proc = subprocess.Popen(
            [
                edge,
                "--app=" + url,
                "--user-data-dir=" + profile,
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=Translate",
            ]
        )
    except OSError:
        return False
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    return True


def open_browser_with_panel(url: str) -> None:
    """退路二：系统默认浏览器 + 一个极简控制面板（用来退出程序）。"""
    import webbrowser

    webbrowser.open(url)

    try:
        import tkinter as tk
    except Exception:
        while True:
            time.sleep(3600)
        return

    root = tk.Tk()
    root.title("CP-IDE")
    root.configure(background="#131a26")
    root.resizable(False, False)
    tk.Label(
        root,
        text="CP-IDE 已经在浏览器中打开",
        background="#131a26",
        foreground="#d7dfec",
        font=("Microsoft YaHei UI", 11),
    ).pack(padx=26, pady=(22, 6))
    tk.Label(
        root,
        text=url,
        background="#131a26",
        foreground="#6ea8ff",
        font=("Consolas", 10),
    ).pack(padx=26, pady=(0, 16))

    def reopen() -> None:
        webbrowser.open(url)

    def quit_all() -> None:
        root.destroy()
        os._exit(0)

    buttons = tk.Frame(root, background="#131a26")
    buttons.pack(pady=(0, 22))
    tk.Button(
        buttons, text="重新打开", width=12, command=reopen,
        bg="#1d2637", fg="#d7dfec", activebackground="#27344a", relief="flat",
    ).pack(side="left", padx=6)
    tk.Button(
        buttons, text="退出 CP-IDE", width=12, command=quit_all,
        bg="#8b3a3a", fg="#ffffff", activebackground="#a34545", relief="flat",
    ).pack(side="left", padx=6)
    root.mainloop()


def _log(message: str) -> None:
    """打包成无控制台 exe 后，日志只能写文件。"""
    try:
        log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "."), "CP-IDE")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "desktop.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
#  入口
# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        port = pick_port()
    except RuntimeError as exc:
        _log(str(exc))
        open_browser_with_panel("")
        return 1

    url = "http://127.0.0.1:%d/" % port
    _log("启动服务器：%s" % url)
    start_server(port)

    if not wait_until_ready(port):
        _log("服务器启动超时")
        open_browser_with_panel(url)
        return 1

    # 1) 内嵌窗口
    if open_embedded_window(url):
        _log("窗口已关闭，退出")
        return 0

    # 2) Edge 应用模式窗口
    if open_edge_app_window(url):
        _log("Edge 窗口已关闭，退出")
        return 0

    # 3) 默认浏览器 + 控制面板
    open_browser_with_panel(url)
    return 0


if __name__ == "__main__":
    # 打包成 exe 之后，这个可执行文件同时充当 Python 解释器：
    # 用户脚本通过 "CP-IDE.exe --cpide-run 脚本.py" 启动。
    if len(sys.argv) >= 3 and sys.argv[1] == "--cpide-run":
        from core.pyrunner import run_script_file

        sys.exit(run_script_file(sys.argv[2], sys.argv[3:]))
    sys.exit(main())
