@echo off
REM ============================================================
REM  Huangguo Downloader - build single-file exe (ASCII only!)
REM  Run this on a Windows PC where Python is installed with
REM  "tcl/tk and IDLE" and "Add python.exe to PATH" checked.
REM ============================================================

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Please install Python from https://www.python.org
    echo and check "Add python.exe to PATH" and "tcl/tk and IDLE".
    pause
    exit /b 1
)

REM --- Guard: the Python used for packing MUST have working tkinter/tcl-tk. ---
REM If "python" resolves to an embedded/managed interpreter (no tcl/tk),
REM PyInstaller silently produces an exe that starts and exits with no window.
python -c "import tkinter" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] The Python in PATH has no working tkinter/tcl-tk.
    echo Packing with it would produce an exe that shows nothing.
    echo Fix: install Python from https://www.python.org with
    echo      "tcl/tk and IDLE" checked, and put it first in PATH.
    echo Current python:
    where python
    pause
    exit /b 1
)

echo [1/3] Upgrading pip ...
python -m pip install --upgrade pip

echo [2/3] Installing dependencies: pycryptodome Pillow pywebview pyinstaller ...
python -m pip install pycryptodome Pillow pywebview pyinstaller

echo [3/3] Building HuangguoDownloader.exe ...
python -m PyInstaller --onefile --windowed --name HuangguoDownloader --icon app_icon.ico --add-data "hls.min.js;." --add-data "app_icon.ico;." --hidden-import Crypto.Cipher.AES --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageTk --collect-all webview --collect-all clr_loader --hidden-import clr huangguo_downloader.py

echo.
if exist "dist\HuangguoDownloader.exe" (
    echo [OK] Build succeeded: dist\HuangguoDownloader.exe
    echo Keep config.json and bin\ in the same folder as the exe.
) else (
    echo [FAIL] Build failed. Check the error messages above.
)
pause
