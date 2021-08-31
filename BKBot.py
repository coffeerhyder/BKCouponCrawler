import math
import sys
import time
import traceback
from typing import Tuple, Union, List

import schedule
from couchdb import Database
from furl import furl, urllib
from telegram import Update, InlineKeyboardButton, InputMediaPhoto, Message, ReplyMarkup
from telegram.error import RetryAfter, Unauthorized, BadRequest
from telegram.ext import Updater, CommandHandler, CallbackContext, ConversationHandler, CallbackQueryHandler, MessageHandler, Filters
from telegram.utils.helpers import DEFAULT_NONE
from telegram.utils.types import ODVInput, FileInput

from BotNotificator import updatePublicChannel, notifyUsersAboutNewCoupons, ChannelUpdateMode, nukeChannel, cleanupChannel
from BotUtils import *
import logging

from Helper import *
from Crawler import BKCrawler, sortCouponsByPrice
from Models import CouponFilter

from UtilsCouponsDB import couponDBGetUniqueCouponID, \
    couponDBGetTitleShortened, couponDBGetUniqueIdentifier, couponDBGetPriceFormatted, couponDBGetImageQR, isValidBotCoupon, \
    couponDBGetImagePath, couponDBGetPLUOrUniqueID, Coupon, User, ChannelCoupon, CouponSortMode, getFormattedPrice, InfoEntry, generateCouponLongTextFormatted, \
    generateCouponLongTextFormattedWithDescription, generateCouponShortText, generateCouponShortTextFormatted, generateCouponShortTextFormattedWithHyperlinkToChannelPost, \
    generateCouponLongTextFormattedWithHyperlinkToChannelPost, getCouponsSeparatedByType
from CouponCategory import CouponCategory, BotAllowedCouponSources, CouponSource
from UtilsOffers import offerGetImagePath

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
# Use public API: https://gist.github.com/max1220/7f2f65be4381bc0878e64a985fd71da4
headers = {"User-Agent": "BurgerKing/6.7.0 (de.burgerking.kingfinder; build:432; Android 8.0.0) okhttp/3.12.3"}


class CouponDisplayMode:
    ALL = "a"
    ALL_WITHOUT_MENU = 'a2'
    CATEGORY = 'c'
    CATEGORY_WITHOUT_MENU = 'c2'
    HIDDEN_APP_COUPONS_ONLY = 'h'
    FAVORITES = 'f'


class PhotoCacheVars:
    FILE_ID = 'file_id'
    FILE_ID_QR = 'file_id_qr'
    TIMESTAMP_CREATED = 'timestamp_created'
    TIMESTAMP_LAST_USED = 'timestamp_last_used'
    UNIQUE_IDENTIFIER = 'unique_identifier'
    IMAGE_URL = 'image_url'


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


