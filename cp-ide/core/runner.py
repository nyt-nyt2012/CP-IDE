"""Execution of the compiled program with time & memory accounting.

The runner spawns the program, feeds it the test data on stdin and measures

* the wall clock time (milliseconds), and
* the peak working set size / peak commit charge (KB) using the Windows
  ``GetProcessMemoryInfo`` API.

Both the time limit and the memory limit are enforced while the process is
running, so a program that allocates too much memory or loops forever is
killed instead of hanging the judge.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

# --------------------------------------------------------------------------- #
#  verdict constants
# --------------------------------------------------------------------------- #
STATUS_AC = "accept"
STATUS_WA = "wrong_answer"
STATUS_PE = "presentation_error"
STATUS_TLE = "time_limit_exceeded"
STATUS_MLE = "memory_limit_exceeded"
STATUS_RE = "runtime_error"
STATUS_OLE = "output_limit_exceeded"
STATUS_JUDGING = "judging"
STATUS_COMPILING = "compiling"
STATUS_PENDING = "pending"
STATUS_UNKNOWN = "unknown_error"
STATUS_SKIPPED = "skipped"

STATUS_LABELS = {
    STATUS_AC: "Accept (AC)",
    STATUS_WA: "Wrong Answer (WA)",
    STATUS_PE: "Presentation Error (PE)",
    STATUS_TLE: "Time Limit Exceeded (TLE)",
    STATUS_MLE: "Memory Limit Exceeded (MLE)",
    STATUS_RE: "Runtime Error (RE)",
    STATUS_OLE: "Output Limit Exceeded (OLE)",
    STATUS_JUDGING: "Judging",
    STATUS_COMPILING: "Compiling",
    STATUS_PENDING: "Pending",
    STATUS_UNKNOWN: "Unknown Error",
    STATUS_SKIPPED: "Skipped",
}

#: Exit codes used by the bundled mini testlib custom checker.
CUSTOM_CHECKER_CODES = {
    0: STATUS_AC,
    1: STATUS_WA,
    2: STATUS_PE,
    3: STATUS_WA,
    4: STATUS_WA,
    5: STATUS_UNKNOWN,
}


# --------------------------------------------------------------------------- #
#  Windows memory counters
# --------------------------------------------------------------------------- #
class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("PageFaultCount", ctypes.wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


_psapi = None
if os.name == "nt":  # pragma: no branch - platform check
    try:
        _psapi = ctypes.WinDLL("psapi")
        _psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            ctypes.wintypes.DWORD,
        ]
        _psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
    except Exception:  # pragma: no cover - defensive
        _psapi = None


def _read_memory(handle) -> tuple:
    """Return ``(peak_working_set_kb, peak_commit_kb)`` for a process handle."""
    if _psapi is None or handle is None:
        return (0, 0)
    counters = _PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    try:
        ok = _psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
    except Exception:  # pragma: no cover - defensive
        return (0, 0)
    if not ok:
        return (0, 0)
    return (counters.PeakWorkingSetSize // 1024, counters.PeakPagefileUsage // 1024)


# --------------------------------------------------------------------------- #
#  result container
# --------------------------------------------------------------------------- #
@dataclass
class RunResult:
    status: str = STATUS_UNKNOWN
    time_ms: int = 0
    memory_kb: int = 0
    commit_kb: int = 0
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    message: str = ""
    output_truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "time_ms": self.time_ms,
            "memory_kb": self.memory_kb,
            "commit_kb": self.commit_kb,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "message": self.message,
            "output_truncated": self.output_truncated,
        }


def _kill_tree(pid: int) -> None:
    """Kill a process and all of its children."""
    if os.name == "nt":
        try:
            from .winflags import creation_flags, startup_info

            # taskkill 本身也是个控制台程序：不给它窗口，免得又闪一个黑框。
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=15,
                creationflags=creation_flags(no_window=True),
                startupinfo=startup_info(),
            )
            return
        except Exception:  # pragma: no cover - fall through
            pass
    try:
        os.kill(pid, 9)
    except Exception:  # pragma: no cover - defensive
        pass


def _read_limited(path: str, limit_bytes: int) -> tuple:
    """Read at most *limit_bytes* from *path* and report whether it was cut."""
    if not os.path.exists(path):
        return ("", False)
    size = os.path.getsize(path)
    truncated = size > limit_bytes
    with open(path, "rb") as fh:
        raw = fh.read(limit_bytes)
    for encoding in ("utf-8", "gbk", "cp1252"):
        try:
            return (raw.decode(encoding), truncated)
        except UnicodeDecodeError:
            continue
    return (raw.decode("utf-8", errors="replace"), truncated)


def run_program(
    exe_path: str,
    input_data: str = "",
    time_limit_ms: int = 1000,
    memory_limit_mb: int = 256,
    output_limit_kb: int = 256,
    work_dir: Optional[str] = None,
    args: Optional[List[str]] = None,
) -> RunResult:
    """Run *exe_path* under the given limits and return a :class:`RunResult`."""
    if not exe_path or not os.path.isfile(exe_path):
        result = RunResult()
        result.status = STATUS_UNKNOWN
        result.message = "可执行文件不存在，请先编译。"
        return result

    work_dir = work_dir or os.path.dirname(os.path.abspath(exe_path))
    return run_command(
        [exe_path] + list(args or []),
        input_data=input_data,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
        output_limit_kb=output_limit_kb,
        work_dir=work_dir,
    )


def _spawn(
    command: List[str],
    stdin_fh,
    stdout_fh,
    stderr_fh,
    work_dir: str,
    creationflags: int,
    startupinfo,
):
    """启动被测程序，返回 ``(进程, 错误)``。

    刚编译出来的可执行文件偶尔会被杀毒软件（国产安全卫士最容易「积极」）
    拦一下：先报「拒绝访问」，过一会儿可能直接被隔离删除。
    「拒绝访问」通常只是安全软件正在扫描、临时占用了文件，等一下重试就能启动；
    真的被删掉了就只能如实告诉用户。
    """
    last_error = None
    for attempt in range(3):
        try:
            proc = subprocess.Popen(
                command,
                stdin=stdin_fh,
                stdout=stdout_fh,
                stderr=stderr_fh,
                cwd=work_dir,
                creationflags=creationflags,
                startupinfo=startupinfo,
            )
            return proc, None
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.25 * (attempt + 1))
        except OSError as exc:
            last_error = exc
            break
    return None, last_error


def _launch_error_message(command: List[str], error) -> str:
    """启动失败时给用户一句看得懂的解释。"""
    target = command[0] if command else ""
    if isinstance(error, FileNotFoundError):
        missing = getattr(error, "filename", "") or target
        return (
            "要运行的文件不见了：%s\n"
            "它多半刚被杀毒软件隔离或删除了（刚编译出来的程序最容易被误伤）。\n"
            "换个目录保存代码、把它加进信任列表，或者临时关掉实时防护再试。"
            % missing
        )
    if isinstance(error, PermissionError) or getattr(error, "winerror", None) == 5:
        return (
            "系统拒绝启动这个程序（错误 5：拒绝访问）。\n"
            "刚编译出来的可执行文件常被杀毒软件拦一下，稍等几秒重试，"
            "或者把 %s 所在目录加进信任列表。" % target
        )
    return "运行失败：%s" % (error if error is not None else "未知错误")


def run_command(
    command: List[str],
    input_data: str = "",
    time_limit_ms: int = 1000,
    memory_limit_mb: int = 256,
    output_limit_kb: int = 256,
    work_dir: Optional[str] = None,
) -> RunResult:
    """Run an arbitrary command under the given limits and return a :class:`RunResult`.

    Used for C++ executables as well as for scripts (Python), which are run
    through the interpreter instead of a compiled binary.
    """
    result = RunResult()
    if not command:
        result.status = STATUS_UNKNOWN
        result.message = "没有可执行的命令。"
        return result

    time_limit_ms = max(1, int(time_limit_ms))
    memory_limit_mb = max(1, int(memory_limit_mb))
    output_limit_bytes = max(1, int(output_limit_kb)) * 1024
    work_dir = work_dir or os.getcwd()

    stdin_path = os.path.join(work_dir, ".stdin.tmp")
    stdout_path = os.path.join(work_dir, ".stdout.tmp")
    stderr_path = os.path.join(work_dir, ".stderr.tmp")
    with open(stdin_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(input_data or "")

    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        from .winflags import creation_flags, startup_info as _startup_info

        # 运行的是用户自己的程序（还有 checker、Python 脚本）：
        # 它们不需要控制台，用 CREATE_NO_WINDOW 直接不给分配，
        # 就不会出现那个一闪而过的黑色控制台窗口。
        creationflags = creation_flags(no_window=True)
        startupinfo = _startup_info()

    started = time.perf_counter()
    mle_hit = False
    ole_hit = False
    proc = None
    launch_error = None
    elapsed_ms = 0
    exit_code = None
    peak_ws = 0
    peak_commit = 0
    try:
        with open(stdin_path, "rb") as stdin_fh, \
                open(stdout_path, "wb") as stdout_fh, \
                open(stderr_path, "wb") as stderr_fh:
            proc, launch_error = _spawn(
                command,
                stdin_fh,
                stdout_fh,
                stderr_fh,
                work_dir,
                creationflags,
                startupinfo,
            )

            if proc is not None:
                # Watchdog: enforce the time limit and the memory limit while the
                # program is running.
                deadline = started + time_limit_ms / 1000.0
                mem_limit_kb = memory_limit_mb * 1024
                handle = getattr(proc, "_handle", None)
                while True:
                    if proc.poll() is not None:
                        break
                    now = time.perf_counter()
                    if now > deadline:
                        break
                    ws, commit = _read_memory(handle)
                    peak_ws = max(peak_ws, ws)
                    peak_commit = max(peak_commit, commit)
                    if commit and commit > mem_limit_kb:
                        mle_hit = True
                        break
                    try:
                        if os.path.getsize(stdout_path) > output_limit_bytes:
                            ole_hit = True
                            break
                    except OSError:
                        pass
                    time.sleep(0.004)

                if proc.poll() is None:
                    _kill_tree(proc.pid)
                    try:
                        proc.wait(timeout=5)
                    except Exception:  # pragma: no cover - defensive
                        pass

                elapsed_ms = int((time.perf_counter() - started) * 1000)
                ws, commit = _read_memory(handle)
                peak_ws = max(peak_ws, ws)
                peak_commit = max(peak_commit, commit)
                exit_code = proc.returncode
    except Exception as exc:  # pragma: no cover - defensive
        result.status = STATUS_UNKNOWN
        result.message = "运行失败：%s" % exc
        return result

    stdout, out_truncated = _read_limited(stdout_path, output_limit_bytes)
    stderr, err_truncated = _read_limited(stderr_path, output_limit_bytes)
    for path in (stdin_path, stdout_path, stderr_path):
        try:
            os.remove(path)
        except OSError:
            pass
    result.stdout = stdout
    result.stderr = stderr
    result.time_ms = elapsed_ms
    result.memory_kb = peak_ws
    result.commit_kb = peak_commit
    result.exit_code = exit_code
    result.output_truncated = out_truncated or err_truncated

    if proc is None:
        # 根本没启动起来：文件被安全软件拦了/删了，或者路径不对。
        result.status = STATUS_RE
        result.message = _launch_error_message(command, launch_error)
        return result

    if mle_hit:
        result.status = STATUS_MLE
        result.message = "内存超出限制（%d MB）" % memory_limit_mb
    elif ole_hit:
        result.status = STATUS_OLE
        result.message = "输出超过限制（%d KB）" % output_limit_kb
    elif elapsed_ms > time_limit_ms:
        result.status = STATUS_TLE
        result.message = "运行时间 %d ms 超过限制 %d ms" % (elapsed_ms, time_limit_ms)
    elif exit_code is not None and exit_code < 0:
        result.status = STATUS_RE
        result.message = "程序被信号 %d 终止" % (-exit_code)
    elif exit_code not in (0, None):
        result.status = STATUS_RE
        result.message = "程序返回非零退出码 %d" % exit_code
    else:
        result.status = STATUS_AC
        result.message = "运行成功"

    return result
