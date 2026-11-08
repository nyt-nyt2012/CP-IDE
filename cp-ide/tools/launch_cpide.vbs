' ---------------------------------------------------------------------
'  CP-IDE - 无控制台启动器
'
'  双击本文件不会弹出终端窗口：
'    * 有打包好的 CP-IDE.exe 时，直接以隐藏窗口方式启动它；
'    * 没有时用 Python 起本地服务器，3 秒后自动打开浏览器。
'
'  （Start CP-IDE.bat 也会转调到这里，所以那条路径同样不弹终端。）
' ---------------------------------------------------------------------
Option Explicit

Dim shell, fso, toolsDir, appDir, projectRoot, exePath, pythonExe

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

toolsDir = fso.GetParentFolderName(WScript.ScriptFullName)   ' ...\cp-ide\tools
appDir = fso.GetParentFolderName(toolsDir)                   ' ...\cp-ide
projectRoot = fso.GetParentFolderName(appDir)                ' 项目根目录

' ---- 1) 打包好的桌面版（GUI 程序，本身就没有控制台窗口） ----
exePath = projectRoot & "\CP-IDE.exe"
If fso.FileExists(exePath) Then
    shell.Run """" & exePath & """", 0, False
    WScript.Quit 0
End If

' ---- 2) 源码运行：起服务器，稍后打开浏览器 ----
pythonExe = "python"
If Not fso.FileExists(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe")) Then
    If fso.FileExists(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\python.exe")) Then
        pythonExe = "py"
    End If
End If

shell.CurrentDirectory = appDir
shell.Run """" & pythonExe & """ app.py", 0, False

WScript.Sleep 3000
shell.Run "explorer.exe http://127.0.0.1:5000/", 0, False
