# import qrcode
#
# qr = qrcode.QRCode(
#     version=1,
#     border=8
# )
# qr.add_data("1234")
# """ 2021-01-25: Use the same color they're using in their app. """
# img = qr.make_image(fill_color="#4A1E0D", back_color="white")
# test1 = border=4
# test2 = border=10 -> Looks good
# test3 = border=8 -> Looks also good (?)
# img.save("test3.png")

from furl import furl, urllib
from urllib.parse import urlparse, parse_qs

from Crawler import BKCrawler
from UtilsCouponsDB import Coupon, InfoEntry

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

test = Coupon(plu='', id="")
test.plu = "44"

print("plu=" + test.plu)
print("gettest=" + str(test.data.get(Coupon.priceCompare.name, 1337.77)))
print("varTest = " + test.data.get(Coupon.plu.name, "123456"))

array1 = [1, 2, 3]
array2 = [4, 5, 6]
array3 = array1 + array2
print(str(array3))


infoDoc = InfoEntry(messageIDsToDelete=[1, 2, 3])

print(str(infoDoc.messageIDsToDelete))

# Crawler example code for readme.md

crawler = BKCrawler()
""" Nur für den Bot geeignete Coupons crawlen oder alle?
 Wenn du den Bot 'produktiv' einsetzt, solltest du alle ressourcenhungrigen Schalter deaktivieren (= default). """
crawler.setCrawlOnlyBotCompatibleCoupons(True)
# History Datenbank aufbauen z.B. zur späteren Auswertung?
crawler.setKeepHistory(True)
# CSV Export bei jedem Crawlvorgang (de-)aktivieren
crawler.setExportCSVs(False)
# Coupons crawlen
# crawler.crawlAndProcessData()
# Coupons filtern und sortieren Bsp. 1: Nur aktive, die der Bot handlen kann sortiert nach Typ, Menü, Preis
# activeCoupons = crawler.filterCoupons(CouponFilter(activeOnly=True, allowedCouponSources=BotAllowedCouponSources, sortMode=CouponSortMode.SOURCE_MENU_PRICE))
# Coupons filtern und sortieren Bsp. 1: Nur aktive, nur App Coupons, mit und ohne Menü, nur versteckte, sortiert nach Preis
# activeCoupons = crawler.filterCoupons(CouponFilter(sortMode=CouponSortMode.PRICE, allowedCouponSources=CouponSource.APP, containsFriesAndCoke=None, isHidden=True))
# crawler.addExtraCoupons(crawledCouponsDict={}, immediatelyAddToDB=False)
