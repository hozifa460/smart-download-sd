@echo off
setlocal
REM Launcher for Smart Download (SD) Native Messaging Host
set SCRIPT_DIR=%~dp0

REM 1. Fast Standalone path: If SmartDownload.exe exists in directory, launch immediately (<5ms)
if exist "%SCRIPT_DIR%SmartDownload.exe" (
    "%SCRIPT_DIR%SmartDownload.exe" --native-host %*
    goto :EOF
)
if exist "%SCRIPT_DIR%TurboDownloader.exe" (
    "%SCRIPT_DIR%TurboDownloader.exe" --native-host %*
    goto :EOF
)

REM 2. Development source mode: Execute native_messaging_host.py directly via python (<50ms)
if exist "%SCRIPT_DIR%native_messaging_host.py" (
    python "%SCRIPT_DIR%native_messaging_host.py" %*
    goto :EOF
)
if exist "%SCRIPT_DIR%..\native_messaging_host.py" (
    python "%SCRIPT_DIR%..\native_messaging_host.py" %*
    goto :EOF
)

REM 3. Dist folder fallback
if exist "%SCRIPT_DIR%dist\SmartDownload.exe" (
    "%SCRIPT_DIR%dist\SmartDownload.exe" --native-host %*
    goto :EOF
)
if exist "%SCRIPT_DIR%dist\TurboDownloader.exe" (
    "%SCRIPT_DIR%dist\TurboDownloader.exe" --native-host %*
    goto :EOF
)

REM 4. Py launcher fallback
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    if exist "%SCRIPT_DIR%native_messaging_host.py" (
        py -3 "%SCRIPT_DIR%native_messaging_host.py" %*
        goto :EOF
    )
)

REM 5. Final fallback
python "%SCRIPT_DIR%native_messaging_host.py" %*
