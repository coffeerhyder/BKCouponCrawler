import asyncio
import logging
from datetime import datetime
from enum import Enum

from couchdb import Database
from telegram import InputMediaPhoto

from BotUtils import getBotImpressum, Commands, ImageCache
from Helper import DATABASES, getCurrentDate, SYMBOLS, getFormattedPassedTime, URLs, BotAllowedCouponTypes, formatSeconds

from UtilsCouponsDB import User, ChannelCoupon, InfoEntry, CouponFilter, sortCouponsByPrice, getCouponTitleMapping, CouponSortModes, \
    MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER, MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING, MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION, \
    MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION

WAIT_SECONDS_AFTER_EACH_MESSAGE_OPERATION = 0
""" For testing purposes only!! """
DEBUGNOTIFICATOR = False


async def notifyUsersAboutNewCoupons(bkbot) -> None:
    """
    Notifies user about new coupons and users' expired favorite coupons that are back (well = also new coupons).
    """
    logging.info("Checking for pending new coupons notifications")
    timestampStart = datetime.now().timestamp()
    userDB = bkbot.crawler.getUserDB()
    allNewCoupons = bkbot.crawler.getFilteredCouponsAsDict(CouponFilter(activeOnly=True, isNew=True, allowedCouponTypes=BotAllowedCouponTypes, sortCode=CouponSortModes.PRICE.getSortCode()))
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
    logging.info('Computing new coupons\' notification messages...')
    for userIDStr in userDB:
        user = User.load(userDB, userIDStr)
        usertext = ""
        # Obey Telegram entity limits...
        remainingEntities = 50
        userNewFavoriteCoupons = {}
        # Check if user wants to be notified about favorites that are back
        if user.isAllowSendFavoritesNotification():
            # Collect users favorite coupons that are currently new --> Those ones are 'Favorites that are back'
            userFavoritesInfo = user.getUserFavoritesInfo(allNewCoupons, sortCoupons=True)
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
        logging.info(f"Auto updated favorites of {len(dbUserFavoritesUpdates)} users")
        userDB.update(list(dbUserFavoritesUpdates))
    logging.info(f"Notifying {len(usersNotify)} users about favorites/new coupons")
    position = 0
    for userIDStr, postText in usersNotify.items():
        position += 1
        logging.info("Sending user notification " + str(position) + "/" + str(len(usersNotify)) + " to user: " + userIDStr)
        user = User.load(userDB, userIDStr)
        await bkbot.sendMessageWithUserBlockedHandling(user=user, userDB=userDB, text=postText, parse_mode='HTML', disable_web_page_preview=True)
    logging.info("New coupons notifications done | Duration: " + getFormattedPassedTime(timestampStart))


async def notifyUsersAboutUpcomingAccountDeletion(bkbot) -> None:
    userDB = bkbot.crawler.getUserDB()
    numberOfMessagesSent = 0
    for userID in userDB:
        user = User.load(db=userDB, id=userID)
        currentTimestampSeconds = getCurrentDate().timestamp()
        secondsPassedSinceLastUsage = currentTimestampSeconds - user.timestampLastTimeAccountUsed
        secondsPassedSinceLastAccountDeletionWarning = currentTimestampSeconds - user.timestampLastTimeWarnedAboutUpcomingAutoAccountDeletion
        if secondsPassedSinceLastUsage >= MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER and secondsPassedSinceLastAccountDeletionWarning > MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING and user.timesInformedAboutUpcomingAutoAccountDeletion < MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION:
            secondsUntilAccountDeletion = user.getSecondsUntilAccountDeletion()
            text = f'{SYMBOLS.WARNING}<b>Achtung!</b>'
            text += f'\nDu hast diesen Bot seit ca. {formatSeconds(seconds=secondsPassedSinceLastUsage)} nicht mehr verwendet.'
            text += f'\nInaktive Accounts werden nach {formatSeconds(seconds=MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION)} automatisch gelöscht.'
            forceLastWarningText = False
            if secondsUntilAccountDeletion == 0:
                text += '\nDein BetterKing Account wird bei der nächsten Gelegenheit automatisch gelöscht.'
                forceLastWarningText = True
            else:
                text += f'\nDein BetterKing Account wird in {formatSeconds(seconds=secondsUntilAccountDeletion)} gelöscht!'
            user.timesInformedAboutUpcomingAutoAccountDeletion += 1
            user.timestampLastTimeWarnedAboutUpcomingAutoAccountDeletion = getCurrentDate().timestamp()
            if user.timesInformedAboutUpcomingAutoAccountDeletion >= MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION or forceLastWarningText:
                text += '\n<b>Dies ist die letzte Warnung!</b>'
            else:
                text += f'\nDies ist Warnung {user.timesInformedAboutUpcomingAutoAccountDeletion}/{MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION}.'
            text += '\nÖffne das Hauptmenü einmalig mit /start, um dem Bot zu zeigen, dass du noch lebst.'
            text += f'\nWahlweise kannst du deinen Account mit /{Commands.DELETE_ACCOUNT} selbst löschen.'
            await bkbot.sendMessageWithUserBlockedHandling(user=user, userDB=userDB, text=text, parse_mode='HTML', disable_web_page_preview=True)
            user.store(db=userDB)
            numberOfMessagesSent += 1
    logging.info('Number of users informed about account deletion: ' + str(numberOfMessagesSent))


