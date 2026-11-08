' ---------------------------------------------------------------------
'  CP-IDE - start the local server without a console window.
'  Used by the "CP-IDE Server" scheduled task so the server is not
'  affected by console close events (it keeps running in the background).
' ---------------------------------------------------------------------
Option Explicit

Dim shell, fso, appDir, pythonExe

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' This script lives in <cp-ide>\tools\, the server runs in <cp-ide>
appDir = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
shell.CurrentDirectory = appDir

' Prefer the interpreter that is already on PATH, fall back to py.exe
pythonExe = "python"
If Not fso.FileExists(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe")) Then
    If fso.FileExists(shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python\Python312\python.exe")) Then
        pythonExe = "py"
    End If
End If

' 0 = hidden window, False = do not wait for it to finish
shell.Run """" & pythonExe & """ app.py", 0, False
