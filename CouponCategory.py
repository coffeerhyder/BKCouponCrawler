from typing import Union, List

from Helper import SYMBOLS, formatDateGerman, BotAllowedCouponSources, CouponSource, formatPrice
from UtilsCouponsDB import Coupon


class CouponCategory:

    def __init__(self, parameter: Union[CouponSource, int, List]):
        self.coupons = None
        self.couponSource = parameter
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
            mainCouponSource = self.coupons[0].source
            isAllSameCouponSource = True
            for coupon in self.coupons:
                self.updateWithCouponInfo(coupon)
                if coupon.source != mainCouponSource:
                    isAllSameCouponSource = False
            if isAllSameCouponSource:
                self.couponSource = mainCouponSource
            else:
                self.couponSource = None
        else:
            self.couponSource = parameter
        if self.couponSource is None:
            self.nameSingular = "Coupon"
            self.namePlural = "Alle Coupons"
            self.namePluralWithoutSymbol = "Alle Coupons"
            self.description = "Coupons mehrerer Kategorien"
        elif self.couponSource == CouponSource.APP:
            self.nameSingular = "App Coupon"
            self.namePlural = "App Coupons"
            self.namePluralWithoutSymbol = "App Coupons"
            self.description = "Coupons aus der BK App"
        elif self.couponSource == CouponSource.PAPER:
            self.nameSingular = "Papiercoupon"
            self.namePlural = SYMBOLS.NEWSPAPER + "Papiercoupons"
            self.namePluralWithoutSymbol = "Papiercoupons"
            self.description = "Coupons der Papier Couponbögen"
        elif self.couponSource == CouponSource.PAPER_UNSAFE:
            self.nameSingular = "Papiercoupon (unsafe)"
            self.namePlural = SYMBOLS.NEWSPAPER + "Papiercoupons (unsafe)"
            self.namePluralWithoutSymbol = "Papiercoupons (unsafe)"
            self.description = "Coupons aus der \"Coupons2\" API, die keinem anderen Coupon-Typen zugewiesen werden konnten."
        elif self.couponSource == CouponSource.ONLINE_ONLY:
            self.nameSingular = "Online Only"
            self.namePlural = "Online only"
            self.namePluralWithoutSymbol = "Online Only"
            self.description = "Coupons, die mit hoher Wahrscheinlichkeit nur online oder am Terminal bestellbar sind"
        elif self.couponSource == CouponSource.ONLINE_ONLY_STORE_SPECIFIC:
            self.nameSingular = "Online only (store specific)"
            self.namePlural = "Online only (store specific)"
            self.namePluralWithoutSymbol = "Online only (store specific)"
            self.description = "Coupons, die nur in bestimmten Filialen gültig sind"
        elif self.couponSource == CouponSource.SPECIAL:
            self.nameSingular = "Special Coupon"
            self.namePlural = SYMBOLS.GIFT + "Special Coupons"
            self.namePluralWithoutSymbol = "Special Coupons"
            self.description = "Diese Coupons sind evtl. nicht in allen Filialen einlösbar!"
        elif self.couponSource == CouponSource.PAYBACK:
            self.nameSingular = "Payback Coupon"
            self.namePlural = SYMBOLS.PARK + "ayback Coupons"
            self.namePluralWithoutSymbol = "Payback Coupons"
            self.description = "Payback Papiercoupons"
        else:
            self.nameSingular = "Unbekannt"
            self.namePlural = "Unbekannt"
            self.namePluralWithoutSymbol = "Unbekannt"

    def isValidSourceForBot(self) -> bool:
        if self.couponSource in BotAllowedCouponSources:
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

    def getCategoryInfoText(self, withMenu: Union[bool, None], includeHiddenCouponsInCount: Union[bool, None]) -> str:
        if self.couponSource == CouponSource.APP and self.numberofCouponsTotal == self.numberofCouponsHidden:
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
    mainCouponSource = coupons[0].source
    category = CouponCategory(parameter=mainCouponSource)
    for coupon in coupons:
        category.updateWithCouponInfo(coupon)
    return category

