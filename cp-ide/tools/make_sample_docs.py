"""生成示例文件：Python 脚本、Markdown 文档（洛谷语法全集）、PDF 文档。

用法::

    python tools/make_sample_docs.py
"""

import io
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(APP_DIR, "samples", "demo-docs")

HELLO_PY = '''"""CP-IDE 里运行 Python 的示例。

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
'''

DEMO_MD = r"""# 洛谷 Markdown 格式手册 · 完整演示

这份文档演示了 CP-IDE 预览模式支持的 **全部** Markdown 语法（CommonMark + GFM + 洛谷扩展）。

## 段落和换行

第一段话，第二行用两个空格结尾
或者用反斜杠结尾也可以换行。

这是新的一段。

## 标题

### 三级标题

#### 四级标题

##### 五级标题

###### 六级标题

## 强调

*单星号斜体*、_单下划线斜体_、**双星号加粗**、__双下划线加粗__、~~删除线~~。

## 代码块

```cpp
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int n;
    cin >> n;
    long long sum = 0;
    for (int i = 0; i < n; ++i) {
        long long x;
        cin >> x;
        sum += x;
    }
    cout << sum << '\n';
    return 0;
}
```

```python
import sys

def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    print(sum(int(x) for x in data[1:1 + n]))

main()
```

### 行号与语法高亮

在围栏后面写 `line-numbers`，这个代码块就会带上行号，并按语言自动语法高亮：

```cpp line-numbers
#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    int a, b;
    cin >> a >> b;          // 读入两个整数
    cout << a + b << endl;  // 输出它们的和
    return 0;
}
```

Python 一样支持：

```python line-numbers
import sys

def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    print(sum(int(x) for x in data[1:1 + n]))

if __name__ == "__main__":
    main()
```

不想用行号时，只写语言名即可（例如用三个反引号后面跟 cpp）；不写语言则按纯文本显示。

行内代码：`std::sort`。

## 区块引用

> 这是引用块。
>
> 引用块里也可以用 **粗体** 和 `行内代码`。
>
> #### 引用块内使用 3 级标题语法

## 列表

- 无序列表第一项
- 无序列表第二项
  - 嵌套的子项

1. 有序列表第一项
2. 有序列表第二项
3. 有序列表第三项

- [x] 已完成的任务
- [ ] 未完成的任务
- [ ] 另一个未完成的任务

## 链接与图片

行内链接：[洛谷官网](https://www.luogu.com.cn/)、[KaTeX 文档](https://katex.org/docs/supported.html)。

引用式链接：[CommonMark][commonmark]

[commonmark]: https://spec.commonmark.org/

自动链接：https://www.luogu.com.cn/ 会自动变成链接。

![一个占位图片](https://cdn.luogu.com.cn/upload/usericon/1.png)

## 分隔线

---

## 反斜杠

\*这样不会变成斜体\*。

## 表格

| 标题 1 | 标题 2 | 标题 3 |
| :- | :-: | -: |
| 左对齐 | 居中 | 右对齐 |
| 内容 | 内容 | 内容 |

### 表格合并

`^` 向上合并单元格，`<` 向左合并单元格。

| 标题 1 | 标题 2 | 标题 3    | 标题 4 |
| :-: | :-: | :-: | :-: |
| 1 | $\le 10$ | $\le 10$ | 无 |
| 2 | ^ | ^ | 无 |
| 3 | ^ | ^ | 无 |
| 4 | $\le 3\times 10^5$ | ^ | 无 |
| 5 | ^ | ^ | 无 |
| 9 | ^ | 跨列合并 1 | < |
| 10 | 跨列合并 2 | < | 无 |

### 更像 Tuack 的表格

::cute-table{tuack}

| 测试点编号 | $n, m \leq$ | $k \leq$ | 特殊性质 |
| :-: | :-: | :-: | :-: |
| $1, 2$ | $6$ | $6$ | C |
| $3 \sim 5$ | $10^3$ | $10^3$ | ^ |
| $6 \sim 8$ | $5 \times 10^4$ | $10^2$ | 无 |
| $9, 10$ | $10^5$ | $10^5$ | AB |

## 居中与居右排版

:::align{center}
这段文字居中显示。

**居中的粗体**
:::

:::align{right}
这段文字居右显示。
:::

## 引言

:::epigraph[——otto]
大家好啊，我是说的道理，今天来点大家想看的东西。
:::

## 折叠框

::::info[我是提示框]
这里是提示框的内容，可以折叠。

:::warning[嵌套的警告]
警告框也能嵌套在提示框里。
:::
::::

::::success[$$\displaystyle\sum_{i = 1}^n \sum_{j = 1}^n \gcd(i, j)$$]
数学公式也是可以出现在标题上的。
::::

::::warning[警告]
这是一个警告框。
::::

::::error[错误]
这是一个错误框。
::::

## LaTeX 公式

行内公式：质数个数是 $\pi(x) \approx \frac{x}{\ln x}$。

块级公式：

$$
\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}
$$

矩阵与分段函数：

$$
\begin{pmatrix}
a & b \\
c & d
\end{pmatrix}
\cdot
\begin{pmatrix} x \\ y \end{pmatrix}
=
\begin{pmatrix} ax + by \\ cx + dy \end{pmatrix}
$$

$$
f(x) = \begin{cases}
x^2, & x \ge 0 \\
-x, & x < 0
\end{cases}
$$

常用命令：$\sum_{i=1}^{n} i$、$\prod_{i=1}^{n} i$、$\lim_{n \to \infty} \left(1 + \frac{1}{n}\right)^n$、
$\binom{n}{k}$、$\sqrt[3]{x}$、$\vec{v}$、$\alpha \cdot \beta$、$\mathbb{R}$。

## Bilibili 视频

![](https://www.bilibili.com/video/BV1GJ411x7h7)
"""


