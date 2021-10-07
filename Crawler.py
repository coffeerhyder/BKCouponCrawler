import csv
import logging
import traceback
from typing import List, Union, Dict

import qrcode
import requests
from couchdb import Document, Database
from hyper import HTTP20Connection  # we're using hyper instead of requests because of its' HTTP/2.0 capability

import couchdb
from json import loads

from BotUtils import Config
from Helper import *
from Helper import getPathImagesOffers, getPathImagesProducts, couponTitleContainsFriesOrCoke, isCouponShortPLU, isValidImageFile
from Models import CouponFilter
from UtilsCoupons2 import coupon2GetDatetimeFromString, coupon2FixProductTitle
from UtilsOffers import offerGetImagePath, offerIsValid
from UtilsCoupons import couponGetUniqueCouponID, couponGetTitleFull, \
    couponGetExpireDatetime, couponIsValid, couponGetStartTimestamp
from UtilsCouponsDB import couponDBIsValid, couponDBGetUniqueCouponID, couponDBGetComparableValue, \
    couponDBGetExpireDateFormatted, couponDBGetPriceFormatted, couponDBGetImagePathQR, isValidBotCoupon, getImageBasePath, \
    couponDBGetImagePath, Coupon, User, InfoEntry, CouponSortMode, couponDBGetTitleShortened
from CouponCategory import CouponSource, BotAllowedCouponSources

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
HEADERS = {"User-Agent": "BurgerKing/6.7.0 (de.burgerking.kingfinder; build:432; Android 8.0.0) okhttp/3.12.3"}
""" Enable this to crawl from localhost instead of API. Useful if there is a lot of testing to do! """
DEBUGCRAWLER = False


class UserFavorites:
    """ Small helper class """
    def __init__(self, favoritesAvailable: Union[List[Coupon], None] = None, favoritesUnavailable: Union[List[Coupon], None] = None):
        # Do not allow null values when arrays are expected. This makes it easier to work with this.
        if favoritesAvailable is None:
            favoritesAvailable = []
        if favoritesUnavailable is None:
            favoritesUnavailable = []
        self.couponsAvailable = favoritesAvailable
        self.couponsUnavailable = favoritesUnavailable

    def getUnavailableFavoritesText(self) -> Union[str, None]:
        if len(self.couponsUnavailable) == 0:
            return None
        else:
            unavailableFavoritesText = ''
            for coupon in self.couponsUnavailable:
                if len(unavailableFavoritesText) > 0:
                    unavailableFavoritesText += '\n'
                unavailableFavoritesText += couponDBGetUniqueCouponID(coupon) + ' | ' + couponDBGetTitleShortened(coupon)
                if coupon.price is not None:
                    unavailableFavoritesText += ' | ' + couponDBGetPriceFormatted(coupon)
            return unavailableFavoritesText


