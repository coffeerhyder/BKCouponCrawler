import os
import random
import re
from datetime import datetime, timedelta
from re import Pattern
from typing import Union

import pytz
import simplejson as json
from PIL import Image


class DATABASES:
    """ Names of all databases used in this project. """
    INFO_DB = 'info_db'
    COUPONS = 'coupons'
    COUPONS_HISTORY = 'coupons_history'
    COUPONS_HISTORY_SIMPLE = 'coupons_history_simple'
    OFFERS = 'offers'
    PRODUCTS = 'products'
    PRODUCTS_HISTORY = 'products_history'
    PRODUCTS2_HISTORY = 'products2_history'
    TELEGRAM_USERS = 'telegram_users'
    TELEGRAM_CHANNEL = 'telegram_channel'


class HISTORYDB:
    COUPONS_HISTORY_DOC = 'history'


class URLs:
    PROTOCOL_BK = 'https://www.'
    ELEMENT = 'https://app.element.io/#/room/#BetterKingDE:matrix.org'
    BK_SPAR_KINGS = 'burgerking.de/sparkings'
    BK_KING_FINDER = 'burgerking.de/store-locator'
    BK_KING_DEALS = 'burgerking.de/kingdeals'
    NO_PROTOCOL_COUPONS = 'burgerking.de/rewards/offers'


def loadJson(path: str):
    with open(os.path.join(os.getcwd(), path), encoding='utf-8') as infile:
        loadedJson = json.load(infile, use_decimal=True)
    return loadedJson


def saveJson(path: str, data: Union[list, dict]):
    with open(path, 'w') as f:
        json.dump(data, f, indent=4, sort_keys=True)


def couponOrOfferGetImageURL(data: dict) -> str:
    """ Only for new API objects (coupons and offers)! Chooses lowest resolution to save traffic (Some URLs have a fixed resolution. In this case we cannot change it.) """
    image_url = data['image_url']
    """ 2020-12-25: Hardcoded lowest resolution. We assume that this is always available if a resolution has to be chosen.
        We can usually chose the resolution for coupon pictures but only sometimes for offer pictures. """
    image_url = setImageURLQuality(image_url)
    return image_url


def setImageURLQuality(image_url: str) -> str:
    return image_url.replace('%{resolution}', '320')


def normalizeString(string: str):
    """ Returns lowercase String with all non-word characters removed. """
    return re.sub(r'[\W_]+', '', string).lower()


def splitStringInPairs(string: str) -> str:
    """ Changes input to pairs of max. 4 separated by spaces. """
    addedCharsBlock = 0
    index = 0
    splitString = ''
    for char in string:
        isLast = index == len(string) - 1
        splitString += char
        index += 1
        addedCharsBlock += 1
        if addedCharsBlock == 4 and not isLast:
            splitString += ' '
            addedCharsBlock = 0
    return splitString


