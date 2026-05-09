@echo off
setlocal
cd /d "%~dp0.."
python scripts\sync_wechat_stats.py --source api >> scripts\wechat_stats_sync.log 2>&1