def make_pdf(path: str, pages) -> None:
    """生成一个最小可用的 PDF（纯 ASCII 文本页）。"""
    objects = []

    def add(body: str) -> int:
        objects.append(body)
        return len(objects)

    font_id = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    content_ids = []
    page_ids = []

    for lines in pages:
        text_ops = ["BT", "/F1 16 Tf", "72 760 Td", "18 TL"]
        for line in lines:
            safe = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            text_ops.append("(%s) Tj" % safe)
            text_ops.append("T*")
        text_ops.append("ET")
        stream = "\n".join(text_ops).encode("latin-1", "replace")
        content_ids.append(add(
            "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream.decode("latin-1"))
        ))

    for content_id in content_ids:
        page_ids.append(add(
            "<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (len(objects) + len(content_ids) + 1, font_id, content_id)
        ))

    real_pages_id = add(
        "<< /Type /Pages /Kids [%s] /Count %d >>"
        % (" ".join("%d 0 R" % pid for pid in page_ids), len(page_ids))
    )
    catalog_id = add("<< /Type /Catalog /Pages %d 0 R >>" % real_pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (index, body)).encode("latin-1", "replace")

    xref_pos = len(out)
    out += ("xref\n0 %d\n" % (len(objects) + 1)).encode("ascii")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += ("%010d 00000 n \n" % offset).encode("ascii")
    out += ("trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objects) + 1, catalog_id, xref_pos)).encode("ascii")

    with open(path, "wb") as fh:
        fh.write(bytes(out))


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    with io.open(os.path.join(OUT_DIR, "hello.py"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(HELLO_PY)
    with io.open(os.path.join(OUT_DIR, "demo.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(DEMO_MD)

    make_pdf(
        os.path.join(OUT_DIR, "sample.pdf"),
        [
            [
                "CP-IDE - Sample PDF Document",
                "",
                "This PDF is generated by tools/make_sample_docs.py",
                "so that the built-in PDF reader can be tried out.",
                "",
                "Page 1 / 2",
            ],
            [
                "Second Page",
                "",
                "Use the toolbar above the page to:",
                "    - turn the page",
                "    - zoom in / out",
                "    - open the file with the system viewer",
            ],
        ],
    )

    for name in sorted(os.listdir(OUT_DIR)):
        print("  %-12s %8d B" % (name, os.path.getsize(os.path.join(OUT_DIR, name))))
    print("完成：%s" % OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
