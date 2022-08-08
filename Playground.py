from datetime import datetime

from barcode import EAN13
from barcode.writer import ImageWriter
from furl import furl, urllib
from urllib.parse import urlparse, parse_qs

import httpx

from Helper import getTimezone
from UtilsCouponsDB import CouponViews

url = "?action=displaycoupons&which=favorites&page=3"
o = urlparse(url)
query = parse_qs(o.query)

print(o.query)

print(o.query)
print(query["which"])

urlquery = furl(url)
print(urlquery.args["action"])

quotedStr = urllib.parse.quote(url)

print(quotedStr)

urlquery.args['page'] = 3
print("furl url: " + urlquery.url)


# python-barcode tests
# rv = BytesIO()
# EAN13(str(240000902922), writer=ImageWriter()).write(rv)
#
# with open('test.png', 'wb') as f:
#     EAN13('240000902922', writer=ImageWriter()).write(f)

# f = open('somefile.png', 'wb')
ean = EAN13(ean='100000011111', writer=ImageWriter())
# ean.save(filename='test22.png', options={'foreground': 'black', 'text': 'Test'})

allViews = CouponViews.__dict__

print(str(CouponViews.__dict__))

# 2022-08-08: New API endpoint tests
data = b"""{"operationName":"evaluateAllUserOffers","variables":{"locale":"de","platform":"web","serviceMode":"TAKEOUT","redeemedOn":"2022-08-08T22:43:14.331+02:00","storeId":null},"query":"query evaluateAllUserOffers($locale: Locale, $platform: Platform, $redeemedOn: String!, $serviceMode: ServiceMode, $storeId: String) {\n  evaluateAllUserOffers(locale: $locale, platform: $platform, redeemedOn: $redeemedOn, serviceMode: $serviceMode, storeId: $storeId) {\n    offersFeedback {\n      ...OfferFeedbackEntryFragment\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment OfferFeedbackEntryFragment on CouponUserOffersFeedbackEntry {\n  cartEntry {\n    cartId: lineId\n    __typename\n  }\n  _id: couponId\n  tokenId\n  couponId\n  offerDetails\n  offerState\n  offerVariables {\n    key\n    type\n    value\n    __typename\n  }\n  rank\n  redemptionEligibility {\n    isRedeemable\n    isValid\n    evaluationFeedback {\n      code\n      condition\n      message\n      redeemableForSeconds\n      redeemableInSeconds\n      ruleSetType\n      sanityId\n      __typename\n    }\n    validationErrors {\n      code\n      message\n      ruleSetType\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n"}"""
json = {"operationName": "evaluateAllUserOffers",
        "variables": {"locale": "de", "platform": "web", "serviceMode": "TAKEOUT", "redeemedOn": "2022-08-08T22:43:14.331+02:00", "storeId": None},
        "query": "query evaluateAllUserOffers($locale: Locale, $platform: Platform, $redeemedOn: String!, $serviceMode: ServiceMode, $storeId: String) {\n  evaluateAllUserOffers(locale: $locale, platform: $platform, redeemedOn: $redeemedOn, serviceMode: $serviceMode, storeId: $storeId) {\n    offersFeedback {\n      ...OfferFeedbackEntryFragment\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment OfferFeedbackEntryFragment on CouponUserOffersFeedbackEntry {\n  cartEntry {\n    cartId: lineId\n    __typename\n  }\n  _id: couponId\n  tokenId\n  couponId\n  offerDetails\n  offerState\n  offerVariables {\n    key\n    type\n    value\n    __typename\n  }\n  rank\n  redemptionEligibility {\n    isRedeemable\n    isValid\n    evaluationFeedback {\n      code\n      condition\n      message\n      redeemableForSeconds\n      redeemableInSeconds\n      ruleSetType\n      sanityId\n      __typename\n    }\n    validationErrors {\n      code\n      message\n      ruleSetType\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36",
           "Origin": "https://www.burgerking.de",
           "Content-Type": "application/json",
           "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"99\", \"Google Chrome\";v=\"99\"",
           "sec-ch-ua-mobile": "?0",
           "sec-ch-ua-platform": "\"Windows\"",
           "sec-fetch-dest": "empty",
           "sec-fetch-mode": "cors",
           "sec-fetch-site": "cross-site",
           "x-ui-language": "de",
           "x-ui-platform": "web",
           "x-ui-region": "DE"}
# r = httpx.post('https://euc1-prod-bk.rbictg.com/graphql', json=json, headers=HEADERS)
# print(r.text)

datetimetest = datetime.strptime('2022-07-18T21:59:00.000Z', '%Y-%m-%dT%H:%M:%S.%fZ')
print('datetimemillis = ' + str(datetimetest.timestamp()))
date = datetime.now(getTimezone())
utcOffset = date.strftime('%z')
utcOffsetFormatted = utcOffset[:3] + ':' + utcOffset[3:]
dateformatted = date.strftime('%Y-%m-%dT%H:%M:%S.%f') + utcOffsetFormatted
print('datetimeformattest: ' + dateformatted)
