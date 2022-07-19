import logging
import time
from datetime import datetime
from enum import Enum
from typing import Union

from telegram import InputMediaPhoto
from telegram.error import BadRequest, Unauthorized

from BotUtils import getBotImpressum
from Helper import DATABASES, getCurrentDate, SYMBOLS, getFormattedPassedTime, URLs, BotAllowedCouponTypes

from UtilsCouponsDB import User, ChannelCoupon, InfoEntry, CouponFilter, sortCouponsByPrice, getCouponTitleMapping, CouponSortModes

WAIT_SECONDS_AFTER_EACH_MESSAGE_OPERATION = 0
""" For testing purposes only!! """
DEBUGNOTIFICATOR = False


def notifyUsersAboutNewCoupons(bkbot) -> None:
    """
    Notifies user about new coupons and users' expired favorite coupons that are back (well = also new coupons).
    """
    logging.info("Checking for pending new coupons notifications")
    timestampStart = datetime.now().timestamp()
    userDB = bkbot.crawler.getUserDB()
    allNewCoupons = bkbot.crawler.getFilteredCoupons(CouponFilter(activeOnly=True, isNew=True, allowedCouponTypes=BotAllowedCouponTypes, sortMode=CouponSortModes.PRICE))
    if len(allNewCoupons) == 0:
        logging.info("No new coupons available to notify about")
        return

    couponTitleMappingTmp = getCouponTitleMapping(allNewCoupons)
    # Now clean our mapping: Sometimes one product may be available twice with multiple prices -> We want exactly one mapping per title
    couponTitleMapping = {}
    for normalizedTitle, coupons in couponTitleMappingTmp.items():
        if len(coupons) > 1:
            # Sort these ones by price and pick the first (= cheapest) one for our mapping.
            couponsSorted = sortCouponsByPrice(coupons)
            couponTitleMapping[normalizedTitle] = couponsSorted[0]
        else:
            couponTitleMapping[normalizedTitle] = coupons[0]
    dbUserFavoritesUpdates = set()
    usersNotify = {}
    numberofFavoriteNotifications = 0
    numberofNewCouponsNotifications = 0
    for userIDStr in userDB:
        user = User.load(userDB, userIDStr)
        usertext = ""
        # Obey Telegram entity limits...
        remainingEntities = 50
        userNewFavoriteCoupons = {}
        # Check if user wants to be notified about favorites that are back
        if user.isAllowSendFavoritesNotification():
            # Collect users favorite coupons that are currently new --> Those ones are 'Favorites that are back'
            userFavoritesInfo = user.getUserFavoritesInfo(allNewCoupons)
            for coupon in userFavoritesInfo.couponsAvailable:
                userNewFavoriteCoupons[coupon.id] = coupon
            """ Smart-update users favorites: Try to look for new coupons with the same product this was we can update users' favorite
             even if BK decided to change the price and/or ID of acoupon containing the same product(s). """
            # Collect titles of all unavailable favorites to set so we don't get any duplicates
            unavailableCouponNormalizedTitles = set()
            for unavailableCoupon in userFavoritesInfo.couponsUnavailable:
                unavailableCouponNormalizedTitles.add(unavailableCoupon.getNormalizedTitle())
            # Look for alternative coupon based on names of currently unavailable favorite coupons
            foundAtLeastOneAlternativeCoupon = False
            for unavailableCouponNormalizedTitle in unavailableCouponNormalizedTitles:
                alternativeCoupon = couponTitleMapping.get(unavailableCouponNormalizedTitle)
                if alternativeCoupon is not None:
                    # Hit! Add it to users' favorite coupons.
                    user.addFavoriteCoupon(alternativeCoupon)
                    userNewFavoriteCoupons[alternativeCoupon.id] = alternativeCoupon
                    foundAtLeastOneAlternativeCoupon = True
            if foundAtLeastOneAlternativeCoupon:
                # DB update required
                dbUserFavoritesUpdates.add(user)
            if len(userNewFavoriteCoupons) > 0:

                usertext += "<b>" + SYMBOLS.STAR + str(
                    len(userNewFavoriteCoupons)) + " deiner Favoriten sind wieder verfügbar:</b>" + bkbot.getNewCouponsTextWithChannelHyperlinks(userNewFavoriteCoupons, 49)
                numberofFavoriteNotifications += 1
                # The '<b>' entity is also one entity so let's substract this so we know how many are remaining
                remainingEntities -= 1
                remainingEntities -= len(userNewFavoriteCoupons)
        # Check if user has enabled notifications for new coupons
        if user.settings.notifyWhenNewCouponsAreAvailable:
            newCouponsListForThisUsersNotification = {}
            if user.isAllowSendFavoritesNotification() and len(userNewFavoriteCoupons) > 0:
                """ Avoid duplicates: If e.g. user has set favorite coupon to 'DoubleChiliCheese' and it's back in this run, we do not need to include it again in the list of new coupons.
                 If this dict is empty after the loop this means that all of this users' favorites would also be in the "new coupons" list thus no need to include them in the post we send to the user (= duplicates).
                 """
                for couponID in allNewCoupons:
                    if couponID not in userNewFavoriteCoupons:
                        newCouponsListForThisUsersNotification[couponID] = allNewCoupons[couponID]
            else:
                newCouponsListForThisUsersNotification = allNewCoupons
            if len(newCouponsListForThisUsersNotification) > 0:
                if len(usertext) == 0:
                    # '<b>' entity only counts as one even if there are multiple of those used in one post
                    remainingEntities -= 1
                else:
                    usertext += "\n---\n"
                usertext += "<b>" + SYMBOLS.NEW + str(len(newCouponsListForThisUsersNotification)) + " neue Coupons verfügbar:</b>" + bkbot.getNewCouponsTextWithChannelHyperlinks(newCouponsListForThisUsersNotification, 49)
                numberofNewCouponsNotifications += 1
                remainingEntities -= len(newCouponsListForThisUsersNotification)
        if len(usertext) > 0:
            # Complete user text and save it to send it later
            if bkbot.getPublicChannelName() is None:
                # Different text in case someone sets up this bot without a public channel (kinda makes no sense).
                usertext += "\nMit /start gelangst du ins Hauptmenü des Bots."
            else:
                usertext += "\nPer Klick gelangst du zu den jeweiligen Coupons im " + bkbot.getPublicChannelHyperlinkWithCustomizedText(
                    "Channel") + " und mit /start ins Hauptmenü des Bots."
            if remainingEntities < 0:
                usertext += "\n" + SYMBOLS.WARNING + "Wegen Telegram Limits konnten evtl. nicht alle Coupons verlinkt werden."
                usertext += "\nDas ist nicht weiter tragisch. Du findest alle Coupons im Bot/Channel."
            # Store text and send it later
            usersNotify[userIDStr] = usertext
    if len(usersNotify) == 0:
        logging.info("No users available who want to be notified on new coupons")
        return
    if len(dbUserFavoritesUpdates) > 0:
        logging.info("Auto updated favorites of " + str(len(dbUserFavoritesUpdates)) + " users")
        userDB.update(list(dbUserFavoritesUpdates))
    logging.info("Notifying " + str(len(usersNotify)) + " users about favorites/new coupons")
    index = -1
    dbUserUpdates = []
    # TODO: Update auto deletion handling
    for userIDStr, postText in usersNotify.items():
        index += 1
        # isLastItem = index == len(usersNotify) - 1
        logging.info("Sending user notification " + str(index + 1) + "/" + str(len(usersNotify)) + " to user: " + userIDStr)
        user = User.load(userDB, userIDStr)
        try:
            bkbot.sendMessage(chat_id=userIDStr, text=postText, parse_mode='HTML', disable_web_page_preview=True)
            if user.botBlockedCounter > 0:
                """ User had blocked but at some point of time but unblocked it --> Reset this counter so upper handling will not delete user at some point of time. """
                user.botBlockedCounter = 0
                dbUserUpdates.append(user)
        except Unauthorized as botBlocked:
            # Almost certainly it will be "Forbidden: bot was blocked by the user"
            logging.info(botBlocked.message + " --> chat_id: " + userIDStr)
            user.botBlockedCounter += 1
            dbUserUpdates.append(user)
    if len(dbUserUpdates) > 0:
        logging.info("Pushing DB updates for users who have blocked/unblocked bot: " + str(len(dbUserUpdates)))
        userDB.update(dbUserUpdates)
    logging.info("New coupons notifications done | Duration: " + getFormattedPassedTime(timestampStart))


