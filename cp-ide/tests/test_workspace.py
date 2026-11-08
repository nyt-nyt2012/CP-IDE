"""工作区持久化 + 导出功能的测试。

覆盖：
* core/workspace.py 的保存 / 读取 / 备份
* /api/workspace 的 GET / POST
* /api/export/file（把对话框打桩，避免真的弹窗）
* /api/export/workspace（导出 zip）
* /api/export/workspace.zip（浏览器下载用）
"""

import io
import json
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from core import savedialog  # noqa: E402
from core import workspace as workspace_lib  # noqa: E402

failures = []


def check(condition, message):
    if condition:
        print("  ok   %s" % message)
    else:
        print("  FAIL %s" % message)
        failures.append(message)


def main() -> int:
    app.config["TESTING"] = True
    client = app.test_client()

    tmpdir = tempfile.mkdtemp(prefix="cpide-ws-")
    original_dir = workspace_lib.workspace_dir
    workspace_lib.workspace_dir = lambda: tmpdir
    try:
        print("工作区文件")
        check(workspace_lib.load_workspace() == {}, "没有工作区文件时返回空字典")

        payload = {
            "version": 1,
            "tabs": [{"id": "tab-1", "name": "main.cpp", "content": "int main(){}", "dirty": True}],
            "activeTabId": "tab-1",
            "settings": {"theme": "light", "mono": "consolas", "fontSize": "14.5"},
        }
        result = workspace_lib.save_workspace(payload)
        check(result.get("ok") is True, "保存返回 ok")
        saved = workspace_lib.load_workspace()
        check(saved["tabs"][0]["content"] == "int main(){}", "内容原样保存")
        check(saved["settings"]["mono"] == "consolas", "界面偏好原样保存")
        check(os.path.isfile(os.path.join(tmpdir, "workspace.json")), "工作区文件已落盘")

        # 再存一次，应该留下 .bak 备份
        workspace_lib.save_workspace({"tabs": [], "settings": {}})
        check(os.path.isfile(os.path.join(tmpdir, "workspace.json.bak")), "保留了一份备份")

        print("/api/workspace")
        response = client.post("/api/workspace", json={"workspace": payload})
        check(response.status_code == 200, "POST /api/workspace 返回 200")
        check(response.get_json()["ok"] is True, "POST 返回 ok")

        response = client.get("/api/workspace")
        data = response.get_json()
        check(data["ok"] is True, "GET 返回 ok")
        check(data["workspace"]["tabs"][0]["name"] == "main.cpp", "GET 能读回标签页")

        print("/api/export/file")
        target = os.path.join(tmpdir, "exported.cpp")
        original_dialog = savedialog.save_file_dialog
        savedialog.save_file_dialog = lambda *args, **kwargs: target
        try:
            response = client.post(
                "/api/export/file",
                json={"name": "main.cpp", "content": "#include <bits/stdc++.h>\nint main(){}\n"},
            )
            body = response.get_json()
            check(body["ok"] is True, "导出成功")
            check(body["path"] == target, "返回保存路径")
            with open(target, "r", encoding="utf-8") as fh:
                check(fh.read().startswith("#include"), "文件内容写对了")

            # 取消对话框
            savedialog.save_file_dialog = lambda *args, **kwargs: ""
            response = client.post("/api/export/file", json={"name": "x.cpp", "content": "y"})
            body = response.get_json()
            check(body.get("cancelled") is True, "取消时返回 cancelled")
            check(body.get("ok") is False, "取消时不算成功")
        finally:
            savedialog.save_file_dialog = original_dialog

        print("/api/export/workspace")
        files = [
            {"name": "main.cpp", "content": "int main(){}"},
            {"name": "a.py", "content": "print(1)"},
        ]
        zip_target = os.path.join(tmpdir, "workspace.zip")
        savedialog.save_file_dialog = lambda *args, **kwargs: zip_target
        try:
            response = client.post("/api/export/workspace", json={"files": files})
            body = response.get_json()
            check(body["ok"] is True, "导出 zip 成功")
            check(body["count"] == 2, "文件数量正确")
            with zipfile.ZipFile(zip_target) as archive:
                names = archive.namelist()
                check("main.cpp" in names and "a.py" in names, "zip 里有各个文件")
        finally:
            savedialog.save_file_dialog = original_dialog

        print("/api/export/workspace.zip")
        response = client.post("/api/export/workspace.zip", json={"files": files})
        check(response.status_code == 200, "下载接口返回 200")
        check(response.mimetype == "application/zip", "MIME 是 zip")
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            check(len(archive.namelist()) == 2, "下载的 zip 里有 2 个文件")

        print("损坏文件不影响启动")
        with open(os.path.join(tmpdir, "workspace.json"), "w", encoding="utf-8") as fh:
            fh.write("{ this is not json")
        check(workspace_lib.load_workspace() == {}, "文件损坏时返回空字典")
    finally:
        workspace_lib.workspace_dir = original_dir
        try:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    print("")
    if failures:
        print("%d WORKSPACE TESTS FAILED" % len(failures))
        return 1
    print("ALL WORKSPACE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
