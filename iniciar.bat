@echo off
rem TUC7FJ - liga o sistema. Na primeira vez, instala o que for preciso.
chcp 65001 >nul
cd /d "%~dp0"
title TUC7FJ - nao feche esta janela durante a gira
set PYTHONUTF8=1

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto sem_python

if not exist ".venv\Scripts\python.exe" (
  echo Preparando o sistema pela primeira vez. Isso leva alguns minutos...
  %PY% -m venv .venv || goto sem_python
)

rem instala/atualiza as dependencias so quando a lista mudou
fc /b requirements.txt .venv\instalado.txt >nul 2>nul
if errorlevel 1 (
  echo Instalando componentes. Precisa de internet so desta vez...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto erro_instalar
  copy /y requirements.txt .venv\instalado.txt >nul
)

".venv\Scripts\python.exe" servidor.py
echo.
echo O sistema foi desligado.
pause
exit /b 0

:sem_python
echo.
echo Python nao encontrado neste computador.
echo Instale pelo site https://www.python.org/downloads/
echo IMPORTANTE: na primeira tela da instalacao, marque "Add python.exe to PATH".
echo Depois, abra este arquivo de novo.
pause
exit /b 1

:erro_instalar
echo.
echo Nao foi possivel instalar os componentes. Verifique a internet e tente de novo.
pause
exit /b 1
