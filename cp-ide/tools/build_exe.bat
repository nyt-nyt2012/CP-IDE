@echo off
rem ---------------------------------------------------------------
rem  CP-IDE  -  build the standalone Windows executable (single file)
rem
rem  Usage:  build_exe.bat
rem
rem  Produces  cp-ide\dist\CP-IDE.exe  and copies it next to
rem  "Start CP-IDE.bat" so it can be launched directly.
rem
rem  The build time is stamped into core\version.py so the running
rem  app can tell you which build it is (Settings - About).
rem
rem  NOTE: building needs the build-time dependencies (one-time, needs
rem  network access).  The resulting exe runs fully offline.
rem ---------------------------------------------------------------------
setlocal
cd /d "%~dp0.."

echo.
echo   ==============================================
echo     CP-IDE  -  build standalone exe
echo   ==============================================
echo.

python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo   Installing build dependencies ...
    python -m pip install --disable-pip-version-check pyinstaller==6.22.3 pywebview==6.2.1 pythonnet==3.2.1
)

rem --- stamp the build time into core\version.py ------------------------
python tools\stamp_version.py

echo   Building cp-ide\dist\CP-IDE.exe ...
python -m PyInstaller --clean --noconfirm CP-IDE.spec
if errorlevel 1 (
    echo.
    echo   BUILD FAILED.
    exit /b 1
)

if not exist "dist\CP-IDE.exe" (
    echo.
    echo   BUILD FAILED: dist\CP-IDE.exe not found.
    exit /b 1
)

copy /y "dist\CP-IDE.exe" "..\CP-IDE.exe" >nul
echo.
echo   Done.
echo   - cp-ide\dist\CP-IDE.exe
echo   - ..\CP-IDE.exe  (next to Start CP-IDE.bat)
echo.
endlocal
