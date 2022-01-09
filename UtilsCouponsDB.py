import logging
import os
from datetime import datetime
from enum import Enum
from typing import Union, List, Optional

from couchdb.mapping import TextField, FloatField, ListField, IntegerField, BooleanField, Document, DictField, Mapping
from pydantic import BaseModel

from CouponCategory import BotAllowedCouponSources, CouponSource
from Helper import getTimezone, getCurrentDate, getFilenameFromURL, SYMBOLS


class Coupon(Document):
    plu = TextField()
    uniqueID = TextField()
    price = FloatField()
    priceCompare = FloatField()
    staticReducedPercent = FloatField()
    title = TextField()
    titleShortened = TextField()
    timestampStart = FloatField()
    timestampExpire = FloatField()  # Internal expire-date
    timestampExpire2 = FloatField()  # Expire date used by BK in their apps -> "Real" expire date.
    dateFormattedStart = TextField()
    dateFormattedExpire = TextField()
    dateFormattedExpire2 = TextField()
    imageURL = TextField()
    productIDs = ListField(IntegerField())
    source = IntegerField()
    containsFriesOrCoke = BooleanField()
    isNew = BooleanField()
    isNewUntilDate = TextField()
    isHidden = BooleanField(default=False)  # Typically only available for App coupons
    isUnsafeExpiredate = BooleanField(
        default=False)  # Set this if timestampExpire2 is a made up date that is just there to ensure that the coupon is considered valid for a specified time
    description = TextField()

    def getPLUOrUniqueID(self) -> str:
        """ Returns PLU if existant, returns UNIQUE_ID otherwise. """
        if self.plu is not None:
            return self.plu
        else:
            return self.id

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

    def isEatable(self) -> bool:
        """ If the product(s) this coupon provide(s) is/are not eatable and e.g. just probide a discount like Payback coupons, this will return False, else True. """
        if self.source == CouponSource.PAYBACK:
            return False
        else:
            return True

    def getIsNew(self) -> bool:
        """ Determines whether ir not this coupon is considered 'new'. """
        if self.isNew is not None:
            return self.isNew
        elif self.isNewUntilDate is not None:
            try:
                enforceIsNewOverrideUntilDateStr = self.isNewUntilDate + ' 23:59:59'
                enforceIsNewOverrideUntilDate = datetime.strptime(enforceIsNewOverrideUntilDateStr, '%Y-%m-%d %H:%M:%S').astimezone(getTimezone())
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
        # First check for artificial expire-date which is usually shorter than the other date - prefer that!
        if self.timestampExpire2 is not None:
            return datetime.fromtimestamp(self.timestampExpire2, getTimezone())
        elif self.timestampExpire is not None:
            return datetime.fromtimestamp(self.timestampExpire, getTimezone())
        else:
            # This should never happen
            logging.warning("Found coupon without expiredate: " + self.id)
            return None

    def getExpireDateFormatted(self, fallback=None) -> Union[str, None]:
        if self.dateFormattedExpire2 is not None:
            return self.dateFormattedExpire2
        elif self.dateFormattedExpire is not None:
            return self.dateFormattedExpire
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
        else:
            return fallback

    def getUniqueIdentifier(self) -> str:
        """ Returns an unique identifier String which can be used to compare coupon objects. """
        expiredateStr = self.getExpireDateFormatted(fallback='undefined')
        return self.id + '_' + ("undefined" if self.plu is None else self.plu) + '_' + expiredateStr + '_' + self.imageURL

    def getComparableValue(self) -> str:
        """ Returns value which can be used to compare given coupon object to another one.
         This might be useful in the future to e.g. find coupons that contain exactly the same products and cost the same price as others.
          Do NOT use this to compare multiple Coupon objects! Use couponDBGetUniqueIdentifier instead!
          """
        return self.title.lower() + str(self.price)

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
            return None

    def generateCouponShortText(self, highlightIfNew: bool) -> str:
        """ Returns e.g. "Y15 | 2Whopper+M🍟+0,4Cola | 8,99€" """
        couponText = ''
        if self.getIsNew() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += self.getPLUOrUniqueID() + " | " + self.titleShortened
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponShortTextFormatted(self, highlightIfNew: bool) -> str:
        """ Returns e.g. "<b>Y15</b> | 2Whopper+M🍟+0,4Cola | 8,99€" """
        couponText = ''
        if self.getIsNew() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += "<b>" + self.getPLUOrUniqueID() + "</b> | " + self.titleShortened
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponShortTextFormattedWithHyperlinkToChannelPost(self, highlightIfNew: bool, publicChannelName: str, messageID: int) -> str:
        """ Returns e.g. "Y15 | 2Whopper+M🍟+0,4Cola (https://t.me/betterkingpublic/1054) | 8,99€" """
        couponText = "<b>" + self.getPLUOrUniqueID() + "</b> | <a href=\"https://t.me/" + publicChannelName + '/' + str(
            messageID) + "\">"
        if self.getIsNew() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += self.titleShortened + "</a>"
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponLongTextFormatted(self) -> str:
        """ Returns e.g. "2 Whopper + Mittlere Pommes + 0,4L Cola
         <b>Y15</b> | 8,99€ | -25% " """
        couponText = ''
        if self.getIsNew():
            couponText += SYMBOLS.NEW
        couponText += self.title
        couponText += "\n<b>" + self.getPLUOrUniqueID() + "</b>"
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponLongTextFormattedWithHyperlinkToChannelPost(self, publicChannelName: str, messageID: int) -> str:
        """ Returns e.g. "2 Whopper + Mittlere Pommes +0,4L Cola (https://t.me/betterkingpublic/1054)
         <b>Y15</b> | 8,99€ | -25% " """
        couponText = "<a href=\"https://t.me/" + publicChannelName + '/' + str(
            messageID) + "\">"
        if self.getIsNew():
            couponText += SYMBOLS.NEW
        couponText += self.title
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
        if self.getIsNew() and highlightIfNew:
            couponText += SYMBOLS.NEW
        couponText += self.title + '\n'
        if self.plu is not None:
            couponText += '<b>' + self.plu + '</b>' + ' | ' + self.id
        else:
            couponText += '<b>' + self.id + '</b>'
        couponText = self.appendPriceInfoText(couponText)
        """ Expire date should be always given but we can't be 100% sure! """
        expireDateFormatted = self.getExpireDateFormatted()
        if expireDateFormatted is not None:
            couponText += '\nGültig bis ' + expireDateFormatted
        if self.description is not None:
            couponText += "\n" + self.description
        return couponText

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