class ChannelUpdateMode(Enum):
    """ Different modes that can be used to perform a channel update """
    RESEND_ALL = 1
    # This will only re-send all items older than X hours - can be used to resume channel update if it was e.g. interrupted due to a connection loss
    RESUME_CHANNEL_UPDATE = 2


async def updatePublicChannel(bkbot, updateMode: ChannelUpdateMode):
    """ Updates public channel if one is defined.
    Make sure to run cleanupChannel soon after excecuting this! """
    if bkbot.getPublicChannelName() is None:
        """ While it is not necessary to provide a name of a public channel for the bot to manage, this should not be called if not needed ... """
        raise Exception("You've called this function but bot.publicChannelName is undefined -> U stupid")
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
    activeCoupons = bkbot.crawler.getFilteredCouponsAsDict(CouponFilter(activeOnly=True, allowedCouponTypes=BotAllowedCouponTypes, sortCode=CouponSortModes.TYPE_MENU_PRICE.getSortCode()))
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
            if channelCoupon is None or datetime.now().timestamp() - channelCoupon.timestampMessagesPosted > 16 * 60 * 60:
                # Coupon has not been posted into channel yet or has been posted in there too long ago -> Add to list of coupons to re-send later
                couponsToSendOut[coupon.id] = coupon
    else:
        # This should never happen!
        logging.warning("Unsupported ChannelUpdateMode! Developer mistake?!")

    if numberOfCouponsNewToThisChannel != len(newCoupons):
        # During normal usage this should never happen
        logging.warning("Developer mistake or DB has been updated without sending channel update in between for at least 2 days: Number of 'new' coupons to send into channel is: " + str(numberOfCouponsNewToThisChannel) + " but should be: " + str(len(newCoupons)))
    if len(couponsToSendOut) > 0:
        # Send relevant coupons into chat
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
            if coupon.id not in channelDB:
                channelDB[coupon.id] = {}
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            channelCoupon.uniqueIdentifier = coupon.getUniqueIdentifier()
            couponText = coupon.generateCouponLongTextFormattedWithDescription(highlightIfNew=True)
            photoAlbum = [InputMediaPhoto(media=bkbot.getCouponImage(coupon), caption=couponText, parse_mode='HTML'),
                          InputMediaPhoto(media=bkbot.getCouponImageQR(coupon), caption=couponText, parse_mode='HTML')
                          ]
            logging.debug("Sending new coupon messages 1/2: Coupon photos")
            chatMessages = await asyncio.create_task(bkbot.sendMediaGroup(chat_id=bkbot.getPublicChannelChatID(), media=photoAlbum, disable_notification=True))

            msgImage = chatMessages[0]
            msgImageQR = chatMessages[1]
            # Update bot cache
            bkbot.couponImageCache[coupon.id] = ImageCache(fileID=msgImage.photo[0].file_id)
            bkbot.couponImageQRCache[coupon.id] = ImageCache(fileID=msgImageQR.photo[0].file_id)
            # Update our DB
            channelCoupon.channelMessageID_image = msgImage.message_id
            channelCoupon.channelMessageID_qr = msgImageQR.message_id
            # Update DB
            channelCoupon.store(channelDB)
            # Send coupon information as text (= last message for this coupon)
            logging.debug("Sending new coupon messages 2/2: Coupon text")
            couponTextMsg = await asyncio.create_task(bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=couponText, parse_mode='HTML', disable_notification=True,
                                              disable_web_page_preview=True))
            channelCoupon.channelMessageID_text = couponTextMsg.message_id
            # Save timestamp so we roughly know when these messages have been posted
            channelCoupon.timestampMessagesPosted = datetime.now().timestamp()
            # Update DB
            channelCoupon.store(channelDB)

    await bkbot.sendCouponOverviewWithChannelLinks(chat_id=bkbot.getPublicChannelChatID(), coupons=activeCoupons, useLongCouponTitles=False, channelDB=channelDB, infoDB=infoDB, infoDBDoc=infoDBDoc)

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
    infoText += '\n<b>------</b>'
    if DEBUGNOTIFICATOR:
        infoText += '\n<b>' + SYMBOLS.WARNING + 'Debug Modus!!!' + SYMBOLS.WARNING + '</b>'
    if bkbot.maintenanceMode:
        infoText += '\n<b>' + SYMBOLS.DENY + 'Wartungsmodus!' + SYMBOLS.DENY
        infoText += '\nDie Funktionalität von Bot/Channel kann derzeit nicht gewährleistet werden!'
        infoText += '\nFalls vorhanden, bitte die angepinnten Infos im Channel beachten.'
        infoText += '</b>'
    missingPaperCouponsText = bkbot.crawler.getMissingPaperCouponsText()
    if missingPaperCouponsText is not None:
        infoText += '\n<b>' + SYMBOLS.WARNING + 'Derzeit im Channel fehlende Papiercoupons: </b>' + missingPaperCouponsText
    infoText += "\nTechnisch bedingt werden die Coupons täglich erneut in diesen Channel geschickt."
    infoText += "\nStören dich die Benachrichtigungen?"
    infoText += "\nErstelle eine Verknüpfung: Drücke oben auf den Namen des Chats -> Rechts auf die drei Punkte -> Verknüpfung hinzufügen (funktioniert auch mit Bots)"
    infoText += "\nNun kannst du den Channel verlassen und ihn jederzeit wie eine App öffnen, ohne erneut beizutreten!"
    infoText += "\n... oder verwende <a href=\"https://t.me/" + bkbot.botName + "\">den Bot</a>."
    infoText += "\n<b>Der Bot kann außerdem deine Favoriten speichern, Coupons filtern und einiges mehr ;)</b>"
    infoText += "\nMöchtest du diesen Channel mit jemandem teilen, der kein Telegram verwendet?"
    infoText += "\nNimm <a href=\"https://t.me/s/" + bkbot.getPublicChannelName() + "\">diesen Link</a> oder <a href=\"" + URLs.ELEMENT + "\">Element per Matrix Bridge</a>."
    infoText += f"\nMehr Infos siehe <a href=\"{bkbot.getPublicChannelFAQLink()}\">FAQ</a>."
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
    newMsg = await asyncio.create_task(bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=infoText, parse_mode="HTML", disable_web_page_preview=True, disable_notification=True))
    # Store new messageID
    infoDBDoc.informationMessageID = newMsg.message_id
    infoDBDoc.store(infoDB)
    logging.info("Channel update done | Total time needed: " + getFormattedPassedTime(timestampStart))