class BKBot:

    def __init__(self):
        self.couponImageCache = {}
        self.offerImageCache = {}
        self.cfg = loadConfig()
        if self.cfg is None:
            raise Exception('Broken or missing config')
        self.crawler = BKCrawler()
        self.crawler.setExportCSVs(False)
        self.publicChannelName = self.cfg.get(Config.PUBLIC_CHANNEL_NAME)
        self.botName = self.cfg[Config.BOT_NAME]
        self.couchdb = self.crawler.getServer()
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
                    CallbackQueryHandler(self.botDisplayCoupons, pattern='.*a=dcs.*'),
                    CallbackQueryHandler(self.botDisplayCouponsWithImagesFavorites, pattern='^' + CallbackVars.MENU_COUPONS_FAVORITES_WITH_IMAGES + '$'),
                    CallbackQueryHandler(self.botDisplayOffers, pattern='^' + CallbackVars.MENU_OFFERS + '$'),
                    CallbackQueryHandler(self.botDisplayFeedbackCodes, pattern='^' + CallbackVars.MENU_FEEDBACK_CODES + '$'),
                    CallbackQueryHandler(self.botDisplaySettings, pattern='^' + CallbackVars.MENU_SETTINGS + '$'),
                ],
                CallbackVars.MENU_OFFERS: [
                    CallbackQueryHandler(self.botDisplayCoupons, pattern='.*a=dcs.*'),
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                ],
                CallbackVars.MENU_FEEDBACK_CODES: [
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                ],
                CallbackVars.MENU_DISPLAY_COUPON: [
                    # Back to last coupons menu
                    CallbackQueryHandler(self.botDisplayCoupons, pattern='.*a=dcs.*'),
                    # Display single coupon
                    CallbackQueryHandler(self.botDisplaySingleCoupon, pattern='.*a=dc.*'),
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                    CallbackQueryHandler(self.botDisplayEasterEgg, pattern='^' + CallbackVars.EASTER_EGG + '$'),
                ],
                CallbackVars.MENU_SETTINGS: [
                    # Back to main menu
                    CallbackQueryHandler(self.botDisplayMenuMain, pattern='^' + CallbackVars.MENU_MAIN + '$'),
                    CallbackQueryHandler(self.botDisplaySettingsToggleSetting, pattern=generateCallbackRegEx(User().settings)),
                    CallbackQueryHandler(self.botDeleteUnavailableFavoriteCoupons, pattern="^" + CallbackVars.MENU_SETTINGS_DELETE_UNAVAILABLE_FAVORITE_COUPONS + "$"),
                ],
            },
            fallbacks=[CommandHandler('start', self.botDisplayMenuMain)],
            name="MainConversationHandler",
        )
        dispatcher.add_handler(conv_handler)
        """ Handles deletion of userdata. """
        conv_handler2 = ConversationHandler(
            entry_points=[CommandHandler('tschau', self.botUserDeleteSTART)],
            states={
                CallbackVars.MENU_SETTINGS_USER_DELETE_DATA: [
                    CommandHandler('cancel', self.botUserDeleteCancel),
                    # Delete users account
                    MessageHandler(Filters.text, self.botUserDelete),
                ],

            },
            fallbacks=[CommandHandler('start', self.botDisplayMenuMain)],
            name="DeleteUserConvHandler",
            allow_reentry=True,
        )
        dispatcher.add_handler(conv_handler2)
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
        dispatcher.add_handler(conv_handler3)
        """
        2021-01-12: I've decided to drop these commands for now as our menu "back" button won't work like this.
        It would need a lot of refactoring to make the menus and commands work at the same time!
        """
        # dispatcher.add_handler(CommandHandler('favoriten', self.botDisplayCouponsFavorites))
        # dispatcher.add_handler(CommandHandler('coupons', self.botDisplayCoupons))
        # dispatcher.add_handler(CommandHandler('coupons2', self.botDisplayCouponsWithoutFriesAndCoke))
        # dispatcher.add_handler(CommandHandler('angebote', self.botDisplayOffers))
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
        query = update.callback_query
        query.answer()
        query.edit_message_text(text=botError.getErrorMsg(), parse_mode="HTML", reply_markup=botError.getReplyMarkup())

    def getPublicChannelName(self, fallback=None) -> Union[str, None]:
        """ Returns name of public channel which this bot is taking care of. """
        if self.publicChannelName is not None:
            return self.publicChannelName
        else:
            return fallback

    def getPublicChannelChatID(self) -> Union[str, None]:
        if self.getPublicChannelName() is None:
            return None
        else:
            return '@' + self.getPublicChannelName()

    def getPublicChannelHyperlinkWithCustomizedText(self, linkText: str) -> str:
        """ Returns: e.g. <a href="https://t.me/channelName">linkText</a>
        Only call this if self.publicChannelName != None!!! """
        return "<a href=\"https://t.me/" + self.getPublicChannelName() + "\">" + linkText + "</a>"

    def botDisplayMenuMain(self, update: Update, context: CallbackContext):
        query = update.callback_query
        if query is not None:
            query.answer()
        userDB = self.crawler.getUsersDB()
        """ New user --> Add userID to DB. """
        if str(update.effective_user.id) not in userDB:
            # Add user to DB for the first time
            user = User(
                id=str(update.effective_user.id)
            )
            user.store(userDB)
        allButtons = []
        if self.getPublicChannelName() is not None:
            allButtons.append([InlineKeyboardButton('Alle Coupons Liste + Pics + News', url='https://t.me/' + self.getPublicChannelName())])
            allButtons.append([InlineKeyboardButton('Alle Coupons Liste lange Titel + Pics', callback_data=CallbackVars.MENU_DISPLAY_ALL_COUPONS_LIST_WITH_FULL_TITLES)])
        if len(self.crawler.cachedAvailableCouponSources) != 1:
            # Only show these two buttons if more than one coupon source is available and also if none is available (else our main menu would be nearly completely empty which would probably confuse our users)
            allButtons.append([InlineKeyboardButton('Alle Coupons', callback_data="?a=dcs&m=" + CouponDisplayMode.ALL + "&cs=")])
            allButtons.append([InlineKeyboardButton('Alle Coupons ohne Menü', callback_data="?a=dcs&m=" + CouponDisplayMode.ALL_WITHOUT_MENU + "&cs=")])
        for couponSrc in BotAllowedCouponSources:
            # Only add buttons for coupon sources for which at least one coupon is available
            if couponSrc not in self.crawler.cachedAvailableCouponSources:
                continue
            couponCategory = CouponCategory(couponSrc)
            allButtons.append([InlineKeyboardButton(CouponCategory(couponSrc).namePlural, callback_data="?a=dcs&m=" + CouponDisplayMode.CATEGORY + "&cs=" + str(couponSrc))])
            if couponCategory.allowsExtraSelectionForCouponsWithoutMenu:
                allButtons.append([InlineKeyboardButton(CouponCategory(couponSrc).namePlural + ' ohne Menü',
                                                        callback_data="?a=dcs&m=" + CouponDisplayMode.CATEGORY_WITHOUT_MENU + "&cs=" + str(couponSrc))])
            if couponSrc == CouponSource.APP and self.crawler.cachedHasHiddenAppCouponsAvailable:
                allButtons.append([InlineKeyboardButton(CouponCategory(couponSrc).namePlural + ' versteckte',
                                                        callback_data="?a=dcs&m=" + CouponDisplayMode.HIDDEN_APP_COUPONS_ONLY + "&cs=" + str(couponSrc))])
        keyboardCouponsFavorites = [InlineKeyboardButton(SYMBOLS.STAR + 'Favoriten' + SYMBOLS.STAR, callback_data="?a=dcs&m=" + CouponDisplayMode.FAVORITES),
                                    InlineKeyboardButton(SYMBOLS.STAR + 'Favoriten + Pics' + SYMBOLS.STAR, callback_data=CallbackVars.MENU_COUPONS_FAVORITES_WITH_IMAGES)]
        allButtons.append(keyboardCouponsFavorites)
        # keyboardFeedbackCodes = [InlineKeyboardButton('Feedback Code Generator', callback_data=CallbackVars.MENU_FEEDBACK_CODES)]
        allButtons.append(
            [InlineKeyboardButton('Angebote', callback_data=CallbackVars.MENU_OFFERS), InlineKeyboardButton('KING Finder', url='https://www.burgerking.de/kingfinder')])
        allButtons.append([InlineKeyboardButton(SYMBOLS.WRENCH + 'Einstellungen', callback_data=CallbackVars.MENU_SETTINGS)])
        reply_markup = InlineKeyboardMarkup(allButtons)
        menuText = 'Hallo ' + update.effective_user.first_name + ', <b>Bock auf Fastfood?</b>'
        menuText += '\n' + getBotImpressum()
        if query is not None:
            query.edit_message_text(text=menuText, reply_markup=reply_markup, parse_mode='HTML')
        else:
            self.sendMessage(chat_id=update.effective_message.chat_id, text=menuText, reply_markup=reply_markup, parse_mode='HTML')
        return CallbackVars.MENU_MAIN

    def botDisplayAllCouponsListWithFullTitles(self, update: Update, context: CallbackContext):
        """ Send list containing all coupons with long titles linked to coupon channel to user. This may result in up to 10 messages being sent! """
        update.callback_query.answer()
        activeCoupons = bkbot.crawler.filterCoupons(CouponFilter(activeOnly=True, allowedCouponSources=BotAllowedCouponSources, sortMode=CouponSortMode.SOURCE_MENU_PRICE))
        self.sendCouponOverviewWithChannelLinks(chat_id=update.effective_user.id, coupons=activeCoupons, useLongCouponTitles=True, channelDB=self.couchdb[DATABASES.TELEGRAM_CHANNEL], infoDB=None, infoDBDoc=None,
                                                allowMessageEdit=False)
        # Delete last message containing menu as it is of no use for us anymore
        self.deleteMessage(chat_id=update.effective_user.id, messageID=update.callback_query.message.message_id)
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]])
        self.updater.bot.send_message(chat_id=update.effective_user.id, text="Alle " + str(len(activeCoupons)) + " Coupons als Liste mit langen Titeln", reply_markup=reply_markup)
        return CallbackVars.MENU_MAIN

    def botDisplayCoupons(self, update: Update, context: CallbackContext):
        """ Displays all coupons in a pre selected mode """
        callbackVar = update.callback_query.data
        # Important! This is required so that we can e.g. jump from "Category 'App coupons' page 2 display single coupon" back into "Category 'App coupons' page 2"
        callbackVar += "&cb=" + urllib.parse.quote(callbackVar)
        urlQuery = furl(callbackVar)
        urlinfo = urlQuery.args
        mode = urlinfo["m"]
        # page = int(urlinfo.get('page', 0))
        try:
            coupons = None
            menuText = None
            highlightFavorites = True
            user = User.load(self.couchdb[DATABASES.TELEGRAM_USERS], str(update.effective_user.id))
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
                coupons = self.getFilteredCoupons(CouponFilter(sortMode=CouponSortMode.PRICE, allowedCouponSources=[couponSrc], containsFriesAndCoke=None, isHidden=True))
                menuText = '<b>' + str(len(coupons)) + ' versteckte ' + CouponCategory(couponSrc).namePluralWithoutSymbol + ' verfügbar:</b>'
            elif mode == CouponDisplayMode.FAVORITES:
                coupons, unavailableCouponsText = self.getValidUserFavoritesAndUnavailableFavoritesString(user)
                menuText = SYMBOLS.STAR + str(len(coupons)) + ' Favoriten verfügbar ' + SYMBOLS.STAR
                numberofCouponsWithoutPrice = 0
                totalSum = 0
                for coupon in coupons:
                    if coupon.price is not None:
                        totalSum += coupon.price
                    else:
                        numberofCouponsWithoutPrice += 1
                menuText += "\n<b>Gesamtwert:</b> " + getFormattedPrice(totalSum)
                if numberofCouponsWithoutPrice > 0:
                    menuText += "*\n* exklusive " + str(numberofCouponsWithoutPrice) + " Coupons, deren Preis nicht bekannt ist."
                if len(unavailableCouponsText) > 0:
                    menuText += '\n' + unavailableCouponsText
                highlightFavorites = False
            self.displayCouponsAsButtons(update, user, coupons, menuText, urlQuery, highlightFavorites=highlightFavorites)
            return CallbackVars.MENU_DISPLAY_COUPON
        except BetterBotException as botError:
            self.handleBotErrorGently(update, context, botError)
            return CallbackVars.MENU_MAIN

    def getValidUserFavoritesAndUnavailableFavoritesString(self, user: User) -> Tuple[List[Coupon], str]:
        """
        Returns favorites of current user. Raises Exception if e.g. user has no favorites or all of his favorites are expired.
        """
        if len(user.favoriteCoupons) == 0:
            menuText = '<b>Du hast noch keine Favoriten!</b>'
            raise BetterBotException(menuText, InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]]))
        # Prefer custom code over crawler function as it requires less CPU cycles
        # Collect users' currently existing favorite coupons
        validFavoriteCoupons = []
        unavailableCouponsText = ''
        numberofUnavailableFavorites = 0
        productiveCouponDB = self.crawler.getCouponDB()
        for uniqueCouponID, coupon in user.favoriteCoupons.items():
            couponFromProductiveDB = Coupon.load(productiveCouponDB, uniqueCouponID)
            if couponFromProductiveDB is not None and isValidBotCoupon(couponFromProductiveDB):
                validFavoriteCoupons.append(couponFromProductiveDB)
            else:
                # User chosen favorite coupon has expired or is not in DB
                coupon = Coupon.wrap(coupon)  # We want a 'real' coupon object
                unavailableCouponsText += '\n' + uniqueCouponID + ' | ' + couponDBGetTitleShortened(coupon)
                if coupon.price is not None:
                    unavailableCouponsText += ' | ' + couponDBGetPriceFormatted(coupon)
                numberofUnavailableFavorites += 1
        if len(validFavoriteCoupons) == 0:
            # Edge case
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]])
            menuText = SYMBOLS.WARNING + '\n<b>Derzeit ist keiner deiner ' + str(len(user.favoriteCoupons)) + ' favorisierten Coupons verfügbar:</b>'
            menuText += unavailableCouponsText
            raise BetterBotException(menuText, reply_markup)
        if len(unavailableCouponsText) > 0:
            unavailableCouponsText = '\n' + SYMBOLS.WARNING + str(numberofUnavailableFavorites) + ' deiner Favoriten sind abgelaufen:' + '\n' + unavailableCouponsText.strip()
            if user.settings.notifyWhenFavoritesAreBack:
                # 2021-08-27: Removed this text to purify the favorites overview -> It contains a lot of text already!
                # unavailableCouponsText += '\n' + SYMBOLS.CONFIRM + 'Du wirst benachrichtigt, sobald abgelaufene Coupons wieder verfügbar sind.'
                pass
            else:
                unavailableCouponsText += '\n' + SYMBOLS.INFORMATION + 'Schau in die Einstellungen: Lasse dich benachrichtigen, wenn abgelaufene Coupons wieder verfügbar sind oder lösche diese mit einem Klick.'
                # unavailableCouponsText += '\nEbenfalls kannst du abgelaufene Favoriten in den Einstellungen löschen.'
        validFavoriteCoupons = sortCouponsByPrice(validFavoriteCoupons)
        return validFavoriteCoupons, unavailableCouponsText

    def getUnavailableFavoriteCouponIDs(self, user: User) -> list:
        """ Returns all couponIDs which the user has set as favorite but which are not available (expired) at this moment. """
        if len(user.favoriteCoupons) == 0:
            # Saves one DB request if user has no favorites at all :)
            return []
        inactiveFavoriteCouponIDs = []
        productiveCouponDB = self.crawler.getCouponDB()
        for favoriteCouponID in user.favoriteCoupons:
            coupon = Coupon.load(productiveCouponDB, favoriteCouponID)
            if coupon is None:
                # Favorite couponID is not present anymore in DB -> Counts as expired!
                inactiveFavoriteCouponIDs.append(favoriteCouponID)
            elif not isValidBotCoupon(coupon):
                inactiveFavoriteCouponIDs.append(favoriteCouponID)
        return inactiveFavoriteCouponIDs

    def displayCouponsAsButtons(self, update: Update, user: Union[User, None], coupons: list, menuText: str, urlquery, highlightFavorites: bool):
        if len(coupons) == 0:
            # This should never happen
            raise BetterBotException(SYMBOLS.DENY + ' <b>Ausnahmefehler: Es gibt derzeit keine Coupons!</b>',
                                     InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=urlquery.url)]]))
        query = update.callback_query
        query.answer()
        urlquery_callbackBack = furl(urlquery.args["cb"])
        buttons = []
        userFavoritesDict = {}
        if highlightFavorites:
            userFavoritesDict = user.favoriteCoupons
        maxCouponsPerPage = 20
        paginationMax = math.ceil(len(coupons) / maxCouponsPerPage)
        desiredPage = int(urlquery.args.get("p", 1))
        if desiredPage > paginationMax:
            # Fallback - can happen if user leaves menu open for a long time, DB changes and user presses old "next/previous page" button
            desiredPage = paginationMax
        # Grab all items in desired range (= on desired page)
        index = (desiredPage * maxCouponsPerPage - maxCouponsPerPage)
        # Whenever the user has at least one favorite coupon on page > 1 we'll replace the dummy middle page overview button which usually does not do anything with Easter Egg functionality
        containsAtLeastOneFavoriteCoupon = False
        while len(buttons) < maxCouponsPerPage and index < len(coupons):
            coupon = coupons[index]
            uniqueCouponID = couponDBGetUniqueCouponID(coupon)
            buttonText = ''
            if uniqueCouponID in userFavoritesDict:
                buttonText += SYMBOLS.STAR
                containsAtLeastOneFavoriteCoupon = True
            buttonText += generateCouponShortText(coupon)

            buttons.append([InlineKeyboardButton(buttonText, callback_data="?a=dc&plu=" + uniqueCouponID + "&cb=" + urllib.parse.quote(urlquery_callbackBack.url))])
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
                # Easter egg: Trigger it if there are at least two pages AND user is on the last page AND that page contains at least one favorite coupon
                if containsAtLeastOneFavoriteCoupon and desiredPage > 1:
                    navigationButtons.append(InlineKeyboardButton(SYMBOLS.GHOST, callback_data=CallbackVars.EASTER_EGG))
                else:
                    navigationButtons.append(InlineKeyboardButton(SYMBOLS.GHOST, callback_data="DummyButtonNextPage"))
            buttons.append(navigationButtons)
        buttons.append([InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)])
        reply_markup = InlineKeyboardMarkup(buttons)
        query.edit_message_text(text=menuText, reply_markup=reply_markup, parse_mode='HTML')
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
            coupons, unavailableCouponsText = self.getValidUserFavoritesAndUnavailableFavoritesString(User.load(self.crawler.getUsersDB(), str(update.effective_user.id)))
        except BetterBotException as botError:
            self.handleBotErrorGently(update, context, botError)
            return CallbackVars.MENU_DISPLAY_COUPON
        query = update.callback_query
        query.answer()
        bottomMsgText = ''
        if len(unavailableCouponsText) > 0:
            bottomMsgText += unavailableCouponsText + '\n'
        bottomMsgText += '<b>Guten Hunger!</b>'
        self.displayCouponsWithImagesAndBackButton(update, context, coupons, topMsgText='<b>Alle Favoriten mit Bildern:</b>', bottomMsgText=bottomMsgText)
        # Delete last message containing menu
        context.bot.delete_message(chat_id=update.effective_message.chat_id, message_id=query.message.message_id)
        return CallbackVars.MENU_DISPLAY_COUPON

    def displayCouponsWithImagesAndBackButton(self, update: Update, context: CallbackContext, coupons: list, topMsgText: str, bottomMsgText: str = "Zurück zum Hauptmenü?"):
        self.displayCouponsWithImages(update, context, coupons, topMsgText)
        update.effective_message.reply_text(text=bottomMsgText, parse_mode="HTML",
                                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)], []]))

    def displayCouponsWithImages(self, update: Update, context: CallbackContext, coupons: list, msgText: str):
        self.sendMessage(chat_id=update.effective_message.chat_id, text=msgText, parse_mode='HTML')
        index = 0
        user = User.load(self.crawler.getUsersDB(), str(update.effective_user.id))
        showCouponIndexText = False
        for coupon in coupons:
            isUserFavorite = coupon.id in user.favoriteCoupons
            if showCouponIndexText:
                additionalText = 'Coupon ' + str(index + 1) + ' / ' + str(len(coupons))
            else:
                additionalText = None
            self.displayCouponWithImage(update, context, coupon, isUserFavorite, user.settings.displayQR, additionalText)
            index += 1

    def botDisplayOffers(self, update: Update, context: CallbackContext):
        """
        Posts all current offers (= photos with captions) into current chat.
        """
        query = update.callback_query
        activeOffers = self.crawler.getOffersActive()
        if len(activeOffers) == 0:
            # BK should always have offers but let's check for this case anyways.
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]])
            menuText = SYMBOLS.WARNING + '<b>Es gibt derzeit keine Angebote!</b>'
            if query is not None:
                query.edit_message_text(text=menuText, reply_markup=reply_markup, parse_mode='HTML')
            else:
                update.effective_message.reply_text(menuText, reply_markup=reply_markup, parse_mode='HTML')
            return CallbackVars.MENU_MAIN
        prePhotosText = '<b>Es sind derzeit ' + str(len(activeOffers)) + ' Angebote verfügbar:</b>'
        # Try to "recycle" latest message
        if query is not None:
            query.answer()
            query.edit_message_text(text=prePhotosText, parse_mode='HTML')
        else:
            update.effective_message.reply_text(prePhotosText, parse_mode='HTML')
        for offer in activeOffers:
            offerID = offer['id']
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
            if offerID not in self.offerImageCache or self.offerImageCache[offerID][PhotoCacheVars.IMAGE_URL] != couponOrOfferGetImageURL(offer):
                self.offerImageCache[offerID] = {PhotoCacheVars.FILE_ID: sentMessage.photo[0].file_id, PhotoCacheVars.IMAGE_URL: couponOrOfferGetImageURL(offer),
                                                 PhotoCacheVars.TIMESTAMP_CREATED: datetime.now().timestamp(),
                                                 PhotoCacheVars.TIMESTAMP_LAST_USED: datetime.now().timestamp()}

        menuText = '<b>Nix dabei?</b>'
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN),
                                              InlineKeyboardButton(SYMBOLS.ARROW_RIGHT + " Zu den Gutscheinen", callback_data="?a=dcs&m=" + CouponDisplayMode.ALL + "&cs=")], []])
        update.effective_message.reply_text(menuText, parse_mode='HTML', reply_markup=reply_markup)
        return CallbackVars.MENU_OFFERS

    def botDisplayFeedbackCodes(self, update: Update, context: CallbackContext):
        """ 2021-07-15: New- and unfinished feature """
        query = update.callback_query
        query.answer()
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]])
        numberOfFeedbackCodesToGenerate = 3
        text = "<b>Hier sind " + str(numberOfFeedbackCodesToGenerate) + " Feedback Codes für dich:</b>"
        for index in range(numberOfFeedbackCodesToGenerate):
            text += "\n" + generateFeedbackCode()
        text += "\nSchreibe einen Code deiner Wahl auf die Rückseine deines BK Kassenbons, um den (gratis) Artikel zu erhalten."
        text += "\nFalls du keinen Kassenbon hast und kein Schamgefühl kennst, hier ein Trick:"
        text += "\nBestelle ein einzelnes Päckchen Mayo oder Ketchup (~0,20€)."
        text += "\nDie Konditionen der Feedback Codes variieren.\nAktuell gibt es: Gratis Eiswaffel oder Kaffee(klein) [Stand 14.04.2021]"
        text += "\nDanke an <a href=\"https://edik.ch/posts/hack-the-burger-king.html\">Edik</a>!"
        query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode='HTML', disable_web_page_preview=True)
        return CallbackVars.MENU_FEEDBACK_CODES

    def botDisplaySettings(self, update: Update, context: CallbackContext):
        update.callback_query.answer()
        user = User.load(self.crawler.getUsersDB(), str(update.effective_user.id))
        return self.displaySettings(update, context, user)

    def displaySettings(self, update: Update, context: CallbackContext, user: User):
        keyboard = []
        # TODO: Make this nicer
        dummyUser = User()
        for settingKey, setting in dummyUser["settings"].items():
            description = USER_SETTINGS_ON_OFF[settingKey]["description"]
            if user.settings.get(settingKey, dummyUser.settings[settingKey]):
                # Add symbol to enabled settings button text so user can see which settings are currently enabled
                keyboard.append(
                    [InlineKeyboardButton(SYMBOLS.CONFIRM + " " + description, callback_data=settingKey)])
            else:
                keyboard.append([InlineKeyboardButton(description, callback_data=settingKey)])
        unavailableCoupons = self.getUnavailableFavoriteCouponIDs(user)
        menuText = SYMBOLS.WRENCH + "<b>Einstellungen:</b>\n"
        menuText += "Nicht alle Filialen nehmen alle Gutschein-Typen!\nPrüfe die Akzeptanz von App- bzw. Papiercoupons vorm Bestellen über den <a href=\"https://www.burgerking.de/kingfinder\">KINGFINDER</a>."
        menuText += "\n** Versteckte Coupons sind meist überteuerte große Menüs."
        menuText += "\nWenn aktiviert, werden diese nicht nur über den extra Menüpunkt 'App Coupons versteckte' angezeigt sondern zusätzlich innerhalb der folgenden Kategorien: Alle Coupons, App Coupons"
        if len(unavailableCoupons) > 0:
            keyboard.append([InlineKeyboardButton(SYMBOLS.DENY + "Abgelaufene Favoriten löschen (" + str(len(unavailableCoupons)) + ")?***",
                                                  callback_data=CallbackVars.MENU_SETTINGS_DELETE_UNAVAILABLE_FAVORITE_COUPONS)])
            menuText += "\n***Achtung: Abgelaufene Favoriten werden beim Drücken des Buttons sofort ohne Bestätigung gelöscht!"
        # Back button
        keyboard.append([InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)])
        update.callback_query.edit_message_text(text=menuText, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
        return CallbackVars.MENU_SETTINGS

    def botDisplaySingleCoupon(self, update: Update, context: CallbackContext):
        query = update.callback_query
        query.answer()
        callbackArgs = furl(query.data).args
        uniqueCouponID = callbackArgs['plu']
        callbackBack = callbackArgs['cb']
        coupon = Coupon.load(self.crawler.getCouponDB(), uniqueCouponID)
        user = User.load(self.crawler.getUsersDB(), str(update.effective_user.id))
        couponIsUserFavorite = uniqueCouponID in user.favoriteCoupons
        self.displayCouponWithImage(update, context, coupon, couponIsUserFavorite, user.settings.displayQR)
        menuText = 'Coupon Details'
        if not user.settings.displayQR:
            menuText += '\n' + SYMBOLS.INFORMATION + 'Möchtest du QR-Codes angezeigt bekommen?\nSiehe Hauptmenü -> Einstellungen'
        self.sendMessage(chat_id=update.effective_message.chat_id, text=menuText, parse_mode='HTML',
                         reply_markup=InlineKeyboardMarkup([[], [InlineKeyboardButton(SYMBOLS.BACK, callback_data=callbackBack)]]))
        # Delete previous message containing menu buttons from chat as we don't need it anymore.
        context.bot.delete_message(chat_id=update.effective_message.chat_id, message_id=query.message.message_id)
        return CallbackVars.MENU_DISPLAY_COUPON

    def botUserDeleteSTART(self, update: Update, context: CallbackContext):
        menuText = '<b>\"Dann geh\' doch zu Netto!\"</b>\nAntworte mit deiner Benutzer-ID <b>' + str(
            update.effective_user.id) + '</b>, um deine Benutzerdaten vom Server zu löschen.\n'
        menuText += 'Abbruch mit /cancel'
        update.effective_message.reply_text(text=menuText, parse_mode='HTML')
        return CallbackVars.MENU_SETTINGS_USER_DELETE_DATA

    def botUserDelete(self, update: Update, context: CallbackContext):
        userInput = update.message.text
        if userInput is not None and userInput == str(update.effective_user.id):
            userDB = self.crawler.getUsersDB()
            """ Only delete userID if it exists -> It being nonexistant really is an edge case that doesn't happen during normal usage! """
            if str(update.effective_user.id) in userDB:
                del userDB[str(update.effective_user.id)]
            menuText = SYMBOLS.CONFIRM + ' Deine Daten wurden vernichtet!\n'
            menuText += 'Du kannst diesen Chat nun löschen.\n'
            menuText += '<b>Viel Erfolg beim Abnehmen!</b>\n'
            menuText += '<i>In loving memory of blauelagunepb ' + SYMBOLS.HEART + '</i>'
            update.effective_message.reply_text(text=menuText, parse_mode='HTML')
        else:
            menuText = SYMBOLS.DENY + '<b> Falsche Antwort!</b>\n'
            menuText += 'Hast du dich umentschieden?\n'
            menuText += 'Mit /start gelangst du zurück in\'s Hauptmenü und mit /tschau kannst du deine Daten löschen!'
            update.effective_message.reply_text(text=menuText, parse_mode='HTML')
        return ConversationHandler.END

    def botUserDeleteCancel(self, update: Update, context: CallbackContext):
        """ Gets called if user cancels deletion of his own data. """
        menuText = SYMBOLS.DENY + ' <b>Löschen der Benutzerdaten abgebrochen!</b>\nMit /start gelangst du zurück in\'s Hauptmenü.'
        update.effective_message.reply_text(text=menuText, parse_mode='HTML')
        return ConversationHandler.END

    def displayCouponWithImage(self, update: Update, context: CallbackContext, coupon: Coupon, isFavorite: bool, sendQRCode: bool, additionalText: Union[str, None] = None):
        """
        Sends new message with coupon information & photo (& optionally coupon QR code) + "Save/Delete favorite" button in chat.
        """
        favoriteKeyboard = self.getCouponFavoriteKeyboard(isFavorite, coupon.id, CallbackVars.COUPON_LOOSE_WITH_FAVORITE_SETTING)
        replyMarkupWithoutBackButton = InlineKeyboardMarkup([favoriteKeyboard, []])
        couponText = generateCouponLongTextFormattedWithDescription(coupon)
        if additionalText is not None:
            couponText += '\n' + additionalText
        msgQR = None
        if sendQRCode:
            photoCoupon = InputMediaPhoto(media=self.getCouponImage(coupon), caption=couponText, parse_mode='HTML')
            photoQR = InputMediaPhoto(media=self.getCouponImageQR(coupon), caption=couponText, parse_mode='HTML')
            chatMessages = self.sendMediaGroup(chat_id=update.effective_message.chat_id, media=[photoCoupon, photoQR])
            msgCoupon = chatMessages[0]
            msgQR = chatMessages[1]
            self.sendMessage(chat_id=update.effective_message.chat_id, text=couponText, parse_mode='HTML', reply_markup=replyMarkupWithoutBackButton,
                             disable_web_page_preview=True)
        else:
            msgCoupon = self.sendPhoto(chat_id=update.effective_message.chat_id, photo=self.getCouponImage(coupon), caption=couponText, parse_mode='HTML',
                                       reply_markup=replyMarkupWithoutBackButton)
        # Update coupon image cache
        if coupon.id not in self.couponImageCache:
            self.couponImageCache[coupon.id] = {PhotoCacheVars.UNIQUE_IDENTIFIER: couponDBGetUniqueIdentifier(coupon), PhotoCacheVars.FILE_ID: msgCoupon.photo[0].file_id,
                                                PhotoCacheVars.TIMESTAMP_CREATED: datetime.now().timestamp(),
                                                PhotoCacheVars.TIMESTAMP_LAST_USED: datetime.now().timestamp()}
        elif self.couponImageCache[coupon.id][PhotoCacheVars.UNIQUE_IDENTIFIER] != couponDBGetUniqueIdentifier(coupon):
            logging.info("Refreshing coupon cache of: " + coupon.id)
            self.couponImageCache[coupon.id] = {PhotoCacheVars.UNIQUE_IDENTIFIER: couponDBGetUniqueIdentifier(coupon), PhotoCacheVars.FILE_ID: msgCoupon.photo[0].file_id,
                                                PhotoCacheVars.TIMESTAMP_LAST_USED: datetime.now().timestamp()}
        if sendQRCode:
            self.couponImageCache[coupon.id][PhotoCacheVars.FILE_ID_QR] = msgQR.photo[0].file_id
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
            del user.favoriteCoupons[uniqueCouponID]
            isFavorite = False
        else:
            # Add coupon to favorites
            user.favoriteCoupons[uniqueCouponID] = self.crawler.getCouponDB()[uniqueCouponID]
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
        text = "<b>" + couponDBGetPLUOrUniqueID(coupon) + "</b> | <a href=\"https://t.me/" + self.getPublicChannelName() + '/' + str(
            messageID) + "\">" + coupon.titleShortened + "</a>"
        priceFormatted = couponDBGetPriceFormatted(coupon)
        if priceFormatted is not None:
            text += " | " + priceFormatted
        return text

    def getFilteredCoupons(self, couponFilter: CouponFilter):
        """  Wrapper for crawler.filterCouponsList """
        coupons = self.crawler.filterCouponsList(couponFilter)
        if len(coupons) == 0:
            menuText = SYMBOLS.DENY + ' <b>Es gibt derzeit keine Coupons in den von dir ausgewählten Kategorien und/oder in Kombination mit den eingestellten Filtern!</b>'
            # menuText += "\nZurück mit /start"
            raise BetterBotException(menuText, InlineKeyboardMarkup([[InlineKeyboardButton(SYMBOLS.BACK, callback_data=CallbackVars.MENU_MAIN)]]))
        else:
            return coupons

    def getCouponImage(self, coupon):
        """ Returns either image URL or file or Telegram file_id of a given coupon. """
        uniqueCouponID = couponDBGetUniqueCouponID(coupon)
        cachedImageData = self.couponImageCache.get(uniqueCouponID)
        """ Re-use Telegram file-ID if possible: https://core.telegram.org/bots/api#message
        If the PLU has changed, we cannot just re-use the old ID because the images can contain that PLU code and the PLU code in our saved image can lead to a completely different product now!
        According to the Telegram FAQ, sich file_ids can be trusted to be persistent: https://core.telegram.org/bots/faq#can-i-count-on-file-ids-to-be-persistent """
        imagePath = couponDBGetImagePath(coupon)
        if cachedImageData is not None and cachedImageData[PhotoCacheVars.UNIQUE_IDENTIFIER] == couponDBGetUniqueIdentifier(coupon):
            # Re-use cached image_id and update cache timestamp
            self.couponImageCache[uniqueCouponID][PhotoCacheVars.TIMESTAMP_LAST_USED] = datetime.now().timestamp()
            logging.debug("Returning coupon image file_id: " + cachedImageData[PhotoCacheVars.FILE_ID])
            return cachedImageData[PhotoCacheVars.FILE_ID]
        elif isValidImageFile(imagePath):
            # Return image file
            logging.debug("Returning coupon image file in path: " + imagePath)
            return open(imagePath, mode='rb')
        else:
            # Return fallback image file -> Should usually not be required!
            logging.warning("Returning coupon fallback image")
            return open("media/fallback_image_missing_coupon_image.jpeg", mode='rb')

    def getCouponImageQR(self, coupon):
        """ Returns either image URL or file or Telegram file_id of a given coupon QR image. """
        uniqueCouponID = couponDBGetUniqueCouponID(coupon)
        cachedImageData = self.couponImageCache.get(uniqueCouponID)
        # Re-use Telegram file-ID if possible: https://core.telegram.org/bots/api#message
        if cachedImageData is not None and PhotoCacheVars.FILE_ID_QR in cachedImageData:
            # Return cached image_id and update cache timestamp
            self.couponImageCache[uniqueCouponID][PhotoCacheVars.TIMESTAMP_LAST_USED] = datetime.now().timestamp()
            logging.debug("Returning QR image file_id: " + cachedImageData[PhotoCacheVars.FILE_ID_QR])
            return cachedImageData[PhotoCacheVars.FILE_ID_QR]
        else:
            # Return image
            logging.debug("Returning QR image file")
            return couponDBGetImageQR(coupon)

    def getOfferImage(self, offer):
        """ Returns either image URL or file or Telegram file_id of a given offer. """
        offerID = offer['id']
        image_url = couponOrOfferGetImageURL(offer)
        cachedImageData = self.offerImageCache.get(offerID)
        if cachedImageData is not None and cachedImageData[PhotoCacheVars.IMAGE_URL] == image_url:
            # Re-use cached image_id and update cache timestamp
            self.offerImageCache[offerID][PhotoCacheVars.TIMESTAMP_LAST_USED] = datetime.now().timestamp()
            return cachedImageData[PhotoCacheVars.FILE_ID]
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

    def botDeleteUnavailableFavoriteCoupons(self, update: Update, context: CallbackContext):
        """ Removes all user selected favorites which are unavailable/expired at this moment. """
        userDB = self.crawler.getUsersDB()
        user = User.load(userDB, str(update.effective_user.id))
        userUnavailableFavoriteCouponIDs = self.getUnavailableFavoriteCouponIDs(user)
        if len(userUnavailableFavoriteCouponIDs) > 0:
            for unavailableFavoriteCouponID in userUnavailableFavoriteCouponIDs:
                # Double-check - we can't know whether or not has changed in between!
                if unavailableFavoriteCouponID in user.favoriteCoupons:
                    del user.favoriteCoupons[unavailableFavoriteCouponID]
            # Update DB
            user.store(userDB)
        else:
            # This should never happen
            logging.info("No expired favorites there to delete")
        # Reload settings menu
        return self.displaySettings(update, context, user)

    def getNewCouponsTextWithChannelHyperlinks(self, couponsDict: dict, maxNewCouponsDescriptionLines: int) -> str:
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
                messageIDs = ChannelCoupon.load(channelDB, coupon.id).messageIDs
                if len(messageIDs) > 0:
                    couponText = generateCouponShortTextFormattedWithHyperlinkToChannelPost(coupon, self.getPublicChannelName(), messageIDs[0])
                else:
                    # This should never happen but we'll allow it to
                    logging.warning("Can't hyperlink coupon because no messageIDs available: " + coupon.id)
                    couponText = generateCouponShortTextFormatted(coupon)
            else:
                # This should never happen but we'll allow it to anyways
                logging.warning("Can't hyperlink coupon because it is not in channelDB: " + coupon.id)
                couponText = generateCouponShortTextFormatted(coupon)
            infoText += '\n' + couponText

            if index == maxNewCouponsDescriptionLines - 1:
                # We processed the max. number of allowed items!
                break
            else:
                index += 1
                continue
        if len(couponsDict) > maxNewCouponsDescriptionLines:
            numberOfNonHyperinkedItems = len(couponsDict) - maxNewCouponsDescriptionLines
            if numberOfNonHyperinkedItems == 1:
                infoText += '\n+ ' + str(numberOfNonHyperinkedItems) + ' weiterer'
            else:
                infoText += '\n+ ' + str(numberOfNonHyperinkedItems) + ' weitere'
        return infoText

    def batchProcess(self):
        """ Runs all processes which should only run once per day:
         1. Crawler, 2. Channel renew/update, 3. User notify favorites/new coupons, 4. Cleanup channel """
        self.crawl()
        self.renewPublicChannel()
        self.notifyUsers()
        self.cleanupPublicChannel()

    def batchProcessWithoutChannelUpdate(self):
        """ Runs all processes which should only run once per day:
         1. Crawler, 2. User notify favorites and user notify new coupons """
        self.crawl()
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

    def updatePublicChannel(self):
        try:
            updatePublicChannel(self, updateMode=ChannelUpdateMode.UPDATE)
        except:
            traceback.print_exc()
            logging.warning("Update of public channel failed")

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
        self.cleanupCache(self.couponImageCache)
        self.cleanupCache(self.offerImageCache)

    def cleanupCache(self, cacheDict: dict):
        cacheDictCopy = cacheDict.copy()
        maxCacheAgeSeconds = 7 * 24 * 60 * 60
        for cacheID, cache in cacheDictCopy.items():
            cacheItemAge = datetime.now().timestamp() - cache[PhotoCacheVars.TIMESTAMP_LAST_USED]
            if cacheItemAge > maxCacheAgeSeconds:
                logging.info("Deleting cache item " + str(cacheID) + " as it was last used before: " + str(cacheItemAge) + " seconds")
                del cacheDict[cacheID]

    def sendCouponOverviewWithChannelLinks(self, chat_id: Union[int, str], coupons: dict, useLongCouponTitles: bool, channelDB: Database, infoDB: Union[None, Database],
                                           infoDBDoc: Union[None, InfoEntry], allowMessageEdit: bool):
        """ Sends all given coupons to given chat_id separated by source and split into multiple messages as needed. """
        couponsSeparatedByType = getCouponsSeparatedByType(coupons)
        """ Update/re-send coupon overview(s), spread this information on multiple pages if needed. """
        for couponSourceIndex in range(len(BotAllowedCouponSources)):
            couponSource = BotAllowedCouponSources[couponSourceIndex]
            couponCategory = CouponCategory(couponSource)
            logging.info("Working on coupon overview update " + str(couponSourceIndex + 1) + "/" + str(len(BotAllowedCouponSources)) + " | " + couponCategory.nameSingular)
            hasAddedSeparatorAfterCouponsWithoutMenu = False
            listContainsAtLeastOneItemWithoutMenu = False
            dbKeyMessageIDsCouponType = INFO_DB.DB_INFO_channel_last_coupon_type_overview_message_ids + str(couponSource)
            messageIDsForThisCategory = None if infoDBDoc is None else infoDBDoc.setdefault(dbKeyMessageIDsCouponType, [])
            if couponSource in couponsSeparatedByType:
                # allowMessageEdit == True --> Handling untested!
                coupons = couponsSeparatedByType[couponSource]
                # Depends on the max entities per post limit of Telegram and we're not only using hyperlinks but also the "<b>" tag so we do not have 50 hyperlinks left but 49.
                maxCouponsPerPage = 49
                maxPage = math.ceil(len(coupons) / maxCouponsPerPage)
                if allowMessageEdit and messageIDsForThisCategory is not None:
                    # Delete pages if there are too many
                    if len(messageIDsForThisCategory) > maxPage:
                        deleteStartIndex = (len(messageIDsForThisCategory) - (len(messageIDsForThisCategory) - maxPage)) - 1
                        for index in range(deleteStartIndex, len(messageIDsForThisCategory)):
                            infoDBDoc.messageIDsToDelete.append(messageIDsForThisCategory[index])
                        # Update our array as we fill it again later
                        del messageIDsForThisCategory[deleteStartIndex: len(messageIDsForThisCategory)]
                        # Update DB
                        infoDBDoc.store(infoDB)
                elif messageIDsForThisCategory is not None and len(messageIDsForThisCategory) > 0 and infoDBDoc is not None:
                    # Delete all old pages for current coupon type
                    # Save old messages for later deletion
                    infoDBDoc[InfoEntry.messageIDsToDelete.name] += messageIDsForThisCategory
                    messageIDsForThisCategory.clear()
                    # Update DB
                    infoDBDoc.store(infoDB)
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
                        """ Add a little separator so it is easier for the user to distinguish between coupons with- and without menu. 
                        This only works as "simple" as that because we pre-sorted these coupons!
                        """
                        if not coupon.containsFriesOrCoke:
                            listContainsAtLeastOneItemWithoutMenu = True
                        elif not hasAddedSeparatorAfterCouponsWithoutMenu and listContainsAtLeastOneItemWithoutMenu:
                            couponOverviewText += '\n<b>' + SYMBOLS.WHITE_DOWN_POINTING_BACKHAND + 'Coupons mit Menü' + SYMBOLS.WHITE_DOWN_POINTING_BACKHAND + '</b>'
                            hasAddedSeparatorAfterCouponsWithoutMenu = True
                        """ Generates e.g. "Y15 | 2Whopper+M🍟+0,4LCola | 8,99€"
                        Returns the same with hyperlink if a chat_id is given for this coupon e.g.:
                        "Y15 | 2Whopper+M🍟+0,4LCola (https://t.me/betterkingpublic/1054) | 8,99€"
                        """
                        if coupon.id in channelDB:
                            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
                            if len(channelCoupon.messageIDs) > 0:
                                if useLongCouponTitles:
                                    couponText = generateCouponLongTextFormattedWithHyperlinkToChannelPost(coupon, self.getPublicChannelName(), channelCoupon.messageIDs[0])
                                else:
                                    couponText = generateCouponShortTextFormattedWithHyperlinkToChannelPost(coupon, self.getPublicChannelName(), channelCoupon.messageIDs[0])
                            else:
                                # This should never happen but we'll allow it to
                                logging.warning("Can't hyperlink coupon because no messageIDs available: " + coupon.id)
                                if useLongCouponTitles:
                                    couponText = generateCouponLongTextFormatted(coupon)
                                else:
                                    couponText = generateCouponShortTextFormatted(coupon)
                        else:
                            # This should never happen but we'll allow it to
                            logging.warning("Can't hyperlink coupon because it is not in channelDB: " + coupon.id)
                            if useLongCouponTitles:
                                couponText = generateCouponLongTextFormatted(coupon)
                            else:
                                couponText = generateCouponShortTextFormatted(coupon)

                        couponOverviewText += '\n' + couponText
                        # Exit loop after last coupon info has been added
                        if couponIndex == len(coupons) - 1:
                            break
                    if allowMessageEdit and page - 1 <= len(messageIDsForThisCategory) - 1:
                        # Edit last post of current page
                        msgIDToEdit = messageIDsForThisCategory[page - 1]
                        self.editMessage(chat_id=chat_id, message_id=msgIDToEdit, text=couponOverviewText, parse_mode="HTML", disable_web_page_preview=True)
                    else:
                        # Send new post containing current page
                        msg = self.sendMessage(chat_id=chat_id, text=couponOverviewText, parse_mode="HTML", disable_web_page_preview=True,
                                                disable_notification=True)
                        if messageIDsForThisCategory is not None:
                            messageIDsForThisCategory.append(msg.message_id)
                        if infoDBDoc is not None:
                            # Update DB
                            infoDBDoc.store(infoDB)
            elif messageIDsForThisCategory is not None and len(messageIDsForThisCategory) > 0:
                """ Cleanup chat:
                Typically needed if a complete supported coupon type was there but is not existant anymore e.g. paper coupons were there but aren't existant anymore -> Delete old overview-message(s) """
                self.deleteMessages(chat_id=chat_id, messageIDs=messageIDsForThisCategory)
                if infoDBDoc is not None:
                    del infoDBDoc[dbKeyMessageIDsCouponType]
                    infoDBDoc.store(infoDB)
            else:
                # Rare case
                logging.info("Nothing to do: No coupons of this type available and no old ones to delete :)")

        pass

    def deleteMessages(self, chat_id: Union[int, str], messageIDs: Union[List[int], None]):
        """ Deletes array of messageIDs. """
        if messageIDs is None:
            return
        index = 0
        for msgID in messageIDs:
            logging.info("Deleting message " + str(index + 1) + " / " + str(len(messageIDs)) + " | " + str(msgID))
            self.deleteMessage(chat_id=chat_id, messageID=msgID)
            index += 1

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
                    waitseconds = 3
                    logging.info("Group send failed, waiting " + str(waitseconds) + " seconds | Try number: " + str(retryNumber))
                    time.sleep(3)
                    continue
                else:
                    raise requesterror
            except Unauthorized as wtf:
                logging.warning("User has blocked bot (?): " + str(chat_id))
                raise wtf
        raise lastException

    def deleteMessage(self, chat_id: Union[int, str], messageID: Union[int, None]):
        if messageID is None:
            return
        try:
            self.updater.bot.delete_message(chat_id=chat_id, message_id=messageID)
        except BadRequest:
            """ Typically this means that this message has already been deleted """
            logging.warning("Failed to delete message with message_id: " + str(messageID))


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
    if 'forcechannelupdate' in sys.argv:
        bkbot.updatePublicChannel()
        bkbot.cleanupPublicChannel()
    elif 'forcechannelupdatewithresend' in sys.argv:
        bkbot.renewPublicChannel()
        bkbot.cleanupPublicChannel()
    elif 'resumechannelupdate' in sys.argv:
        bkbot.resumePublicChannelUpdate()
        bkbot.cleanupPublicChannel()
    elif 'usernotify' in sys.argv:
        bkbot.notifyUsers()
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
    # schedule.every(10).seconds.do(bkbot.startBot)
    while True:
        schedule.run_pending()
        time.sleep(1)
