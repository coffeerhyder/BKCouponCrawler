import logging
import os
from datetime import datetime

import BotUtils
from Helper import saveJson, loadPaperCouponConfigFile, getTimezone

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)

""" Helper to complete config file with data from 'paper_coupon_helper_ids.txt'. """


def main():
    activePaperCouponInfo = getActivePaperCouponInfo2()
    if len(activePaperCouponInfo) == 0:
        raise Exception("Failed to find any paper coupon candidates")
    elif len(activePaperCouponInfo) > 1:
        raise Exception("Too many paper coupon candidates available: " + str(activePaperCouponInfo.keys()))
    paperfile = 'paper_coupon_helper_ids.txt'
    if not os.path.isfile(paperfile):
        # Shouldn't happen but it's not too fatal - maybe there are just no paper coupons available at this moment.
        logging.warning('File missing: ' + paperfile)
        return

    paperChar = list(activePaperCouponInfo.keys())[0]
    couponIDs = []
    with open(os.path.join(os.getcwd(), paperfile), encoding='utf-8') as infile:
        lineNumber = 0
        for line in infile:
            line = line.strip()
            if not line.isdecimal():
                raise Exception('Invalid paper coupon input: ' + line)
            couponID = int(line)
            if couponID in couponIDs:
                raise Exception('Found at least one duplicate ID at line' + str(lineNumber) + ' : ' + str(couponID))
            couponIDs.append(couponID)
            lineNumber += 1
    if len(couponIDs) == 0:
        # No mapping data available
        raise Exception("Failed to find any mapping data in mapping file " + paperfile)
    # Validate array size
    if len(couponIDs) < 47 or len(couponIDs) > 48:
        logging.warning('Array length mismatch: ' + str(len(couponIDs)))
    # Build mapping
    mapping = {}
    number = 1
    for couponID in couponIDs:
        # Correct number: Assume than when only 47 items are given, the payback code is missing -> That is usually number 47
        if len(couponIDs) == 47 and number == 47:
            number = 48
        mapping[couponID] = paperChar + str(number)
        number += 1
    # print('Mapping result = ' + str(mapping))

    # Finally update our config
    paperCouponConfig = loadPaperCouponConfigFile()
    paperCouponConfig.setdefault(paperChar, {})['mapping'] = mapping
    # paperCouponConfig[paperChar]['mapping'] = mapping
    # Update our config file accordingly
    saveJson(BotUtils.BotProperty.paperCouponExtraDataPath, paperCouponConfig)


if __name__ == "__main__":
    main()


def getActivePaperCouponInfo2() -> dict:
    paperCouponInfo = {}
    """ Load file which contains some extra data which can be useful to correctly determine the "CouponSource" and expire date of paper coupons. """
    for paperChar, paperData in loadPaperCouponConfigFile().items():
        validuntil = datetime.strptime(paperData['expire_date'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S').astimezone(getTimezone()).timestamp()
        if validuntil > datetime.now().timestamp():
            newPaperData = paperData
            newPaperData['expire_timestamp'] = validuntil
            paperCouponInfo[paperChar] = newPaperData
    return paperCouponInfo

