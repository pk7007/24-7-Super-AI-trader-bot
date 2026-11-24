@echo off
rem Launcher for the Windows scheduled tasks IndiaCryptoBot-paper / IndiaCryptoBot-shadow.
rem Usage: run_bot.cmd paper|shadow   (live is deliberately not allowed here)
if /I not "%~1"=="paper" if /I not "%~1"=="shadow" (
  echo run_bot.cmd only starts paper or shadow mode & exit /b 2
)
cd /d "%~dp0"
set STRATEGY=ensemble
set MARKET=spot
set START_EQUITY_USD=113.6
set BOT_MODE=%~1
echo %date% %time% launcher starting %~1 >> "state\%~1_stdout.log"
"C:\tb\venv\Scripts\python.exe" -m bot.main %~1 >> "state\%~1_stdout.log" 2>&1
set RC=%ERRORLEVEL%
echo %date% %time% launcher: bot exited with code %RC% >> "state\%~1_stdout.log"
exit /b %RC%
