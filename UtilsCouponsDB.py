import logging
from typing import Union, List

from Helper import SYMBOLS, CouponType
from models.Coupon import Coupon
from utils.CouponViews import CouponSortModes, getSortModeBySortCode, getAllCouponViews, CouponSortMode

MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION = 6 * 30 * 24 * 60 * 60
# X time before account would get deleted, we can inform the user X time before about upcoming auto account deletion
MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER = MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION - 9 * 24 * 60 * 60
MAX_HOURS_ACTIVITY_TRACKING = 48
MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION = 3
MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING = 2 * 24 * 60 * 60


def groupCouponsByType(coupons: dict) -> dict:
    """ Returns dict containing lists of coupons by type """
    couponsSeparatedByType = {}
    for coupon in list(coupons.values()):
        typelist = couponsSeparatedByType.setdefault(coupon.type, [])
        typelist.append(coupon)
    return couponsSeparatedByType


def sortCouponsByPrice(couponList: List[Coupon], descending: bool = False) -> List[Coupon]:
    """Sort by price -> But price is not always given -> Place items without prices at the BEGINNING of each list."""
    if isinstance(couponList, dict):
        couponList = couponList.values()
    return sorted(couponList,
                  key=lambda x: -1 if x.getPrice() is None else x.getPrice(), reverse=descending)


def sortCouponsByDiscount(couponList: List[Coupon], descending: bool = False) -> List[Coupon]:
    """Sort by price -> But price is not always given -> Place items without prices at the BEGINNING of each list."""
    if isinstance(couponList, dict):
        couponList = couponList.values()
    return sorted(couponList,
                  key=lambda x: 0 if x.getReducedPercentage() is None else x.getReducedPercentage(), reverse=descending)


def sortCouponsByNew(couponList: List[Coupon], descending: bool = False) -> List[Coupon]:
    """Sort by price -> But price is not always given -> Place items without prices at the BEGINNING of each list."""
    if isinstance(couponList, dict):
        couponList = couponList.values()
    return sorted(couponList,
                  key=lambda x: x.isNewCoupon(), reverse=descending)


def getCouponTitleMapping(coupons: Union[dict, list]) -> dict:
    """ Maps normalized coupon titles to coupons with the goal of being able to match coupons by title
    e.g. to find duplicates or coupons with different IDs containing the same products. """
    if isinstance(coupons, dict):
        coupons = coupons.values()
    couponTitleMappingTmp = {}
    for coupon in coupons:
        normalizedTitle = coupon.getNormalizedTitle()
        dupeslist = couponTitleMappingTmp.setdefault(normalizedTitle, [])
        dupeslist.append(coupon)
    return couponTitleMappingTmp


class SettingCategory:

    def __init__(self, title: str):
        self.title = title

    def getViewCode(self) -> Union[int, None]:
        """ Returns position of current sort mode in array of all sort modes. """
        couponViews = getAllCouponViews()
        index = 0
        for couponView in couponViews:
            if couponView == self:
                return index
            index += 1
        # This should never happen
        return None


class SettingCategories:
    MAIN_MENU = SettingCategory(title='Hauptmenü Buttons')
    GLOBAL_FILTERS = SettingCategory(title='Globale Coupon Filter')
    COUPON_DISPLAY = SettingCategory(title='Anzeigeeinstellungen')
    NOTIFICATIONS = SettingCategory(title='Benachrichtigungen')
    MISC = SettingCategory(title='Sonstige')


