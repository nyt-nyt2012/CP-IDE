"""End to end test of the CP-IDE backend (uses the Flask test client)."""

import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(APP_DIR, "samples", "demo")

GOOD_CODE = """#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    long long sum = 0;
    for (int i = 0; i < n; i++) {
        long long x;
        cin >> x;
        sum += x;
    }
    cout << sum << "\\n";
    return 0;
}
"""

WRONG_CODE = GOOD_CODE.replace('cout << sum', 'cout << sum + 1')

BROKEN_CODE = """#include <bits/stdc++.h>
int main() {
    undefined_function();
    return 0
}
"""

TLE_CODE = """#include <bits/stdc++.h>
int main() {
    while (true) {}
    return 0;
}
"""

TLE_PY_CODE = """while True:
    pass
"""

MEM_CODE = """#include <bits/stdc++.h>
#include <vector>
int main() {
    std::vector<char> v;
    while (true) { v.resize(v.size() + (1 << 20), 1); }
    return 0;
}
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


def blocked_by_security_software(result):
    """判断这次运行是不是被杀毒软件拦掉了（而不是代码/逻辑有问题）。"""
    message = str(result.get("message") or "")
    markers = ("杀毒软件", "安全软件", "拒绝访问", "不见了", "隔离")
    return any(marker in message for marker in markers)


def demo_files():
    files = []
    for name in sorted(os.listdir(DEMO)):
        if name.endswith(".cfg"):
            continue
        with open(os.path.join(DEMO, name), "rb") as fh:
            data = fh.read()
        files.append({"name": name, "content_b64": base64.b64encode(data).decode("ascii")})
    return files


def main():
    settings = {"std": "c++14", "warnings": ["wall"], "opt": "-O2"}

    # ---------------------------------------------------------------- toolchain
    info = app.test_client().get("/api/toolchain").get_json()
    check("toolchain detected", info.get("ok") is True, str(info)[:200])
    check("toolchain version", "g++" in (info.get("version") or ""), info.get("version"))

    # ---------------------------------------------------------------- compile
    result = post("/api/compile", {"code": GOOD_CODE, "settings": settings})
    check("compile ok", result.get("ok") is True, json.dumps(result)[:400])
    check("compile has session", bool(result.get("session_id")))
    check("compile time recorded", result.get("duration_ms", 0) >= 0)

    result = post("/api/compile", {"code": BROKEN_CODE, "settings": settings})
    check("compile detects error", result.get("ok") is False)
    check("compile parses diagnostics", result.get("errors", 0) >= 1, json.dumps(result)[:300])
    lines = [d.get("line") for d in result.get("diagnostics", []) if d.get("line")]
    check("diagnostic has line number", bool(lines), str(result.get("diagnostics"))[:300])

    # ---------------------------------------------------------------- run
    result = post("/api/run", {
        "code": GOOD_CODE, "input": "3\n1 2 3\n", "expected": "6\n",
        "settings": settings, "time_limit": 2000, "memory_limit": 256,
    })
    check("run accepts correct answer", result.get("status") == "accept", json.dumps(result)[:300])
    check("run measures time", result.get("time_ms", -1) >= 0)
    check("run measures memory", result.get("memory_kb", -1) >= 0)

    result = post("/api/run", {
        "code": WRONG_CODE, "input": "3\n1 2 3\n", "expected": "6\n",
        "settings": settings, "time_limit": 2000, "memory_limit": 256,
    })
    check("run detects wrong answer", result.get("status") == "wrong_answer",
          json.dumps(result)[:300])

    # 超时判定：优先用 Python 脚本验证（解释器不会被杀毒软件误伤），
    # 再用 C++ 版本验证一次。有些机器上的安全软件会把「刚编译出来、死循环」
    # 的可执行文件直接隔离掉，这时只提示跳过，不算失败。
    result = post("/api/run", {
        "code": TLE_PY_CODE, "language": "python", "input": "", "expected": "",
        "settings": settings, "time_limit": 800, "memory_limit": 256,
    })
    check("run detects TLE (python)", result.get("status") == "time_limit_exceeded",
          json.dumps(result)[:300])

    result = post("/api/run", {
        "code": TLE_CODE, "input": "", "expected": "",
        "settings": settings, "time_limit": 800, "memory_limit": 256,
    })
    if result.get("status") == "time_limit_exceeded":
        check("run detects TLE (c++)", True)
    elif blocked_by_security_software(result):
        print("skip run detects TLE (c++) —— 刚编译出来的 exe 被安全软件拦截，"
              "本机无法验证（见 %s）" % (result.get("message") or "").splitlines()[0])
    else:
        check("run detects TLE (c++)", False, json.dumps(result)[:300])

    # ---------------------------------------------------------------- judge
    with open(os.path.join(DEMO, "testpoints.cfg"), encoding="utf-8") as fh:
        config_text = fh.read()

    result = post("/api/judge", {
        "code": GOOD_CODE, "settings": settings,
        "config": config_text, "files": demo_files(),
    })
    check("judge compiles", (result.get("compile") or {}).get("ok") is True,
          json.dumps(result)[:400])
    points = result.get("points") or []
    check("judge finds 4 points", len(points) == 4, str(len(points)))
    check("judge all accept", all(p["status"] == "accept" for p in points),
          json.dumps([p["status"] for p in points]))
    check("judge reports time", all(p["time_ms"] >= 0 for p in points))
    check("judge reports memory", all(p["memory_kb"] >= 0 for p in points))
    check("judge summary", (result.get("summary") or {}).get("accept") == 4,
          json.dumps(result.get("summary")))

    result = post("/api/judge", {
        "code": WRONG_CODE, "settings": settings,
        "config": config_text, "files": demo_files(),
    })
    points = result.get("points") or []
    check("judge detects WA", all(p["status"] == "wrong_answer" for p in points),
          json.dumps([p["status"] for p in points]))
    check("judge provides diff", any(p.get("diff") for p in points))

    # 配置文件解析：通配符
    result = post("/api/judge", {
        "code": GOOD_CODE, "settings": settings,
        "config": "[tests]\n1-4 | 1.in | 1.out\n", "files": demo_files(),
    })
    check("wildcard expands", len(result.get("points") or []) == 1,
          str(len(result.get("points") or [])))

    # 自动配对（不提供配置文件）
    result = post("/api/judge", {
        "code": GOOD_CODE, "settings": settings, "config": "", "files": demo_files(),
    })
    check("auto pairing finds 4 points", len(result.get("points") or []) == 4,
          str(len(result.get("points") or [])))

    # 配置预览
    result = post("/api/config/preview", {
        "config": config_text,
        "files": ["1.in", "1.out", "2.in", "2.out"],
    })
    check("config preview", result.get("ok") and len(result["config"]["tests"]) == 4,
          json.dumps(result)[:200])

    # ---------------------------------------------------------------- format
    result = post("/api/format", {"code": "int  main(){int a=1;return a;}"})
    check("format runs", result.get("ok") is True)
    check("format output", result["code"].startswith("int main()"), repr(result["code"]))

    # ---------------------------------------------------------------- insert
    result = post("/api/insert", {
        "code": "#include <bits/stdc++.h>\nint main(){}\n",
        "snippet_id": "using", "position": "top",
    })
    check("insert snippet", "using namespace std;" in result.get("code", ""),
          result.get("code", ""))

    # ---------------------------------------------------------------- snippets
    result = post("/api/snippets", {
        "id": "user-test", "name": "测试片段", "code": "int x = 1;",
    })
    check("save snippet", result.get("ok") is True)
    listing = app.test_client().get("/api/snippets").get_json()
    check("snippet listed", any(s["id"] == "user-test" for s in listing["snippets"]))
    deleted = app.test_client().delete("/api/snippets/user-test").get_json()
    check("delete snippet", deleted.get("ok") is True)

    # ---------------------------------------------------------------- samples
    result = app.test_client().get("/api/samples").get_json()
    check("built-in samples", len(result.get("samples") or []) >= 1, str(result)[:200])

    # ---------------------------------------------------------------- licenses
    result = app.test_client().get("/api/licenses").get_json()
    check("licenses ok", result.get("ok") is True, str(result)[:200])
    check("licenses list not empty", len(result.get("components") or []) >= 5, str(result)[:200])
    check("licenses has self entry", (result.get("self") or {}).get("license") == "MIT", str(result.get("self"))[:200])
    check("licenses has external", len(result.get("external") or []) >= 1, str(result)[:200])
    names = [item.get("name") for item in result.get("components") or []]
    check("licenses lists CodeMirror", "CodeMirror" in names, str(names))
    check("licenses lists PDF.js", "PDF.js" in names, str(names))
    text = app.test_client().get("/api/licenses/codemirror-LICENSE.txt").get_json()
    check("license text served", text.get("ok") is True and "MIT" in (text.get("text") or ""), str(text)[:200])
    missing = app.test_client().get("/api/licenses/does-not-exist.txt")
    check("missing license 404", missing.status_code == 404, str(missing.status_code))
    traversal = app.test_client().get("/api/licenses/..%2F..%2Fapp.py")
    check("license path traversal blocked", traversal.status_code == 404, str(traversal.status_code))

    print()
    if failures:
        print("FAILED: %d" % len(failures))
        for name in failures:
            print("  -", name)
        return 1
    print("ALL API TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
