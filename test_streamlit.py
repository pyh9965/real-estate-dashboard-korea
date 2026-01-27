import sys
import subprocess
import os

print("Python version:", sys.version)
print("Current directory:", os.getcwd())

try:
    import streamlit
    print("Streamlit version:", streamlit.__version__)
except ImportError as e:
    print("Streamlit import error:", e)
    sys.exit(1)

# Change to the app directory
app_dir = r"c:\Users\pyh99\OneDrive\바탕 화면\마포구 실거래가"
os.chdir(app_dir)
print("Changed to:", os.getcwd())

# Run streamlit
print("Starting Streamlit...")
subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])

