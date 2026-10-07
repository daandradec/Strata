@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m serve.server --port 62795
