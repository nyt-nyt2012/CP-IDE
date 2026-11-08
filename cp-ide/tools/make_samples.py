import os

base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'samples')
os.makedirs(base, exist_ok=True)


def write(name, text):
    with open(os.path.join(base, name), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


write('sample1.in', '5\n3\n-2\n7\n0\n11\n')
write('sample1.out', '19\n')
write('sample2.in', '3\n1\n2\n3\n')
write('sample2.out', '6\n')
write('sample3.in', '1\n0\n')
write('sample3.out', '0\n')

# a small ready-to-use test set for the judging demo
demo = os.path.join(base, 'demo')
os.makedirs(demo, exist_ok=True)


def write_demo(name, text):
    with open(os.path.join(demo, name), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(text)


cases = [('1', [1, 2, 3]), ('2', [10, -5]), ('3', [0]), ('4', [100, 200, 300, 400, 500])]
for name, values in cases:
    write_demo(name + '.in', str(len(values)) + '\n' + '\n'.join(str(v) for v in values) + '\n')
    write_demo(name + '.out', str(sum(values)) + '\n')

write_demo('testpoints.cfg', """# 测试点配置文件示例
[config]
std = c++14
time_limit = 1000
memory_limit = 256
checker = default

[tests]
1 | 1.in | 1.out | 1000 | 256
2 | 2.in | 2.out | 1000 | 256
3 | 3.in | 3.out | 1000 | 256
4 | 4.in | 4.out | 1000 | 256
""")

print('samples written to', base)
for name in sorted(os.listdir(base)):
    print(' -', name)
