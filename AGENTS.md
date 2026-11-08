# AGENTS.md — CP-IDE 的工作约定

> 这份文件是给「在这个目录里干活的 AI / 人」看的规则。
> 任何改动前后都请先读一遍。

## 项目是什么

**CP-IDE**：一个完全离线的 C++ 竞赛编程 IDE 与评测机。
交付形态是项目根目录的单文件 `CP-IDE.exe`（自带 Python 运行时、页面资源、CodeMirror /
KaTeX / marked / pdf.js、官方 testlib），双击即用，不联网、不需要装 Python、不弹控制台窗口。

源码在 `cp-ide/`：Flask 后端 + 原生 JS 前端 + 自研 C++ 格式化器 + 自研评测机。

---

## 铁律

### 1. 每次改完都要提交并推送到 GitHub（最高优先级）

**只要动了这个目录里的任何文件，完成后一律：提交 → 推送。**

仓库：<https://github.com/nyt-nyt2012/CP-IDE>（**私有**，远端 `origin`，分支 `main`）

```powershell
cd "C:\Users\nieyu\Desktop\IDE项目"
$git = "C:\Program Files\Git\cmd\git.exe"   # 本机 git 不在 PATH，必须用全路径
& $git add -A
& $git commit -m "用中文说明这次改了什么"
& $git push origin main
```

要求：

- **提交信息用中文**，写清「改了什么 / 为什么」，不要只写 "update"。
- 推送前看一眼 `& $git status -sb`，工作区应当干净（没有未提交的残留）。
- 推完用 `& $git ls-remote origin refs/heads/main` 比对本地 `& $git rev-parse HEAD`，确认两边一致。
- 凭据已经在 Git Credential Manager 里（账号 `nyt-nyt2012`），**不需要也不要去动令牌**。
- 如果因为改动了作者身份需要 `--amend`，用 `--force` 强推（这个仓库只有你自己用，没有别人协作）。

### 2. 不要擅自删东西

- 删除一律走可恢复的回收站：`rm -- "<绝对路径>"`，**单独一条命令**，不要和别的语句用 `;` 串在一起。
- 不要动：`winlibs-*.zip`、`cpeditor-master.zip`、`测试点配置文件说明.md`、`_ref/`（除非用户明确要求）。
- 删自己的临时诊断脚本没问题；删用户的文件必须先问。

### 3. 重新打包后要同步 exe

```powershell
cd "C:\Users\nieyu\Desktop\IDE项目\cp-ide"
python tools\stamp_version.py "2026-11-08 12:00 功能说明"     # 写构建时间
python -m PyInstaller --clean --noconfirm CP-IDE.spec         # 产物在 cp-ide\dist\
Copy-Item "C:\Users\nieyu\Desktop\IDE项目\cp-ide\dist\CP-IDE.exe" "C:\Users\nieyu\Desktop\IDE项目\CP-IDE.exe" -Force
```

- 根目录的 `CP-IDE.exe` 才是用户双击的那个，**每次打包后必须覆盖它**。
- 如果 exe 正在运行，Windows 会锁住文件、覆盖失败；这时别反复重试，**告诉用户关掉 IDE 再换**，或挂一个「退出即替换」的守护脚本。
- 打包完顺手清掉 `cp-ide\build\`、`cp-ide\dist\`、`__pycache__\`（`.gitignore` 已经排除了它们）。

### 4. 改完要自测

```powershell
cd "C:\Users\nieyu\Desktop\IDE项目\cp-ide"
python tests\test_formatter.py    # 全部五套必须绿
python tests\test_api.py
python tests\test_checker.py
python tests\test_languages.py
python tests\test_workspace.py
```

改前端还要在浏览器里实测（见下面「怎么起服务」）。

### 5. 改完前端要同步更新 README

`README.md` 在项目根目录，功能一览、快捷键表、HTTP 接口表、常见问题都要跟上改动。

---

## 怎么起服务做实测

```powershell
# 开发服务器（无控制台窗口）
$env:CPIDE_PORT = "5055"          # 5000 常被正在运行的 exe 占着，换个端口
cd "C:\Users\nieyu\Desktop\IDE项目\cp-ide"
python app.py

# 打包好的桌面版（能脱离当前命令存活）
wscript.exe "C:\Users\nieyu\Desktop\IDE项目\cp-ide\tools\launch_cpide.vbs"
```

> ⚠️ 临时改 `LOCALAPPDATA` 做隔离测试会让 Windows 的 Python 安装管理器去重新下载 Python，**不要这么做**。要隔离工作区文件，改用别的端口 + 事后手动恢复。

---

## 踩过的坑（别再踩）

| 现象 | 原因 | 怎么办 |
| --- | --- | --- |
| `WinError 5 拒绝访问`，刚编译的 exe 一启动就没了 | 360安全卫士把新编译的可执行文件隔离了 | 运行器已改成自动重试 + 中文提示；必要时换个目录或关掉实时防护 |
| PowerShell 脚本里的中文全是乱码、语法报错 | PS 5.1 按 GBK 读无 BOM 的 `.ps1` | 脚本写成纯 ASCII，或用 `$PSScriptRoot` 推导路径 |
| `.bat` 被改成 LF | Git 的 `autocrlf` | 项目根的 `.gitattributes` 已固定 `*.bat text eol=crlf` |
| `git` 提示不是内部或外部命令 | 本机 Git 不在 PATH | 用 `C:\Program Files\Git\cmd\git.exe` |
| winget 装 GitHub CLI 一直 504 | 代理挡了 GitHub release CDN | 不需要 gh：Git Credential Manager 里已有凭据，走 API + `git push` 即可 |
| 浏览器里点击总点到隔壁按钮 | Electron 面板窄，坐标映射会偏 | 用 `query(kind="semantic")` 拿 ref 再按 ref 点 |

---

## 目录速览

```
CP-IDE.exe          用户双击的单文件成品
README.md           使用文档（改功能要同步更新）
Start CP-IDE.bat    备用启动器（必须保持 ASCII + CRLF）
.gitignore/.gitattributes
cp-ide/
  app.py            Flask 主程序与全部 HTTP 路由
  desktop.py        桌面版入口（起服务 + pywebview 窗口）
  core/             后端模块：toolchain 编译 / runner 运行与超时 / checker 比对 /
                    formatter 格式化 / testconfig 配置解析 / workspace 持久化 /
                    savedialog 另存为 / snippets 片段 / languages 识别 /
                    pyrunner Python / winflags 子进程窗口标志
  templates/index.html   整个界面（单页）
  static/js/app.js       前端主逻辑
  static/js/md-enhance.js Markdown 扩展渲染（洛谷语法 / KaTeX / 代码块高亮行号）
  static/css/app.css     全部样式（深浅双主题）
  static/vendor/         本地化的 CodeMirror / KaTeX / marked / pdf.js
  include/testlib.h      官方 testlib v0.9.45
  samples/               内置样例、示例文档、示例测试集
  tests/                 五套自测
  tools/                 打包与生成脚本
_ref/                   cpeditor 源码参考（已 gitignore）
```

## 当前版本

- v1.9 —— 侧栏可折叠（`Alt + H`）、编译并运行、运行不带黑框、工作区持久化、临时目录自动清理。
