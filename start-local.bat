@echo off
if exist "%USERPROFILE%\.cargo\bin" (
  set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1" %*
