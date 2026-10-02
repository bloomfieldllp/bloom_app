import os
import shutil
import zipfile

def create_windows_build_zip():
    staging_dir = "staging_build"
    zip_filename = "BloomOperator_WindowsBuild_2026-09-02_ManualMapping_v02.zip"
    
    # Remove old staging/zip if exists
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir)
    if os.path.exists(zip_filename):
        os.remove(zip_filename)
        
    os.makedirs(staging_dir)
    
    # Required files at root
    root_files = [
        "build_windows.bat",
        "BloomOperator.spec",
        "requirements.txt",
        "main.py",
        "database.py",
        "config.py",
        "dependencies.py",
        "utils.py",
        "vercel.json"
    ]
    
    # Required directories
    dirs = [
        "services",
        "routes",
        "templates",
        "static",
        "scripts"
    ]
    
    for f in root_files:
        if os.path.exists(f):
            shutil.copy2(f, os.path.join(staging_dir, f))
            
    for d in dirs:
        if os.path.exists(d):
            # Ignore __pycache__
            shutil.copytree(d, os.path.join(staging_dir, d), ignore=shutil.ignore_patterns('__pycache__'))
            
    # Create ZIP archive from staging directory root
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(staging_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # Calculate relative path from staging_dir root
                arcname = os.path.relpath(file_path, staging_dir)
                zipf.write(file_path, arcname)
                
    # Cleanup staging
    shutil.rmtree(staging_dir)
    print(f"Successfully created {zip_filename}")

if __name__ == "__main__":
    create_windows_build_zip()
