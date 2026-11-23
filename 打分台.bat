@echo off
chcp 65001 >nul
cd /d G:\_setup
curl -s -o nul --max-time 2 http://127.0.0.1:8765/
if %errorlevel%==0 (
  echo 服务已在运行，直接打开页面...
  start "" http://127.0.0.1:8765/
  exit /b
)
echo 启动打分台...
start "mt-rate" /min G:\Python310\python.exe mt_rate_app.py --port 8765
timeout /t 3 >nul
start "" http://127.0.0.1:8765/
