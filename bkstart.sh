#!/bin/bash

# Dieses Script ist zur Verwendung in Crontab gedacht -> Crontab Eintrag:
# */1 * * * * sh /root/betterking/BKCouponCrawler/bkstart.sh

start_betterking() {
  cd ~/betterking/BKCouponCrawler && python3 BKBot.py > /tmp/bkbot.log 2>&1 & echo $! >/tmp/betterkingbot.pid
}

filepath=/tmp/betterkingbot.pid

# Start if pid file does not exist
[ ! -f $filepath ] && start_betterking && echo Betterking gestartet weil PID File nicht existiert

thispid=$(cat $filepath)
echo pid ist $thispid

# Partially stolen from: https://stackoverflow.com/questions/3043978/how-to-check-if-a-process-id-pid-exists
# Start if pid does not exist
[ ! -d /proc/$thispid ] && start_betterking && echo Betterking gestartet weil PID nicht existiert
# echo Script execution done