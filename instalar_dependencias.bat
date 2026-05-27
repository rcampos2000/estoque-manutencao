@echo off
title Instalando dependencias...
color 0B
echo.
echo  =====================================================
echo   INSTALACAO DE DEPENDENCIAS
echo  =====================================================
echo.
echo  Instalando pacotes Python necessarios...
echo  (Isso pode demorar alguns minutos na primeira vez)
echo.

pip install customtkinter>=5.2.0
pip install pillow>=10.0.0
pip install python-barcode>=0.15.0
pip install qrcode>=7.4.0
pip install matplotlib>=3.7.0
pip install openpyxl>=3.1.0
pip install pyzbar>=0.1.9
pip install tkcalendar>=1.6.1

echo.
echo  =====================================================
echo   Instalacao concluida!
echo   Execute "iniciar.bat" para abrir o sistema.
echo  =====================================================
echo.
pause
