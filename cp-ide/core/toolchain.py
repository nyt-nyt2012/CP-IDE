"""C++ toolchain discovery and compilation.

Locates a MinGW-w64 g++ on the machine, compiles a source file and parses the
GCC diagnostics into structured records that the front-end can turn into
clickable markers in the editor.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .paths import exe_dir

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_STD = "c++14"
SUPPORTED_STDS = ("c++11", "c++14", "c++17", "c++20", "c++23", "gnu++14", "gnu++17")

#: Flags offered by the "编译环境" panel. Every entry maps a UI key to the
#: real compiler switch.
WARNING_FLAGS = {
    "wall": "-Wall",
    "wextra": "-Wextra",
    "wshadow": "-Wshadow",
    "wconversion": "-Wconversion",
    "wpedantic": "-Wpedantic",
    "wunused": "-Wunused",
}

OPT_LEVELS = ("-O0", "-O1", "-O2", "-O3", "-Os", "-Ofast")


# --------------------------------------------------------------------------- #
#  toolchain discovery
# --------------------------------------------------------------------------- #
def _candidate_roots() -> List[str]:
    roots: List[str] = []

    env_root = os.environ.get("CPIDE_TOOLCHAIN_ROOT")
    if env_root:
        roots.append(env_root)
    # 打包成 exe 后，winlibs 往往就放在 exe 旁边
    roots.append(exe_dir())
    roots.append(APP_DIR)
    roots.append(os.path.dirname(APP_DIR))
    home = os.path.expanduser("~")
    roots.append(os.path.join(home, "Desktop"))
    roots.append(os.path.join(home, "Downloads"))

    unique: List[str] = []
    for root in roots:
        if root and os.path.isdir(root) and root not in unique:
            unique.append(root)
    return unique


def _walk_for_gpp(root: str, max_depth: int = 3) -> Optional[str]:
    """Look for ``g++.exe`` inside *root* without walking the whole disk."""
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for current, dirs, files in os.walk(root):
        depth = current.count(os.sep) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() != "node_modules"]
        if "g++.exe" in files:
            candidate = os.path.join(current, "g++.exe")
            if os.path.isfile(candidate):
                return candidate
    return None


def find_cxx() -> Optional[str]:
    """Return the path of the g++ executable, or ``None`` when not found."""
    env = os.environ.get("CPIDE_CXX")
    if env and os.path.isfile(env):
        return env

    which = shutil.which("g++") or shutil.which("g++.exe")
    if which:
        return which

    for root in _candidate_roots():
        found = _walk_for_gpp(root)
        if found:
            return found
    return None


_cxx_cache: Optional[str] = None
_cxx_version: Optional[str] = None


def cxx_path() -> Optional[str]:
    global _cxx_cache
    if _cxx_cache is None:
        _cxx_cache = find_cxx() or ""
    return _cxx_cache or None


def cxx_version() -> str:
    """Human readable version banner of the detected compiler."""
    global _cxx_version
    if _cxx_version is not None:
        return _cxx_version
    cxx = cxx_path()
    if not cxx:
        _cxx_version = ""
        return _cxx_version
    try:
        proc = subprocess.run(
            [cxx, "--version"],
            capture_output=True,
            timeout=20,
            creationflags=_creation_flags(),
            startupinfo=_startup_info(),
        )
        _cxx_version = _decode(proc.stdout).strip()
    except Exception:  # pragma: no cover - defensive
        _cxx_version = ""
    return _cxx_version


def _creation_flags() -> int:
    """启动编译器时的窗口标志。

    注意：这里**不能**加 CREATE_NO_WINDOW —— g++ 会继续派生子进程
    (cc1plus / as / ld)，一旦 g++ 自己没有控制台，这些子进程就会
    各自新建一个**可见**的控制台窗口，编译时就会闪出黑框。
    正确做法是保留控制台、但把窗口隐藏（见 _startup_info）。
    """
    from .winflags import creation_flags

    return creation_flags()


def _startup_info():
    """隐藏编译器及其子进程的控制台窗口。"""
    from .winflags import startup_info

    return startup_info()


def _decode(raw: bytes) -> str:
    """Decode compiler output, tolerating the local code page."""
    for encoding in ("utf-8", "gbk", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
#  build workspace
# --------------------------------------------------------------------------- #
_work_root: Optional[str] = None


def _is_ascii_path(path: str) -> bool:
    return all(ord(ch) < 128 for ch in path)


def _can_link_here(directory: str) -> bool:
    """Check that the linker is able to create an executable in *directory*."""
    cxx = cxx_path()
    if not cxx:
        return False
    source = os.path.join(directory, "_probe.cpp")
    target = os.path.join(directory, "_probe.exe")
    try:
        with open(source, "w", encoding="ascii") as fh:
            fh.write("int main(){return 0;}\n")
        proc = subprocess.run(
            [cxx, "-x", "c++", "-std=c++14", source, "-o", target],
            capture_output=True,
            timeout=90,
            creationflags=_creation_flags(),
            startupinfo=_startup_info(),
        )
        return proc.returncode == 0 and os.path.isfile(target)
    except Exception:
        return False
    finally:
        for path in (source, target):
            try:
                os.remove(path)
            except OSError:
                pass


def find_work_root() -> str:
    """Return a directory the MinGW linker can write executables into.

    The ``ld.exe`` of the MinGW tool chain cannot create a file when the
    path contains non ASCII characters, so the build directory is moved to a
    safe location (the temporary directory of the user) whenever the
    project itself lives in such a folder.
    """
    global _work_root
    if _work_root:
        return _work_root

    candidates: List[str] = []
    env = os.environ.get("CPIDE_WORK_DIR")
    if env:
        candidates.append(env)
    candidates.append(os.path.join(tempfile.gettempdir(), "cpide-work"))
    candidates.append(os.path.join(APP_DIR, "data", "work"))
    drive = os.path.splitdrive(APP_DIR)[0]
    if drive:
        candidates.append(os.path.join(drive + os.sep, "cpide-work"))

    fallback = candidates[-1]
    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
        except Exception:
            continue
        if _is_ascii_path(candidate) or _can_link_here(candidate):
            _work_root = candidate
            return _work_root
    _work_root = fallback
    return _work_root


def new_workspace(prefix: str = "work") -> str:
    """Create a fresh, empty build directory."""
    import uuid

    root = find_work_root()
    path = os.path.join(root, "%s-%s" % (prefix, uuid.uuid4().hex[:12]))
    os.makedirs(path, exist_ok=True)
    _OWNED_WORKSPACES.append(path)
    try:
        with open(os.path.join(path, ".cpide-owner"), "w", encoding="utf-8") as fh:
            fh.write("%d\n%.3f\n" % (os.getpid(), time.time()))
    except OSError:  # pragma: no cover - defensive
        pass
    return path


#: 本进程创建出来的构建目录，正常退出时一并清掉
_OWNED_WORKSPACES: List[str] = []


def _cleanup_owned_workspaces() -> None:
    """进程退出时删掉自己创建的临时构建目录。"""
    for path in list(_OWNED_WORKSPACES):
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:  # pragma: no cover - defensive
            pass
    _OWNED_WORKSPACES.clear()


atexit.register(_cleanup_owned_workspaces)


def purge_stale_workspaces(max_age_seconds: float = 3 * 3600.0) -> int:
    """清理上一次运行残留的临时构建目录，返回删掉的数量。

    会话表只能在**进程还活着**的时候回收自己的目录；一旦 IDE 被强杀、
    或者直接跑测试脚本，这些目录就永久留在临时目录里（一次开发下来能堆
    上百个、几百 MB）。所以每次启动时顺手把「明显过期」的旧目录清掉。

    ``max_age_seconds`` 默认三小时：既不会误删正在运行的那个实例的目录，
    也能把上一次崩溃留下的垃圾清干净。
    """
    root = find_work_root()
    now = time.time()
    removed = 0
    try:
        names = os.listdir(root)
    except OSError:  # pragma: no cover - defensive
        return 0
    for name in names:
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        created = 0.0
        try:
            with open(os.path.join(path, ".cpide-owner"), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            if len(lines) >= 2:
                created = float(lines[1])
        except (OSError, ValueError):
            created = 0.0
        if not created:
            # 没有归属标记的（老版本留下的），按目录自己的修改时间判断
            try:
                created = os.path.getmtime(path)
            except OSError:
                continue
        if now - created < max_age_seconds:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed += 1
    return removed


# --------------------------------------------------------------------------- #
#  compile settings
# --------------------------------------------------------------------------- #
@dataclass
class CompileSettings:
    """Everything the user can tweak in the "编译环境" panel."""

    std: str = DEFAULT_STD
    warnings: List[str] = field(default_factory=list)
    opt: str = "-O2"
    debug: bool = False
    static: bool = False
    sanitize: bool = False
    extra_args: str = ""
    language: str = "cpp"

    def sanitised(self) -> "CompileSettings":
        """Return a copy with invalid values replaced by safe defaults."""
        std = self.std if self.std in SUPPORTED_STDS else DEFAULT_STD
        warnings = [w for w in self.warnings if w in WARNING_FLAGS]
        opt = self.opt if self.opt in OPT_LEVELS else "-O2"
        extra = re.sub(r"[\r\n]+", " ", self.extra_args or "").strip()
        return CompileSettings(
            std=std,
            warnings=warnings,
            opt=opt,
            debug=bool(self.debug),
            static=bool(self.static),
            sanitize=bool(self.sanitize),
            extra_args=extra,
            language=self.language or "cpp",
        )

    def build_command(self, source: str, output: str, cxx: Optional[str] = None) -> List[str]:
        """Assemble the full compiler command line."""
        compiler = cxx or cxx_path() or "g++"
        cmd: List[str] = [compiler]
        cmd += ["-x", "c++" if self.language in ("cpp", "c++", "cc") else self.language,
                "-std=" + self.std]
        for key in self.warnings:
            cmd.append(WARNING_FLAGS[key])
        if self.opt:
            cmd.append(self.opt)
        if self.debug:
            cmd.append("-g")
        if self.static:
            cmd.append("-static")
        if self.sanitize:
            cmd += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        if self.extra_args:
            cmd += self.extra_args.split()
        cmd += [source, "-o", output]
        return cmd


@dataclass
class Diagnostic:
    severity: str          # error | warning | note
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    col: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "col": self.col,
        }


@dataclass
class CompileResult:
    ok: bool
    exit_code: int
    duration_ms: int
    command: List[str]
    stdout: str
    stderr: str
    diagnostics: List[Diagnostic] = field(default_factory=list)
    exe_path: str = ""
    script_path: str = ""      # Python 等脚本语言：待运行的脚本路径
    timed_out: bool = False
    message: str = ""

    @property
    def errors(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == "warning")

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "errors": self.errors,
            "warnings": self.warnings,
            "exe_path": self.exe_path,
            "script_path": self.script_path,
            "timed_out": self.timed_out,
            "message": self.message,
        }


# --------------------------------------------------------------------------- #
#  diagnostic parsing
# --------------------------------------------------------------------------- #
_DIAG_RE = re.compile(
    r"^(?P<file>(?:[A-Za-z]:)?[^:\n]*?):(?P<line>\d+)(?::(?P<col>\d+))?:\s*"
    r"(?P<severity>fatal error|error|warning|note):\s*(?P<message>.*)$"
)
_BARE_RE = re.compile(r"^(?P<severity>fatal error|error|warning|note):\s*(?P<message>.*)$")


def parse_diagnostics(text: str) -> List[Diagnostic]:
    """Parse GCC/clang style diagnostics out of *text*."""
    result: List[Diagnostic] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        m = _DIAG_RE.match(line)
        if m:
            severity = m.group("severity")
            if severity == "fatal error":
                severity = "error"
            result.append(
                Diagnostic(
                    severity=severity,
                    message=m.group("message").strip(),
                    file=m.group("file").strip(),
                    line=int(m.group("line")),
                    col=int(m.group("col")) if m.group("col") else None,
                )
            )
            continue
        m = _BARE_RE.match(line)
        if m:
            severity = m.group("severity")
            if severity == "fatal error":
                severity = "error"
            result.append(
                Diagnostic(
                    severity=severity,
                    message=m.group("message").strip(),
                )
            )
    return result


# --------------------------------------------------------------------------- #
#  compilation
# --------------------------------------------------------------------------- #
def compile_source(
    code: str,
    work_dir: str,
    settings: Optional[CompileSettings] = None,
    filename: str = "main.cpp",
    timeout: int = 60,
) -> CompileResult:
    """Compile *code* inside *work_dir* and return a structured result."""
    settings = (settings or CompileSettings()).sanitised()
    cxx = cxx_path()
    if not cxx:
        return CompileResult(
            ok=False,
            exit_code=-1,
            duration_ms=0,
            command=[],
            stdout="",
            stderr="",
            message="未找到 C++ 编译器 g++。请在设置中指定编译器路径，或解压 winlibs 压缩包。",
        )

    os.makedirs(work_dir, exist_ok=True)
    source = os.path.join(work_dir, filename)
    exe = os.path.join(work_dir, os.path.splitext(filename)[0] + ".exe")
    with open(source, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(code)

    command = settings.build_command(source, exe, cxx)
    started = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.run(
            command,
            cwd=work_dir,
            capture_output=True,
            timeout=timeout,
            creationflags=_creation_flags(),
            startupinfo=_startup_info(),
        )
        stdout = _decode(proc.stdout)
        stderr = _decode(proc.stderr)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout = ""
        stderr = "编译超时（超过 %d 秒），可能是代码中存在死循环或过大的模板。" % timeout
        exit_code = -9
    except Exception as exc:  # pragma: no cover - defensive
        stdout = ""
        stderr = "无法启动编译器：%s" % exc
        exit_code = -1
    duration_ms = int((time.perf_counter() - started) * 1000)

    combined = stderr + ("\n" + stdout if stdout else "")
    diagnostics = parse_diagnostics(combined)
    ok = (exit_code == 0) and not timed_out and os.path.isfile(exe)

    message = ""
    if timed_out:
        message = "编译超时"
    elif exit_code != 0:
        message = "编译失败（退出码 %d）" % exit_code
    elif not ok:
        message = "编译失败：未生成可执行文件"

    return CompileResult(
        ok=ok,
        exit_code=exit_code,
        duration_ms=duration_ms,
        command=command,
        stdout=stdout,
        stderr=stderr,
        diagnostics=diagnostics,
        exe_path=exe if ok else "",
        timed_out=timed_out,
        message=message,
    )
