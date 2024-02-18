import csv
import logging
import traceback
from typing import List

import httpx
import qrcode
import requests
from couchdb import Database

import couchdb

import PaperCouponHelper
from BotUtils import getImageBasePath, loadConfig
from Helper import *
from Helper import getPathImagesOffers, getPathImagesProducts, \
    isValidImageFile, CouponType, Paths
from UtilsOffers import offerGetImagePath, offerIsValid
from UtilsCouponsDB import Coupon, InfoEntry, CouponFilter, getCouponTitleMapping, User, removeDuplicatedCoupons, sortCoupons
from CouponCategory import CouponCategory

HEADERS_OLD = {"User-Agent": "BurgerKing/6.7.0 (de.burgerking.kingfinder; build:432; Android 8.0.0) okhttp/3.12.3"}
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
# x-user-datetime: 2022-03-16T20:59:45+01:00
""" Enable this to crawl from localhost instead of API. Useful if there is a lot of testing to do! """
DEBUGCRAWLER = False


class UserStats:
    """ Returns an object containing statistic data about given users Database instance. """

    def __init__(self, userdb: Database):
        self.numberofUsersTotal = len(userdb)
        self.numberofUsersWhoFoundEasterEgg = 0
        self.numberofFavorites = 0
        self.numberofUsersWhoProbablyBlockedBot = 0
        self.numberofUsersWhoAreEligableForAutoDeletion = 0
        self.numberofUsersWhoRecentlyUsedBot = 0
        self.numberofUsersWhoAddedPaybackCard = 0
        self.numberofUsersWhoEnabledBotNewsletter = 0
        for userID in userdb:
            userTmp = User.load(userdb, userID)
            if userTmp.hasFoundEasterEgg():
                self.numberofUsersWhoFoundEasterEgg += 1
            self.numberofFavorites += len(userTmp.favoriteCoupons)
            if userTmp.hasProbablyBlockedBot():
                self.numberofUsersWhoProbablyBlockedBot += 1
            if userTmp.getPaybackCardNumber() is not None:
                self.numberofUsersWhoAddedPaybackCard += 1
            if userTmp.isEligableForAutoDeletion():
                self.numberofUsersWhoAreEligableForAutoDeletion += 1
            elif userTmp.hasRecentlyUsedBot():
                self.numberofUsersWhoRecentlyUsedBot += 1
            if userTmp.settings.notifyOnBotNewsletter:
                self.numberofUsersWhoEnabledBotNewsletter += 1


