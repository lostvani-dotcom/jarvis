@echo off
REM iniciar_jarvis_com_console.bat
REM =================================
REM Mesma coisa que "Iniciar Jarvis.vbs", mas com o console visível --
REM use este pra diagnosticar um problema (Python não encontrado,
REM dependência faltando, erro na inicialização), já que o .vbs não
REM mostra nada na tela se der errado.
cd /d "%~dp0"
python main.py
pause
