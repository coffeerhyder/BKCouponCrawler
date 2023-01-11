import json
from typing import Optional, List

import pydantic
from telegram import InlineKeyboardMarkup

from Helper import SYMBOLS

VERSION = '1.9.6'

""" Place static stuff into this class. """


def getBotImpressum() -> str:
    # 2022-04-26: Add some love for Ukraine (RE stupid war RU vs UA 2022)
    text = f"BetterKing Bot v.{VERSION} | {SYMBOLS.FLAG_UA}{SYMBOLS.HEART}"
    text += f"\n<i>Made with {SYMBOLS.HEART} and {SYMBOLS.BEER} during {SYMBOLS.CORONA}"
    text += "\nKontakt: bkfeedback@pm.me</i>"
    return text


class CallbackVars:
    GENERIC_BACK = 'back'
    GENERIC_CANCEL = 'cancel'
    MENU_MAIN = 'menu_main'
    MENU_DISPLAY_ALL_COUPONS_LIST_WITH_FULL_TITLES = 'menu_display_all_coupons_list_with_full_titles'
    MENU_DISPLAY_COUPON = 'menu_display_coupon'
    MENU_COUPONS_WITH_IMAGES = 'menu_coupons_with_images'
    MENU_COUPONS_FAVORITES_WITH_IMAGES = 'menu_coupon_favorites_with_images'
    MENU_OFFERS = 'menu_offers'
    MENU_DISPLAY_PAYBACK_CARD = 'menu_display_payback_card'
    FAV_COUPON = 'fav_coupon'
    COUPON_LOOSE_WITH_FAVORITE_SETTING = 'coupon_loose_with_favorite_setting'
    MENU_FEEDBACK_CODES = 'menu_feedback_codes'
    MENU_SETTINGS = 'menu_settings'
    MENU_SETTINGS_RESET = 'menu_settings_reset'
    MENU_SETTINGS_ADD_PAYBACK_CARD = 'menu_settings_add_payback_card'
    MENU_SETTINGS_DELETE_PAYBACK_CARD = 'menu_settings_delete_payback_card'
    MENU_SETTINGS_DELETE_UNAVAILABLE_FAVORITE_COUPONS = 'menu_settings_delete_unavailable_favorite_coupons'
    MENU_SETTINGS_USER_DELETE_ACCOUNT = 'menu_settings_user_delete_account'
    EASTER_EGG = 'easter_egg'


class Commands:
    """ Contains commands that are programmatically used at multiple places to keep the strings at one place. """
    DELETE_ACCOUNT = 'tschau'
    MAINTENANCE = 'maintenance'


class PATTERN:
    PLU = r'^plu,(\d{2,})$'
    PLU_TOGGLE_FAV = r'^plu,(\d{2,}),togglefav,([^,]+)$'


class BetterBotException(Exception):
    def __init__(self, errorMsg, replyMarkup=None):
        self.errorMsg = errorMsg
        self.replyMarkup = replyMarkup

    def getErrorMsg(self):
        return self.errorMsg

    def getReplyMarkup(self) -> InlineKeyboardMarkup:
        return self.replyMarkup


def getImageBasePath() -> str:
    return "crawler/images/couponsproductive"


class Config(pydantic.BaseModel):

    bot_token: str
    bot_name: str
    db_url: str
    admin_ids: Optional[List]
    public_channel_name: Optional[str]


def loadConfig() -> Config:
    with open('config.json', encoding='utf-8') as infile:
        jsondict = json.load(infile)
        return Config(**jsondict)