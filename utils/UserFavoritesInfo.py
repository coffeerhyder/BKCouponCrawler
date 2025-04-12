from typing import Union, List

from models.Coupon import Coupon


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
        unavailableFavoritesText = ''
        for coupon in self.couponsUnavailable:
            if len(unavailableFavoritesText) > 0:
                unavailableFavoritesText += '\n'
            unavailableFavoritesText += coupon.id + ' | ' + coupon.getTitleShortened(includeVeggieSymbol=False)
            priceInfoText = coupon.getPriceInfoText()
            if priceInfoText is not None:
                unavailableFavoritesText += ' | ' + priceInfoText
        return unavailableFavoritesText
