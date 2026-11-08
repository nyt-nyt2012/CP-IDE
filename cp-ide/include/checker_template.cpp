/*
 * CP-IDE 内置自定义 checker 模板（基于 testlib）
 * ---------------------------------------------------------------------------
 * 用法一：把本文件改名为 checker.cpp，连同测试数据一起打包成 zip 上传，
 *         IDE 会自动识别并启用它（无需再单独上传 testlib.h）。
 *
 * 用法二：在 IDE 里新建一个名为 checker.cpp 的标签页，把本模板粘进去，
 *         评测时 IDE 会自动使用编辑器中的这份代码。
 *
 * 运行方式：checker <输入文件> <程序输出文件> <标准答案文件>
 *
 * testlib 的约定（务必遵守，否则会被判成 FAIL）：
 *   1. main 的第一行必须调用 registerTestlibCmd(argc, argv)；
 *   2. 程序输出文件由 testlib 的 ouf 打开，答案文件由 ans 打开，
 *      输入文件由 inf 打开；
 *   3. quitf(_ok, ...) 返回 AC，quitf(_wa, ...) 返回 WA，
 *      quitf(_pe, ...) 返回 PE，quitf(_fail, ...) 返回其它错误。
 *      quitf 里的说明文字会显示在评测结果里。
 */
#include "testlib.h"

#include <cctype>
#include <cmath>
#include <cstdlib>
#include <string>

using namespace std;

/* 改成 true 可以按数值比较（自动忽略浮点误差） */
static const bool NUMERIC_COMPARE = false;

/* 数值比较时使用的相对容差 */
static const double EPS = 1e-6;

/* 转成小写，便于做大小写不敏感的比较 */
static string toLower(string s) {
    for (size_t i = 0; i < s.size(); ++i) {
        s[i] = (char)tolower((unsigned char)s[i]);
    }
    return s;
}

/* 两个 token 是否在数值意义上相等 */
static bool numericEqual(const string &a, const string &b) {
    char *endA = 0;
    char *endB = 0;
    double x = strtod(a.c_str(), &endA);
    double y = strtod(b.c_str(), &endB);
    if (endA == a.c_str() || endB == b.c_str()) {
        return false;                      // 不是数字
    }
    if (*endA != '\0' || *endB != '\0') {
        return false;                      // 带其它字符
    }
    double diff = fabs(x - y);
    double scale = max(1.0, max(fabs(x), fabs(y)));
    return diff <= EPS * scale;
}

int main(int argc, char *argv[]) {
    /* testlib 要求把这一句写在 main 的第一行 */
    registerTestlibCmd(argc, argv);

    /* 逐个空白分隔的 token 比较：
       ouf 是程序输出，ans 是标准答案，inf 是测试输入。 */
    int index = 0;
    while (!ans.seekEof() || !ouf.seekEof()) {
        ++index;
        if (ans.seekEof() || ouf.seekEof()) {
            quitf(_wa, "token count mismatch at token %d", index);
        }
        string expected = ans.readWord();
        string got = ouf.readWord();
        bool same = NUMERIC_COMPARE ? numericEqual(got, expected)
                                    : (got == expected);
        if (!same) {
            quitf(_wa, "token %d mismatch: got '%s', expected '%s'",
                  index, got.c_str(), expected.c_str());
        }
    }

    quitf(_ok, "answer is correct");
}
