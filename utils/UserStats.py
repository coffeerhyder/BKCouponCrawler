from couchdb import Database

from models.User import User


class UserStats:
    """ Returns an object containing statistic data about given users Database instance. """

    def __init__(self, userdb: Database):
        self.numberofUsersTotal = len(userdb)
        self.numberofUsersWhoFoundEasterEgg = 0
        self.numberofFavorites = 0
        self.numberofUsersWhoProbablyBlockedBot = 0
        self.numberofUsersWhoAreEligableForAutoDeletion = 0
        self.numberofUsersWhoRecentlyUsedBot = 0
        self.numberofUsersWhoAddedPaybackCard = 0
        self.numberofUsersWhoEnabledBotNewsletter = 0
        self.numberofUsersWhoDisabledDonateButton = 0
        for userID in userdb:
            user: User = User.load(userdb, userID)
            if user.hasFoundEasterEgg():
                self.numberofUsersWhoFoundEasterEgg += 1
            self.numberofFavorites += len(user.favoriteCoupons)
            if user.hasProbablyBlockedBot():
                self.numberofUsersWhoProbablyBlockedBot += 1
            if user.getPaybackCardNumber() is not None:
                self.numberofUsersWhoAddedPaybackCard += 1
            if user.isEligableForAutoDeletion():
                self.numberofUsersWhoAreEligableForAutoDeletion += 1
            elif user.hasRecentlyUsedBot():
                self.numberofUsersWhoRecentlyUsedBot += 1
            if user.settings.notifyOnBotNewsletter:
                self.numberofUsersWhoEnabledBotNewsletter += 1
            if user.settings.displayDonateButton is False:
                self.numberofUsersWhoDisabledDonateButton += 1
