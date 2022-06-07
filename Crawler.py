import csv
import logging
import traceback
from typing import List

import qrcode
import requests
from couchdb import Document, Database
from hyper import HTTP20Connection  # we're using hyper instead of requests because of its' HTTP/2.0 capability

import couchdb
from json import loads

import PaperCouponHelper
from BotUtils import Config, getImageBasePath
from Helper import *
from Helper import getPathImagesOffers, getPathImagesProducts, couponTitleContainsFriesOrCoke, \
    isCouponShortPLUWithAtLeastOneLetter, isValidImageFile, BotAllowedCouponTypes, CouponType, Paths
from UtilsCoupons2 import coupon2GetDatetimeFromString, coupon2FixProductTitle
from UtilsOffers import offerGetImagePath, offerIsValid
from UtilsCoupons import couponGetUniqueCouponID, couponGetTitleFull, \
    couponGetExpireDatetime, couponGetStartTimestamp
from UtilsCouponsDB import Coupon, InfoEntry, CouponSortMode, sortCouponsByPrice, CouponFilter, getCouponTitleMapping, User, removeDuplicatedCoupons
from CouponCategory import CouponCategory

HEADERS_OLD = {"User-Agent": "BurgerKing/6.7.0 (de.burgerking.kingfinder; build:432; Android 8.0.0) okhttp/3.12.3"}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36",
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
           "x-ui-region": "DE",
           "": ""}
# x-user-datetime: 2022-03-16T20:59:45+01:00
""" Enable this to crawl from localhost instead of API. Useful if there is a lot of testing to do! """
DEBUGCRAWLER = False


class UserStats:
    """ Returns an object containing statistic data about given users Database instance. """

    def __init__(self, usrDB: Database):
        self.numberofUsersWhoFoundEasterEgg = 0
        self.numberofFavorites = 0
        self.numberofUsersWhoBlockedBot = 0
        self.numberofUsersWhoAddedPaybackCard = 0
        for userID in usrDB:
            userTmp = User.load(usrDB, userID)
            if userTmp.hasFoundEasterEgg():
                self.numberofUsersWhoFoundEasterEgg += 1
            self.numberofFavorites += len(userTmp.favoriteCoupons)
            if userTmp.hasProbablyBlockedBot():
                self.numberofUsersWhoBlockedBot += 1
            userTmp.getPaybackCardNumber()
            if userTmp.getPaybackCardNumber() is not None:
                self.numberofUsersWhoAddedPaybackCard += 1


