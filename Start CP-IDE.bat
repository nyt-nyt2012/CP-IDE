@echo off
rem ---------------------------------------------------------------
rem  CP-IDE  -  C++ competitive programming IDE & judge (local)
rem
rem  This file simply hands over to the hidden VBS launcher, so no
rem  terminal window is left on screen.  For the cleanest experience
rem  just double-click CP-IDE.exe in this folder.
rem ---------------------------------------------------------------
wscript.exe "%~dp0cp-ide\tools\launch_cpide.vbs"
exit /b 0
