""" Helper functions for json returns via API call: https://mo.burgerking-app.eu/api/v2/stores/<storeID>/menu """
import re
from datetime import datetime

from Helper import sanitizeCouponTitle


def coupon2GetDatetimeFromString(dateStr: str) -> datetime:
    """ Parses e.g.: "2020-12-22T09:10:13+01:00" """
    return datetime.strptime(dateStr, '%Y-%m-%dT%H:%M:%S.%f%z')


def coupon2FixProductTitle(productTitle: str) -> str:
    """ Fixes- and sanitizes product titles e.g. "King Fries large" --> "Große KING Pommes". """
    newProductTitle = productTitle
    # Correct fries and dip e.g. "KING FRIES LARGE +2 DIPs" --> "GROßE KING POMMES + 2 DIPs"
    fries = re.compile(r"(?i)((\d\s*)?king\s*fries\s*(small|large|medium)).*").search(newProductTitle)
    if fries:
        productQuantity = fries.group(2)
        friesSize = fries.group(3).lower()
        if friesSize == 'small':
            friesSizeCorrected = 'kleine'
        elif friesSize == 'medium':
            friesSizeCorrected = 'mittlere'
        else:
            friesSizeCorrected = 'große'
        improvedTitle = friesSizeCorrected + " KING POMMES"
        if productQuantity is not None:
            improvedTitle = productQuantity + ' ' + improvedTitle
        newProductTitle = newProductTitle.replace(fries.group(1), improvedTitle)
    # Other products can also contain dips --> Make sure to correct all
    dipQuantifier = re.compile(r"(?i)(\s*?\+\s*(\d+)\s*(DIPs?))").search(productTitle)
    if dipQuantifier:
        newDipQuantifier = ' + ' + dipQuantifier.group(2) + ' ' + dipQuantifier.group(3)
        newProductTitle = newProductTitle.replace(dipQuantifier.group(0), newDipQuantifier)
    # Remove things we don't need!
    forPriceOfOne = re.compile(r"(?i)\s*?ZUM\s*PREIS\s*VON\s*EINER(\s*\d+ER\s*PORTION)?").search(newProductTitle)
    if forPriceOfOne:
        newProductTitle = newProductTitle.replace(forPriceOfOne.group(0), '')
    buyOneGetOneFree = re.compile(r"(?i)[\s-]*?Buy\s*1\s*get\s*1\s*free").search(newProductTitle)
    if buyOneGetOneFree:
        newProductTitle = newProductTitle.replace(buyOneGetOneFree.group(0), '')
    # Where is the point? Yeah the point is sometimes missing which is why we have to fix it...
    whopperJrFix = re.compile(r"(?i)((\d+)\s*)?WHOPPER\s*JR\.?").search(newProductTitle)
    if whopperJrFix:
        whopperJrQuantifier = whopperJrFix.group(2)
        newWhopper = "WHOPPER Jr."
        if whopperJrQuantifier is not None:
            newWhopper = whopperJrQuantifier + " " + newWhopper
        newProductTitle = newProductTitle.replace(whopperJrFix.group(0), newWhopper)
    """ 
    Special case: "2 LONG TEXAS BBQ 31661" --> "2 Long Texas BBQ"
    Seriously BK how did that shit make it into your DB??? """
    longTexasFix = re.compile(r"(?i)((\d+)\s*)?LONG\s*TEXAS\s*BBQ\s*31611").search(newProductTitle)
    if longTexasFix:
        longTexasQuantifier = longTexasFix.group(2)
        newLongTexasBBQ = "Long Texas BBQ"
        if longTexasQuantifier is not None:
            newLongTexasBBQ = longTexasQuantifier + " " + longTexasQuantifier
        newProductTitle = newProductTitle.replace(longTexasFix.group(0), newLongTexasBBQ)
    # Fix nuggets e.g. "KING NUGGETS 6 STK." --> "6 KING NUGGETS"
    nuggetsFix1 = re.compile(r"(?i)KING\s*NUGGETS(?:\s*®)?\s*(\d+)\s*STK\s*\.?").search(newProductTitle)
    if nuggetsFix1:
        newProductTitle = newProductTitle.replace(nuggetsFix1.group(0), nuggetsFix1.group(1) + " Chicken Nuggets")
    # Fix nuggets version 2 e.g. "CHICKEN NUGGETS (6)" --> "6 KING NUGGETS"
    nuggetsFix2 = re.compile(r"(?i)CHICKEN\s*NUGGETS\s*\((\d+)\)").search(newProductTitle)
    if nuggetsFix2:
        newNuggets2 = nuggetsFix2.group(1) + " Chicken Nuggets"
        newProductTitle = newProductTitle.replace(nuggetsFix2.group(0), newNuggets2)
    cocaColaMediumFix = re.compile(r"(?i)Coca[\s-]*Cola\s*®?\s*medium").search(newProductTitle)
    if cocaColaMediumFix:
        newProductTitle = newProductTitle.replace(cocaColaMediumFix.group(0), '0,4L Coca-Cola')

    newProductTitle = sanitizeCouponTitle(newProductTitle)
    return newProductTitle
