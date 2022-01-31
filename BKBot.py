import math
import sys
import time
import traceback
from typing import List, Tuple

import schedule
from couchdb import Database
from furl import furl, urllib
from telegram import Update, InlineKeyboardButton, InputMediaPhoto, Message, ReplyMarkup
from telegram.error import RetryAfter, BadRequest
from telegram.ext import Updater, CommandHandler, CallbackContext, ConversationHandler, CallbackQueryHandler, MessageHandler, Filters, Handler
from telegram.utils.helpers import DEFAULT_NONE
from telegram.utils.types import ODVInput, FileInput

from BotNotificator import updatePublicChannel, notifyUsersAboutNewCoupons, ChannelUpdateMode, nukeChannel, cleanupChannel
from BotUtils import *
import logging

from Helper import *
from Crawler import BKCrawler

from UtilsCouponsDB import Coupon, User, ChannelCoupon, CouponSortMode, getFormattedPrice, InfoEntry, getCouponsSeparatedByType, CouponFilter, UserFavoritesInfo
from CouponCategory import CouponCategory, BotAllowedCouponSources, CouponSource
from UtilsOffers import offerGetImagePath

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
# Enable this to show BETA setting to users --> Only enable this if there are beta features available
DISPLAY_BETA_SETTING = True

""" This is a helper for basic user on/off settings """
USER_SETTINGS_ON_OFF = {
    # TODO: Obtain these Keys and default values from "User" Mapping class and remove this mess!
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
    "displayHiddenAppCouponsWithinGenericCategories": {
        "description": "Versteckte App Coupons in Kategorien zeigen*¹",
        "default": False
    },
    "displayCouponCategoryPayback": {
        "description": "Payback Coupons/Karte im Hauptmenü zeigen",
        "default": True
    },
    "highlightFavoriteCouponsInButtonTexts": {
        "description": "Favoriten in Buttons mit " + SYMBOLS.STAR + " markieren",
        "default": True
    },
    "highlightNewCouponsInCouponButtonTexts": {
        "description": "Neue Coupons in Buttons mit " + SYMBOLS.NEW + " markieren",
        "default": True
    },
    "autoDeleteExpiredFavorites": {
        "description": "Abgelaufene Favoriten automatisch löschen",
        "default": False
    }
}
if DISPLAY_BETA_SETTING:
    USER_SETTINGS_ON_OFF["enableBetaFeatures"] = {
        "description": "Beta Features aktivieren",
        "default": False
    }


class CouponDisplayMode:
    ALL = "a"
    ALL_WITHOUT_MENU = 'a2'
    CATEGORY = 'c'
    CATEGORY_WITHOUT_MENU = 'c2'
    HIDDEN_APP_COUPONS_ONLY = 'h'
    FAVORITES = 'f'


class CouponCallbackVars:
    ALL_COUPONS = "?a=dcs&m=" + CouponDisplayMode.ALL + "&cs="
    ALL_COUPONS_WITHOUT_MENU = "?a=dcs&m=" + CouponDisplayMode.ALL_WITHOUT_MENU + "&cs="
    FAVORITES = "?a=dcs&m=" + CouponDisplayMode.FAVORITES + "&cs="


def generateCallbackRegEx(settings: dict):
    # Generates one CallBack RegEx for a set of settings.
    settingsCallbackRegEx = '^'
    index = 0
    for settingsKey in settings:
        isLastSetting = index == len(settings) - 1
        settingsCallbackRegEx += settingsKey
        if not isLastSetting:
            settingsCallbackRegEx += '|'
        index += 1
    settingsCallbackRegEx += '$'
    return settingsCallbackRegEx


def cleanupCache(cacheDict: dict):
    cacheDictCopy = cacheDict.copy()
    maxCacheAgeSeconds = 7 * 24 * 60 * 60
    for cacheID, cacheData in cacheDictCopy.items():
        cacheItemAge = datetime.now().timestamp() - cacheData.timestampLastUsed
        if cacheItemAge > maxCacheAgeSeconds:
            logging.info("Deleting cache item " + str(cacheID) + " as it was last used before: " + str(cacheItemAge) + " seconds")
            del cacheDict[cacheID]


