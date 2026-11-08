"""工作区持久化。

把「上次在做什么」存到 ``%LOCALAPPDATA%\\CP-IDE\\workspace.json``：

* 打开的标签页（含还没保存的代码内容）
* 上一次的编译信息 / 评测结果
* 界面偏好（主题、代码字体、字号、C++ 标准与警告选项、Python 解释器路径……）

之所以放在用户目录而不是程序目录，是因为打包成 exe 之后程序目录会被覆盖，
放用户目录才能保证「关掉 IDE 再打开，代码还在」。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from typing import Any, Dict, Optional

_LOCK = threading.Lock()

#: 工作区结构版本号，将来结构变化时可以据此迁移
WORKSPACE_VERSION = 1


def workspace_dir() -> str:
    """工作区目录（不存在就创建）。"""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "CP-IDE")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def workspace_path() -> str:
    return os.path.join(workspace_dir(), "workspace.json")


def load_workspace() -> Dict[str, Any]:
    """读取上次保存的工作区；文件不存在或损坏时返回空字典。"""
    try:
        with open(workspace_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_workspace(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """原子写入工作区文件，并保留上一份作为备份。"""
    if not isinstance(data, dict):
        data = {}
    payload = dict(data)
    payload.setdefault("version", WORKSPACE_VERSION)
    payload["savedAt"] = time.time()

    directory = workspace_dir()
    path = workspace_path()
    with _LOCK:
        fd, tmp = tempfile.mkstemp(prefix="workspace-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            # 旧的留一份备份，万一写坏了还能救回来
            if os.path.isfile(path):
                try:
                    shutil.copyfile(path, path + ".bak")
                except OSError:
                    pass
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    return {"ok": True, "savedAt": payload["savedAt"], "path": path}
