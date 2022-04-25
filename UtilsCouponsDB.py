import logging
import os
from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import Union, List, Optional

from barcode.ean import EuropeanArticleNumber13
from barcode.writer import ImageWriter
from couchdb.mapping import TextField, FloatField, ListField, IntegerField, BooleanField, Document, DictField, Mapping, \
    DateTimeField
from pydantic import BaseModel

from Helper import getTimezone, getCurrentDate, getFilenameFromURL, SYMBOLS, normalizeString, shortenProductNames, \
    formatDateGerman, couponTitleContainsFriesOrCoke, BotAllowedCouponSources, CouponSource


class Coupon(Document):
    plu = TextField()
    uniqueID = TextField()
    price = FloatField()
    priceCompare = FloatField()
    staticReducedPercent = FloatField()
    title = TextField()
    titleShortened = TextField()
    timestampStart = FloatField()
    timestampExpireInternal = FloatField()  # Internal expire-date
    timestampExpire = FloatField()  # Expire date used by BK in their apps -> "Real" expire date.
    dateFormattedStart = TextField()
    dateFormattedExpireInternal = TextField()
    dateFormattedExpire = TextField()
    imageURL = TextField()
    paybackMultiplicator = IntegerField()
    productIDs = ListField(IntegerField())
    source = IntegerField()
    containsFriesOrCoke = BooleanField()
    isNew = BooleanField()
    isNewUntilDate = TextField()
    isHidden = BooleanField(default=False)  # Typically only available for App coupons
    isUnsafeExpiredate = BooleanField(
        default=False)  # Set this if timestampExpire is a made up date that is just there to ensure that the coupon is considered valid for a specified time
    description = TextField()

    def getPLUOrUniqueID(self) -> str:
        """ Returns PLU if existant, returns UNIQUE_ID otherwise. """
        if self.plu is not None:
            return self.plu
        else:
            return self.id

    def getNormalizedTitle(self):
        return normalizeString(self.getTitle())

    def getTitle(self):
        return self.title

    def getTitleShortened(self):
        # TODO: Make use of this everywhere
        return self.titleShortened
        # return shortenProductNames(self.title)

    def isValid(self):
        expireDatetime = self.getExpireDatetime()
        if expireDatetime is None:
            # Coupon without expire-date = invalid --> Should never happen
            return False
        elif expireDatetime > getCurrentDate():
            return True
        else:
            return False

    def isValidForBot(self) -> bool:
        """ Checks if the given coupon can be used in bot e.g. is from allowed source (App/Paper) and is valid. """
        if self.source in BotAllowedCouponSources and self.isValid():
            return True
        else:
            return False

    def isContainsFriesOrCoke(self) -> bool:
        # TODO: Make use of this
        if couponTitleContainsFriesOrCoke(self.title):
            return True
        else:
            return False

    def isEatable(self) -> bool:
        """ If the product(s) this coupon provide(s) is/are not eatable and e.g. just probide a discount like Payback coupons, this will return False, else True. """
        if self.source == CouponSource.PAYBACK:
            return False
        else:
            return True

    def isNewCoupon(self) -> bool:
        """ Determines whether or not this coupon is considered 'new'. """
        if self.isNew is not None:
            # isNew status is pre-given --> Preferably return that
            return self.isNew
        elif self.isNewUntilDate is not None:
            # Check if maybe coupon should be considered as new for X
            try:
                enforceIsNewOverrideUntilDate = datetime.strptime(self.isNewUntilDate + ' 23:59:59',
                                                                  '%Y-%m-%d %H:%M:%S').astimezone(getTimezone())
                if enforceIsNewOverrideUntilDate.timestamp() > datetime.now().timestamp():
                    return True
                else:
                    return False
            except:
                # This should never happen
                logging.warning("Coupon.getIsNew: WTF invalid date format??")
                return False
        else:
            return False

    def getExpireDatetime(self) -> Union[datetime, None]:
        if self.timestampExpire is not None:
            return datetime.fromtimestamp(self.timestampExpire, getTimezone())
        else:
            # This should never happen
            logging.warning("Found coupon without expiredate: " + self.id)
            return None

    def getExpireDateFormatted(self, fallback: Union[str, None] = None) -> Union[str, None]:
        if self.timestampExpire is not None:
            # return self.dateFormattedExpire
            return formatDateGerman(datetime.fromtimestamp(self.timestampExpire))
        else:
            return fallback

    def getStartDateFormatted(self, fallback: Union[str, None] = None) -> Union[str, None]:
        if self.timestampStart is not None:
            return formatDateGerman(datetime.fromtimestamp(self.timestampStart))
        else:
            return fallback

    def getPriceFormatted(self, fallback=None) -> Union[str, None]:
        if self.price is not None:
            return getFormattedPrice(self.price)
        else:
            return fallback

    def getPriceCompareFormatted(self, fallback=None) -> Union[str, None]:
        if self.priceCompare is not None:
            return getFormattedPrice(self.priceCompare)
        else:
            return fallback

    def getReducedPercentageFormatted(self, fallback=None) -> Union[str, None]:
        """ Returns price reduction in percent if bothb the original price and the reduced/coupon-price are available.
         E.g. "-39%" """
        if self.price is not None and self.priceCompare is not None:
            return '-' + f'{(1 - (self.price / self.priceCompare)) * 100:2.0f}'.replace('.', ',') + '%'
        elif self.staticReducedPercent is not None:  # Sometimes we don't have a compare-price but the reduce amount is pre-given via App-API.
            return '-' + f'{self.staticReducedPercent:2.0f}' + '%'
        elif self.paybackMultiplicator is not None:
            # 0.5 points per euro (= base discount of 0.5% without multiplicator)
            paybackReducedPercent = (0.5 * self.paybackMultiplicator)
            return '-' + f'{paybackReducedPercent:2.1f}' + '%'
        else:
            return fallback

    def getUniqueIdentifier(self) -> str:
        """ Returns an unique identifier String which can be used to compare coupon objects. """
        expiredateStr = self.getExpireDateFormatted(fallback='undefined')
        return self.id + '_' + (
            "undefined" if self.plu is None else self.plu) + '_' + expiredateStr + '_' + self.imageURL

    def getComparableValue(self) -> str:
        """ Returns value which can be used to compare given coupon object to another one.
         This might be useful in the future to e.g. find coupons that contain exactly the same products and cost the same price as others.
          Do NOT use this to compare multiple Coupon objects! Use couponDBGetUniqueIdentifier instead!
          """
        return self.getTitle().lower() + str(self.price)

    def getImagePath(self) -> str:
        if self.imageURL.startswith('file://'):
            # Image should be present in local storage: Use pre-given path
            return self.imageURL.replace('file://', '')
        else:
            return getImageBasePath() + "/" + self.id + "_" + getFilenameFromURL(self.imageURL)

    def getImagePathQR(self) -> str:
        return getImageBasePath() + "/" + self.id + "_QR.png"

    def getImageQR(self):
        path = self.getImagePathQR()
        if os.path.exists(path):
            return open(path, mode='rb')
        else:
            # Return fallback --> This should never happen!
            return open('media/fallback_image_missing_qr_image.jpeg', mode='rb')

    def generateCouponShortText(self, highlightIfNew: bool) -> str:
        """ Returns e.g. "Y15 | 2Whopper+M🍟+0,4Cola | 8,99€" """
        couponText = ''
        if self.isNewCoupon() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += self.getPLUOrUniqueID() + " | " + self.getTitleShortened()
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponShortTextFormatted(self, highlightIfNew: bool) -> str:
        """ Returns e.g. "<b>Y15</b> | 2Whopper+M🍟+0,4Cola | 8,99€" """
        couponText = ''
        if self.isNewCoupon() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += "<b>" + self.getPLUOrUniqueID() + "</b> | " + self.getTitleShortened()
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponShortTextFormattedWithHyperlinkToChannelPost(self, highlightIfNew: bool, publicChannelName: str,
                                                                   messageID: int) -> str:
        """ Returns e.g. "Y15 | 2Whopper+M🍟+0,4Cola (https://t.me/betterkingpublic/1054) | 8,99€" """
        couponText = "<b>" + self.getPLUOrUniqueID() + "</b> | <a href=\"https://t.me/" + publicChannelName + '/' + str(
            messageID) + "\">"
        if self.isNewCoupon() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += self.getTitleShortened() + "</a>"
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponLongTextFormatted(self) -> str:
        """ Returns e.g. "2 Whopper + Mittlere Pommes + 0,4L Cola
         <b>Y15</b> | 8,99€ | -25% " """
        couponText = ''
        if self.isNewCoupon():
            couponText += SYMBOLS.NEW
        couponText += self.getTitle()
        couponText += "\n<b>" + self.getPLUOrUniqueID() + "</b>"
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponLongTextFormattedWithHyperlinkToChannelPost(self, publicChannelName: str, messageID: int) -> str:
        """ Returns e.g. "2 Whopper + Mittlere Pommes +0,4L Cola (https://t.me/betterkingpublic/1054)
         <b>Y15</b> | 8,99€ | -25% " """
        couponText = "<a href=\"https://t.me/" + publicChannelName + '/' + str(
            messageID) + "\">"
        if self.isNewCoupon():
            couponText += SYMBOLS.NEW
        couponText += self.getTitle()
        couponText += "</a>"
        couponText += "\n<b>" + self.getPLUOrUniqueID() + "</b>"
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponLongTextFormattedWithDescription(self, highlightIfNew: bool):
        """
        :param highlightIfNew: Add emoji to text if coupon is new.
        :return: E.g. "<b>B3</b> | 1234 | 13.99€ | -50%\nGültig bis:19.06.2021\nCoupon.description"
        """
        couponText = ''
        if self.isNewCoupon() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += self.getTitle() + '\n'
        couponText += self.getPLUInformationFormatted()
        couponText = self.appendPriceInfoText(couponText)
        """ Expire date should be always given but we can't be 100% sure! """
        expireDateFormatted = self.getExpireDateFormatted()
        if expireDateFormatted is not None:
            couponText += '\nGültig bis ' + expireDateFormatted
        if self.description is not None:
            couponText += "\n" + self.description
        return couponText

    def getPLUInformationFormatted(self) -> str:
        """ Returns e.g. <b>123</b> | 67407 """
        if self.plu is not None and self.plu != self.id:
            return '<b>' + self.plu + '</b>' + ' | ' + self.id
        else:
            return '<b>' + self.id + '</b>'

    def appendPriceInfoText(self, couponText: str) -> str:
        priceFormatted = self.getPriceFormatted()
        if priceFormatted is not None:
            couponText += " | " + priceFormatted
        reducedPercentage = self.getReducedPercentageFormatted()
        if reducedPercentage is not None:
            couponText += " | " + reducedPercentage
        return couponText

    def getPriceInfoText(self) -> Union[str, None]:
        priceInfoText = None
        priceFormatted = self.getPriceFormatted()
        if priceFormatted is not None:
            priceInfoText = priceFormatted
        reducedPercentage = self.getReducedPercentageFormatted()
        if reducedPercentage is not None:
            if priceInfoText is None:
                priceInfoText = reducedPercentage
            else:
                priceInfoText += " | " + reducedPercentage
        return priceInfoText