def shortenProductNames(couponTitle: str) -> str:
    """ Cleans up coupon titles to make them shorter so they hopefully fit in the length of one button.
     E.g. "Long Chicken + Crispy Chicken + mittlere KING Pommes + 0,4 L Coca-Cola" -> "LngChn+CrispyCkn+M🍟+0,4LCola"
     """
    """ Let's start with fixing the fries -> Using an emoji as replacement really shortens product titles with fries! """
    couponTitle = sanitizeCouponTitle(couponTitle)
    pommesReplacement = SYMBOLS.FRIES
    colaReplacement = "🥤"
    couponTitle = re.sub(r"kleine(\s*KING)?\s*Pommes", r"S" + pommesReplacement, couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"mittlere(\s*KING)?\s*Pommes", r"M" + pommesReplacement, couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"große(\s*KING)?\s*Pommes", r"L" + pommesReplacement, couponTitle, flags=re.IGNORECASE)
    """ Just in case we missed one fries-case... """
    couponTitle = re.sub(r"KING\s*(Pommes)", pommesReplacement, couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Coca[\s-]*Cola", colaReplacement, couponTitle, flags=re.IGNORECASE)
    """ E.g. "Big KING" --> "Big K" """
    couponTitle = re.sub(r"(Big|Bacon|Fish|Halloumi)\s*KING", r"\1", couponTitle, flags=re.IGNORECASE)
    """ E.g. "KING Shake" --> "Shake" """
    couponTitle = re.sub(r"KING\s*(Jr\.?\s*Meal|Jr\.?\s*Menü|Shake|Nuggets?|Wings?)", r"\1", couponTitle, flags=re.IGNORECASE)
    """ 'Meta' replaces """
    # Normalize- and fix drink unit e.g. "0,3 L" or "0.3l" to "0.3" (remove unit character to save even more space)
    couponTitle = re.sub(r"(0[.,]\d{1,2})\s*L", r"\1", couponTitle, flags=re.IGNORECASE)
    # Normalize 'nugget unit e.g. "6er KING Nuggets" -> "6 KING Nuggets"
    couponTitle = re.sub(r"(\d{1,2})er\s*", r"\1", couponTitle, flags=re.IGNORECASE)
    # E.g. "2x Crispy Chicken" --> 2 Crispy Chicken
    couponTitle = re.sub(r"((\d+)[Xx] )([A-Za-z]+)", r"\2 \3", couponTitle, flags=re.IGNORECASE)
    # "Chicken Nuggets" -> "Nuggets"
    couponTitle = re.sub(r"Chicken\s*(Nuggets)", r"\1", couponTitle, flags=re.IGNORECASE)
    # Cheeseburger -> Cheesebrgr
    couponTitle = re.sub(r"(b)urger", r"\1rgr", couponTitle, flags=re.IGNORECASE)

    # Assume that all users know that "Cheddar" is cheese so let's remove this double entry
    couponTitle = re.sub(r"Cheddar\s*Cheese", r"Cheddar", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Chicken", r"Ckn", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Chili[\s-]*Cheese", r"CC", couponTitle, flags=re.IGNORECASE)
    # couponTitle = re.sub(r"Coca[\s-]*Cola", r"Cola", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Deluxe", r"Dlx", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Dips", r"Dip", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Double", r"Dbl", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Long", r"Lng", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Nuggets?", r"Nug", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Plant[\s-]*Based", r"Plnt", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Tripp?le", r"Trple", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Veggie", r"Veg", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Whopper", r"Wppr", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Steakhouse", r"SteakH", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"X[\s-]*tra", r"Xtra", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Onion[\s-]*Rings", r"Rings", couponTitle, flags=re.IGNORECASE)
    # Remove 'oder'
    couponTitle = re.sub(r"\s*oder\s*", r"", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"\s*zum\s*Preis\s*von\s*(1!?|einem|einer)", r"", couponTitle, flags=re.IGNORECASE)
    # Remove e.g. "Im KING Menü (+ 50 Cent)"
    couponTitle = re.sub(r"Im King Menü \(\+[^)]+\)", r"", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r" mit ", r"&", couponTitle, flags=re.IGNORECASE)
    couponTitle = re.sub(r"Jr\s*\.", r"Jr", couponTitle, flags=re.IGNORECASE)
    # Do some more basic replacements
    couponTitle = couponTitle.replace(' ', '')
    # E.g. "...Chili-Cheese"
    couponTitle = couponTitle.replace('-', '')
    # couponTitle = couponTitle.replace(' + ', '+')
    return couponTitle


def sanitizeCouponTitle(couponTitle: str) -> str:
    """ Generic method which sanitizes strings and removes unneeded symbols such as trademark symbols. """
    couponTitle = couponTitle.replace('®', '')
    couponTitle = couponTitle.strip()
    return couponTitle


def getPathImagesOffers() -> str:
    """ Returns path to directory containing all offer images. """
    return 'crawler/images/offers'


def getPathImagesProducts() -> str:
    """ Returns path to directory containing all product images. """
    return 'crawler/images/products'


def convertCouponAndOfferDateToGermanFormat(date: str) -> str:
    """ 2020-12-22T09:10:13+01:00 --> 22.12.2020 10:13 Uhr """
    return formatDateGerman(getDatetimeFromString(date))


def formatDateGerman(date: Union[datetime, float]) -> str:
    """ Accepts timestamp as float or datetime instance.
    Returns date in format: 13.10.2020 21:36 Uhr """
    if isinstance(date, float) or isinstance(date, int):
        # We want datetime
        date = datetime.fromtimestamp(date, getTimezone())
    return date.strftime('%d.%m.%Y %H:%M Uhr')


def formatDateGermanHuman(date: Union[datetime, float, int]) -> str:
    """ Returns human readable string representation of given datetime or timestamp. """
    if date is None or isinstance(date, (int, float, complex)) and date <= 0:
        return 'Nie'
    else:
        return formatDateGerman(date)


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


class SYMBOLS:
    BACK = '⬅Zurück'
    MEAT = '🥩'
    BROCCOLI = '🥦'
    CONFIRM = '✅'
    DENY = '🚫'
    DENY2 = '❌'
    FLAG_UA = '🇺🇦'
    THUMBS_UP = '👍'
    THUMBS_DOWN = '👎'
    ARROW_RIGHT = '➡'
    ARROW_LEFT = '⬅'
    ARROW_UP_RIGHT = '↗'
    ARROW_DOWN = '⬇'
    ARROW_UP = '⬆'
    ARROWS_CLOCKWISE_VERTICAL = '🔃'
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
    PARK = '🅿️'
    CIRLCE_BLUE = '🔵'
    # SOON = '🔜'


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


def couponTitleContainsFriesAndDrink(title: str) -> bool:
    titleLower = title.lower()
    if '+' in titleLower and couponTitleContainsFries(titleLower) and couponTitleContainsDrink(titleLower):
        return True
    elif re.compile(r'.*king\s*jr\s*\.?\s*meal.*').search(titleLower):
        return True
    elif re.compile(r'.*king\s*jr\s*\.?\s*menü.*').search(titleLower):
        return True
    else:
        return False


def couponTitleContainsVeggieFood(title: str) -> bool:
    # Convert title to lowercase for more thoughtless string comparison
    if couponTitleContainsPlantBasedFood(title):
        # All plant based articles are veggie
        return True
    titleLower = title.lower()
    if 'veggie' in titleLower:
        return True
    elif 'fusion' in titleLower:
        # Ice cream
        return True
    elif couponTitleIsFries(titleLower):
        return True
    elif '+' not in titleLower and 'cheese nacho' in titleLower:
        # Cheese Nachos
        return True
    elif '+' not in titleLower and 'chili cheese nuggets' in titleLower:
        return True
    elif '+' not in titleLower and 'onion rings' in titleLower:
        return True
    elif '+' not in titleLower and 'shake' in titleLower:
        return True
    elif '+' not in titleLower and 'brownie' in titleLower:
        return True
    else:
        # Non veggie menus and all the stuff that this handling doesn't detect properly yet
        return False


def couponTitleContainsPlantBasedFood(title: str) -> bool:
    titleLower = title.lower()
    if 'plant' in titleLower:
        return True
    else:
        return False


def couponTitleContainsFries(title: str) -> bool:
    titleLower = title.lower()
    # 2021-04-13: Chili Cheese Fries are now treated the same way as normal fries are!
    if 'pommes' in titleLower:
        return True
    elif 'fries' in titleLower:
        return True
    elif 'wedges' in titleLower:
        return True
    else:
        return False


def couponTitleIsFries(title: str) -> bool:
    titleLower = title.lower()
    if '+' not in titleLower and couponTitleContainsFries(titleLower):
        return True
    else:
        return False


def couponTitleContainsDrink(title: str) -> bool:
    titleLower = title.lower()
    if 'cola' in titleLower or re.compile(r'red\s*bull').search(titleLower):
        return True
    else:
        return False


REGEX_PLU_WITH_AT_LEAST_ONE_LETTER = re.compile(r'(?i)^([A-Z]+)\d+[A-Z]?$')


def isCouponShortPLUWithAtLeastOneLetter(plu: str) -> bool:
    """ 2021-04-13: Examples of allowed shortPLUs: "X11", "X11B"
    2021-05-25: New e.g. "KDM2"
    """
    return plu is not None and REGEX_PLU_WITH_AT_LEAST_ONE_LETTER.search(plu) is not None


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
    return formatSeconds(seconds=secondsPassed)


def formatSeconds(seconds: float) -> str:
    return str(timedelta(seconds=seconds))


def isValidImageFile(path: str) -> bool:
    """ Checks if a valid image file exists under given filepath. """
    try:
        im = Image.open(path)
        im.verify()
        return True
    except:
        return False


# All CouponTypes which will be used in our bot (will be displayed in bot menu as categories)
class CouponType:
    UNKNOWN = -1
    APP = 0
    # APP_VALID_AFTER_DELETION = 1  # Deprecated!
    # APP_SAME_CHAR_AS_CURRENT_APP_COUPONS = 2 # Deprecated!
    PAPER = 3
    PAPER_UNSAFE = 4
    ONLINE_ONLY = 5
    ONLINE_ONLY_STORE_SPECIFIC = 6  # Placeholder - not used
    SPECIAL = 7
    PAYBACK = 8

# TODO: Remove this
BotAllowedCouponTypes = [CouponType.APP, CouponType.PAPER, CouponType.SPECIAL, CouponType.PAYBACK]


class Paths:
    configPath = 'config.json'
    paperCouponExtraDataPath = 'config_paper_coupons.json'
    extraCouponConfigPath = 'config_extra_coupons.json'


def formatPrice(price: float) -> str:
    return f'{(price / 100):2.2f}'.replace('.', ',') + '€'


TEXT_NOTIFICATION_DISABLE = "Du kannst diese Benachrichtigung in den Einstellungen deaktivieren."
