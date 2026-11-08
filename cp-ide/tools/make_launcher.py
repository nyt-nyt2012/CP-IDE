import os

root = r'C:\Users\nieyu\Desktop\IDE项目'

bat = r'''@echo off
rem ---------------------------------------------------------------
rem  CP-IDE  -  C++ competitive programming IDE & judge (local)
rem  Double click this file to start the server and open the browser.
rem ---------------------------------------------------------------
title CP-IDE  -  C++ Judge Workbench
cd /d "%~dp0cp-ide"

echo.
echo   ==============================================
echo     CP-IDE   C++  judge workbench
echo   ==============================================
echo.
echo   Starting server ...  please wait a moment.
echo   Then the browser will open automatically.
echo   If it does not, visit:  http://127.0.0.1:5000/
echo   Press Ctrl+C in this window to stop the server.
echo.

start "" /b python -c "import time,webbrowser;time.sleep(3);webbrowser.open('http://127.0.0.1:5000/')"
python app.py

echo.
echo   Server stopped.
pause
'''

path = os.path.join(root, 'Start CP-IDE.bat')
with open(path, 'w', encoding='ascii', newline='\r\n') as fh:
    fh.write(bat)

print('written:', path)
print('size:', os.path.getsize(path))
