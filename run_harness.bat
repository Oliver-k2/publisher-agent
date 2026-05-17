@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE="

if exist "%LOCALAPPDATA%\OpenAI\Codex\bin\codex.exe" (
    set "CODEX_COMMAND=%LOCALAPPDATA%\OpenAI\Codex\bin\codex.exe"
)
set "CODEX_MODEL=gpt-5.5"

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
    if exist "%%~fD\python.exe" set "PYTHON_EXE=%%~fD\python.exe"
)

if defined PYTHON_EXE (
    "%PYTHON_EXE%" main.py
) else (
    py -3 --version >nul 2>nul
    if "%ERRORLEVEL%"=="0" (
        py -3 main.py
    ) else (
        echo Python was not found.
        echo Install Python, or run this from a terminal that has python on PATH.
        set "EXIT_CODE=1"
        goto finish
    )
)

set "EXIT_CODE=%ERRORLEVEL%"

:finish
echo.
if not "%EXIT_CODE%"=="0" (
    echo Harness exited with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
