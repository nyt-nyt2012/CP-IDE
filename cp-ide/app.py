"""CP-IDE - a local web IDE and judge for C++ competitive programming.

Run with::

    python app.py

and open http://127.0.0.1:5000/ in the browser.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

from flask import Flask, Response, jsonify, render_template, request, send_from_directory
from flask import __version__ as flask_version

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import languages  # noqa: E402
from core import licenses as license_lib  # noqa: E402
from core import savedialog  # noqa: E402
from core import snippets as snippet_lib  # noqa: E402
from core import winflags  # noqa: E402
from core import workspace as workspace_lib  # noqa: E402
from core.checker import CHECKER_CHOICES, CHECKER_LABELS, compare  # noqa: E402
from core.formatter import FormatOptions, format_code  # noqa: E402
from core.paths import data_dir, resource_dir  # noqa: E402
from core.pyrunner import check_syntax, interpreter, script_command, write_script  # noqa: E402
from core.runner import (  # noqa: E402
    CUSTOM_CHECKER_CODES,
    STATUS_AC,
    STATUS_COMPILING,
    STATUS_JUDGING,
    STATUS_LABELS,
    STATUS_PE,
    STATUS_UNKNOWN,
    STATUS_WA,
    run_command,
    run_program,
)
from core.testconfig import ConfigError, auto_pair_files, parse_config  # noqa: E402
from core.toolchain import (  # noqa: E402
    CompileResult,
    CompileSettings,
    Diagnostic,
    SUPPORTED_STDS,
    WARNING_FLAGS,
    compile_source,
    cxx_path,
    cxx_version,
    find_work_root,
    new_workspace,
    purge_stale_workspaces,
)
from core.version import BUILD, VERSION  # noqa: E402

APP_DIR = resource_dir()
DATA_DIR = data_dir()
WORK_DIR = os.path.join(DATA_DIR, "work")
os.makedirs(WORK_DIR, exist_ok=True)

# 启动时顺手清掉上一次残留的临时构建目录（IDE 被强杀 / 跑测试脚本都会留下）
try:
    _stale = purge_stale_workspaces()
    if _stale:
        print("已清理 %d 个残留的临时构建目录" % _stale)
except Exception:  # pragma: no cover - 清理失败不影响启动
    pass

# 内置 testlib：用户上传测试数据时无需再自行附带 testlib.h
INCLUDE_DIR = os.path.join(APP_DIR, "include")
TESTLIB_PATH = os.path.join(INCLUDE_DIR, "testlib.h")
CHECKER_TEMPLATE_PATH = os.path.join(INCLUDE_DIR, "checker_template.cpp")

#: 文件名（不区分大小写）
CHECKER_FILENAMES = ("checker.cpp", "checker.cc", "checker.cxx", "check.cpp", "chk.cpp")
#: 上传数据里可能出现的 testlib 头文件名
TESTLIB_FILENAMES = ("testlib.h",)

app = Flask(
    __name__,
    static_folder=os.path.join(APP_DIR, "static"),
    template_folder=os.path.join(APP_DIR, "templates"),
)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024 * 1024
# 即使不是 debug 模式也实时加载模板与静态文件，改完刷新即可看到效果
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True


# --------------------------------------------------------------------------- #
#  session handling
# --------------------------------------------------------------------------- #
class Session:
    """Keeps a compiled executable around so it can be reused."""

    def __init__(self, session_id: str, directory: str):
        self.id = session_id
        self.dir = directory
        self.exe = ""
        self.script = ""
        self.language = "cpp"
        self.python_path = ""
        self.source_hash = ""
        self.settings: Dict = {}

    def to_dict(self) -> dict:
        return {
            "session_id": self.id,
            "has_executable": bool(self.exe),
            "script": self.script,
            "language": self.language,
            "source_hash": self.source_hash,
        }


SESSIONS: "OrderedDict[str, Session]" = OrderedDict()
MAX_SESSIONS = 24


def _register_session(session: Session) -> None:
    SESSIONS[session.id] = session
    while len(SESSIONS) > MAX_SESSIONS:
        _, old = SESSIONS.popitem(last=False)
        shutil.rmtree(old.dir, ignore_errors=True)


def _new_workspace(prefix: str = "work") -> str:
    return new_workspace(prefix)


def _source_hash(code: str, settings: CompileSettings) -> str:
    payload = code + "\n" + json.dumps(settings.sanitised().__dict__, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _settings_from_payload(payload: Optional[dict]) -> CompileSettings:
    payload = payload or {}
    return CompileSettings(
        std=str(payload.get("std") or "c++14"),
        warnings=[w for w in (payload.get("warnings") or []) if w in WARNING_FLAGS],
        opt=str(payload.get("opt") or "-O2"),
        debug=bool(payload.get("debug")),
        static=bool(payload.get("static")),
        sanitize=bool(payload.get("sanitize")),
        extra_args=str(payload.get("extra_args") or ""),
        language=str(payload.get("language") or "cpp"),
    ).sanitised()


def _python_path(payload: dict) -> str:
    """请求里指定的 Python 解释器路径。"""
    settings = payload.get("settings") or {}
    return str(settings.get("python_path") or "").strip()


def _compile_python(code: str, directory: str, python_path: str = "") -> CompileResult:
    """Python 的「编译」= 语法检查。

    通过 ``compile()`` 找出语法错误并给出行列号，界面上的诊断列表因此
    和 C++ 的编译错误一样可以点击跳转。
    """
    started = time.perf_counter()
    script = write_script(code, directory)
    check = check_syntax(code, os.path.basename(script))
    duration_ms = int((time.perf_counter() - started) * 1000)
    diagnostics = [
        Diagnostic(
            severity=item.get("severity", "error"),
            message=item.get("message", ""),
            file=item.get("file"),
            line=item.get("line"),
            col=item.get("col"),
        )
        for item in check["diagnostics"]
    ]
    command = [interpreter(python_path), "-m", "py_compile", os.path.basename(script)]
    return CompileResult(
        ok=check["ok"],
        exit_code=0 if check["ok"] else 1,
        duration_ms=duration_ms,
        command=command,
        stdout="",
        stderr="" if check["ok"] else check["message"],
        diagnostics=diagnostics,
        script_path=script,
        message=check["message"],
    )


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def _decode_bytes(raw: bytes) -> str:
    for encoding in ("utf-8", "gbk", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_uploaded_files() -> Tuple[List[Tuple[str, bytes]], Optional[bytes]]:
    """Return the uploaded files and an optional configuration file."""
    files: List[Tuple[str, bytes]] = []
    config_bytes: Optional[bytes] = None
    for storage in request.files.getlist("files[]"):
        name = os.path.basename(storage.filename or "file")
        if not name:
            continue
        data = storage.read()
        lower = name.lower()
        if lower.endswith((".cfg", ".ini", ".conf", ".txt")) and config_bytes is None \
                and len(files) == 0:
            config_bytes = data
            files.append((name, data))
        else:
            files.append((name, data))
    return files, config_bytes


def _extract_zip(data: bytes, target: str) -> List[Tuple[str, bytes]]:
    """Extract an uploaded zip archive, ignoring directory entries."""
    import io
    import zipfile

    result: List[Tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = os.path.basename(info.filename)
            if not name:
                continue
            try:
                result.append((name, archive.read(info)))
            except Exception:  # pragma: no cover - defensive
                continue
    return result


# --------------------------------------------------------------------------- #
#  testlib / checker 相关辅助
# --------------------------------------------------------------------------- #
def _expand_archives(files: Dict[str, bytes]) -> List[str]:
    """Expand every zip archive in ``files`` in place; return a note per archive."""
    notes: List[str] = []
    for name in list(files.keys()):
        if not name.lower().endswith(".zip"):
            continue
        try:
            inner = _extract_zip(files[name], "")
        except Exception as exc:  # pragma: no cover - defensive
            notes.append("解压 %s 失败：%s" % (name, exc))
            continue
        for inner_name, inner_data in inner:
            files.setdefault(inner_name, inner_data)
        notes.append("已解压 %s（%d 个文件）" % (name, len(inner)))
    return notes


def _pick_file(files: Dict[str, bytes], candidates) -> Optional[str]:
    """Find the first file whose name matches one of ``candidates``."""
    lowered = {name.lower(): name for name in files}
    for candidate in candidates:
        real = lowered.get(candidate)
        if real:
            return real
    return None


def _is_checker_filename(name: str) -> bool:
    return name.lower() in CHECKER_FILENAMES


def _is_testlib_filename(name: str) -> bool:
    return name.lower() in TESTLIB_FILENAMES


def _testlib_info() -> dict:
    """Metadata about the bundled testlib header."""
    info = {
        "available": False,
        "version": "",
        "path": "include/testlib.h",
        "size": 0,
        "template": "",
    }
    if os.path.isfile(TESTLIB_PATH):
        with open(TESTLIB_PATH, "rb") as fh:
            raw = fh.read()
        info["available"] = True
        info["size"] = len(raw)
        text = _decode_bytes(raw)
        match = re.search(r'#define\s+VERSION\s+"([^"]+)"', text)
        if match:
            info["version"] = match.group(1)
    if os.path.isfile(CHECKER_TEMPLATE_PATH):
        with open(CHECKER_TEMPLATE_PATH, encoding="utf-8") as fh:
            info["template"] = fh.read()
    return info


def _read_template() -> str:
    if not os.path.isfile(CHECKER_TEMPLATE_PATH):
        return ""
    with open(CHECKER_TEMPLATE_PATH, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
#  文档资源（PDF 等二进制文件）
# --------------------------------------------------------------------------- #
#: 文档资源（PDF 等）统一放在 %LOCALAPPDATA%\CP-IDE\assets，
#: 这样「源码运行」和「打包后的 exe」看到的是同一批文件。
ASSET_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "CP-IDE", "assets"
)
os.makedirs(ASSET_DIR, exist_ok=True)

#: token -> {"name": 文件名, "path": 落盘路径, "size": 大小}
ASSETS: "OrderedDict[str, dict]" = OrderedDict()
MAX_ASSETS = 24

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".py": "text/x-python; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def _guess_mime(name: str) -> str:
    ext = os.path.splitext(name or "")[1].lower()
    return _MIME_TYPES.get(ext, "application/octet-stream")


def _asset_path(token: str, name: str) -> str:
    ext = os.path.splitext(name or "")[1]
    return os.path.join(ASSET_DIR, token + ext)


def _load_assets() -> None:
    """把上次会话留下的文档重新登记进来（重启后 PDF 依然能打开）。"""
    if not os.path.isdir(ASSET_DIR):
        return
    for filename in sorted(os.listdir(ASSET_DIR)):
        stem, ext = os.path.splitext(filename)
        if len(stem) != 32:
            continue
        path = os.path.join(ASSET_DIR, filename)
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        ASSETS[stem] = {"name": stem + ext, "path": path, "size": size}


_load_assets()


@app.route("/api/assets", methods=["POST"])
def api_assets_upload():
    """保存一个本地文件（PDF 等），返回访问令牌。"""
    payload = request.get_json(silent=True) or {}
    name = os.path.basename(str(payload.get("name") or "file"))
    raw = payload.get("content_b64") or ""
    try:
        data = base64.b64decode(raw) if raw else b""
    except (binascii.Error, ValueError):
        data = b""
    token = uuid.uuid4().hex
    path = _asset_path(token, name)
    with open(path, "wb") as fh:
        fh.write(data)
    ASSETS[token] = {"name": name, "path": path, "size": len(data)}
    while len(ASSETS) > MAX_ASSETS:
        old_token, old = ASSETS.popitem(last=False)
        try:
            os.remove(old["path"])
        except OSError:
            pass
    return jsonify({"ok": True, "token": token, "name": name, "size": len(data)})


@app.route("/api/assets/<token>", methods=["GET"])
def api_assets_get(token: str):
    """把保存的文件取回去（浏览器内置阅读器 / pdf.js 直接读这个地址）。"""
    item = ASSETS.get(token)
    if not item or not os.path.isfile(item["path"]):
        return jsonify({"ok": False, "error": "文件不存在或已过期，请重新打开。"}), 404
    with open(item["path"], "rb") as fh:
        data = fh.read()
    response = Response(data, mimetype=_guess_mime(item["name"]))
    response.headers["Content-Disposition"] = (
        "inline; filename*=UTF-8''" + quote(item["name"])
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/assets/open", methods=["POST"])
def api_assets_open():
    """用系统默认程序打开这个文件。"""
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token") or "")
    item = ASSETS.get(token)
    if not item or not os.path.isfile(item["path"]):
        return jsonify({"ok": False, "error": "文件不存在或已过期，请重新打开。"}), 404
    if hasattr(os, "startfile"):
        try:
            os.startfile(item["path"])  # type: ignore[attr-defined]
            return jsonify({"ok": True})
        except OSError as exc:
            return jsonify({"ok": False, "error": "无法打开：%s" % exc})
    return jsonify({"ok": False, "error": "当前系统不支持用外部程序打开。"})


# --------------------------------------------------------------------------- #
#  工作区持久化（关掉 IDE 也不丢代码）
# --------------------------------------------------------------------------- #
@app.route("/api/workspace", methods=["GET"])
def api_workspace_get():
    """读取上次保存的工作区：标签页、编译信息、界面偏好等。"""
    return jsonify({"ok": True, "workspace": workspace_lib.load_workspace()})


@app.route("/api/workspace", methods=["POST"])
def api_workspace_save():
    """保存工作区。前端每次改动后都会调用（已做防抖）。"""
    payload = request.get_json(silent=True) or {}
    data = payload.get("workspace")
    if not isinstance(data, dict):
        data = {}
    try:
        result = workspace_lib.save_workspace(data)
    except OSError as exc:
        return jsonify({"ok": False, "error": "保存工作区失败：%s" % exc})
    return jsonify(result)


# --------------------------------------------------------------------------- #
#  导出到电脑
# --------------------------------------------------------------------------- #
def _save_filter(name: str) -> str:
    """按扩展名拼出「另存为」对话框的文件类型过滤器。"""
    ext = os.path.splitext(name or "")[1].lower()
    table = {
        ".cpp": "C++ 源码 (*.cpp;*.cc;*.cxx)|*.cpp;*.cc;*.cxx|所有文件 (*.*)|*.*",
        ".c": "C 源码 (*.c;*.h)|*.c;*.h|所有文件 (*.*)|*.*",
        ".h": "C/C++ 头文件 (*.h;*.hpp)|*.h;*.hpp|所有文件 (*.*)|*.*",
        ".py": "Python 源码 (*.py)|*.py|所有文件 (*.*)|*.*",
        ".md": "Markdown 文档 (*.md;*.markdown)|*.md;*.markdown|所有文件 (*.*)|*.*",
        ".txt": "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*",
        ".json": "JSON 文件 (*.json)|*.json|所有文件 (*.*)|*.*",
    }
    return table.get(ext, "所有文件 (*.*)|*.*")


def _build_zip(files) -> bytes:
    """把 [{name, content}] 打成一个 zip（字节流）。"""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        used = set()
        for item in files or []:
            if not isinstance(item, dict):
                continue
            name = os.path.basename(str(item.get("name") or "")).strip()
            if not name:
                continue
            safe = name
            counter = 1
            while safe.lower() in used:
                stem, ext = os.path.splitext(name)
                safe = "%s(%d)%s" % (stem, counter, ext)
                counter += 1
            used.add(safe.lower())
            archive.writestr(safe, str(item.get("content") or ""))
    return buffer.getvalue()


@app.route("/api/export/file", methods=["POST"])
def api_export_file():
    """把当前文件另存到电脑（弹系统的「另存为」对话框）。"""
    payload = request.get_json(silent=True) or {}
    name = os.path.basename(str(payload.get("name") or "untitled.txt")) or "untitled.txt"
    content = str(payload.get("content") or "")
    path = savedialog.save_file_dialog(name, "另存为 — " + name, _save_filter(name))
    if not path:
        return jsonify({"ok": False, "cancelled": True, "error": "已取消保存。"})
    try:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
    except OSError as exc:
        return jsonify({"ok": False, "error": "写入失败：%s" % exc})
    return jsonify({"ok": True, "path": path})


@app.route("/api/export/workspace", methods=["POST"])
def api_export_workspace():
    """把当前所有文件导出成一个 zip（弹系统的「另存为」对话框）。"""
    payload = request.get_json(silent=True) or {}
    files = payload.get("files") or []
    path = savedialog.save_file_dialog("workspace.zip", "导出工作区", "ZIP 压缩包 (*.zip)|*.zip")
    if not path:
        return jsonify({"ok": False, "cancelled": True, "error": "已取消导出。"})
    if not path.lower().endswith(".zip"):
        path += ".zip"
    try:
        with open(path, "wb") as fh:
            fh.write(_build_zip(files))
    except OSError as exc:
        return jsonify({"ok": False, "error": "导出失败：%s" % exc})
    return jsonify({"ok": True, "path": path, "count": len(files)})


@app.route("/api/export/workspace.zip", methods=["POST"])
def api_export_workspace_zip():
    """不弹对话框，直接把工作区打成 zip 下载（浏览器里用）。"""
    payload = request.get_json(silent=True) or {}
    data = _build_zip(payload.get("files") or [])
    response = Response(data, mimetype="application/zip")
    response.headers["Content-Disposition"] = "attachment; filename*=UTF-8''workspace.zip"
    response.headers["Cache-Control"] = "no-store"
    return response


# --------------------------------------------------------------------------- #
#  routes
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template(
        "index.html",
        checker_choices=[{"value": c, "label": CHECKER_LABELS[c]} for c in CHECKER_CHOICES],
        supported_stds=list(SUPPORTED_STDS),
        warning_flags=[{"key": k, "label": v} for k, v in WARNING_FLAGS.items()],
        demo_docs=_demo_docs(),
    )


@app.route("/api/toolchain")
def api_toolchain():
    cxx = cxx_path()
    return jsonify(
        {
            "ok": bool(cxx),
            "compiler": cxx or "",
            "version": cxx_version() if cxx else "",
            "supported_stds": list(SUPPORTED_STDS),
            "warning_flags": [{"key": k, "label": v} for k, v in WARNING_FLAGS.items()],
            "checker_choices": [{"value": c, "label": CHECKER_LABELS[c]} for c in CHECKER_CHOICES],
            "status_labels": STATUS_LABELS,
        }
    )


@app.route("/api/compile", methods=["POST"])
def api_compile():
    payload = request.get_json(silent=True) or {}
    code = payload.get("code") or ""
    language = languages.get(payload.get("language") or "cpp")
    settings = _settings_from_payload(payload.get("settings"))
    python_path = _python_path(payload)
    directory = _new_workspace("compile")

    if language.id == "python":
        result = _compile_python(code, directory, python_path)
    else:
        result = compile_source(code, directory, settings)

    session = Session(uuid.uuid4().hex, directory)
    session.language = language.id
    session.python_path = python_path
    if result.ok:
        if language.id == "python":
            session.script = result.script_path
        else:
            session.exe = result.exe_path
        session.source_hash = _source_hash(code, settings)
        session.settings = settings.__dict__
    _register_session(session)
    data = result.to_dict()
    data["session_id"] = session.id
    data["command_line"] = " ".join(result.command)
    data["language"] = language.id
    return jsonify(data)


@app.route("/api/version", methods=["GET"])
def api_version():
    """当前版本与构建信息（界面「设置 → 关于」里显示）。"""
    import platform

    return jsonify(
        {
            "ok": True,
            "version": VERSION,
            "build": BUILD,
            "python": platform.python_version(),
            "flask": flask_version,
            "compiler": cxx_path() or "",
            "compiler_version": (cxx_version() or "").split("\n")[0],
            "frozen": bool(getattr(sys, "frozen", False)),
        }
    )


@app.route("/api/licenses", methods=["GET"])
def api_licenses():
    """第三方组件的许可清单（界面「设置 → 关于 → 开源许可」里显示）。"""
    data = license_lib.manifest()
    data["ok"] = True
    return jsonify(data)


@app.route("/api/licenses/<path:filename>", methods=["GET"])
def api_license_text(filename):
    """某个许可证文件的全文。"""
    text = license_lib.read_license(filename)
    if text is None:
        return jsonify({"ok": False, "error": "找不到该许可证文件"}), 404
    return jsonify({"ok": True, "name": filename, "text": text})


@app.route("/api/languages", methods=["GET"])
def api_languages():
    """Supported file types (used by the front-end to pick the editor mode)."""
    return jsonify(
        {
            "ok": True,
            "languages": [
                {
                    "id": lang.id,
                    "name": lang.name,
                    "extensions": list(lang.extensions),
                    "cm_mode": lang.cm_mode,
                    "kind": lang.kind,
                    "runnable": lang.runnable,
                    "editable": lang.editable,
                }
                for lang in languages.LANGUAGES
            ],
            "python_interpreter": interpreter(),
        }
    )


@app.route("/api/run", methods=["POST"])
def api_run():
    """Compile (if needed) and run the program on a single test case."""
    payload = request.get_json(silent=True) or {}
    code = payload.get("code") or ""
    language = languages.get(payload.get("language") or "cpp")
    settings = _settings_from_payload(payload.get("settings"))
    session_id = payload.get("session_id") or ""
    input_data = payload.get("input") or ""
    expected = payload.get("expected")
    checker = payload.get("checker") or "default"
    time_limit = int(payload.get("time_limit") or 1000)
    memory_limit = int(payload.get("memory_limit") or 256)
    output_limit = int(payload.get("output_limit") or 256)

    session = SESSIONS.get(session_id)
    source_hash = _source_hash(code, settings) if code else ""
    is_python = language.id == "python"
    python_path = _python_path(payload)

    stale = (
        not session
        or session.language != language.id
        or (source_hash and session.source_hash != source_hash)
    )
    if is_python:
        stale = stale or not session.script
    else:
        stale = stale or not session.exe

    result = None
    if stale:
        directory = _new_workspace("run")
        result = (
            _compile_python(code, directory, python_path)
            if is_python
            else compile_source(code, directory, settings)
        )
        session = Session(uuid.uuid4().hex, directory)
        session.language = language.id
        session.python_path = python_path
        if result.ok:
            if is_python:
                session.script = result.script_path
            else:
                session.exe = result.exe_path
            session.source_hash = source_hash
            session.settings = settings.__dict__
        _register_session(session)
        if not result.ok:
            return jsonify(
                {
                    "ok": False,
                    "status": "compile_error",
                    "status_label": "编译错误",
                    "compile": result.to_dict(),
                    "session_id": session.id,
                    "language": language.id,
                }
            )

    if is_python:
        run = run_command(
            script_command(session.script, session.python_path),
            input_data=input_data,
            time_limit_ms=time_limit,
            memory_limit_mb=memory_limit,
            output_limit_kb=output_limit,
            work_dir=session.dir,
        )
    else:
        run = run_program(
            session.exe,
            input_data=input_data,
            time_limit_ms=time_limit,
            memory_limit_mb=memory_limit,
            output_limit_kb=output_limit,
            work_dir=session.dir,
        )

    data = run.to_dict()
    data["session_id"] = session.id
    data["ok"] = run.status == STATUS_AC
    data["language"] = language.id
    if expected is not None:
        check = compare(run.stdout, expected, checker)
        data["check"] = check.to_dict()
        if not check.ok:
            data["ok"] = False
            data["status"] = check.status
            data["status_label"] = STATUS_LABELS.get(check.status, check.status)
            data["message"] = check.message
    if result is not None:
        data["compile"] = result.to_dict()
    return jsonify(data)


@app.route("/api/judge", methods=["POST"])
def api_judge():
    """Compile the program and judge it against a whole test set."""
    payload = request.get_json(silent=True) or {}
    code = payload.get("code") or ""
    language = languages.get(payload.get("language") or "cpp")
    is_python = language.id == "python"
    settings = _settings_from_payload(payload.get("settings"))
    python_path = _python_path(payload)
    config_text = payload.get("config") or ""
    checker_code = payload.get("checker_code") or ""
    global_checker = payload.get("checker") or "default"

    # ---- collect the uploaded files --------------------------------- #
    files: Dict[str, bytes] = {}
    for item in payload.get("files") or []:
        name = os.path.basename(str(item.get("name") or ""))
        if not name:
            continue
        raw = item.get("content_b64")
        try:
            data = base64.b64decode(raw) if raw else b""
        except (binascii.Error, ValueError):
            data = str(item.get("content") or "").encode("utf-8", "replace")
        files[name] = data
    uploaded, uploaded_config = _read_uploaded_files()
    for name, data in uploaded:
        files.setdefault(name, data)
    if not config_text and uploaded_config:
        config_text = _decode_bytes(uploaded_config)

    # a zip archive is expanded in place
    for note in _expand_archives(files):
        if note.startswith("解压") and "失败" in note:
            return jsonify({"ok": False, "error": note})

    # ---- 识别上传数据里的 checker.cpp / testlib.h ------------------------ #
    checker_file = _pick_file(files, CHECKER_FILENAMES)
    testlib_file = _pick_file(files, TESTLIB_FILENAMES)

    if not config_text:
        for name, data in files.items():
            if name.lower().endswith((".cfg", ".ini", ".conf")):
                config_text = _decode_bytes(data)
                break

    available = [
        n for n in files
        if not n.lower().endswith((".cfg", ".ini", ".conf"))
        and not _is_checker_filename(n)
        and not _is_testlib_filename(n)
    ]

    # ---- parse the test point configuration -------------------------- #
    warnings: List[str] = []
    config = None
    if config_text.strip():
        try:
            config = parse_config(config_text, available)
        except ConfigError as exc:
            return jsonify({"ok": False, "error": str(exc)})
        warnings.extend(config.warnings)
    else:
        warnings.append("未提供测试点配置文件，已按照文件名自动配对 .in / .out。")

    points = config.test_points if config else []
    if not points:
        pairs = auto_pair_files(available)
        if not pairs:
            return jsonify(
                {
                    "ok": False,
                    "error": "没有找到任何测试数据。请上传 .in / .out 文件以及测试点配置文件。",
                }
            )
        from core.testconfig import GlobalConfig, TestPoint

        g = GlobalConfig()
        for index, (in_name, out_name) in enumerate(pairs, start=1):
            points.append(
                TestPoint(
                    index=index,
                    name=os.path.splitext(in_name)[0],
                    input_file=in_name,
                    output_file=out_name,
                    time_limit=g.time_limit,
                    memory_limit=g.memory_limit,
                    checker=g.checker,
                )
            )

    # ---- compile ------------------------------------------------------ #
    directory = _new_workspace("judge")
    compile_result = (
        _compile_python(code, directory, python_path)
        if is_python
        else compile_source(code, directory, settings)
    )
    session = Session(uuid.uuid4().hex, directory)
    session.language = language.id
    session.python_path = python_path
    if compile_result.ok:
        if is_python:
            session.script = compile_result.script_path
        else:
            session.exe = compile_result.exe_path
        session.source_hash = _source_hash(code, settings)
        session.settings = settings.__dict__
    _register_session(session)

    if not compile_result.ok:
        return jsonify(
            {
                "ok": False,
                "status": "compile_error",
                "status_label": "编译错误",
                "compile": compile_result.to_dict(),
                "command_line": " ".join(compile_result.command),
                "points": [],
                "warnings": warnings,
                "session_id": session.id,
                "language": language.id,
            }
        )

    # ---- custom checker ------------------------------------------------ #
    # 优先使用上传数据里的 checker.cpp，其次使用编辑器里传来的 checker 源码
    checker_source_code = ""
    checker_origin = ""
    checker_label = ""
    if checker_file:
        checker_source_code = _decode_bytes(files[checker_file])
        checker_origin = "upload"
        checker_label = checker_file
    elif checker_code.strip():
        checker_source_code = checker_code
        checker_origin = "editor"
        checker_label = "编辑器中的 checker 源码"

    if checker_file:
        # 放进 zip 的 checker.cpp 自动生效，所有测试点改用自定义 checker
        for point in points:
            point.checker = "custom"
        global_checker = "custom"
        warnings.append("已在上传数据中检测到 %s，所有测试点改用自定义 checker。" % checker_file)
    elif global_checker == "custom" or any(p.checker == "custom" for p in points):
        global_checker = "custom"
        for point in points:
            if point.checker != "custom":
                point.checker = "custom"

    checker_exe = ""
    checker_command = ""
    checker_info = {
        "enabled": False,
        "source": checker_label,
        "origin": checker_origin,
        "testlib": _testlib_info(),
    }

    need_custom = (
        global_checker == "custom"
        or any(p.checker == "custom" for p in points)
    )
    if need_custom:
        if not checker_source_code.strip():
            return jsonify(
                {
                    "ok": False,
                    "error": "选择了自定义 checker，但没有找到 checker 源码。"
                             "请把 checker.cpp 放进 zip 一起上传，"
                             "或者在编辑器里打开一个名为 checker.cpp 的标签页。",
                    "compile": compile_result.to_dict(),
                }
            )
        # 用户自带 testlib.h 时优先使用（放在源文件同目录），否则用内置版本
        if testlib_file:
            with open(os.path.join(directory, "testlib.h"), "wb") as fh:
                fh.write(files[testlib_file])
        checker_source = os.path.join(directory, "checker.cpp")
        with open(checker_source, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(checker_source_code)
        checker_out = os.path.join(directory, "checker.exe")
        cmd = [cxx_path() or "g++", "-std=c++17", "-O2", "-I", INCLUDE_DIR,
               checker_source, "-o", checker_out]
        checker_command = " ".join(cmd)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=180,
            creationflags=winflags.creation_flags(),
            startupinfo=winflags.startup_info(),
        )
        if proc.returncode == 0 and os.path.isfile(checker_out):
            checker_exe = checker_out
            checker_info["enabled"] = True
            checker_info["command_line"] = checker_command
        else:
            message = _decode_bytes(proc.stderr)
            return jsonify(
                {
                    "ok": False,
                    "error": "自定义 checker 编译失败：\n" + message[:4000],
                    "compile": compile_result.to_dict(),
                    "checker": checker_info,
                }
            )

    # ---- run every test point ------------------------------------------ #
    results: List[dict] = []
    for point in points:
        entry = {
            "index": point.index,
            "name": point.name,
            "input_file": point.input_file,
            "output_file": point.output_file,
            "time_limit": point.time_limit,
            "memory_limit": point.memory_limit,
            "checker": point.checker,
            "status": STATUS_JUDGING,
            "status_label": STATUS_LABELS[STATUS_JUDGING],
            "time_ms": 0,
            "memory_kb": 0,
            "exit_code": None,
            "message": "",
            "output": "",
            "expected": "",
            "diff": "",
        }
        results.append(entry)

        input_data = files.get(point.input_file)
        if input_data is None:
            entry["status"] = STATUS_UNKNOWN
            entry["status_label"] = STATUS_LABELS[STATUS_UNKNOWN]
            entry["message"] = "缺少输入文件 %s" % point.input_file
            continue

        expected_bytes = files.get(point.output_file) if point.output_file else None
        expected_text = _decode_bytes(expected_bytes) if expected_bytes is not None else None

        if is_python:
            run = run_command(
                script_command(session.script, session.python_path),
                input_data=_decode_bytes(input_data),
                time_limit_ms=point.time_limit,
                memory_limit_mb=point.memory_limit,
                output_limit_kb=(config.global_config.output_limit if config else 256),
                work_dir=session.dir,
            )
        else:
            run = run_program(
                session.exe,
                input_data=_decode_bytes(input_data),
                time_limit_ms=point.time_limit,
                memory_limit_mb=point.memory_limit,
                output_limit_kb=(config.global_config.output_limit if config else 256),
                work_dir=session.dir,
            )
        entry["time_ms"] = run.time_ms
        entry["memory_kb"] = run.memory_kb
        entry["commit_kb"] = run.commit_kb
        entry["exit_code"] = run.exit_code
        entry["output"] = run.stdout
        entry["stderr"] = run.stderr
        entry["expected"] = expected_text or ""

        if run.status != STATUS_AC:
            entry["status"] = run.status
            entry["status_label"] = STATUS_LABELS.get(run.status, run.status)
            entry["message"] = run.message
            continue

        if point.checker == "custom" and checker_exe:
            verdict = _run_custom_checker(
                checker_exe, session.dir, input_data, run.stdout.encode("utf-8"),
                expected_bytes or b"",
            )
            entry.update(verdict)
            continue

        check = compare(run.stdout, expected_text, point.checker)
        if check.ok:
            entry["status"] = STATUS_AC
            entry["status_label"] = STATUS_LABELS[STATUS_AC]
            entry["message"] = check.message or "答案正确"
        else:
            entry["status"] = check.status
            entry["status_label"] = STATUS_LABELS.get(check.status, check.status)
            entry["message"] = check.message
            entry["diff"] = check.diff or ""
            if check.first_mismatch:
                entry["first_mismatch"] = check.first_mismatch

    summary = _summarise(results)
    return jsonify(
        {
            "ok": summary.get("accept", 0) == summary.get("total", 0) and summary.get("total", 0) > 0,
            "status": "done",
            "compile": compile_result.to_dict(),
            "command_line": " ".join(compile_result.command),
            "points": results,
            "summary": summary,
            "warnings": warnings,
            "checker": checker_info,
            "language": language.id,
            "session_id": session.id,
        }
    )


def _run_custom_checker(checker_exe: str, work_dir: str, input_data: bytes,
                        output_data: bytes, answer_data: bytes) -> dict:
    """Run a user supplied checker and translate its exit code into a verdict."""
    in_path = os.path.join(work_dir, "checker_input.in")
    out_path = os.path.join(work_dir, "checker_output.out")
    ans_path = os.path.join(work_dir, "checker_answer.out")
    for path, data in ((in_path, input_data), (out_path, output_data), (ans_path, answer_data)):
        with open(path, "wb") as fh:
            fh.write(data)
    try:
        proc = subprocess.run(
            [checker_exe, in_path, out_path, ans_path],
            capture_output=True,
            timeout=30,
            # checker 不需要控制台：不给分配就不会闪黑色窗口
            creationflags=winflags.creation_flags(no_window=True),
            startupinfo=winflags.startup_info(),
            cwd=work_dir,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": STATUS_UNKNOWN,
            "status_label": STATUS_LABELS[STATUS_UNKNOWN],
            "message": "自定义 checker 超时",
        }
    # testlib 的 quitf 把说明文字写到 stdout，程序自己可能写到 stderr，
    # 两个流都收下来，这样评测信息才完整。
    stdout_text = _decode_bytes(proc.stdout).strip()
    stderr_text = _decode_bytes(proc.stderr).strip()
    parts = [part for part in (stdout_text, stderr_text) if part]
    message = "\n".join(parts)
    status = CUSTOM_CHECKER_CODES.get(proc.returncode, STATUS_UNKNOWN)
    return {
        "status": status,
        "status_label": STATUS_LABELS.get(status, status),
        "message": message or STATUS_LABELS.get(status, status),
        "checker_exit_code": proc.returncode,
    }


def _summarise(results: List[dict]) -> dict:
    summary = {"total": len(results), "accept": 0, "failed": 0}
    for entry in results:
        if entry.get("status") == STATUS_AC:
            summary["accept"] += 1
        else:
            summary["failed"] += 1
    return summary


@app.route("/api/format", methods=["POST"])
def api_format():
    payload = request.get_json(silent=True) or {}
    code = payload.get("code") or ""
    options_payload = payload.get("options") or {}
    options = FormatOptions(
        indent_size=int(options_payload.get("indent_size") or 4),
        use_tabs=bool(options_payload.get("use_tabs")),
        brace_style=str(options_payload.get("brace_style") or "allman"),
        space_around_operators=bool(options_payload.get("space_around_operators", True)),
        align_trailing_comments=bool(options_payload.get("align_trailing_comments", True)),
        max_blank_lines=int(options_payload.get("max_blank_lines", 1)),
        keep_blank_lines=bool(options_payload.get("keep_blank_lines", True)),
        space_after_comma=bool(options_payload.get("space_after_comma", True)),
    )
    formatted = format_code(code, options)
    return jsonify({"ok": True, "code": formatted, "changed": formatted != code})


@app.route("/api/insert", methods=["POST"])
def api_insert():
    payload = request.get_json(silent=True) or {}
    code = payload.get("code") or ""
    snippet_id = payload.get("snippet_id") or ""
    position = payload.get("position")
    snippet = snippet_lib.get_snippet(snippet_id)
    if snippet is None:
        return jsonify({"ok": False, "error": "找不到代码片段 %s" % snippet_id})
    result = snippet_lib.insert_snippet(code, snippet, position)
    return jsonify({"ok": True, "code": result, "snippet": snippet.to_dict()})


@app.route("/api/snippets", methods=["GET"])
def api_snippets_list():
    return jsonify({"ok": True, "snippets": [s.to_dict() for s in snippet_lib.all_snippets()],
                    "positions": snippet_lib.POSITION_LABELS})


@app.route("/api/snippets", methods=["POST"])
def api_snippets_save():
    payload = request.get_json(silent=True) or {}
    snippet_id = str(payload.get("id") or "user-%s" % uuid.uuid4().hex[:8])
    snippet = snippet_lib.Snippet(
        id=snippet_id,
        name=str(payload.get("name") or "未命名片段"),
        description=str(payload.get("description") or ""),
        code=str(payload.get("code") or ""),
        position=payload.get("position") if payload.get("position") in snippet_lib.POSITIONS else "top",
        builtin=False,
    )
    snippet_lib.save_user_snippet(snippet)
    return jsonify({"ok": True, "snippet": snippet.to_dict()})


@app.route("/api/snippets/<snippet_id>", methods=["DELETE"])
def api_snippets_delete(snippet_id: str):
    ok = snippet_lib.delete_user_snippet(snippet_id)
    return jsonify({"ok": ok})


@app.route("/api/config/preview", methods=["POST"])
def api_config_preview():
    payload = request.get_json(silent=True) or {}
    config_text = payload.get("config") or ""
    names = [str(n) for n in (payload.get("files") or [])]
    try:
        config = parse_config(config_text, names)
    except ConfigError as exc:
        return jsonify({"ok": False, "error": str(exc)})
    return jsonify({"ok": True, "config": config.to_dict()})


@app.route("/api/upload-scan", methods=["POST"])
def api_upload_scan():
    """Scan uploaded files (zip archives included) for a checker and testlib.

    The front-end calls this right after the user picks files so it can tell
    them *before* the judge run that a ``checker.cpp`` was found.
    """
    payload = request.get_json(silent=True) or {}
    files: Dict[str, bytes] = {}
    for item in payload.get("files") or []:
        name = os.path.basename(str(item.get("name") or ""))
        if not name:
            continue
        raw = item.get("content_b64")
        try:
            data = base64.b64decode(raw) if raw else b""
        except (binascii.Error, ValueError):
            data = str(item.get("content") or "").encode("utf-8", "replace")
        files[name] = data

    notes = _expand_archives(files)
    checker_file = _pick_file(files, CHECKER_FILENAMES)
    testlib_file = _pick_file(files, TESTLIB_FILENAMES)

    config_text = ""
    for name, data in files.items():
        if name.lower().endswith((".cfg", ".ini", ".conf")):
            config_text = _decode_bytes(data)
            break

    data_files = [
        n for n in files
        if not n.lower().endswith((".cfg", ".ini", ".conf"))
        and not _is_checker_filename(n)
        and not _is_testlib_filename(n)
    ]
    pairs = auto_pair_files(data_files)

    return jsonify(
        {
            "ok": True,
            "entries": sorted(files.keys()),
            "notes": notes,
            "checker": checker_file,
            "testlib": testlib_file,
            "config": config_text,
            "data_files": sorted(data_files),
            "pairs": len(pairs),
            "testlib_info": _testlib_info(),
        }
    )


@app.route("/api/testlib")
def api_testlib():
    """Metadata (version, size) plus the ready-to-use checker template."""
    info = _testlib_info()
    info["ok"] = True
    return jsonify(info)


@app.route("/api/testlib-source")
def api_testlib_source():
    """The bundled testlib.h, as a download or as JSON for the in-app viewer."""
    if not os.path.isfile(TESTLIB_PATH):
        return jsonify({"ok": False, "error": "内置 testlib.h 不存在"}), 404
    with open(TESTLIB_PATH, "rb") as fh:
        text = _decode_bytes(fh.read())
    if (request.args.get("mode") or "text").lower() == "json":
        return jsonify({"ok": True, "source": text})
    return Response(
        text,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="testlib.h"'},
    )


@app.route("/api/demo-tests", methods=["GET"])
def api_demo_tests():
    """The bundled demo test set (4 .in/.out pairs + a config file)."""
    directory = os.path.join(APP_DIR, "samples", "demo")
    files: List[dict] = []
    config_text = ""
    if os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                data = fh.read()
            if name.lower().endswith(".cfg"):
                config_text = _decode_bytes(data)
            files.append({
                "name": name,
                "content_b64": base64.b64encode(data).decode("ascii"),
                "size": len(data),
            })
    return jsonify({"ok": True, "files": files, "config": config_text})


@app.route("/api/demo-checker-archive", methods=["GET"])
def api_demo_checker_archive():
    """A demo test archive that carries its own ``checker.cpp``.

    The answer files inside store the expected numbers with leading zeros,
    so a plain text comparison would fail while the bundled numeric
    checker accepts them -- which makes the effect of the custom checker
    visible in the result list.
    """
    path = os.path.join(APP_DIR, "samples", "demo-checker", "demo-with-checker.zip")
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "示例测试包不存在"})
    with open(path, "rb") as fh:
        data = fh.read()
    return jsonify(
        {
            "ok": True,
            "name": "demo-with-checker.zip",
            "content_b64": base64.b64encode(data).decode("ascii"),
            "size": len(data),
        }
    )


def _demo_docs() -> List[dict]:
    """内置示例文档列表（Python / Markdown / PDF）。"""
    directory = os.path.join(APP_DIR, "samples", "demo-docs")
    result: List[dict] = []
    if not os.path.isdir(directory):
        return result
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        language = languages.detect(name)
        size = os.path.getsize(path)
        result.append(
            {
                "name": name,
                "size": size,
                "size_text": "%.1f KB" % (size / 1024.0),
                "lang": language.id,
                "lang_name": language.name,
            }
        )
    return result


@app.route("/api/demo-docs", methods=["GET"])
def api_demo_docs():
    """内置的示例文档：Python 脚本、Markdown（含 LaTeX）、PDF。

    用来快速体验不同文件类型在 IDE 里的表现。
    """
    result = []
    for item in _demo_docs():
        path = os.path.join(APP_DIR, "samples", "demo-docs", item["name"])
        with open(path, "rb") as fh:
            data = fh.read()
        entry = dict(item)
        entry["content_b64"] = base64.b64encode(data).decode("ascii")
        result.append(entry)
    return jsonify({"ok": True, "docs": result})


@app.route("/api/demo-doc/<name>", methods=["GET"])
def api_demo_doc(name: str):
    """取某一个示例文档的内容。"""
    safe = os.path.basename(name)
    path = os.path.join(APP_DIR, "samples", "demo-docs", safe)
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "示例文档不存在"}), 404
    with open(path, "rb") as fh:
        data = fh.read()
    return jsonify(
        {
            "ok": True,
            "name": safe,
            "content_b64": base64.b64encode(data).decode("ascii"),
            "size": len(data),
        }
    )


@app.route("/api/samples", methods=["GET"])
def api_samples():
    """The built-in sample test data."""
    directory = os.path.join(APP_DIR, "samples")
    result = []
    if os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".in"):
                continue
            base = os.path.splitext(name)[0]
            out_path = os.path.join(directory, base + ".out")
            with open(os.path.join(directory, name), encoding="utf-8") as fh:
                data_in = fh.read()
            data_out = ""
            if os.path.isfile(out_path):
                with open(out_path, encoding="utf-8") as fh:
                    data_out = fh.read()
            result.append({"name": base, "input": data_in, "expected": data_out})
    return jsonify({"ok": True, "samples": result})


@app.after_request
def _disable_static_cache(response):
    """静态资源与首页一律不走缓存，保证改完刷新就能看到效果。"""
    if request.path.startswith("/static/") or request.path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.errorhandler(413)
def too_large(_error):  # pragma: no cover - defensive
    return jsonify({"ok": False, "error": "上传的数据过大（上限 256 MB）。"}), 413


if __name__ == "__main__":
    port = int(os.environ.get("CPIDE_PORT", "5000"))
    print("CP-IDE 已启动： http://127.0.0.1:%d/" % port)
    print("编译器： %s" % (cxx_path() or "未找到"))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
