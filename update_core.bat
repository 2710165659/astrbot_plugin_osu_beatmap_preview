@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Manually update bundled core from upstream repo.
set "REPO_URL=https://github.com/2710165659/osu-agent-skills.git"
set "BRANCH=%~1"
if not defined BRANCH set "BRANCH=main"
set "TARGET_DIR=osu-beatmap-preview"
set "TMP_DIR="
set "EXIT_CODE=0"

call :make_temp_dir
if errorlevel 1 goto :fail

echo Cloning %REPO_URL% ^(%BRANCH%^)...
git clone --depth 1 --branch "%BRANCH%" --filter=blob:none --sparse "%REPO_URL%" "%TMP_DIR%"
if errorlevel 1 goto :fail

echo Fetching %TARGET_DIR% ...
git -C "%TMP_DIR%" sparse-checkout set "%TARGET_DIR%"
if errorlevel 1 goto :fail

if not exist "%TMP_DIR%\%TARGET_DIR%" (
    echo Failed to find fetched directory: %TARGET_DIR%
    goto :fail
)

echo Replacing local %TARGET_DIR% ...
if exist "%TARGET_DIR%" (
    rmdir /s /q "%TARGET_DIR%"
    if errorlevel 1 goto :fail
)

xcopy "%TMP_DIR%\%TARGET_DIR%" "%TARGET_DIR%\" /E /I /H /Y /Q >nul
if errorlevel 1 goto :fail

echo Core updated: %TARGET_DIR%
goto :cleanup

:make_temp_dir
set "TMP_DIR=%TEMP%\update_core_%RANDOM%%RANDOM%"
if exist "%TMP_DIR%" goto :make_temp_dir
mkdir "%TMP_DIR%"
exit /b %ERRORLEVEL%

:fail
set "EXIT_CODE=1"

:cleanup
if defined TMP_DIR if exist "%TMP_DIR%" rmdir /s /q "%TMP_DIR%"
endlocal & exit /b %EXIT_CODE%
