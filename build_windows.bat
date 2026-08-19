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

:: Compile package using Windows semicolon separators
echo Compiling project executable...
pyinstaller --name="BloomOperator" --onedir --add-data="templates;templates" --add-data="static;static" main.py

echo ===================================================
echo BUILD COMPLETE! 
echo The Windows standalone app is inside: dist\BloomOperator\
echo ===================================================
pause
