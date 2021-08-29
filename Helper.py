import os
import random
import re
from datetime import datetime, timedelta
from re import Pattern

import pytz
import simplejson as json
from PIL import Image

from BotUtils import BotProperty


class DATABASES:
    """ Names of all databases used in this project. """
    INFO_DB = 'info_db'
    COUPONS = 'coupons'
    COUPONS_HISTORY = 'coupons_history'
    COUPONS2_HISTORY = 'coupons2_history'
    OFFERS = 'offers'
    OFFERS_HISTORY = 'offers_history'
    PRODUCTS = 'products'
    PRODUCTS_HISTORY = 'products_history'
    PRODUCTS2_HISTORY = 'products2_history'
    TELEGRAM_USERS = 'telegram_users'
    TELEGRAM_CHANNEL = 'telegram_channel'


class INFO_DB:
    """ Names of keys inside different DBs. """
    DB_INFO_TIMESTAMP_LAST_CRAWL = 'timestamp_last_crawl'
    DB_INFO_channel_last_information_message_id = 'channel_last_information_message_id'
    DB_INFO_channel_last_coupon_type_overview_message_ids = 'channel_last_coupon_type_overview_message_ids_'
    DB_INFO_TIMESTAMP_LAST_TELEGRAM_CHANNEL_UPDATE = 'timestamp_last_telegram_channel_update'
    MESSAGE_IDS_TO_DELETE = 'message_ids_to_delete'


class HISTORYDB:
    COUPONS_HISTORY_DOC = 'history'


def loadConfig(fallback=None):
    try:
        return loadJson(BotProperty.configPath)
    except:
        print('Failed to load ' + BotProperty.configPath)
        return fallback


def loadJson(path):
    with open(os.path.join(os.getcwd(), path), encoding='utf-8') as infile:
        loadedJson = json.load(infile, use_decimal=True)
    return loadedJson


def couponOrOfferGetImageURL(data: dict) -> str:
    """ Only for new API objects (coupons and offers)! Chooses lowest resolution to save traffic (Some URLs have a fixed resolution. In this case we cannot change it.) """
    image_url = data['image_url']
    """ 2020-12-25: Hardcoded lowest resolution. We assume that this is always available if a resolution has to be chosen.
        We can usually chose the resolution for coupon pictures but only sometimes for offer pictures. """
    image_url = setImageURLQuality(image_url)
    return image_url


def setImageURLQuality(image_url: str) -> str:
    return image_url.replace('%{resolution}', '320')


