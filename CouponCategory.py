from typing import Union, List

from Helper import SYMBOLS, formatDateGerman, BotAllowedCouponTypes, CouponType, formatPrice
from UtilsCouponsDB import Coupon, CouponSortMode, CouponSortModes


class CouponCategory:

    def __init__(self, coupons: Union[CouponType, int, dict, List]):
        # TODO: Improve this so we can inject custom category names as auto detection may return unexpected results
        self.coupons = None
        self.mainCouponType = None
        self.couponTypes = set()
        self.displayDescription = False  # Display description for this category in bot menu?
        self.expireDatetimeLowest = None
        self.expireDatetimeHighest = None
        self.numberofCouponsValid = 0
        self.numberofCouponsTotal = 0
        self.numberofCouponsHidden = 0
        self.numberofCouponsEatable = 0
        self.numberofCouponsEatableWithPrice = 0
        self.numberofCouponsNew = 0
        self.numberofCouponsWithFriesAndDrink = 0
        self.numberofVeggieCoupons = 0
        self.totalPrice = 0
        if isinstance(coupons, dict):
            self.coupons = list(coupons.values())
        elif isinstance(coupons, list):
            self.coupons = coupons
        if self.coupons is not None:
            for coupon in self.coupons:
                self.updateWithCouponInfo(coupon)
            if len(self.couponTypes) == 1:
                for first_item in self.couponTypes:
                    self.mainCouponType = first_item
                    break
            else:
                self.mainCouponType = None
        else:
            self.mainCouponType = coupons
        if self.mainCouponType is None:
            self.nameSingular = "Coupon"
            self.namePlural = "Alle Coupons"
            self.namePluralWithoutSymbol = "Alle Coupons"
            self.description = "Coupons mehrerer Kategorien"
        elif self.mainCouponType == CouponType.APP:
            self.nameSingular = "App Coupon"
            self.namePlural = "App Coupons"
            self.namePluralWithoutSymbol = "App Coupons"
            self.description = "Coupons aus der BK App"
        elif self.mainCouponType == CouponType.PAPER:
            self.nameSingular = "Papiercoupon"
            self.namePlural = SYMBOLS.NEWSPAPER + "Papiercoupons"
            self.namePluralWithoutSymbol = "Papiercoupons"
            self.description = "Coupons der Papier Couponbögen"
        elif self.mainCouponType == CouponType.PAPER_UNSAFE:
            self.nameSingular = "Papiercoupon (unsafe)"
            self.namePlural = SYMBOLS.NEWSPAPER + "Papiercoupons (unsafe)"
            self.namePluralWithoutSymbol = "Papiercoupons (unsafe)"
            self.description = "Coupons aus der \"Coupons2\" API, die keinem anderen Coupon-Typen zugewiesen werden konnten."
        elif self.mainCouponType == CouponType.ONLINE_ONLY:
            self.nameSingular = "Online Only"
            self.namePlural = "Online only"
            self.namePluralWithoutSymbol = "Online Only"
            self.description = "Coupons, die mit hoher Wahrscheinlichkeit nur online oder am Terminal bestellbar sind"
        elif self.mainCouponType == CouponType.ONLINE_ONLY_STORE_SPECIFIC:
            self.nameSingular = "Online only (store specific)"
            self.namePlural = "Online only (store specific)"
            self.namePluralWithoutSymbol = "Online only (store specific)"
            self.description = "Coupons, die nur in bestimmten# Filialen gültig sind"
        elif self.mainCouponType == CouponType.SPECIAL:
            self.nameSingular = "Special Coupon"
            self.namePlural = SYMBOLS.GIFT + "Special Coupons"
            self.namePluralWithoutSymbol = "Special Coupons"
            self.description = "Diese Coupons sind evtl. nicht in allen Filialen einlösbar!"
        elif self.mainCouponType == CouponType.PAYBACK:
            self.nameSingular = "Payback Coupon"
            self.namePlural = SYMBOLS.PARK + "ayback Coupons"
            self.namePluralWithoutSymbol = "Payback Coupons"
            self.description = "Payback Papiercoupons"
        else:
            self.nameSingular = "Unbekannt"
            self.namePlural = "Unbekannt"
            self.namePluralWithoutSymbol = "Unbekannt"
        # if self.isVeggie():
        #     self.nameSingular = '[Veggie] ' + self.nameSingular
        #     self.namePlural = '[Veggie] ' + self.namePlural

    def isValidSourceForBot(self) -> bool:
        if self.mainCouponType in BotAllowedCouponTypes:
            return True
        else:
            return False

    def getTotalPrice(self) -> float:
        return self.totalPrice

    def getNumberofCouponsEatableWithPrice(self) -> int:
        return self.numberofCouponsEatableWithPrice

    def getNumberofCouponsEatableWithoutPrice(self) -> int:
        return self.numberofCouponsEatable - self.numberofCouponsEatableWithPrice

    def setNumberofCouponsEatableWithPrice(self, newNumber: int):
        self.numberofCouponsEatableWithPrice = newNumber

    def setTotalPrice(self, newPrice: float):
        self.totalPrice = newPrice

    def isEatable(self) -> bool:
        """ Typically all coupon categories except Payback coupons will return True here as they do contain at least one item that is considered 'eatable'. """
        if self.numberofCouponsEatable > 0:
            return True
        else:
            return False

    def isVeggie(self):
        """ Returns True if all coupons in this categorie are veggie. """
        if len(self.couponTypes) == 1 and self.mainCouponType == CouponType.PAYBACK:
            # Only Payback coupons in this category -> Technically veggie but logically not ;)
            return False
        elif self.numberofCouponsTotal > 0 and self.numberofCouponsTotal == self.numberofVeggieCoupons:
            return True
        else:
            return False

    def isEligibleForDuplicateRemoval(self):
        if self.mainCouponType == CouponType.PAYBACK:
            return False
        else:
            return True

    def isEligableForSort(self):
        if len(self.getSortModes()) > 1:
            return True
        else:
            return False

    def getSortModes(self) -> List:
        """ Returns all SortModes which make sense for this set of coupons. """
        if self.coupons is None:
            return []
        sortModes = []
        if self.totalPrice > 0:
            sortModes.append(CouponSortModes.PRICE)
            sortModes.append(CouponSortModes.PRICE_DESCENDING)
        if self.numberofCouponsTotal != self.numberofCouponsWithFriesAndDrink:
            sortModes.append(CouponSortModes.MENU_PRICE)
        if len(self.couponTypes) > 1:
            sortModes.append(CouponSortModes.TYPE_MENU_PRICE)
        return sortModes

    def allowsSortMode(self, sortModeToCheckFor: CouponSortMode) -> bool:
        """ Checks if desired sortMode is currently allowed. """
        sortModes = self.getSortModes()
        for possibleSortMode in sortModes:
            if possibleSortMode == sortModeToCheckFor:
                return True
        return False

    def getNextPossibleSortMode(self, sortMode: CouponSortMode) -> CouponSortMode:
        possibleSortModes = self.getSortModes()
        for possibleSortMode in possibleSortModes:
            if possibleSortMode.getSortCode() > sortMode.getSortCode():
                return possibleSortMode
        # Fallback/Rollover to first sort
        return possibleSortModes[0]

    def getSortModeCode(self, desiredSortMode: CouponSortMode, fallbackSortMode: CouponSortMode) -> CouponSortMode:
        if self.allowsSortMode(desiredSortMode):
            return desiredSortMode
        else:
            return fallbackSortMode

    def getCategoryInfoText(self, withMenu: Union[bool, None], includeHiddenCouponsInCount: Union[bool, None]) -> str:
        if self.mainCouponType == CouponType.APP and self.numberofCouponsTotal == self.numberofCouponsHidden:
            # Only hidden (App-) coupons
            couponCount = self.numberofCouponsHidden
            text = '<b>[{couponCount} Stück] {couponCategoryName} versteckte</b>'
        elif withMenu is None or withMenu is True:
            couponCount = self.numberofCouponsTotal
            text = '<b>[{couponCount} Stück] {couponCategoryName}</b>'
        else:
            couponCount = self.numberofCouponsTotal - self.numberofCouponsWithFriesAndDrink
            text = '<b>[{couponCount} Stück] {couponCategoryName} ohne Menü</b>'
        if includeHiddenCouponsInCount is False:
            couponCount -= self.numberofCouponsHidden
        # if self.coupons is not None:
        #     couponCount = len(self.coupons)
        if couponCount == 1:
            couponCategoryName = self.nameSingular
        else:
            couponCategoryName = self.namePluralWithoutSymbol
        text = text.format(couponCount=couponCount, couponCategoryName=couponCategoryName)
        if self.displayDescription and self.description is not None:
            text += '\n' + self.description
        text += '\n' + self.getExpireDateInfoText()
        return text

    def getExpireDateInfoText(self) -> str:
        if self.expireDatetimeLowest is None or self.expireDatetimeHighest is None:
            return "Gültig bis ??"
        elif self.expireDatetimeLowest == self.expireDatetimeHighest:
            return "Gültig bis " + formatDateGerman(self.expireDatetimeLowest)
        else:
            return "Gültig bis min " + formatDateGerman(self.expireDatetimeLowest) + " max " + formatDateGerman(self.expireDatetimeHighest)

    def getPriceInfoText(self) -> Union[str, None]:
        if self.getNumberofCouponsEatableWithPrice() == 0:
            return None
        text = "<b>Gesamtwert:</b> " + formatPrice(self.getTotalPrice())
        if self.getNumberofCouponsEatableWithoutPrice() > 0:
            text += "*\n* außer " + str(
                self.getNumberofCouponsEatableWithoutPrice()) + " Coupons, deren Preis nicht bekannt ist."
        return text

    def updateWithCouponInfo(self, couponOrCouponList: Union[Coupon, List[Coupon]]):
        """ Updates category with information of given Coupon(s). """
        if isinstance(couponOrCouponList, Coupon):
            couponList = [couponOrCouponList]
        else:
            couponList = couponOrCouponList
        for coupon in couponList:
            if coupon.isValid():
                self.numberofCouponsValid += 1
            self.couponTypes.add(coupon.type)
            self.numberofCouponsTotal += 1
            if coupon.isHidden:
                self.numberofCouponsHidden += 1
            if coupon.isEatable():
                self.numberofCouponsEatable += 1
            if coupon.isNewCoupon():
                self.numberofCouponsNew += 1
            if coupon.isContainsFriesAndDrink():
                self.numberofCouponsWithFriesAndDrink += 1
            if coupon.isVeggie():
                self.numberofVeggieCoupons += 1
            # Update expire-date info
            date = coupon.getExpireDatetime()
            if self.expireDatetimeLowest is None and self.expireDatetimeHighest is None:
                self.expireDatetimeLowest = date
                self.expireDatetimeHighest = date
            else:
                if date < self.expireDatetimeLowest:
                    self.expireDatetimeLowest = date
                elif date > self.expireDatetimeHighest:
                    self.expireDatetimeHighest = date
            if coupon.getPrice() is not None:
                self.setTotalPrice(self.getTotalPrice() + coupon.getPrice())
                self.setNumberofCouponsEatableWithPrice(self.getNumberofCouponsEatableWithPrice() + 1)
        # End of function
        return