class BKCrawler:

    def __init__(self):
        self.cfg = loadConfig()
        if self.cfg is None or self.cfg.get(Config.DB_URL) is None:
            raise Exception('Broken or missing config')
        # Init DB
        self.couchdb = couchdb.Server(self.cfg[Config.DB_URL])
        self.cachedAvailableCouponSources = {}
        self.cachedHasHiddenAppCouponsAvailable = False
        self.keepHistory = False
        self.crawlOnlyBotCompatibleCoupons = True
        self.storeCouponAPIDataAsJson = False
        self.exportCSVs = False
        # Create required DBs
        if DATABASES.INFO_DB not in self.couchdb:
            infoDB = self.couchdb.create(DATABASES.INFO_DB)
        else:
            infoDB = self.couchdb[DATABASES.INFO_DB]
        # Special case: We not only need to make sure that this DB exists but also need to add this special doc
        if DATABASES.INFO_DB not in infoDB:
            infoDoc = InfoEntry(id=DATABASES.INFO_DB)
            infoDoc.store(self.couchdb[DATABASES.INFO_DB])
        if DATABASES.TELEGRAM_USERS not in self.couchdb:
            self.couchdb.create(DATABASES.TELEGRAM_USERS)
        if DATABASES.COUPONS not in self.couchdb:
            self.couchdb.create(DATABASES.COUPONS)
        if DATABASES.OFFERS not in self.couchdb:
            self.couchdb.create(DATABASES.OFFERS)
        if DATABASES.COUPONS_HISTORY not in self.couchdb:
            self.couchdb.create(DATABASES.COUPONS_HISTORY)
        if DATABASES.OFFERS_HISTORY not in self.couchdb:
            self.couchdb.create(DATABASES.OFFERS_HISTORY)
        if DATABASES.PRODUCTS not in self.couchdb:
            self.couchdb.create(DATABASES.PRODUCTS)
        if DATABASES.PRODUCTS_HISTORY not in self.couchdb:
            self.couchdb.create(DATABASES.PRODUCTS_HISTORY)
        if DATABASES.PRODUCTS2_HISTORY not in self.couchdb:
            self.couchdb.create(DATABASES.PRODUCTS2_HISTORY)
        if DATABASES.COUPONS2_HISTORY not in self.couchdb:
            self.couchdb.create(DATABASES.COUPONS2_HISTORY)
        if DATABASES.TELEGRAM_CHANNEL not in self.couchdb:
            self.couchdb.create(DATABASES.TELEGRAM_CHANNEL)
        # Create required folders
        if not os.path.exists(getImageBasePath()):
            os.makedirs(getImageBasePath())
        if not os.path.exists(getPathImagesOffers()):
            os.makedirs(getPathImagesOffers())
        if not os.path.exists(getPathImagesProducts()):
            os.makedirs(getPathImagesProducts())
        # Make sure that our cache gets filled on init
        self.updateCache()

    def getServer(self):
        return self.couchdb

    def setKeepHistory(self, keepHistory: bool):
        """ Enable this if you want the crawler to maintain a history of past coupons/offers and update it on every crawl process. """
        self.keepHistory = keepHistory

    def setCrawlOnlyBotCompatibleCoupons(self, crawlOnlyBotCompatibleCoupons: bool):
        """ Enabling this will speedup the crawl process!
         Disable this if you want the crawler to crawl all items -> Will need some more time! """
        self.crawlOnlyBotCompatibleCoupons = crawlOnlyBotCompatibleCoupons

    def setStoreCouponAPIDataAsJson(self, storeCouponAPIDataAsJson: bool):
        """ If enabled, all obtained API json responses will be saved into json files on each run. """
        self.storeCouponAPIDataAsJson = storeCouponAPIDataAsJson

    def setExportCSVs(self, exportCSVs: bool):
        """ If enabled, CSV file(s) will be exported into the "crawler" folder on each full crawl run. """
        self.exportCSVs = exportCSVs

    def crawl(self):
        """ Updates DB with new coupons & offers. """
        """ Using public API: https://gist.github.com/max1220/7f2f65be4381bc0878e64a985fd71da4 """
        if DEBUGCRAWLER:
            apiResponse = loads(requests.get('http://localhost/bkcrawler/coupons1.json').text)
        else:
            conn = HTTP20Connection('mo.burgerking-app.eu')
            conn.request("GET", '/api/v2/coupons', headers=HEADERS)
            apiResponse = loads(conn.get_response().read())
            if self.storeCouponAPIDataAsJson:
                # Save API response so we can easily use this data for local testing later on.
                with open('crawler/coupons1.json', 'w') as outfile:
                    json.dump(apiResponse, outfile)
        self.crawlProcessCoupons(apiResponse)
        self.crawlProcessOffers(apiResponse)
        logging.info('App API Crawling done')
        self.crawlProcessCoupons2()
        # self.crawlProducts()

    def downloadProductiveCouponDBImagesAndCreateQRCodes(self):
        """ Downloads coupons images and generates QR codes for current productive coupon DB. """
        timestampStart = datetime.now().timestamp()
        couponDB = self.getCouponDB()
        numberofDownloadedImages = 0
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            if downloadImageIfNonExistant(coupon.imageURL, couponDBGetImagePath(coupon)):
                numberofDownloadedImages += 1
            generateQRImageIfNonExistant(uniqueCouponID, couponDBGetImagePathQR(coupon))
        if numberofDownloadedImages > 0:
            logging.info("Number of coupon images downloaded: " + str(numberofDownloadedImages))
            logging.info("Download image files duration: " + getFormattedPassedTime(timestampStart))

    def migrateDBs(self):
        """ Migrate DBs from old to new version - leave this function empty if there is nothing to migrate. """
        # logging.info("Migrating DBs...")
        # logging.info("Migrate DBs done")
        pass

    def crawlAndProcessData(self):
        """ One function that does it all! Launch this every time you run the crawler. """
        # Use last state so we can compare them against the new data
        timestampStart = datetime.now().timestamp()
        self.migrateDBs()
        # Get all coupons, also invalid ones (they could become valid again after crawling so we need them in this list otherwise such coupons could be tagged as new although they are not!)
        lastCoupons = self.filterCoupons(CouponFilter(activeOnly=False))
        self.crawl()
        if self.exportCSVs:
            self.couponCsvExport()
            self.couponCsvExport2()
        self.updateIsNewFlags(lastCoupons)
        self.addSpecialCoupons()
        self.downloadProductiveCouponDBImagesAndCreateQRCodes()
        # self.checkProductiveCouponsDBImagesIntegrity()
        # self.checkProductiveOffersDBImagesIntegrity()
        self.checkProductiveCouponDBForAnomalies()
        self.updateCache()
        logging.info("Total crawl duration: " + getFormattedPassedTime(timestampStart))

    def updateIsNewFlags(self, lastCoupons: dict):
        """ Tags coupons as "NEW" if they haven't been in the DB before by comparing current DB to the last state before crawling. """
        logging.info("Updating IS_NEW flags...")
        if len(lastCoupons) == 0:
            # Edge case e.g. first start of the crawler -> We do not want to flag all items as new!
            logging.info("DB was empty before --> Not setting any IS_NEW flags")
            return
        couponDB = self.getCouponDB()
        numberofCouponsNewFlagRemoved = 0
        newCouponIDs = []
        dbUpdates = []
        for couponID in couponDB:
            coupon = Coupon.load(couponDB, couponID)
            if coupon.isNew:
                # Remove IS_NEW flag if it has been set before!
                coupon.isNew = False
                dbUpdates.append(coupon)
                numberofCouponsNewFlagRemoved += 1
            elif self.crawlOnlyBotCompatibleCoupons and couponID not in lastCoupons:
                newCouponIDs.append(couponID)
                coupon.isNew = True
                dbUpdates.append(coupon)
            elif not self.crawlOnlyBotCompatibleCoupons and couponDBIsValid(coupon) and (couponID not in lastCoupons or not couponDBIsValid(lastCoupons[couponID])):
                newCouponIDs.append(couponID)
                coupon.isNew = True
                dbUpdates.append(coupon)
            else:
                # Coupon is not new isNew default == False
                pass
        # Update DB if needed
        if len(dbUpdates) > 0:
            couponDB.update(dbUpdates)
            if len(newCouponIDs) > 0:
                logging.info(str(len(newCouponIDs)) + " IS_NEW flags were issued: " + str(newCouponIDs))
            if numberofCouponsNewFlagRemoved > 0:
                logging.info(str(numberofCouponsNewFlagRemoved) + " IS_NEW flags were removed")
        # Update timestamp of last complete run.
        infoDatabase = self.couchdb[DATABASES.INFO_DB]
        infoDBDoc = InfoEntry.load(infoDatabase, DATABASES.INFO_DB)
        infoDBDoc.timestampLastCrawl = datetime.now().timestamp()
        infoDBDoc.store(infoDatabase)
        logging.info("IS_NEW update done")

    def crawlProcessCoupons(self, apiResponse: dict):
        """ Stores coupons from App API, generates- and adds some special strings to DB for later usage. """
        timestampCrawlStart = datetime.now().timestamp()
        couponDB = self.couchdb[DATABASES.COUPONS]
        dbCouponsHistory = None
        if self.keepHistory:
            dbCouponsHistory = self.couchdb[DATABASES.COUPONS_HISTORY]
        appCoupons = apiResponse['coupons']
        couponIndex = -1
        numberofNewCoupons = 0
        numberOfUpdatedCoupons = 0
        newCouponsIDsText = ''
        updatedCouponIDsText = ''
        appCouponsIDs = []
        logging.info("Crawling app coupons...")
        """ Update DB """
        # When comparing new and old data let's ignore all of the data that gets added via 2nd API later on
        couponsCompareIgnoreKeys = [Coupon.timestampExpire.name, Coupon.dateFormattedExpire.name, Coupon.priceCompare.name]
        couponDBUpdates = []
        for coupon in appCoupons:
            couponIndex += 1
            uniqueCouponID = couponGetUniqueCouponID(coupon)
            plu = coupon['plu']
            imageURL = couponOrOfferGetImageURL(coupon)
            if uniqueCouponID is None or plu is None or imageURL is None:
                """ This should never happen """
                logging.warning('Skipping invalid coupon on position: ' + str(couponIndex) + ' because data is missing')
                continue
            appCouponsIDs.append(uniqueCouponID)
            titleFull = sanitizeCouponTitle(couponGetTitleFull(coupon))
            newCoupon = Coupon(id=uniqueCouponID, uniqueID=uniqueCouponID, plu=plu, title=titleFull, titleShortened=shortenProductNames(titleFull),
                               source=CouponSource.APP, isHidden=coupon['hidden'])
            expireDatetime = couponGetExpireDatetime(coupon)
            if expireDatetime is not None:
                newCoupon.timestampExpire2 = expireDatetime.timestamp()
                newCoupon.dateFormattedExpire2 = formatDateGerman(expireDatetime)
                if expireDatetime < getCurrentDate():
                    """ This should never happen/rare case thus let's log it. """
                    logging.info("Detected expired coupon: " + uniqueCouponID)
            timestampStart = couponGetStartTimestamp(coupon)
            if timestampStart > -1:
                newCoupon.timestampStart = timestampStart
                newCoupon.dateFormattedStart = formatDateGerman(datetime.fromtimestamp(timestampStart, getTimezone()))
            newCoupon.containsFriesOrCoke = couponTitleContainsFriesOrCoke(titleFull)
            newCoupon.imageURL = imageURL
            # price_text could be either e.g. "50%" or "2,99€" -> We want to find the price otherwise that is worthless for us!
            priceText = coupon['price_text']
            realPriceRegEx = re.compile(r'^(\d+[.|,]\d+)\s*€\s*$').search(priceText)
            if realPriceRegEx is not None:
                realPriceStr = realPriceRegEx.group(1)
                realPriceStr = replaceRegex(re.compile('[.,]'), '', realPriceStr)
                newCoupon.price = float(realPriceStr)
            else:
                reducedPercentRegEx = re.compile(r'(\d{1,3})%').search(priceText)
                if reducedPercentRegEx is not None:
                    newCoupon.staticReducedPercent = float(reducedPercentRegEx.group(1))
                else:
                    # This should never happen
                    logging.warning("WTF inconsistent App API response")
            if self.keepHistory:
                self.updateHistoryEntry(dbCouponsHistory, uniqueCouponID, coupon)
            if uniqueCouponID in couponDB:
                # Update doc in DB if needed
                existantCoupon = Coupon.load(couponDB, uniqueCouponID)
                if hasChanged(existantCoupon, newCoupon, couponsCompareIgnoreKeys):
                    # Important: We need the "_rev" value to be able to couponsCompareIgnoreKeys existing documents!
                    newCoupon["_rev"] = existantCoupon.rev
                    couponDBUpdates.append(newCoupon)
                    numberOfUpdatedCoupons += 1
                    updatedCouponIDsText += uniqueCouponID + ','
            else:
                # Add new coupon to DB
                couponDBUpdates.append(newCoupon)
                numberofNewCoupons += 1
                newCouponsIDsText += uniqueCouponID + ','
        if len(couponDBUpdates) > 0:
            # Handle all DB updates with one call
            couponDB.update(couponDBUpdates)
        if not self.crawlOnlyBotCompatibleCoupons or CouponSource.APP_VALID_AFTER_DELETION in BotAllowedCouponSources:
            # Experimental functionality: Tag expired app coupons as separate category (CouponSource)
            couponDBUpdates = []
            for uniqueCouponID in couponDB:
                coupon = Coupon.load(couponDB, uniqueCouponID)
                if uniqueCouponID not in appCouponsIDs and coupon.source == CouponSource.APP:
                    logging.info("Initial app coupon is not an app coupon anymore: " + uniqueCouponID)
                    coupon.source = CouponSource.APP_VALID_AFTER_DELETION
                    coupon.store(couponDB)
                    couponDBUpdates.append(coupon)
            if len(couponDBUpdates) > 0:
                couponDB.update(couponDBUpdates)

        devPrintAppCouponsThatMightBeStillValidButAreNotInAppAPIAnymore = False
        if devPrintAppCouponsThatMightBeStillValidButAreNotInAppAPIAnymore and self.keepHistory:
            for uniqueCouponID in dbCouponsHistory:
                couponHistoryDoc = dbCouponsHistory[uniqueCouponID]
                historyDict = couponHistoryDoc[HISTORYDB.COUPONS_HISTORY_DOC]
                latestHistoryCouponVersion = list(historyDict.values())[len(historyDict) - 1]
                currentCouponVersion = couponDB.get(uniqueCouponID)
                plu = latestHistoryCouponVersion['plu']
                if couponIsValid(latestHistoryCouponVersion) and currentCouponVersion is not None and currentCouponVersion[
                    Coupon.source.name] == CouponSource.APP and uniqueCouponID not in appCouponsIDs:
                    logging.info('Coupon valid but not in App: ' + plu + ' | ' + uniqueCouponID + ' | ' + couponGetTitleFull(latestHistoryCouponVersion) + ' | ' +
                                 latestHistoryCouponVersion[
                                     'price_text'])

        # Cleanup DB: Remove leftover app coupons from DB which are not in current App API response
        couponsToDelete = []
        for couponID in couponDB:
            coupon = Coupon.load(couponDB, couponID)
            if coupon.source == CouponSource.APP and couponID not in appCouponsIDs:
                couponsToDelete.append(coupon)
        if len(couponsToDelete) > 0:
            logging.info("Deleted " + str(couponsToDelete) + " old App coupons")
            couponDB.purge(couponsToDelete)
        self.genericCouponDBCleanup(couponDB)

        if numberofNewCoupons > 0:
            logging.info('App coupons new: ' + str(numberofNewCoupons))
            logging.info('New app coupons IDs: ' + newCouponsIDsText)
        else:
            logging.info('No new app coupons today')
        if numberOfUpdatedCoupons > 0:
            logging.info('App coupons updated: ' + str(numberOfUpdatedCoupons))
            logging.info('Updated app coupons IDs: ' + updatedCouponIDsText)
        logging.info('Coupons in app: ' + str(len(appCoupons)))
        logging.info("Total coupons1 crawl time: " + getFormattedPassedTime(timestampCrawlStart))

    def crawlProcessCoupons2(self):
        """ Crawls coupons from secondary sources and adds additional information to the data crawled via app API.
         Main purpose: Crawl paper coupons """
        timestampStart = datetime.now().timestamp()
        couponDB = self.getCouponDB()
        logging.info("Collecting stores to crawl coupons from...")
        if DEBUGCRAWLER:
            # storeIDs = [682, 4108, 514]
            storeIDs = [666]
        else:
            conn = HTTP20Connection('api.burgerking.de')
            """ Returns List of all stores """
            conn.request("GET", '/api/o2uvrPdUY57J5WwYs6NtzZ2Knk7TnAUY/v2/de/de/stores/', headers=HEADERS)
            stores = loads(conn.get_response().read())
            storeIDs = []
            # Collect storeIDs from which we can obtain coupons
            for store in stores:
                properties = store['properties']
                """ 2021-02-24: Only such stores will present us with an online list of products and coupons -> Only stores with mobileOrdering is called "Vorbestellen/Vorbestellung" in their app. """
                if 'mobileOrdering' in properties or 'paperCoupons' in properties:
                    storeIDs.append(store['id'])
        if len(storeIDs) == 0 or len(storeIDs) > 100:
            # 2021-07-22: TODO: Workaround! Either the "mobileOrdering" property is not present anymore at night or we need to find a new way to detect stores with available additional online coupon DB...
            logging.warning("Using store-crawler workaround/fallback!")
            storeIDs = [682, 4108, 514]
        if len(storeIDs) == 0:
            # This should never happen!
            logging.warning("Failed to find any storeIDs to crawl coupons from!")
            return
        logging.info("Found " + str(len(storeIDs)) + " stores to crawl coupons from")
        logging.info("Crawling coupons2...")
        # Store possible paper coupon short-PLU numbers without chars e.g. {"B": [1, 2, 3], "C": [1, 2, 3] }
        foundPaperCouponMap = {}
        paperCouponCharsToValidExpireTimestamp = {}
        try:
            """ Load file which contains some extra data which can be useful to correctly determine the "CouponSource" and expire date of paper coupons. """
            paperExtraData = loadJson(BotProperty.paperCouponExtraDataPath)
            for paperChar, paperData in paperExtraData.items():
                validuntil = datetime.strptime(paperData['expire_date'] + ' 23:59:59', '%Y-%m-%d %H:%M:%S').astimezone(getTimezone()).timestamp()
                if validuntil > datetime.now().timestamp():
                    paperData['expire_timestamp'] = validuntil
                    paperCouponCharsToValidExpireTimestamp[paperChar] = validuntil
        except:
            logging.warning("Error during loading paper coupon extra data")
            traceback.print_exc()
        # Collect all app coupon chars e.g. "Z13" -> "Z"
        dbAllPLUsList = set()
        appCouponCharList = set()
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            dbAllPLUsList.add(coupon.plu)
            if coupon.source == CouponSource.APP and couponDBIsValid(coupon):
                pluChar = re.compile(r"([A-Za-z]+)\d+.*").search(coupon.plu).group(1)
                appCouponCharList.add(pluChar.upper())
        numberofNewCoupons = 0
        numberofUpdatedCoupons = 0
        allProducts2 = {}
        # Contains the original unmodified DB data
        allCoupons2 = {}
        # Contains our own created coupon data dicts
        coupons2LeftToProcess = {}
        # List of all DB items we will later change via a single DB request
        dbUpdates = []
        # The more stores we crawl coupons from the longer it takes -> Limit that (set this to -1 to crawl all stores that are providing coupons). This can take a lot of time so without threading we won't be able to crawl all coupons from all stores for our bot (TG channel)!
        maxNumberofStoresToCrawlCouponsFrom = 2
        for storeIndex in range(len(storeIDs)):
            storeID = storeIDs[storeIndex]
            # This is for logging purposes only so that our log output is easier to read and we know roughly when this loop will be finished.
            if len(storeIDs) > maxNumberofStoresToCrawlCouponsFrom:
                logging.info("Crawling coupons from store " + str(storeIndex + 1) + "/" + str(maxNumberofStoresToCrawlCouponsFrom) + ": " + str(
                    storeID) + " (Not crawling all to speedup this process)")
            else:
                logging.info("Crawling coupons from store " + str(storeIndex + 1) + "/" + str(len(storeIDs)) + ": " + str(storeID))
            if DEBUGCRAWLER:
                apiResponse = loads(requests.get('http://localhost/bkcrawler/coupons2_latest.json').text)
            else:
                conn = HTTP20Connection('mo.burgerking-app.eu')
                conn.request("GET", '/api/v2/stores/' + str(storeID) + '/menu', headers=HEADERS)
                apiResponse = loads(conn.get_response().read())
                if self.storeCouponAPIDataAsJson:
                    # Save API response so we can easily use this data for local testing later on.
                    with open('crawler/coupons2_latest.json', 'w') as outfile:
                        json.dump(apiResponse, outfile)
                    with open('crawler/coupons2_' + str(storeID) + '.json', 'w') as outfile:
                        json.dump(apiResponse, outfile)
            products = apiResponse.get('products')
            coupons = apiResponse.get('coupons')
            if products is None or coupons is None:
                # This should never happen!
                logging.warning("Failed to obtain coupons from this store -> Skipping it")
                continue
            # Collect all poductIDs to separate dict for later usage
            for productIDTmp, productTmp in products.items():
                if productIDTmp not in allProducts2:
                    allProducts2[productIDTmp] = productTmp
            # Now update our coupon DB
            for coupon in coupons:
                """ First collect all data we need """
                productID = coupon['product_id']
                uniqueCouponID = coupon['promo_code']
                plu = coupon['store_promo_code']
                """ Find the product which belongs to this coupon (basically a dataset containing more details). """
                product = products.get(str(productID))
                title = product['name']
                price = product['price']
                image_url = product['image_url']
                startDate = coupon2GetDatetimeFromString(coupon['start_date'])
                expirationDate = coupon2GetDatetimeFromString(coupon['expiration_date'])
                if product is None or len(product) == 0:
                    # This should never happen
                    logging.warning("WTF failed to find product for couponID: " + uniqueCouponID)
                    continue
                if plu.isdecimal() and isCouponShortPLU(uniqueCouponID):
                    # Let's fix Burger Kings database errors!
                    logging.debug("Found swapped plu/uniqueID: " + plu + " / " + uniqueCouponID)
                    newplu = uniqueCouponID
                    uniqueCouponID = plu
                    plu = newplu
                elif not uniqueCouponID.isdecimal():
                    # This should never ever happen!
                    logging.warning("WTF uniqueCouponID has unexpected format")
                    continue
                if uniqueCouponID not in allCoupons2:
                    allCoupons2[uniqueCouponID] = coupon
                # Fix- and sanitize title: Again BK has a very 'dirty' DB!
                title = coupon2FixProductTitle(title)
                # Try to find a meaningful compare price (the hard way...)
                priceCompare = -1
                if 'combo_groups' in product:
                    combo_groups = product['combo_groups']
                    containsUnsupportedGroup = False
                    """ "50%" coupons will contain dummy products that have a price of 0 -> We cannot easily find a compare price! """
                    containsUnidentifiedDummyProducts = False
                    containsUnidentifiedZeroPriceProducts = False
                    for combo_group in combo_groups:
                        comboGroupType = combo_group['type']
                        if comboGroupType != 'entrees':
                            containsUnsupportedGroup = True
                            continue
                        product_ids = combo_group['product_ids']
                        containedProductsDebug = []
                        namesToPricesTmp = {}
                        unidentifiedDummyProductNamesWithoutPrices = {}
                        for product_idTmp in product_ids:
                            productTmp = products.get(str(product_idTmp))
                            pruductNameTmp = coupon2FixProductTitle(productTmp['name'])
                            containedProductsDebug.append(str(productTmp['id']) + " -> " + pruductNameTmp)
                            """ Find products ending with "STEPX" - usually "STEP2" and in some rare cases "STEP3" """
                            dummyProductNameRegex = re.compile('(?i)(.*?)\\s*step\\s?[23]\\s*').search(pruductNameTmp)
                            if dummyProductNameRegex and productTmp['price'] == 0:
                                """ Dummy product """
                                unidentifiedDummyProductNamesWithoutPrices[dummyProductNameRegex.group(1).lower()] = {
                                    "id": productTmp['id'],
                                    "fullname": pruductNameTmp
                                }
                            elif productTmp['price'] == 0:
                                """ Zero price product """
                                # print("WTF zero price product in: " + uniqueCouponID)
                                containsUnidentifiedZeroPriceProducts = True
                            else:
                                """ "Real" product with real price """
                                priceCompare += productTmp['price']
                            namesToPricesTmp[pruductNameTmp.lower()] = productTmp['price']
                        # Now try to find all missing prices
                        identifiedAllDummyProductsPrices = True
                        for unidentifiedDummyProductName in unidentifiedDummyProductNamesWithoutPrices:
                            realPriceOfDummyProduct = namesToPricesTmp.get(unidentifiedDummyProductName)
                            if realPriceOfDummyProduct is None:
                                identifiedAllDummyProductsPrices = False
                            else:
                                priceCompare += realPriceOfDummyProduct
                        if not identifiedAllDummyProductsPrices:
                            # print("Coupon contains unidentified step2 products: " + uniqueCouponID + " --> ProductID: " + str(productID) + " --> " + str(unidentifiedDummyProductNamesWithoutPrices))
                            # print('Contained products: ' + str(containedProductsDebug))
                            pass
                    if not containsUnsupportedGroup and not containsUnidentifiedDummyProducts and not containsUnidentifiedZeroPriceProducts and priceCompare > price:
                        # print("Found compare price: " + plu + '\t' + uniqueCouponID + '\t' + title + '\t' + str(price / 100) + '\t' + str(priceCompare / 100))
                        pass
                    else:
                        """ Invalidate whatever we've found there as we cannot trust that value! """
                        priceCompare = -1
                # Check if this coupon exists/existed in app -> Update information as other BK endpoints may serve more info than their official app endpoint!
                existantCoupon = Coupon.load(couponDB, uniqueCouponID)
                if existantCoupon is not None and couponDBIsValid(existantCoupon) and existantCoupon.source in [CouponSource.APP,
                                                                                                                CouponSource.APP_VALID_AFTER_DELETION]:
                    # Update existing app coupon with new information.
                    if existantCoupon.price is None:
                        # 201-07-06: Only update current price if we failed to find it before as entrys of this APIs can sometimes be wrong (e.g. for 32749: 4,99€ according to this API but 9,89€ according to API)
                        existantCoupon.price = price
                    elif price != existantCoupon.price:
                        # Rare case
                        logging.warning("Detected API price difference for coupon " + existantCoupon.id + " | App: " + str(existantCoupon.price) + " | API2: " + str(price))
                    if priceCompare > 0:
                        existantCoupon.priceCompare = priceCompare
                    # Add additional expire date data
                    existantCoupon.timestampExpire = expirationDate.timestamp()
                    existantCoupon.dateFormattedExpire = formatDateGerman(expirationDate)
                    dbUpdates.append(existantCoupon)
                else:
                    # Add/Update non-App coupons
                    # logging.info("Possible paper coupon: " + plu + '\t' + uniqueCouponID + '\t' + title + '\t' + str(price / 100))
                    newCoupon = Coupon(id=uniqueCouponID, uniqueID=uniqueCouponID, plu=plu, title=title, titleShortened=shortenProductNames(title),
                                       timestampStart=expirationDate.timestamp(), timestampExpire=expirationDate.timestamp(),
                                       dateFormattedStart=formatDateGerman(startDate), dateFormattedExpire=formatDateGerman(expirationDate),
                                       price=price, containsFriesOrCoke=couponTitleContainsFriesOrCoke(title))
                    if priceCompare > 0:
                        newCoupon.priceCompare = priceCompare
                    # Now determine coupon type
                    if len(plu) == 0:
                        # "Secret" coupon -> Only online orderable 'type 1'
                        newCoupon.source = CouponSource.ONLINE_ONLY
                    elif plu.isdecimal():
                        # "Secret" coupon -> Only online orderable 'type 2'
                        newCoupon.source = CouponSource.ONLINE_ONLY
                    elif plu[0] in appCouponCharList:
                        newCoupon.source = CouponSource.APP_SAME_CHAR_AS_CURRENT_APP_COUPONS
                    else:
                        # Assumed "unsafe paper coupon" --> This may be changed later on!
                        newCoupon.source = CouponSource.PAPER_UNSAFE
                    newCoupon.imageURL = image_url
                    coupons2LeftToProcess[uniqueCouponID] = newCoupon
            logging.info("Found coupons2 so far (except app coupons): " + str(len(coupons2LeftToProcess)))
            if storeIndex + 1 >= maxNumberofStoresToCrawlCouponsFrom:
                logging.info("Stopping store coupon crawling because reached store limit of: " + str(maxNumberofStoresToCrawlCouponsFrom))
                break
        # Create a map containing char -> coupons e.g. {"X": {"plu": "1234"}}
        pluCharMap = {}
        for uniqueCouponID, coupon in coupons2LeftToProcess.items():
            # Make sure that we got a valid "paper PLU"
            pluRegEx = REGEX_PLU_ONLY_ONE_LETTER.search(coupon.plu)
            if not pluRegEx:
                # Skip invalid items
                continue
            else:
                pluCharMap.setdefault(pluRegEx.group(1).upper(), []).append(coupon)
        # Remove all results that cannot be paper coupoons by length
        for pluChar, coupons in pluCharMap.copy().items():
            if pluChar in appCouponCharList:
                # App coupons cannot be paper coupons
                del pluCharMap[pluChar]
            elif len(coupons) != 46 and len(coupons) != 47:
                logging.debug("Removing paper char candidate because of bad length:" + pluChar + " [" + str(len(coupons)) + "]")
                del pluCharMap[pluChar]
        """ Now do some workarounds/corrections of our results.
         This was necessary because as of 09-2021 e.g., current paper coupons' PLUs started with letter "A" but were listed with letter "F" in the BK DB.
         """
        corrections = {"F": "A"}
        for oldChar, newChar in corrections.items():
            if oldChar in pluCharMap and newChar in paperCouponCharsToValidExpireTimestamp.keys():
                logging.info("Correcting paper coupons starting with " + oldChar + " --> " + newChar)
                if newChar in pluCharMap:
                    # Edge case: This is very very unlikely going to happen!
                    logging.warning("Correction failed due to possible collision: " + newChar + " already exists in our results!")
                    continue
                else:
                    coupons = pluCharMap[oldChar]
                    for coupon in coupons:
                        coupon.plu = newChar + coupon.plu[1:]
                    del pluCharMap[oldChar]
                    pluCharMap[newChar] = coupons
        if len(pluCharMap) == 0:
            logging.info("Failed to find any paper coupon candidates")
        else:
            # More logging
            couponCharsLogtext = ''
            for paperPluChar, coupons in pluCharMap.items():
                if len(couponCharsLogtext) > 0:
                    couponCharsLogtext += ', '
                couponCharsLogtext += paperPluChar + "[" + str(len(coupons)) + "]"
            logging.info("Auto-found the following " + str(len(pluCharMap)) + " possible paper coupon char(s): " + couponCharsLogtext)
            # Evaluate our findings
            for paperPluChar, paperCoupons in pluCharMap.items():
                if paperPluChar in paperCouponCharsToValidExpireTimestamp.keys():
                    # We safely detected this set of paper coupons
                    logging.info("Safely detected paper coupon char is: " + paperPluChar)
                    # Update data of these coupons and add them to DB later
                    expireTimestamp = paperCouponCharsToValidExpireTimestamp[paperPluChar]
                    for paperCoupon in paperCoupons:
                        paperCoupon.source = CouponSource.PAPER
                        paperCoupon.timestampExpire2 = expireTimestamp
                        paperCoupon.dateFormattedExpire2 = formatDateGerman(datetime.fromtimestamp(expireTimestamp))
                else:
                    # We assume that these coupons are paper coupons
                    logging.info("Auto assigned paper coupon char is: " + paperPluChar)
                    # Update data of these coupons and add them to DB later
                    # https://www.quora.com/In-Python-what-is-the-cleanest-way-to-get-a-datetime-for-the-start-of-today
                    today = datetime.today()  # or datetime.now to use local timezone
                    todayDayEnd = datetime(year=today.year, month=today.month,
                                           day=today.day, hour=23, minute=59, second=59)
                    # Add them with fake validity of 2 days
                    artificialExpireTimestamp = todayDayEnd.timestamp() + 2 * 24 * 60
                    for paperCoupon in paperCoupons:
                        paperCoupon.source = CouponSource.PAPER
                        paperCoupon.timestampExpire2 = artificialExpireTimestamp
                        paperCoupon.dateFormattedExpire2 = formatDateGerman(datetime.fromtimestamp(artificialExpireTimestamp))
                        paperCoupon.isUnsafeExpiredate = True
                        paperCoupon.description = SYMBOLS.INFORMATION + "Das hier eingetragene Ablaufdatum ist vorläufig und wird zeitnah korrigiert!"
                foundPaperCouponMap[paperPluChar] = paperCoupons
        if len(paperCouponCharsToValidExpireTimestamp) > 0 and len(foundPaperCouponMap) == 0:
            # This should never happen
            logging.warning("Failed to find any paper coupons alhough we expect some to be there!")

        """ Check for missing paper coupons based on the ones we found.
        2021-09-29: Now we do filter by array size before so this handling is pretty much useless but let's keep it anyways.
        """
        logging.info("Looking for missing paper coupons...")
        for paperChar, paperCoupons in foundPaperCouponMap.items():
            # Now get a list of the numbers only and consider: paperCoupons may contain duplicates but we don't want those in paperCouponNumbersList!
            paperCouponNumbersList = []
            for coupon in paperCoupons:
                couponNumber = int(coupon.plu[1:])
                if couponNumber not in paperCouponNumbersList:
                    paperCouponNumbersList.append(couponNumber)
            # Sort list to easily find highest number
            paperCouponNumbersList.sort()
            highestPaperPLUNumber = paperCouponNumbersList[len(paperCouponNumbersList) - 1]
            # Now collect possibly missing paper coupons
            # Even if all "real" paper coupons are found, it may happen that the last one, usually number 47 is not found as thart is a dedicated Payback coupon
            if highestPaperPLUNumber != len(paperCouponNumbersList):
                missingPaperPLUs = []
                missingPaperPLUsButPresentInDB = []
                for numberToCheck in range(1, highestPaperPLUNumber + 1):
                    plu = paperChar + str(numberToCheck)
                    if numberToCheck not in paperCouponNumbersList:
                        if plu in dbAllPLUsList:
                            # 2021-06-10: This may happen right before paper coupons expire as BK will already remove them from their apps earlier than their real expire date...
                            missingPaperPLUsButPresentInDB.append(plu)
                        else:
                            missingPaperPLUs.append(plu)
                paybackDummyPLU = paperChar + '47'
                if len(missingPaperPLUs) > 0:
                    if len(missingPaperPLUs) == 1 and missingPaperPLUs[0] == paybackDummyPLU:
                        # Our 'missing' PLU seems to be the dummy Payback PLU --> Looks like we found all paper coupons :)
                        logging.info("Paper coupons OK: " + paperChar + "[" + str(len(paperCoupons)) + "]")
                    else:
                        logging.info("Possibly missing paper PLUs: " + str(missingPaperPLUs))
                        logging.info("Paper coupons NOT OK: " + paperChar + " [" + str(len(paperCoupons)) + "] | Possibly missing PLUs: " + str(missingPaperPLUs))
                # Rare case: BK has deleted the paper coupons in their API already but we still got them in our DB because they should still be valid!
                if len(missingPaperPLUsButPresentInDB) > 0:
                    logging.info("Paper PLUs that are present in DB but not in API: " + str(missingPaperPLUsButPresentInDB))
            else:
                # Looks like we found all paper coupons :)
                logging.info("Paper coupons OK: " + paperChar + " [" + str(len(paperCoupons)) + "]")
        couponsToAddToDB = {}
        # Collect items we want to add to DB
        if self.crawlOnlyBotCompatibleCoupons:
            # Only add paper coupons to DB
            for paperCoupons in foundPaperCouponMap.values():
                for paperCoupon in paperCoupons:
                    couponsToAddToDB[paperCoupon.id] = paperCoupon
        else:
            # Add all detected coupons to DB
            couponsToAddToDB = coupons2LeftToProcess
        # Now collect all DB updates we want to do
        for uniqueCouponID, newCoupon in couponsToAddToDB.items():
            existantCoupon = Coupon.load(couponDB, uniqueCouponID)
            # Update DB
            if existantCoupon is not None:
                # Update existing coupon
                if hasChanged(existantCoupon, newCoupon):
                    # Important: We need the "_rev" value to be able to couponsCompareIgnoreKeys existing documents!
                    newCoupon["_rev"] = existantCoupon.rev
                    dbUpdates.append(newCoupon)
                    numberofUpdatedCoupons += 1
            else:
                # Add new coupon
                numberofNewCoupons += 1
                dbUpdates.append(newCoupon)
        if len(dbUpdates) > 0:
            couponDB.update(dbUpdates)
        logging.info("Number of crawled coupons2: " + str(len(couponsToAddToDB)))
        # Update history if needed
        if self.keepHistory:
            timestampHistoryDBUpdateStart = datetime.now().timestamp()
            logging.info("Updating history DBs... 1/2: products2")
            dbHistoryProducts2 = self.couchdb[DATABASES.PRODUCTS2_HISTORY]
            for itemID, product in allProducts2.items():
                self.updateHistoryEntry(dbHistoryProducts2, itemID, product)
            logging.info("Updating history DBs... 2/2: coupons2")
            dbHistoryCoupons2 = self.couchdb[DATABASES.COUPONS2_HISTORY]
            for itemID, coupon in allCoupons2.items():
                self.updateHistoryEntry(dbHistoryCoupons2, itemID, coupon)
            logging.info("Time it took to update coupons2 history DBs: " + getFormattedPassedTime(timestampHistoryDBUpdateStart))
        # Cleanup DB: Remove all non-App coupons that do not exist in API anymore
        deleteCouponDocs = {}
        if self.crawlOnlyBotCompatibleCoupons:
            # Allow to clean paper coupons if we found new/current ones in this run
            if len(foundPaperCouponMap) > 0:
                cleanupPapercoupons = True
            else:
                cleanupPapercoupons = False
            for uniqueCouponID in couponDB:
                couponDoc = Coupon.load(couponDB, uniqueCouponID)
                if cleanupPapercoupons and couponDoc.source == CouponSource.PAPER and uniqueCouponID not in couponsToAddToDB:
                    # Remove paper coupon regardless of validity because we found new paper coupons this run
                    deleteCouponDocs[uniqueCouponID] = couponDoc
                if couponDoc.source == CouponSource.PAPER and couponDBIsValid(couponDoc):
                    # 2021-05-26: Allow 'valid' paper coupons to stay in DB as long as they're not expired. This makes sense as BK sometimes removes them from DB for some time even though they're still valid...
                    continue
                elif couponDoc.source != CouponSource.APP and uniqueCouponID not in allCoupons2.keys():
                    deleteCouponDocs[uniqueCouponID] = couponDoc
        else:
            # Less 'intelligent' cleanup
            for uniqueCouponID in couponDB:
                couponDoc = Coupon.load(couponDB, uniqueCouponID)
                if couponDoc.source != CouponSource.APP and uniqueCouponID not in allCoupons2.keys():
                    deleteCouponDocs[uniqueCouponID] = couponDoc
        if len(deleteCouponDocs) > 0:
            couponDB.purge(deleteCouponDocs.values())
        self.genericCouponDBCleanup(couponDB)

        if numberofNewCoupons > 0:
            logging.info("Coupons2 new IDs: " + str(numberofNewCoupons))
        if numberofUpdatedCoupons > 0:
            logging.info("Coupons2 updated IDs: " + str(numberofUpdatedCoupons))
        if len(deleteCouponDocs) > 0:
            logging.info("Coupons2 deleted coupons: " + str(len(deleteCouponDocs)) + " | " + str(list(deleteCouponDocs.keys())))
        # 2021-03-21: Debug-Test debugtest
        for couponID in couponDB:
            coupon = Coupon.load(couponDB, couponID)
            if coupon.plu is not None and (len(coupon.plu) > 0 and (coupon.plu[0] == 'S' or coupon.plu[0] == 'Z')) and coupon.source != CouponSource.APP:
                # Debugtest
                print(
                    'Coupon contains app coupon char but is not available in app anymore: ' + (
                        "N/A" if coupon.plu is None else coupon.plu) + " | " + coupon.id + " | " + coupon.title + " | " + couponDBGetPriceFormatted(
                        coupon, "??€") + " | " + ("NO_EXPIRE_DATE_2" if coupon.dateFormattedExpire2 is None else coupon.dateFormattedExpire2) + " | " + (
                        "NO_EXPIRE_DATE_" if coupon.dateFormattedExpire is None else coupon.dateFormattedExpire))
        logging.info("API Crawling 2 done | Total number of coupons in DB: " + str(len(couponDB)))
        logging.info("Total coupons2 crawl time: " + getFormattedPassedTime(timestampStart))

    def genericCouponDBCleanup(self, couponDB):
        deleteCouponDocs = {}
        for uniqueCouponID in couponDB:
            couponDoc = Coupon.load(couponDB, uniqueCouponID)
            if self.crawlOnlyBotCompatibleCoupons and not isValidBotCoupon(couponDoc):
                deleteCouponDocs[uniqueCouponID] = couponDoc
        if len(deleteCouponDocs) > 0:
            logging.info("Deleting non-allowed coupons from DB: " + str(len(deleteCouponDocs)))
            couponDB.purge(deleteCouponDocs.values())

    def addSpecialCoupons(self):
        """ Adds special coupons which are manually added via config_special_coupons.json.
         Make sure to execute this AFTER DB cleanup so this can set IS_NEW flags without them being removed immediately afterwards!
         This will only add VALID coupons to DB! """
        specialCouponData = loadJson(BotProperty.specialCouponConfigPath)
        specialCoupons = specialCouponData["special_coupons"]
        couponsToAdd = {}
        for specialCoupon in specialCoupons:
            newCoupon = Coupon(id=specialCoupon[Coupon.uniqueID.name], uniqueID=specialCoupon[Coupon.uniqueID.name], title=sanitizeCouponTitle(specialCoupon[Coupon.title.name]),
                               source=specialCoupon[Coupon.source.name], imageURL=specialCoupon[Coupon.imageURL.name],
                               titleShortened=shortenProductNames(specialCoupon[Coupon.title.name]),
                               containsFriesOrCoke=couponTitleContainsFriesOrCoke(specialCoupon[Coupon.title.name]))
            # Add optional fields
            if Coupon.plu.name in specialCoupon:
                newCoupon.plu = specialCoupon[Coupon.plu.name]
            if Coupon.price.name in specialCoupon:
                newCoupon.price = specialCoupon[Coupon.price.name]
            if Coupon.staticReducedPercent.name in specialCoupon:
                newCoupon.staticReducedPercent = specialCoupon[Coupon.staticReducedPercent.name]
            if Coupon.description.name in specialCoupon:
                newCoupon.description = specialCoupon[Coupon.description.name]
            expiredateStr = specialCoupon["expire_date"] + " 23:59:59"
            expiredate = datetime.strptime(expiredateStr, '%Y-%m-%d %H:%M:%S').astimezone(getTimezone())
            # Only add active coupons if it is valid
            if expiredate.timestamp() > datetime.now().timestamp():
                newCoupon.timestampExpire2 = expiredate.timestamp()
                newCoupon.dateFormattedExpire2 = formatDateGerman(expiredate)
                if "enforce_is_new_override_until_date" in specialCoupon:
                    enforceIsNewOverrideUntilDateStr = specialCoupon["enforce_is_new_override_until_date"] + " 23:59:59"
                    enforceIsNewOverrideUntilDate = datetime.strptime(enforceIsNewOverrideUntilDateStr, '%Y-%m-%d %H:%M:%S').astimezone(getTimezone())
                    if enforceIsNewOverrideUntilDate.timestamp() > datetime.now().timestamp():
                        newCoupon.isNew = True
                couponsToAdd[specialCoupon[Coupon.uniqueID.name]] = newCoupon
        if len(couponsToAdd) > 0:
            logging.info("Adding special coupons...")
            # Only do DB request if we want to add stuff
            couponDB = self.getCouponDB()
            dbUpdates = []
            for uniqueCouponID, coupon in couponsToAdd.items():
                existantCoupon = Coupon.load(couponDB, uniqueCouponID)
                if existantCoupon is not None:
                    coupon["_rev"] = existantCoupon.rev
                dbUpdates.append(coupon)
            couponDB.update(dbUpdates)
            logging.info("Number of special coupons added: " + str(len(couponsToAdd)))

    def updateHistoryEntry(self, historyDB, primaryKey: str, newData):
        """ Adds/Updates entry inside given database. """
        if primaryKey not in historyDB:
            # Add this ID for the first time
            historyDB[primaryKey] = {HISTORYDB.COUPONS_HISTORY_DOC: {getCurrentDateIsoFormat(): newData}}
        else:
            # Update history in our DB for this item if needed
            couponHistoryDoc = historyDB[primaryKey]
            historyDict = couponHistoryDoc[HISTORYDB.COUPONS_HISTORY_DOC]
            latestHistoryVersion = list(historyDict.values())[len(historyDict) - 1]
            if hasChanged(latestHistoryVersion, newData):
                # Data has changed -> Add new entry with timestamp and new data.
                historyDict[getCurrentDateIsoFormat()] = newData
                couponHistoryDoc[HISTORYDB.COUPONS_HISTORY_DOC] = historyDict
                historyDB.save(couponHistoryDoc)
            else:
                # Data is the same as last time - no update needed
                pass

    def crawlProcessOffers(self, apiResponse):
        """ Crawls offers from app API and saves them. Downloads new offer images if available. """
        offerDB = self.couchdb[DATABASES.OFFERS]
        # Delete all old entries
        if len(offerDB) > 0:
            dbUpdateDelete = []
            for offerIDStr in offerDB:
                dbUpdateDelete.append(offerDB[offerIDStr])
            offerDB.purge(dbUpdateDelete)
        dbOffersHistory = None
        # This requires one DB request so only do it when needed
        if self.keepHistory:
            dbOffersHistory = self.couchdb[DATABASES.OFFERS_HISTORY]
        offers = apiResponse['promos']
        numberofNewOfferImages = 0
        offerIDsAPI = []
        dbUpdates = []
        for offer in offers:
            offerIDStr = str(offer['id'])
            offerIDsAPI.append(offerIDStr)
            # Save current version of image
            imageURL = couponOrOfferGetImageURL(offer)
            if downloadImageIfNonExistant(imageURL, offerGetImagePath(offer)):
                numberofNewOfferImages += 1
            dbUpdates.append(Document(offer, _id=offerIDStr))
            if self.keepHistory:
                self.updateHistoryEntry(dbOffersHistory, offerIDStr, offer)
        if len(dbUpdates) > 0:
            offerDB.update(dbUpdates)
        if numberofNewOfferImages > 0:
            logging.info('Offers new downloaded images: ' + str(numberofNewOfferImages))
        logging.info('Offers found: ' + str(len(offerDB)))

    def checkProductiveCouponsDBImagesIntegrity(self):
        """ Small helper functions to detect missing images e.g. after manual images folder cleanup. """
        couponDB = self.getCouponDB()
        numberOfMissingImages = 0
        for couponIDStr in couponDB:
            coupon = Coupon.load(couponDB, couponIDStr)
            # 2021-04-20: Skip invalid/expired coupons as they're not relevant for the user (we don't access them anyways at this moment).
            if not couponDBIsValid(coupon) or coupon.source not in BotAllowedCouponSources:
                continue
            imagePathCoupon = couponDBGetImagePath(coupon)
            if not isValidImageFile(imagePathCoupon):
                logging.warning(couponIDStr + ": Coupon image does not exist: " + imagePathCoupon)
                numberOfMissingImages += 1
            imagePathQR = couponDBGetImagePathQR(coupon)
            if not isValidImageFile(imagePathQR):
                logging.warning(couponIDStr + ": QR image does not exist: " + imagePathQR)
                numberOfMissingImages += 1
        if numberOfMissingImages > 0:
            logging.warning("Total number of missing images: " + str(numberOfMissingImages))

    def checkProductiveOffersDBImagesIntegrity(self):
        """ Small helper functions to detect missing images e.g. after manual images folder cleanup. """
        offersDB = self.getOfferDB()
        numberOfMissingImages = 0
        for offerIDStr in offersDB:
            offer = offersDB[offerIDStr]
            if not isValidImageFile(offerGetImagePath(offer)):
                logging.warning(offerIDStr + ": Offer image does not exist: " + offerGetImagePath(offer))
                numberOfMissingImages += 1
        if numberOfMissingImages > 0:
            logging.warning("Total number of missing images: " + str(numberOfMissingImages))

    def checkProductiveCouponDBForAnomalies(self):
        couponDB = self.getCouponDB()
        # Check for e.g. two times "D13" which is listed under at least two separate IDs -> Should never happen but can happen...
        pluDuplicateMap = {}
        for uniqueCouponID in couponDB:
            currentPLUDupeList = pluDuplicateMap.setdefault(uniqueCouponID, [])
            currentPLUDupeList.append(uniqueCouponID)
        for plu, dupeList in pluDuplicateMap.items():
            if len(dupeList) > 1:
                logging.warning("Found dupes for PLU: " + plu + " | " + str(dupeList))

    def crawlProducts_DEPRECATED(self):
        # 2021-04-20: Not required at this moment!
        dbProducts = self.couchdb[DATABASES.PRODUCTS]
        dbProductsHistory = None
        if self.keepHistory:
            dbProductsHistory = self.couchdb[DATABASES.PRODUCTS_HISTORY]
        host = 'api.burgerking.de'
        conn = HTTP20Connection(host)
        conn.request("GET", '/api/o2uvrPdUY57J5WwYs6NtzZ2Knk7TnAUY/v2/de/de/products/',
                     headers=HEADERS)
        products = loads(conn.get_response().read())
        numberofNewProductImages = 0
        """ Enable this if you want to laugh hard! """
        printAlternativeTerms = False
        """ Debug switch """
        printShortenedProductTitles = False
        for product in products:
            productID = product.get('id', None)
            if productID is None:
                """ This should never happen -> Skip invalid items """
                logging.warning('Product parser failure')
                continue
            title = product['name']
            uniqueID = str(productID)
            if printAlternativeTerms:
                print(title + ' | ' + uniqueID)
                alternativeTerms = product['alternativeTerms']
                for alternativeTerm in alternativeTerms:
                    print(alternativeTerm)
                print('-----')
            if printShortenedProductTitles:
                print(shortenProductNames(title))
                print('---')
            """ Save product image """
            imageInfo = product['images']['bgImage']
            """ 2021-01-24: Products which haven't been released yet may already be available via API but without product image! """
            if imageInfo is not None and imageInfo.get('url') is not None:
                imageURL = imageInfo['url']
                if imageURL[0] == '/':
                    imageURL = 'https://' + host + imageURL
                imageURL = setImageURLQuality(imageURL)
                imagePath = getPathImagesProducts() + "/" + str(productID) + "_" + getFilenameFromURL(imageURL)
                if downloadImageIfNonExistant(imageURL, imagePath):
                    numberofNewProductImages += 1
            else:
                logging.info('Product without image: ' + title)
            # Update products DB
            if uniqueID in dbProducts:
                del dbProducts[uniqueID]
            dbProducts[uniqueID] = product
            if self.keepHistory:
                # Update history DB
                self.updateHistoryEntry(dbProductsHistory, uniqueID, product)
        # Done! Now do some logging ...
        if numberofNewProductImages > 0:
            logging.info('Products new downloaded images: ' + str(numberofNewProductImages))
        logging.info('Products in DB: ' + str(len(dbProducts)))
        logging.info('Products in API: ' + str(len(products)))

    def findProductIDsOfCoupons_DEPRECATED(self):
        """ Finds productIDs of products contained in vouchers.
        In the future this can be used to e.g. find duplicated coupons or reliably compare coupons to other coupons!
        E.g. "Long Chicken® + Crispy Chicken + große King Pommes + 0,5 L Coca-Cola®" --> Coupon contains products: 1139, 1136, (0,5L)1098, (große)1143
        """
        """ 2021-02-06: Not needed anymore as new handling can find the exact product IDs of coupons with no issue at all! """
        logging.info("Matching coupon products -> ProductIDs")
        couponDB = self.getCouponDB()
        productIDsDB = self.couchdb[DATABASES.PRODUCTS]
        if len(productIDsDB) == 0:
            """ Don't continue if the required data is not available. """
            return
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            fullCouponTitle = coupon.title
            """ Check if coupon contains multiple products """
            if ' + ' in fullCouponTitle:
                """ Assume that we got multiple products """
                unsafeProductTitles = fullCouponTitle.split(' + ')
            else:
                """ We only got one product """
                unsafeProductTitles = [fullCouponTitle]
            foundProductIDsMap = {}
            foundProductIDsList = []
            failedUnsafeProductTitles = []
            for unsafeProductTitle in unsafeProductTitles:
                """ First correct unsafe title and remove any quantities present """
                unsafeProductTitleCleaned = unsafeProductTitle.lower().strip()
                matchObjectDrinksAtBeginning = re.compile('(?i)^(\\d[.,]\\d\\s*L)\\s*(.+)').search(unsafeProductTitleCleaned)
                matchObjectDrinksAtEnd = re.compile('(?i)(.+)(\\d[.,]\\d\\s*L)$').search(unsafeProductTitleCleaned)
                matchObjectGenericQuantityAtBeginning = re.compile('(?i)^(\\d{1,2}( x \\d{1,2})?)\\s*(.+)').search(unsafeProductTitleCleaned)
                matchObjectGenericFriesQuantity = re.compile('(?i)^(kleine|mittlere|große) (.+)').search(unsafeProductTitleCleaned)
                if matchObjectDrinksAtBeginning:
                    """ E.g. "0,5 L Coca-Cola" -> "Coca-Cola" """
                    unsafeProductTitleCleaned = matchObjectDrinksAtBeginning.group(2)
                    productQuantityValue = matchObjectDrinksAtBeginning.group(1)
                elif matchObjectDrinksAtEnd:
                    """ E.g. "King Shake 0,4L" -> "King Shake" """
                    unsafeProductTitleCleaned = matchObjectDrinksAtEnd.group(1)
                    productQuantityValue = matchObjectDrinksAtEnd.group(2)
                elif matchObjectGenericFriesQuantity:
                    """ E.g. "große KING Pommes" -> "KING Pommes" """
                    unsafeProductTitleCleaned = matchObjectGenericFriesQuantity.group(2)
                    productQuantityValue = matchObjectGenericFriesQuantity.group(1)
                elif matchObjectGenericQuantityAtBeginning:
                    """ E.g. "2 x 6 chili cheese nuggets" -> "chili cheese nuggets" """
                    unsafeProductTitleCleaned = matchObjectGenericQuantityAtBeginning.group(3)
                    productQuantityValue = matchObjectGenericQuantityAtBeginning.group(1)
                else:
                    """ unsafeProductTitleCleaned should already be fine (= doesn't contain any quantity value -> productQuantityValue == 1)!
                     2021-01-14: Yes wrong data type but at this moment we do not store this data correctly anyways so dontcare!
                     """
                    productQuantityValue = '1'
                    pass
                """ Prevent RegEx failures - remove spaces at beginning and end! """
                unsafeProductTitleCleaned = unsafeProductTitleCleaned.strip()

                """ Now check if we can find the productID for the current product! """
                foundProductID = False
                for productID in productIDsDB:
                    product = productIDsDB[productID]
                    if product['name'].lower() == unsafeProductTitleCleaned:
                        """ Success! We found the corresponding ID for the current product name! """
                        foundProductIDsMap[product['id']] = {'name': product['name'], 'quantity': productQuantityValue}
                        foundProductIDsList.append(product['id'])
                        foundProductID = True
                        break
                """ Save failed items for later """
                if not foundProductID:
                    failedUnsafeProductTitles.append(unsafeProductTitleCleaned)
            """ Log failed items """
            if len(failedUnsafeProductTitles) > 0:
                for failedUnsafeProductTitle in failedUnsafeProductTitles:
                    logging.warning('[ProductIDParserFailure] | ' + failedUnsafeProductTitle)
            elif Coupon.productIDs.name not in coupon:
                """ Update coupon in DB with new info. Only do this if we safely found all items AND they haven't been added already. """
                coupon.productIDs = foundProductIDsMap
                coupon.store(couponDB)
        logging.info('ProductID parser done')

    def couponCsvExport(self):
        """ Exports coupons DB to CSV (all headers). """
        couponDB = self.getCouponDB()
        with open('crawler/coupons.csv', 'w', newline='') as csvfile:
            fieldnames = ['PRODUCT', 'MENU', 'PLU', 'PLU2', 'TYPE', 'PRICE', 'PRICE_COMPARE', 'START', 'EXP', 'EXP2', 'EXP_PRODUCTIVE']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for couponID in couponDB:
                coupon = Coupon.load(couponDB, couponID)
                writer.writerow({'PRODUCT': coupon.title, 'MENU': coupon.containsFriesOrCoke,
                                 'PLU': (coupon.plu if coupon.plu is not None else "N/A"), 'PLU2': coupon.id,
                                 'TYPE': coupon.source,
                                 'PRICE': coupon.get(Coupon.price.name, -1), 'PRICE_COMPARE': coupon.get(Coupon.priceCompare.name, -1),
                                 'START': (coupon.dateFormattedStart if coupon.dateFormattedStart is not None else "N/A"),
                                 'EXP': (coupon.dateFormattedExpire if coupon.dateFormattedExpire is not None else "N/A"),
                                 'EXP2': (coupon.dateFormattedExpire2 if coupon.dateFormattedExpire2 is not None else "N/A"),
                                 'EXP_PRODUCTIVE': couponDBGetExpireDateFormatted(coupon)
                                 })

    def couponCsvExport2(self):
        """ Exports coupons DB to CSV (only includes 'relevant' headers). """
        couponDB = self.getCouponDB()
        with open('crawler/coupons2.csv', 'w', newline='') as csvfile:
            fieldnames = ['Produkt', 'Menü', 'PLU', 'PLU2', 'Preis', 'OPreis', 'Ablaufdatum']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for couponID in couponDB:
                coupon = Coupon.load(couponDB, couponID)
                if coupon.source != CouponSource.PAPER:
                    continue
                writer.writerow({'Produkt': coupon.title, 'Menü': coupon.containsFriesOrCoke,
                                 'PLU': coupon.plu, 'PLU2': coupon.id,
                                 'Preis': coupon.price, 'OPreis': coupon.get(Coupon.priceCompare.name, -1),
                                 'Ablaufdatum': couponDBGetExpireDateFormatted(coupon)
                                 })

    def updateUserDBNotificationFlags_DEPRECATED(self):
        """
        DEPRECATED as of 2021-05-30 but keep it just in case it's useful!
        Updates DB containing information on which user is supposed to be notified next time when e.g. a saved coupon is available again. """
        thisuserDB = self.getUsersDB()
        couponsDB = self.getCouponDB()
        numberofUsersToExpectNotifications = 0
        numberofExpectedNotifications = 0
        logging.info("Updating notifications DB")
        for userID in thisuserDB:
            userExpectsNotification = False
            user = User.load(thisuserDB, userID)
            storeNewDoc = False
            for userCouponFavoriteID in user.favoriteCoupons:
                userCouponFavorite = user.favoriteCoupons[userCouponFavoriteID]
                coupon = Coupon.load(couponsDB, userCouponFavoriteID)
                if coupon is None:
                    """ This should not happen if we treat our DB like it's designed to be treated! """
                    logging.debug("ID " + userCouponFavoriteID + " is not in our couponDB -> This should never happen")
                    continue
                elif not couponDBIsValid(coupon):
                    """ Coupon currently invalid/expire -> Set notification flag """
                    userCouponFavorite["notify"] = True
                    userExpectsNotification = True
                    numberofExpectedNotifications += 1
                    storeNewDoc = True
            if storeNewDoc:
                user.store(thisuserDB)
            if userExpectsNotification:
                numberofUsersToExpectNotifications += 1
        if numberofUsersToExpectNotifications > 0:
            logging.info("Number of users who can expect notifications: " + str(numberofUsersToExpectNotifications))
            logging.info("Number of set notification flags: " + str(numberofExpectedNotifications))
        else:
            logging.info("No new notification flags were set")
        logging.info("Notifications DB updated")

    def updateCache(self):
        """ Updates cache containing all existant coupon sources e.g. used be the Telegram bot to display them inside main menu without having to do any DB requests. """
        couponDB = self.getCouponDB()
        newCachedAvailableCouponSources = {}
        foundHiddenAppCoupons = False
        for couponID in couponDB:
            coupon = Coupon.load(couponDB, couponID)
            if couponDBIsValid(coupon):
                newCachedAvailableCouponSources.setdefault(coupon.source, {})
                if coupon.source == CouponSource.APP and coupon.isHidden:
                    foundHiddenAppCoupons = True
        # Overwrite old cache
        self.cachedAvailableCouponSources = newCachedAvailableCouponSources
        self.cachedHasHiddenAppCouponsAvailable = foundHiddenAppCoupons

    def getCouponDB(self):
        return self.couchdb[DATABASES.COUPONS]

    def getOfferDB(self):
        return self.couchdb[DATABASES.OFFERS]

    def getUsersDB(self):
        return self.couchdb[DATABASES.TELEGRAM_USERS]

    def filterCoupons(
            self, filters: CouponFilter
    ) -> dict:
        """ Use filters to only get the coupons you want.
         Returns all by default."""
        timestampStart = datetime.now().timestamp()
        couponDB = self.getCouponDB()
        # TODO: Use couchDB built in filter functions which should improve performance
        # if True:
        #     allCoupons = {}
        #     for couponID in couponDB:
        #         allCoupons[couponID] = couponDB[couponID]
        #     return allCoupons
        desiredCoupons = {}
        # if True:
        #     for uniqueCouponID in couponDB:
        #         desiredCoupons[uniqueCouponID] = couponDB[uniqueCouponID]
        #     return desiredCoupons
        namesDupeMap = {}
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            if filters.activeOnly and not couponDBIsValid(coupon):
                # Skip expired coupons if needed
                continue
            elif filters.allowedCouponSources is not None and coupon.source not in filters.allowedCouponSources:
                # Skip non-allowed coupon-types
                continue
            elif filters.containsFriesAndCoke is not None and coupon.containsFriesOrCoke != filters.containsFriesAndCoke:
                # Skip items if they do not have the expected "containsFriesOrCoke" state
                continue
            elif filters.excludeCouponsByDuplicatedProductTitles and couponDBGetComparableValue(coupon) in namesDupeMap:
                # Skip duplicates if needed
                continue
            elif filters.isNew is not None and coupon.isNew != filters.isNew:
                # Skip item if it does not have the expected "is_new" state
                continue
            elif filters.isHidden is not None and coupon.isHidden != filters.isHidden:
                continue
            else:
                desiredCoupons[uniqueCouponID] = coupon
                namesDupeMap[couponDBGetComparableValue(coupon)] = couponDBGetUniqueCouponID(coupon)
        if filters.sortMode is None:
            return desiredCoupons
        else:
            # Sort coupons: Separate by type and sort each by coupons with/without menu and price.
            filteredCouponsList = list(desiredCoupons.values())
            if filters.sortMode == CouponSortMode.SOURCE_MENU_PRICE:
                couponsWithoutFriesOrCoke = []
                couponsWithFriesOrCoke = []
                allContainedCouponSources = []
                for coupon in filteredCouponsList:
                    if coupon.source not in allContainedCouponSources:
                        allContainedCouponSources.append(coupon.source)
                    if coupon.containsFriesOrCoke:
                        couponsWithFriesOrCoke.append(coupon)
                    else:
                        couponsWithoutFriesOrCoke.append(coupon)
                couponsWithoutFriesOrCoke = sortCouponsByPrice(couponsWithoutFriesOrCoke)
                couponsWithFriesOrCoke = sortCouponsByPrice(couponsWithFriesOrCoke)
                # Merge them together again.
                filteredCouponsList = couponsWithoutFriesOrCoke + couponsWithFriesOrCoke
                # App coupons(source == 0) > Paper coupons
                allContainedCouponSources.sort()
                # Separate sorted coupons by type
                couponsSeparatedByType = {}
                for couponSource in allContainedCouponSources:
                    couponsTmp = list(filter(lambda x: x.source == couponSource, filteredCouponsList))
                    couponsSeparatedByType[couponSource] = couponsTmp
                # Put our list sorted by type together again -> Sort done
                filteredCouponsList = []
                for allCouponsOfOneSourceType in couponsSeparatedByType.values():
                    filteredCouponsList += allCouponsOfOneSourceType
            elif filters.sortMode == CouponSortMode.MENU_PRICE:
                couponsWithoutFriesOrCoke = []
                couponsWithFriesOrCoke = []
                for coupon in filteredCouponsList:
                    if coupon.containsFriesOrCoke:
                        couponsWithFriesOrCoke.append(coupon)
                    else:
                        couponsWithoutFriesOrCoke.append(coupon)
                couponsWithoutFriesOrCoke = sortCouponsByPrice(couponsWithoutFriesOrCoke)
                couponsWithFriesOrCoke = sortCouponsByPrice(couponsWithFriesOrCoke)
                # Merge them together again.
                filteredCouponsList = couponsWithoutFriesOrCoke + couponsWithFriesOrCoke
            elif filters.sortMode == CouponSortMode.PRICE:
                filteredCouponsList = sortCouponsByPrice(filteredCouponsList)
            else:
                # This should never happen
                logging.warning("Developer mistake!! Unknown sortMode: " + filters.sortMode.name)
            # Make dict out of list
            filteredAndSortedCouponsDict = {}
            for coupon in filteredCouponsList:
                filteredAndSortedCouponsDict[coupon.id] = coupon
            logging.debug("Time it took to get- and sort coupons: " + getFormattedPassedTime(timestampStart))
            return filteredAndSortedCouponsDict

    def filterCouponsList(
            self, filters: CouponFilter
    ) -> List[dict]:
        """ Wrapper for filterCoupons """
        filteredCouponsDict = self.filterCoupons(filters)
        return list(filteredCouponsDict.values())

    def getOffersActive(self) -> list:
        """ Returns all offers that are not expired according to 'expiration_date'. """
        offerDB = self.getOfferDB()
        offers = []
        for offerID in offerDB:
            offer = offerDB[offerID]
            if offerIsValid(offer):
                offers.append(offer)
        return offers

    def getUserFavorites(self, user: User, coupons: Union[dict, None]=None) -> UserFavorites:
        """
        Gathers information about the given users' favorite available/unavailable coupons.
        """
        if len(user.favoriteCoupons) == 0:
            # User does not have any favorites set --> There is no point to look for the additional information
            return UserFavorites()
        # Get coupons if they're not given already
        if coupons is None:
            coupons = self.filterCoupons(CouponFilter(activeOnly=True, allowedCouponSources=BotAllowedCouponSources, sortMode=CouponSortMode.PRICE))
        availableFavoriteCoupons = []
        unavailableFavoriteCoupons = []
        for uniqueCouponID, coupon in user.favoriteCoupons.items():
            couponFromProductiveDB = coupons.get(uniqueCouponID)
            if couponFromProductiveDB is not None and isValidBotCoupon(couponFromProductiveDB):
                availableFavoriteCoupons.append(couponFromProductiveDB)
            else:
                # User chosen favorite coupon has expired or is not in DB
                coupon = Coupon.wrap(coupon)  # We want a 'real' coupon object
                unavailableFavoriteCoupons.append(coupon)
        availableFavoriteCoupons = sortCouponsByPrice(availableFavoriteCoupons)
        return UserFavorites(favoritesAvailable=availableFavoriteCoupons, favoritesUnavailable=unavailableFavoriteCoupons)