def shortenProductNames(couponTitle: str) -> str:
    """ Cleans up coupon titles to make them shorter so they hopefully fit in the length of one button.
     E.g. "Long Chicken + Crispy Chicken + mittlere KING Pommes + 0,4 L Coca-Cola" -> "LngChn+CrispyCkn+M🍟+0,4LCola"
     """
    """ Let's start with fixing the fries -> Using an emoji as replacement really shortens product titles with fries! """
    couponTitle = sanitizeCouponTitle(couponTitle)
    pommesReplacement = SYMBOLS.FRIES
    # pommesReplacement = 'Pomm'
    couponTitle = replaceRegex(re.compile(r'(?i)kleine\s*KING\s*Pommes'), 'S ' + pommesReplacement, couponTitle)
    couponTitle = replaceRegex(re.compile(r'(?i)mittlere\s*KING\s*Pommes'), 'M ' + pommesReplacement, couponTitle)
    couponTitle = replaceRegex(re.compile(r'(?i)große\s*KING\s*Pommes'), 'L ' + pommesReplacement, couponTitle)
    """ Just in case we missed one case... """
    couponTitle = replaceRegex(re.compile(r'(?i)KING\s*Pommes'), pommesReplacement, couponTitle)
    """ E.g. "Big KING" --> "Big K" """
    regexKingAfterProductName = re.compile(r"(?i)(Big|Bacon|Fish|Halloumi)\s*KING").search(couponTitle)
    if regexKingAfterProductName:
        couponTitle = couponTitle.replace(regexKingAfterProductName.group(0), regexKingAfterProductName.group(1) + " K")
    """ E.g. "KING Shake" --> "Shake" """
    regexKingInFrontOfProductTitle = re.compile(r"(?i)KING\s*(Jr\.?\\s*Meal|Shake|Nuggets?|Wings?)").search(couponTitle)
    if regexKingInFrontOfProductTitle:
        couponTitle = couponTitle.replace(regexKingInFrontOfProductTitle.group(0), regexKingInFrontOfProductTitle.group(1))
    """ 'Meta' replaces """
    # Normalize- and fix drink unit e.g. "0,3 L" or "0.3l" to "0.3" (leave out the unit character to save even more space)
    drinkUnitRegEx = re.compile(r'(?i)(0[.,]\d{1,2})\s*L').search(couponTitle)
    if drinkUnitRegEx:
        couponTitle = couponTitle.replace(drinkUnitRegEx.group(0), drinkUnitRegEx.group(1))
    # Normalize 'nugget unit e.g. "6er KING Nuggets" -> "6 KING Nuggets"
    nuggetUnitRegEx = re.compile(r'(?i)(\d{1,2})er\s*?').search(couponTitle)
    if nuggetUnitRegEx:
        couponTitle = couponTitle.replace(nuggetUnitRegEx.group(0), nuggetUnitRegEx.group(1))
    # "Chicken Nuggets" -> "Nuggets" (because everyone knows what's ment by that and it's shorter!)
    chickenNuggetsFix = re.compile(r'(?i)Chicken\s*Nuggets').search(couponTitle)
    if chickenNuggetsFix:
        couponTitle = couponTitle.replace(chickenNuggetsFix.group(0), "Nuggets")
    burgerFix = re.compile(r'(?i)(b)urger').search(couponTitle)
    if burgerFix:
        # Keep first letter of "burger" as it is sometimes used as part of one word e.g. "Cheeseburger"
        b = burgerFix.group(1)
        couponTitle = replaceCaseInsensitive(burgerFix.group(0), b + 'rgr', couponTitle)

    # Assume that all users know that "Cheddar" is cheese so let's remove this double entry
    couponTitle = replaceRegex(re.compile(r'(?i)Cheddar\s*Cheese'), 'Cheddar', couponTitle)
    couponTitle = replaceCaseInsensitive('Chicken', 'Ckn', couponTitle)
    couponTitle = replaceRegex(re.compile(r'(?i)Chili\s*Cheese'), 'CC', couponTitle)
    couponTitle = replaceRegex(re.compile(r'(?i)Coca[\s-]*Cola'), 'Cola', couponTitle)
    couponTitle = replaceCaseInsensitive('Deluxe', 'Dlx', couponTitle)
    couponTitle = replaceCaseInsensitive('Dips', 'Dip', couponTitle)
    couponTitle = replaceCaseInsensitive('Double', 'Dbl', couponTitle)
    couponTitle = replaceCaseInsensitive('Long', 'Lng', couponTitle)
    couponTitle = replaceRegex(re.compile('(?i)Nuggets?'), 'Nugg', couponTitle)
    couponTitle = replaceRegex(re.compile(r'(?i)Plant[\s-]*Based'), 'Plant', couponTitle)
    couponTitle = replaceCaseInsensitive('Triple', 'Trple', couponTitle)
    couponTitle = replaceCaseInsensitive('Veggie', 'Veg', couponTitle)
    couponTitle = replaceCaseInsensitive('Whopper', 'Whppr', couponTitle)
    couponTitle = replaceCaseInsensitive('Steakhouse', 'SteakH', couponTitle)
    couponTitle = replaceRegex(re.compile(r'(?i)X[\s-]*tra'), 'Xtra', couponTitle)

    # drinkUnitRegEx = re.compile('(?i)(0[.,]\\d{1,2})\\s*L').search(couponTitle)
    # if drinkUnitRegEx:
    #     couponTitle = couponTitle.replace(drinkUnitRegEx.group(0), drinkUnitRegEx.group(1) + " L")
    # couponTitle = replaceRegex(re.compile('(?i)(0[.,]\\d{1,2})\\s*L'), '0,4 L', couponTitle)
    # couponTitle = replaceRegex(re.compile('(?i)0[.,]4\\s*L'), '0,4 L', couponTitle)
    # couponTitle = replaceRegex(re.compile('(?i)0[.,]5\\s*L'), '0,5 L', couponTitle)
    couponTitle = replaceRegex(re.compile(r'(?i)Jr\s*\.'), 'Jr', couponTitle)
    """ Uahh removing all spaces makes it more ugly but we need to save that space! """
    couponTitle = couponTitle.replace(' ', '')
    # E.g. "...Chili-Cheese"
    couponTitle = couponTitle.replace('-', '')
    # couponTitle = couponTitle.replace(' + ', '+')
    return couponTitle


def sanitizeCouponTitle(title: str) -> str:
    """ Generic method which sanitizes strings and removes unneeded symbols such as trademark symbols. """
    return title.replace('®', '').strip()


def getPathImagesOffers() -> str:
    """ Returns path to directory containing all offer images. """
    return 'crawler/images/offers'


def getPathImagesProducts() -> str:
    """ Returns path to directory containing all product images. """
    return 'crawler/images/products'


def convertCouponAndOfferDateToGermanFormat(date: str) -> str:
    """ 2020-12-22T09:10:13+01:00 --> 22.12.2020 10:13 Uhr """
    return formatDateGerman(getDatetimeFromString(date))


def formatDateGerman(date: datetime) -> str:
    """ Returns date in format: 13.10.2020 21:36 Uhr """
    return date.strftime('%d.%m.%Y %H:%M Uhr')


def getDatetimeFromString(dateStr: str) -> datetime:
    """ Parses e.g.: "2020-12-22T09:10:13+01:00" """
    return datetime.strptime(dateStr, '%Y-%m-%dT%H:%M:%S%z')


def getDatetimeFromString2(dateStr: str) -> datetime:
    """ Parses e.g. "10.01.2021 23:59+01:00" """
    return datetime.strptime(dateStr, '%d.%m.%Y %H:%M%z')


def getCurrentDate() -> datetime:
    return datetime.now(getTimezone())


