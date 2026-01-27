@echo off
chcp 65001 >nul
cls

echo ========================================
echo   Apartment Real Estate Dashboard
echo ========================================
echo.

cd /d "%~dp0"

echo Checking Python installation...
py --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed.
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)
echo Python found!
echo.

echo Installing required packages...
py -m pip install --upgrade pip >nul 2>&1
py -m pip install streamlit pandas plotly openpyxl --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install packages.
    pause
    exit /b 1
)
echo Packages installed successfully!
echo.

echo ========================================
echo   Starting Dashboard...
echo ========================================
echo.
echo The app will open in your browser at:
echo    http://localhost:8501
echo.
echo Press Ctrl+C to stop the server.
echo ========================================
echo.

py -m streamlit run app.py --server.port 8501 --server.address localhost

pause
