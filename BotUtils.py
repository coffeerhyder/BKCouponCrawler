from telegram import InlineKeyboardMarkup

VERSION = '1.5.7'


def getBotImpressum() -> str:
    text = "BKBot v." + VERSION
    text += "\n<i>Made with ❤ and 🍻 during 😷"
    text += "\nKontakt: bkfeedback@pm.me</i>"
    return text


class BotProperty:
    configPath = 'config.json'
    paperCouponExtraDataPath = 'config_paper_coupons.json'
    extraCouponConfigPath = 'config_extra_coupons.json'


class Config:
    BOT_TOKEN = 'bot_token'
    DB_URL = 'db_url'
    PUBLIC_CHANNEL_NAME = 'public_channel_name'
    BOT_NAME = 'bot_name'


class CallbackVars:
    MENU_MAIN = 'menu_main'
    MENU_DISPLAY_ALL_COUPONS_LIST_WITH_FULL_TITLES = 'menu_display_all_coupons_list_with_full_titles'
    MENU_DISPLAY_COUPON = 'menu_display_coupon'
    MENU_COUPONS_WITH_IMAGES = 'menu_coupons_with_images'
    MENU_COUPONS_FAVORITES_WITH_IMAGES = 'menu_coupon_favorites_with_images'
    MENU_OFFERS = 'menu_offers'
    FAV_COUPON = 'fav_coupon'
    COUPON_LOOSE_WITH_FAVORITE_SETTING = 'coupon_loose_with_favorite_setting'
    MENU_FEEDBACK_CODES = 'menu_feedback_codes'
    MENU_SETTINGS = 'menu_settings'
    MENU_SETTINGS_TOGGLE_NOTIFICATIONS_FAVORITES_COUPONS = 'menu_settings_toggle_notifications_favorites_coupons'
    MENU_SETTINGS_TOGGLE_DISPLAY_QR_CODE = 'menu_settings_toggle_display_qr_code'
    MENU_SETTINGS_RESET = 'menu_settings_reset'
    MENU_SETTINGS_DELETE_UNAVAILABLE_FAVORITE_COUPONS = 'menu_settings_delete_unavailable_favorite_coupons'
    MENU_SETTINGS_USER_DELETE_DATA_COMMAND = 'menu_settings_user_delete_data_command'
    MENU_SETTINGS_USER_DELETE_DATA = 'menu_settings_user_delete_data'
    MENU_SETTINGS_USER_DELETE_DATA_DONE = 'menu_settings_user_delete_data_done'
    EASTER_EGG = 'easter_egg'


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
