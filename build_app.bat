@echo off
rem Builds "AI Brief.exe" with the project's .venv and puts it in this folder. Double-click to run.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No .venv found. Create it first:  python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  pause & exit /b 1
)
echo Installing app packages...
".venv\Scripts\python.exe" -m pip install -q -r requirements-app.txt || (pause & exit /b 1)
echo Building...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name "AI Brief" app.py || (pause & exit /b 1)
copy /y "dist\AI Brief.exe" "AI Brief.exe" >nul
echo.
echo Done: "AI Brief.exe" is in this folder. Make a desktop shortcut to it if you like.
pause
