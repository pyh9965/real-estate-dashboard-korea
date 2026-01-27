#!/usr/bin/env python
# -*- coding: utf-8 -*-
import subprocess
import sys
import os
import time
import socket

def check_port(port):
    """포트가 열려있는지 확인"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    sock.close()
    return result == 0

def main():
    # 디렉토리 변경
    app_dir = r"c:\Users\pyh99\OneDrive\바탕 화면\마포구 실거래가"
    os.chdir(app_dir)
    print(f"작업 디렉토리: {os.getcwd()}")
    
    # 필요한 패키지 확인
    print("\n필요한 패키지 확인 중...")
    try:
        import streamlit
        import pandas
        import plotly
        import openpyxl
        print("✅ 모든 패키지가 설치되어 있습니다.")
    except ImportError as e:
        print(f"❌ 패키지 설치 필요: {e}")
        print("패키지를 설치합니다...")
        subprocess.run([sys.executable, "-m", "pip", "install", "streamlit", "pandas", "plotly", "openpyxl"])
    
    # Streamlit 실행
    print("\n" + "="*50)
    print("Streamlit 앱을 시작합니다...")
    print("="*50)
    print("\n브라우저에서 http://localhost:8501 로 접속하세요!")
    print("종료하려면 Ctrl+C를 누르세요.\n")
    
    # Streamlit 실행
    try:
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.port", "8501",
            "--server.address", "localhost"
        ])
    except KeyboardInterrupt:
        print("\n\n앱이 종료되었습니다.")

if __name__ == "__main__":
    main()