class UserFavoritesInfo:
    """ Helper class for users favorites. """

    def __init__(self, favoritesAvailable: Union[List[Coupon], None] = None,
                 favoritesUnavailable: Union[List[Coupon], None] = None):
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
                unavailableFavoritesText += coupon.id + ' | ' + coupon.getTitleShortened()
                priceInfoText = coupon.getPriceInfoText()
                if priceInfoText is not None:
                    unavailableFavoritesText += ' | ' + priceInfoText
            return unavailableFavoritesText


class User(Document):
    settings = DictField(
        Mapping.build(
            displayQR=BooleanField(default=True),
            displayBKWebsiteURLs=BooleanField(default=True),
            displayCouponCategoryPayback=BooleanField(default=True),
            displayFeedbackCodeGenerator=BooleanField(default=True),
            displayHiddenAppCouponsWithinGenericCategories=BooleanField(default=False),
            notifyWhenFavoritesAreBack=BooleanField(default=False),
            notifyWhenNewCouponsAreAvailable=BooleanField(default=False),
            highlightFavoriteCouponsInButtonTexts=BooleanField(default=True),
            highlightNewCouponsInCouponButtonTexts=BooleanField(default=True),
            autoDeleteExpiredFavorites=BooleanField(default=False),
            enableBetaFeatures=BooleanField(default=False)
        )
    )
    botBlockedCounter = IntegerField(default=0)
    easterEggCounter = IntegerField(default=0)
    favoriteCoupons = DictField(default={})
    paybackCard = DictField(
        Mapping.build(
            paybackCardNumber=TextField(),
            addedDate=DateTimeField()
        ))

    def hasProbablyBlockedBot(self) -> bool:
        if self.botBlockedCounter > 0:
            return True
        else:
            return False

    def hasDefaultSettings(self) -> bool:
        for settingKey, settingValue in self["settings"].items():
            settingInfo = USER_SETTINGS_ON_OFF.get(settingKey)
            if settingInfo is None:
                # Ignore keys that aren't covered in our settings map
                continue
            elif settingValue != settingInfo['default']:
                return False

        return True

    def hasFoundEasterEgg(self) -> bool:
        if self.easterEggCounter > 0:
            return True
        else:
            return False

    def isFavoriteCoupon(self, coupon: Coupon):
        """ Checks if given coupon is users' favorite """
        return self.isFavoriteCouponID(coupon.id)

    def isFavoriteCouponID(self, couponID: str):
        if couponID in self.favoriteCoupons:
            return True
        else:
            return False

    def addFavoriteCoupon(self, coupon: Coupon):
        self.favoriteCoupons[coupon.id] = coupon._data

    def deleteFavoriteCoupon(self, coupon: Coupon):
        self.deleteFavoriteCouponID(coupon.id)

    def deleteFavoriteCouponID(self, couponID: str):
        del self.favoriteCoupons[couponID]

    def isAllowSendFavoritesNotification(self):
        if self.settings.autoDeleteExpiredFavorites:
            return False
        elif self.settings.notifyWhenFavoritesAreBack:
            return True
        else:
            return False

    def getPaybackCardNumber(self) -> Union[str, None]:
        return self.paybackCard.paybackCardNumber

    def getPaybackCardImage(self) -> bytes:
        ean = EuropeanArticleNumber13(ean='240' + self.getPaybackCardNumber(), writer=ImageWriter())
        file = BytesIO()
        ean.write(file, options={'foreground': 'black'})
        return file.getvalue()

    def addPaybackCard(self, paybackCardNumber: str):
        self.paybackCard.paybackCardNumber = paybackCardNumber
        self.paybackCard.addedDate = datetime.now()

    def deletePaybackCard(self):
        dummyUser = User()
        self.paybackCard = dummyUser.paybackCard

    def getUserFavoritesInfo(self, couponsFromDB: Union[dict, Document]) -> UserFavoritesInfo:
        """
        Gathers information about the given users' favorite available/unavailable coupons.
        Coupons from DB are required to get current dataset of available favorites.
        """
        if len(self.favoriteCoupons) == 0:
            # User does not have any favorites set --> There is no point to look for the additional information
            return UserFavoritesInfo()
        else:
            availableFavoriteCoupons = []
            unavailableFavoriteCoupons = []
            for uniqueCouponID, coupon in self.favoriteCoupons.items():
                couponFromProductiveDB = couponsFromDB.get(uniqueCouponID)
                if couponFromProductiveDB is not None and couponFromProductiveDB.isValid():
                    availableFavoriteCoupons.append(couponFromProductiveDB)
                else:
                    # User chosen favorite coupon has expired or is not in DB
                    coupon = Coupon.wrap(coupon)  # We want a 'real' coupon object
                    unavailableFavoriteCoupons.append(coupon)
            # Sort all coupon arrays by price
            availableFavoriteCoupons = sortCouponsByPrice(availableFavoriteCoupons)
            unavailableFavoriteCoupons = sortCouponsByPrice(unavailableFavoriteCoupons)
            return UserFavoritesInfo(favoritesAvailable=availableFavoriteCoupons,
                                     favoritesUnavailable=unavailableFavoriteCoupons)

    def resetSettings(self):
        dummyUser = User()
        self.settings = dummyUser.settings


