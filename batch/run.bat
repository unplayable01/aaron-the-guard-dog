@echo off
setlocal
cd /d "%~dp0..\src"
set PYTHON="%~dp0..\venv\Scripts\python.exe"

:menu
echo.
echo ===== Face Recognition =====
echo 1. Capture faces (add/refresh a person)
echo 2. Train model
echo 3. Recognize (live webcam)
echo 4. Full pipeline (capture + train + recognize)
echo 5. Security watch (Telegram alert on unknown face, visible window)
echo 6. Start guard NOW (hidden, locks PC on unknown face)
echo 7. Stop guard
echo 8. Start remote listener (lets you /wake Aaron from Telegram)
echo 9. Stop remote listener
echo 10. Capture a custom gesture
echo 11. Train gestures (fold captures into gesture_model.json)
echo 12. Enroll your voice (for voice-activated wake)
echo 13. Start voice wake listener
echo 14. Stop voice wake listener
echo 15. Exit
echo.
set /p choice="Choose an option (1-15): "

if "%choice%"=="1" goto capture
if "%choice%"=="2" goto train
if "%choice%"=="3" goto recognize
if "%choice%"=="4" goto pipeline
if "%choice%"=="5" goto watch
if "%choice%"=="6" goto guardstart
if "%choice%"=="7" goto guardstop
if "%choice%"=="8" goto listenerstart
if "%choice%"=="9" goto listenerstop
if "%choice%"=="10" goto capturegesture
if "%choice%"=="11" goto traingestures
if "%choice%"=="12" goto enrollvoice
if "%choice%"=="13" goto voicewakestart
if "%choice%"=="14" goto voicewakestop
if "%choice%"=="15" goto end
echo Invalid choice.
goto menu

:capture
set /p personname="Name for this person: "
%PYTHON% capture_faces.py "%personname%"
goto menu

:train
%PYTHON% train_model.py
goto menu

:recognize
%PYTHON% recognize.py
goto menu

:watch
%PYTHON% security_watch.py
goto menu

:guardstart
start "" wscript.exe "%~dp0run_guard_hidden.vbs"
echo Guard started in the background (no window). Check guard_watch.log for activity.
goto menu

:guardstop
call "%~dp0stop_guard.bat"
goto menu

:listenerstart
start "" wscript.exe "%~dp0run_listener_hidden.vbs"
echo Listener started (no window). Message the bot with /wake to start Aaron remotely.
goto menu

:listenerstop
call "%~dp0stop_listener.bat"
goto menu

:capturegesture
set /p gesturename="Name for this gesture (e.g. peace_sign): "
%PYTHON% capture_gesture.py "%gesturename%"
echo Now edit gesture_actions.json to map "%gesturename%" to an action (sleep/lock/snapshot/sit/guard).
goto menu

:traingestures
%PYTHON% train_gestures.py
goto menu

:enrollvoice
%PYTHON% enroll_voice.py
goto menu

:voicewakestart
start "" wscript.exe "%~dp0run_voice_wake_hidden.vbs"
echo Voice wake started (no window). Say the wake phrase to start Aaron.
goto menu

:voicewakestop
call "%~dp0stop_voice_wake.bat"
goto menu

:pipeline
set /p personname="Name for this person: "
%PYTHON% capture_faces.py "%personname%"
if errorlevel 1 goto menu
%PYTHON% train_model.py
if errorlevel 1 goto menu
%PYTHON% recognize.py
goto menu

:end
endlocal
