@echo off
setlocal

rem Build a folder-based Windows distribution. This keeps Qt startup fast and
rem avoids relying on a developer's globally installed Python.
cd /d "%~dp0"
set "PYTHON_EXE=%~dp0.runtime-env\python.exe"
if not exist "%PYTHON_EXE%" (
    echo The local application runtime was not found: "%PYTHON_EXE%"
    echo Create .runtime-env and install the build extra first.
    exit /b 1
)

"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --windowed ^
    --name "FRC Architecture Modeler" ^
    --paths src ^
    --collect-all PySide6 ^
    --collect-all tree_sitter_java ^
    --add-data "LICENSE;." ^
    --distpath dist ^
    --workpath build\pyinstaller ^
    --specpath build\pyinstaller ^
    src\frc_arch_modeler\app.py

if errorlevel 1 (
    echo Build failed.
    exit /b %ERRORLEVEL%
)

echo.
echo Build complete: dist\FRC Architecture Modeler\FRC Architecture Modeler.exe
endlocal
