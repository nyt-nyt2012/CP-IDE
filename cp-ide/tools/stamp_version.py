"""把打包时间写进 core/version.py，界面上就能看出当前跑的是哪一版。

用法::

    python tools/stamp_version.py "2026-07-23 23:40 打包版"
"""

import io
import os
import re
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(APP_DIR, "core", "version.py")


def main() -> int:
    stamp = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not stamp:
        import datetime

        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + " 打包版"

    with io.open(TARGET, encoding="utf-8") as fh:
        text = fh.read()

    new_text, count = re.subn(r'^BUILD\s*=.*$', 'BUILD = "%s"' % stamp, text, flags=re.M)
    if not count:
        new_text = text.rstrip("\n") + '\n\nBUILD = "%s"\n' % stamp

    with io.open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_text)

    print("   build stamp: %s" % stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
