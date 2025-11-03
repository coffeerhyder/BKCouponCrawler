from datetime import datetime
from io import BytesIO
from typing import Union

from barcode.ean import EuropeanArticleNumber13
from barcode.writer import ImageWriter
from couchdb.mapping import Document, DictField, Mapping, BooleanField, IntegerField, TextField, DateTimeField, ListField, FloatField

from Helper import getCurrentDate
from utils.UtilsCouponsDB import MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION, USER_SETTINGS_ON_OFF, sortCouponsAsList, MAX_HOURS_ACTIVITY_TRACKING, MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION, \
    MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER, MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING
from utils.CouponViews import CouponViews, CouponView, getNextSortMode, getSortModeBySortCode, CouponSortMode
from utils.UserFavoritesInfo import UserFavoritesInfo
from models.Coupon import Coupon


class User(Document):
    settings = DictField(
        Mapping.build(
            displayCouponCategoryAllCouponsLongListWithLongTitles=BooleanField(default=False),
            displayCouponCategoryAppCouponsHidden=BooleanField(default=True),
            displayCouponCategoryMeatOnly=BooleanField(default=True),
            displayCouponCategoryVeggie=BooleanField(default=True),
            displayCouponCategoryKingDesMonats=BooleanField(default=True),
            displayCouponCategoryPayback=BooleanField(default=True),
            displayCouponSortButton=BooleanField(default=True),
            enableTerminalMode=BooleanField(default=False),
            displayOffersButton=BooleanField(default=True),
            displayBKWebsiteURLs=BooleanField(default=True),
            displayFeedbackCodeGenerator=BooleanField(default=True),
            displayFAQLinkButton=BooleanField(default=True),
            displayDonateButton=BooleanField(default=True),
            displayAdminButtons=BooleanField(default=True),
            displayPlantBasedCouponsWithinGenericCategories=BooleanField(default=True),
            displayHiddenUpsellingAppCouponsWithinGenericCategories=BooleanField(default=True),
            hideDuplicates=BooleanField(default=False),
            notifyWhenFavoritesAreBack=BooleanField(default=False),
            notifyWhenNewCouponsAreAvailable=BooleanField(default=False),
            notifyMeAsAdminIfThereAreProblems=BooleanField(default=True),
            notifyOnBotNewsletter=BooleanField(default=True),
            highlightFavoriteCouponsInButtonTexts=BooleanField(default=True),
            highlightNewCouponsInCouponButtonTexts=BooleanField(default=True),
            highlightVeggieCouponsInCouponButtonTexts=BooleanField(default=True),
            highlightChiliCheeseCouponsInCouponButtonTexts=BooleanField(default=True),
            displayQR=BooleanField(default=True),
            autoDeleteExpiredFavorites=BooleanField(default=False),
            enableBetaFeatures=BooleanField(default=False),
        )
    )
    botBlockedCounter = IntegerField(default=0)
    easterEggCounter = IntegerField(default=0)
    favoriteCoupons = DictField(default={})
    paybackCard = DictField(
        Mapping.build(
            paybackCardNumber=TextField(),
            addedDate=DateTimeField()
        ))
    couponViewSortModes = DictField(default={})
    pendingNotifications = ListField(TextField())
    # Rough timestamp when user user start commenad of bot last time -> Can be used to delete inactive users after X time
    timestampLastTimeBotUsed = FloatField(default=0)
    timestampLastTimeNotificationSentSuccessfully = FloatField(default=0)
    timesInformedAboutUpcomingAutoAccountDeletion = IntegerField(default=0)
    timestampLastTimeWarnedAboutUpcomingAutoAccountDeletion = IntegerField(default=0)
    timestampLastTimeBlockedBot = IntegerField(default=0)

    def hasProbablyBlockedBot(self) -> bool:
        if self.botBlockedCounter > 0:
            return True
        else:
            return False

    def hasProbablyBlockedBotForLongerTime(self) -> bool:
        if self.botBlockedCounter >= 30:
            return True
        else:
            return False

    def isEligableForAutoDeletion(self):
        """ If this returns True, upper handling is allowed to delete this account as it looks like it has been abandoned by the user. """
        if self.hasProbablyBlockedBotForLongerTime():
            return True
        elif self.getSecondsUntilAccountDeletion() == 0 and self.timesInformedAboutUpcomingAutoAccountDeletion >= MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION:
            # Looks like user hasn't used this bot for a loong time. Only allow this to return true if user has been warned enough times in beforehand.
            return True
        else:
            return False

    def hasDefaultSettings(self) -> bool:

        for settingKey, settingValue in self["settings"].items():
            settingInfo = USER_SETTINGS_ON_OFF.get(settingKey)
            if settingInfo is None:
                # Ignore keys that aren't covered in our settings map
                continue
            elif settingValue != settingInfo['default']:
                return False
        # Check for custom sort modes
        if self.hasStoredSortModes():
            # User has used/saved custom sort modes
            return False
        # No non-default value found -> User has default settings
        return True

    def hasStoredSortModes(self) -> bool:
        if self.couponViewSortModes is not None and len(self.couponViewSortModes) > 0:
            # User has saved preferred sort modes
            return True
        else:
            # User does not have any stored sort modes
            return False

    def hasFoundEasterEgg(self) -> bool:
        if self.easterEggCounter > 0:
            return True
        else:
            return False

    def isFavoriteCoupon(self, coupon: Coupon):
        """ Checks if given coupon is users' favorite """
        return self.isFavoriteCouponID(coupon.id)

    def isFavoriteCouponID(self, couponID: str):
        if couponID in self.favoriteCoupons:
            return True
        else:
            return False

    def addFavoriteCoupon(self, coupon: Coupon):
        self.favoriteCoupons[coupon.id] = coupon._data

    def deleteFavoriteCouponID(self, couponID: Union[str, Coupon]):
        if isinstance(couponID, Coupon):
            couponID = couponID.id
        del self.favoriteCoupons[couponID]

    def isAllowSendFavoritesNotification(self):
        if self.settings.autoDeleteExpiredFavorites:
            # User wants expired coupons to be auto-deleted so it is impossible to inform him about expired favourites that are back.
            return False
        elif self.settings.notifyWhenFavoritesAreBack:
            # User wants to be informed about expired favourite coupons that are back.
            return True
        else:
            # User does not want to be informed about expired favourite coupons that are back.
            return False

    def getPaybackCardNumber(self) -> Union[str, None]:
        """ Returns Payback card number of users' [first] Payback card. """
        """ Can this be considered a workaround or is the mapping made in a stupid way that it does not return "None" for keys without defined defaults??!
          doing User.paybackCard.paybackCardNumber directly would raise an AttributeError!
          Alternative would be to set empty String as default value. """
        if len(self.paybackCard) > 0:
            return self.paybackCard.paybackCardNumber
        else:
            return None

    def getPaybackCardImage(self) -> bytes:
        ean = EuropeanArticleNumber13(ean='240' + self.getPaybackCardNumber(), writer=ImageWriter())
        file = BytesIO()
        ean.write(file, options={'foreground': 'black'})
        return file.getvalue()

    def addPaybackCard(self, paybackCardNumber: str):
        if self.paybackCard is None or len(self.paybackCard) == 0:
            """ Workaround for Document bug/misbehavior. """
            self['paybackCard'] = {}
        self.paybackCard.paybackCardNumber = paybackCardNumber
        self.paybackCard.addedDate = datetime.now()

    def deletePaybackCard(self):
        """ Deletes users' [first] Payback card. """
        dummyUser = User()
        self.paybackCard = dummyUser.paybackCard

    def getUserFavoritesInfo(self, couponsFromDB: dict, returnSortedCoupons: bool) -> UserFavoritesInfo:
        """
        Gathers information about the given users' favorite available/unavailable coupons.
        Coupons from DB are required to get current dataset of available favorites.
        """
        if len(self.favoriteCoupons) == 0:
            # User does not have any favorites set --> There is no point to look for the additional information
            return UserFavoritesInfo()
        availableFavoriteCoupons = []
        unavailableFavoriteCoupons = []
        for uniqueCouponID, coupon in self.favoriteCoupons.items():
            couponFromProductiveDB = couponsFromDB.get(uniqueCouponID)
            if couponFromProductiveDB is not None and couponFromProductiveDB.isValid():
                availableFavoriteCoupons.append(couponFromProductiveDB)
            else:
                # User chosen favorite coupon has expired or is not in DB
                coupon = Coupon.wrap(coupon)  # We want a 'real' coupon object
                unavailableFavoriteCoupons.append(coupon)
        # Sort all coupon arrays by price
        if returnSortedCoupons:
            favoritesFilter = CouponViews.FAVORITES.getFilter()
            availableFavoriteCoupons = sortCouponsAsList(availableFavoriteCoupons, favoritesFilter.sortCode)
            unavailableFavoriteCoupons = sortCouponsAsList(unavailableFavoriteCoupons, favoritesFilter.sortCode)
        return UserFavoritesInfo(favoritesAvailable=availableFavoriteCoupons,
                                 favoritesUnavailable=unavailableFavoriteCoupons)

    def getSortModeForCouponView(self, couponView: CouponView) -> CouponSortMode:
        if self.couponViewSortModes is not None:
            # User has at least one custom sortCode for one CouponView.
            sortCode = self.couponViewSortModes.get(str(couponView.getViewCode()))
            if sortCode is not None:
                # User has saved SortMode for this CouponView.
                return getSortModeBySortCode(sortCode=sortCode)
            else:
                # User does not have saved SortMode for this CouponView --> Return default
                return getSortModeBySortCode(sortCode=couponView.couponfilter.sortCode)
        else:
            # User has no saved sortCode --> Return default
            return getSortModeBySortCode(sortCode=couponView.couponfilter.sortCode)

    def getNextSortModeForCouponView(self, couponView: CouponView) -> CouponSortMode:
        currentSortMode = self.getSortModeForCouponView(couponView=couponView)
        return getNextSortMode(currentSortMode=currentSortMode)

    def setCustomSortModeForCouponView(self, couponView: CouponView, sortMode: CouponSortMode):
        if self.couponViewSortModes is None or len(self.couponViewSortModes) == 0:
            """ Workaround for stupid Document bug/misbehavior. """
            self["couponViewSortModes"] = {}
            # self.couponViewSortModes = {} --> This does not work
        self.couponViewSortModes[str(couponView.getViewCode())] = sortMode.getSortCode()

    def hasRecentlyUsedBot(self) -> bool:
        if self.timestampLastTimeBotUsed == 0:
            # User has never used bot - this is nearly impossible unless user has been manually added to DB.
            return False
        else:
            currentTimestamp = getCurrentDate().timestamp()
            if currentTimestamp - self.timestampLastTimeBotUsed < MAX_HOURS_ACTIVITY_TRACKING * 60 * 60:
                return True
            else:
                return False

    def hasEverUsedBot(self) -> bool:
        """ Every user in DB should have used the bot at least once so this is kind of an ugly helper function which will return False
         if DB values do not match current DB activity values e.g. due to DB changes.
          Can especially be used to avoid sending account deletion notifications to users who are not eligable for auto account deletion. """
        if self.timestampLastTimeBotUsed > 0:
            return True
        elif self.timestampLastTimeNotificationSentSuccessfully > 0:
            return True
        elif len(self.favoriteCoupons) > 0:
            return True
        elif self.getPaybackCardNumber() is not None:
            return True
        else:
            return False

    def updateActivityTimestamp(self, force: bool = False) -> bool:
        if force or not self.hasRecentlyUsedBot():
            self.timestampLastTimeBotUsed = getCurrentDate().timestamp()
            # Reset this as user is active and is not about to be auto deleted
            self.timesInformedAboutUpcomingAutoAccountDeletion = 0
            # Reset this because user is using bot so it's obviously not blocked (anymore)
            self.botBlockedCounter = 0
            return True
        else:
            return False

    def hasRecentlyReceivedBotNotification(self) -> bool:
        if self.timestampLastTimeNotificationSentSuccessfully == 0:
            # User has never received notification from bot.
            return False
        else:
            currentTimestamp = getCurrentDate().timestamp()
            if currentTimestamp - self.timestampLastTimeNotificationSentSuccessfully < MAX_HOURS_ACTIVITY_TRACKING * 60 * 60:
                return True
            else:
                return False

    def updateNotificationReceivedActivityTimestamp(self, force: bool = False) -> bool:
        if force or not self.hasRecentlyReceivedBotNotification():
            self.timestampLastTimeNotificationSentSuccessfully = getCurrentDate().timestamp()
            # Reset this as user is active and is not about to be auto deleted
            self.timesInformedAboutUpcomingAutoAccountDeletion = 0
            # Reset this because user is using bot so it's obviously not blocked (anymore)
            self.botBlockedCounter = 0
            return True
        else:
            return False

    def getSecondsUntilAccountDeletion(self) -> float:
        secondsPassedSinceLastAccountActivity = self.getSecondsPassedSinceLastAccountActivity()
        if secondsPassedSinceLastAccountActivity > MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION:
            # Account can be deleted now
            return 0
        else:
            # Account can be deleted in X seconds
            return MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION - secondsPassedSinceLastAccountActivity

    def getSecondsPassedSinceLastAccountActivity(self) -> float:
        """ Returns smaller of these two values:
         - Seconds passed since user used bot last time
         - Seconds passed since bot sent user notification successfully last time
         """
        secondsPassedSinceLastUsage = self.getSecondsPassedSinceLastTimeUsed()
        secondsPassedSinceLastNotificationSentSuccessfully = self.getSecondsPassedSinceLastTimeNotificationSentSuccessfully()
        return min(secondsPassedSinceLastUsage, secondsPassedSinceLastNotificationSentSuccessfully)

    def getSecondsPassedSinceLastTimeUsed(self) -> float:
        return getCurrentDate().timestamp() - self.timestampLastTimeBotUsed

    def getSecondsPassedSinceLastTimeNotificationSentSuccessfully(self) -> float:
        return getCurrentDate().timestamp() - self.timestampLastTimeNotificationSentSuccessfully

    def allowWarningAboutUpcomingAutoAccountDeletion(self) -> bool:
        currentTimestampSeconds = getCurrentDate().timestamp()
        if currentTimestampSeconds + MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION - self.timestampLastTimeBotUsed <= MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER and currentTimestampSeconds - self.timestampLastTimeWarnedAboutUpcomingAutoAccountDeletion > MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING and self.timesInformedAboutUpcomingAutoAccountDeletion < MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION:
            return True
        else:
            return False

    def resetSettings(self):
        dummyUser = User()
        self.settings = dummyUser.settings
        self.couponViewSortModes = {}
