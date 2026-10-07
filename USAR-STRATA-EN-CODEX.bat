@echo off
cd /d "%~dp0"
call codex --profile qwen
if errorlevel 1 pause
