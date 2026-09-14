@echo off
REM Stops guard_watch.py specifically (not aaron_listener.py, not other
REM pythonw.exe processes) by matching its command line - important now
REM that the always-on listener also runs as pythonw.exe.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*guard_watch.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
