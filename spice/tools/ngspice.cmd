@echo off
setlocal

set "NGSPICE_EXE=%~dp0..\runtime\ngspice-46\bin\ngspice_con.exe"
if exist "%NGSPICE_EXE%" goto run

set "NGSPICE_EXE=C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe"
if exist "%NGSPICE_EXE%" goto run

for %%E in (ngspice_con.exe) do set "NGSPICE_EXE=%%~$PATH:E"
if defined NGSPICE_EXE goto run

>&2 echo ngspice_con.exe was not found.
>&2 echo Install it in spice\runtime\ngspice-46, C:\Tools\ngspice-46\Spice64\bin, or PATH.
exit /b 9009

:run
"%NGSPICE_EXE%" %*
exit /b %ERRORLEVEL%
