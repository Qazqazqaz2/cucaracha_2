@echo off
echo ========================================
echo    Crypto Exchange Bot - Backup Tool
echo ========================================
echo.

if "%1"=="" (
    echo Usage:
    echo   backup.bat backup     - create backup
    echo   backup.bat restore    - restore from backup
    echo   backup.bat history    - show backup history
    echo   backup.bat status     - show status
    echo.
    pause
    exit /b
)

python backup_script.py %1

echo.
pause
