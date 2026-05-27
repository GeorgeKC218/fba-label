@echo off
cd /d "%~dp0"
echo Installing dependencies if needed...
pip install -r requirements.txt -q
echo.
echo Starting web app...
echo Open the URL shown below in your browser.
echo.
streamlit run app.py