def sortCouponsByPrice(couponList: List[Coupon]) -> List[Coupon]:
    # Sort by price -> But price is not always given -> Place items without prices at the BEGINNING of each list.
    return sorted(couponList, key=lambda x: -1 if x.get(Coupon.price.name, -1) is None else x.get(Coupon.price.name, -1))


def hasChanged(originalData, newData, ignoreKeys=None) -> bool:
    """ Returns True if a key of newData is not on originalData or a value has changed. """
    if ignoreKeys is None:
        ignoreKeys = []
    for key in newData:
        if key in ignoreKeys:
            continue
        newValue = newData[key]
        if key not in originalData:
            return True
        elif newValue != originalData[key]:
            return True
    return False


def downloadImageIfNonExistant(url: str, path: str) -> bool:
    try:
        if os.path.exists(path):
            # Image already exists
            return False
        else:
            logging.info('Downloading image to: ' + path)
            r = requests.get(url, allow_redirects=True)
            open(path, mode='wb').write(r.content)
            # Check for broken image and delete it if broken
            # TODO: Solve this in a more elegant way so we do not even write/store broken image files in the first place(?!)
            if isValidImageFile(path):
                return True
            else:
                logging.warning("Image is broken: Deleting broken image: " + path)
                os.remove(path)
                return False
    except:
        traceback.print_exc()
        logging.warning("Image download failed")
        return False


def generateQRImageIfNonExistant(qrCodeData: str, path: str) -> bool:
    if os.path.exists(path):
        return False
    else:
        qr = qrcode.QRCode(
            version=1,
            # 2021-05-02: This makes the image itself bigger but due to the border and the resize of Telegram, these QR codes might be suited better for usage in Telegram
            border=10
        )
        qr.add_data(qrCodeData)
        """ 2021-01-25: Use the same color they're using in their app. """
        img = qr.make_image(fill_color="#4A1E0D", back_color="white")
        img.save(path)
        return True


if __name__ == '__main__':
    crawler = BKCrawler()
    crawler.setCrawlOnlyBotCompatibleCoupons(True)
    crawler.setExportCSVs(False)
    crawler.setKeepHistory(False)

    # 2021-08-20: JokerGermany goodie:
    # crawler.setExportCSVs(True)
    # crawler.setCrawlOnlyBotCompatibleCoupons(False)
    userDB = crawler.getUsersDB()
    print("Number of userIDs in DB: " + str(len(userDB)))
    crawler.crawlAndProcessData()
    print("Crawler done!")
