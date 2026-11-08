"""多语言支持的后端测试：Python 编译 / 运行 / 评测，以及文档资源（PDF 等）。"""

import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PY_OK = """import sys

def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = [int(x) for x in data[1:1 + n]]
    print(sum(nums))

main()
"""

PY_SYNTAX_ERROR = """def broken(:
    print('oops')
"""

PY_RUNTIME_ERROR = """raise ValueError('boom')
"""

failures = []


def check(name, condition, detail=""):
    if condition:
        print("ok   %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        failures.append(name)


def post(path, payload):
    client = app.test_client()
    response = client.post(path, data=json.dumps(payload), content_type="application/json")
    return response.get_json()


def get(path):
    return app.test_client().get(path)


def main():
    # ------------------------------------------------------------- 语言表
    info = get("/api/languages").get_json()
    ids = [lang["id"] for lang in info.get("languages") or []]
    check("languages endpoint", info.get("ok") is True, str(info)[:200])
    check("cpp language present", "cpp" in ids, str(ids))
    check("python language present", "python" in ids, str(ids))
    check("markdown language present", "markdown" in ids, str(ids))
    check("pdf language present", "pdf" in ids, str(ids))
    check("python interpreter reported", bool(info.get("python_interpreter")))

    # -------------------------------------------------------- Python 编译
    result = post("/api/compile", {"code": PY_OK, "language": "python"})
    check("python compile ok", result.get("ok") is True, json.dumps(result)[:400])
    check("python compile reports language", result.get("language") == "python")
    check("python compile no diagnostics", not (result.get("diagnostics") or []),
          str(result.get("diagnostics"))[:200])
    check("python compile has session", bool(result.get("session_id")))

    result = post("/api/compile", {"code": PY_SYNTAX_ERROR, "language": "python"})
    check("python syntax error detected", result.get("ok") is False, json.dumps(result)[:300])
    diags = result.get("diagnostics") or []
    check("python diagnostic has line", bool(diags and diags[0].get("line")), str(diags)[:200])
    check("python diagnostic has message",
          bool(diags and diags[0].get("message")), str(diags)[:200])

    # C++ 编译不受影响
    cpp_code = "#include <bits/stdc++.h>\nint main(){return 0;}\n"
    result = post("/api/compile", {"code": cpp_code, "language": "cpp",
                                    "settings": {"std": "c++14", "opt": "-O2"}})
    check("cpp compile still works", result.get("ok") is True, json.dumps(result)[:300])

    # -------------------------------------------------------- Python 运行
    result = post("/api/run", {
        "code": PY_OK, "language": "python",
        "input": "3\n1 2 3\n", "expected": "6\n",
        "time_limit": 10000, "memory_limit": 256,
    })
    check("python run accepts", result.get("status") == "accept", json.dumps(result)[:400])
    check("python run stdout", (result.get("stdout") or "").strip() == "6",
          repr(result.get("stdout")))
    check("python run measured time", result.get("time_ms", -1) >= 0)
    check("python run measured memory", result.get("memory_kb", -1) >= 0)

    result = post("/api/run", {
        "code": PY_OK, "language": "python",
        "input": "3\n1 2 3\n", "expected": "7\n",
        "time_limit": 10000, "memory_limit": 256,
    })
    check("python run detects WA", result.get("status") == "wrong_answer",
          json.dumps(result)[:300])

    result = post("/api/run", {
        "code": PY_RUNTIME_ERROR, "language": "python",
        "input": "", "expected": "",
        "time_limit": 10000, "memory_limit": 256,
    })
    check("python run detects runtime error",
          result.get("status") in ("runtime_error", "unknown_error"),
          json.dumps(result)[:300])
    check("python stderr captured", "ValueError" in (result.get("stderr") or ""),
          repr(result.get("stderr"))[:200])

    # ------------------------------------------------------- Python 评测
    files = [
        {"name": "1.in", "content_b64": base64.b64encode(b"3\n1 2 3\n").decode()},
        {"name": "1.out", "content_b64": base64.b64encode(b"6\n").decode()},
        {"name": "2.in", "content_b64": base64.b64encode(b"2\n10 20\n").decode()},
        {"name": "2.out", "content_b64": base64.b64encode(b"30\n").decode()},
    ]
    result = post("/api/judge", {
        "code": PY_OK, "language": "python", "config": "", "files": files,
    })
    points = result.get("points") or []
    check("python judge finds 2 points", len(points) == 2, str(len(points)))
    check("python judge accepts", all(p["status"] == "accept" for p in points),
          json.dumps([p.get("status") for p in points]))
    check("python judge reports language", result.get("language") == "python")

    bad_files = [
        {"name": "1.in", "content_b64": base64.b64encode(b"3\n1 2 3\n").decode()},
        {"name": "1.out", "content_b64": base64.b64encode(b"7\n").decode()},
    ]
    result = post("/api/judge", {
        "code": PY_OK, "language": "python", "config": "",
        "files": bad_files,
    })
    points = result.get("points") or []
    check("python judge detects WA", any(p["status"] == "wrong_answer" for p in points),
          json.dumps([p.get("status") for p in points]))

    # 语法错误时评测直接报编译错误
    result = post("/api/judge", {
        "code": PY_SYNTAX_ERROR, "language": "python", "config": "", "files": files,
    })
    check("python judge reports compile error", result.get("status") == "compile_error",
          json.dumps(result)[:200])

    # ------------------------------------------------------------ 文档资源
    payload = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
    result = post("/api/assets", {
        "name": "paper.pdf",
        "content_b64": base64.b64encode(payload).decode(),
    })
    check("asset uploaded", result.get("ok") is True, json.dumps(result)[:200])
    token = result.get("token")
    check("asset has token", bool(token))

    response = get("/api/assets/" + token)
    check("asset served", response.status_code == 200, str(response.status_code))
    check("asset mime type", "application/pdf" in (response.headers.get("Content-Type") or ""),
          response.headers.get("Content-Type"))
    check("asset content matches", response.data == payload, str(response.data[:40]))

    missing = get("/api/assets/deadbeef")
    check("missing asset 404", missing.status_code == 404, str(missing.status_code))

    # ------------------------------------------------------ 前端资源已内置
    vendor = os.path.join(APP_DIR, "static", "vendor")
    for rel in (
        os.path.join("marked", "marked.min.js"),
        os.path.join("katex", "katex.min.js"),
        os.path.join("katex", "katex.min.css"),
        os.path.join("katex", "auto-render.min.js"),
        os.path.join("pdfjs", "pdf.min.js"),
        os.path.join("pdfjs", "pdf.worker.min.js"),
    ):
        check("vendored %s" % rel.replace("\\", "/"), os.path.isfile(os.path.join(vendor, rel)))

    fonts = os.path.join(vendor, "katex", "fonts")
    woff2 = [f for f in os.listdir(fonts)] if os.path.isdir(fonts) else []
    check("katex fonts vendored", len(woff2) >= 10, str(len(woff2)))

    print()
    if failures:
        print("FAILED: %d" % len(failures))
        for name in failures:
            print("  -", name)
        return 1
    print("ALL LANGUAGE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
