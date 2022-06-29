from typing import Union, List

from Helper import SYMBOLS, formatDateGerman, BotAllowedCouponTypes, CouponType, formatPrice
from UtilsCouponsDB import Coupon, CouponSortMode


class CouponCategory:

    def __init__(self, parameter: Union[CouponType, int, List]):
        self.coupons = None
        self.mainCouponType = None
        self.couponTypes = set()
        self.displayDescription = False  # Display description for this category in bot menu?
        self.expireDatetimeLowest = None
        self.expireDatetimeHighest = None
        self.numberofCouponsTotal = 0
        self.numberofCouponsHidden = 0
        self.numberofCouponsEatable = 0
        self.numberofCouponsEatableWithPrice = 0
        self.numberofCouponsNew = 0
        self.numberofCouponsWithFriesOrCoke = 0
        self.totalPrice = 0
        if isinstance(parameter, list):
            self.coupons = parameter
            mainCouponType = self.coupons[0].type
            isAllSameCouponType = True
            for coupon in self.coupons:
                self.updateWithCouponInfo(coupon)
                if coupon.type != mainCouponType:
                    isAllSameCouponType = False
            if isAllSameCouponType:
                self.mainCouponType = mainCouponType
            else:
                self.mainCouponType = None
        else:
            self.mainCouponType = parameter
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
            self.description = "Coupons, die nur in bestimmten Filialen gültig sind"
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

    def setNumberofCouponsTotal(self, newNumber: int):
        self.numberofCouponsTotal = newNumber

    def setNumberofCouponsHidden(self, newNumber: int):
        self.numberofCouponsHidden = newNumber

    def setNumberofCouponsEatable(self, newNumber: int):
        self.numberofCouponsEatable = newNumber

    def setNumberofCouponsEatableWithPrice(self, newNumber: int):
        self.numberofCouponsEatableWithPrice = newNumber

    def setNumberofCouponsNew(self, newNumber: int):
        self.numberofCouponsNew = newNumber

    def setNumberofCouponsWithFriesOrCoke(self, newNumber: int):
        self.numberofCouponsWithFriesOrCoke = newNumber

    def setTotalPrice(self, newPrice: float):
        self.totalPrice = newPrice

    def isEatable(self) -> bool:
        """ Typically all coupon categories except Payback coupons will return True here as they do contain at least one item that is considered 'eatable'. """
        if self.numberofCouponsEatable > 0:
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
        sortModes = []
        if self.totalPrice > 0:
            sortModes.append(CouponSortMode.PRICE)
            sortModes.append(CouponSortMode.PRICE_DESCENDING)
        if self.numberofCouponsTotal != self.numberofCouponsWithFriesOrCoke:
            sortModes.append(CouponSortMode.MENU_PRICE)
        if len(self.couponTypes) > 1:
            sortModes.append(CouponSortMode.TYPE_MENU_PRICE)
        return sortModes

    def getNextPossibleSortMode(self, sortMode: CouponSortMode) -> CouponSortMode:
        possibleSortModes = self.getSortModes()
        for possibleSortMode in possibleSortModes:
            if possibleSortMode.sortCode > sortMode.sortCode:
                return possibleSortMode
        # Fallback/Rollover to first sort
        return possibleSortModes[0]


    def getCategoryInfoText(self, withMenu: Union[bool, None], includeHiddenCouponsInCount: Union[bool, None]) -> str:
        if self.mainCouponType == CouponType.APP and self.numberofCouponsTotal == self.numberofCouponsHidden:
            # Only hidden (App-) coupons
            couponCount = self.numberofCouponsHidden
            text = '<b>[{couponCount} Stück] {couponCategoryName} versteckte</b>'
        elif withMenu is None or withMenu is True:
            couponCount = self.numberofCouponsTotal
            text = '<b>[{couponCount} Stück] {couponCategoryName}</b>'
        else:
            couponCount = self.numberofCouponsTotal - self.numberofCouponsWithFriesOrCoke
            text = '<b>[{couponCount} Stück] {couponCategoryName} ohne Menü</b>'
        if includeHiddenCouponsInCount is False:
            couponCount -= self.numberofCouponsHidden
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
                self.couponTypes.add(coupon.type)
                self.setNumberofCouponsTotal(self.numberofCouponsTotal + 1)
                if coupon.isHidden:
                    self.setNumberofCouponsHidden(self.numberofCouponsHidden + 1)
                if coupon.isEatable():
                    self.setNumberofCouponsEatable(self.numberofCouponsEatable + 1)
                if coupon.isNewCoupon():
                    self.setNumberofCouponsNew(self.numberofCouponsNew + 1)
                if coupon.isContainsFriesOrCoke():
                    self.setNumberofCouponsWithFriesOrCoke(self.numberofCouponsWithFriesOrCoke + 1)
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
        return None


def getCouponCategory(coupons: List[Coupon]) -> CouponCategory:
    """ Returns CouponCategory for given list of coupons.Assumes that this list only contains coupons of one
    category. """
    mainCouponType = coupons[0].type
    category = CouponCategory(parameter=mainCouponType)
    for coupon in coupons:
        category.updateWithCouponInfo(coupon)
    return category


