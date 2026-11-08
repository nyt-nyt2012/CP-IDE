#include <bits/stdc++.h>
using namespace std;
typedef long long ll;
const int MOD = 998244353;
struct Node
{
    int v;
    Node *next;
};
namespace demo
{
    class Solver
    {
        public:
        Solver() : n(0)
        {
        } ~Solver()
        {
            for (int i = 0; i < n; i++) delete a[i];
        } void push(int x)
        {
            a[n++] = new Node
            {
                x
            };
        } int size() const
        {
            return n;
        } private:
        Node *a[1000];
        int n;
    };
} enum Color
{
    RED, GREEN, BLUE
};
int main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    demo::Solver s;
    for (int i = 0; i < 3; i++) s.push(i);
    vector<int> v ={1, 2, 3};
    map<string, int> mp;
    mp["a"] = 1;
    mp["b"] = 2;
    auto it = v.begin();
    while (it != v.end()) {
        cout << *it++;
    } int a = 1, b = 2;
    int c = a + b * 3 - 4 / 2;
    double d = 1.0e-3;
    bool flag =(a < b) &&(a <= b);
    for (auto &[k, val] : mp) cout << k << val;
    int arr[3][4];
    for (int i = 0; i < 3; i++) for (int j = 0; j < 4; j++) arr[i][j] = i * j;
    const char *names[] ={"a", "b"};
    printf("%d\n", c +(int) d +(flag ? 1 : 0));
    return 0;
}
