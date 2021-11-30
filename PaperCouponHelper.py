import os
import sys

import BotUtils
from Helper import saveJson, loadPaperCouponConfigFile

""" Helper to complete config file with data from 'paper_coupon_helper_ids.txt'. """

paperCouponConfig = loadPaperCouponConfigFile()
paperCouponInfo = loadPaperCouponConfigFile()
if len(paperCouponInfo) == 0:
    print('Failed to find any paper coupon candidates')
    sys.exit()
elif len(paperCouponInfo) > 1:
    print('Too many paper coupon candidates available: ' + str(paperCouponInfo.keys()))
    sys.exit()
paperfile = 'paper_coupon_helper_ids.txt'
if not os.path.isfile(paperfile):
    print('File missing: ' + paperfile)
paperChar = list(paperCouponInfo.keys())[0]

couponIDs = []
with open(os.path.join(os.getcwd(), paperfile), encoding='utf-8') as infile:
    lineNumber = 0
    for line in infile:
        line = line.strip()
        if not line.isdecimal():
            print('Invalid paper coupon input: ' + line)
            sys.exit()
        couponID = int(line)
        if couponID in couponIDs:
            print('Found at least one duplicate ID at line' + str(lineNumber) + ' : ' + str(couponID))
            sys.exit()
        couponIDs.append(couponID)
        lineNumber += 1
if len(couponIDs) == 0:
    # No mapping data available
    print("Failed to find any mapping data in mapping file " + paperfile)
    sys.exit()
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

# Finally update our config
paperCouponConfig[paperChar]['mapping'] = mapping
# Update our config file accordingly
saveJson(BotUtils.BotProperty.paperCouponExtraDataPath, paperCouponConfig)

sys.exit()