async def cleanupChannel(bkbot):
    logging.info("Channel cleanup started")
    timestampStart = datetime.now().timestamp()
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    await deleteLeftoverMessageIDsToDelete(bkbot, infoDB, infoDoc)
    logging.info("Channel cleanup done | Total time needed: " + getFormattedPassedTime(timestampStart))


async def deleteLeftoverMessageIDsToDelete(bkbot, infoDB: Database, infoDoc) -> int:
    """ Deletes all channel messages which were previously flagged for deletion.
     @:returns Number of deleted messages
      """
    initialNumberofMsgsToDelete = len(infoDoc.messageIDsToDelete)
    logging.info(f"Deleting {initialNumberofMsgsToDelete} old messages...")
    if initialNumberofMsgsToDelete == 0:
        # Do nothing
        return 0
    index = 0
    for messageID in infoDoc.messageIDsToDelete:
        logging.info(f"Deleting messageID {index + 1}/{initialNumberofMsgsToDelete} | {messageID}")
        await asyncio.create_task(bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=messageID))
        index += 1
    # Update DB so we won't try to delete the same messages again next time
    infoDoc.messageIDsToDelete = []
    infoDoc.store(infoDB)
    return initialNumberofMsgsToDelete


async def nukeChannel(bkbot):
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
                await asyncio.create_task(bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=messageID))
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
            await asyncio.create_task(bkbot.deleteMessages(chat_id=bkbot.getPublicChannelChatID(), messageIDs=couponOverviewMessageIDs))
            infoDoc.deleteCouponCategoryMessageIDs(couponType)
            updateInfoDoc = True
    # Delete coupon information message
    if infoDoc.informationMessageID is not None:
        logging.info(f'Deleting channel overview message with ID {infoDoc.informationMessageID}')
        await asyncio.create_task(bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=infoDoc.informationMessageID))
        infoDoc.informationMessageID = None
        updateInfoDoc = True
    if updateInfoDoc:
        # Update DB if changes were made
        infoDoc.store(infoDB)
    await deleteLeftoverMessageIDsToDelete(bkbot, infoDB, infoDoc)

    logging.info("Cleanup channel DONE! --> Total time needed: " + getFormattedPassedTime(timestampStart))


# def editMessageAndWait(bkbot, messageID: Union[int, str, None], messageText) -> bool:
#     """ WRAPPER!
#      Edits a message from the channel and waits some seconds.
#      Ignores BadRequest Exceptions (e.g. message has already been deleted before). """
#     if messageID is None:
#         return False
#     try:
#         bkbot.editMessage(chat_id='@' + bkbot.getPublicChannelName(), message_id=messageID, text=messageText, parse_mode="HTML", disable_web_page_preview=True)
#         return True
#     except BadRequest:
#         """ Typically this means that this message does not exist anymore. """
#         logging.warning("Failed to edit message with message_id: " + str(messageID))
#         return False
#     finally:
#         time.sleep(WAIT_SECONDS_AFTER_EACH_MESSAGE_OPERATION * 3)
