@echo off
setlocal
REM Launcher for Turbo Download Manager Native Messaging Host
set SCRIPT_DIR=%~dp0

REM 1. Fast path: If python is available on system, run script directly (<50ms)
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    if exist "%SCRIPT_DIR%native_messaging_host.py" (
        python "%SCRIPT_DIR%native_messaging_host.py" %*
        goto :EOF
    )
    if exist "%SCRIPT_DIR%..\native_messaging_host.py" (
        python "%SCRIPT_DIR%..\native_messaging_host.py" %*
        goto :EOF
    )
)

REM 2. Check py launcher
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    if exist "%SCRIPT_DIR%native_messaging_host.py" (
        py -3 "%SCRIPT_DIR%native_messaging_host.py" %*
        goto :EOF
    )
    if exist "%SCRIPT_DIR%..\native_messaging_host.py" (
        py -3 "%SCRIPT_DIR%..\native_messaging_host.py" %*
        goto :EOF
    )
)

REM 3. Standalone binary fallback
if exist "%SCRIPT_DIR%TurboDownloader.exe" (
    "%SCRIPT_DIR%TurboDownloader.exe" --native-host %*
    goto :EOF
) else if exist "%SCRIPT_DIR%dist\TurboDownloader.exe" (
    "%SCRIPT_DIR%dist\TurboDownloader.exe" --native-host %*
    goto :EOF
)

REM 4. Final attempt
python "%SCRIPT_DIR%native_messaging_host.py" %*
