@echo off
chcp 65001 >nul
cd /d "c:\Users\pyh99\OneDrive\바탕 화면\마포구 실거래가"
echo ========================================
echo Streamlit 실행 중...
echo ========================================
echo.
python -m streamlit run app.py 2>&1 | tee streamlit_log.txt
pause

