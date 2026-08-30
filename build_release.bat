@echo off
setlocal

rem Match StrategySimulation's teammate-release workflow: a self-contained ZIP.
cd /d "%~dp0"
call build_windows.bat
if errorlevel 1 exit /b %ERRORLEVEL%

set "VERSION_TAG="
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "VERSION_TAG=%%i"
set "ZIP_NAME=FRC-Architecture-Modeler_%VERSION_TAG%.zip"

echo Zipping portable application to dist\%ZIP_NAME% ...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\FRC Architecture Modeler\*' -DestinationPath 'dist\%ZIP_NAME%' -Force"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo Release complete: dist\%ZIP_NAME%
endlocal
