"""Self test for the C++ formatter.

Checks that

* the formatted output still compiles,
* formatting is idempotent (format(format(x)) == format(x)),
* a couple of specific formatting rules are respected.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.formatter import FormatOptions, format_code  # noqa: E402
from core.toolchain import cxx_path  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_messy.cpp")

EXTRA = r'''
#include <bits/stdc++.h>
using namespace std;
typedef long long ll;
const int MOD = 998244353;
struct Node{int v;Node* next;};
namespace demo{
class Solver{
public:
Solver():n(0){}
~Solver(){for(int i=0;i<n;i++)delete a[i];}
void push(int x){a[n++]=new Node{x};}
int size()const{return n;}
private:
Node* a[1000];int n;
};
}
enum Color{RED,GREEN,BLUE};
int main(){
ios::sync_with_stdio(false);cin.tie(nullptr);
demo::Solver s;for(int i=0;i<3;i++)s.push(i);
vector<int> v={1,2,3};
map<string,int> mp;mp["a"]=1;mp["b"]=2;
auto it=v.begin();while(it!=v.end()){cout<<*it++; }
int a=1,b=2;int c=a+b*3-4/2;
double d=1.0e-3;bool flag=(a<b)&&(a<=b);
for(auto&[k,val]:mp)cout<<k<<val;
int arr[3][4];for(int i=0;i<3;i++)for(int j=0;j<4;j++)arr[i][j]=i*j;
const char* names[]={"a","b"};
printf("%d\n",c+(int)d+(flag?1:0));
return 0;
}
'''


def check_idempotent(name, code, options):
    once = format_code(code, options)
    twice = format_code(once, options)
    if once != twice:
        print("FAIL (not idempotent): %s" % name)
        import difflib
        for line in list(difflib.unified_diff(once.splitlines(), twice.splitlines(),
                                              lineterm=""))[:40]:
            print("   " + line)
        return False
    print("ok   idempotent: %s" % name)
    return True


def check_compiles(name, code, options):
    once = format_code(code, options)
    work = os.path.join(os.path.dirname(SAMPLE), "_fmt_check.cpp")
    with open(work, "w", encoding="utf-8") as fh:
        fh.write(once)
    cxx = cxx_path()
    if not cxx:
        print("skip (no compiler): %s" % name)
        return True
    proc = subprocess.run([cxx, "-std=c++17", "-fsyntax-only", work],
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        print("FAIL (does not compile): %s" % name)
        print(proc.stderr.decode("utf-8", "replace")[:2000])
        return False
    print("ok   compiles: %s" % name)
    return True


def main():
    ok = True
    with open(SAMPLE, encoding="utf-8") as fh:
        sample = fh.read()

    for style in ("allman", "kr"):
        for indent in (2, 4):
            options = FormatOptions(brace_style=style, indent_size=indent)
            tag = "%s/%d" % (style, indent)
            ok &= check_idempotent(tag, sample, options)
            ok &= check_idempotent(tag + " extra", EXTRA, options)
            ok &= check_compiles(tag, sample, options)
            ok &= check_compiles(tag + " extra", EXTRA, options)

    # specific rules
    out = format_code("int  a=1;\nint  b  =  2 ;\n", FormatOptions())
    if out != "int a = 1;\nint b = 2;\n":
        print("FAIL spacing rule, got: %r" % out)
        ok = False
    else:
        print("ok   spacing rule")

    out = format_code("if(x){y();}\n", FormatOptions(brace_style="allman"))
    if out != "if (x)\n{\n    y();\n}\n":
        print("FAIL brace rule, got: %r" % out)
        ok = False
    else:
        print("ok   brace rule")

    out = format_code("vector<int> v;\n", FormatOptions())
    if out != "vector<int> v;\n":
        print("FAIL template rule, got: %r" % out)
        ok = False
    else:
        print("ok   template rule")

    out = format_code("if (a < b && c > d) {}\n", FormatOptions())
    if out != "if (a < b && c > d)\n{\n}\n":
        print("FAIL comparison rule, got: %r" % out)
        ok = False
    else:
        print("ok   comparison rule")

    print()
    print("ALL TESTS PASSED" if ok else "SOME TESTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
