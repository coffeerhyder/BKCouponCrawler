import logging
import re
from datetime import datetime
from typing import Union

from Helper import getDatetimeFromString, getDatetimeFromString2, getCurrentDate

from BaseUtils import logging

""" Class to work with json objects returned in array "coupons" of App API request. """


def couponGetUniqueCouponID(coupon: dict) -> Union[str, None]:
    for barcode in coupon['barcodes']:
        if barcode['type'] == 'QR':
            return barcode['value']
    return None


def couponGetTitleFull(coupon: dict) -> str:
    """ Generate real title e.g. often title == '2 Big KING XXL' and subline = '+ mittlere KING Pommes + 0,4 L Coca-Cola®' """
    title = coupon['title']
    subline = coupon['subline']
    useNewHandling = False
    if useNewHandling:
        """ 2021-08-04: New experimental handling to auto-detect whenever our title consists of title + subline, only title or only subline
        Conclusion: auto-detection is possible but not easy. We'd have to work with some kind of whitelist leaving the possibility of currupted coupon titles.
        At this moment I rather prefer the other handling because if that fails our product titles might be unnecessarily long but at least they will always contain all required information.
         """
        if subline is not None and len(subline) > 0:
            # Subline will start with "+ " most of all times but sometimes also with " + "
            subline = subline.strip()
            if subline.startswith('+'):
                # subline + title
                couponTitleFull = title + ' ' + subline
            else:
                # Only subline
                logging.info("Auto-detected only-subline-title: " + str(coupon["id"]) + " | subline: " + subline + " | title: " + title)
                # 2021-08-04: At this moment this would only fail for one coupon with subline "Vanilla, Chocolate oder Strawberry"
                couponTitleFull = subline
        else:
            # Only title
            couponTitleFull = title
    else:
        """ 2021-04-13: "Fix" titles of some new 'hidden' coupons (App works differently, we need clean titles for our DB and the bot!)!"""
        fixPreferSublineAsTitle = re.search(r'(?i)^\s*(?:Tausche|Plus)\s*(.+)', title)
        # 2021-07-07
        fixPreferSublineAsTitle2 = re.search(r'(?i)^Mach\'s\s*groß\s*zum\s*King\s*Menü$', title)
        # 2021-08-03
        fixPreferSublineAsTitle3 = re.search(r'(?i)^mit Käse$', title)
        # 2022-04-23
        fixPreferSublineAsTitle4 = re.search(r'(?i)^Im King Men([uü])$', title)
        fixPlantBaseRubbish = re.search(r'(?i)^\*Pflanzlich basierte Geflügelalternative$', subline)
        if fixPreferSublineAsTitle:
            addedOrSwappedProducts = fixPreferSublineAsTitle.group(1)
            if addedOrSwappedProducts not in subline:
                logging.info("Product(s) inside title of supposedly hidden coupon are not contained in subline: " + str(coupon["id"]) + " | subline: " + subline + " | Potentially missing product: " + addedOrSwappedProducts)
            couponTitleFull = subline
        elif fixPreferSublineAsTitle2:
            couponTitleFull = subline
        elif fixPreferSublineAsTitle3:
            couponTitleFull = subline
        elif fixPreferSublineAsTitle4:
            couponTitleFull = subline
        elif re.search(r'(?i)^\s*Im\s*großen\s*King\s*Men[uü]\s*$', title):  # 2021-04-13: More title corrections... (in this case, all info we need is in subline)
            couponTitleFull = subline
        elif fixPlantBaseRubbish:
            fixPlantBasedNuggets = re.search(r'^\d+\s*Plant[\s-]*based\*\s*Nuggets$', title)
            if fixPlantBasedNuggets:
                # 2021-06-10: "4 Plant-based* Nuggets" --> "4 Plant-based Nuggets"
                couponTitleFull = title.replace("*", "")
            else:
                couponTitleFull = title
        else:
            couponTitleFull = title
            # Subline will start with "+ " most of all times but sometimes also with " + "
            if subline is not None and len(subline) > 0:
                subline = subline.strip()
                if not subline.startswith('+'):
                    logging.info("Possibly subline which should be set as title: " + str(coupon["id"]) + " | " + subline)
                couponTitleFull += ' ' + subline
    return couponTitleFull


def couponGetExpireDateFromFootnote(coupon) -> Union[str, None]:
    footnote = coupon.get('footnote')
    if footnote is not None:
        matchO = re.search(r'(?i)Abgabe\s*bis\s*(\d{1,2}\.\d{1,2}\.\d{4})', footnote)
        if matchO is not None:
            return matchO.group(1)
    return None


def couponIsValid(coupon) -> bool:
    expireDatetime = couponGetExpireDatetime(coupon)
    return expireDatetime == -1 or expireDatetime > getCurrentDate()


def couponGetStartTimestamp(coupon) -> float:
    startDatePreciseStr = coupon.get('start_date')
    if startDatePreciseStr is None:
        return -1
    else:
        return getDatetimeFromString(startDatePreciseStr).timestamp()


def couponGetExpireDatetime(coupon) -> Union[datetime, None]:
    expireDatePreciseStr = coupon.get('expiration_date')
    expireDateFromFootnoteStr = couponGetExpireDateFromFootnote(coupon)
    if expireDatePreciseStr is None and expireDateFromFootnoteStr is None:
        return None
    expireTimestampFromFootnote = 0
    expireTimestampPrecise = 0
    if expireDatePreciseStr is not None:
        expireTimestampPrecise = getDatetimeFromString(expireDatePreciseStr)
    if expireDateFromFootnoteStr is not None:
        # Assume they include this day and mean the end of this day
        expireDateFromFootnoteStr += ' 23:59+02:00'
        expireTimestampFromFootnote = getDatetimeFromString2(expireDateFromFootnoteStr)
    # Return highest timestamp -> BK's database is a mess thus we have to find the highest one here on our own.
    if expireTimestampPrecise >= expireTimestampFromFootnote:
        return expireTimestampPrecise
    else:
        return expireTimestampFromFootnote
