@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  start "" http://127.0.0.1:8765
  py -3 radar.py serve
) else (
  start "" http://127.0.0.1:8765
  python radar.py serve
)
pause