class ChannelUpdateMode(Enum):
    """ Different modes that can be used to perform a channel update """
    RESEND_ALL = 1
    # This will only re-send all items older than X hours - can be used to resume channel update if it was e.g. interrupted due to a connection loss
    RESUME_CHANNEL_UPDATE = 2


def updatePublicChannel(bkbot, updateMode: ChannelUpdateMode):
    """ Updates public channel if one is defined.
    Make sure to run cleanupChannel soon after excecuting this! """
    if bkbot.getPublicChannelName() is None:
        """ While it is not necessary to provide a name of a public channel for the bot to manage, this should not be called if not needed ... """
        logging.info("You've called this function but self.publicChannelName is undefined -> U stupid?")
        return
    timestampStart = datetime.now().timestamp()
    logging.info("ChannelUpdateMode = " + updateMode.name)
    # Get last channel info from DB
    channelInfoDB = bkbot.couchdb[DATABASES.INFO_DB]
    channelInfoDoc = InfoEntry.load(channelInfoDB, DATABASES.INFO_DB)
    if channelInfoDoc.timestampLastChannelUpdate > -1:
        passedSeconds = getCurrentDate().timestamp() - channelInfoDoc.timestampLastChannelUpdate
        logging.info("Passed seconds since last channel update: " + str(passedSeconds))
    # Update channel info and DB
    channelInfoDoc.timestampLastChannelUpdate = getCurrentDate().timestamp()
    channelInfoDoc.store(channelInfoDB)
    activeCoupons = bkbot.crawler.getFilteredCoupons(CouponFilter(activeOnly=True, allowedCouponTypes=BotAllowedCouponTypes, sortMode=CouponSortModes.TYPE_MENU_PRICE))
    channelDB = bkbot.couchdb[DATABASES.TELEGRAM_CHANNEL]
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDBDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    # All coupons we want to send out this run
    couponsToSendOut = {}
    # All new coupons
    newCoupons = {}
    numberOfCouponsNewToThisChannel = 0
    updatedCoupons = {}
    # Collect new and updated items
    for coupon in activeCoupons.values():
        if coupon.id not in channelDB:
            # New coupon - save information into both dicts
            couponsToSendOut[coupon.id] = coupon
            if coupon.isNewCoupon():
                newCoupons[coupon.id] = coupon
            numberOfCouponsNewToThisChannel += 1
        elif ChannelCoupon.load(channelDB, coupon.id).uniqueIdentifier != coupon.getUniqueIdentifier():
            # Current/new coupon data differs from coupon we've posted in channel (same unique ID but coupon data has changed)
            updatedCoupons[coupon.id] = coupon
    if len(infoDBDoc.messageIDsToDelete) > 0:
        # This can happen but should only be a rare occurance!
        logging.warning("Found " + str(len(infoDBDoc.messageIDsToDelete)) + " leftover messageIDs to delete")
    # Collect deleted coupons from channel
    deletedChannelCoupons = []
    for uniqueCouponID in channelDB:
        if uniqueCouponID not in activeCoupons:
            channelCoupon = ChannelCoupon.load(channelDB, uniqueCouponID)
            infoDBDoc.addMessageIDsToDelete(channelCoupon.getMessageIDs())
            # Collect it here so we can delete it with only one DB request later.
            deletedChannelCoupons.append(channelCoupon)
    # Update DB if needed
    if len(deletedChannelCoupons) > 0:
        channelDB.purge(deletedChannelCoupons)
        # Save this so we always remember which messageIDs we need to delete later.
        infoDBDoc.store(infoDB)
    # Collect coupons to send out in this run.
    if updateMode == ChannelUpdateMode.RESEND_ALL:
        couponsToSendOut = activeCoupons
    elif updateMode == ChannelUpdateMode.RESUME_CHANNEL_UPDATE:
        # Collect all coupons that haven't been sent into the channel at all or were sent into the channel more than X seconds ago (= "old" entries)
        for coupon in activeCoupons.values():
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            if channelCoupon is None or datetime.now().timestamp() - channelCoupon.timestampMessagesPosted > 6 * 60 * 60:
                # Coupon has not been posted into channel yet or has been posted in there too long ago -> Add to list of coupons to re-send later
                couponsToSendOut[coupon.id] = coupon
    else:
        logging.warning("Unsupported ChannelUpdateMode! Developer mistake?!")

    if numberOfCouponsNewToThisChannel != len(newCoupons):
        # During normal usage this should never happen
        logging.warning("Developer mistake or DB has been updated without sending channel update in between for at least 2 days: Number of 'new' coupons to send into channel is: " + str(numberOfCouponsNewToThisChannel) + " but should be: " + str(len(newCoupons)))
    # Send relevant coupons into chat
    if len(couponsToSendOut) > 0:
        logging.info("Sending out " + str(len(couponsToSendOut)) + " coupons...")
        # Collect all old messageIDs which need to be deleted by checking which of the ones we want to send out are already in our channel at this moment
        channelCouponDBUpdates = []
        for coupon in couponsToSendOut.values():
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            if channelCoupon is not None and len(channelCoupon.getMessageIDs()) > 0:
                infoDBDoc.addMessageIDsToDelete(channelCoupon.getMessageIDs())
                channelCoupon.deleteMessageIDs()
                channelCouponDBUpdates.append(channelCoupon)
        # Update DB
        if len(channelCouponDBUpdates) > 0:
            channelDB.update(channelCouponDBUpdates)
            infoDBDoc.store(infoDB)

        index = -1
        for coupon in couponsToSendOut.values():
            if DEBUGNOTIFICATOR:
                break
            index += 1
            logging.info("Working on coupon " + str(index + 1) + "/" + str(len(couponsToSendOut)) + " | " + coupon.id)
            # Check for missing images: This can only ever happen if they get deleted from the outside at exactly the wrong point of time.
            if bkbot.getCouponImage(coupon) is None:
                # This should never happen
                raise Exception("WTF failed to find coupon image for coupon " + coupon.id)
            elif bkbot.getCouponImageQR(coupon) is None:
                # This should never happen
                raise Exception("WTF failed to find QR image for coupon " + coupon.id)
            if coupon.id not in channelDB:
                channelDB[coupon.id] = {}
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            channelCoupon.uniqueIdentifier = coupon.getUniqueIdentifier()
            couponText = coupon.generateCouponLongTextFormattedWithDescription(highlightIfNew=True)
            photoAlbum = [InputMediaPhoto(media=bkbot.getCouponImage(coupon), caption=couponText, parse_mode='HTML'),
                          InputMediaPhoto(media=bkbot.getCouponImageQR(coupon), caption=couponText, parse_mode='HTML')
                          ]
            logging.debug("Sending new coupon messages 1/2: Coupon photos")
            chatMessages = bkbot.sendMediaGroup(chat_id=bkbot.getPublicChannelChatID(), media=photoAlbum, disable_notification=True)
            channelCoupon.channelMessageID_image = chatMessages[0].message_id
            channelCoupon.channelMessageID_qr = chatMessages[1].message_id
            # Update DB
            channelCoupon.store(channelDB)
            # Send coupon information as text (= last message for this coupon)
            logging.debug("Sending new coupon messages 2/2: Coupon text")
            couponTextMsg = bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=couponText, parse_mode='HTML', disable_notification=True,
                                              disable_web_page_preview=True)
            channelCoupon.channelMessageID_text = couponTextMsg.message_id
            # Save timestamp so we roughly know when these messages have been posted
            channelCoupon.timestampMessagesPosted = datetime.now().timestamp()
            # Update DB
            channelCoupon.store(channelDB)

    bkbot.sendCouponOverviewWithChannelLinks(chat_id=bkbot.getPublicChannelChatID(), coupons=activeCoupons, useLongCouponTitles=False, channelDB=channelDB, infoDB=infoDB, infoDBDoc=infoDBDoc)

    """ Generate new information message text. """
    infoText = '<b>Heutiges Update:</b>'
    if len(deletedChannelCoupons) > 0:
        infoText += '\n' + SYMBOLS.DENY + ' ' + str(len(deletedChannelCoupons)) + ' Coupons gelöscht'
    if len(updatedCoupons) > 0:
        infoText += '\n' + SYMBOLS.ARROW_UP_RIGHT + ' ' + str(len(updatedCoupons)) + ' Coupons aktualisiert'
    if len(newCoupons) > 0:
        # Add detailed information about added coupons. Limit the max. number of that so our information message doesn't get too big.
        infoText += '\n<b>' + SYMBOLS.NEW + ' ' + str(len(newCoupons)) + ' Coupons hinzugefügt:</b>'
        infoText += bkbot.getNewCouponsTextWithChannelHyperlinks(newCoupons, 10)
    infoText += '\n' + SYMBOLS.WRENCH + ' Alle ' + str(len(activeCoupons)) + ' Coupons erneut in die Gruppe gesendet'
    if DEBUGNOTIFICATOR:
        infoText += '\n<b>' + SYMBOLS.WARNING + 'Debug Modus!!!' + SYMBOLS.WARNING + '</b>'
    if bkbot.maintenanceMode:
        infoText += '\n<b>' + SYMBOLS.DENY + 'Wartungsmodus!' + SYMBOLS.DENY
        infoText += '\nDie Funktionalität von Bot/Channel kann derzeit nicht gewährleistet werden!'
        infoText += '\nFalls vorhanden, bitte die angepinnten Infos im Channel beachten.'
        infoText += '</b>'
    missingPaperCouponsText = bkbot.crawler.getMissingPaperCouponsText()
    if missingPaperCouponsText is not None:
        infoText += '\n<b>'
        infoText += SYMBOLS.WARNING + 'Derzeit im Channel fehlende Papiercoupons: ' + missingPaperCouponsText
        infoText += '\nVollständige Papiercouponbögen sind im angepinnten FAQ verlinkt.'
        infoText += '</b>'
    # Add 'useful links text'
    infoText += '\n<b>------</b>'
    infoText += '\n<b>Nützliche Links</b>:'
    infoText += '\n<b>BK</b>:'
    infoText += '\n•<a href=\"' + URLs.BK_SPAR_KINGS + '\">Spar Kings</a>'
    infoText += '\n•<a href=\"' + URLs.BK_KING_FINDER + '\">KING Finder</a>'
    infoText += '\n•<a href=\"' + URLs.NGB_FORUM_THREAD + '\">ngb.to BetterKing Forum Thread</a>'
    infoText += '\n•<a href=\"' + URLs.BK_WUERGER_KING + '\">Würger King</a> (' + '<a href=\"' + URLs.BK_WUERGER_KING_SOURCE + '\">source</a>' + ')'
    infoText += '\n<b>McDonalds</b>'
    infoText += '\n•<a href=\"' + URLs.MCD_MCCOUPON_DEALS + '\">mccoupon.deals</a>'
    infoText += '\n•<a href=\"' + URLs.MCD_COCKBOT + '\">t.me/gimmecockbot</a>'
    infoText += '\n<b>------</b>'
    infoText += "\nTechnisch bedingt werden die Coupons täglich erneut in diesen Channel geschickt."
    infoText += "\nStören dich die Benachrichtigungen?"
    infoText += "\nErstelle eine Verknüpfung: Drücke oben auf den Namen des Chats -> Rechts auf die drei Punkte -> Verknüpfung hinzufügen (funktioniert auch mit Bots)"
    infoText += "\nNun kannst du den Channel verlassen und ihn jederzeit wie eine App öffnen, ohne erneut beizutreten!"
    infoText += "\n... oder verwende <a href=\"https://t.me/" + bkbot.botName + "\">den Bot</a>."
    infoText += "\n<b>Der Bot kann außerdem deine Favoriten speichern, Coupons filtern und einiges mehr ;)</b>"
    infoText += "\nMöchtest du diesen Channel mit jemandem teilen, der kein Telegram verwendet?"
    infoText += "\nNimm <a href=\"https://t.me/s/" + bkbot.getPublicChannelName() + "\">diesen Link</a> oder <a href=\"" + URLs.ELEMENT + "\">Element per Matrix Bridge</a>."
    infoText += "\n<b>Guten Hunger!</b>"
    infoText += "\n" + getBotImpressum()
    """ 
    Did we only delete coupons and/or update existing ones while there were no new coupons coming in AND we were not forced to delete- and re-send all items?
    Edit our last message if existant so the user won't receive a new notification!
    """
    oldInfoMsgID = infoDBDoc.informationMessageID
    # Post new message and store old for later deletion
    if oldInfoMsgID is not None:
        infoDBDoc.messageIDsToDelete.append(oldInfoMsgID)
    newMsg = bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=infoText, parse_mode="HTML", disable_web_page_preview=True, disable_notification=True)
    # Store new messageID
    infoDBDoc.informationMessageID = newMsg.message_id
    infoDBDoc.store(infoDB)
    logging.info("Channel update done | Total time needed: " + getFormattedPassedTime(timestampStart))