USER_SETTINGS_ON_OFF = {
    # TODO: Obtain these Keys and default values from "User" Mapping class and remove this mess!
    "displayCouponCategoryAllCouponsLongListWithLongTitles": {
        "category": SettingCategories.MAIN_MENU,
        "description": f"Kategorie 'Alle Coupons Liste lange Titel + Pics' zeigen",
        "default": False
    },
    "displayCouponCategoryAppCouponsHidden": {
        "category": SettingCategories.MAIN_MENU,
        "description": f"Kategorie 'App Coupons versteckte' zeigen",
        "default": True
    },
    # "displayCouponCategoryMeatWithoutPlantBased": {
    #     "category": SettingCategories.MAIN_MENU,
    #     "description": f"Kategorie Coupons ohne PlantBased ({SYMBOLS.MEAT}) zeigen",
    #     "default": False
    # },
    "displayCouponCategoryVeggie": {
        "category": SettingCategories.MAIN_MENU,
        "description": f"Kategorie Veggie Coupons ({SYMBOLS.BROCCOLI}) zeigen",
        "default": True
    },
    "displayCouponCategoryPayback": {
        "category": SettingCategories.MAIN_MENU,
        "description": "Kategorie Payback Buttons zeigen",
        "default": True
    },
    "displayOffersButton": {
        "category": SettingCategories.MAIN_MENU,
        "description": "Angebote Button zeigen",
        "default": True
    },
    "displayBKWebsiteURLs": {
        "category": SettingCategories.MAIN_MENU,
        "description": "BK Verlinkungen Buttons zeigen",
        "default": True
    },
    "displayFeedbackCodeGenerator": {
        "category": SettingCategories.MAIN_MENU,
        "description": "Feedback Code Generator Button zeigen",
        "default": True
    },
    "displayFAQLinkButton": {
        "category": SettingCategories.MAIN_MENU,
        "description": "FAQ Button zeigen",
        "default": True
    },
    "displayDonateButton": {
        "category": SettingCategories.MAIN_MENU,
        "description": "Spenden Button zeigen",
        "default": True
    },
    "displayAdminButtons": {
        "category": SettingCategories.MAIN_MENU,
        "description": "Admin Buttons anzeigen",
        "default": True
    },
    "displayPlantBasedCouponsWithinGenericCategories": {
        "category": SettingCategories.GLOBAL_FILTERS,
        "description": "Plant Based Coupons in Kategorien zeigen",
        "default": True
    },
    "displayHiddenUpsellingAppCouponsWithinGenericCategories": {
        "category": SettingCategories.GLOBAL_FILTERS,
        "description": "Versteckte App Coupons in Kategorien zeigen*¹",
        "default": True
    },
    "hideDuplicates": {
        "category": SettingCategories.GLOBAL_FILTERS,
        "description": "Duplikate ausblenden | Günstigere CP bevorz.",
        "default": False
    },
    "highlightFavoriteCouponsInButtonTexts": {
        "category": SettingCategories.COUPON_DISPLAY,
        "description": "Favoriten in Buttons mit " + SYMBOLS.STAR + " markieren",
        "default": True
    },
    "highlightNewCouponsInCouponButtonTexts": {
        "category": SettingCategories.COUPON_DISPLAY,
        "description": "Neue Coupons in Buttons mit " + SYMBOLS.NEW + " markieren",
        "default": True
    },
    "highlightVeggieCouponsInCouponButtonTexts": {
        "category": SettingCategories.COUPON_DISPLAY,
        "description": "Veggie Coupons in Buttons mit " + SYMBOLS.BROCCOLI + " markieren",
        "default": True
    },
    "highlightChiliCheeseCouponsInCouponButtonTexts": {
        "category": SettingCategories.COUPON_DISPLAY,
        "description": "Chili Cheese Coupons in Buttons mit " + SYMBOLS.CHILI + " markieren",
        "default": True
    },
    "displayQR": {
        "category": SettingCategories.COUPON_DISPLAY,
        "description": "QR Codes zeigen",
        "default": True
    },
    "displayCouponSortButton": {
        "category": SettingCategories.COUPON_DISPLAY,
        "description": "Coupon sortieren Button zeigen",
        "default": True
    },
    "enableTerminalMode": {
        "category": SettingCategories.COUPON_DISPLAY,
        "description": "Terminal Modus | LangPLU in Buttons zeigen",
        "default": False
    },
    "notifyWhenFavoritesAreBack": {
        "category": SettingCategories.NOTIFICATIONS,
        "description": "Favoriten Benachrichtigungen",
        "default": False
    },
    "notifyWhenNewCouponsAreAvailable": {
        "category": SettingCategories.NOTIFICATIONS,
        "description": "Benachrichtigung bei neuen Coupons",
        "default": False
    },
    "notifyMeAsAdminIfThereAreProblems": {
        "category": SettingCategories.NOTIFICATIONS,
        "description": "Admin Benachrichtigung bei Problemen",
        "default": True
    },
    "notifyOnBotNewsletter": {
        "category": SettingCategories.NOTIFICATIONS,
        "description": "BetterKing TG Newsletter",
        "default": True
    },
    "autoDeleteExpiredFavorites": {
        "category": SettingCategories.MISC,
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


def removeDuplicatedCoupons(coupons: Union[List[Coupon], dict]) -> dict:
    couponTitleMapping = getCouponTitleMapping(coupons)
    # Now clean our mapping: Sometimes one product may be available twice with multiple prices -> We want exactly one mapping per title
    couponsWithoutDuplicates = {}
    for normalizedTitle, coupons in couponTitleMapping.items():
        couponsForDuplicateRemoval = []
        for coupon in coupons:
            if coupon.isEligibleForDuplicateRemoval():
                couponsForDuplicateRemoval.append(coupon)
            else:
                # We cannot remove this coupon as duplicate by title -> Add it to our final results list
                couponsWithoutDuplicates[coupon.id] = coupon
        # Check if anything is left to do
        if len(couponsForDuplicateRemoval) == 0:
            continue
        # Sort these ones by price and pick the first (= cheapest) one for our mapping.
        isDifferentPrices = False
        firstPrice = None
        appCoupon = None
        if len(couponsForDuplicateRemoval) == 1:
            coupon = couponsForDuplicateRemoval[0]
            couponsWithoutDuplicates[coupon.id] = coupon
            continue
        for coupon in couponsForDuplicateRemoval:
            if firstPrice is None:
                firstPrice = coupon.getPrice()
            elif coupon.getPrice() != firstPrice:
                isDifferentPrices = True
            if coupon.type == CouponType.APP:
                appCoupon = coupon
        if isDifferentPrices:
            # Prefer cheapest coupon
            couponsSorted = sortCouponsByPrice(couponsForDuplicateRemoval)
            coupon = couponsSorted[0]
        elif appCoupon is not None:
            # Same prices but different sources -> Prefer App coupon
            coupon = appCoupon
        else:
            # Same prices but all coupons are from the same source -> Should never happen but we'll cover it anyways -> Select first item.
            coupon = couponsForDuplicateRemoval[0]
        couponsWithoutDuplicates[coupon.id] = coupon
    numberofRemovedDuplicates = len(coupons) - len(couponsWithoutDuplicates)
    logging.debug("Number of removed duplicates: " + str(numberofRemovedDuplicates))
    return couponsWithoutDuplicates


def sortCoupons(coupons: Union[list, dict], sortCode: Union[int, CouponSortMode]) -> dict:
    coupons = sortCouponsAsList(coupons, sortCode)
    filteredAndSortedCouponsDict = {}
    for coupon in coupons:
        filteredAndSortedCouponsDict[coupon.id] = coupon
    return filteredAndSortedCouponsDict


def sortCouponsAsList(coupons: Union[list, dict], sortCode: Union[int, CouponSortMode]) -> dict:
    if isinstance(coupons, dict):
        coupons = list(coupons.values())
    if isinstance(sortCode, CouponSortMode):
        sortMode = sortCode
    else:
        sortMode = getSortModeBySortCode(sortCode)
    if sortMode == CouponSortModes.TYPE_MENU_PRICE:
        couponsWithoutFriesAndDrink = []
        couponsWithFriesAndDrink = []
        allContainedCouponTypes = []
        for coupon in coupons:
            if coupon.type not in allContainedCouponTypes:
                allContainedCouponTypes.append(coupon.type)
            if coupon.isContainsFriesAndDrink():
                couponsWithFriesAndDrink.append(coupon)
            else:
                couponsWithoutFriesAndDrink.append(coupon)
        couponsWithoutFriesAndDrink = sortCouponsByPrice(couponsWithoutFriesAndDrink)
        couponsWithFriesAndDrink = sortCouponsByPrice(couponsWithFriesAndDrink)
        # Merge them together again.
        coupons = couponsWithoutFriesAndDrink + couponsWithFriesAndDrink
        # App coupons(source == 0) > Paper coupons
        allContainedCouponTypes.sort()
        # Separate sorted coupons by type
        couponsSeparatedByType = {}
        for couponType in allContainedCouponTypes:
            couponsTmp = list(filter(lambda x: x.type == couponType, coupons))
            couponsSeparatedByType[couponType] = couponsTmp
        # Put our list sorted by type together again -> Sort done
        coupons = []
        for allCouponsOfOneSourceType in couponsSeparatedByType.values():
            coupons += allCouponsOfOneSourceType
    elif sortMode == CouponSortModes.MENU_PRICE:
        couponsWithoutFriesAndDrink = []
        couponsWithFriesAndDrink = []
        for coupon in coupons:
            if coupon.isContainsFriesAndDrink():
                couponsWithFriesAndDrink.append(coupon)
            else:
                couponsWithoutFriesAndDrink.append(coupon)
        couponsWithoutFriesAndDrink = sortCouponsByPrice(couponsWithoutFriesAndDrink)
        couponsWithFriesAndDrink = sortCouponsByPrice(couponsWithFriesAndDrink)
        # Merge them together again.
        coupons = couponsWithoutFriesAndDrink + couponsWithFriesAndDrink
    elif sortMode == CouponSortModes.PRICE:
        coupons = sortCouponsByPrice(coupons)
    elif sortMode == CouponSortModes.PRICE_DESCENDING:
        coupons = sortCouponsByPrice(coupons, descending=True)
    elif sortMode == CouponSortModes.DISCOUNT:
        coupons = sortCouponsByDiscount(coupons)
    elif sortMode == CouponSortModes.DISCOUNT_DESCENDING:
        coupons = sortCouponsByDiscount(coupons, descending=True)
    elif sortMode == CouponSortModes.NEW:
        coupons = sortCouponsByNew(coupons)
    elif sortMode == CouponSortModes.NEW_DESCENDING:
        coupons = sortCouponsByNew(coupons, descending=True)
    else:
        # This should never happen
        logging.warning("Developer mistake!! Unknown sortMode: " + str(sortMode))
    return coupons
