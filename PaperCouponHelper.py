import json
import os
import sys
from datetime import datetime

import BotUtils
from Helper import loadJson, getTimezone


def getPaperCouponInfo() -> dict:
    return getPaperCouponInfo2(loadPaperCouponConfigFile())


def getPaperCouponInfo2(paperExtraData: dict) -> dict:
    paperCouponCharsToValidExpireTimestamp = {}
    """ Load file which contains some extra data which can be useful to correctly determine the "CouponSource" and expire date of paper coupons. """
    for paperChar, paperData in paperExtraData.items():
        validuntil = datetime.strptime(paperData['expire_date'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S').astimezone(getTimezone()).timestamp()
        if validuntil > datetime.now().timestamp():
            paperData['expire_timestamp'] = validuntil
            paperCouponCharsToValidExpireTimestamp[paperChar] = validuntil
    return paperCouponCharsToValidExpireTimestamp


def loadPaperCouponConfigFile() -> dict:
    return loadJson(BotUtils.BotProperty.paperCouponExtraDataPath)


paperExtraData = loadPaperCouponConfigFile()

paperCouponInfo = getPaperCouponInfo2(paperExtraData)
if len(paperCouponInfo) == 0:
    print('Failed to find any paper coupon candidates')
elif len(paperCouponInfo) > 1:
    print('Too many paper coupon candidates available: ' + str(len(paperCouponInfo)))
paperfile = 'paper_coupon_helper_ids.txt'
if not os.path.isfile(paperfile):
    print('File missing: ' + paperfile)
paperChar = list(paperCouponInfo.keys())[0]

couponIDs = []
with open(os.path.join(os.getcwd(), paperfile), encoding='utf-8') as infile:
    for line in infile:
        line = line.strip()
        if not line.isdecimal():
            print('Invalid paper coupon input: ' + line)
            sys.exit()
        couponID = int(line)
        if couponID in couponIDs:
            print('Found duplicate: ' + str(couponID))
            sys.exit()
        couponIDs.append(couponID)
if len(couponIDs) == 0:
    # No mapping data available
    pass
# Validate array size
if len(couponIDs) < 47 or len(couponIDs) > 48:
    print('Array length mismatch: ' + str(len(couponIDs)))
# Build mapping
mapping = {}
number = 1
for couponID in couponIDs:
    # Correct number: Assume than when only 47 items are given, the payback code is missing -> That is usually number 47
    if len(couponIDs) == 47 and number == 47:
        number = 48
    mapping[couponID] = paperChar + str(number)
    number += 1
print(str(mapping))

# Finally update our mapping
paperExtraData[paperChar]['mapping'] = mapping
# Update our config
# open(paper_coupons_config_path, mode='wb').write(paperExtraData)
with open(BotUtils.BotProperty.paperCouponExtraDataPath, 'w') as f:
    json.dump(paperExtraData, f)

sys.exit()