def cleanupChannel(bkbot):
    logging.info("Channel cleanup started")
    timestampStart = datetime.now().timestamp()
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    deleteLeftoverMessageIDsToDelete(bkbot, infoDB, infoDoc)
    logging.info("Channel cleanup done | Total time needed: " + getFormattedPassedTime(timestampStart))


def deleteLeftoverMessageIDsToDelete(bkbot, infoDB, infoDoc) -> int:
    """ Deletes all channel messages which were previously flagged for deletion.
     @:returns Number of deleted messages
      """
    if len(infoDoc.messageIDsToDelete) > 0:
        initialNumberofMsgsToDelete = len(infoDoc.messageIDsToDelete)
        logging.info("Deleting " + str(initialNumberofMsgsToDelete) + " old messages...")
        index = 0
        for messageID in infoDoc.messageIDsToDelete[:]:
            logging.info("Deleting messageID " + str(index + 1) + "/" + str(initialNumberofMsgsToDelete) + " | " + str(messageID))
            bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=messageID)
            infoDoc.messageIDsToDelete.remove(messageID)
            index += 1
        # Update DB
        infoDoc.store(infoDB)
        return initialNumberofMsgsToDelete
    else:
        return 0


def nukeChannel(bkbot):
    """ This will simply delete all message in the TG channel. """
    timestampStart = datetime.now().timestamp()
    logging.info("Nuking channel...")
    channelDB = bkbot.couchdb[DATABASES.TELEGRAM_CHANNEL]
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    if len(channelDB) > 0:
        # Delete all coupons that are currently posted in our channel
        logging.info("Deleting " + str(len(channelDB)) + " coupons...")
        index = 0
        initialItemNumber = len(channelDB)
        for couponID in channelDB:
            index += 1
            logging.info("Working on coupon " + str(index) + "/" + str(initialItemNumber))
            channelCoupon = ChannelCoupon.load(channelDB, couponID)
            messageIDs = channelCoupon.getMessageIDs()
            for messageID in messageIDs:
                bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=messageID)
            del channelDB[couponID]
    # Delete coupon overview messages
    updateInfoDoc = False
    hasLoggedDeletionOfCouponOverviewMessageIDs = False
    for couponType in BotAllowedCouponTypes:
        couponOverviewMessageIDs = infoDoc.getMessageIDsForCouponCategory(couponType)
        if len(couponOverviewMessageIDs) > 0:
            if not hasLoggedDeletionOfCouponOverviewMessageIDs:
                # Only print this logger once
                logging.info("Deleting information messages...")
                hasLoggedDeletionOfCouponOverviewMessageIDs = True
            bkbot.deleteMessages(chat_id=bkbot.getPublicChannelChatID(), messageIDs=couponOverviewMessageIDs)
            infoDoc.deleteCouponCategoryMessageIDs(couponType)
            updateInfoDoc = True
    # Delete coupon information message
    if infoDoc.informationMessageID is not None:
        logging.info("Deleting channel overview message: " + infoDoc.informationMessageID)
        bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=infoDoc.informationMessageID)
        infoDoc.informationMessageID = None
        updateInfoDoc = True
    if updateInfoDoc:
        # Update DB if changes were made
        infoDoc.store(infoDB)
    deleteLeftoverMessageIDsToDelete(bkbot, infoDB, infoDoc)

    logging.info("Cleanup channel DONE! --> Total time needed: " + getFormattedPassedTime(timestampStart))


def editMessageAndWait(bkbot, messageID: Union[int, str, None], messageText) -> bool:
    """ WRAPPER!
     Edits a message from the channel and waits some seconds.
     Ignores BadRequest Exceptions (e.g. message has already been deleted before). """
    if messageID is None:
        return False
    try:
        bkbot.editMessage(chat_id='@' + bkbot.getPublicChannelName(), message_id=messageID, text=messageText, parse_mode="HTML", disable_web_page_preview=True)
        return True
    except BadRequest:
        """ Typically this means that this message does not exist anymore. """
        logging.warning("Failed to edit message with message_id: " + str(messageID))
        return False
    finally:
        time.sleep(WAIT_SECONDS_AFTER_EACH_MESSAGE_OPERATION * 3)
