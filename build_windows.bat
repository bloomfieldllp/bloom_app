@echo off
setlocal EnableDelayedExpansion

echo ===================================================
echo Building Bloom Operator Standalone App for Windows
echo ===================================================

set "PYTHON_EXE="

:: 1. Try to find python 3.12 in common locations or PATH
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
) else if exist "%ProgramFiles%\Python312\python.exe" (
    set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
) else (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=python"
    )
)

if "!PYTHON_EXE!"=="" (
    echo Python 3.12+ not found.
    echo Downloading official Python 3.12.5 installer...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.5/python-3.12.5-amd64.exe' -OutFile 'python-3.12.5-amd64.exe'"
    if not exist "python-3.12.5-amd64.exe" (
        echo [ERROR] Failed to download Python installer.
        pause
        exit /b 1
    )
    echo Installing Python 3.12.5 silently... ^(User-level install, no admin required^)
    start /wait python-3.12.5-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
    if !errorlevel! neq 0 (
        echo [ERROR] Python installation failed.
        pause
        exit /b 1
    )
    
    if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
        set "PYTHON_EXE=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    ) else (
        set "PYTHON_EXE=python"
    )
)

echo Using Python at: !PYTHON_EXE!
"!PYTHON_EXE!" --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Python is still not accessible. Please install it manually.
    pause
    exit /b 1
)

:: 2. Download Microsoft Visual C++ Redistributable x64 installer if not present
if not exist vc_redist.x64.exe (
    echo Downloading Microsoft Visual C++ Redistributable...
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'vc_redist.x64.exe'"
)

echo Installing Microsoft Visual C++ Redistributable ^(may prompt for Administrator privileges^)...
start /wait vc_redist.x64.exe /install /quiet /norestart
if !errorlevel! neq 0 (
    echo [WARNING] VC++ Redistributable installation returned an error. It might already be installed, or you might have denied the Admin prompt. We will continue anyway.
)

:: 3. Create and activate virtual environment
echo Creating virtual environment...
"!PYTHON_EXE!" -m venv venv
if !errorlevel! neq 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

set "VENV_PYTHON=%CD%\venv\Scripts\python.exe"
set "VENV_PIP=%CD%\venv\Scripts\pip.exe"

if not exist "!VENV_PYTHON!" (
    echo [ERROR] Virtual environment python.exe not found.
    pause
    exit /b 1
)

:: 4. Install dependencies
echo Installing requirements...
"!VENV_PIP!" install --upgrade pip
"!VENV_PIP!" install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    pause
    exit /b 1
)

echo Running pip check to verify dependency resolution...
"!VENV_PIP!" check
if !errorlevel! neq 0 (
    echo [ERROR] Dependency conflict detected by pip check.
    pause
    exit /b 1
)

echo Verifying core imports and Python architecture...
"!VENV_PYTHON!" -c "import sys; assert sys.maxsize > 2**32, 'Not running on x64 Python'; import numpy; import pandas; import fastapi; import uvicorn; import bcrypt; import webview; import motor"
if !errorlevel! neq 0 (
    echo [ERROR] Dependency import validation failed or architecture is not 64-bit.
    pause
    exit /b 1
)

echo Installing PyInstaller...
"!VENV_PIP!" install pyinstaller==6.22.2
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install PyInstaller.
    pause
    exit /b 1
)

:: 5. Build the application
echo Building application with PyInstaller...
"!VENV_PYTHON!" -m PyInstaller BloomOperator.spec --noconfirm
if !errorlevel! neq 0 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

:: 6. Verify output
if not exist "dist\BloomOperator\BloomOperator.exe" (
    echo ===================================================
    echo BUILD FAILED
    echo The executable dist\BloomOperator\BloomOperator.exe was not created.
    echo Please check the build logs above.
    echo ===================================================
    pause
    exit /b 1
)

echo ===================================================
echo BUILD SUCCESSFUL
echo.
echo RUN THIS FILE:
echo dist\BloomOperator\BloomOperator.exe
echo ===================================================
pause
