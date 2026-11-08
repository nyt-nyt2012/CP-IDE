"""End to end test of the bundled testlib and the custom checker pipeline.

Covers:

* ``/api/testlib``          – metadata + ready-to-use checker template
* ``/api/testlib-source``   – the bundled ``testlib.h`` itself
* ``/api/upload-scan``      – detecting ``checker.cpp`` inside an uploaded zip
* ``/api/judge``            – a zip containing ``checker.cpp`` is judged with
  that checker (and the built-in testlib is used without uploading it)
"""

import base64
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDE_DIR = os.path.join(APP_DIR, "include")

SETTINGS = {"std": "c++14", "warnings": ["wall"], "opt": "-O2"}

# Prints YES for 1 and NO for 0 – the answer files use a different case on
# purpose, so the default comparison would fail while a case-insensitive
# custom checker accepts.
PROGRAM = """#include <bits/stdc++.h>
using namespace std;
int main() {
    int n;
    cin >> n;
    cout << (n == 1 ? "YES" : "NO") << "\\n";
    return 0;
}
"""

# A testlib based checker: compares tokens case-insensitively.
CHECKER = """#include "testlib.h"

#include <cctype>
#include <string>

using namespace std;

static string lower(string s) {
    for (size_t i = 0; i < s.size(); ++i) {
        s[i] = (char)tolower((unsigned char)s[i]);
    }
    return s;
}

int main(int argc, char *argv[]) {
    registerTestlibCmd(argc, argv);
    int index = 0;
    while (!ans.seekEof() || !ouf.seekEof()) {
        ++index;
        if (ans.seekEof() || ouf.seekEof()) {
            quitf(_wa, "token count mismatch at token %d", index);
        }
        string expected = ans.readWord();
        string got = ouf.readWord();
        if (lower(got) != lower(expected)) {
            quitf(_wa, "token %d mismatch: got '%s', expected '%s'",
                  index, got.c_str(), expected.c_str());
        }
    }
    quitf(_ok, "answer is correct");
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


def get(path):
    return app.test_client().get(path)


def make_zip(entries):
    """Build a zip archive from {name: text} and return it base64 encoded."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def main():
    client = app.test_client()

    # ------------------------------------------------------------- testlib
    check("testlib.h is bundled", os.path.isfile(os.path.join(INCLUDE_DIR, "testlib.h")))

    info = get("/api/testlib").get_json()
    check("testlib endpoint ok", info.get("ok") is True, str(info)[:200])
    check("testlib version detected", info.get("version") == "0.9.45", str(info.get("version")))
    check("testlib has size", info.get("size", 0) > 100000, str(info.get("size")))
    check("testlib template provided", "#include \"testlib.h\"" in (info.get("template") or ""))

    source = get("/api/testlib-source?mode=json").get_json()
    check("testlib source served", (source.get("source") or "").startswith("/*"),
          str(source.get("source"))[:120])
    check("testlib source has VERSION", '#define VERSION "0.9.45"' in (source.get("source") or ""))

    download = get("/api/testlib-source")
    check("testlib download headers",
          "testlib.h" in (download.headers.get("Content-Disposition") or ""),
          download.headers.get("Content-Disposition"))

    # --------------------------------------------------------- upload scan
    zip_b64 = make_zip({
        "1.in": "1\n",
        "1.out": "yes\n",
        "2.in": "0\n",
        "2.out": "no\n",
        "checker.cpp": CHECKER,
    })
    scan = post("/api/upload-scan", {"files": [{"name": "data.zip", "content_b64": zip_b64}]})
    check("scan finds checker", scan.get("checker") == "checker.cpp", str(scan.get("checker")))
    check("scan lists entries", "1.in" in (scan.get("entries") or []), str(scan.get("entries")))
    check("scan counts pairs", scan.get("pairs") == 2, str(scan.get("pairs")))
    check("scan reports testlib version",
          (scan.get("testlib_info") or {}).get("version") == "0.9.45")

    scan_plain = post("/api/upload-scan", {
        "files": [{"name": "checker.cpp", "content_b64": base64.b64encode(CHECKER.encode()).decode()}]
    })
    check("scan finds loose checker", scan_plain.get("checker") == "checker.cpp")

    # --------------------------------------------------------------- judge
    # The zip carries the checker but no testlib.h: the built-in one is used.
    result = post("/api/judge", {
        "code": PROGRAM, "settings": SETTINGS, "config": "", "files": [
            {"name": "data.zip", "content_b64": zip_b64},
        ],
    })
    checker = result.get("checker") or {}
    check("judge enables custom checker", checker.get("enabled") is True, str(checker)[:300])
    check("judge reports checker source", checker.get("source") == "checker.cpp",
          str(checker.get("source")))
    check("judge reports checker origin", checker.get("origin") == "upload",
          str(checker.get("origin")))
    check("judge used built-in testlib",
          (checker.get("testlib") or {}).get("version") == "0.9.45")
    points = result.get("points") or []
    check("judge finds 2 points", len(points) == 2, str(len(points)))
    check("custom checker accepts", all(p["status"] == "accept" for p in points),
          json.dumps([p.get("status") for p in points]))
    check("custom checker message reported",
          any("correct" in (p.get("message") or "") for p in points),
          json.dumps([p.get("message") for p in points]))
    check("judge warns about detected checker",
          any("checker.cpp" in w for w in (result.get("warnings") or [])),
          json.dumps(result.get("warnings")))

    # A checker that always fails must produce WA with its own message.
    bad_checker = CHECKER.replace('lower(got) != lower(expected)',
                                  'lower(got) == lower(expected)')
    bad_zip = make_zip({
        "1.in": "1\n", "1.out": "yes\n",
        "2.in": "0\n", "2.out": "no\n",
        "checker.cpp": bad_checker,
    })
    result = post("/api/judge", {
        "code": PROGRAM, "settings": SETTINGS, "config": "", "files": [
            {"name": "data.zip", "content_b64": bad_zip},
        ],
    })
    points = result.get("points") or []
    check("failing checker reports WA", all(p["status"] == "wrong_answer" for p in points),
          json.dumps([p.get("status") for p in points]))
    check("failing checker message shown",
          any("mismatch" in (p.get("message") or "") for p in points),
          json.dumps([p.get("message") for p in points]))

    # A broken checker must surface the compiler diagnostics.
    broken_zip = make_zip({
        "1.in": "1\n", "1.out": "yes\n",
        "checker.cpp": "int main() { this is not c++ }\n",
    })
    result = post("/api/judge", {
        "code": PROGRAM, "settings": SETTINGS, "config": "", "files": [
            {"name": "data.zip", "content_b64": broken_zip},
        ],
    })
    check("broken checker reports error", result.get("ok") is False, json.dumps(result)[:300])
    check("broken checker explains",
          "checker" in (result.get("error") or "").lower(), str(result.get("error"))[:200])

    # Checker source coming from the editor (no checker.cpp in the upload).
    result = post("/api/judge", {
        "code": PROGRAM, "settings": SETTINGS, "config": "",
        "checker": "custom", "checker_code": CHECKER,
        "files": [
            {"name": "1.in", "content_b64": base64.b64encode(b"1\n").decode()},
            {"name": "1.out", "content_b64": base64.b64encode(b"yes\n").decode()},
        ],
    })
    checker = result.get("checker") or {}
    check("editor checker accepted", checker.get("enabled") is True, str(checker)[:300])
    check("editor checker origin", checker.get("origin") == "editor", str(checker.get("origin")))

    # Asking for a custom checker without any source must give a clear error.
    result = post("/api/judge", {
        "code": PROGRAM, "settings": SETTINGS, "config": "", "checker": "custom",
        "files": [
            {"name": "1.in", "content_b64": base64.b64encode(b"1\n").decode()},
            {"name": "1.out", "content_b64": base64.b64encode(b"yes\n").decode()},
        ],
    })
    check("missing checker source errors", result.get("ok") is False, json.dumps(result)[:200])
    check("missing checker source explains",
          "checker.cpp" in (result.get("error") or ""), str(result.get("error"))[:200])

    print()
    if failures:
        print("FAILED: %d" % len(failures))
        for name in failures:
            print("  -", name)
        return 1
    print("ALL CHECKER TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