class BKBot:

    def __init__(self):
        self.couponImageCache = {}
        self.couponImageQRCache = {}
        self.offerImageCache = {}
        self.maintenanceMode = False
        if 'maintenancemode' in sys.argv:
            self.maintenanceMode = True
        self.cfg = loadConfig()
        if self.cfg is None:
            raise Exception('Broken or missing config')
        self.crawler = BKCrawler()
        self.crawler.setExportCSVs(False)
        self.publicChannelName = self.cfg.get(Config.PUBLIC_CHANNEL_NAME)
        self.botName = self.cfg[Config.BOT_NAME]
        self.couchdb = self.crawler.couchdb
        self.updater = Updater(self.cfg[Config.BOT_TOKEN], request_kwargs={"read_timeout": 30})
        dispatcher = self.updater.dispatcher

        # Main conversation handler - handles nearly all bot menus.
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.botDisplayMenuMain)],
            states={
                CallbackVars.MENU_MAIN: [
                    # Main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),  # E.g. "back" button on error -> Go back to main menu
                    CallbackQueryHandler(self.botDisplayAllCouponsListWithFullTitles, pattern='^' + CallbackVars.MENU_DISPLAY_ALL_COUPONS_LIST_WITH_FULL_TITLES + '$'),
                    CallbackQueryHandler(self.botDisplayCouponsFromBotMenu, pattern='.*a=dcs.*'),
                    CallbackQueryHandler(self.botDisplayCouponsWithImagesFavorites, pattern='^' + CallbackVars.MENU_COUPONS_FAVORITES_WITH_IMAGES + '$'),
                    CallbackQueryHandler(self.botDisplayOffers, pattern='^' + CallbackVars.MENU_OFFERS + '$'),
                    CallbackQueryHandler(self.botDisplayFeedbackCodes, pattern='^' + CallbackVars.MENU_FEEDBACK_CODES + '$'),
                    CallbackQueryHandler(self.botAddPaybackCard, pattern="^" + CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD + "$"),
                    CallbackQueryHandler(self.botDisplayPaybackCard, pattern='^' + CallbackVars.MENU_DISPLAY_PAYBACK_CARD + '$'),
                    CallbackQueryHandler(self.botDisplayMenuSettings, pattern='^' + CallbackVars.MENU_SETTINGS + '$'),
                    CommandHandler('favoriten', self.botDisplayFavoritesCOMMAND),
                    CommandHandler('coupons', self.botDisplayAllCouponsCOMMAND),
                    CommandHandler('coupons2', self.botDisplayAllCouponsWithoutMenuCOMMAND),
                    CommandHandler('angebote', self.botDisplayOffers),
                    CommandHandler('payback', self.botDisplayPaybackCard),
                    CommandHandler('einstellungen', self.botDisplayMenuSettings)
                ],
                CallbackVars.MENU_OFFERS: [
                    CallbackQueryHandler(self.botDisplayCouponsFromBotMenu, pattern='.*a=dcs.*'),
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                ],
                CallbackVars.MENU_FEEDBACK_CODES: [
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                ],
                CallbackVars.MENU_DISPLAY_COUPON: [
                    # Back to last coupons menu
                    CallbackQueryHandler(self.botDisplayCouponsFromBotMenu, pattern='.*a=dcs.*'),
                    # Display single coupon
                    CallbackQueryHandler(self.botDisplaySingleCoupon, pattern='.*a=dc.*'),
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                    CallbackQueryHandler(self.botDisplayEasterEgg, pattern='^' + CallbackVars.EASTER_EGG + '$'),
                ],
                CallbackVars.MENU_DISPLAY_PAYBACK_CARD: [
                    # Back to last coupons menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.GENERIC_BACK + '$'),
                    CallbackQueryHandler(self.botAddPaybackCard, pattern="^" + CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD + "$")
                ],
                CallbackVars.MENU_SETTINGS: [
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                    CallbackQueryHandler(self.botDisplaySettingsToggleSetting, pattern=generateCallbackRegEx(User().settings)),
                    CallbackQueryHandler(self.botResetSettings, pattern="^" + CallbackVars.MENU_SETTINGS_RESET + "$"),
                    CallbackQueryHandler(self.botDeleteUnavailableFavoriteCoupons, pattern="^" + CallbackVars.MENU_SETTINGS_DELETE_UNAVAILABLE_FAVORITE_COUPONS + "$"),
                    CallbackQueryHandler(self.botAddPaybackCard, pattern="^" + CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD + "$"),
                    CallbackQueryHandler(self.botDeletePaybackCard, pattern="^" + CallbackVars.MENU_SETTINGS_DELETE_PAYBACK_CARD + "$"),
                ],
                CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD: [
                    # Back to settings menu
                    CallbackQueryHandler(self.botDisplayMenuSettings, pattern='^' + CallbackVars.GENERIC_BACK + '$'),
                    MessageHandler(filters=Filters.text and (~Filters.command), callback=self.botAddPaybackCard),
                ],
                CallbackVars.MENU_SETTINGS_DELETE_PAYBACK_CARD: [
                    # Back to settings menu
                    CallbackQueryHandler(self.botDisplayMenuSettings, pattern='^' + CallbackVars.GENERIC_BACK + '$'),
                    MessageHandler(Filters.text, self.botDeletePaybackCard),
                ],
            },
            fallbacks=[CommandHandler('start', self.botDisplayMenuMain)],
            name="MainConversationHandler",
        )
        """ Handles deletion of userdata. """
        conv_handler2 = ConversationHandler(
            entry_points=[CommandHandler('tschau', self.botUserDeleteAccountSTART),
                          CallbackQueryHandler(self.botUserDeleteAccount, pattern="^" + CallbackVars.MENU_SETTINGS_USER_DELETE_ACCOUNT + "$")],
            states={
                CallbackVars.MENU_SETTINGS_USER_DELETE_ACCOUNT: [
                    # Back to settings menu
                    CallbackQueryHandler(self.botDisplayMenuSettings, pattern='^' + CallbackVars.GENERIC_BACK + '$'),
                    # Delete users account
                    MessageHandler(filters=Filters.text and (~Filters.command), callback=self.botUserDeleteAccount),
                ],

            },
            fallbacks=[CommandHandler('start', self.botDisplayMenuMain)],
            name="DeleteUserConvHandler",
            allow_reentry=True,
        )
        """ Handles 'favorite buttons' below single coupon-pictures. """
        conv_handler3 = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.botCouponToggleFavorite, pattern=PATTERN.PLU_TOGGLE_FAV)],
            states={
                CallbackVars.COUPON_LOOSE_WITH_FAVORITE_SETTING: [
                    CallbackQueryHandler(self.botCouponToggleFavorite, pattern=PATTERN.PLU_TOGGLE_FAV),
                ],

            },
            fallbacks=[CommandHandler('start', self.botDisplayMenuMain)],
            name="CouponToggleFavoriteWithImageHandler",
        )
        if self.maintenanceMode:
            # Re-route all callbacks to maintenance mode function
            for convHandler in [conv_handler, conv_handler2, conv_handler3]:
                # Collect all handlers
                all_handlers: List[Handler] = []
                all_handlers.extend(convHandler.entry_points)
                all_handlers.extend(convHandler.fallbacks)
                for handlers in convHandler.states.values():
                    all_handlers.extend(handlers)
                for handler in all_handlers:
                    handler.callback = self.botDisplayMaintenanceMode
        dispatcher.add_handler(conv_handler)
        dispatcher.add_handler(conv_handler2)
        dispatcher.add_handler(conv_handler3)
        """
        2021-01-12: I've decided to drop these commands for now as our menu "back" button won't work like this.
        It would need a lot of refactoring to make the menus and commands work at the same time!
        """
        dispatcher.add_handler(CommandHandler('favoriten', self.botDisplayFavoritesCOMMAND))
        dispatcher.add_handler(CommandHandler('coupons', self.botDisplayAllCouponsCOMMAND))
        dispatcher.add_handler(CommandHandler('coupons2', self.botDisplayAllCouponsWithoutMenuCOMMAND))
        dispatcher.add_handler(CommandHandler('angebote', self.botDisplayOffers))
        dispatcher.add_handler(CommandHandler('einstellungen', self.botDisplayMenuSettings))
        dispatcher.add_error_handler(self.botErrorCallback)
        # dispatcher.add_handler(MessageHandler(Filters.command, self.botUnknownCommand))

    def botErrorCallback(self, update: Update, context: CallbackContext):
        try:
            raise context.error
        except BetterBotException as botError:
            errorText = botError.getErrorMsg()
            try:
                self.sendMessage(chat_id=update.effective_user.id, text=errorText, reply_markup=botError.getReplyMarkup(), parse_mode="HTML")
            except:
                logging.warning('Exception during exception handling -> Raising initial Exception')
                raise botError

    def handleBotErrorGently(self, update: Update, context: CallbackContext, botError: BetterBotException):
        """ Can handle BetterBotExceptions -> Answers user with the previously hopefully meaningful messages defined in BetterBotException.getErrorMsg(). """
        self.editOrSendMessage(update, text=botError.getErrorMsg(), parse_mode="HTML", reply_markup=botError.getReplyMarkup())

    def getPublicChannelName(self, fallback=None) -> Union[str, None]:
        """ Returns name of public channel which this bot is taking care of. """
        if self.publicChannelName is not None:
            return self.publicChannelName
        else:
            return fallback

    def getPublicChannelChatID(self) -> Union[str, None]:
        """ Returns public channel chatID like "@ChannelName". """
        if self.getPublicChannelName() is None:
            return None
        else:
            return '@' + self.getPublicChannelName()

    def getPublicChannelHyperlinkWithCustomizedText(self, linkText: str) -> str:
        """ Returns: e.g. <a href="https://t.me/channelName">linkText</a>
        Only call this if self.publicChannelName != None!!! """
        return "<a href=\"https://t.me/" + self.getPublicChannelName() + "\">" + linkText + "</a>"

    def botDisplayMaintenanceMode(self, update: Update, context: CallbackContext):
        text = SYMBOLS.DENY + '<b>Wartungsmodus!' + SYMBOLS.DENY + '</b>'
        if self.getPublicChannelName() is not None:
            text += '\nMehr Infos siehe ' + self.getPublicChannelHyperlinkWithCustomizedText('Channel') + '.'
        self.editOrSendMessage(update, text=text, parse_mode='HTML', disable_web_page_preview=True)

    def botDisplayMenuMain(self, update: Update, context: CallbackContext):
        userDB = self.crawler.getUsersDB()
        user = User.load(userDB, str(update.effective_user.id))
        """ New user? --> Add userID to DB. """
        if user is None:
            # Add user to DB for the first time
            user = User(id=str(update.effective_user.id))
            user.store(userDB)
        allButtons = []
        if self.getPublicChannelName() is not None:
            allButtons.append([InlineKeyboardButton('Alle Coupons Liste + Pics + News', url='https://t.me/' + self.getPublicChannelName())])
            allButtons.append([InlineKeyboardButton('Alle Coupons Liste lange Titel + Pics', callback_data=CallbackVars.MENU_DISPLAY_ALL_COUPONS_LIST_WITH_FULL_TITLES)])
        allButtons.append([InlineKeyboardButton('Alle Coupons', callback_data=CouponCallbackVars.ALL_COUPONS)])
        allButtons.append([InlineKeyboardButton('Alle Coupons ohne Menü', callback_data=CouponCallbackVars.ALL_COUPONS_WITHOUT_MENU)])
        for couponSrc in BotAllowedCouponSources:
            # Only add buttons for coupon categories for which at least one coupon is available
            couponCategory = self.crawler.cachedAvailableCouponCategories.get(couponSrc)
            if couponCategory is None:
                continue
            elif couponSrc == CouponSource.PAYBACK and not user.settings.displayCouponCategoryPayback:
                # Do not display this category if disabled by user
                continue
            allButtons.append([InlineKeyboardButton(CouponCategory(couponSrc).namePlural, callback_data="?a=dcs&m=" + CouponDisplayMode.CATEGORY + "&cs=" + str(couponSrc))])
            if couponCategory.numberofCouponsWithFriesOrCoke < couponCategory.numberofCouponsTotal and couponCategory.isEatable():
                allButtons.append([InlineKeyboardButton(CouponCategory(couponSrc).namePlural + ' ohne Menü',
                                                        callback_data="?a=dcs&m=" + CouponDisplayMode.CATEGORY_WITHOUT_MENU + "&cs=" + str(couponSrc))])
            if couponSrc == CouponSource.APP and couponCategory.numberofCouponsHidden > 0:
                allButtons.append([InlineKeyboardButton(CouponCategory(couponSrc).namePlural + ' versteckte',
                                                        callback_data="?a=dcs&m=" + CouponDisplayMode.HIDDEN_APP_COUPONS_ONLY + "&cs=" + str(couponSrc))])
        keyboardCouponsFavorites = [InlineKeyboardButton(SYMBOLS.STAR + 'Favoriten' + SYMBOLS.STAR, callback_data="?a=dcs&m=" + CouponDisplayMode.FAVORITES),
                                    InlineKeyboardButton(SYMBOLS.STAR + 'Favoriten + Pics' + SYMBOLS.STAR, callback_data=CallbackVars.MENU_COUPONS_FAVORITES_WITH_IMAGES)]
        allButtons.append(keyboardCouponsFavorites)
        if user.settings.displayCouponCategoryPayback:
            if user.getPrimaryPaybackCardNumber() is None:
                allButtons.append([InlineKeyboardButton(SYMBOLS.NEW + 'Payback Karte hinzufügen', callback_data=CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD)])
            else:
                allButtons.append([InlineKeyboardButton(SYMBOLS.PARK + 'ayback Karte', callback_data=CallbackVars.MENU_DISPLAY_PAYBACK_CARD)])
        allButtons.append(
            [InlineKeyboardButton('Angebote', callback_data=CallbackVars.MENU_OFFERS), InlineKeyboardButton('KING Finder', url='https://www.burgerking.de/kingfinder')])
        if user.settings.enableBetaFeatures:
            allButtons.append([InlineKeyboardButton('BETA: Feedback Code Generator', callback_data=CallbackVars.MENU_FEEDBACK_CODES)])
        allButtons.append([InlineKeyboardButton(SYMBOLS.WRENCH + 'Einstellungen', callback_data=CallbackVars.MENU_SETTINGS)])
        reply_markup = InlineKeyboardMarkup(allButtons)
        menuText = 'Hallo ' + update.effective_user.first_name + ', <b>Bock auf Fastfood?</b>'
        menuText += '\n' + getBotImpressum()
        if self.crawler.cachedMissingPaperCouponsText is not None:
            menuText += '\n<b>' + SYMBOLS.WARNING + 'Derzeit im Bot fehlende Papiercoupons: ' + bkbot.crawler.cachedMissingPaperCouponsText + '</b>'
        self.editOrSendMessage(update, text=menuText, reply_markup=reply_markup, parse_mode='HTML')
        return CallbackVars.MENU_MAIN

    def botDisplayAllCouponsListWithFullTitles(self, update: Update, context: CallbackContext):
        """ Send list containing all coupons with long titles linked to coupon channel to user. This may result in up to 10 messages being sent! """
        update.callback_query.answer()
        activeCoupons = bkbot.crawler.getFilteredCoupons(CouponFilter(activeOnly=True, allowedCouponSources=BotAllowedCouponSources, sortMode=CouponSortMode.SOURCE_MENU_PRICE))
        self.sendCouponOverviewWithChannelLinks(chat_id=update.effective_user.id, coupons=activeCoupons, useLongCouponTitles=True,
                                                channelDB=self.couchdb[DATABASES.TELEGRAM_CHANNEL], infoDB=None, infoDBDoc=None)
        # Delete last message containing menu as it is of no use for us anymore
        self.deleteMessage(chat_id=update.effective_user.id, messageID=update.callback_query.message.message_id)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]])
        menuText = "<b>Alle " + str(len(activeCoupons)) + " Coupons als Liste mit langen Titeln</b>"
        if self.getPublicChannelName() is not None:
            menuText += "\nAlle Verlinkungen führen in den " + self.getPublicChannelHyperlinkWithCustomizedText("Channel") + "."
        self.sendMessage(chat_id=update.effective_user.id, text=menuText, parse_mode="HTML", reply_markup=reply_markup, disable_web_page_preview=True)
        return CallbackVars.MENU_MAIN

    def getBotCoupons(self):
        """ Wrapper """
        return self.crawler.getBotCoupons()

    def botDisplayCouponsFromBotMenu(self, update: Update, context: CallbackContext):
        """ Wrapper """
        return self.displayCoupons(update, context, update.callback_query.data)

    def botDisplayAllCouponsCOMMAND(self, update: Update, context: CallbackContext):
        """ Wrapper and this is only to be used for commands. """
        return self.displayCoupons(update, context, CouponCallbackVars.ALL_COUPONS)

    def botDisplayAllCouponsWithoutMenuCOMMAND(self, update: Update, context: CallbackContext):
        """ Wrapper and this is only to be used for commands. """
        return self.displayCoupons(update, context, CouponCallbackVars.ALL_COUPONS_WITHOUT_MENU)

    def botDisplayFavoritesCOMMAND(self, update: Update, context: CallbackContext):
        """ Wrapper and this is only to be used for commands. """
        return self.displayCoupons(update, context, CouponCallbackVars.FAVORITES)

    def displayCoupons(self, update: Update, context: CallbackContext, callbackVar: str):
        """ Displays all coupons in a pre selected mode """
        # Important! This is required so that we can e.g. jump from "Category 'App coupons' page 2 display single coupon" back into "Category 'App coupons' page 2"
        callbackVar += "&cb=" + urllib.parse.quote(callbackVar)
        urlQuery = furl(callbackVar)
        urlinfo = urlQuery.args
        mode = urlinfo["m"]
        try:
            coupons = None
            menuText = None
            user = User.load(self.couchdb[DATABASES.TELEGRAM_USERS], str(update.effective_user.id))
            highlightFavorites = user.settings.highlightFavoriteCouponsInButtonTexts
            displayHiddenCouponsWithinOtherCategories = None if (
                    user.settings.displayHiddenAppCouponsWithinGenericCategories is True) else False  # None = Get all (hidden- and non-hidden coupons), False = Get non-hidden coupons
            if mode == CouponDisplayMode.ALL:
                # Display all coupons
                coupons = self.getFilteredCoupons(
                    CouponFilter(sortMode=CouponSortMode.MENU_PRICE, allowedCouponSources=None, containsFriesAndCoke=None, isHidden=displayHiddenCouponsWithinOtherCategories))
                menuText = '<b>' + str(len(coupons)) + ' Coupons verfügbar:</b>'
            elif mode == CouponDisplayMode.ALL_WITHOUT_MENU:
                # Display all coupons without menu
                coupons = self.getFilteredCoupons(
                    CouponFilter(sortMode=CouponSortMode.PRICE, allowedCouponSources=None, containsFriesAndCoke=False, isHidden=displayHiddenCouponsWithinOtherCategories))
                menuText = '<b>' + str(len(coupons)) + ' Coupons ohne Menü verfügbar:</b>'
            elif mode == CouponDisplayMode.CATEGORY:
                # Display all coupons of a particular category
                couponSrc = int(urlinfo['cs'])
                coupons = self.getFilteredCoupons(CouponFilter(sortMode=CouponSortMode.MENU_PRICE, allowedCouponSources=[couponSrc], containsFriesAndCoke=None,
                                                               isHidden=displayHiddenCouponsWithinOtherCategories))
                menuText = '<b>' + str(len(coupons)) + ' ' + CouponCategory(couponSrc).namePluralWithoutSymbol + ' verfügbar:</b>'
            elif mode == CouponDisplayMode.CATEGORY_WITHOUT_MENU:
                # Display all coupons of a particular category without menu
                couponSrc = int(urlinfo['cs'])
                coupons = self.getFilteredCoupons(
                    CouponFilter(sortMode=CouponSortMode.PRICE, allowedCouponSources=[couponSrc], containsFriesAndCoke=False, isHidden=displayHiddenCouponsWithinOtherCategories))
                menuText = '<b>' + str(len(coupons)) + ' ' + CouponCategory(couponSrc).namePluralWithoutSymbol + ' ohne Menü verfügbar:</b>'
            elif mode == CouponDisplayMode.HIDDEN_APP_COUPONS_ONLY:
                # Display all hidden App coupons (ONLY)
                couponSrc = int(urlinfo['cs'])
                coupons = self.getFilteredCoupons(CouponFilter(sortMode=CouponSortMode.PRICE, allowedCouponSources=[CouponSource.APP], containsFriesAndCoke=None, isHidden=True))
                menuText = '<b>' + str(len(coupons)) + ' versteckte ' + CouponCategory(couponSrc).namePluralWithoutSymbol + ' verfügbar:</b>'
            elif mode == CouponDisplayMode.FAVORITES:
                userFavorites, menuText = self.getUserFavoritesAndUserSpecificMenuText(user=user)
                coupons = userFavorites.couponsAvailable
                highlightFavorites = False
            self.displayCouponsAsButtons(update, user, coupons, menuText, urlQuery, highlightFavorites=highlightFavorites)
            return CallbackVars.MENU_DISPLAY_COUPON
        except BetterBotException as botError:
            self.handleBotErrorGently(update, context, botError)
            return CallbackVars.MENU_MAIN

    def getUserFavoritesAndUserSpecificMenuText(self, user: User, coupons: Union[dict, None] = None) -> Tuple[UserFavoritesInfo, str]:
        if len(user.favoriteCoupons) == 0:
            raise BetterBotException('<b>Du hast noch keine Favoriten!</b>', InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]]))
        else:
            if coupons is None:
                # Perform DB request if not already done before
                coupons = self.getBotCoupons()
            userFavoritesInfo = user.getUserFavoritesInfo(coupons)
            if len(userFavoritesInfo.couponsAvailable) == 0:
                # Edge case
                errorMessage = '<b>' + SYMBOLS.WARNING + 'Derzeit ist keiner deiner ' + str(len(user.favoriteCoupons)) + ' favorisierten Coupons verfügbar:</b>'
                errorMessage += '\n' + userFavoritesInfo.getUnavailableFavoritesText()
                if user.isAllowSendFavoritesNotification():
                    errorMessage += '\n' + SYMBOLS.CONFIRM + 'Du wirst benachrichtigt, sobald abgelaufene Coupons wieder verfügbar sind.'
                raise BetterBotException(errorMessage, InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]]))

            menuText = SYMBOLS.STAR
            if len(userFavoritesInfo.couponsUnavailable) == 0:
                menuText += str(len(userFavoritesInfo.couponsAvailable)) + ' Favoriten verfügbar' + SYMBOLS.STAR
            else:
                menuText += str(len(userFavoritesInfo.couponsAvailable)) + ' / ' + str(len(user.favoriteCoupons)) + ' Favoriten verfügbar' + SYMBOLS.STAR
            numberofEatableCouponsWithoutPrice = 0
            totalPrice = 0
            for coupon in userFavoritesInfo.couponsAvailable:
                if coupon.price is not None:
                    totalPrice += coupon.price
                elif coupon.isEatable():
                    numberofEatableCouponsWithoutPrice += 1
            if totalPrice > 0:
                menuText += "\n<b>Gesamtwert:</b> " + getFormattedPrice(totalPrice)
                if numberofEatableCouponsWithoutPrice > 0:
                    menuText += "*\n* exklusive " + str(numberofEatableCouponsWithoutPrice) + " Coupons, deren Preis nicht bekannt ist."
            if len(userFavoritesInfo.couponsUnavailable) > 0:
                menuText += '\n' + SYMBOLS.WARNING + str(len(userFavoritesInfo.couponsUnavailable)) + ' deiner Favoriten sind abgelaufen:'
                menuText += '\n' + userFavoritesInfo.getUnavailableFavoritesText()
                menuText += '\n' + SYMBOLS.INFORMATION + 'In den Einstellungen kannst du abgelaufene Favoriten löschen oder dich benachrichtigen lassen, sobald diese wieder verfügbar sind.'
            return userFavoritesInfo, menuText

    def displayCouponsAsButtons(self, update: Update, user: Union[User, None], coupons: list, menuText: str, urlquery, highlightFavorites: bool):
        if len(coupons) == 0:
            # This should never happen
            raise BetterBotException(SYMBOLS.DENY + ' <b>Ausnahmefehler: Es gibt derzeit keine Coupons!</b>',
                                     InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=urlquery.url)]]))
        query = update.callback_query
        if query is not None:
            query.answer()
        urlquery_callbackBack = furl(urlquery.args["cb"])
        buttons = []
        maxCouponsPerPage = 20
        paginationMax = math.ceil(len(coupons) / maxCouponsPerPage)
        desiredPage = int(urlquery.args.get("p", 1))
        if desiredPage > paginationMax:
            # Fallback - can happen if user leaves menu open for a long time, DB changes and user presses old "next/previous page" button
            desiredPage = paginationMax
        # Grab all items in desired range (= on desired page)
        index = (desiredPage * maxCouponsPerPage - maxCouponsPerPage)
        # Whenever the user has at least one favorite coupon on page > 1 we'll replace the dummy middle page overview button which usually does not do anything with Easter Egg functionality
        desiredPageContainsAtLeastOneFavoriteCoupon = False
        while len(buttons) < maxCouponsPerPage and index < len(coupons):
            coupon = coupons[index]
            if user.isFavoriteCoupon(coupon) and highlightFavorites:
                buttonText = SYMBOLS.STAR + coupon.generateCouponShortText(highlightIfNew=user.settings.highlightNewCouponsInCouponButtonTexts)
                desiredPageContainsAtLeastOneFavoriteCoupon = True
            else:
                buttonText = coupon.generateCouponShortText(highlightIfNew=user.settings.highlightNewCouponsInCouponButtonTexts)

            buttons.append([InlineKeyboardButton(buttonText, callback_data="?a=dc&plu=" + coupon.id + "&cb=" + urllib.parse.quote(urlquery_callbackBack.url))])
            index += 1
        if paginationMax > 1:
            # Add pagination navigation buttons if needed
            menuText += "\nSeite " + str(desiredPage) + " / " + str(paginationMax)
            navigationButtons = []
            if desiredPage > 1:
                # Add button to go to previous page
                lastPage = desiredPage - 1
                urlquery_callbackBack.args['p'] = lastPage
                navigationButtons.append(InlineKeyboardButton(SYMBOLS.ARROW_LEFT, callback_data=urlquery_callbackBack.url))
            else:
                # Add dummy button for a consistent button layout
                navigationButtons.append(InlineKeyboardButton(SYMBOLS.GHOST, callback_data="DummyButtonPrevPage"))
            navigationButtons.append(InlineKeyboardButton("Seite " + str(desiredPage) + " / " + str(paginationMax), callback_data="DummyButtonMiddle"))
            if desiredPage < paginationMax:
                # Add button to go to next page
                nextPage = desiredPage + 1
                urlquery_callbackBack.args['p'] = nextPage
                navigationButtons.append(InlineKeyboardButton(SYMBOLS.ARROW_RIGHT, callback_data=urlquery_callbackBack.url))
            else:
                # Add dummy button for a consistent button layout
                # Easter egg: Trigger it if there are at least two pages available AND user is currently on the last page AND that page contains at least one user-favorited coupon.
                if desiredPageContainsAtLeastOneFavoriteCoupon and desiredPage > 1:
                    navigationButtons.append(InlineKeyboardButton(SYMBOLS.GHOST, callback_data=CallbackVars.EASTER_EGG))
                else:
                    navigationButtons.append(InlineKeyboardButton(SYMBOLS.GHOST, callback_data="DummyButtonNextPage"))
            buttons.append(navigationButtons)
        buttons.append([InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)])
        reply_markup = InlineKeyboardMarkup(buttons)
        self.editOrSendMessage(update, text=menuText, reply_markup=reply_markup, parse_mode='HTML')
        return CallbackVars.MENU_DISPLAY_COUPON

    def botDisplayEasterEgg(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        text = "🥚<b>Glückwunsch! Du hast ein Easter Egg gefunden!</b>"
        text += "\nKlicke <a href=\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\">HIER</a>, um es anzusehen ;)"
        text += "\nDrücke /start, um das Menü neu zu laden."
        self.sendMessage(chat_id=update.effective_user.id, text=text, parse_mode="html", disable_web_page_preview=True)
        return CallbackVars.MENU_DISPLAY_COUPON

    def botDisplayCouponsWithImagesFavorites(self, update: Update, context: CallbackContext):
        try:
            userFavorites, favoritesInfoText = self.getUserFavoritesAndUserSpecificMenuText(user=User.load(self.crawler.getUsersDB(), str(update.effective_user.id)))
        except BetterBotException as botError:
            self.handleBotErrorGently(update, context, botError)
            return CallbackVars.MENU_DISPLAY_COUPON
        query = update.callback_query
        query.answer()
        self.displayCouponsWithImagesAndBackButton(update, context, userFavorites.couponsAvailable, topMsgText='<b>Alle Favoriten mit Bildern:</b>',
                                                   bottomMsgText=favoritesInfoText)
        # Delete last message containing bot menu
        context.bot.delete_message(chat_id=update.effective_message.chat_id, message_id=query.message.message_id)
        return CallbackVars.MENU_DISPLAY_COUPON

    def displayCouponsWithImagesAndBackButton(self, update: Update, context: CallbackContext, coupons: list, topMsgText: str, bottomMsgText: str = "Zurück zum Hauptmenü?"):
        self.displayCouponsWithImages(update, context, coupons, topMsgText)
        # Post back button
        update.effective_message.reply_text(text=bottomMsgText, parse_mode="HTML",
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)], []]))

    def displayCouponsWithImages(self, update: Update, context: CallbackContext, coupons: list, msgText: str):
        self.sendMessage(chat_id=update.effective_message.chat_id, text=msgText, parse_mode='HTML')
        index = 0
        user = User.load(self.crawler.getUsersDB(), str(update.effective_user.id))
        showCouponIndexText = False
        for coupon in coupons:
            if showCouponIndexText:
                additionalText = 'Coupon ' + str(index + 1) + ' / ' + str(len(coupons))
            else:
                additionalText = None
            self.displayCouponWithImage(update, context, coupon, user, additionalText)
            index += 1

    def botDisplayOffers(self, update: Update, context: CallbackContext):
        """
        Posts all current offers (= photos with captions) into current chat.
        """
        activeOffers = self.crawler.getOffersActive()
        if len(activeOffers) == 0:
            # BK should always have offers but let's check for this case anyways.
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]])
            menuText = SYMBOLS.WARNING + '<b>Es gibt derzeit keine Angebote!</b>'
            self.editOrSendMessage(update, text=menuText, reply_markup=reply_markup, parse_mode='HTML')
            return CallbackVars.MENU_MAIN
        prePhotosText = '<b>Es sind derzeit ' + str(len(activeOffers)) + ' Angebote verfügbar:</b>'
        self.editOrSendMessage(update, text=prePhotosText, parse_mode='HTML')
        for offer in activeOffers:
            offerText = offer['title']
            subtitle = offer.get('subline')
            if subtitle is not None and len(subtitle) > 0:
                offerText += subtitle
            startDateStr = offer.get('start_date')
            if startDateStr is not None:
                offerText += '\nGültig ab ' + convertCouponAndOfferDateToGermanFormat(startDateStr)
            expirationDateStr = offer.get('expiration_date')
            if expirationDateStr is not None:
                offerText += '\nGültig bis ' + convertCouponAndOfferDateToGermanFormat(expirationDateStr)
            # This is a bit f*cked up but should work - offerIDs are not really unique but we'll compare the URL too and if the current URL is not in our cache we'll have to re-upload that file!
            sentMessage = self.sendPhoto(chat_id=update.effective_message.chat_id, photo=self.getOfferImage(offer), caption=offerText)
            # Save Telegram fileID pointing to that image in our cache
            self.offerImageCache.setdefault(couponOrOfferGetImageURL(offer), ImageCache(fileID=sentMessage.photo[0].file_id))

        menuText = '<b>Nix dabei?</b>'
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN),
                                              InlineKeyboardButton(SYMBOLS.ARROW_RIGHT + " Zu den Gutscheinen", callback_data="?a=dcs&m=" + CouponDisplayMode.ALL + "&cs=")], []])
        update.effective_message.reply_text(menuText, parse_mode='HTML', reply_markup=reply_markup)
        return CallbackVars.MENU_OFFERS

    def botDisplayFeedbackCodes(self, update: Update, context: CallbackContext):
        """ 2021-07-15: New- and unfinished feature """
        numberOfFeedbackCodesToGenerate = 3
        text = SYMBOLS.WARNING + "<b>Achtung! BETA Feature und unklar, ob diese 'random' Codes so funktionieren!</b>" + SYMBOLS.WARNING
        text += "\n<b>Hier sind " + str(numberOfFeedbackCodesToGenerate) + " Feedback Codes für dich:</b>"
        for index in range(numberOfFeedbackCodesToGenerate):
            text += "\n" + generateFeedbackCode()
        text += "\nSchreibe einen Code deiner Wahl auf die Rückseine (d)eines BK Kassenbons, um den (gratis) Artikel zu erhalten."
        text += "\nFalls du keinen Kassenbon hast und kein Schamgefühl kennst, hier ein Trick:"
        text += "\nBestelle ein einzelnes Päckchen Mayo oder Ketchup für ~0,20€ ;)"
        text += "\nDie Konditionen der Feedback Codes variieren.\nAktuell gibt es: Gratis Eiswaffel oder Kaffee(klein) [Stand 14.04.2021]"
        text += "\nDanke an <a href=\"https://edik.ch/posts/hack-the-burger-king.html\">Edik</a>!"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]])
        self.editOrSendMessage(update, text=text, reply_markup=reply_markup, parse_mode='HTML', disable_web_page_preview=True)
        return CallbackVars.MENU_FEEDBACK_CODES

    def botDisplayMenuSettings(self, update: Update, context: CallbackContext):
        user = User.load(self.crawler.getUsersDB(), str(update.effective_user.id))
        return self.displaySettings(update, context, user)

    def displaySettings(self, update: Update, context: CallbackContext, user: User):
        keyboard = []
        # TODO: Make this nicer
        dummyUser = User()
        userWantsAutodeleteOfFavoriteCoupons = user.settings.autoDeleteExpiredFavorites
        for settingKey, setting in dummyUser["settings"].items():
            # All settings that are in 'USER_SETTINGS_ON_OFF' are simply on/off settings and will automatically be included in users' settings.
            if settingKey in USER_SETTINGS_ON_OFF:
                description = USER_SETTINGS_ON_OFF[settingKey]["description"]
                # Check for special cases where one setting depends of the state of another
                if settingKey == 'notifyWhenFavoritesAreBack' and userWantsAutodeleteOfFavoriteCoupons:
                    continue
                if user.settings.get(settingKey, dummyUser.settings[settingKey]):
                    # Add symbol to enabled settings button text so user can see which settings are currently enabled
                    keyboard.append(
                        [InlineKeyboardButton(SYMBOLS.CONFIRM + description, callback_data=settingKey)])
                else:
                    keyboard.append([InlineKeyboardButton(description, callback_data=settingKey)])
        if user.getPrimaryPaybackCardNumber() is None:
            keyboard.append([InlineKeyboardButton(SYMBOLS.NEW + 'Payback Karte hinzufügen', callback_data=CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD)])
        else:
            keyboard.append([InlineKeyboardButton(SYMBOLS.DENY + 'Payback Karte löschen', callback_data=CallbackVars.MENU_SETTINGS_DELETE_PAYBACK_CARD)])
        menuText = SYMBOLS.WRENCH + "<b>Einstellungen:</b>"
        menuText += "\nNicht alle Filialen nehmen alle Gutschein-Typen!\nPrüfe die Akzeptanz von App- bzw. Papiercoupons vorm Bestellen über den <a href=\"https://www.burgerking.de/kingfinder\">KINGFINDER</a>."
        menuText += "\n*¹ Versteckte Coupons sind meist überteuerte große Menüs."
        menuText += "\nWenn aktiviert, werden diese nicht nur über den extra Menüpunkt 'App Coupons versteckte' angezeigt sondern zusätzlich innerhalb der folgenden Kategorien: Alle Coupons, App Coupons"
        # Add 'reset settings' button (only if user has changed settings to non-default)
        if user.settings.__dict__ != dummyUser.settings.__dict__:
            keyboard.append([InlineKeyboardButton(SYMBOLS.WARNING + "Einstell. zurücksetzen (" + SYMBOLS.STAR + "bleiben)" + SYMBOLS.WARNING,
                                                  callback_data=CallbackVars.MENU_SETTINGS_RESET)])
        if len(user.favoriteCoupons) > 0:
            # Additional DB request required so let's only jump into this handling if the user has at least one favorite coupon.
            userFavoritesInfo = user.getUserFavoritesInfo(self.getBotCoupons())
            if len(userFavoritesInfo.couponsUnavailable) > 0:
                keyboard.append([InlineKeyboardButton(SYMBOLS.DENY + "Abgelaufene Favoriten löschen (" + str(len(userFavoritesInfo.couponsUnavailable)) + ")?*²",
                                                      callback_data=CallbackVars.MENU_SETTINGS_DELETE_UNAVAILABLE_FAVORITE_COUPONS)])
                menuText += "\n*²" + SYMBOLS.DENY + "Löschbare abgelaufene Favoriten:"
                menuText += "\n" + userFavoritesInfo.getUnavailableFavoritesText()
        keyboard.append([InlineKeyboardButton(SYMBOLS.DENY + "Meinen Account löschen",
                                              callback_data=CallbackVars.MENU_SETTINGS_USER_DELETE_ACCOUNT)])
        # Back button
        keyboard.append([InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)])
        self.editOrSendMessage(update=update, text=menuText, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
        return CallbackVars.MENU_SETTINGS

    def botDisplaySingleCoupon(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        callbackArgs = furl(query.data).args
        uniqueCouponID = callbackArgs['plu']
        callbackBack = callbackArgs['cb']
        coupon = Coupon.load(self.crawler.getCouponDB(), uniqueCouponID)
        user = User.load(self.crawler.getUsersDB(), str(update.effective_user.id))
        # Send coupon image in chat
        self.displayCouponWithImage(update, context, coupon, user)
        # Post user-menu into chat
        menuText = 'Coupon Details'
        if not user.settings.displayQR:
            menuText += '\n' + SYMBOLS.INFORMATION + 'Möchtest du QR-Codes angezeigt bekommen?\nSiehe Hauptmenü -> Einstellungen'
        self.sendMessage(chat_id=update.effective_message.chat_id, text=menuText, parse_mode='HTML',
                         reply_markup=InlineKeyboardMarkup([[], [InlineKeyboardButton(SYMBOLS.BACK, callback_data=callbackBack)]]))
        # Delete previous message containing menu buttons from chat as we don't need it anymore.
        context.bot.delete_message(chat_id=update.effective_message.chat_id, message_id=query.message.message_id)
        return CallbackVars.MENU_DISPLAY_COUPON

    def botUserDeleteAccountSTART(self, update: Update, context: CallbackContext):
        menuText = '<b>\"Dann geh\' doch zu Netto!\"</b>\nAntworte mit deiner Benutzer-ID <b>' + str(
            update.effective_user.id) + '</b>, um deine Benutzerdaten <b>endgültig</b> vom Server zu löschen.'
        # Only display back button if user triggered this in context of a bot menu
        if update.callback_query is not None:
            self.editOrSendMessage(update, text=menuText, parse_mode='HTML',
                                   reply_markup=InlineKeyboardMarkup([[], [InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK)]]))
        else:
            self.editOrSendMessage(update, text=menuText, parse_mode='HTML')
        return CallbackVars.MENU_SETTINGS_USER_DELETE_ACCOUNT

    def botUserDeleteAccount(self, update: Update, context: CallbackContext):
        """ Deletes users' account from DB. """
        userInput = None if update.message is None else update.message.text
        if userInput is None:
            self.botUserDeleteAccountSTART(update, context)
            return CallbackVars.MENU_SETTINGS_USER_DELETE_ACCOUNT
        elif userInput == str(update.effective_user.id):
            userDB = self.crawler.getUsersDB()
            # Delete user from DB
            del userDB[str(update.effective_user.id)]
            menuText = SYMBOLS.CONFIRM + 'Dein BetterKing Account wurde vernichtet!'
            menuText += '\nDu kannst diesen Chat nun löschen.'
            menuText += '\n<b>Viel Erfolg beim Abnehmen!</b>'
            menuText += '\nIn loving memory of <i>blauelagunepb</i> ' + SYMBOLS.HEART
            self.editOrSendMessage(update, text=menuText, parse_mode='HTML')
            return ConversationHandler.END
        else:
            menuText = SYMBOLS.DENY + '<b>Falsche Antwort!</b>'
            menuText += '\nHast du dich umentschieden?'
            menuText += '\nMit /start gelangst du zurück ins Hauptmenü.'
            self.editOrSendMessage(update, text=menuText, parse_mode='HTML')
            return CallbackVars.MENU_SETTINGS_USER_DELETE_ACCOUNT

    def displayCouponWithImage(self, update: Update, context: CallbackContext, coupon: Coupon, user: User, additionalText: Union[str, None] = None):
        """
        Sends new message with coupon information & photo (& optionally coupon QR code) + "Save/Delete favorite" button in chat.
        """
        favoriteKeyboard = self.getCouponFavoriteKeyboard(user.isFavoriteCoupon(coupon), coupon.id, CallbackVars.COUPON_LOOSE_WITH_FAVORITE_SETTING)
        replyMarkupWithoutBackButton = InlineKeyboardMarkup([favoriteKeyboard, []])
        couponText = coupon.generateCouponLongTextFormattedWithDescription(highlightIfNew=True)
        if additionalText is not None:
            couponText += '\n' + additionalText
        if user.settings.displayQR:
            # We need to send two images -> Send as album
            photoCoupon = InputMediaPhoto(media=self.getCouponImage(coupon), caption=couponText, parse_mode='HTML')
            photoQR = InputMediaPhoto(media=self.getCouponImageQR(coupon), caption=couponText, parse_mode='HTML')
            chatMessages = self.sendMediaGroup(chat_id=update.effective_message.chat_id, media=[photoCoupon, photoQR])
            msgCoupon = chatMessages[0]
            msgQR = chatMessages[1]
            self.sendMessage(chat_id=update.effective_message.chat_id, text=couponText, parse_mode='HTML', reply_markup=replyMarkupWithoutBackButton,
                             disable_web_page_preview=True)
            # Add to cache if not already present
            self.couponImageQRCache.setdefault(coupon.id, ImageCache(fileID=msgQR.photo[0].file_id))
        else:
            msgCoupon = self.sendPhoto(chat_id=update.effective_message.chat_id, photo=self.getCouponImage(coupon), caption=couponText, parse_mode='HTML',
                                       reply_markup=replyMarkupWithoutBackButton)
        # Add to cache if not already present
        self.couponImageCache.setdefault(coupon.getUniqueIdentifier(), ImageCache(fileID=msgCoupon.photo[0].file_id))
        return CallbackVars.COUPON_LOOSE_WITH_FAVORITE_SETTING

    def botCouponToggleFavorite(self, update: Update, context: CallbackContext):
        """ Toggles coupon favorite state and edits reply_markup accordingly so user gets to see the new state of this setting. """
        uniqueCouponID = re.search(PATTERN.PLU_TOGGLE_FAV, update.callback_query.data).group(1)
        query = update.callback_query
        userDB = self.crawler.getUsersDB()
        user = User.load(userDB, str(update.effective_user.id))
        query.answer()

        if uniqueCouponID in user.favoriteCoupons:
            # Delete coupon from favorites
            user.deleteFavoriteCouponID(uniqueCouponID)
            isFavorite = False
        else:
            # Add coupon to favorites
            user.addFavoriteCoupon(Coupon.load(self.crawler.getCouponDB(), uniqueCouponID))
            isFavorite = True
        # Update DB
        user.store(userDB)
        favoriteKeyboard = self.getCouponFavoriteKeyboard(isFavorite, uniqueCouponID, CallbackVars.COUPON_LOOSE_WITH_FAVORITE_SETTING)
        replyMarkupWithoutBackButton = InlineKeyboardMarkup([favoriteKeyboard, []])
        query.edit_message_reply_markup(reply_markup=replyMarkupWithoutBackButton)
        return CallbackVars.COUPON_LOOSE_WITH_FAVORITE_SETTING

    def getCouponFavoriteKeyboard(self, isFavorite: bool, uniqueCouponID: str, callbackBack: str) -> list:
        """
        Returns an InlineKeyboardButton button array containing a single favorite save/delete button depending on the current favorite state.
        """
        favoriteKeyboard = []
        if isFavorite:
            favoriteKeyboard.append(InlineKeyboardButton(SYMBOLS.DENY + ' Favorit entfernen', callback_data='plu,' + uniqueCouponID + ',togglefav,' + callbackBack))
        else:
            favoriteKeyboard.append(InlineKeyboardButton(SYMBOLS.STAR + ' Favorit speichern', callback_data='plu,' + uniqueCouponID + ',togglefav,' + callbackBack))
        return favoriteKeyboard

    def generateCouponShortTextWithHyperlinkToChannelPost(self, coupon: Coupon, messageID: int) -> str:
        """ Returns e.g. "Y15 | 2Whopper+M🍟+0,4Cola (https://t.me/betterkingpublic/1054) | 8,99€" """
        text = "<b>" + coupon.getPLUOrUniqueID() + "</b> | <a href=\"https://t.me/" + self.getPublicChannelName() + '/' + str(
            messageID) + "\">" + coupon.titleShortened + "</a>"
        priceFormatted = coupon.getPriceFormatted()
        if priceFormatted is not None:
            text += " | " + priceFormatted
        return text

    def getFilteredCoupons(self, couponFilter: CouponFilter):
        """  Wrapper for crawler.filterCouponsList with errorhandling when zero results are available. """
        coupons = self.crawler.getFilteredCouponsAsList(couponFilter)
        if len(coupons) == 0:
            menuText = SYMBOLS.DENY + ' <b>Es gibt derzeit keine Coupons in den von dir ausgewählten Kategorien und/oder in Kombination mit den eingestellten Filtern!</b>'
            # menuText += "\nZurück mit /start"
            raise BetterBotException(menuText, InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]]))
        else:
            return coupons

    def getCouponImage(self, coupon: Coupon):
        """ Returns either image URL or file or Telegram file_id of a given coupon. """
        cachedImageData = self.couponImageCache.get(coupon.getUniqueIdentifier())
        """ Re-use Telegram file-ID if possible: https://core.telegram.org/bots/api#message
        If the PLU has changed, we cannot just re-use the old ID because the images can contain that PLU code and the PLU code in our saved image can lead to a completely different product now!
        According to the Telegram FAQ, sich file_ids can be trusted to be persistent: https://core.telegram.org/bots/faq#can-i-count-on-file-ids-to-be-persistent """
        imagePath = coupon.getImagePath()
        if cachedImageData is not None:
            # Re-use cached image_id and update cache timestamp
            cachedImageData.updateLastUsedTimestamp()
            logging.debug("Returning coupon image file_id: " + cachedImageData.imageFileID)
            return cachedImageData.imageFileID
        elif isValidImageFile(imagePath):
            # Return image file
            logging.debug("Returning coupon image file in path: " + imagePath)
            return open(imagePath, mode='rb')
        else:
            # Return fallback image file -> Should usually not be required!
            logging.warning("Returning coupon fallback image for path: " + imagePath)
            return open("media/fallback_image_missing_coupon_image.jpeg", mode='rb')

    def getCouponImageQR(self, coupon: Coupon):
        """ Returns either image URL or file or Telegram file_id of a given coupon QR image. """
        cachedQRImageData = self.couponImageQRCache.get(coupon.id)
        # Re-use Telegram file-ID if possible: https://core.telegram.org/bots/api#message
        if cachedQRImageData is not None:
            # Return cached image_id and update cache timestamp
            cachedQRImageData.updateLastUsedTimestamp()
            logging.debug("Returning QR image file_id: " + cachedQRImageData.imageFileID)
            return cachedQRImageData.imageFileID
        else:
            # Return image
            logging.debug("Returning QR image file")
            return coupon.getImageQR()

    def getOfferImage(self, offer: dict):
        """ Returns either image URL or file or Telegram file_id of a given offer. """
        image_url = couponOrOfferGetImageURL(offer)
        cachedImageData = self.offerImageCache.get(image_url)
        if cachedImageData is not None:
            # Re-use cached image_id and update cache timestamp
            cachedImageData.updateLastUsedTimestamp()
            return cachedImageData.imageFileID
        if os.path.exists(offerGetImagePath(offer)):
            # Return image file
            return open(offerGetImagePath(offer), mode='rb')
        else:
            # Fallback -> Shouldn't be required!
            return open('media/fallback_image_missing_offer_image.jpeg', mode='rb')

    def botDisplaySettingsToggleSetting(self, update: Update, context: CallbackContext):
        """ Toggles pre-selected setting via settingKey. """
        update.callback_query.answer()
        settingKey = update.callback_query.data
        userDB = self.crawler.getUsersDB()
        dummyUser = User()
        user = User.load(userDB, str(update.effective_user.id))
        if user.settings.get(settingKey, dummyUser.settings[settingKey]):
            user.settings[settingKey] = False
        else:
            user.settings[settingKey] = True
        user.store(userDB)
        return self.displaySettings(update, context, user)

    def botResetSettings(self, update: Update, context: CallbackContext):
        """ Resets users' settings to default """
        userDB = self.crawler.getUsersDB()
        user = User.load(userDB, str(update.effective_user.id))
        dummyUser = User()
        user.settings = dummyUser.settings
        # Update DB
        user.store(userDB)
        # Reload settings menu
        return self.displaySettings(update, context, user)

    def botDeleteUnavailableFavoriteCoupons(self, update: Update, context: CallbackContext):
        """ Removes all user selected favorites which are unavailable/expired at this moment. """
        userDB = self.crawler.getUsersDB()
        user = User.load(userDB, str(update.effective_user.id))
        self.deleteUsersUnavailableFavorites(userDB, [user])
        return self.displaySettings(update, context, user)

    def botAddPaybackCard(self, update: Update, context: CallbackContext):
        userInput = None if update.message is None else update.message.text
        if userInput is not None and len(userInput) == 13:
            # Maybe user entered barcode instead of Payback number --> Correct input
            userInput = userInput[3:13]
        if userInput is None:
            text = 'Antworte mit deiner Payback Kartennummer, um diese hinzuzufügen.'
            text += '\nDeine Kartennummer wird ausschließlich gespeichert, um sie dir in diesem Chat als EAN13 Code zu zeigen.'
            text += '\nDu kannst deine Karte in den Einstellungen jederzeit und endgültig aus dem Bot löschen.'
            self.editOrSendMessage(update, text=text, parse_mode='HTML',
                                   reply_markup=InlineKeyboardMarkup([[], [InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK)]]))
            return CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD
        elif userInput.isdecimal() and len(userInput) == 10:
            userDB = self.crawler.getUsersDB()
            user = User.load(userDB, str(update.effective_user.id))
            user.addPaybackCard(paybackCardNumber=userInput)
            user.store(userDB)
            text = SYMBOLS.CONFIRM + 'Deine Payback Karte wurde erfolgreich eingetragen.'
            self.sendMessage(chat_id=update.effective_user.id, text=text)
            return self.displayPaybackCard(update=update, context=context, user=user)
        else:
            self.sendMessage(chat_id=update.effective_user.id, text=SYMBOLS.DENY + 'Ungültige Eingabe!', parse_mode='HTML',
                             reply_markup=InlineKeyboardMarkup([[], [InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK)]]))
            return CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD

    def botDeletePaybackCard(self, update: Update, context: CallbackContext):
        """ Deletes Payback card from users account if his answer is matching his Payback card number. """
        # Validate input
        userDB = self.crawler.getUsersDB()
        user = User.load(userDB, str(update.effective_user.id))
        userInput = None if update.message is None else update.message.text
        if userInput is None:
            self.editOrSendMessage(update, text='Antworte mit deiner Payback Kartennummer <b>' + user.getPrimaryPaybackCardNumber() + '</b>, um diese zu löschen.',
                                   parse_mode='HTML',
                                   reply_markup=InlineKeyboardMarkup([[], [InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK)]]))
        elif userInput == user.getPrimaryPaybackCardNumber():
            user.deletePrimaryPaybackCard()
            user.store(userDB)
            text = SYMBOLS.CONFIRM + 'Payback Karte ' + userInput + ' wurde erfolgreich gelöscht.'
            self.editOrSendMessage(update, text=text,
                                   parse_mode='HTML',
                                   reply_markup=InlineKeyboardMarkup([[], [InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK)]]))
        else:
            self.editOrSendMessage(update, text=SYMBOLS.DENY + 'Ungültige Eingabe!', parse_mode='HTML',
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK)]]))
        return CallbackVars.MENU_SETTINGS_DELETE_PAYBACK_CARD

    def botDisplayPaybackCard(self, update: Update, context: CallbackContext):
        user = self.getUser(userID=update.effective_user.id)
        return self.displayPaybackCard(update, context, user)

    def displayPaybackCard(self, update: Update, context: CallbackContext, user: User):
        # TODO: Make EAN13 Payback card image nicer
        if user.getPrimaryPaybackCardNumber() is None:
            text = SYMBOLS.WARNING + 'Du hast noch keine Payback Karte eingetragen!'
            self.editOrSendMessage(update, text=text, parse_mode='html', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK), InlineKeyboardButton('Karte hinzufügen', callback_data=CallbackVars.MENU_SETTINGS_ADD_PAYBACK_CARD)]]))
        else:
            text = 'Payback Kartennummer: <b>' + splitStringInPairs(user.getPrimaryPaybackCardNumber()) + '</b>'
            text += '\n<b>Tipp:</b> Pinne diese Nachricht an, um im Bot Chat noch einfacher auf deine Payback Karte zugreifen zu können.'
            replyMarkup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.GENERIC_BACK)]])
            self.sendPhoto(chat_id=update.effective_user.id, photo=user.getPrimaryPaybackCardImage(), caption=text, parse_mode='html', disable_notification=True,
                           reply_markup=replyMarkup)
        return CallbackVars.MENU_DISPLAY_PAYBACK_CARD

    def batchProcessAutoDeleteUsersUnavailableFavorites(self):
        """ Deletes expired favorite coupons of all users who enabled auto deletion of those. """
        userDB = self.crawler.getUsersDB()
        users = []
        for userIDStr in userDB:
            user = User.load(userDB, userIDStr)
            if user.settings.autoDeleteExpiredFavorites:
                users.append(user)
        self.deleteUsersUnavailableFavorites(userDB, users)

    def deleteUsersUnavailableFavorites(self, userDB: Database, users: list):
        """ Deletes expired favorite coupons of all users who enabled auto deletion of those. """
        coupons = self.getBotCoupons()
        dbUpdates = []
        for user in users:
            userUnavailableFavoriteCouponInfo = user.getUserFavoritesInfo(coupons)
            if len(userUnavailableFavoriteCouponInfo.couponsUnavailable) > 0:
                for unavailableCoupon in userUnavailableFavoriteCouponInfo.couponsUnavailable:
                    user.deleteFavoriteCouponID(unavailableCoupon.id)
                dbUpdates.append(user)
        if len(dbUpdates) > 0:
            logging.info('Deleting expired favorites of ' + str(len(dbUpdates)) + ' users')
            userDB.update(dbUpdates)

    def getNewCouponsTextWithChannelHyperlinks(self, couponsDict: dict, maxNewCouponsToLink: int) -> str:
        infoText = ''
        """ Add detailed information about added coupons. Limit the max. number of that so our information message doesn't get too big. """
        index = 0
        channelDB = self.couchdb[DATABASES.TELEGRAM_CHANNEL]
        for uniqueCouponID in couponsDict:
            coupon = couponsDict[uniqueCouponID]

            """ Generates e.g. "Y15 | 2Whopper+M🍟+0,4LCola | 8,99€"
            Returns the same with hyperlink if a chat_id is given for this coupon e.g.:
            "Y15 | 2Whopper+M🍟+0,4LCola (https://t.me/betterkingpublic/1054) | 8,99€"
            """
            if coupon.id in channelDB:
                channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
                messageID = channelCoupon.getMessageIDForChatHyperlink()
                if messageID is not None:
                    couponText = coupon.generateCouponShortTextFormattedWithHyperlinkToChannelPost(highlightIfNew=False, publicChannelName=self.getPublicChannelName(),
                                                                                                   messageID=messageID)
                else:
                    # This should never happen but we'll allow it to
                    logging.warning("Can't hyperlink coupon because no messageIDs available: " + coupon.id)
                    couponText = coupon.generateCouponShortTextFormatted(highlightIfNew=False)
            else:
                # This should never happen but we'll allow it to anyways
                logging.warning("Can't hyperlink coupon because it is not in channelDB: " + coupon.id)
                couponText = coupon.generateCouponShortTextFormatted(highlightIfNew=False)
            infoText += '\n' + couponText

            if index == maxNewCouponsToLink - 1:
                # We processed the max. number of allowed items!
                break
            else:
                index += 1
                continue
        if len(couponsDict) > maxNewCouponsToLink:
            numberOfNonHyperinkedItems = len(couponsDict) - maxNewCouponsToLink
            if numberOfNonHyperinkedItems == 1:
                infoText += '\n+ ' + str(numberOfNonHyperinkedItems) + ' weiterer'
            else:
                infoText += '\n+ ' + str(numberOfNonHyperinkedItems) + ' weitere'
        return infoText

    def batchProcess(self):
        """ Runs all processes which should only run once per day. """
        self.crawl()
        self.renewPublicChannel()
        self.batchProcessAutoDeleteUsersUnavailableFavorites()
        self.notifyUsers()
        self.cleanupPublicChannel()

    def batchProcessWithoutChannelUpdate(self):
        """ Runs all processes which should only run once per day:
         1. Crawler, 2. User notify favorites and user notify new coupons """
        self.crawl()
        self.batchProcessAutoDeleteUsersUnavailableFavorites()
        self.notifyUsers()

    def crawl(self):
        try:
            self.crawler.crawlAndProcessData()
        except:
            traceback.print_exc()
            logging.warning("Crawler failed")

    def notifyUsers(self):
        """ Notify users about expired favorite coupons that are back or new coupons depending on their settings. """
        try:
            notifyUsersAboutNewCoupons(self)
        except Exception:
            # This should never happen
            traceback.print_exc()
            logging.warning("Exception happened during user notify")

    def renewPublicChannel(self):
        """ Deletes all channel messages and re-sends them / updates channel with current content. """
        try:
            updatePublicChannel(self, updateMode=ChannelUpdateMode.RESEND_ALL)
        except Exception:
            traceback.print_exc()
            logging.warning("Renew of public channel failed")

    def resumePublicChannelUpdate(self):
        """ Resumes channel update. """
        try:
            updatePublicChannel(self, updateMode=ChannelUpdateMode.RESUME_CHANNEL_UPDATE)
        except Exception:
            traceback.print_exc()
            logging.warning("Resume of public channel update failed")

    def cleanupPublicChannel(self):
        try:
            cleanupChannel(self)
        except:
            traceback.print_exc()
            logging.warning("Cleanup channel failed")

    def startBot(self):
        self.updater.start_polling()
        # Don't call this blocking method!
        # self.updater.idle()

    def stopBot(self):
        self.updater.stop()

    def cleanupCaches(self):
        cleanupCache(self.couponImageCache)
        cleanupCache(self.couponImageQRCache)
        cleanupCache(self.offerImageCache)

    def sendCouponOverviewWithChannelLinks(self, chat_id: Union[int, str], coupons: dict, useLongCouponTitles: bool, channelDB: Database, infoDB: Union[None, Database],
                                           infoDBDoc: Union[None, InfoEntry]):
        """ Sends all given coupons to given chat_id separated by source and split into multiple messages as needed. """
        couponsSeparatedByType = getCouponsSeparatedByType(coupons)
        if infoDBDoc is not None:
            # Mark old coupon overview messageIDs for deletion
            oldCategoryMsgIDs = infoDBDoc.getAllCouponCategoryMessageIDs()
            if len(oldCategoryMsgIDs) > 0:
                logging.info("Saving coupon category messageIDs for deletion: " + str(oldCategoryMsgIDs))
                infoDBDoc.addMessageIDsToDelete(oldCategoryMsgIDs)
                infoDBDoc.deleteAllCouponCategoryMessageIDs()
                # Update DB
                infoDBDoc.store(infoDB)
        """ Re-send coupon overview(s), spread this information on multiple pages if needed. """
        for couponSourceIndex in range(len(BotAllowedCouponSources)):
            couponSource = BotAllowedCouponSources[couponSourceIndex]
            couponCategory = CouponCategory(couponSource)
            logging.info("Working on coupon overview " + str(couponSourceIndex + 1) + "/" + str(len(BotAllowedCouponSources)) + " | " + couponCategory.nameSingular)
            hasAddedSeparatorAfterCouponsWithoutMenu = False
            listContainsAtLeastOneItemWithoutMenu = False
            if couponSource in couponsSeparatedByType:
                coupons = couponsSeparatedByType[couponSource]
                # Depends on the max entities per post limit of Telegram and we're not only using hyperlinks but also the "<b>" tag so we do not have 50 hyperlinks left but 49.
                maxCouponsPerPage = 49
                maxPage = math.ceil(len(coupons) / maxCouponsPerPage)
                for page in range(1, maxPage + 1):
                    logging.info("Sending category page: " + str(page) + "/" + str(maxPage))
                    couponOverviewText = "<b>[" + str(len(coupons)) + " Stück] " + couponCategory.nameSingular + " Übersicht"
                    if couponCategory.displayDescription:
                        couponOverviewText += "\n" + couponCategory.description
                    if maxPage > 1:
                        couponOverviewText += " Teil " + str(page) + " / " + str(maxPage)
                    couponOverviewText += "</b>"
                    startIndex = page * maxCouponsPerPage - maxCouponsPerPage
                    for couponIndex in range(startIndex, startIndex + maxCouponsPerPage):
                        coupon = coupons[couponIndex]
                        """ Add a separator so it is easier for the user to distinguish between coupons with- and without menu. 
                        This only works as "simple" as that because we pre-sorted these coupons!
                        """
                        if not coupon.containsFriesOrCoke:
                            listContainsAtLeastOneItemWithoutMenu = True
                        elif not hasAddedSeparatorAfterCouponsWithoutMenu and listContainsAtLeastOneItemWithoutMenu:
                            couponOverviewText += '\n<b>' + SYMBOLS.WHITE_DOWN_POINTING_BACKHAND + couponCategory.namePluralWithoutSymbol + ' mit Menü' + SYMBOLS.WHITE_DOWN_POINTING_BACKHAND + '</b>'
                            hasAddedSeparatorAfterCouponsWithoutMenu = True
                        """ Generates e.g. "Y15 | 2Whopper+M🍟+0,4LCola | 8,99€"
                        Returns the same with hyperlink if a chat_id is given for this coupon e.g.:
                        "Y15 | 2Whopper+M🍟+0,4LCola (https://t.me/betterkingpublic/1054) | 8,99€"
                        """
                        if coupon.id in channelDB:
                            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
                            messageID = channelCoupon.getMessageIDForChatHyperlink()
                            if messageID is not None:
                                if useLongCouponTitles:
                                    couponText = coupon.generateCouponLongTextFormattedWithHyperlinkToChannelPost(self.getPublicChannelName(), messageID)
                                else:
                                    couponText = coupon.generateCouponShortTextFormattedWithHyperlinkToChannelPost(highlightIfNew=True,
                                                                                                                   publicChannelName=self.getPublicChannelName(),
                                                                                                                   messageID=messageID)
                            else:
                                # This should never happen but we'll allow it to
                                logging.warning("Can't hyperlink coupon because no messageIDs available: " + coupon.id)
                                if useLongCouponTitles:
                                    couponText = coupon.generateCouponLongTextFormatted()
                                else:
                                    couponText = coupon.generateCouponShortTextFormatted(highlightIfNew=True)
                        else:
                            # This should never happen but we'll allow it to
                            logging.warning("Can't hyperlink coupon because it is not in channelDB: " + coupon.id)
                            if useLongCouponTitles:
                                couponText = coupon.generateCouponLongTextFormatted()
                            else:
                                couponText = coupon.generateCouponShortTextFormatted(highlightIfNew=True)

                        couponOverviewText += '\n' + couponText
                        # Exit loop after last coupon info has been added
                        if couponIndex == len(coupons) - 1:
                            break
                    # Send new post containing current page
                    msg = self.sendMessage(chat_id=chat_id, text=couponOverviewText, parse_mode="HTML", disable_web_page_preview=True,
                                           disable_notification=True)
                    if infoDBDoc is not None:
                        # Update DB
                        infoDBDoc.addCouponCategoryMessageID(couponSource, msg.message_id)
                        infoDBDoc.lastMaintenanceModeState = self.maintenanceMode
                        infoDBDoc.store(infoDB)
            else:
                logging.info("Nothing to do: No coupons of this type available :)")

        return

    def deleteMessages(self, chat_id: Union[int, str], messageIDs: Union[List[int], None]):
        """ Deletes array of messageIDs. """
        if messageIDs is None:
            return
        index = 0
        for msgID in messageIDs:
            logging.info("Deleting message " + str(index + 1) + " / " + str(len(messageIDs)) + " | " + str(msgID))
            self.deleteMessage(chat_id=chat_id, messageID=msgID)
            index += 1

    def editOrSendMessage(self, update: Update, text: str, parse_mode: str = None, reply_markup: ReplyMarkup = None, disable_web_page_preview: bool = False,
                          disable_notification=False) -> Union[Message, bool]:
        """ Edits last message if possible. Sends new message otherwise.
         Usable for message with text-content only!
         Returns:
        :class:`telegram.Message`: On success, if edited message is sent by the bot, the
        edited Message is returned, otherwise :obj:`True` is returned.
        """
        query = update.callback_query
        if query is not None and query.message.text is not None:
            query.answer()
            return query.edit_message_text(text=text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)
        else:
            return self.sendMessage(chat_id=update.effective_user.id, text=text, parse_mode=parse_mode, reply_markup=reply_markup,
                                    disable_web_page_preview=disable_web_page_preview, disable_notification=disable_notification)

    def editMessage(self, chat_id: Union[int, str], message_id: Union[int, str], text: str, parse_mode: str = None, disable_web_page_preview: bool = False):
        self.updater.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)

    def sendMessage(self, chat_id: Union[int, str], text: Union[str, None] = None, parse_mode: Union[None, str] = None,
                    disable_notification: ODVInput[bool] = DEFAULT_NONE, disable_web_page_preview: Union[bool, None] = None,
                    reply_markup: ReplyMarkup = None
                    ) -> Message:
        """ Wrapper """
        return self.processMessage(chat_id=chat_id, text=text, parse_mode=parse_mode, disable_notification=disable_notification, disable_web_page_preview=disable_web_page_preview,
                                   reply_markup=reply_markup)

    def sendPhoto(self, chat_id: Union[int, str], photo: Union[FileInput, 'PhotoSize'], caption: Union[None, str] = None,
                  parse_mode: Union[None, str] = None, disable_notification: ODVInput[bool] = DEFAULT_NONE,
                  reply_markup: 'ReplyMarkup' = None) -> Message:
        """ Wrapper """
        return self.processMessage(chat_id=chat_id, photo=photo, caption=caption, parse_mode=parse_mode, disable_notification=disable_notification, reply_markup=reply_markup)

    def sendMediaGroup(self, chat_id: Union[int, str], media: List[
        Union['InputMediaAudio', 'InputMediaDocument', 'InputMediaPhoto', 'InputMediaVideo']
    ], disable_notification: ODVInput[bool] = DEFAULT_NONE) -> List[Message]:
        """ Wrapper """
        return self.processMessage(chat_id=chat_id, media=media, disable_notification=disable_notification)

    def processMessage(self, chat_id: Union[int, str], maxTries: int = 15, text: Union[str, None] = None, parse_mode: Union[None, str] = None,
                       disable_notification: ODVInput[bool] = DEFAULT_NONE, disable_web_page_preview: Union[bool, None] = None,
                       reply_markup: 'ReplyMarkup' = None,
                       media: Union[None, List[
                           Union['InputMediaAudio', 'InputMediaDocument', 'InputMediaPhoto', 'InputMediaVideo']
                       ]] = None,
                       photo: Union[None, FileInput, 'PhotoSize'] = None, caption: Union[None, str] = None
                       ) -> Union[Message, List[Message]]:
        """ This will take care of "flood control exceeded" API errors (RetryAfter Errors). """
        retryNumber = -1
        lastException = None
        while retryNumber < maxTries:
            try:
                retryNumber += 1
                if media is not None:
                    # Multiple photos/media
                    return self.updater.bot.sendMediaGroup(chat_id=chat_id, disable_notification=disable_notification, media=media)
                elif photo is not None:
                    # Photo
                    return self.updater.bot.send_photo(chat_id=chat_id, disable_notification=disable_notification, parse_mode=parse_mode, photo=photo, reply_markup=reply_markup,
                                                       caption=caption
                                                       )
                else:
                    # Text message
                    return self.updater.bot.send_message(chat_id=chat_id, disable_notification=disable_notification, text=text, parse_mode=parse_mode, reply_markup=reply_markup,
                                                         disable_web_page_preview=disable_web_page_preview)
            except RetryAfter as retryError:
                # https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this
                lastException = retryError
                """ Rate-Limit errorhandling: Wait some time and try again (one retry should do the job) """
                logging.info("Rate limit reached, waiting " + str(retryError.retry_after) + " seconds | Try number: " + str(retryNumber))
                time.sleep(retryError.retry_after)
                continue
            except BadRequest as requesterror:
                if requesterror.message == 'Group send failed':
                    # 2021-08-17: For unknown reasons this keeps happening sometimes...
                    # 2021-08-31: Seems like this is also some kind of rate limit or the same as the other one but no retry_after value given...
                    lastException = requesterror
                    waitseconds = 5
                    logging.info("Group send failed, waiting " + str(waitseconds) + " seconds | Try number: " + str(retryNumber))
                    time.sleep(waitseconds)
                    continue
                else:
                    raise requesterror
        raise lastException

    def deleteMessage(self, chat_id: Union[int, str], messageID: Union[int, None]):
        if messageID is None:
            return
        try:
            self.updater.bot.delete_message(chat_id=chat_id, message_id=messageID)
        except BadRequest:
            """ Typically this means that this message has already been deleted """
            logging.warning("Failed to delete message with message_id: " + str(messageID))

    def getUser(self, userID: Union[int, str]) -> User:
        """ Wrapper """
        return User.load(self.crawler.getUsersDB(), str(userID))


