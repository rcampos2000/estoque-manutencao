@echo off
title Controle de Pecas de Reposicao - Manutencao Industrial
color 0A
echo.
echo  =====================================================
echo   CONTROLE DE PECAS DE REPOSICAO - MANUTENCAO
echo  =====================================================
echo.
echo  Verificando Python...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  ERRO: Python nao encontrado!
    echo  Instale o Python em: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo  Verificando dependencias...
pip install customtkinter pillow python-barcode qrcode matplotlib openpyxl pyzbar --quiet --break-system-packages 2>nul

echo  Iniciando o sistema...
echo.
cd /d "%~dp0"
python app.py

if %errorlevel% neq 0 (
    echo.
    echo  ERRO ao iniciar o sistema. Verifique o arquivo app.py
    pause
)
