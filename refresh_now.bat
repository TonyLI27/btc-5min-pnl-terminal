@echo off
setlocal EnableExtensions
title BTC 5-MIN PnL - Manual Refresh

rem Run from this script's own directory (online_pnl_web/) regardless of how it was launched.
pushd "%~dp0"

set "PYTHON=C:\Users\User\anaconda3\python.exe"

echo ============================================================
echo   BTC 5-MIN PnL  -  Manual Online Refresh
echo   Repo: TonyLI27/btc-5min-pnl-terminal  (branch: main)
echo ============================================================
echo.

if not exist "%PYTHON%" (
    echo ERROR: Python not found at "%PYTHON%".
    goto :failed
)

if not exist "calc_pnl.py" (
    echo ERROR: calc_pnl.py not found in "%CD%".
    goto :failed
)

echo [1/4] Syncing with origin/main (rebase) ...
rem data.json + activity_cache.json are regenerated below (step 2) and are
rem also rewritten by the GitHub Actions cron every tick. Discard any local
rem copy BEFORE the pull so the --autostash pop can never collide on them.
rem (-X theirs governs only the rebase, NOT the autostash pop; a pop conflict
rem leaves UU paths with no MERGE_HEAD and a stranded stash, which previously
rem wedged the repo. Source-file edits still autostash normally.)
git checkout HEAD -- data.json activity_cache.json 2>nul
git pull --rebase -X theirs --autostash origin main
if errorlevel 1 (
    echo.
    echo ERROR: git pull --rebase failed. Resolve manually, then re-run.
    goto :failed
)
echo.

echo [2/4] Running calc_pnl.py to regenerate data.json ...
echo ------------------------------------------------------------
"%PYTHON%" calc_pnl.py
if errorlevel 1 (
    echo.
    echo ERROR: calc_pnl.py failed. See output above.
    goto :failed
)
echo ------------------------------------------------------------
echo.

echo [3/4] Staging data.json + activity_cache.json ...
git add data.json activity_cache.json
if errorlevel 1 goto :failed

set "HAVE_NEW_COMMIT=0"
set "TS="
git diff --cached --quiet
if errorlevel 1 goto :have_changes
echo No new data to commit from this run.
goto :check_push

:have_changes
echo.
echo [4/4] Committing fresh data ...
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mmZ')"`) do set "TS=%%i"
git commit -m "data: refresh %TS%"
if errorlevel 1 goto :failed
set "HAVE_NEW_COMMIT=1"

:check_push
rem --- Push anything we have ahead of origin (covers commits stranded by a previous rejected push) ---
set "AHEAD=0"
for /f "usebackq delims=" %%i in (`git rev-list --count "@{u}..HEAD" 2^>nul`) do set "AHEAD=%%i"

if "%AHEAD%"=="0" (
    echo Nothing to push. Online dashboard is already up-to-date.
    goto :done
)

echo.
echo Pushing %AHEAD% commit(s) to origin/main ...
git push
if not errorlevel 1 goto :pushed

rem Race with GitHub Actions cron: pull again, then retry once.
echo.
echo Push rejected (remote moved). Pulling again and retrying ...
git pull --rebase -X theirs --autostash origin main
if errorlevel 1 goto :failed
git push
if errorlevel 1 goto :failed

:pushed
echo.
echo ============================================================
if "%HAVE_NEW_COMMIT%"=="1" (
    echo   SUCCESS: pushed "data: refresh %TS%" to origin/main.
) else (
    echo   SUCCESS: pushed pending commit^(s^) to origin/main.
)
echo   GitHub Pages usually reflects the change within ~1 minute.
echo   Reload: https://tonyli27.github.io/btc-5min-pnl-terminal/
echo ============================================================
goto :done

:failed
echo.
echo ============================================================
echo   *** REFRESH FAILED ***
echo ============================================================
popd
echo.
pause
exit /b 1

:done
popd
echo.
pause
exit /b 0
