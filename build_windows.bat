@echo off
echo ===================================================
echo Building Bloom Operator Standalone App for Windows
echo ===================================================

:: Ensure python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH! Please install Python first.
    pause
    exit /b
)

:: Install required packages
echo Installing pyinstaller and requirements...
pip install -r requirements.txt
pip install pyinstaller

:: Download Microsoft Visual C++ Redistributable x64 installer if not present
if not exist vc_redist.x64.exe (
    echo Downloading Microsoft Visual C++ Redistributable...
    powershell -Command "Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'vc_redist.x64.exe'"
)

:: Compile package using Windows semicolon separators
pyinstaller BloomOperator.spec --noconfirm

echo ===================================================
echo BUILD COMPLETE! 
echo The Windows standalone app is inside: dist\BloomOperator\
echo ===================================================
pause
