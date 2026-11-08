#include <bits/stdc++.h>
using namespace std;
int main(){
int n;cin>>n;
vector<int>a(n);
for(int i=0;i<n;i++){cin>>a[i];}
long long sum=0;
for(auto &x:a)sum+=x;
if(sum>0){cout<<sum<<endl;}else{cout<<-sum<<endl;}
switch(n){
case 1:
cout<<"one";
break;
case 2:{
int t=2;
cout<<t;
break;
}
default:
break;
}
struct P{int x,y;};
P p{1,2};
cout<<p.x+p.y<<endl;
const char* s = "hello, world";
string t2 = R"(raw "string" here)";
int *ptr=new int[10];
int **pp=&ptr;
auto lam=[](int x)->int{return x*2;};
cout<<lam(21)<<' '<<s<<' '<<t2<<' '<<*ptr<<' '<<**pp<<endl;
return 0;
}
