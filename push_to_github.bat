@echo off
chcp 65001 >nul
cd /d G:\_setup
echo ============================================================
echo  G:\_setup  -  github.com/a2074629867-crypto/zk7q2m9xvp
echo ============================================================
echo.
echo First push is done. Credentials are already stored in Windows.
echo Double-click this file later to push new changes.
echo.
git add -A
git commit -m "update"
git push
echo.
if errorlevel 1 (
  echo PUSH FAILED - see message above
) else (
  echo DONE
)
pause
