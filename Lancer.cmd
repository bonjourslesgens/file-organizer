@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 -m file_organizer %*
goto finished
:try_python
where python >nul 2>&1
if errorlevel 1 goto missing
python -m file_organizer %*
goto finished
:missing
echo Python 3.11 ou plus recent est requis. Installez-le depuis python.org.
echo Choisissez Add Python to PATH pendant l'installation.
pause
exit /b 1
:finished
if errorlevel 1 pause
endlocal
