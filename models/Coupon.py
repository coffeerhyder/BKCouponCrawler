import logging
import os
import re
from datetime import datetime
from enum import Enum
from typing import Union

from couchdb.mapping import Document, TextField, IntegerField, FloatField, ListField, BooleanField

from BotUtils import getImageBasePath
from Helper import shortenProductNames, SYMBOLS, getCurrentDate, couponTitleContainsFriesAndDrink, couponTitleContainsChiliCheese, couponTitleContainsPlantBasedFood, \
    productTitleIsVeggieFood, CouponType, getTimezone, formatDateGerman, formatPrice, getFilenameFromURL

COUPON_IS_NEW_FOR_SECONDS = 24 * 60 * 60


class CouponTextRepresentationPLUMode(Enum):
    """ This can be used to define how PLUs in short texts shall be represented. """
    SHORT_PLU = 1
    LONG_PLU = 2
    ALL_PLUS = 3


class Coupon(Document):
    plu = TextField()
    uniqueID = TextField()
    price = IntegerField()
    priceCompare = IntegerField()
    staticReducedPercent = IntegerField()
    title = TextField()
    subtitle = TextField()
    timestampAddedToDB = FloatField(default=0)
    timestampLastModifiedDB = FloatField(default=0)
    timestampStart = FloatField(default=0)
    timestampExpireInternal = FloatField()  # Internal expire-date
    timestampExpire = FloatField()  # Expire date used by BK in their apps -> "Real" expire date.
    timestampCouponNotInAPIAnymore = FloatField() # 2023-05-09: Not used at this moment
    timestampIsNew = FloatField(default=0)  # Last timestamp from which on this coupon was new
    dateFormattedExpire = TextField()
    imageURL = TextField()
    paybackMultiplicator = IntegerField()
    productIDs = ListField(IntegerField())
    type = IntegerField(name='source')  # Legacy. This is called "type" now!
    isNewUntilDate = TextField()  # Date until which this coupon shall be treated as new. Use this as an override of default handling.
    isHidden = BooleanField(default=False)  # Typically only available for upsell App coupons
    description = TextField()
    tags = ListField(TextField())
    webviewID = TextField()
    webviewURL = TextField()

    def __str__(self):
        return f'{self.id=} | {self.plu} | {self.getTitle()} | {self.getPriceFormatted()} | START: {self.getStartDateFormatted()} | END {self.getExpireDateFormatted()}  | WEBVIEW: {self.getWebviewURL()}'

    def getPLUOrUniqueIDOrRedemptionHint(self) -> str:
        """ Returns PLU if existant, returns UNIQUE_ID otherwise. """
        if self.plu is not None:
            return self.plu
        else:
            showQrHintWhenPLUIsUnavailable = True
            if showQrHintWhenPLUIsUnavailable:
                return 'QR! ' + self.id
            else:
                return self.id

    def getNormalizedTitle(self) -> Union[str, None]:
        title = self.getTitle()
        title = shortenProductNames(title)
        title = re.sub(r'[\W_]+', '', title).lower()
        return title

    def getTitle(self) -> Union[str, None]:
        if self.paybackMultiplicator is not None:
            return f'{self.paybackMultiplicator}Fach auf alle Speisen & Getränke'
        else:
            return self.title

    def getSubtitle(self) -> Union[str, None]:
        return self.subtitle

    def getTitleShortened(self, includeVeggieSymbol: bool = True, includeChiliCheeseSymbol: bool = True) -> Union[str, None]:
        shortenedTitle = shortenProductNames(self.getTitle())
        nutritionSymbolsString = self.getNutritionSymbols(includeVeggieSymbol=includeVeggieSymbol, includeChiliCheeseSymbol=includeChiliCheeseSymbol)
        if nutritionSymbolsString is not None:
            shortenedTitle = nutritionSymbolsString + shortenedTitle
        return shortenedTitle

    def getNutritionSymbols(self, includeMeatSymbol: bool = False, includeVeggieSymbol: bool = True, includeChiliCheeseSymbol: bool = True) -> Union[str, None]:
        """ Returns string of [allowed] nutrition symbols. """
        if not self.isEatable():
            return None
        symbols = []
        if includeMeatSymbol and self.isContainsMeat():
            symbols.append(SYMBOLS.MEAT)
        elif includeVeggieSymbol and self.isVeggie():
            symbols.append(SYMBOLS.BROCCOLI)
        if includeChiliCheeseSymbol and self.isContainsChiliCheese():
            symbols.append(SYMBOLS.CHILI)
        if len(symbols) == 0:
            return None
        symbolsString = "".join(symbols)
        return symbolsString

    def isExpiredForLongerTime(self) -> bool:
        """ Using this check, coupons that e.g. expire on midnight and get elongated will not be marked as new because really they aren't. """
        expireDatetime = self.getExpireDatetime()
        if expireDatetime is None:
            return True
        elif getCurrentDate().second - expireDatetime.second > 3600:
            """ 
             Coupon expired over one hour ago -> We consider this a "longer time"
             Using this check, coupons that e.g. expire on midnight and get elongated will not be marked as new because really they aren't.
             """
            return True
        else:
            """ Coupon is not expired or not "long enough". """
            return False

    def isExpired(self) -> bool:
        expireDatetime = self.getExpireDatetime()
        if expireDatetime is None or expireDatetime < getCurrentDate():
            # Coupon is expired
            return True
        else:
            return False

    def isNotYetActive(self) -> bool:
        startDatetime = self.getStartDatetime()
        if startDatetime is not None and startDatetime > getCurrentDate():
            # Start time hasn't been reached yet -> Coupon is not valid yet
            return True
        else:
            return False

    def isValid(self) -> bool:
        """ If this returns true, we can present the coupon to the user.
         If this returns false, this usually means that the coupon is expired or not yet available. """
        if self.isExpired():
            return False
        elif self.isNotYetActive():
            return False
        else:
            return True

    def isContainsFriesAndDrink(self) -> bool:
        return couponTitleContainsFriesAndDrink(self.getTitle())

    def isContainsChiliCheese(self) -> bool:
        return couponTitleContainsChiliCheese(self.getTitle())

    def isPlantBased(self) -> bool:
        if self.tags is not None:
            # First check tags
            for tag in self.tags:
                tag = tag.lower()
                if 'plant' in tag:
                    return True
        if couponTitleContainsPlantBasedFood(self.getTitle()):
            return True
        else:
            return False

    def isVeggie(self) -> bool:
        if self.isPlantBased():
            return True
        couponTitle = self.getTitle()
        products = couponTitle.split("+")
        # Check if tags contain any useful information.
        if self.tags:
            for tag in self.tags:
                tag = tag.lower()
                if tag == 'sweetkings':
                    return True
        for product in products:
            if not productTitleIsVeggieFood(product):
                # Coupon contains at least one non veggie product -> Not a veggie coupon
                return False
        # All products in this coupons are veggie -> It is a veggie coupon
        return True

    def isContainsMeat(self) -> bool:
        """ Returns true if this coupon contains at least one article with meat. """
        """ First check for plant based stuff in title because BK sometimes has wrong tags (e.g. tag contains "chicken" when article is veggie lol)... """
        if self.isPlantBased():
            return False
        elif self.isVeggie():
            return False
        elif self.tags is not None:
            for tag in self.tags:
                tag = tag.lower()
                if 'beef' in tag or 'chicken' in tag:
                    return True

        titleLower = self.getTitle().lower()
        if 'chicken' in titleLower:
            return True
        elif 'wings' in titleLower:
            return True
        elif 'beef' in titleLower:
            return True
        elif 'nugget' in titleLower and 'chili' not in titleLower:
            return True
        elif 'whopper' in titleLower:
            return True
        elif 'chili cheese burger' in titleLower:
            return True
        else:
            # If in doubt, it's not meat
            return False

    def getPrice(self) -> Union[float, None]:
        return self.price

    def getPriceCompare(self) -> Union[float, None]:
        """ Returns original price of this product (or all product it contains) without discount. """
        return self.priceCompare

    def isEatable(self) -> bool:
        """ If the product(s) this coupon provide(s) is/are not eatable and e.g. just probide a discount like Payback coupons, this will return False, else True. """
        if self.type == CouponType.PAYBACK:
            return False
        else:
            return True

    def isEligibleForDuplicateRemoval(self):
        """ Returns true if coupon title can be used to remove duplicates.
         """
        if self.type == CouponType.PAYBACK:
            return False
        else:
            return True

    def isNewCoupon(self) -> bool:
        """ Determines whether or not this coupon is considered 'new'. """
        currentTimestamp = getCurrentDate().timestamp()
        timePassedSinceCouponWasAddedToDB = currentTimestamp - self.timestampAddedToDB
        if timePassedSinceCouponWasAddedToDB < COUPON_IS_NEW_FOR_SECONDS:
            return True
        timePassedSinceLastNewTimestamp = currentTimestamp - self.timestampIsNew
        if timePassedSinceLastNewTimestamp < COUPON_IS_NEW_FOR_SECONDS:
            # Coupon has been added just recently and thus can still be considered 'new'
            # couponNewSecondsRemaining = COUPON_IS_NEW_FOR_SECONDS - timePassedSinceLastNewTimestamp
            # print(f'Coupon is considered as new for {formatSeconds(seconds=couponNewSecondsRemaining)} time')
            return True
        timePassedSinceCouponValidityStarted = -1
        if self.timestampStart > 0:
            timePassedSinceCouponValidityStarted = currentTimestamp - self.timestampStart
        if 0 < timePassedSinceCouponValidityStarted < COUPON_IS_NEW_FOR_SECONDS:
            return True
        if self.isNewUntilDate is not None:
            # Check if maybe coupon should be considered as new for X
            try:
                enforceIsNewOverrideUntilDate = datetime.strptime(self.isNewUntilDate + ' 23:59:59',
                                                                  '%Y-%m-%d %H:%M:%S').astimezone(getTimezone())
                if enforceIsNewOverrideUntilDate.timestamp() > getCurrentDate().timestamp():
                    return True
                else:
                    return False
            except:
                # This should never happen
                logging.warning("Coupon.isNewCoupon: WTF invalid date format??")
                return False
        return False

    def getStartDatetime(self) -> Union[datetime, None]:
        """ Returns datetime from which coupon is valid. Not all coupons got a startDatetime. """
        if self.timestampStart is not None and self.timestampStart > 0:
            return datetime.fromtimestamp(self.timestampStart, getTimezone())
        else:
            # Start date must not always be given
            return None

    def getExpireDatetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestampExpire, getTimezone())

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

    def getPriceFormatted(self, fallback: Union[str, None] = None) -> Union[str, None]:
        if self.price is not None:
            return formatPrice(self.price)
        else:
            return fallback

    def getPriceCompareFormatted(self, fallback=None) -> Union[str, None]:
        if self.priceCompare is not None:
            return formatPrice(self.priceCompare)
        else:
            return fallback

    def getReducedPercentage(self) -> Union[float, None]:
        if self.paybackMultiplicator is not None:
            # 0.5 points per euro (= base discount of 0.5% without higher multiplicator)
            return 0.5 * self.paybackMultiplicator
        elif self.price is not None and self.priceCompare is not None:
            return (1 - (self.price / self.priceCompare)) * 100
        elif self.staticReducedPercent is not None:
            return self.staticReducedPercent
        else:
            return None

    def getReducedPercentageFormatted(self, fallback=None) -> Union[str, None]:
        """ Returns price reduction in percent if bothb the original price and the reduced/coupon-price are available.
         E.g. "-39%" """
        reducedPercentage = self.getReducedPercentage()
        if reducedPercentage is not None:
            if self.paybackMultiplicator is not None:
                # Add one decimal point for low percentage reducements such as Payback coupons as those will often only get us like 2.5% discount.
                return '-' + f'{reducedPercentage:2.1f}' + '%'
            else:
                return '-' + f'{reducedPercentage:2.0f}' + '%'
        else:
            return fallback

    def getUniqueIdentifier(self) -> str:
        """ Returns an unique identifier String which can be used to compare coupon objects. """
        plustring = "undefined" if self.plu is None else self.plu
        return f'{self.id}_{plustring}_{self.timestampExpire}_{self.imageURL}'

    def getComparableValue(self) -> str:
        """ Returns value which can be used to compare given coupon object to another one.
         This might be useful in the future to e.g. find coupons that contain exactly the same products and cost the same price as others.
          Do NOT use this to compare multiple Coupon objects! Use couponDBGetUniqueIdentifier instead!
          """
        return self.getTitle().lower() + str(self.price)

    def getImagePath(self) -> Union[str, None]:
        if self.imageURL is None:
            return None
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
            logging.warning(f'Returning fallback QR image for: {path}')
            return open('media/fallback_image_missing_qr_image.jpeg', mode='rb')

    def getWebviewURL(self) -> Union[str, None]:
        if self.webviewID is not None:
            # Default for DB coupons
            return f'https://www.burgerking.de/rewards/offers/{self.webviewID}'
        elif self.webviewURL is not None:
            # Static webview URL e.g. useful for Payback coupons -> Links to mydealz deals
            return self.webviewURL
        else:
            return None

    def getDescription(self) -> Union[str, None]:
        description = self.description
        if self.type == CouponType.PAPER and self.imageURL is not None:
            if description is None:
                description = ""
            elif len(description) > 0:
                description += "\n"
            description += f"{SYMBOLS.WARNING}Achtung!\nDerzeit fehlen die original Produktbilder von Papiercoupons!\nDas Bild dieses Coupons stammt vom gleichnamigen App Coupon! Es gelten die Textangaben in den Buttons und hier im Post-Text, nicht die aus den Bildern!!"
        return description

    def generateCouponShortText(self, highlightIfNew: bool = True, includeVeggieSymbol: bool = True, includeChiliCheeseSymbol: bool = True, plumode: CouponTextRepresentationPLUMode = CouponTextRepresentationPLUMode.ALL_PLUS) -> str:
        """ Returns e.g. "Y15 | 2Whopper+M🍟+0,4Cola | 8,99€" """
        if plumode == CouponTextRepresentationPLUMode.ALL_PLUS and self.plu is not None:
            # All PLUs
            vouchercode = f"{self.plu} | {self.id}"
        elif plumode == CouponTextRepresentationPLUMode.SHORT_PLU and self.plu is not None:
            # Short-PLU
            vouchercode = self.plu
        else:
            # Long-PLU
            vouchercode = self.id
        couponText = ''
        if highlightIfNew and self.isNewCoupon():
            couponText += SYMBOLS.NEW
        couponText += vouchercode + " | " + self.getTitleShortened(includeVeggieSymbol=includeVeggieSymbol, includeChiliCheeseSymbol=includeChiliCheeseSymbol)
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponShortTextFormatted(self, highlightIfNew: bool) -> str:
        """ Returns e.g. "<b>Y15</b> | 2Whopper+M🍟+0,4Cola | 8,99€" """
        couponText = ''
        if highlightIfNew and self.isNewCoupon():
            couponText += SYMBOLS.NEW
        couponText += "<b>" + self.getPLUOrUniqueIDOrRedemptionHint() + "</b> | " + self.getTitleShortened()
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponShortTextFormattedWithHyperlinkToChannelPost(self, highlightIfNew: bool, publicChannelName: str,
                                                                   messageID: int) -> str:
        """ Returns e.g. "Y15 | 2Whopper+M🍟+0,4Cola (https://t.me/betterkingpublic/1054) | 8,99€" """
        couponText = "<b>" + self.getPLUOrUniqueIDOrRedemptionHint() + "</b> | <a href=\"https://t.me/" + publicChannelName + '/' + str(
            messageID) + "\">"
        if highlightIfNew and self.isNewCoupon():
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
        couponText += "\n<b>" + self.getPLUOrUniqueIDOrRedemptionHint() + "</b>"
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
        couponText += "\n<b>" + self.getPLUOrUniqueIDOrRedemptionHint() + "</b>"
        couponText = self.appendPriceInfoText(couponText)
        return couponText

    def generateCouponLongTextFormattedWithDescription(self, highlightIfNew: bool):
        """
        :param highlightIfNew: Add emoji to text if coupon is new.
        :return: E.g. "<b>B3</b> | 1234 | 13.99€ | -50%\nGültig bis:19.06.2021\nCoupon.description"
        """
        couponText = ''
        if highlightIfNew and self.isNewCoupon():
            couponText += SYMBOLS.NEW
        couponText += self.getTitle() + '\n'
        # Add PLU information
        if self.plu is not None and self.plu != self.id:
            couponText += '<b>' + self.plu + '</b>' + ' | ' + self.id
        else:
            # No PLU available or PLU equals ID (This is e.g. the case for Payback coupons)
            couponText += '<b>' + self.id + '</b>'
        couponText = self.appendPriceInfoText(couponText)
        """ Expire date should be always given but we can't be 100% sure! """
        expireDateFormatted = self.getExpireDateFormatted()
        if expireDateFormatted is not None:
            couponText += '\nGültig bis ' + expireDateFormatted
        description = self.getDescription()
        if description is not None:
            couponText += "\n" + description
        webviewURL = self.getWebviewURL()
        if self.plu is None:
            couponText += f'\n{SYMBOLS.WARNING} Keine nennbare PLU verfügbar -> QR Code zeigen!'
        if webviewURL is not None:
            couponText += f"\n{SYMBOLS.ARROW_RIGHT}<a href=\"{webviewURL}\">Webansicht</a>"
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