class BKCrawler:

    def __init__(self):
        self.cfg = loadConfig()
        if self.cfg is None or self.cfg.get(Config.DB_URL) is None:
            raise Exception('Broken or missing config')
        # Init DB
        self.couchdb = couchdb.Server(self.cfg[Config.DB_URL])
        self.cachedAvailableCouponCategories = {}
        self.keepHistory = False
        self.crawlOnlyBotCompatibleCoupons = True
        self.storeCouponAPIDataAsJson = False
        self.exportCSVs = False
        self.missingPaperCouponPLUs = []
        # Create required DBs
        if DATABASES.INFO_DB not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.INFO_DB)
            infoDB = self.couchdb.create(DATABASES.INFO_DB)
        else:
            infoDB = self.couchdb[DATABASES.INFO_DB]
        # Special case: Not only do we need to make sure that this DB exists but also need to add this special doc
        if DATABASES.INFO_DB not in infoDB:
            infoDoc = InfoEntry(id=DATABASES.INFO_DB)
            infoDoc.store(self.couchdb[DATABASES.INFO_DB])
        if DATABASES.TELEGRAM_USERS not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.TELEGRAM_USERS)
            self.couchdb.create(DATABASES.TELEGRAM_USERS)
        if DATABASES.COUPONS not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.COUPONS)
            self.couchdb.create(DATABASES.COUPONS)
        if DATABASES.OFFERS not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.OFFERS)
            self.couchdb.create(DATABASES.OFFERS)
        if DATABASES.COUPONS_HISTORY not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.COUPONS_HISTORY)
            self.couchdb.create(DATABASES.COUPONS_HISTORY)
        if DATABASES.PRODUCTS not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.PRODUCTS)
            self.couchdb.create(DATABASES.PRODUCTS)
        if DATABASES.PRODUCTS_HISTORY not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.PRODUCTS_HISTORY)
            self.couchdb.create(DATABASES.PRODUCTS_HISTORY)
        if DATABASES.PRODUCTS2_HISTORY not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.PRODUCTS2_HISTORY)
            self.couchdb.create(DATABASES.PRODUCTS2_HISTORY)
        if DATABASES.TELEGRAM_CHANNEL not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.TELEGRAM_CHANNEL)
            self.couchdb.create(DATABASES.TELEGRAM_CHANNEL)
        # Test 2022-06-05 to find invalid datasets
        # userDB = self.couchdb[DATABASES.TELEGRAM_USERS]
        # if os.path.exists('telegram_users.json'):
        #     usersOld = loadJson("telegram_users.json")['docs']
        #     for userO in usersOld:
        #         user = User.wrap(userO)
        #         del user.data['_rev']
        #         if user.id not in userDB:
        #             logging.info("Adding new user: " + str(user.id))
        #             user.store(userDB)

        # Create required folders
        if not os.path.exists(getImageBasePath()):
            logging.info("Creating missing filepath: " + getImageBasePath())
            os.makedirs(getImageBasePath())
        if not os.path.exists(getPathImagesOffers()):
            logging.info("Creating missing filepath: " + getPathImagesOffers())
            os.makedirs(getPathImagesOffers())
        if not os.path.exists(getPathImagesProducts()):
            logging.info("Creating missing filepath: " + getPathImagesProducts())
            os.makedirs(getPathImagesProducts())
        # Do this here so manually added coupons will get added on application start without extra crawl process
        self.addExtraCoupons(crawledCouponsDict={}, immediatelyAddToDB=True)
        # Make sure that our cache gets filled on init
        couponDB = self.getCouponDB()
        self.updateCache(couponDB)
        self.updateCachedMissingPaperCouponsInfo(couponDB)

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
        useNewAPI = False
        crawledCouponsDict = {}
        if useNewAPI:
            self.crawlCoupons1New(crawledCouponsDict)
        else:
            """ Using public API: https://gist.github.com/max1220/7f2f65be4381bc0878e64a985fd71da4 """
            conn = HTTP20Connection('mo.burgerking-app.eu')
            conn.request("GET", '/api/v2/coupons', headers=HEADERS_OLD)
            apiResponse = loads(conn.get_response().read())
            if self.storeCouponAPIDataAsJson:
                # Save API response so we can easily use this data for local testing later on.
                saveJson('crawler/coupons1_old.json', apiResponse)
            self.crawlProcessOffers(apiResponse)
            self.crawlCoupons1(apiResponse, crawledCouponsDict)
            logging.info('App API Crawling done')
            self.crawlCoupons2(crawledCouponsDict)
        self.addExtraCoupons(crawledCouponsDict=crawledCouponsDict, immediatelyAddToDB=False)
        self.processCrawledCoupons(crawledCouponsDict)
        # self.crawlProducts()

    def downloadProductiveCouponDBImagesAndCreateQRCodes(self):
        """ Downloads coupons images and generates QR codes for current productive coupon DB. """
        timestampStart = datetime.now().timestamp()
        couponDB = self.getCouponDB()
        numberofDownloadedImages = 0
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            if downloadCouponImageIfNonExistant(coupon):
                numberofDownloadedImages += 1
            generateQRImageIfNonExistant(uniqueCouponID, coupon.getImagePathQR())
        if numberofDownloadedImages > 0:
            logging.info("Number of coupon images downloaded: " + str(numberofDownloadedImages))
            logging.info("Download image files duration: " + getFormattedPassedTime(timestampStart))

    def migrateDBs(self):
        """ Migrate DBs from old to new version - leave this function empty if there is nothing to migrate. """
        # logging.info("Migrating DBs...")
        # logging.info("Migrate DBs done")
        # 2022-01-16: Not required anymore
        # userDB = self.getUsersDB()
        # keysMapping = {"timestampExpire": "timestampExpireInternal", "dateFormattedExpire": "dateFormattedExpireInternal", "timestampExpire2": "timestampExpire", "dateFormattedExpire2": "dateFormattedExpire"}
        # for userID in userDB:
        #     user = User.load(userDB, userID)
        #     needsUpdate = False
        #     for couponData in user.favoriteCoupons.values():
        #         for oldKey, newKey in keysMapping.items():
        #             valueOfOldKey = couponData.get(oldKey)
        #             if valueOfOldKey is not None:
        #                 needsUpdate = True
        #                 couponData[newKey] = valueOfOldKey
        #                 del couponData[oldKey]
        #     if needsUpdate:
        #         user.store(userDB)
        pass

    def crawlAndProcessData(self):
        """ One function that does it all! Execute this every time you run the crawler. """
        try:
            timestampStart = datetime.now().timestamp()
            self.migrateDBs()
            self.crawl()
            if self.exportCSVs:
                self.couponCsvExport()
                self.couponCsvExport2()
            self.downloadProductiveCouponDBImagesAndCreateQRCodes()
            # self.checkProductiveCouponsDBImagesIntegrity()
            # self.checkProductiveOffersDBImagesIntegrity()
            logging.info("Total crawl duration: " + getFormattedPassedTime(timestampStart))
        finally:
            self.updateCache(self.getCouponDB())

    def crawlCoupons1New(self, crawledCouponsDict: dict):
        """ Stores coupons from App API, generates- and adds some special strings to DB for later usage.
         This is work in progress. Does not work yet!!
         """
        timestampCrawlStart = datetime.now().timestamp()
        conn = HTTP20Connection('euc1-prod-bk.rbictg.com')
        conn.request("POST", '/graphql', body="TODO"
                     , headers=HEADERS)
        apiResponse = loads(conn.get_response().read())
        if self.storeCouponAPIDataAsJson:
            # Save API response so we can easily use this data for local testing later on.
            saveJson('crawler/coupons1.json', apiResponse)
        offersFeedback = apiResponse['data']['evaluateAllUserOffers']['offersFeedback']
        couponJsons = []
        for offerFeedback in offersFeedback:
            couponJsons.append(offerFeedback['offerDetails'])
        appCoupons = []
        for couponJson in couponJsons:
            couponBK = loads(couponJson)
            try:
                uniqueCouponID = couponBK['vendorConfigs']['rpos']['constantPlu']
                title = couponBK['name']['de'].get(0)['children'].get(0)['text']
                subtitle = couponBK['description']['de'].get(0)['children'].get(0)['text']
                titleFull = sanitizeCouponTitle(title + subtitle)
                imageURL = couponBK['localizedImage']['de']['app']['asset']['url']
                newCoupon = Coupon(id=uniqueCouponID, uniqueID=uniqueCouponID, plu=couponBK['shortCode'], title=titleFull, titleShortened=shortenProductNames(titleFull),
                                   type=CouponType.APP, price=couponBK['offerPrice'])
                newCoupon.imageURL = imageURL
                # Find expire-date
                ruleSets = couponBK['ruleSet']
                for ruleSet in ruleSets:
                    if ruleSet['_type'] != 'between-dates':
                        continue
                    # see startDate and endDate given in format: 2022-01-31T01:00:00.000Z
                    break
                newCoupon.containsFriesOrCoke = couponTitleContainsFriesOrCoke(titleFull)
                crawledCouponsDict[uniqueCouponID] = newCoupon
            except:
                logging.warning("Got unexpected json structure")
                pass
        logging.info('Coupons in app: ' + str(len(appCoupons)))
        logging.info("Total coupons1 crawl time: " + getFormattedPassedTime(timestampCrawlStart))

    def crawlCoupons1(self, apiResponse: dict, crawledCouponsDict: dict):
        """ Stores coupons from App API, generates- and adds some special strings to DB for later usage. """
        timestampCrawlStart = datetime.now().timestamp()
        appCoupons = apiResponse['coupons']
        appCouponsIDs = []
        logging.info("Crawling old app coupons...")
        for coupon in appCoupons:
            uniqueCouponID = couponGetUniqueCouponID(coupon)
            appCouponsIDs.append(uniqueCouponID)
            titleFull = sanitizeCouponTitle(couponGetTitleFull(coupon))
            newCoupon = Coupon(id=uniqueCouponID, uniqueID=uniqueCouponID, plu=coupon['plu'], title=titleFull, titleShortened=shortenProductNames(titleFull),
                               type=CouponType.APP, isHidden=coupon['hidden'])
            expireDatetime = couponGetExpireDatetime(coupon)
            if expireDatetime is not None:
                newCoupon.timestampExpire = expireDatetime.timestamp()
                newCoupon.dateFormattedExpire = formatDateGerman(expireDatetime)
            timestampStart = couponGetStartTimestamp(coupon)
            if timestampStart > -1:
                newCoupon.timestampStart = timestampStart
                newCoupon.dateFormattedStart = formatDateGerman(datetime.fromtimestamp(timestampStart))
            newCoupon.containsFriesOrCoke = couponTitleContainsFriesOrCoke(titleFull)
            newCoupon.imageURL = couponOrOfferGetImageURL(coupon)
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
                    logging.warning("WTF inconsistent App API response in object: " + uniqueCouponID)
            crawledCouponsDict[uniqueCouponID] = newCoupon
        logging.info('Coupons in old app API: ' + str(len(appCoupons)))
        logging.info("Total coupons1_old crawl time: " + getFormattedPassedTime(timestampCrawlStart))

    def crawlCoupons2(self, crawledCouponsDict: dict):
        """ Crawls coupons from secondary sources and adds additional information to the data crawled via app API.
         Main purpose: Crawl paper coupons """
        timestampStart = datetime.now().timestamp()
        logging.info("Collecting stores to crawl coupons from...")
        if DEBUGCRAWLER:
            # storeIDs = [682, 4108, 514]
            storeIDs = [666]
        else:
            conn = HTTP20Connection('api.burgerking.de')
            """ Returns List of all stores """
            conn.request("GET", '/api/o2uvrPdUY57J5WwYs6NtzZ2Knk7TnAUY/v2/de/de/stores/', headers=HEADERS_OLD)
            stores = loads(conn.get_response().read())
            storeIDs = []
            # Collect storeIDs from which we can obtain coupons
            for store in stores:
                properties = store['properties']
                """ 2021-02-24: Only such stores will present us with an online list of products and coupons -> Only stores with mobileOrdering is called "Vorbestellen/Vorbestellung" in their app. """
                if 'mobileOrdering' in properties or 'paperCoupons' in properties:
                    storeIDs.append(store['id'])
        if len(storeIDs) == 0 or len(storeIDs) > 100:
            # 2021-07-22: Workaround
            logging.warning("Using store-crawler workaround/fallback!")
            storeIDs = [682, 4108, 514]
        if len(storeIDs) == 0:
            # This should never happen!
            logging.warning("Failed to find any storeIDs to crawl coupons from!")
            return
        logging.info("Found " + str(len(storeIDs)) + " stores to crawl coupons from")
        logging.info("Crawling coupons2...")
        # Contains the original unmodified DB data
        allProducts = {}
        allCouponIDs = []
        # The more stores we crawl coupons from the longer it takes -> Limit that (set this to -1 to crawl all stores that are providing coupons). This can take a lot of time so without threading we won't be able to crawl all coupons from all stores for our bot (TG channel)!
        maxNumberofStoresToCrawlCouponsFrom = 2
        numberofAddedCoupons = 0
        numberofSeenCoupons = 0
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
                conn.request("GET", '/api/v2/stores/' + str(storeID) + '/menu', headers=HEADERS_OLD)
                apiResponse = loads(conn.get_response().read())
                if self.storeCouponAPIDataAsJson:
                    # Save API response so we can easily use this data for local testing later on.
                    saveJson('crawler/coupons2_latest.json', apiResponse)
                    saveJson('crawler/coupons2_' + str(storeID) + '.json', apiResponse)
            products = apiResponse.get('products')
            coupons = apiResponse.get('coupons')
            if products is None or coupons is None:
                # This should never happen!
                logging.warning("Failed to obtain coupons from this store -> Skipping it")
                continue
            # Collect all productIDs to separate dict for later usage
            for productIDTmp, productTmp in products.items():
                allProducts[productIDTmp] = productTmp
            # Collect all coupon objects and apply slight corrections
            numberofNewCouponsInCurrentStore = 0
            for coupon in coupons:
                numberofSeenCoupons += 1
                productID = coupon['product_id']
                uniqueCouponID = coupon['promo_code']
                plu = coupon['store_promo_code']
                """ Find the product which belongs to this coupon (basically a dataset containing more details). """
                product = products.get(str(productID))
                if product is None or len(product) == 0:
                    # This should never happen
                    logging.warning("WTF failed to find product for couponID: " + uniqueCouponID)
                    continue
                if plu.isdecimal() and isCouponShortPLUWithAtLeastOneLetter(uniqueCouponID):
                    # Let's fix Burger Kings database errors!
                    logging.debug("Found swapped plu/uniqueID: " + plu + " / " + uniqueCouponID)
                    newplu = uniqueCouponID
                    uniqueCouponID = plu
                    plu = newplu
                elif not uniqueCouponID.isdecimal():
                    # This should never ever happen!
                    logging.warning("WTF uniqueCouponID has unexpected format")
                    continue
                title = product['name']
                price = product['price']
                image_url = product['image_url']
                startDate = coupon2GetDatetimeFromString(coupon['start_date'])
                expirationDate = coupon2GetDatetimeFromString(coupon['expiration_date'])
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
                            productTmp = allProducts.get(str(product_idTmp))
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
                existantCoupon = crawledCouponsDict.get(uniqueCouponID)
                if existantCoupon is not None and existantCoupon.isValid() and existantCoupon.getCouponType() == CouponType.APP:
                    # Update existing app coupon with new information.
                    if existantCoupon.price is None:
                        # 201-07-06: Only update current price if we failed to find it before as entrys of this APIs can sometimes be wrong (e.g. for 32749: 4,99€ according to this API but 9,89€ according to API)
                        existantCoupon.price = price
                    elif price != existantCoupon.price:
                        # Rare case
                        logging.warning("Detected API price difference for coupon " + existantCoupon.id + " | App: " + str(existantCoupon.price) + " | API2: " + str(price))
                    if priceCompare > 0:
                        existantCoupon.priceCompare = priceCompare
                else:
                    # Add/Update non-App coupons
                    newCoupon = Coupon(id=uniqueCouponID, type=CouponType.UNKNOWN, uniqueID=uniqueCouponID, plu=plu, title=title, titleShortened=shortenProductNames(title),
                                       timestampStart=expirationDate.timestamp(), timestampExpire=expirationDate.timestamp(),
                                       dateFormattedStart=formatDateGerman(startDate), dateFormattedExpire=formatDateGerman(expirationDate),
                                       price=price, containsFriesOrCoke=couponTitleContainsFriesOrCoke(title))
                    if priceCompare > 0:
                        newCoupon.priceCompare = priceCompare
                    newCoupon.imageURL = image_url
                    if uniqueCouponID not in crawledCouponsDict:
                        numberofAddedCoupons += 1
                        crawledCouponsDict[uniqueCouponID] = newCoupon
                        allCouponIDs.append(uniqueCouponID)
                        numberofNewCouponsInCurrentStore += 1
            logging.info("Found coupons2 so far: " + str(numberofAddedCoupons) + " | Total seen: " + str(numberofSeenCoupons))
            if numberofNewCouponsInCurrentStore > 0:
                logging.info("Number of new coupon IDs in current store: " + str(numberofNewCouponsInCurrentStore))
            if storeIndex + 1 >= maxNumberofStoresToCrawlCouponsFrom:
                logging.info("Stopping store coupon crawling because reached store limit of: " + str(maxNumberofStoresToCrawlCouponsFrom))
                break

        # Update history if needed
        if self.keepHistory:
            timestampHistoryDBUpdateStart = datetime.now().timestamp()
            logging.info("Updating history DB products2")
            dbHistoryProducts2 = self.couchdb[DATABASES.PRODUCTS2_HISTORY]
            for itemID, product in allProducts.items():
                self.updateHistoryEntry(dbHistoryProducts2, itemID, product)
            logging.info("Time it took to update products2 history DB: " + getFormattedPassedTime(timestampHistoryDBUpdateStart))
        logging.info("API Crawling 2 done | Total coupons2 crawl time: " + getFormattedPassedTime(timestampStart))

    def addExtraCoupons(self, crawledCouponsDict: dict, immediatelyAddToDB: bool):
        """ Adds extra coupons which have been manually added to config_extra_coupons.json.
         This will only add VALID coupons to DB! """
        # First prepare extra coupons config because manual steps are involved to make this work
        PaperCouponHelper.main()
        extraCouponData = loadJson(Paths.extraCouponConfigPath)
        extraCouponsJson = extraCouponData["extra_coupons"]
        extraCouponsToAdd = self.getValidExtraCoupons()
        for coupon in extraCouponsToAdd.values():
            crawledCouponsDict[coupon.uniqueID] = coupon
        if immediatelyAddToDB and len(extraCouponsToAdd) > 0:
            # Add items to DB
            couponDB = self.getCouponDB()
            dbUpdates = []
            for coupon in extraCouponsToAdd.values():
                existantCoupon = Coupon.load(couponDB, coupon.id)
                if existantCoupon is None:
                    dbUpdates.append(coupon)
                elif existantCoupon is not None and hasChanged(existantCoupon, coupon):
                    # Put rev of existing coupon into 'new' object otherwise DB update will throw Exception.
                    coupon["_rev"] = existantCoupon.rev
                    dbUpdates.append(coupon)
            if len(dbUpdates) > 0:
                couponDB.update(dbUpdates)
                logging.info("Pushed " + str(len(dbUpdates)) + " extra coupons DB updates")
                # Important!
                self.downloadProductiveCouponDBImagesAndCreateQRCodes()

    def getValidExtraCoupons(self) -> dict:
        PaperCouponHelper.main()
        extraCouponData = loadJson(Paths.extraCouponConfigPath)
        extraCouponsJson = extraCouponData["extra_coupons"]
        validExtraCoupons = {}
        for extraCouponJson in extraCouponsJson:
            coupon = Coupon.wrap(extraCouponJson)
            coupon.id = coupon.uniqueID  # Set custom uniqueID otherwise couchDB will create one later -> This is not what we want to happen!!
            coupon.title = sanitizeCouponTitle(coupon.title)
            coupon.titleShortened = shortenProductNames(coupon.title)
            coupon.containsFriesOrCoke = couponTitleContainsFriesOrCoke(coupon.title)
            expiredateStr = extraCouponJson["expire_date"] + " 23:59:59"
            expiredate = datetime.strptime(expiredateStr, '%Y-%m-%d %H:%M:%S').astimezone(getTimezone())
            coupon.timestampExpire = expiredate.timestamp()
            coupon.dateFormattedExpire = formatDateGerman(expiredate)
            # Only add coupon if it is valid
            if coupon.isValid():
                validExtraCoupons[coupon.uniqueID] = coupon
        return validExtraCoupons

    def processCrawledCoupons(self, crawledCouponsDict: dict):
        """ Process crawled coupons: Apply necessary corrections and update DB. """
        timestampStart = datetime.now().timestamp()
        # Detect paper coupons
        paperCouponMapping = getCouponMappingForCrawler()
        usedMappingToFindPaperCoupons = False
        for coupon in crawledCouponsDict.values():
            paperCouponOverride = paperCouponMapping.get(coupon.id)
            if paperCouponOverride is not None:
                usedMappingToFindPaperCoupons = True
                coupon.type = CouponType.PAPER
                coupon.timestampExpire = paperCouponOverride.timestampExpire
                coupon.dateFormattedExpire = paperCouponOverride.dateFormattedExpire
                coupon.plu = paperCouponOverride.plu

        foundPaperCoupons = []
        if usedMappingToFindPaperCoupons:
            # New/current handling
            for crawledCoupon in crawledCouponsDict.values():
                if crawledCoupon.type == CouponType.PAPER:
                    foundPaperCoupons.append(crawledCoupon)
        else:
            # Old/fallback handling -> DEPRECATED
            # Create a map containing char -> coupons e.g. {"X": {"plu": "1234"}}
            pluCharMap = {}
            for uniqueCouponID, coupon in crawledCouponsDict.items():
                # Check if we got a valid "paper PLU"
                firstLetterOfPLU = coupon.getFirstLetterOfPLU()
                if firstLetterOfPLU is not None:
                    pluCharMap.setdefault(firstLetterOfPLU, []).append(coupon)
            # Remove all results that cannot be paper coupons by length
            for pluIdentifier, coupons in pluCharMap.copy().items():
                if len(coupons) != 46 and len(coupons) != 47:
                    del pluCharMap[pluIdentifier]
            """ Now do some workarounds/corrections of our results.
             This was necessary because as of 09-2021 e.g. current paper coupons' PLUs started with letter "A" but were listed with letter "F" in the BK DB.
             """
            # corrections = {"F": "A"}
            corrections = {}  # 2021-11-28: No corrections required
            if len(corrections) > 0:
                paperCouponConfig = PaperCouponHelper.getActivePaperCouponInfo()
                for oldChar, newChar in corrections.items():
                    if oldChar in pluCharMap and newChar in paperCouponConfig.keys():
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
            # Store possible paper coupon short-PLU numbers without chars e.g. {"B": [1, 2, 3], "C": [1, 2, 3] }
            foundPaperCouponMap = {}
            if len(pluCharMap) == 0:
                logging.info("Failed to find any currently valid paper coupon candidates")
            else:
                # Logging
                couponCharsLogtext = ''
                for paperPLUChar, coupons in pluCharMap.items():
                    if len(couponCharsLogtext) > 0:
                        couponCharsLogtext += ', '
                    couponCharsLogtext += paperPLUChar + "(" + str(len(coupons)) + " items)"
                logging.info("Auto-found the following " + str(len(pluCharMap)) + " possible paper coupon char(s): " + couponCharsLogtext)
                allowAutoDetectedPaperCoupons = False  # 2021-11-15: Added this switch as their DB is f*cked at this moment so the auto-detection found wrong coupons.
                # Evaluate our findings
                if allowAutoDetectedPaperCoupons:
                    for paperPLUChar, paperCoupons in pluCharMap.items():
                        # We assume that these coupons are paper coupons
                        logging.info("Auto detected paper coupon char is: " + paperPLUChar)
                        # Update data of these coupons and add them to DB later
                        # https://www.quora.com/In-Python-what-is-the-cleanest-way-to-get-a-datetime-for-the-start-of-today
                        today = datetime.today()  # or datetime.now to use local timezone
                        todayDayEnd = datetime(year=today.year, month=today.month,
                                               day=today.day, hour=23, minute=59, second=59)
                        # Add them with fake validity of 2 days
                        artificialExpireTimestamp = todayDayEnd.timestamp() + 2 * 24 * 60
                        for paperCoupon in paperCoupons:
                            paperCoupon.type = CouponType.PAPER
                            paperCoupon.timestampExpire = artificialExpireTimestamp
                            paperCoupon.dateFormattedExpire = formatDateGerman(datetime.fromtimestamp(artificialExpireTimestamp))
                            paperCoupon.isUnsafeExpiredate = True
                            paperCoupon.description = SYMBOLS.INFORMATION + "Das hier eingetragene Ablaufdatum ist vorläufig und wird zeitnah korrigiert!"
                        foundPaperCouponMap[paperPLUChar] = paperCoupons
            if len(paperCouponMapping) > 0 and len(foundPaperCouponMap) == 0:
                # This should never happen
                logging.warning("Failed to find any paper coupons alhough we expect some to be there!")

            """ Check for missing paper coupons based on the ones we found.
            2021-09-29: Now we do filter by array size before so this handling is pretty much useless but let's keep it anyways.
            """
            logging.debug("Looking for missing paper coupons...")
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
                    paybackDummyPLUNumber = 47
                    # paybackDummyPLU = paperChar + str(paybackDummyPLUNumber) --> C47
                    for numberToCheck in range(1, highestPaperPLUNumber + 1):
                        if numberToCheck == paybackDummyPLUNumber:
                            # Skip this
                            continue
                        plu = paperChar + str(numberToCheck)
                        if numberToCheck not in paperCouponNumbersList:
                            missingPaperPLUs.append(plu)
                    if len(missingPaperPLUs) > 0:
                        logging.info("Paper coupons NOT OK: " + paperChar + " | Found items: " + str(len(paperCoupons)) + " | Possibly missing PLUs: " + str(missingPaperPLUs))
                        for missingPaperPLU in missingPaperPLUs:
                            self.missingPaperCouponPLUs.append(missingPaperPLU)
                else:
                    # Looks like we found all paper coupons :)
                    logging.info("Paper coupons OK: " + paperChar + " [" + str(len(paperCoupons)) + "]")
            for paperCoupons in foundPaperCouponMap.values():
                for paperCoupon in paperCoupons:
                    foundPaperCoupons.append(paperCoupon)
        logging.info('Detected ' + str(len(foundPaperCoupons)) + ' paper coupons')
        """ Now tag original price values for 'duplicated' coupons: If we got two coupons containing the same product but we only found the original price for one of them,
         we can set this on the other one(s) too. """
        couponTitleMapping = getCouponTitleMapping(crawledCouponsDict)
        for couponsContainingSameProducts in couponTitleMapping.values():
            if len(couponsContainingSameProducts) > 1:
                originalPrice = None
                for coupon in couponsContainingSameProducts:
                    if originalPrice is None:
                        originalPrice = coupon.getPriceCompare()
                if originalPrice is not None:
                    for coupon in couponsContainingSameProducts:
                        if coupon.getPriceCompare() is None:
                            coupon.priceCompare = originalPrice
        # Collect items we want to add to DB
        couponsToAddToDB = {}
        if self.crawlOnlyBotCompatibleCoupons:
            for coupon in crawledCouponsDict.values():
                if coupon.isValidForBot():
                    couponsToAddToDB[coupon.id] = coupon
        else:
            # Add all crawled coupons to DB
            couponsToAddToDB = crawledCouponsDict
        infoDatabase = self.couchdb[DATABASES.INFO_DB]
        infoDBDoc = InfoEntry.load(infoDatabase, DATABASES.INFO_DB)
        couponDB = self.getCouponDB()
        numberofCouponsNew = 0
        numberofCouponsUpdated = 0
        numberofCouponsFlaggedAsNew = 0
        dbUpdates = []
        # Now collect all resulting DB updates, set isNew flags and update DB
        newCouponIDs = []
        updatedCouponIDs = []
        """ Only flag coupons as new if either some coupons have been in our DB before or this is the first run ever.
        Prevents flagging all coupons as new if e.g. DB has been dumped before during debugging.
        """
        validExtraCoupons = self.getValidExtraCoupons()
        dbContainsOnlyExtraCoupons = False
        if len(validExtraCoupons) > 0:
            dbContainsOnlyExtraCoupons = True
            for couponID in couponDB:
                if couponID not in validExtraCoupons:
                    dbContainsOnlyExtraCoupons = False
                    break
        flagNewCouponsAsNew = None
        if infoDBDoc.timestampLastCrawl == -1:
            # First start: Allow to flag new coupons as new
            flagNewCouponsAsNew = True
        elif len(couponDB) > 0 and not dbContainsOnlyExtraCoupons:
            # Allow to flag new coupons as new (new = has not been in DB before)
            flagNewCouponsAsNew = True
        else:
            """ DB is empty or contains only extraCoupons which will get added on application launch
            --> Flag only existing expired coupons as new """
            flagNewCouponsAsNew = False
            logging.info("Not flagging new coupons as new in this run!!")
        for crawledCoupon in couponsToAddToDB.values():
            existentCoupon = Coupon.load(couponDB, crawledCoupon.id)
            # Update DB
            if existentCoupon is not None:
                # Update existing coupon
                if hasChanged(existentCoupon, crawledCoupon):
                    # Set isNew flag if necessary
                    if not existentCoupon.isValid() and crawledCoupon.isValid():
                        crawledCoupon.isNew = True
                        numberofCouponsFlaggedAsNew += 1
                    # Important: We need the "_rev" value to be able to update/overwrite existing documents!
                    crawledCoupon["_rev"] = existentCoupon.rev
                    dbUpdates.append(crawledCoupon)
                    updatedCouponIDs.append(crawledCoupon.id)
                    numberofCouponsUpdated += 1
            else:
                # Add new coupon to DB
                numberofCouponsNew += 1
                if flagNewCouponsAsNew:
                    numberofCouponsFlaggedAsNew += 1
                    crawledCoupon.isNew = True
                dbUpdates.append(crawledCoupon)
                newCouponIDs.append(crawledCoupon.id)
        logging.info('Pushing ' + str(len(dbUpdates)) + ' coupon DB updates')
        couponDB.update(dbUpdates)
        logging.info("Number of crawled coupons: " + str(len(couponsToAddToDB)))
        self.updateCachedMissingPaperCouponsInfo(couponDB)
        # Update history if needed
        if self.keepHistory:
            timestampHistoryDBUpdateStart = datetime.now().timestamp()
            logging.info("Updating history DB: coupons")
            dbHistoryCoupons = self.couchdb[DATABASES.COUPONS_HISTORY]
            for itemID, coupon in couponsToAddToDB.items():
                self.updateHistoryEntry(dbHistoryCoupons, itemID, coupon)
            logging.info("Time it took to update coupons history DB: " + getFormattedPassedTime(timestampHistoryDBUpdateStart))
        # Cleanup DB
        deleteCouponDocs = {}
        for uniqueCouponID in couponDB:
            dbCoupon = Coupon.load(couponDB, uniqueCouponID)
            crawledCoupon = crawledCouponsDict.get(uniqueCouponID)
            if crawledCoupon is None:
                # Coupon is in DB but not in crawled coupons -> Remove from DB
                deleteCouponDocs[uniqueCouponID] = dbCoupon
            elif self.crawlOnlyBotCompatibleCoupons and not crawledCoupon.isValidForBot():
                # This will usually only happen if operator set crawlOnlyBotCompatibleCoupons to False first and then to True.
                deleteCouponDocs[uniqueCouponID] = dbCoupon
        if len(deleteCouponDocs) > 0:
            couponDB.purge(deleteCouponDocs.values())
        # Update timestamp of last complete run in DB
        infoDBDoc.timestampLastCrawl = datetime.now().timestamp()
        infoDBDoc.store(infoDatabase)
        logging.info("Coupons new IDs: " + str(numberofCouponsNew))
        if len(newCouponIDs) > 0:
            logging.info("New IDs: " + str(newCouponIDs))
        logging.info("Coupons updated: " + str(numberofCouponsUpdated))
        if len(updatedCouponIDs) > 0:
            logging.info("Coupons updated IDs: " + str(updatedCouponIDs))
        logging.info("Coupons deleted: " + str(len(deleteCouponDocs)))
        if len(deleteCouponDocs) > 0:
            logging.info("Coupons deleted IDs: " + str(list(deleteCouponDocs.keys())))
        logging.info("Coupons flagged as new: " + str(numberofCouponsFlaggedAsNew))
        logging.info("Coupon processing done | Total number of coupons in DB: " + str(len(couponDB)))
        logging.info("Total coupon processing time: " + getFormattedPassedTime(timestampStart))

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
        offers = apiResponse['promos']
        numberofNewOfferImages = 0
        dbUpdates = []
        for offer in offers:
            offerIDStr = str(offer['id'])
            # Save current version of image
            imageURL = couponOrOfferGetImageURL(offer)
            if downloadImageIfNonExistant(imageURL, offerGetImagePath(offer)):
                numberofNewOfferImages += 1
            dbUpdates.append(Document(offer, _id=offerIDStr))
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
            if coupon.type not in BotAllowedCouponTypes or not coupon.isValid():
                continue
            imagePathCoupon = coupon.getImagePath()
            if not isValidImageFile(imagePathCoupon):
                logging.warning(couponIDStr + ": Coupon image does not exist: " + imagePathCoupon)
                numberOfMissingImages += 1
            imagePathQR = coupon.getImagePathQR()
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

    def crawlProducts_DEPRECATED(self):
        # 2021-04-20: Not required at this moment!
        dbProducts = self.couchdb[DATABASES.PRODUCTS]
        dbProductsHistory = None
        if self.keepHistory:
            dbProductsHistory = self.couchdb[DATABASES.PRODUCTS_HISTORY]
        host = 'api.burgerking.de'
        conn = HTTP20Connection(host)
        conn.request("GET", '/api/o2uvrPdUY57J5WwYs6NtzZ2Knk7TnAUY/v2/de/de/products/',
                     headers=HEADERS_OLD)
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
            fullCouponTitle = coupon.getTitle()
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
                writer.writerow({'PRODUCT': coupon.getTitle(), 'MENU': coupon.isContainsFriesOrCoke(),
                                 'PLU': (coupon.plu if coupon.plu is not None else "N/A"), 'PLU2': coupon.id,
                                 'TYPE': coupon.type,
                                 'PRICE': coupon.get(Coupon.price.name, -1), 'PRICE_COMPARE': coupon.get(Coupon.priceCompare.name, -1),
                                 'START': coupon.getStartDateFormatted('N/A'),
                                 'EXP': (coupon.dateFormattedExpireInternal if coupon.dateFormattedExpireInternal is not None else "N/A"),
                                 'EXP2': (coupon.dateFormattedExpire if coupon.dateFormattedExpire is not None else 'N/A'),
                                 'EXP_PRODUCTIVE': coupon.getExpireDateFormatted()
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
                if coupon.type != CouponType.PAPER:
                    continue
                writer.writerow({'Produkt': coupon.getTitle(), 'Menü': coupon.isContainsFriesOrCoke(),
                                 'PLU': coupon.plu, 'PLU2': coupon.id,
                                 'Preis': coupon.getPrice(), 'OPreis': coupon.get(Coupon.priceCompare.name, -1),
                                 'Ablaufdatum': coupon.getExpireDateFormatted()
                                 })

    def updateCache(self, couponDB: Database):
        """ Updates cache containing all existent coupon sources e.g. used be the Telegram bot to display them inside
        main menu without having to do any DB requests. """
        newCachedAvailableCouponCategories = {}
        for couponID in couponDB:
            coupon = Coupon.load(couponDB, couponID)
            if coupon.isValid():
                category = newCachedAvailableCouponCategories.setdefault(coupon.type, CouponCategory(
                    parameter=coupon.type))
                category.updateWithCouponInfo(coupon)
        # Overwrite old cache
        self.cachedAvailableCouponCategories = newCachedAvailableCouponCategories

    def getCachedCouponCategory(self, couponSrc: Union[CouponType, int]):
        return self.cachedAvailableCouponCategories.get(couponSrc)

    def updateCachedMissingPaperCouponsInfo(self, couponDB: Database):
        paperCouponMapping = getCouponMappingForCrawler()
        self.cachedMissingPaperCouponsText = None
        missingPaperPLUs = []
        for mappingCoupon in paperCouponMapping.values():
            if mappingCoupon.id not in couponDB:
                missingPaperPLUs.append(mappingCoupon.plu)
        missingPaperPLUs.sort()
        self.missingPaperCouponPLUs = missingPaperPLUs
        for missingPLU in missingPaperPLUs:
            if self.cachedMissingPaperCouponsText is None:
                self.cachedMissingPaperCouponsText = missingPLU
            else:
                self.cachedMissingPaperCouponsText += ', ' + missingPLU
        if self.cachedMissingPaperCouponsText is not None:
            logging.info("Missing paper coupons: " + self.cachedMissingPaperCouponsText)

    def getMissingPaperCouponsText(self) -> Union[str, None]:
        if len(self.missingPaperCouponPLUs) > 0:
            cachedMissingPaperCouponsText = ''
            for missingPLU in self.missingPaperCouponPLUs:
                if len(cachedMissingPaperCouponsText) == 0:
                    cachedMissingPaperCouponsText = missingPLU
                else:
                    cachedMissingPaperCouponsText += ', ' + missingPLU
            return cachedMissingPaperCouponsText
        else:
            return None

    def getCouponDB(self):
        return self.couchdb[DATABASES.COUPONS]

    def getOfferDB(self):
        return self.couchdb[DATABASES.OFFERS]

    def getUsersDB(self):
        return self.couchdb[DATABASES.TELEGRAM_USERS]

    def getFilteredCoupons(
            self, filters: CouponFilter
    ) -> dict:
        """ Use this to only get the coupons you want.
         Returns all by default."""
        timestampStart = datetime.now().timestamp()
        couponDB = self.getCouponDB()
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
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            if filters.activeOnly and not coupon.isValid():
                # Skip expired coupons if needed
                continue
            elif filters.allowedCouponTypes is not None and coupon.type not in filters.allowedCouponTypes:
                # Skip non-allowed coupon-types
                continue
            elif filters.containsFriesAndCoke is not None and coupon.isContainsFriesOrCoke() != filters.containsFriesAndCoke:
                # Skip items if they do not have the expected "containsFriesOrCoke" state
                continue
            elif filters.isNew is not None and coupon.isNewCoupon() != filters.isNew:
                # Skip item if it does not have the expected "is_new" state
                continue
            elif filters.isHidden is not None and coupon.isHidden != filters.isHidden:
                continue
            else:
                desiredCoupons[uniqueCouponID] = coupon
        # Remove duplicates if needed and if it makes sense to attempt that
        if filters.removeDuplicates is True and (filters.allowedCouponTypes is None or (filters.allowedCouponTypes is not None and len(filters.allowedCouponTypes) > 1)):
            desiredCoupons = removeDuplicatedCoupons(desiredCoupons)
        # Now check if the result shall be sorted
        if filters.sortMode is None:
            return desiredCoupons
        else:
            # Sort coupons: Separate by type and sort each by coupons with/without menu and price.
            filteredCouponsList = list(desiredCoupons.values())
            if filters.sortMode == CouponSortMode.SOURCE_MENU_PRICE:
                couponsWithoutFriesOrCoke = []
                couponsWithFriesOrCoke = []
                allContainedCouponTypes = []
                for coupon in filteredCouponsList:
                    if coupon.type not in allContainedCouponTypes:
                        allContainedCouponTypes.append(coupon.type)
                    if coupon.isContainsFriesOrCoke():
                        couponsWithFriesOrCoke.append(coupon)
                    else:
                        couponsWithoutFriesOrCoke.append(coupon)
                couponsWithoutFriesOrCoke = sortCouponsByPrice(couponsWithoutFriesOrCoke)
                couponsWithFriesOrCoke = sortCouponsByPrice(couponsWithFriesOrCoke)
                # Merge them together again.
                filteredCouponsList = couponsWithoutFriesOrCoke + couponsWithFriesOrCoke
                # App coupons(source == 0) > Paper coupons
                allContainedCouponTypes.sort()
                # Separate sorted coupons by type
                couponsSeparatedByType = {}
                for couponType in allContainedCouponTypes:
                    couponsTmp = list(filter(lambda x: x.type == couponType, filteredCouponsList))
                    couponsSeparatedByType[couponType] = couponsTmp
                # Put our list sorted by type together again -> Sort done
                filteredCouponsList = []
                for allCouponsOfOneSourceType in couponsSeparatedByType.values():
                    filteredCouponsList += allCouponsOfOneSourceType
            elif filters.sortMode == CouponSortMode.MENU_PRICE:
                couponsWithoutFriesOrCoke = []
                couponsWithFriesOrCoke = []
                for coupon in filteredCouponsList:
                    if coupon.isContainsFriesOrCoke():
                        couponsWithFriesOrCoke.append(coupon)
                    else:
                        couponsWithoutFriesOrCoke.append(coupon)
                couponsWithoutFriesOrCoke = sortCouponsByPrice(couponsWithoutFriesOrCoke)
                couponsWithFriesOrCoke = sortCouponsByPrice(couponsWithFriesOrCoke)
                # Merge them together again.
                filteredCouponsList = couponsWithoutFriesOrCoke + couponsWithFriesOrCoke
            elif filters.sortMode == CouponSortMode.PRICE:
                filteredCouponsList = sortCouponsByPrice(filteredCouponsList)
            elif filters.sortMode == CouponSortMode.PRICE_DESCENDING:
                filteredCouponsList = sortCouponsByPrice(filteredCouponsList, descending=True)
            else:
                # This should never happen
                logging.warning("Developer mistake!! Unknown sortMode: " + filters.sortMode.name)
            # Make dict out of list
            filteredAndSortedCouponsDict = {}
            for coupon in filteredCouponsList:
                filteredAndSortedCouponsDict[coupon.id] = coupon
            logging.debug("Time it took to get- and sort coupons: " + getFormattedPassedTime(timestampStart))
            return filteredAndSortedCouponsDict

    def getFilteredCouponsAsList(
            self, filters: CouponFilter
    ) -> List[dict]:
        """ Wrapper """
        filteredCouponsDict = self.getFilteredCoupons(filters)
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

    def getBotCoupons(self) -> dict:
        """ Returns all coupons suitable for bot-usage (not sorted in any special order!). """
        return self.getFilteredCoupons(CouponFilter(activeOnly=True, allowedCouponTypes=BotAllowedCouponTypes, sortMode=CouponSortMode.PRICE))


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


def downloadCouponImageIfNonExistant(coupon: Coupon) -> bool:
    return downloadImageIfNonExistant(coupon.imageURL, coupon.getImagePath())


def downloadImageIfNonExistant(url: str, path: str) -> bool:
    if url is None or path is None:
        return False
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
        logging.warning("Image download failed: " + url)
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


def getCouponMappingForCrawler() -> dict:
    paperCouponConfig = PaperCouponHelper.getActivePaperCouponInfo()
    paperCouponMapping = {}
    for pluIdentifier, paperData in paperCouponConfig.items():
        mappingTmp = paperData.get('mapping')
        if mappingTmp is not None:
            expireTimestamp = paperData['expire_timestamp']
            for uniquePaperCouponID, plu in mappingTmp.items():
                paperCouponMapping[uniquePaperCouponID] = Coupon(id=uniquePaperCouponID, type=CouponType.PAPER, plu=plu, timestampExpire=expireTimestamp,
                                                                 dateFormattedExpire=formatDateGerman(expireTimestamp))
    return paperCouponMapping


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
