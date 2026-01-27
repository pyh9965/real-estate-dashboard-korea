@echo off
chcp 65001 >nul
cd /d "c:\Users\pyh99\OneDrive\바탕 화면\마포구 실거래가"
echo 현재 디렉토리: %CD%
echo Streamlit 앱을 시작합니다...
echo.
python -m streamlit run app.py
pause