class InfoEntry(Document):
    timestampLastCrawl = FloatField(default=-1)
    timestampLastChannelUpdate = FloatField(default=-1)
    informationMessageID = TextField()
    couponTypeOverviewMessageIDs = DictField(default={})
    messageIDsToDelete = ListField(IntegerField(), default=[])
    lastMaintenanceModeState = BooleanField()

    def addMessageIDToDelete(self, messageID: int):
        # Avoid duplicates
        if messageID not in self.messageIDsToDelete:
            self.messageIDsToDelete.append(messageID)

    def addMessageIDsToDelete(self, messageIDs: List):
        for messageID in messageIDs:
            self.addMessageIDToDelete(messageID)

    def addCouponCategoryMessageID(self, couponSource: int, messageID: int):
        self.couponTypeOverviewMessageIDs.setdefault(couponSource, []).append(messageID)

    def getMessageIDsForCouponCategory(self, couponSource: int) -> List[int]:
        return self.couponTypeOverviewMessageIDs.get(str(couponSource), [])

    def getAllCouponCategoryMessageIDs(self) -> List[int]:
        messageIDs = []
        for messageIDsTemp in self.couponTypeOverviewMessageIDs.values():
            messageIDs += messageIDsTemp
        return messageIDs

    def deleteCouponCategoryMessageIDs(self, couponSource: int):
        if str(couponSource) in self.couponTypeOverviewMessageIDs:
            del self.couponTypeOverviewMessageIDs[str(couponSource)]

    def deleteAllCouponCategoryMessageIDs(self):
        self.couponTypeOverviewMessageIDs = {}


