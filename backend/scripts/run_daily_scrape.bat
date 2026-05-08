@echo off
chcp 65001 >nul
echo [%date% %time%] Starting WeChat stats scrape...

cd /d "C:\Users\anzib\gzh-platform\backend\scripts"
python scrape_wechat_stats.py --headless >> scrape.log 2>&1

echo [%date% %time%] Scrape finished.
