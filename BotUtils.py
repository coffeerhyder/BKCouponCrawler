import json
from datetime import datetime

from telegram import InlineKeyboardMarkup

from Helper import SYMBOLS
from utils.Config import Config

VERSION = '2.3.6'

""" Place static stuff into this class. """


def getBotImpressum() -> str:
    # 2022-04-26: Add some love for Ukraine (RE stupid war RU vs UA 2022)
    text = f"BetterKing Bot v.{VERSION} | est. 2020 | {SYMBOLS.FLAG_UA}{SYMBOLS.HEART}"
    text += f"\n<i>Made with {SYMBOLS.HEART} and {SYMBOLS.BEER}"
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
    MENU_DONATE = 'menu_donate'
    MENU_SETTINGS = 'menu_settings'
    MENU_SETTINGS_SORTS_RESET = 'menu_settings_sorts_reset'
    MENU_SETTINGS_RESET = 'menu_settings_reset'
    MENU_SETTINGS_ADD_PAYBACK_CARD = 'menu_settings_add_payback_card'
    MENU_SETTINGS_DELETE_PAYBACK_CARD = 'menu_settings_delete_payback_card'
    MENU_SETTINGS_DELETE_UNAVAILABLE_FAVORITE_COUPONS = 'menu_settings_delete_unavailable_favorite_coupons'
    MENU_SETTINGS_USER_DELETE_ACCOUNT = 'menu_settings_user_delete_account'
    EASTER_EGG = 'easter_egg'
    ADMIN_RESEND_COUPONS = 'admin_resend_coupons'
    ADMIN_NUKE_CHANNEL = 'admin_nuke_channel'
    ADMIN_SEND_MSG_TO_ALL_USERS = 'admin_send_msg_to_all_users'


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


def loadConfig() -> Config:
    with open('config.json', encoding='utf-8') as infile:
        jsondict = json.load(infile)
        return Config(**jsondict)


class ImageCache:
    def __init__(self, fileID: str):
        self.imageFileID = fileID
        self.dateCreated = datetime.now()
        self.dateLastUsed = datetime.now()

    def updateLastUsedDate(self):
        """ Updates last used timestamp to current timestamp. """
        self.dateLastUsed = datetime.now()