class ChannelCoupon(Document):
    """ Represents a coupon posted in a Telegram channel.
     Only contains minimum of required information as information about coupons itself is stored in another DB. """
    uniqueIdentifier = TextField()
    messageIDs = ListField(IntegerField())
    timestampMessagesPosted = FloatField(default=-1)
    channelMessageID_image = IntegerField()
    channelMessageID_qr = IntegerField()
    channelMessageID_text = IntegerField()

    def getMessageIDs(self) -> List[int]:
        messageIDs = []
        if self.channelMessageID_image is not None:
            messageIDs.append(self.channelMessageID_image)
        if self.channelMessageID_qr is not None:
            messageIDs.append(self.channelMessageID_qr)
        if self.channelMessageID_text is not None:
            messageIDs.append(self.channelMessageID_text)
        return messageIDs

    def deleteMessageIDs(self):
        # Nullification
        self.channelMessageID_image = None
        self.channelMessageID_qr = None
        self.channelMessageID_text = None

    def getMessageIDForChatHyperlink(self) -> Union[None, int]:
        return self.channelMessageID_image


class CouponSortMode(Enum):
    PRICE = 0
    MENU_PRICE = 1
    SOURCE_MENU_PRICE = 2


def getImageBasePath() -> str:
    return "crawler/images/couponsproductive"


