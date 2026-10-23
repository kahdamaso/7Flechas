@echo off
rem TUC7FJ - importa os cadastros da planilha baixada do Google Drive (.xlsx).
rem Uso: arraste o arquivo .xlsx para cima deste arquivo.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if "%~1"=="" (
  echo Arraste o arquivo .xlsx baixado do Google Drive para cima do importar.bat.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Abra primeiro o iniciar.bat uma vez, para preparar o sistema.
  pause
  exit /b 1
)
echo Importando "%~nx1"...
".venv\Scripts\python.exe" -m flask --app run importar "%~1" > importacao-relatorio.txt 2>&1
type importacao-relatorio.txt
echo.
echo Este relatorio tambem foi salvo em importacao-relatorio.txt
pause
