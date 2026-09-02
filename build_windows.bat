@echo off
REM Bu betik Windows bilgisayarda calistirilir ve tek dosyalik bir .exe uretir.
REM Onceden Python 3.10+ kurulu olmasi gerekir (https://www.python.org/downloads/).

setlocal

python -m venv .venv
call .venv\Scripts\activate.bat

pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

pyinstaller --noconfirm --onefile --windowed ^
    --name "DersProgrami" ^
    --paths src ^
    --add-data "src\dersprogram\assets;dersprogram\assets" ^
    src\run_app.py

echo.
echo Islem tamamlandi. .exe dosyasi "dist\DersProgrami.exe" icinde.
pause
