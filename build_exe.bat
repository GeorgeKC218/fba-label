@echo off
cd /d "%~dp0"
echo Installing PyInstaller...
pip install pyinstaller -q
echo.
echo Building FBA barcode desktop app (may take 1-2 minutes)...
pyinstaller --onefile --windowed --name "FBA条码排版" ^
  --hidden-import=fitz ^
  --collect-all pymupdf ^
  desktop_app.py
echo.
if exist "dist\FBA条码排版.exe" (
  echo Success: dist\FBA条码排版.exe
  explorer dist
) else (
  echo Build failed. Check errors above.
)
pause
