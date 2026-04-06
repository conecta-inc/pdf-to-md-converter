@echo off
echo ============================================
echo   Conecta .md Converter - Build
echo ============================================
echo.

echo Instalando dependencias...
pip install pymupdf pyinstaller
echo.

echo Gerando executavel...
python -m PyInstaller --onefile --windowed --name "Conecta MD Converter" --add-data "logo a ser utilizado.png;." pdf2md.py
echo.

echo.
echo Build concluido! O executavel esta em: dist\Conecta MD Converter.exe
echo.
pause
