@echo off
title TenderPulse - Tender Monitoring Agent
cd /d "%~dp0"
echo Starting TenderPulse Agent...
call .\venv\Scripts\activate.bat
streamlit run app.py --server.port 8501
pause
