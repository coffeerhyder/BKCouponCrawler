import logging
import os
from datetime import datetime

import BotUtils
from Helper import saveJson, getTimezone, loadJson

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)

""" Helper to complete config file with data from 'paper_coupon_helper_ids.txt'. """


def main():
    activePaperCouponInfo = getActivePaperCouponInfo()
    if len(activePaperCouponInfo) == 0:
        # logging.info("Failed to find any currently valid paper coupon candidates --> Cannot add additional information")
        return
    paperCouponConfig = loadPaperCouponConfigFile()
    for paperIdentifier in activePaperCouponInfo.keys():
        filepath = 'paper_coupon_data/paper_coupon_helper_ids_' + paperIdentifier + '.txt'
        if not os.path.isfile(filepath):
            # Shouldn't happen but it's not too fatal - maybe there are just no paper coupons available at this moment.
            logging.warning('No file available for paper coupon char ' + paperIdentifier + ' | ' + filepath)
            continue
        mapping = {}
        if paperIdentifier == 'NOCHAR':
            # Build mapping for currently valid coupons without char
            couponIDs = []
            with open(os.path.join(os.getcwd(), filepath), encoding='utf-8') as infile:
                lineNumber = 0
                for line in infile:
                    line = line.strip()
                    couponInfo = line.split(':')
                    couponIDStr = couponInfo[0]
                    if not couponIDStr.isdecimal():
                        raise Exception('Invalid paper coupon input: ' + line)
                    if couponIDStr in couponIDs:
                        logging.warning('Found at least one duplicate ID at line' + str(lineNumber) + ' : ' + couponIDStr)
                        continue
                    mapping[couponIDStr] = couponInfo[1]
                    lineNumber += 1
        else:
            couponIDs = []
            with open(os.path.join(os.getcwd(), filepath), encoding='utf-8') as infile:
                lineNumber = 0
                for line in infile:
                    line = line.strip()
                    if not line.isdecimal():
                        raise Exception('Invalid paper coupon input: ' + line)
                    couponIDStr = line
                    if line in couponIDs:
                        logging.warning('Found at least one duplicate ID at line' + str(lineNumber) + ' : ' + couponIDStr)
                        continue
                    couponIDs.append(couponIDStr)
                    lineNumber += 1
            if len(couponIDs) == 0:
                raise Exception("Failed to find any mapping data in mapping file " + filepath)
            # Validate array size
            if len(couponIDs) < 47 or len(couponIDs) > 48:
                logging.warning('Array length mismatch: ' + str(len(couponIDs)))
            # Build mapping
            number = 1
            for couponIDStr in couponIDs:
                # Correct number: Assume than when only 47 items are given, the payback code is missing -> That is usually number 47
                if len(couponIDs) == 47 and number == 47:
                    number = 48
                mapping[couponIDStr] = paperIdentifier + str(number)
                number += 1
        # print('Mapping result = ' + str(mapping))

        # Finally update our config
        paperCouponConfig.setdefault(paperIdentifier, {})['mapping'] = mapping

    # paperCouponConfig[paperChar]['mapping'] = mapping
    # Update our config file accordingly
    saveJson(BotUtils.BotProperty.paperCouponExtraDataPath, paperCouponConfig)


if __name__ == "__main__":
    main()


def getActivePaperCouponInfo() -> dict:
    paperCouponInfo = {}
    """ Load file which contains some extra data which can be useful to correctly determine the "CouponSource" and expire date of paper coupons. """
    for paperIdentifier, paperData in loadPaperCouponConfigFile().items():
        validuntil = datetime.strptime(paperData['expire_date'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S').astimezone(getTimezone()).timestamp()
        if validuntil > datetime.now().timestamp():
            newPaperData = paperData
            newPaperData['expire_timestamp'] = validuntil
            paperCouponInfo[paperIdentifier] = newPaperData
    return paperCouponInfo


def loadPaperCouponConfigFile() -> dict:
    return loadJson(BotUtils.BotProperty.paperCouponExtraDataPath)