@echo off
setlocal

rem Run from the repository root even when launched by double-clicking in Explorer.
cd /d "%~dp0"

rem The application uses a local isolated Conda runtime to avoid the base Anaconda Qt DLL conflict.
set "PYTHON_EXE=%~dp0.runtime-env\python.exe"
if not exist "%PYTHON_EXE%" (
    echo.
    echo The local application runtime was not found:
    echo   "%PYTHON_EXE%"
    echo.
    echo Ask a developer to create or restore the .runtime-env folder, then try again.
    pause
    exit /b 1
)

rem Make the src-layout package importable without requiring a separate installation step.
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"

echo Launching FRC Architecture Modeler...
"%PYTHON_EXE%" -m frc_arch_modeler.app %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo FRC Architecture Modeler exited with code %EXIT_CODE%.
    pause
)

endlocal
