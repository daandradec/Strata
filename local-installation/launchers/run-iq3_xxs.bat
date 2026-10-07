@echo off
title Strata IQ3_XXS
cd /d "E:\Strata"
"E:\Strata\.venv\Scripts\python.exe" "E:\Strata\serve\server.py" "--engine" "strata" "--config" "E:\Strata\strata-iq3_xxs.json" "--port" "8081"
if errorlevel 1 pause
