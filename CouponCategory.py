from datetime import datetime
from typing import Union, List

from Helper import SYMBOLS, formatDateGerman, BotAllowedCouponSources, CouponSource
from UtilsCouponsDB import Coupon
from BaseUtils import *


class CouponCategory:

    def __init__(self, couponSrc: Union[CouponSource, int]):
        self.couponSource = couponSrc
        self.displayDescription = False  # Display description for this category in bot menu?
        self.expireDatetimeLowest = None
        self.expireDatetimeHighest = None
        self.numberofCouponsTotal = 0
        self.numberofCouponsHidden = 0
        self.numberofCouponsEatable = 0
        self.numberofCouponsEatableWithoutPrice = 0
        self.numberofCouponsNew = 0
        self.numberofCouponsWithFriesOrCoke = 0
        self.totalPrice = 0
        if couponSrc == CouponSource.APP:
            self.nameSingular = "App Coupon"
            self.namePlural = "App Coupons"
            self.namePluralWithoutSymbol = "App Coupons"
            self.description = "Coupons aus der BK App"
        elif couponSrc == CouponSource.PAPER:
            self.nameSingular = "Papiercoupon"
            self.namePlural = SYMBOLS.NEWSPAPER + "Papiercoupons"
            self.namePluralWithoutSymbol = "Papiercoupons"
            self.description = "Coupons der Papier Couponbögen"
        elif couponSrc == CouponSource.PAPER_UNSAFE:
            self.nameSingular = "Papiercoupon (unsafe)"
            self.namePlural = SYMBOLS.NEWSPAPER + "Papiercoupons (unsafe)"
            self.namePluralWithoutSymbol = "Papiercoupons (unsafe)"
            self.description = "Coupons aus der \"Coupons2\" API, die keinem anderen Coupon-Typen zugewiesen werden konnten."
        elif couponSrc == CouponSource.ONLINE_ONLY:
            self.nameSingular = "Online Only"
            self.namePlural = "Online only"
            self.namePluralWithoutSymbol = "Online Only"
            self.description = "Coupons, die mit hoher Wahrscheinlichkeit nur online oder am Terminal bestellbar sind"
        elif couponSrc == CouponSource.ONLINE_ONLY_STORE_SPECIFIC:
            self.nameSingular = "Online only (store specific)"
            self.namePlural = "Online only (store specific)"
            self.namePluralWithoutSymbol = "Online only (store specific)"
            self.description = "Coupons, die nur in bestimmten Filialen gültig sind"
        elif couponSrc == CouponSource.SPECIAL:
            self.nameSingular = "Special Coupon"
            self.namePlural = SYMBOLS.GIFT + "Special Coupons"
            self.namePluralWithoutSymbol = "Special Coupons"
            self.description = "Diese Coupons sind evtl. nicht in allen Filialen einlösbar!"
        elif couponSrc == CouponSource.PAYBACK:
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

    def getNumberofCouponsEatableWithoutPrice(self) -> int:
        return self.numberofCouponsEatableWithoutPrice

    def setNumberofCouponsTotal(self, newNumber: int):
        self.numberofCouponsTotal = newNumber

    def setNumberofCouponsHidden(self, newNumber: int):
        self.numberofCouponsHidden = newNumber

    def setNumberofCouponsEatable(self, newNumber: int):
        self.numberofCouponsEatable = newNumber

    def setNumberofCouponsEatableWithoutPrice(self, newNumber: int):
        self.numberofCouponsEatableWithoutPrice = newNumber

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

    def getCategoryInfoText(self, withMenu: bool, includeHiddenCouponsInCount: bool) -> str:
        if withMenu:
            couponCount = self.numberofCouponsTotal
            text = '<b>{couponCount} {couponCategoryName} verfügbar:</b>'
        else:
            couponCount = self.numberofCouponsTotal - self.numberofCouponsWithFriesOrCoke
            text = '<b>{couponCount} {couponCategoryName} ohne Menü verfügbar:</b>'
        if not includeHiddenCouponsInCount:
            couponCount -= self.numberofCouponsHidden
        text = text.format(couponCount=couponCount, couponCategoryName=self.namePluralWithoutSymbol)
        text += '\n' + self.getExpireDateInfoText()
        return text

    def getExpireDateInfoText(self) -> str:
        if self.expireDatetimeLowest is None or self.expireDatetimeHighest is None:
            return "Gültig bis ??"
        elif self.expireDatetimeLowest == self.expireDatetimeHighest:
            return "Gültig bis " + formatDateGerman(self.expireDatetimeLowest)
        else:
            return "Gültig bis mind. " + formatDateGerman(self.expireDatetimeLowest) + " max. " + formatDateGerman(self.expireDatetimeHighest)

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
                price = coupon.getPrice()
                if price is not None:
                    self.setTotalPrice(self.getTotalPrice() + price)
                elif coupon.isEatable():
                    self.numberofCouponsEatableWithoutPrice += 1
        return None


def getCouponCategory(coupons: list) -> CouponCategory:
    """ Returns CouponCategory for given list of coupons. Assumes that this list only contains coupons of one
    category. """
    mainCouponSource = coupons[0].source
    category = CouponCategory(couponSrc=mainCouponSource)
    for coupon in coupons:
        # if coupon.source != mainCouponSource:
        #    logging.warning("Given list of coupons contains multiple categories! Result will be wrong!!")
        category.updateWithCouponInfo(coupon)
    return category
