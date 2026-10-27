@echo off
setlocal
cd /d "%~dp0"

set "PYTHON="
where py >nul 2>nul
if not errorlevel 1 (
    py --version >nul 2>nul
    if not errorlevel 1 set "PYTHON=py"
)
if not defined PYTHON (
    where python >nul 2>nul
    if not errorlevel 1 (
        python --version >nul 2>nul
        if not errorlevel 1 set "PYTHON=python"
    )
)
if not defined PYTHON if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYTHON (
    echo ERROR: Python 3.10 or newer was not found. Install Python and retry.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating project virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create .venv.
        pause
        exit /b 1
    )
)

echo Checking project dependencies...
.venv\Scripts\python.exe -c "import pandas, matplotlib, openpyxl" >nul 2>nul
if errorlevel 1 (
    if not exist "requirements.txt" (
        echo ERROR: requirements.txt is missing.
        pause
        exit /b 1
    )
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Dependency installation failed.
        pause
        exit /b 1
    )
)

.venv\Scripts\python.exe tourism.py
set "EXIT_CODE=%errorlevel%"
if not "%EXIT_CODE%"=="0" echo ERROR: tourism.py exited with code %EXIT_CODE%.
if not defined CI pause
exit /b %EXIT_CODE%
