@echo off
REM =====================================================================
REM  GravaTrem — build.bat: pipeline completo ate o instalador final.
REM  1) confere Python  ->  2) instala deps  ->  3) PyInstaller (onedir)
REM  4) valida o exe     ->  5) Inno Setup (ISCC) -> instalador em
REM     installer\Output\GravaTrem-Setup-<VERSAO>.exe
REM  Uso:  build.bat  (rode na raiz do projeto)
REM =====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set APPNAME=GravaTrem
set VERSION=0.0.1
set DISTDIR=dist\%APPNAME%
set SETUP=installer\Output\%APPNAME%-Setup-%VERSION%.exe

echo [1/5] Verificando Python...
python --version || (echo ERRO: Python nao encontrado no PATH. & exit /b 1)

echo [2/5] Instalando dependencias...
python -m pip install -r requirements.txt || exit /b 1
python -c "import PyInstaller" 2>nul || python -m pip install pyinstaller || exit /b 1

echo [3/5] Gerando bundle com PyInstaller (pode levar alguns minutos)...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer\Output rmdir /s /q installer\Output
python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name %APPNAME% --icon icon.ico ^
  --add-data "lang;lang" --add-data "icon.ico;." --add-data "app.ini;." ^
  --hidden-import win32gui --hidden-import win32api ^
  --hidden-import mss --hidden-import mss.windows ^
  --hidden-import sounddevice --hidden-import pyaudiowpatch ^
  --hidden-import av --hidden-import PIL.Image ^
  --collect-data mss --collect-data sounddevice --collect-data av --collect-data PIL ^
  --collect-binaries av --collect-binaries sounddevice --collect-binaries pyaudiowpatch --collect-binaries numpy ^
  --copy-metadata mss --copy-metadata sounddevice --copy-metadata av --copy-metadata pyaudiowpatch ^
  app.py || exit /b 1

echo [4/5] Validando bundle...
if not exist "%DISTDIR%\%APPNAME%.exe" (echo ERRO: exe nao gerado. & exit /b 1)
if not exist "%DISTDIR%\_internal\icon.ico" if not exist "%DISTDIR%\icon.ico" (echo ERRO: icon.ico nao embutido. & exit /b 1)
if not exist "%DISTDIR%\_internal\app.ini" if not exist "%DISTDIR%\app.ini" (echo ERRO: app.ini nao embutido. & exit /b 1)
if not exist "%DISTDIR%\_internal\lang\Portuguese(BR).ini" (echo ERRO: lang nao embutido. & exit /b 1)
echo OK: %DISTDIR%\%APPNAME%.exe

echo [5/5] Localizando Inno Setup e compilando instalador...
set ISCC=
where iscc >nul 2>nul && (for /f "delims=" %%i in ('where iscc') do set ISCC=%%i)
if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if not defined ISCC (echo ERRO: ISCC.exe nao encontrado. Instale o Inno Setup 6. & exit /b 1)
"%ISCC%" /DAppVersion=%VERSION% installer\%APPNAME%.iss || exit /b 1

if not exist "%SETUP%" (echo ERRO: instalador nao gerado. & exit /b 1)
echo.
echo =====================================================================
echo  INSTALADOR PRONTO: %SETUP%
echo =====================================================================
endlocal
