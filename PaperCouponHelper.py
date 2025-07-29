import os
import traceback
from datetime import datetime
from typing import List

import Helper
from Helper import getTimezone, loadJson

from models.Coupon import Coupon

""" Helper for adding paper coupons to the coupon system. """


def main() -> List[Coupon]:
    extrainfomap = {
        "08.11.2024": {
            "thx": "Danke an die MyDealz User DerShitstorm und rote_rakete: mydealz.de/deals/burger-king-coupons-gultig-vom-sa-07092024-bis-fr-08112024-2418876#reply-49124677",
            "start_date": "07.09.2024"
        },
        "07.03.2025": {
            "thx": "Danke an die MyDealz User DerShitstorm für den hochauflösenden Scan, HalloTheEngineer für das Digitalisieren der Coupons und den Dealersteller, siehe: mydealz.de/deals/burger-king-coupons-gultig-vom-sa-11012025-bis-fr-07032025-2497319",
            "start_date": "11.01.2025"
        },
        "25.04.2025": {
            "thx": "Danke an den MyDealz User HalloTheEngineer für das Digitalisieren der Coupons und den Dealersteller, siehe: mydealz.de/deals/burger-king-coupons-gultig-vom-sa-08032025-bis-fr-25042025-2531675",
            "start_date": "08.03.2025"
        },
        "05.09.2025": {
            "thx": "Danke an den MyDealz User Mucho_Mitchi für das Bereitstellen der Coupons siehe: mydealz.de/deals/burger-king-aktuelle-coupons-0825-bei-burger-king-bundesweit-in-teilnehmenden-restaurants-gultig-bis-fr-05092025-2611425",
            "start_date": "08.03.2025"
        }
    }

    # Pfad zum Ordner "paper_coupon_data"
    folder_path = 'paper_coupon_data'

    # Liste für alle JSON-Dateien im Ordner
    json_files = [os.path.join(folder_path, file) for file in os.listdir(folder_path) if file.endswith('.json')]
    allresults = []
    # numberofExpectedCoupons = 48
    numberofExpectedCoupons = None
    if len(json_files) == 0:
        print("Found zero paper coupon json sources")
        return allresults

    for json_file in json_files:
        index = 0
        try:
            papercs = loadJson(json_file)
            expireDates = set()
            for paperc in papercs:
                expiredateStr = paperc['expireDate']
                expireDates.add(expiredateStr)
                extrainfo = extrainfomap.get(expiredateStr)
                start_dateStr = extrainfo['start_date'] if extrainfo is not None else None
                thankyouText = extrainfo['thx'] if extrainfo is not None else None
                coupon = Coupon.wrap(paperc)
                # Do some minor corrections
                coupon.title = coupon.title.replace("*", "")
                coupon.id = paperc['uniqueID']  # Set custom uniqueID otherwise couchDB will create one later -> This is not what we want to happen!!
                price = paperc['price']
                if price == 0:
                    coupon.price = None
                    coupon.staticReducedPercent = 50
                if start_dateStr is not None:
                    startdate = datetime.strptime(start_dateStr, '%d.%m.%Y').astimezone(getTimezone())
                    coupon.timestampStart = startdate.timestamp()
                else:
                    print(f"DEV U FORGOT TO ADD START_DATE FOR {expiredateStr}")
                expiredate = datetime.strptime(expiredateStr + " 23:59:59", '%d.%m.%Y %H:%M:%S').astimezone(getTimezone())
                coupon.timestampExpire = expiredate.timestamp()
                coupon.type = Helper.CouponType.PAPER
                if thankyouText is not None:
                    coupon.description = thankyouText
                else:
                    print(f"DEV U FORGOT PAPER THANK YOU FOR {expiredateStr}")
                # Only add coupon if it is valid
                if coupon.isExpired():
                    continue
                allresults.append(coupon)
                index += 1
            # Log inconsistent stuff
            if len(expireDates) != 1:
                print(f"Warnung: Ungleiche Ablaufdaten entdeckt! {expireDates}")
            if numberofExpectedCoupons is not None and len(papercs) != numberofExpectedCoupons:
                print(f"Warnung | Erwartete Anzahl Papiercoupons: {numberofExpectedCoupons} | Gefunden: {len(papercs)}")
        except:
            traceback.print_exc()
            print(f"Fehler beim Laden oder Verarbeiten der Papiercoupons {json_file} | Index {index}")
            continue
    """ Sort items and add each unique ID only once. Prefer the coupons that expire next.
     BK does sometimes prolong the expire date of a coupon so the same number can be in that list twice -> We want the currently valid one only.
     """
    allresults = sorted(allresults,
                        key=lambda x: 0 if x.timestampExpire is None else x.timestampExpire)
    coupon_ids = []
    coupon_plus = []
    finalResults = []
    """ Detect duplicates, log them and ignore them. """
    for coupon in allresults:
        if coupon.id in coupon_ids:
            print(f"Skipped duplicated paper coupon via ID: {coupon.id}")
            continue
        elif coupon.plu in coupon_plus:
            print(f"Skipped duplicated paper coupon via PLU: {coupon.id} | PLU {coupon.plu}")
            continue
        coupon_ids.append(coupon.id)
        coupon_plus.append(coupon.plu)
        finalResults.append(coupon)
    return finalResults


if __name__ == "__main__":
    main()


def getValidPaperCouponList() -> list:
    return main()


def getValidPaperCouponDict() -> dict:
    couponDict = {}
    resultlist = main()
    for coupon in resultlist:
        couponDict[coupon.id] = coupon
    return couponDict
