"""CP-IDE 里运行 Python 的示例。

按「运行」按钮，会读入标准输入里的数字并求和，
和 C++ 示例程序的行为完全一样，方便对比两种语言的评测流程。
"""

import sys


def main() -> None:
    data = sys.stdin.read().split()
    if not data:
        return
    n = int(data[0])
    nums = [int(x) for x in data[1:1 + n]]
    print(sum(nums))


if __name__ == "__main__":
    main()
