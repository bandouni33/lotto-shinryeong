@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  브라우저에서 미리듣기 페이지를 엽니다...
echo  주소: http://localhost:8765/promo_listen.html
echo  종료: 이 창에서 Ctrl+C
echo.
start "" "http://localhost:8765/promo_listen.html"
python -m http.server 8765
