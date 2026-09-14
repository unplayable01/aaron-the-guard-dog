@echo off
REM Stops voice_wake.py specifically (not guard_watch.py, not aaron_listener.py,
REM not other pythonw.exe processes) by matching its command line.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*voice_wake.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