class ImageCache:
    # TODO: Replace current photo cache with this
    def __init__(self, fileID: str):
        self.imageFileID = fileID
        self.timestampCreated = datetime.now().timestamp()
        self.timestampLastUsed = datetime.now().timestamp()

    def updateLastUsedTimestamp(self):
        """ Updates last used timestamp to current timestamp. """
        self.timestampLastUsed = datetime.now().timestamp()


if __name__ == '__main__':
    bkbot = BKBot()
    # schedule.every().day.do(bkbot.crawl)
    """ We could even choose the same time here as schedule will run jobs that were "missed" because the job before was taking too long ;) """
    if bkbot.getPublicChannelName() is None:
        schedule.every().day.at("00:01").do(bkbot.batchProcessWithoutChannelUpdate)
    else:
        schedule.every().day.at("00:01").do(bkbot.batchProcess)
    schedule.every(21).days.do(bkbot.cleanupCaches)
    # schedule.every().day.at("00:02").do(bkbot.renewPublicChannel)
    # schedule.every().day.at("00:03").do(bkbot.notifyUsers)
    """ Always run bot first. """
    bkbot.startBot()
    """ Check for special flag to force-run batch process immediately. """
    # First the ones which can be combined with others and need to be executed first
    if 'crawl' in sys.argv:
        bkbot.crawl()
    # Now the ones where only one is allowed
    if 'forcechannelupdatewithresend' in sys.argv:
        bkbot.renewPublicChannel()
        bkbot.cleanupPublicChannel()
    elif 'resumechannelupdate' in sys.argv:
        bkbot.resumePublicChannelUpdate()
        bkbot.cleanupPublicChannel()
    elif 'forcebatchprocess' in sys.argv:
        # bkbot.crawl()
        # bkbot.notifyUsers()
        bkbot.batchProcess()
        # updatePublicChannel(bkbot, reSendAll=False)
        # schedule.every(10).seconds.do(bkbot.updatePublicChannel)
        # schedule.every(10).seconds.do(bkbot.notifyUsers)
    elif 'nukechannel' in sys.argv:
        nukeChannel(bkbot)
    elif 'cleanupchannel' in sys.argv:
        cleanupChannel(bkbot)
    elif 'migrate' in sys.argv:
        bkbot.crawler.migrateDBs()
    if 'usernotify' in sys.argv:
        bkbot.notifyUsers()
    # schedule.every(10).seconds.do(bkbot.startBot)
    while True:
        schedule.run_pending()
        time.sleep(1)
