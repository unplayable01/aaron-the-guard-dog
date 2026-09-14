@echo off
REM Stops aaron_listener.py specifically (not guard_watch.py, not other
REM pythonw.exe processes) by matching its command line.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*aaron_listener.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
