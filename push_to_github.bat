@echo off
chcp 65001 >nul
cd /d G:\_setup
echo ============================================================
echo  MintReader TTS - push to GitHub
echo  repo: https://github.com/a2074629867-crypto/mintreader-tts-pipeline
echo ============================================================
echo.
echo [1/3] checking remote ...
git remote set-url origin https://github.com/a2074629867-crypto/mintreader-tts-pipeline.git
echo [2/3] local branch / commits:
git log --oneline
echo.
echo [3/3] pushing (a browser window may pop up for GitHub login) ...
git push -u origin main
if errorlevel 1 (
  echo.
  echo PUSH FAILED.
  echo   - if repo does not exist yet: create it at https://github.com/new
  echo     name = mintreader-tts-pipeline , Public , do NOT add README
  echo   - if login failed: a credential window should pop up; sign in and run again
) else (
  echo.
  echo OK - view it at https://github.com/a2074629867-crypto/mintreader-tts-pipeline
)
echo.
pause
