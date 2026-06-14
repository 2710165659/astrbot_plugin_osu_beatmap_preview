@echo off
setlocal EnableExtensions DisableDelayedExpansion

rem Download latest osu-beatmap-preview Rust binaries from GitHub releases.
rem Platforms: Windows amd64, Linux amd64, macOS amd64, macOS arm64.

set "REPO=2710165659/osu-beatmap-preview"
set "BIN_DIR=%~dp0bin"
set "TAG="
set "EXIT_CODE=0"

echo Fetching latest release tag from %REPO% ...
powershell -NoProfile -Command ^
  "$r = Invoke-RestMethod -Uri 'https://api.github.com/repos/%REPO%/releases/latest'; Write-Output $r.tag_name" > "%TEMP%\latest_tag.txt"
if errorlevel 1 goto :fail

set /p TAG=<"%TEMP%\latest_tag.txt"
if not defined TAG goto :fail
echo Latest tag: %TAG%

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
if errorlevel 1 goto :fail

echo Downloading binaries into bin\ ...

set "BASE_URL=https://github.com/%REPO%/releases/download/%TAG%"

rem --- Windows amd64 ---
echo   [1/4] windows-amd64 ...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri '%BASE_URL%/osu-beatmap-preview-windows-amd64.exe' -OutFile '%BIN_DIR%\osu-beatmap-preview-windows-amd64.exe'" -ErrorAction Stop
if errorlevel 1 goto :fail
echo     ok

rem --- Linux amd64 ---
echo   [2/4] linux-amd64 ...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri '%BASE_URL%/osu-beatmap-preview-linux-amd64' -OutFile '%BIN_DIR%\osu-beatmap-preview-linux-amd64'" -ErrorAction Stop
if errorlevel 1 goto :fail
echo     ok

rem --- macOS amd64 ---
echo   [3/4] macos-amd64 ...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri '%BASE_URL%/osu-beatmap-preview-macos-amd64' -OutFile '%BIN_DIR%\osu-beatmap-preview-macos-amd64'" -ErrorAction Stop
if errorlevel 1 goto :fail
echo     ok

rem --- macOS arm64 ---
echo   [4/4] macos-arm64 ...
powershell -NoProfile -Command ^
  "Invoke-WebRequest -Uri '%BASE_URL%/osu-beatmap-preview-macos-arm64' -OutFile '%BIN_DIR%\osu-beatmap-preview-macos-arm64'" -ErrorAction Stop
if errorlevel 1 goto :fail
echo     ok

echo.
echo Core updated successfully to %TAG%.
echo Binaries placed in: %BIN_DIR%
goto :cleanup

:fail
set "EXIT_CODE=1"
echo Update failed.

:cleanup
if exist "%TEMP%\latest_tag.txt" del "%TEMP%\latest_tag.txt"
endlocal & exit /b %EXIT_CODE%