class BKCrawler:

    def __init__(self):
        self.cfg = loadConfig()
        if self.cfg is None:
            raise Exception('Broken or missing config')
        # Init DB
        self.couchdb = couchdb.Server(self.cfg.db_url)
        self.cachedAvailableCouponCategories = {}
        self.cachedNumberofAvailableOffers = 0
        self.keepHistoryDB = False
        self.keepSimpleHistoryDB = False
        self.storeCouponAPIDataAsJson = False
        self.exportCSVs = False
        self.missingPaperCouponPLUs = []
        self.cachedMissingPaperCouponsText = None
        self.cachedFutureCouponsText = None
        self.cachedFutureCoupons = []
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
        if DATABASES.COUPONS_HISTORY_SIMPLE not in self.couchdb:
            logging.info("Creating missing DB: " + DATABASES.COUPONS_HISTORY_SIMPLE)
            self.couchdb.create(DATABASES.COUPONS_HISTORY_SIMPLE)
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
        #     usersBackup = loadJson("telegram_users.json")['docs']
        #     for userO in usersBackup:
        #         user = User.wrap(userO)
        #         del user.data['_rev']
        #         if user.id not in userDB:
        #             logging.info("Adding new user: " + str(user.id))
        #             user.store(userDB)

        # couponDB_debug = self.couchdb[DATABASES.COUPONS]
        # if os.path.exists('coupons.json'):
        #     couponsBackup = loadJson("coupons.json")['docs']
        #     for userO in couponsBackup:
        #         coupon = Coupon.wrap(userO)
        #         del coupon.data['_rev']
        #         if coupon.id not in couponDB_debug:
        #             logging.info("Adding coupon from backup: " + str(coupon.id))
        #             coupon.store(couponDB_debug)

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
        self.migrateDBs()
        self.addExtraCoupons(crawledCouponsDict={}, immediatelyAddToDB=True)
        # Make sure that our cache gets filled on init
        couponDB = self.getCouponDB()
        self.updateCaches(couponDB)
        self.updateCachedMissingPaperCouponsInfo(couponDB)

    def setKeepHistoryDB(self, keepHistory: bool):
        """ Enable this if you want the crawler to maintain a history of past coupons/offers and update it on every crawl process. """
        self.keepHistoryDB = keepHistory

    def setKeepSimpleHistoryDB(self, keepSimpleHistoryDB: bool):
        """ Enable this if you want the crawler to maintain a simple history of past coupons and update it on every crawl process.
         Simple means that of every couponID, only the latest version will be kept.
         """
        self.keepSimpleHistoryDB = keepSimpleHistoryDB

    def setStoreCouponAPIDataAsJson(self, storeCouponAPIDataAsJson: bool):
        """ If enabled, all obtained API json responses will be saved into json files on each run. """
        self.storeCouponAPIDataAsJson = storeCouponAPIDataAsJson

    def setExportCSVs(self, exportCSVs: bool):
        """ If enabled, CSV file(s) will be exported into the "crawler" folder on each full crawl run. """
        self.exportCSVs = exportCSVs

    def crawl(self):
        """ Updates DB with new coupons & offers. """
        crawledCouponsDict = {}
        self.crawlCoupons(crawledCouponsDict)
        self.addExtraCoupons(crawledCouponsDict=crawledCouponsDict, immediatelyAddToDB=False)
        self.processCrawledCoupons(crawledCouponsDict)
        # self.crawlProducts()

    def downloadProductiveCouponDBImagesAndCreateQRCodes(self):
        """ Downloads coupons images and generates QR codes for current productive coupon DB. """
        dateStart = datetime.now()
        couponDB = self.getCouponDB()
        # Step 1: Create QR images
        coupons = []
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            coupons.append(coupon)
            generateQRImageIfNonExistant(uniqueCouponID, coupon.getImagePathQR())
        # Step 2: Download coupon images
        numberofDownloadedImages = 0
        for coupon in coupons:
            if downloadCouponImageIfNonExistant(coupon):
                numberofDownloadedImages += 1
        logging.info(f"Number of coupon images downloaded: {numberofDownloadedImages} | Duration: {datetime.now() - dateStart}")

    def migrateDBs(self):
        """ Migrate DBs from old to new version - leave this function empty if there is nothing to migrate. """
        # logging.info("Migrating DBs...")
        # logging.info("Migrate DBs done")
        migrationActionRequired = False
        if not migrationActionRequired:
            return
        # userDB = self.getUserDB()
        # keysMapping = {"timestampExpire": "timestampExpireInternal", "dateFormattedExpire": "dateFormattedExpireInternal", "timestampExpire2": "timestampExpire", "dateFormattedExpire2": "dateFormattedExpire"}

        # for userID in userDB:
        #     user = User.load(userDB, userID)
        # for couponData in user.favoriteCoupons.values():
        #     for oldKey, newKey in keysMapping.items():
        #         valueOfOldKey = couponData.get(oldKey)
        #         if valueOfOldKey is not None:
        #             needsUpdate = True
        #             couponData[newKey] = valueOfOldKey
        #             del couponData[oldKey]
        # if needsUpdate:
        #     user.store(userDB)

        # timestamp migration/introduction 2022-07-20
        return

    def crawlAndProcessData(self):
        """ One function that does it all! Execute this every time you run the crawler. """
        try:
            timestampStart = datetime.now().timestamp()
            self.crawl()
            if self.exportCSVs:
                self.couponCsvExport()
                self.couponCsvExport2()
            self.downloadProductiveCouponDBImagesAndCreateQRCodes()
            # self.checkProductiveCouponsDBImagesIntegrity()
            # self.checkProductiveOffersDBImagesIntegrity()
            logging.info("Total crawl duration: " + getFormattedPassedTime(timestampStart))
        finally:
            self.updateCaches(couponDB=self.getCouponDB(), offerDB=self.getOfferDB())

    def crawlCoupons(self, crawledCouponsDict: dict):
        """ Crawls coupons from App API.
         """
        timestampCrawlStart = datetime.now().timestamp()
        # Docs: https://czqk28jt.apicdn.sanity.io/v1/graphql/prod_bk_de/default
        # Official live instance: https://www.burgerking.de/rewards/offers
        # Old one: https://euc1-prod-bk.rbictg.com/graphql
        req = httpx.get(
            url='https://czqk28jt.apicdn.sanity.io/v1/graphql/prod_bk_de/default?operationName=featureSortedLoyaltyOffers&variables=%7B%22id%22%3A%22feature-loyalty-offers-ui-singleton%22%7D&query=query+featureSortedLoyaltyOffers%28%24id%3AID%21%29%7BLoyaltyOffersUI%28id%3A%24id%29%7B_id+sortedSystemwideOffers%7B...SystemwideOffersFragment+__typename%7D__typename%7D%7Dfragment+SystemwideOffersFragment+on+SystemwideOffer%7B_id+_type+loyaltyEngineId+name%7BlocaleRaw%3AdeRaw+__typename%7Ddescription%7BlocaleRaw%3AdeRaw+__typename%7DmoreInfo%7BlocaleRaw%3AdeRaw+__typename%7DhowToRedeem%7BenRaw+__typename%7DbackgroundImage%7B...MenuImageFragment+__typename%7DshortCode+mobileOrderOnly+redemptionMethod+daypart+redemptionType+upsellOptions%7B_id+loyaltyEngineId+description%7BlocaleRaw%3AdeRaw+__typename%7DlocalizedImage%7Blocale%3Ade%7B...MenuImagesFragment+__typename%7D__typename%7Dname%7BlocaleRaw%3AdeRaw+__typename%7D__typename%7DofferPrice+marketPrice%7B...on+Item%7B_id+_type+vendorConfigs%7B...VendorConfigsFragment+__typename%7D__typename%7D...on+Combo%7B_id+_type+vendorConfigs%7B...VendorConfigsFragment+__typename%7D__typename%7D__typename%7DlocalizedImage%7Blocale%3Ade%7B...MenuImagesFragment+__typename%7D__typename%7DuiPattern+lockedOffersPanel%7BcompletedChallengeHeader%7BlocaleRaw%3AdeRaw+__typename%7DcompletedChallengeDescription%7BlocaleRaw%3AdeRaw+__typename%7D__typename%7DpromoCodePanel%7BpromoCodeDescription%7BlocaleRaw%3AdeRaw+__typename%7DpromoCodeLabel%7BlocaleRaw%3AdeRaw+__typename%7DpromoCodeLink+__typename%7Dincentives%7B__typename+...on+Combo%7B_id+_type+mainItem%7B_id+_type+operationalItem%7Bdaypart+__typename%7DvendorConfigs%7B...VendorConfigsFragment+__typename%7D__typename%7DvendorConfigs%7B...VendorConfigsFragment+__typename%7DisOfferBenefit+__typename%7D...on+Item%7B_id+_type+operationalItem%7Bdaypart+__typename%7DvendorConfigs%7B...VendorConfigsFragment+__typename%7D__typename%7D...on+Picker%7B_id+_type+options%7Boption%7B__typename+...on+Combo%7B_id+_type+mainItem%7B_id+_type+operationalItem%7Bdaypart+__typename%7DvendorConfigs%7B...VendorConfigsFragment+__typename%7D__typename%7DvendorConfigs%7B...VendorConfigsFragment+__typename%7D__typename%7D...on+Item%7B_id+_type+operationalItem%7Bdaypart+__typename%7DvendorConfigs%7B...VendorConfigsFragment+__typename%7D__typename%7D%7D__typename%7DisOfferBenefit+__typename%7D...on+OfferDiscount%7B_id+_type+discountValue+discountType+__typename%7D...on+OfferActivation%7B_id+_type+__typename%7D...on+SwapMapping%7B_type+__typename%7D%7DvendorConfigs%7B...VendorConfigsFragment+__typename%7Drules%7B...on+RequiresAuthentication%7BrequiresAuthentication+__typename%7D...on+LoyaltyBetweenDates%7BstartDate+endDate+__typename%7D__typename%7D__typename%7Dfragment+MenuImageFragment+on+Image%7Bhotspot%7Bx+y+height+width+__typename%7Dcrop%7Btop+bottom+left+right+__typename%7Dasset%7Bmetadata%7Blqip+palette%7Bdominant%7Bbackground+foreground+__typename%7D__typename%7D__typename%7D_id+__typename%7D__typename%7Dfragment+MenuImagesFragment+on+Images%7Bapp%7B...MenuImageFragment+__typename%7Dkiosk%7B...MenuImageFragment+__typename%7DimageDescription+__typename%7Dfragment+VendorConfigsFragment+on+VendorConfigs%7Bcarrols%7B...VendorConfigFragment+__typename%7DcarrolsDelivery%7B...VendorConfigFragment+__typename%7Dncr%7B...VendorConfigFragment+__typename%7DncrDelivery%7B...VendorConfigFragment+__typename%7Doheics%7B...VendorConfigFragment+__typename%7DoheicsDelivery%7B...VendorConfigFragment+__typename%7Dpartner%7B...VendorConfigFragment+__typename%7DpartnerDelivery%7B...VendorConfigFragment+__typename%7DproductNumber%7B...VendorConfigFragment+__typename%7DproductNumberDelivery%7B...VendorConfigFragment+__typename%7Dsicom%7B...VendorConfigFragment+__typename%7DsicomDelivery%7B...VendorConfigFragment+__typename%7Dqdi%7B...VendorConfigFragment+__typename%7DqdiDelivery%7B...VendorConfigFragment+__typename%7Dqst%7B...VendorConfigFragment+__typename%7DqstDelivery%7B...VendorConfigFragment+__typename%7Drpos%7B...VendorConfigFragment+__typename%7DrposDelivery%7B...VendorConfigFragment+__typename%7DsimplyDelivery%7B...VendorConfigFragment+__typename%7DsimplyDeliveryDelivery%7B...VendorConfigFragment+__typename%7Dtablet%7B...VendorConfigFragment+__typename%7DtabletDelivery%7B...VendorConfigFragment+__typename%7D__typename%7Dfragment+VendorConfigFragment+on+VendorConfig%7BpluType+parentSanityId+pullUpLevels+constantPlu+discountPlu+quantityBasedPlu%7Bquantity+plu+qualifier+__typename%7DmultiConstantPlus%7Bquantity+plu+qualifier+__typename%7DparentChildPlu%7Bplu+childPlu+__typename%7DsizeBasedPlu%7BcomboPlu+comboSize+__typename%7D__typename%7D',
            headers=HEADERS, timeout=120)
        print(req.text)
        apiResponse = req.json()
        if self.storeCouponAPIDataAsJson:
            # Save API response so we can easily use this data for local testing later on.
            saveJson('crawler/coupons1.json', apiResponse)
        couponArrayBK = apiResponse['data']['LoyaltyOffersUI']['sortedSystemwideOffers']
        appCoupons = []
        appCouponsNotYetActive = []
        for couponBKTmp in couponArrayBK:
            bkCoupons = [couponBKTmp]
            # Collect hidden coupons
            upsellOptions = couponBKTmp.get('upsellOptions')
            if upsellOptions is not None:
                for upsellOption in upsellOptions:
                    upsellID = upsellOption.get('_id')
                    upsellType = upsellOption.get('_type')
                    upsellShortCode = upsellOption.get('shortCode')
                    if upsellType != 'offer' or upsellShortCode is None:
                        # Skip invalid items: This should never happen
                        logging.info(f"Found invalid/unsupported upsell object: {upsellID=}")
                        continue
                    bkCoupons.append(upsellOption)
            index = 0
            for couponBK in bkCoupons:
                uniqueCouponID = couponBK['vendorConfigs']['rpos']['constantPlu']
                legacyInternalName = couponBK.get('internalName')
                # Find coupon-title. Prefer to get it from 'internalName' as the other title may contain crap we don't want.
                # 2022-11-02: Prefer normal titles again because internal ones are sometimes incomplete
                useInternalNameAsTitle = False
                legacyInternalNameRegex = None
                if legacyInternalName is not None:
                    legacyInternalNameRegex = re.compile(r'[A-Za-z0-9]+_\d+_(?:UPSELL_|CRM_MYBK_|MYBK_|\d{3,}_)?(.+)').search(legacyInternalName)
                subtitle = None
                try:
                    subtitle = couponBK['description']['localeRaw'][0]['children'][0]['text']
                except:
                    pass
                if legacyInternalNameRegex is not None and useInternalNameAsTitle:
                    titleFull = legacyInternalNameRegex.group(1)
                    titleFull = titleFull.replace('_', ' ')
                else:
                    """ Decide how to use title and subtitle and if it makes sense to put both into one string. """
                    title = couponBK['name']['localeRaw'][0]['children'][0]['text']
                    title = title.strip()
                    if subtitle is None:
                        titleFull = title
                    else:
                        subtitle = subtitle.strip()
                        titleShortened = shortenProductNames(title)
                        subtitleShortened = shortenProductNames(subtitle)
                        if len(subtitleShortened) == 0 or subtitleShortened.isspace():
                            # Useless subtitle -> Use title only
                            titleFull = title
                        elif len(titleShortened) == 0 or titleShortened.isspace():
                            # Useless title -> Use subtitle only
                            titleFull = subtitle
                        elif titleShortened == subtitleShortened:  # Small hack: Shorten titles before comparing them
                            # Title and subtitle are the same -> Use title only
                            titleFull = title
                        else:
                            # Assume that subtitle is usable and put both together
                            titleFull = title + ' ' + subtitle
                            # Log seemingly strange values
                            if not subtitle.startswith('+'):
                                logging.info(f'Coupon {uniqueCouponID}: Possible subtitle which should not be included in coupon title: {subtitle=} | {title=} | {titleFull=}')

                titleFull = sanitizeCouponTitle(titleFull)
                price = couponBK['offerPrice']
                plu = couponBK['shortCode']
                coupon = Coupon(id=uniqueCouponID, uniqueID=uniqueCouponID, plu=plu, title=titleFull, subtitle=subtitle, titleShortened=shortenProductNames(titleFull),
                                type=CouponType.APP)
                coupon.webviewID = couponBK.get('loyaltyEngineId')
                # TODO: Check where those tags are located in new API endpoint
                offerTags = couponBK.get('offerTags')
                if offerTags is not None and len(offerTags) > 0:
                    # 2023-01-09: Looks like this field doesn't exist anymore
                    tagsStringArray = []
                    for offerTag in offerTags:
                        tagsStringArray.append(offerTag['value'])
                    coupon.tags = tagsStringArray
                if index > 0:
                    # First item = Real coupon, all others = upsell/"hidden" coupon(s)
                    coupon.isHidden = True
                if price == 0:
                    # Special detection for some 50%/2for1 coupons that are listed with price == 0€
                    if titleFull.startswith('2'):
                        # E.g. 2 Crispy Chicken
                        coupon.staticReducedPercent = 50
                    else:
                        # While it is super unlikely let's allow BK to provide coupons for free products :)
                        coupon.price = 0
                else:
                    coupon.price = price
                # Build URL to coupon product image
                imageurl = couponBK['localizedImage']['locale']['app']['asset']['_id']
                imageurl = "https://cdn.sanity.io/images/czqk28jt/prod_bk_de/" + imageurl.replace('image-', '')
                imageurl = imageurl.replace('-png', '.png')
                coupon.imageURL = imageurl
                """ Find and set start- and expire-date.
                 """
                datetimeExpire1 = None
                datetimeExpire2 = None
                datetimeStart = None
                try:
                    footnote = couponBK['moreInfo']['localeRaw'][0]['children'][0]['text']
                    expiredateRegex = re.compile(r'(?i)Abgabe bis (\d{1,2}\.\d{1,2}\.\d{4})').search(footnote)
                    if expiredateRegex is not None:
                        expiredateStr = expiredateRegex.group(1) + ' 23:59:59'
                        datetimeExpire1 = datetime.strptime(expiredateStr, '%d.%m.%Y %H:%M:%S')
                except:
                    # Dontcare
                    logging.warning('Failed to find BetterExpiredate for coupon: ' + coupon.id)
                rulesHere = couponBK.get('rules')
                if rulesHere is not None:
                    rulesAll = []
                    for ruleSet in rulesHere:
                        ruleSetsChilds = ruleSet.get('rules')
                        if ruleSetsChilds is not None:
                            for ruleSetsChild in ruleSetsChilds:
                                rulesAll.append(ruleSetsChild)
                        else:
                            rulesAll.append(ruleSet)
                    dateformatStart = '%Y-%m-%d'
                    dateformatEnd = '%Y-%m-%d %H:%M:%S'
                    for rule in rulesAll:
                        if rule['__typename'] == 'LoyaltyBetweenDates':
                            datetimeStart = datetime.strptime(rule['startDate'], dateformatStart)
                            datetimeExpire2 = datetime.strptime(rule['endDate'] + ' 23:59:59', dateformatEnd)
                            break
                else:
                    logging.info(f'Coupon without rules field: {coupon.id}')
                if datetimeExpire1 is None and datetimeExpire2 is None:
                    # This should never happen
                    logging.warning(f'WTF failed to find any expiredate for coupon: {uniqueCouponID}')
                elif datetimeExpire1 is not None:
                    # Prefer this expiredate
                    coupon.timestampExpire = datetimeExpire1.timestamp()
                else:
                    coupon.timestampExpire = datetimeExpire2.timestamp()
                if datetimeStart is not None:
                    coupon.timestampStart = datetimeStart.timestamp()
                crawledCouponsDict[uniqueCouponID] = coupon
                appCoupons.append(coupon)
                if datetimeStart is not None and datetimeStart > datetime.now():
                    appCouponsNotYetActive.append(coupon)
                index += 1

        logging.info(f'Coupons in app total: {len(appCoupons)}')
        logging.info(f'Coupons in app not yet active: {len(appCouponsNotYetActive)}')
        if len(appCouponsNotYetActive) > 0:
            logging.info(getLogSeparatorString())
            for coupon in appCouponsNotYetActive:
                logging.info(coupon)
            logging.info(getLogSeparatorString())
        logging.info(f'Total coupons crawl time: {getFormattedPassedTime(timestampCrawlStart)}')

    def addExtraCoupons(self, crawledCouponsDict: dict, immediatelyAddToDB: bool):
        """ Adds extra coupons which have been manually added to config_extra_coupons.json.
         This will only add VALID coupons to DB! """
        # First prepare extra coupons config because manual steps are involved to make this work
        PaperCouponHelper.main()
        extraCouponsToAdd = self.getValidExtraCoupons()
        if immediatelyAddToDB and len(extraCouponsToAdd) > 0:
            # Add items to DB
            couponDB = self.getCouponDB()
            dbWasUpdated = self.addCouponsToDB(couponDB=couponDB, couponsToAddToDB=extraCouponsToAdd)
            if dbWasUpdated:
                # Important!
                self.downloadProductiveCouponDBImagesAndCreateQRCodes()
        else:
            for coupon in extraCouponsToAdd.values():
                crawledCouponsDict[coupon.uniqueID] = coupon

    def getValidExtraCoupons(self) -> dict:
        PaperCouponHelper.main()
        extraCouponData = loadJson(Paths.extraCouponConfigPath)
        extraCouponsJson = extraCouponData["extra_coupons"]
        validExtraCoupons = {}
        for extraCouponJson in extraCouponsJson:
            coupon = Coupon.wrap(extraCouponJson)
            coupon.id = coupon.uniqueID  # Set custom uniqueID otherwise couchDB will create one later -> This is not what we want to happen!!
            expiredateStr = extraCouponJson["expire_date"] + " 23:59:59"
            expiredate = datetime.strptime(expiredateStr, '%Y-%m-%d %H:%M:%S').astimezone(getTimezone())
            coupon.timestampExpire = expiredate.timestamp()
            # Only add coupon if it is valid
            if coupon.isValid():
                validExtraCoupons[coupon.uniqueID] = coupon
        return validExtraCoupons

    def processCrawledCoupons(self, crawledCouponsDict: dict):
        """ Process crawled coupons: Apply necessary corrections and update DB. """
        dateStart = datetime.now()
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
        # Get rid of invalid coupons so we won't even bother adding them to our DB.
        notYetActiveCoupons = []
        expiredCoupons = []
        for coupon in crawledCouponsDict.values():
            if coupon.isExpired():
                expiredCoupons.append(coupon)
            else:
                if coupon.isNotYetActive():
                    notYetActiveCoupons.append(coupon)
                couponsToAddToDB[coupon.id] = coupon
        if len(notYetActiveCoupons) > 0 or len(expiredCoupons) > 0:
            logging.info(getLogSeparatorString())
            logging.info("Coupons which will not go into DB:")
            logging.info(getLogSeparatorString())
            logging.info(f"Expired coupons: {len(expiredCoupons)}")
            for coupon in expiredCoupons:
                logging.info(f'{coupon}')
            logging.info(getLogSeparatorString())
            logging.info(f"Not yet active coupons: {len(notYetActiveCoupons)}")
            for coupon in notYetActiveCoupons:
                logging.info(f'{coupon}')
            logging.info(getLogSeparatorString())
        logging.info(f'Crawled coupons: {len(crawledCouponsDict)} | To be added to DB: {len(couponsToAddToDB)}')
        infoDatabase = self.getInfoDB()
        infoDBDoc = InfoEntry.load(infoDatabase, DATABASES.INFO_DB)
        couponDB = self.getCouponDB()
        self.addCouponsToDB(couponDB=couponDB, couponsToAddToDB=couponsToAddToDB)
        # Cleanup DB
        deleteCouponDocs = {}
        # modifyCouponDocsUnreliableAPIWorkaround = {}
        # 2023-03-17: Unfinished work
        # doAPIWorkaroundHandling = False
        for uniqueCouponID in couponDB:
            dbCoupon = Coupon.load(couponDB, uniqueCouponID)
            crawledCoupon = crawledCouponsDict.get(uniqueCouponID)
            if crawledCoupon is None:
                # Coupon is in DB but not in crawled coupons anymore -> Remove from DB
                # if doAPIWorkaroundHandling:
                #     if not dbCoupon.isValid():
                #         # Coupon is ivalid/expired -> Remove it
                #         deleteCouponDocs[uniqueCouponID] = dbCoupon
                #     elif dbCoupon.timestampCouponNotInAPIAnymore is None:
                #         # Save timestamp when coupon disappeared from API first time
                #         dbCoupon.timestampCouponNotInAPIAnymore = getCurrentDate().timestamp()
                #         modifyCouponDocsUnreliableAPIWorkaround[dbCoupon.id] = dbCoupon
                #     elif getCurrentDate().timestamp() - dbCoupon.timestampCouponNotInAPIAnymore > 3 * 24 * 60 * 60:
                #         # Coupon hasn't been in API for at least 3 days -> Delete it
                #         deleteCouponDocs[uniqueCouponID] = dbCoupon
                deleteCouponDocs[uniqueCouponID] = dbCoupon
            elif crawledCoupon.isExpired():
                # Coupon is in DB and in crawled coupons but is expired -> Delete from DB
                deleteCouponDocs[uniqueCouponID] = dbCoupon
        if len(deleteCouponDocs) > 0:
            couponDB.purge(deleteCouponDocs.values())
        # Update timestamp of last complete run in DB
        infoDBDoc.dateLastSuccessfulCrawlRun = datetime.now()
        infoDBDoc.store(infoDatabase)
        logging.info(f"Coupons deleted: {len(deleteCouponDocs)}")
        if len(deleteCouponDocs) > 0:
            logging.info(f"Coupons deleted IDs: {list(deleteCouponDocs.keys())}")
        logging.info(f"Coupon processing done | Total number of coupons in DB: {len(couponDB)}")
        logging.info(f"Total coupon processing time: {datetime.now() - dateStart}")

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
                writer.writerow({'PRODUCT': coupon.getTitle(), 'MENU': coupon.isContainsFriesAndDrink(),
                                 'PLU': (coupon.plu if coupon.plu is not None else "N/A"), 'PLU2': coupon.id,
                                 'TYPE': coupon.type,
                                 'PRICE': coupon.get(Coupon.price.name, -1), 'PRICE_COMPARE': coupon.get(Coupon.priceCompare.name, -1),
                                 'START': coupon.getStartDateFormatted('N/A'),
                                 'EXP': (coupon.dateFormattedExpireInternal if coupon.dateFormattedExpireInternal is not None else "N/A"),
                                 'EXP2': (coupon.getExpireDateFormatted(fallback='N/A')),
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
                writer.writerow({'Produkt': coupon.getTitle(), 'Menü': coupon.isContainsFriesAndDrink(),
                                 'PLU': coupon.plu, 'PLU2': coupon.id,
                                 'Preis': coupon.getPrice(), 'OPreis': coupon.get(Coupon.priceCompare.name, -1),
                                 'Ablaufdatum': coupon.getExpireDateFormatted()
                                 })

    def updateCaches(self, couponDB: Database, offerDB: Database = None):
        """ Updates cache containing all existent coupon sources e.g. used be the Telegram bot to display them inside
        main menu without having to do any DB requests. """
        # Nullification
        self.cachedFutureCouponsText = None
        self.cachedFutureCoupons.clear()
        # End of nullification
        newCachedAvailableCouponCategories = {}
        futureCoupons = []
        for couponID in couponDB:
            coupon = Coupon.load(couponDB, couponID)
            if coupon.isValid():
                category = newCachedAvailableCouponCategories.setdefault(coupon.type, CouponCategory(
                    coupons=coupon.type))
                category.updateWithCouponInfo(coupon)
            elif coupon.isNotYetActive():
                futureCoupons.append(coupon)
        # Overwrite old cache
        self.cachedAvailableCouponCategories = newCachedAvailableCouponCategories
        self.cachedFutureCoupons = sorted(futureCoupons,
                                   key=lambda x: 0 if x.getStartDatetime() is None else x.getStartDatetime().timestamp())
        if offerDB is not None:
            validOffers = []
            for offerID in offerDB:
                offer = offerDB[offerID]
                if offerIsValid(offer):
                    validOffers.append(offer)
            self.cachedNumberofAvailableOffers = len(validOffers)
        self.updateCachedMissingPaperCouponsInfo(couponDB=couponDB)
        if len(self.cachedFutureCoupons) > 0:
            # Sort coupons by "release date"
            self.cachedFutureCouponsText = f"<b>{SYMBOLS.WHITE_DOWN_POINTING_BACKHAND}Demnächst verfügbare Coupons{SYMBOLS.WHITE_DOWN_POINTING_BACKHAND}</b>"
            for futureCoupon in self.cachedFutureCoupons:
                datetimeCouponAvailable = futureCoupon.getStartDatetime()
                if datetimeCouponAvailable is not None:
                    startDateFormatted = datetimeCouponAvailable.strftime('%d.%m.%Y')
                else:
                    startDateFormatted = "?"
                couponDescr = futureCoupon.generateCouponShortText(highlightIfNew=False, includeVeggieSymbol=True)
                thisCouponText = f"<b>{startDateFormatted}</b> | " + couponDescr
                self.cachedFutureCouponsText += "\n" + thisCouponText

    def updateCachedMissingPaperCouponsInfo(self, couponDB: Database):
        paperCouponMapping = getCouponMappingForCrawler()
        self.cachedMissingPaperCouponsText = None
        missingPaperPLUs = []
        for mappingCoupon in paperCouponMapping.values():
            if mappingCoupon.id not in couponDB:
                missingPaperPLUs.append(mappingCoupon.plu)
        missingPaperPLUs.sort()
        if len(missingPaperPLUs) > 0:
            self.missingPaperCouponPLUs = missingPaperPLUs
            for missingPLU in missingPaperPLUs:
                if self.cachedMissingPaperCouponsText is None:
                    self.cachedMissingPaperCouponsText = missingPLU
                else:
                    self.cachedMissingPaperCouponsText += ', ' + missingPLU
            logging.info("Missing paper coupons: " + self.cachedMissingPaperCouponsText)

    def getCachedCouponCategory(self, couponSrc: Union[CouponType, int]):
        return self.cachedAvailableCouponCategories.get(couponSrc)

    def getMissingPaperCouponsText(self) -> Union[str, None]:
        if len(self.missingPaperCouponPLUs) == 0:
            return None
        cachedMissingPaperCouponsText = ''
        for missingPLU in self.missingPaperCouponPLUs:
            if len(cachedMissingPaperCouponsText) == 0:
                cachedMissingPaperCouponsText = missingPLU
            else:
                cachedMissingPaperCouponsText += ', ' + missingPLU
        return cachedMissingPaperCouponsText

    def addCouponsToDB(self, couponDB: Database, couponsToAddToDB: Union[dict, List[Coupon]]) -> bool:
        if len(couponsToAddToDB) == 0:
            # Nothing to do
            return False
        if isinstance(couponsToAddToDB, dict):
            couponsToAddToDB = list(couponsToAddToDB.values())
        infoDatabase = self.couchdb[DATABASES.INFO_DB]
        infoDBDoc = InfoEntry.load(infoDatabase, DATABASES.INFO_DB)
        numberofCouponsNew = 0
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
        if infoDBDoc.dateLastSuccessfulCrawlRun is None:
            # First start: Allow to flag new coupons as new
            flagNewCouponsAsNew = True
        elif len(couponDB) > 0 and not dbContainsOnlyExtraCoupons:
            # Allow to flag new coupons as new (new = has not been in DB before)
            flagNewCouponsAsNew = True
        else:
            """ DB is empty or contains only extraCoupons which will get added on application launch
            --> Flag only existing expired coupons as new """
            flagNewCouponsAsNew = False
            logging.info("Not flagging new coupons as new while adding coupons now because DB is empty or contains only extraCoupons!")
        dbUpdates = []
        updatedCouponIDs = []
        newCouponIDs = []
        numberofCouponsUpdated = 0
        numberofCouponsFlaggedAsNew = 0
        for crawledCoupon in couponsToAddToDB:
            existingCoupon = Coupon.load(couponDB, crawledCoupon.id)
            # Update DB
            if existingCoupon is not None:
                # Update existing coupon
                if existingCoupon.timestampCouponNotInAPIAnymore is not None:
                    existingCoupon.timestampCouponNotInAPIAnymore = None
                if hasChanged(existingCoupon, crawledCoupon, ignoreKeys=['timestampAddedToDB', 'timestampLastModifiedDB']):
                    # Set isNew flag if necessary
                    if existingCoupon.isExpiredForLongerTime() and crawledCoupon.isValid():
                        crawledCoupon.timestampIsNew = getCurrentDate().timestamp()
                        numberofCouponsFlaggedAsNew += 1
                    # Important: We need the "_rev" value to be able to update/overwrite existing documents!
                    crawledCoupon["_rev"] = existingCoupon.rev
                    crawledCoupon.timestampLastModifiedDB = getCurrentDate().timestamp()
                    crawledCoupon.timestampAddedToDB = existingCoupon.timestampAddedToDB
                    dbUpdates.append(crawledCoupon)
                    updatedCouponIDs.append(crawledCoupon.id)
                    numberofCouponsUpdated += 1
            else:
                # Add new coupon to DB
                crawledCoupon.timestampAddedToDB = datetime.now().timestamp()
                numberofCouponsNew += 1
                if flagNewCouponsAsNew:
                    numberofCouponsFlaggedAsNew += 1
                    crawledCoupon.timestampIsNew = getCurrentDate().timestamp()
                dbUpdates.append(crawledCoupon)
                newCouponIDs.append(crawledCoupon.id)
        logging.info(f'Pushing {len(dbUpdates)} coupon DB updates')
        couponDB.update(dbUpdates)
        logging.info("Coupons new: " + str(numberofCouponsNew))
        if len(newCouponIDs) > 0:
            logging.info("New IDs: " + str(newCouponIDs))
        logging.info("Coupons updated: " + str(numberofCouponsUpdated))
        if len(updatedCouponIDs) > 0:
            logging.info("Coupons updated IDs: " + str(updatedCouponIDs))
        logging.info("Coupons flagged as new: " + str(numberofCouponsFlaggedAsNew))
        if numberofCouponsUpdated > 0 or numberofCouponsFlaggedAsNew > 0:
            # Update history DB(s) if needed
            if self.keepHistoryDB:
                timestampHistoryDBUpdateStart = datetime.now().timestamp()
                logging.info("Updating history DB: coupons")
                dbHistoryCoupons = self.couchdb[DATABASES.COUPONS_HISTORY]
                for coupon in couponsToAddToDB:
                    self.updateHistoryEntry(dbHistoryCoupons, coupon.uniqueID, coupon)
                logging.info("Time it took to update coupons history DB: " + getFormattedPassedTime(timestampHistoryDBUpdateStart))
            if self.keepSimpleHistoryDB:
                self.updateSimpleHistoryDB(couponDB)
            # DB was updated
            return True
        else:
            # DB was not updated
            return False

    def updateSimpleHistoryDB(self, couponDB: Database) -> bool:
        dbUpdates = []
        simpleHistoryDB = self.couchdb[DATABASES.COUPONS_HISTORY_SIMPLE]
        for couponID in couponDB:
            coupon = Coupon.load(db=couponDB, id=couponID)
            existingCoupon = Coupon.load(simpleHistoryDB, coupon.id)
            if existingCoupon is None:
                dbUpdates.append(coupon)
            elif hasChanged(existingCoupon, coupon, ignoreKeys=['_rev']):
                # Important: We need the "_rev" value to be able to update/overwrite existing documents!
                coupon["_rev"] = existingCoupon.rev
                dbUpdates.append(coupon)
        if len(dbUpdates) > 0:
            # Update DB
            simpleHistoryDB.update(dbUpdates)
            return True
        else:
            # DB was not updated
            return False

    def getCouponDB(self):
        return self.couchdb[DATABASES.COUPONS]

    def getOfferDB(self):
        return self.couchdb[DATABASES.OFFERS]

    def getUserDB(self):
        return self.couchdb[DATABASES.TELEGRAM_USERS]

    def getInfoDB(self):
        return self.couchdb[DATABASES.INFO_DB]

    def getFilteredCouponsAsDict(
            self, couponfilter: CouponFilter, sortIfSortCodeIsGivenInCouponFilter: bool = True
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
        # Log if developer is trying to use incorrect filters
        if couponfilter.isVeggie is False and couponfilter.isPlantBased is True:
            logging.warning(f'Bad params: {couponfilter.isVeggie=} and {couponfilter.isPlantBased=}')
        for uniqueCouponID in couponDB:
            coupon = Coupon.load(couponDB, uniqueCouponID)
            if couponfilter.activeOnly and not coupon.isValid():
                # Skip expired coupons if needed
                continue
            elif couponfilter.isNotYetActive is not None and coupon.isNotYetActive() != couponfilter.isNotYetActive:
                continue
            elif couponfilter.allowedCouponTypes is not None and coupon.type not in couponfilter.allowedCouponTypes:
                # Skip non-allowed coupon-types
                continue
            elif couponfilter.containsFriesAndCoke is not None and coupon.isContainsFriesAndDrink() != couponfilter.containsFriesAndCoke:
                # Skip items if they do not have the expected "containsFriesOrCoke" state
                continue
            elif couponfilter.isNew is not None and coupon.isNewCoupon() != couponfilter.isNew:
                # Skip item if it does not have the expected "is_new" state
                continue
            elif couponfilter.isHidden is not None and coupon.isHidden != couponfilter.isHidden:
                continue
            elif couponfilter.isVeggie is not None and coupon.isVeggie() != couponfilter.isVeggie:
                continue
            elif couponfilter.isPlantBased is not None and coupon.isPlantBased() != couponfilter.isPlantBased:
                continue
            elif couponfilter.isEatable is not None and coupon.isEatable() != couponfilter.isEatable:
                continue
            else:
                desiredCoupons[uniqueCouponID] = coupon
        # Remove duplicates if needed and if it makes sense to attempt that
        if couponfilter.removeDuplicates is True and (couponfilter.allowedCouponTypes is None or (couponfilter.allowedCouponTypes is not None and len(couponfilter.allowedCouponTypes) > 1)):
            desiredCoupons = removeDuplicatedCoupons(desiredCoupons)
        # Now check if the result shall be sorted
        if couponfilter.sortCode is not None and sortIfSortCodeIsGivenInCouponFilter:
            # Sort coupons: Separate by type and sort each by coupons with/without menu and price.
            # Make dict out of list
            filteredAndSortedCouponsDict = sortCoupons(desiredCoupons, couponfilter.sortCode)
            logging.debug("Time it took to get- and sort coupons: " + getFormattedPassedTime(timestampStart))
            return filteredAndSortedCouponsDict
        else:
            return desiredCoupons

    def getFilteredCouponsAsList(
            self, filters: CouponFilter, sortIfSortCodeIsGivenInCouponFilter: bool = True
    ) -> List[Coupon]:
        """ Wrapper """
        filteredCouponsDict = self.getFilteredCouponsAsDict(filters, sortIfSortCodeIsGivenInCouponFilter=sortIfSortCodeIsGivenInCouponFilter)
        return list(filteredCouponsDict.values())

    def getOffersActive(self) -> list:
        """ Returns all offers that are not expired according to 'expiration_date'. """
        # 2023-03-18: There are no offers at this moment. What was an offer back then ("King of the month") has been moved into coupons now by BK.
        if True:
            return []
        offerDB = self.getOfferDB()
        offers = []
        for offerID in offerDB:
            offer = offerDB[offerID]
            if offerIsValid(offer):
                offers.append(offer)
        return offers


def getCouponByID(coupons: List[Coupon], couponID: str) -> Union[Coupon, None]:
    """ Returns first coupon with desired ID in list. """
    for coupon in coupons:
        if coupon.uniqueID == couponID:
            return coupon
    return None


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


def getLogSeparatorString() -> str:
    return '**************************'


if __name__ == '__main__':
    crawler = BKCrawler()
    crawler.setExportCSVs(False)
    crawler.setKeepHistoryDB(False)
    crawler.setKeepSimpleHistoryDB(False)

    # crawler.setExportCSVs(True)
    # crawler.setCrawlOnlyBotCompatibleCoupons(False)
    print("Number of userIDs in DB: " + str(len(crawler.getUserDB())))
    crawler.crawlAndProcessData()
    print("Crawler done!")