def getTimezone() -> pytz:
    return pytz.timezone('Europe/Berlin')


def getCurrentDateIsoFormat() -> str:
    """ Returns current date in format yyyy-MM-dd """
    return getCurrentDate().isoformat()


def replaceCaseInsensitive(old: str, repl: str, text: str) -> str:
    """ THX: https://stackoverflow.com/a/15831118 """
    return re.sub('(?i)' + re.escape(old), lambda m: repl, text)


def replaceRegex(old: Pattern, repl: str, text: str) -> str:
    return re.sub(old, lambda m: repl, text)


class SYMBOLS:
    BACK = '⬅Zurück'
    CONFIRM = '✅'
    DENY = '🚫'
    DENY2 = '❌'
    THUMBS_UP = '👍'
    THUMBS_DOWN = '👎'
    ARROW_RIGHT = '➡'
    ARROW_LEFT = '⬅'
    ARROW_UP_RIGHT = '↗'
    ARROW_DOWN = '⬇'
    STAR = '⭐'
    HEART = '❤'
    BEER = '🍺'
    BEERS = '🍻'
    CORONA = '😷'
    FRIES = '🍟'
    INFORMATION = 'ℹ'
    WRENCH = '🔧'
    WARNING = '⚠'
    NEWSPAPER = '📰'
    PLUS = '➕'
    WHITE_DOWN_POINTING_BACKHAND = '👇'
    NEW = '🆕'
    GHOST = '👻'
    GIFT = '🎁'


def getFilenameFromURL(url: str) -> str:
    filenameRegex = re.compile(r'(?i)^http.*[/=]([\w-]+\.(jpe?g|png))').search(url)
    if filenameRegex:
        filenameURL = filenameRegex.group(1)
    else:
        # Fallback / old handling
        filenameURL = url.split('/')[-1]
        # Remove URL parameters if existant
        if '?' in filenameURL:
            filenameURL = filenameURL[:filenameURL.rindex('?')]
    return filenameURL


def couponTitleContainsFriesOrCoke(title: str) -> bool:
    # title to lowercase for more thoughtless string comparison
    title = title.lower()
    if re.compile(r'(?i).*king\s*jr\s*\.?\s*meal.*').search(title):
        return True
    elif '+' in title and (('pommes' in title or 'fries' in title) and 'cola' in title):  # 2021-04-13: Chili Cheese Fries are now treated the same way as normal fries are!
        return True
    else:
        return False


def isCouponShortPLU(plu: str) -> bool:
    """ 2021-04-13: Examples of allowed shortPLUs: "X11", "X11B"
    2021-05-25: New e.g. "KDM2"
    """
    return plu is not None and re.compile('(?i)^[A-Z]+\\d+[A-Z]?$').search(plu) is not None


def generateFeedbackCode() -> str:
    """ Credits for that go to: https://edik.ch/posts/hack-the-burger-king.html """
    currentMonth = datetime.now().month
    if currentMonth == 1:
        res = 'BB'
    elif currentMonth == 2:
        res = 'LS'
    elif currentMonth == 3:
        res = 'JH'
    elif currentMonth == 4:
        res = 'PL'
    elif currentMonth == 5:
        res = 'BK'
    elif currentMonth == 6:
        res = 'WH'
    elif currentMonth == 7:
        res = 'FF'
    elif currentMonth == 8:
        res = 'BF'
    elif currentMonth == 9:
        res = 'CF'
    elif currentMonth == 10:
        res = 'CK'
    elif currentMonth == 11:
        res = 'CB'
    else:
        res = 'VM'
    randomNumberList = random.sample(range(0, 9), 6)
    string_ints = [str(integer) for integer in randomNumberList]
    return res + ''.join(string_ints)


def getFormattedPassedTime(pastTimestamp: float) -> str:
    """ Returns human readable duration until given future timestamp is reached """
    # https://stackoverflow.com/questions/538666/format-timedelta-to-string
    secondsPassed = datetime.now().timestamp() - pastTimestamp
    # duration = datetime.utcfromtimestamp(secondsPassed)
    # return duration.strftime("%Hh:%Mm")
    return str(timedelta(seconds=secondsPassed))


def isValidImageFile(path: str) -> bool:
    """ Checks if a valid image file exists under given filepath. """
    try:
        im = Image.open(path)
        im.verify()
        return True
    except:
        return False


USER_SETTINGS_ON_OFF = {
    # TODO: Obtain these Keys and default values from "User" Mapping class!
    "notifyWhenFavoritesAreBack": {
        "description": "Favoriten Benachrichtigungen",
        "default": False
    },
    "notifyWhenNewCouponsAreAvailable": {
        "description": "Benachrichtigung bei neuen Coupons",
        "default": False
    },
    "displayQR": {
        "description": "QR Codes zeigen",
        "default": False
    },
    # "displayHiddenAppCoupons": { # Deprecated
    #     "description": "Versteckte App Coupons zeigen**",
    #     "default": True
    # },
    "displayHiddenAppCouponsWithinGenericCategories": {
        "description": "Versteckte App Coupons in Kategorien zeigen**",
        "default": False
    }
}
