@echo off
REM Start the Sinopac/Shioaji quote service (HTTP API on SJ_HTTP_ADDR, default 127.0.0.1:8090).
REM shioaji.exe auto-loads .env from its working directory, so cd to the project root first.
cd /d "%~dp0"
if exist "%~dp0env.local.bat" call "%~dp0env.local.bat"
if not defined STOCK_APP_PYTHON set "STOCK_APP_PYTHON=python"
REM shioaji.exe ships in the same env's Scripts\ folder; fall back to PATH.
set "SHIOAJI=shioaji"
for %%I in ("%STOCK_APP_PYTHON%") do if exist "%%~dpIScripts\shioaji.exe" set "SHIOAJI=%%~dpIScripts\shioaji.exe"
REM Sweep old quote-service-<timestamp>.log archives into logs\quote-service\.
"%STOCK_APP_PYTHON%" scripts\rotate_quote_logs.py
"%SHIOAJI%" server start --no-open