def getFormattedPrice(price: float) -> str:
    return f'{(price / 100):2.2f}'.replace('.', ',') + '€'


def getCouponsTotalPrice(coupons: List[Coupon]) -> float:
    """ Returns the total summed price of a list of coupons. """
    totalSum = 0
    for coupon in coupons:
        if coupon.price is not None:
            totalSum += coupon.price
    return totalSum


def getCouponsSeparatedByType(coupons: dict) -> dict:
    couponsSeparatedByType = {}
    for couponSource in BotAllowedCouponSources:
        couponsTmp = list(filter(lambda x: x[Coupon.source.name] == couponSource, list(coupons.values())))
        couponsSeparatedByType[couponSource] = couponsTmp
    return couponsSeparatedByType


def sortCouponsByPrice(couponList: List[Coupon]) -> List[Coupon]:
    # Sort by price -> But price is not always given -> Place items without prices at the BEGINNING of each list.
    return sorted(couponList,
                  key=lambda x: -1 if x.get(Coupon.price.name, -1) is None else x.get(Coupon.price.name, -1))


class CouponFilter(BaseModel):
    activeOnly: Optional[bool] = True
    containsFriesAndCoke: Optional[Union[bool, None]] = None
    excludeCouponsByDuplicatedProductTitles: Optional[
        bool] = False  # Enable to filter duplicated coupons for same products - only returns cheapest of all
    allowedCouponSources: Optional[Union[List[int], None]] = None  # None = allow all sources!
    isNew: Optional[Union[bool, None]] = None
    isHidden: Optional[Union[bool, None]] = None
    sortMode: Optional[Union[None, CouponSortMode]]


