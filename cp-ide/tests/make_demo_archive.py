"""Build a demo test archive that contains a checker.cpp.

The answer files store the expected numbers with leading zeros, so a plain
text comparison would report WA while the numeric checker shipped here
accepts them.  Running the IDE with this archive therefore proves that the
bundled checker really is the one making the decision.

Usage::

    python tests/make_demo_archive.py
"""

import os
import re
import sys
import zipfile

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(APP_DIR, "samples", "demo")
OUT_DIR = os.path.join(APP_DIR, "samples", "demo-checker")
ZIP_PATH = os.path.join(OUT_DIR, "demo-with-checker.zip")

CHECKER = """#include "testlib.h"

#include <cmath>
#include <cstdlib>
#include <string>

using namespace std;

/* 数值比较：允许前导零、小数误差等写法差异 */
static bool numericEqual(const string &a, const string &b) {
    char *endA = 0;
    char *endB = 0;
    double x = strtod(a.c_str(), &endA);
    double y = strtod(b.c_str(), &endB);
    if (endA == a.c_str() || endB == b.c_str()) return false;
    if (*endA != '\\0' || *endB != '\\0') return false;
    double diff = fabs(x - y);
    double scale = max(1.0, max(fabs(x), fabs(y)));
    return diff <= 1e-6 * scale;
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
        if (!numericEqual(got, expected)) {
            quitf(_wa, "token %d mismatch: got '%s', expected '%s'",
                  index, got.c_str(), expected.c_str());
        }
    }

    quitf(_ok, "answer is correct");
}
"""

NUMBER = re.compile(r"^[+-]?\d+$")


def main():
    if not os.path.isdir(DEMO_DIR):
        print("找不到示例测试集目录：%s" % DEMO_DIR)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(os.listdir(DEMO_DIR)):
            path = os.path.join(DEMO_DIR, name)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                raw = fh.read()
            if name.endswith(".out"):
                # 数字补前导零：让普通文本比较判成 WA
                text = raw.decode("utf-8").split()
                padded = []
                for token in text:
                    if NUMBER.match(token):
                        sign = "-" if token.startswith("-") else ""
                        digits = token.lstrip("+-")
                        token = sign + digits.lstrip("0").rjust(8, "0")
                    padded.append(token)
                raw = (" ".join(padded) + "\n").encode("utf-8")
            archive.writestr(name, raw)
        archive.writestr("checker.cpp", CHECKER.encode("utf-8"))

    print("已生成：%s（%d 字节）" % (ZIP_PATH, os.path.getsize(ZIP_PATH)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
