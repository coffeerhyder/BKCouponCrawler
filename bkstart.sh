#!/bin/bash

# Dieses Script ist zur Verwendung in Crontab gedacht -> Crontab Eintrag:
# */1 * * * * bash /root/betterking/BKCouponCrawler/bkstart.sh

filepath="/root/betterking/BKCouponCrawler/process.pid"
venv_path="/root/betterking/BKCouponCrawler/venv"

start_betterking() {
  cd /root/betterking/BKCouponCrawler \
    && source "$venv_path/bin/activate" \
    && python3 BKBot.py > /tmp/bkbot.log 2>&1 \
    & echo $! > "$filepath"
}

# Start if pid file does not exist
[ ! -f "$filepath" ] && start_betterking && echo "Betterking gestartet weil PID File nicht existiert"

thispid=$(cat "$filepath")
echo "pid ist $thispid"

# Start if pid does not exist
[ ! -d "/proc/$thispid" ] && start_betterking && echo "Betterking gestartet weil PID nicht existiert"

# echo Script execution done
