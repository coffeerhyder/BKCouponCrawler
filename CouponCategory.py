from typing import Union

from Helper import SYMBOLS


class CouponSource:
    UNKNOWN = -1
    APP = 0
    APP_VALID_AFTER_DELETION = 1
    APP_SAME_CHAR_AS_CURRENT_APP_COUPONS = 2
    PAPER = 3
    PAPER_UNSAFE = 4
    ONLINE_ONLY = 5
    ONLINE_ONLY_STORE_SPECIFIC = 6  # Placeholder - not used
    SPECIAL = 7
    PAYBACK = 8


class CouponCategory:

    def __init__(self, couponSrc: Union[CouponSource, int]):
        self.couponSource = couponSrc
        self.displayDescription = False  # Display description for this category in bot menu?
        self.addMenuEntryForCouponsWithoutCokeOrFries = True  # Deprecated 2021-12-14 TODO: Replace this with stuff below
        # TODO: Implement the stuff below
        self.numberofCouponsTotal = 0
        self.numberofCouponsHidden = 0
        self.numberofCouponsEatable = 0
        self.numberofCouponsNew = 0
        self.numberofCouponsWithFriesOrCoke = 0
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
            self.addMenuEntryForCouponsWithoutCokeOrFries = False
        elif couponSrc == CouponSource.PAYBACK:
            self.nameSingular = "Payback Coupon"
            self.namePlural = SYMBOLS.PARK + "ayback Coupons"
            self.namePluralWithoutSymbol = "Payback Coupons"
            self.description = "Payback Papiercoupons"
            # No extra "Coupons ohne Menü" menu selection for Payback coupons!
            self.addMenuEntryForCouponsWithoutCokeOrFries = False
        else:
            self.nameSingular = "Unbekannt"
            self.namePlural = "Unbekannt"
            self.namePluralWithoutSymbol = "Unbekannt"

    def isValidSourceForBot(self) -> bool:
        if self.couponSource in BotAllowedCouponSources:
            return True
        else:
            return False


# All CouponSources which will be used in our bot (will be displayed in bot menu as categories)
BotAllowedCouponSources = [CouponSource.APP, CouponSource.PAPER, CouponSource.SPECIAL, CouponSource.PAYBACK]
