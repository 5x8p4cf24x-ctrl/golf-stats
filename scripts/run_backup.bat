@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\sergi\Documents\golf-stats\scripts\backup_golfstats.ps1"

exit /b %ERRORLEVEL%