def getCouponTitleMapping(coupons: dict) -> dict:
    """ Maps normalized coupon titles to coupons with the goal of being able to match coupons by title
    e.g. to find duplicates or coupons with different IDs containing the same products. """
    couponTitleMappingTmp = {}
    for coupon in coupons.values():
        couponTitleMappingTmp.setdefault(coupon.getNormalizedTitle(), []).append(coupon)
    return couponTitleMappingTmp


USER_SETTINGS_ON_OFF = {
    # TODO: Obtain these Keys and default values from "User" Mapping class and remove this mess!
    "notifyWhenFavoritesAreBack": {
        "description": "Favoriten Benachrichtigungen",
        "default": False
    },
    "notifyWhenNewCouponsAreAvailable": {
        "description": "Benachrichtigung bei neuen Coupons",
        "default": False
    },
    "displayQR": {
        "description": "QR Codes zeigen",
        "default": True
    },
    "displayHiddenAppCouponsWithinGenericCategories": {
        "description": "Versteckte App Coupons in Kategorien zeigen*¹",
        "default": False
    },
    "displayCouponCategoryPayback": {
        "description": "Payback Coupons/Karte im Hauptmenü zeigen",
        "default": True
    },
    "displayFeedbackCodeGenerator": {
        "description": "Feedback Code Generator im Hauptmenü zeigen",
        "default": True
    },
    "displayBKWebsiteURLs": {
        "description": "BK Verlinkungen im Hauptmenü zeigen?",
        "default": True
    },
    "highlightFavoriteCouponsInButtonTexts": {
        "description": "Favoriten in Buttons mit " + SYMBOLS.STAR + " markieren",
        "default": True
    },
    "highlightNewCouponsInCouponButtonTexts": {
        "description": "Neue Coupons in Buttons mit " + SYMBOLS.NEW + " markieren",
        "default": True
    },
    "autoDeleteExpiredFavorites": {
        "description": "Abgelaufene Favoriten automatisch löschen",
        "default": False
    }
}

# Enable this to show BETA setting to users --> Only enable this if there are beta features available
# 2022-02-19: Keep this enabled as a dummy although there are no BETA features as disabling it would possibly render the "Reset settings to default" function useless
DISPLAY_BETA_SETTING = False

""" This is a helper for basic user on/off settings """
if DISPLAY_BETA_SETTING:
    USER_SETTINGS_ON_OFF["enableBetaFeatures"] = {
        "description": "Beta Features aktivieren",
        "default": False
    }
