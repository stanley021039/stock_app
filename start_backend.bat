@echo off
REM Start the FastAPI backend on port 8000
set "ROOT=%~dp0"
if exist "%ROOT%env.local.bat" call "%ROOT%env.local.bat"
if not defined STOCK_APP_PYTHON set "STOCK_APP_PYTHON=python"
"%STOCK_APP_PYTHON%" -m uvicorn main:app --app-dir "%ROOT%backend" --port 8000 --host 127.0.0.1
