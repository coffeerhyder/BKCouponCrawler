from typing import Union, List

from utils.Filters import CouponFilter
from Helper import CouponType, SYMBOLS


class CouponView:

    def getFilter(self) -> CouponFilter:
        return self.couponfilter

    def __init__(self, couponfilter: CouponFilter, includeVeggieSymbol: Union[bool, None] = None, highlightFavorites: Union[bool, None] = None,
                 allowModifyFilter: bool = True, title: str = None):
        self.title = title
        self.couponfilter = couponfilter
        self.includeVeggieSymbol = includeVeggieSymbol
        self.highlightFavorites = highlightFavorites
        self.allowModifyFilter = allowModifyFilter

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


def getAllSortModes() -> list:
    # Important! The order of this will also determine the sort order which gets presented to the user!
    res = []
    for obj in CouponSortModes.__dict__.values():
        if isinstance(obj, CouponSortMode):
            res.append(obj)
    return res


class CouponSortMode:

    def __init__(self, text: str, isDescending: bool = False):
        self.text = text
        self.isDescending = isDescending

    def getSortCode(self) -> Union[int, None]:
        """ Returns position of current sort mode in array of all sort modes. """
        try:
            return getAllSortModes().index(self)
        except ValueError:
            return None  # Sollte eigentlich nicht vorkommen


def getNextSortMode(currentSortMode: CouponSortMode) -> CouponSortMode:
    allSortModes = getAllSortModes()
    if currentSortMode is None:
        return allSortModes[0]
    for index in range(len(allSortModes)):
        sortMode = allSortModes[index]
        if sortMode == currentSortMode:
            if index == (len(allSortModes) - 1):
                # Last sortMode in list --> Return first
                return allSortModes[0]
            else:
                # Return next sortMode
                return allSortModes[index + 1]
    # Fallback, should not be needed
    return currentSortMode


def getSortModeBySortCode(sortCode: int) -> CouponSortMode:
    allSortModes = getAllSortModes()
    if sortCode < len(allSortModes):
        return allSortModes[sortCode]
    else:
        # Fallback
        return allSortModes[0]


class CouponSortModes:
    PRICE = CouponSortMode("Preis " + SYMBOLS.ARROW_UP)
    PRICE_DESCENDING = CouponSortMode("Preis " + SYMBOLS.ARROW_DOWN, isDescending=True)
    DISCOUNT = CouponSortMode("Rabatt " + SYMBOLS.ARROW_UP)
    DISCOUNT_DESCENDING = CouponSortMode("Rabatt " + SYMBOLS.ARROW_DOWN, isDescending=True)
    NEW = CouponSortMode("Neue Coupons " + SYMBOLS.ARROW_UP)
    NEW_DESCENDING = CouponSortMode("Neue Coupons " + SYMBOLS.ARROW_DOWN, isDescending=True)
    MENU_PRICE = CouponSortMode("Menü_Preis")
    TYPE_MENU_PRICE = CouponSortMode("Typ_Menü_Preis")


class CouponViews:
    ALL = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.MENU_PRICE.getSortCode(), isEatable=True), title="Alle Coupons")
    ALL_WITHOUT_MENU = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.PRICE.getSortCode(), containsFriesAndCoke=False),
                                  title="Alle Coupons ohne Menü")
    ALL_WITH_MENU = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.PRICE.getSortCode(), containsFriesAndCoke=True), title="Alle Coupons mit Menü")
    CATEGORY = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.MENU_PRICE.getSortCode(), removeDuplicates=False))
    CATEGORY_WITHOUT_MENU = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.MENU_PRICE.getSortCode(), containsFriesAndCoke=False, removeDuplicates=False))
    HIDDEN_APP_COUPONS_ONLY = CouponView(
        couponfilter=CouponFilter(sortCode=CouponSortModes.PRICE.getSortCode(), allowedCouponTypes=[CouponType.APP], isHidden=True, removeDuplicates=False),
        title="App Coupons versteckte")
    VEGGIE = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.PRICE.getSortCode(), isVeggie=True, isEatable=True), includeVeggieSymbol=False,
                        title=f"{SYMBOLS.BROCCOLI}Veggie Coupons{SYMBOLS.BROCCOLI}")
    MEAT_ONLY = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.PRICE.getSortCode(), isMeat=True),
                           title="Fleischige Coupons")
    KING_DES_MONATS = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.PRICE.getSortCode(), isKingDesMonats=True),
                                 title="King des Monats Coupons")
    # Dummy item basically only used for holding default sortCode for users' favorites
    FAVORITES = CouponView(couponfilter=CouponFilter(sortCode=CouponSortModes.PRICE.getSortCode(), removeDuplicates=False), highlightFavorites=False, allowModifyFilter=False,
                           title=f"{SYMBOLS.STAR}Favoriten{SYMBOLS.STAR}")


def getAllCouponViews() -> List[CouponView]:
    res = []
    for obj in CouponViews.__dict__.values():
        if isinstance(obj, CouponView):
            res.append(obj)
    return res


def getCouponViewByIndex(index: int) -> Union[CouponView, None]:
    allCouponViews = getAllCouponViews()
    if index < len(allCouponViews):
        return allCouponViews[index]
    else:
        # Fallback
        return allCouponViews[0]
