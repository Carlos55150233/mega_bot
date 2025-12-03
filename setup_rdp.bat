@echo off
title Mega Bot RDP Setup Installer
color 0A

echo ===================================================
echo      MEGA BOT RDP AUTO-INSTALLER
echo ===================================================
echo.
echo [1/6] Checking for Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found. Installing Python 3.10...
    winget install -e --id Python.Python.3.10
    echo Please RESTART this script after Python installation!
    pause
    exit
) else (
    echo Python is installed.
)

echo.
echo [2/6] Checking for Git...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Git not found. Installing Git...
    winget install -e --id Git.Git
    echo Please RESTART this script after Git installation!
    pause
    exit
) else (
    echo Git is installed.
)

echo.
echo [3/6] Cloning Repository...
if exist "mega_bot" (
    echo Repository already exists. Updating...
    cd mega_bot
    git pull
) else (
    echo Cloning repository...
    git clone https://github.com/Carlos55150233/mega_bot.git
    cd mega_bot
)

echo.
echo [4/6] Installing Dependencies...
pip install -r requirements.txt

echo.
echo [5/6] Configuring Environment...
if not exist ".env" (
    echo Creating .env file...
    set /p TOKEN="Enter your Telegram Bot Token: "
    set /p API_ID="Enter your Telegram API ID: "
    set /p API_HASH="Enter your Telegram API HASH: "
    
    echo TELEGRAM_TOKEN=%TOKEN%> .env
    echo API_ID=%API_ID%>> .env
    echo API_HASH=%API_HASH%>> .env
    echo PORT=8080>> .env
    echo .env created!
) else (
    echo .env file already exists.
)

echo.
echo [6/6] Setup Complete!
echo.
echo To start the bot, run: python main.py
echo.
pause
