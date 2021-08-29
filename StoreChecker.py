import logging
import time
from json import loads

from hyper import HTTP20Connection

from Crawler import HEADERS

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)

""" Helper tools to find storeIDs of stores via which we can obtain a list of coupons via API. """
conn = HTTP20Connection('api.burgerking.de')
""" Returns List of stores """
conn.request("GET", '/api/o2uvrPdUY57J5WwYs6NtzZ2Knk7TnAUY/v2/de/de/stores/', headers=HEADERS)
stores = loads(conn.get_response().read())

storeIDs = []
""" Collect all stores """
for store in stores:
    properties = store['properties']
    if 'mobileOrdering' in properties:
        storeIDs.append(store['id'])

""" 2021-02-15: The first 3 stores that supported mobile ordering were: couponIDs = [682, 4108, 514] """
couponIDs = []
index = -1
printNewCoupons = False
for storeID in storeIDs:
    index += 1
    if index > 0:
        time.sleep(5)
    logging.info("Checking coupons of store " + str(index + 1) + " / " + str(len(storeIDs)) + " (id = " + str(storeID) + ")")
    conn = HTTP20Connection('mo.burgerking-app.eu')
    conn.request("GET", '/api/v2/stores/' + str(storeID) + '/menu', headers=HEADERS)
    apiResponse = loads(conn.get_response().read())
    """ E.g. response for storeIDs without mobileOrdering: {"errors":[{"code":19,"message":"Record not found.","details":{"TillsterStore":null}}]} """
    coupons = apiResponse.get("coupons")
    if coupons is None:
        continue
    for coupon in coupons:
        uniqueCouponID = coupon['promo_code']
        if uniqueCouponID not in couponIDs:
            couponIDs.append(uniqueCouponID)
            if printNewCoupons:
                print("Found couponID which is not present in coupons of first checked store: " + uniqueCouponID)
    # Print all new coupons we find after we've crawled the first store
    printNewCoupons = True

print("StoreChecker done")
