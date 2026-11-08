# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把 CP-IDE 打成单个 Windows exe。

用法（在 cp-ide 目录下）::

    pyinstaller --clean --noconfirm CP-IDE.spec

产物是 ``dist/CP-IDE.exe``：双击即可运行，自带 Python 解释器与全部页面资源，
不需要另外安装 Python，也不依赖网络。

打包之后有两处路径会变化，代码里由 ``core/paths.py`` 统一处理：

* 只读资源（templates / static / include / samples）位于解包出来的临时目录；
* 需要写入的数据（自建代码片段、临时构建目录）放在 ``%LOCALAPPDATA%\\CP-IDE``。
"""

import os

BASE = os.path.abspath(SPECPATH)

# 需要随 exe 一起携带的只读资源
datas = [
    (os.path.join(BASE, "templates"), "templates"),
    (os.path.join(BASE, "static"), "static"),
    (os.path.join(BASE, "include"), "include"),
    (os.path.join(BASE, "samples"), "samples"),
]

# 动态导入的模块：pywebview 的窗口后端、pythonnet 运行时
hiddenimports = [
    "clr",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "webview.http",
    "encodings.idna",
    "jinja2.ext",
    "werkzeug.middleware",
]

block_cipher = None

a = Analysis(
    [os.path.join(BASE, "desktop.py")],
    pathex=[BASE],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter.test",
        "test",
        "unittest",
        "pydoc_data",
        "numpy",
        "pandas",
        "matplotlib",
        "PIL",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CP-IDE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 不弹控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
