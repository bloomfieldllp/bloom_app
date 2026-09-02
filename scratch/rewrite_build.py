import re

with open("build_windows.bat", "r") as f:
    content = f.read()

# VC++ Check
vc_check = r""":: 2\. Download Microsoft Visual C\+\+ Redistributable.*?echo Installing Microsoft Visual C\+\+ Redistributable[^\n]*\nstart /wait vc_redist\.x64\.exe /install /quiet /norestart\nif !errorlevel! neq 0 \([^\)]*\)"""
vc_new = r""":: 2. Check and Install Microsoft Visual C++ Redistributable x64
echo Checking for Microsoft Visual C++ Redistributable...
powershell -Command "if (Get-ItemProperty HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if !errorlevel! equ 0 (
    echo VC++ Redistributable is already installed.
) else (
    echo VC++ Redistributable not found. Installing...
    if not exist vc_redist.x64.exe (
        echo Downloading Microsoft Visual C++ Redistributable...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile 'vc_redist.x64.exe'"
    )
    echo Installing Microsoft Visual C++ Redistributable ^(may prompt for Administrator privileges^)...
    start /wait vc_redist.x64.exe /install /quiet /norestart
    if !errorlevel! neq 0 (
        echo [WARNING] VC++ Redistributable installation returned an error. It might already be installed, or you might have denied the Admin prompt. We will continue anyway.
    )
)"""

# In powershell -Command HKLM:\SOFTWARE, single slash is fine. But for re.sub, we don't want it to treat \S as a group or escape. Wait, re.sub repl string processes \. So I must escape it as \\ in the repl string even if it's a raw string!
vc_new = vc_new.replace("\\", "\\\\")

content = re.sub(vc_check, vc_new, content, flags=re.DOTALL)

# Venv Check
venv_check = r""":: 3\. Create and activate virtual environment\necho Creating virtual environment\.\.\.\n"!PYTHON_EXE!" -m venv venv\nif !errorlevel! neq 0 \([^\)]*\)"""
venv_new = r""":: 3. Create and activate virtual environment
if exist "%CD%\venv\Scripts\python.exe" (
    echo Virtual environment already exists. Reusing...
) else (
    echo Creating virtual environment...
    "!PYTHON_EXE!" -m venv venv
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)"""
venv_new = venv_new.replace("\\", "\\\\")
content = re.sub(venv_check, venv_new, content, flags=re.DOTALL)

# Dep Check
dep_check = r""":: 4\. Install dependencies\necho Installing requirements\.\.\.\n"!VENV_PIP!" install --upgrade pip\n"!VENV_PIP!" install -r requirements\.txt\nif !errorlevel! neq 0 \([^\)]*\)"""
dep_new = r""":: 4. Install dependencies
echo Checking requirements...
set "REQ_HASH_FILE=%CD%\venv\req_hash.txt"
powershell -Command "(Get-FileHash requirements.txt -Algorithm MD5).Hash" > "%CD%\venv\current_req_hash.tmp"
set /p CURRENT_HASH=<"%CD%\venv\current_req_hash.tmp"
del "%CD%\venv\current_req_hash.tmp"

set "STORED_HASH="
if exist "!REQ_HASH_FILE!" (
    set /p STORED_HASH=<!REQ_HASH_FILE!
)

if "!CURRENT_HASH!"=="!STORED_HASH!" (
    echo Requirements have not changed. Skipping pip install.
) else (
    echo Requirements changed or missing. Installing...
    "!VENV_PIP!" install --upgrade pip
    "!VENV_PIP!" install -r requirements.txt
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install dependencies from requirements.txt.
        pause
        exit /b 1
    )
    echo !CURRENT_HASH! > "!REQ_HASH_FILE!"
)"""
dep_new = dep_new.replace("\\", "\\\\")
content = re.sub(dep_check, dep_new, content, flags=re.DOTALL)

# PyInstaller Check
pyinst_check = r"""echo Installing PyInstaller\.\.\.\n"!VENV_PIP!" install pyinstaller==6\.22\.2\nif !errorlevel! neq 0 \([^\)]*\)"""
pyinst_new = r"""echo Checking PyInstaller...
"!VENV_PYTHON!" -c "import PyInstaller; print(PyInstaller.__version__)" > "%CD%\venv\pyinst_ver.tmp" 2>nul
set /p PYINST_VER=<"%CD%\venv\pyinst_ver.tmp"
del "%CD%\venv\pyinst_ver.tmp" 2>nul

if "!PYINST_VER!"=="6.22.2" (
    echo PyInstaller 6.22.2 is already installed.
) else (
    echo Installing PyInstaller 6.22.2...
    "!VENV_PIP!" install pyinstaller==6.22.2
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)"""
pyinst_new = pyinst_new.replace("\\", "\\\\")
content = re.sub(pyinst_check, pyinst_new, content, flags=re.DOTALL)

with open("build_windows.bat", "w") as f:
    f.write(content)
