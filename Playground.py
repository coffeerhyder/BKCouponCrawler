from barcode import EAN13
from barcode.writer import ImageWriter
from furl import furl, urllib
from urllib.parse import urlparse, parse_qs

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

# Crawler example code for readme.md

# crawler = BKCrawler()
""" Nur für den Bot geeignete Coupons crawlen oder alle?
 Wenn du den Bot 'produktiv' einsetzt, solltest du alle ressourcenhungrigen Schalter deaktivieren (= default). """
# crawler.setCrawlOnlyBotCompatibleCoupons(True)
# History Datenbank aufbauen z.B. zur späteren Auswertung?
# crawler.setKeepHistory(True)
# CSV Export bei jedem Crawlvorgang (de-)aktivieren
# crawler.setExportCSVs(False)
# Coupons crawlen
# crawler.crawlAndProcessData()
# Coupons filtern und sortieren Bsp. 1: Nur aktive, die der Bot handlen kann sortiert nach Typ, Menü, Preis
# activeCoupons = crawler.filterCoupons(CouponFilter(activeOnly=True, allowedCouponTypes=BotAllowedCouponTypes, sortMode=CouponSortMode.SOURCE_MENU_PRICE))
# Coupons filtern und sortieren Bsp. 1: Nur aktive, nur App Coupons, mit und ohne Menü, nur versteckte, sortiert nach Preis
# activeCoupons = crawler.filterCoupons(CouponFilter(sortMode=CouponSortMode.PRICE, allowedCouponTypes=CouponType.APP, containsFriesAndCoke=None, isHidden=True))
# crawler.addExtraCoupons(crawledCouponsDict={}, immediatelyAddToDB=False)


# python-barcode tests
# rv = BytesIO()
# EAN13(str(240000902922), writer=ImageWriter()).write(rv)
#
# with open('test.png', 'wb') as f:
#     EAN13('240000902922', writer=ImageWriter()).write(f)

f = open('somefile.png', 'wb')
ean = EAN13(ean='100000011111', writer=ImageWriter())
ean.save(filename='test22.png', options={'foreground': 'black', 'text': 'Test'})