class UserFavorites:
    """ Helper class for users favorites. """

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
                unavailableFavoritesText += coupon.id + ' | ' + coupon.titleShortened
                priceInfoText = coupon.getPriceInfoText()
                if priceInfoText is not None:
                    unavailableFavoritesText += ' | ' + priceInfoText
            return unavailableFavoritesText


class User(Document):
    settings = DictField(
        Mapping.build(
            displayQR=BooleanField(default=False),
            displayHiddenAppCouponsWithinGenericCategories=BooleanField(default=False),
            displayCouponCategoryPayback=BooleanField(default=True),
            notifyWhenFavoritesAreBack=BooleanField(default=False),
            notifyWhenNewCouponsAreAvailable=BooleanField(default=False),
            highlightFavoriteCouponsInButtonTexts=BooleanField(default=True),
            highlightNewCouponsInCouponButtonTexts=BooleanField(default=True),
            autoDeleteExpiredFavorites=BooleanField(default=False),
            enableBetaFeatures=BooleanField(default=False)
        )
    )
    favoriteCoupons = DictField()

    def isFavoriteCoupon(self, coupon: Coupon):
        """ Checks if given coupon is users' favorite """
        if coupon.id in self.favoriteCoupons:
            return True
        else:
            return False

    def getUserFavorites(self, couponsFromDB: Union[dict, Document]) -> UserFavorites:
        """
        Gathers information about the given users' favorite available/unavailable coupons.
        Coupons from DB are required to get current dataset of available favorites.
        """
        if len(self.favoriteCoupons) == 0:
            # User does not have any favorites set --> There is no point to look for the additional information
            return UserFavorites()
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
            return UserFavorites(favoritesAvailable=availableFavoriteCoupons, favoritesUnavailable=unavailableFavoriteCoupons)


class InfoEntry(Document):
    timestampLastCrawl = FloatField(name="timestamp_last_crawl", default=-1)
    timestampLastChannelUpdate = FloatField(name="timestamp_last_telegram_channel_update", default=-1)
    informationMessageID = TextField(name="channel_last_information_message_id")
    couponTypeOverviewMessageIDs = ListField(TextField(), name="channel_last_coupon_type_overview_message_ids_")
    messageIDsToDelete = ListField(IntegerField(), name="message_ids_to_delete", default=[])


class ChannelCoupon(Document):
    # names are given to ensure compatibility to older DB versions. TODO: Remove this whenever possible. To do this, channel needs to be manually wiped with current/older version. Then these names can be removed and channel update can be sent out.
    uniqueIdentifier = TextField(name="coupon_unique_identifier")
    messageIDs = ListField(IntegerField(), name="coupon_message_ids")
    timestampMessagesPosted = FloatField(name="timestamp_tg_messages_posted", default=-1)


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
    return sorted(couponList, key=lambda x: -1 if x.get(Coupon.price.name, -1) is None else x.get(Coupon.price.name, -1))


class CouponFilter(BaseModel):
    activeOnly: Optional[bool] = True
    containsFriesAndCoke: Optional[Union[bool, None]] = None
    excludeCouponsByDuplicatedProductTitles: Optional[bool] = False
    allowedCouponSources: Optional[Union[List[int], None]] = None  # None = allow all sources!
    isNew: Optional[Union[bool, None]] = None
    isHidden: Optional[Union[bool, None]] = None
    sortMode: Optional[Union[None, CouponSortMode]]
