import asyncio
import logging
from datetime import datetime
from enum import Enum

from couchdb import Database
from telegram import InputMediaPhoto

from BotUtils import getBotImpressum, Commands, ImageCache
from Helper import DATABASES, getCurrentDate, SYMBOLS, getFormattedPassedTime, URLs, BotAllowedCouponTypes, formatSeconds, formatDateGermanHuman, TEXT_NOTIFICATION_DISABLE

from UtilsCouponsDB import User, ChannelCoupon, InfoEntry, CouponFilter, sortCouponsByPrice, getCouponTitleMapping, CouponSortModes, \
    MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER, MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING, MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION, \
    MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION

""" For testing purposes only!! """
# TODO: Remove this, add parameter handling so that no code changes are needed for this debug switch.
DEBUGNOTIFICATOR = False


async def collectNewCouponsNotifications(bkbot) -> None:
    """
    Collects user notifications regarding new coupons and adds them to user document so they can be sent out later.
    """
    logging.info("Checking for pending new coupons notifications")
    timeStart = datetime.now()
    newCoupons = bkbot.crawler.getFilteredCouponsAsDict(CouponFilter(activeOnly=True, isNew=True, sortCode=CouponSortModes.PRICE.getSortCode()))
    if len(newCoupons) == 0:
        logging.info("No new coupons available to notify users about")
        return
    userDB = bkbot.userdb
    """ 
     Build a mapping of normalized coupon titles to coupons.
     This way we can easily find alternatives to users' expired coupons (e.g. when BK decides to raise prices for the same product again).
     """
    couponTitleMappingTmp = getCouponTitleMapping(newCoupons)
    # Now clean our mapping: Sometimes one product may be available twice with multiple prices -> We want exactly one mapping per title
    couponTitleMapping = {}
    for normalizedTitle, coupons in couponTitleMappingTmp.items():
        if len(coupons) > 1:
            # Sort these ones by price and pick the first (= cheapest) one for our mapping.
            couponsSorted = sortCouponsByPrice(coupons)
            couponTitleMapping[normalizedTitle] = couponsSorted[0]
        else:
            couponTitleMapping[normalizedTitle] = coupons[0]
    """ 
     Now compute all messages for all users to when sending out the messages we can have a nice progress log output.
     """
    # List of user documents that were changed and need to be pushed to DB
    dbUserUpdateList = set()
    separator = '---'

    numberofFavoriteNotifications = 0
    logging.info('Computing new coupons\' notification messages...')
    for userIDStr in userDB:
        user = User.load(userDB, userIDStr)
        notificationtext = ""
        userNewFavoriteCoupons = {}
        # Check if user wants to be notified about favorites that are back
        updateUserDoc = False
        if user.isAllowSendFavoritesNotification():
            # Collect users favorite coupons that are currently new --> Those ones are 'Favorites that are back'
            userFavoritesInfo = user.getUserFavoritesInfo(newCoupons, returnSortedCoupons=True)
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
                updateUserDoc = True
            if len(userNewFavoriteCoupons) > 0:
                notificationtext += "<b>" + SYMBOLS.STAR + str(
                    len(userNewFavoriteCoupons)) + " deiner Favoriten sind wieder verfügbar:</b>" + bkbot.getNewCouponsTextWithChannelHyperlinks(userNewFavoriteCoupons, 49)
                numberofFavoriteNotifications += 1
        # Check if user has enabled notifications for new coupons
        if user.settings.notifyWhenNewCouponsAreAvailable:
            newCouponsListForThisUsersNotification = {}
            if user.isAllowSendFavoritesNotification() and len(userNewFavoriteCoupons) > 0:
                """ Avoid duplicates: If e.g. user has set favorite coupon to 'DoubleChiliCheese' and it's back in this run, we do not need to include it again in the list of new coupons.
                 If this dict is empty after the loop this means that all of this users' favorites would also be in the "new coupons" list thus no need to include them in the post we send to the user (= duplicates).
                 """
                for couponID in newCoupons:
                    if couponID not in userNewFavoriteCoupons:
                        newCouponsListForThisUsersNotification[couponID] = newCoupons[couponID]
            else:
                newCouponsListForThisUsersNotification = newCoupons
            if len(newCouponsListForThisUsersNotification) > 0:
                if len(notificationtext) > 0:
                    notificationtext += f"\n{separator}\n"
                notificationtext += "<b>" + SYMBOLS.NEW + str(
                    len(newCouponsListForThisUsersNotification)) + " neue Coupons verfügbar:</b>" + bkbot.getNewCouponsTextWithChannelHyperlinks(
                    newCouponsListForThisUsersNotification, 49)
        if len(notificationtext) > 0:
            notificationtext += f"\n{separator}"
            # Complete user text and save it to send it later
            if bkbot.getPublicChannelName() is None:
                # Different text in case someone sets up this bot without a public channel (kinda makes no sense).
                notificationtext += "\nMit /start gelangst du ins Hauptmenü des Bots."
            else:
                notificationtext += f"\nPer Klick gelangst du zu den jeweiligen Coupons im {bkbot.getPublicChannelHyperlinkWithCustomizedText('Channel')} und mit /start ins Hauptmenü des Bots."
            notificationtext += "\n" + TEXT_NOTIFICATION_DISABLE
            if notificationtext not in user.pendingNotifications:
                # Add notification text if it is not already contained in list of pending notifications
                joinedlist = user.pendingNotifications + [notificationtext]
                user.pendingNotifications = joinedlist
                updateUserDoc = True
        if updateUserDoc:
            dbUserUpdateList.add(user)
    if len(dbUserUpdateList) == 0:
        logging.info("Did not collect any new notifications to send out")
        return
    logging.info(f"Pushing DB update of {len(dbUserUpdateList)} user documents")
    userDB.update(list(dbUserUpdateList))
    logging.info(f"New coupons notifications collector done | Duration: {(datetime.now() - timeStart)}")


async def collectUserDeleteNotifications(bkbot) -> None:
    userDB = bkbot.userdb
    numberOfCollectedNotifications = 0
    for userID in userDB:
        user = User.load(db=userDB, id=userID)
        if not user.hasEverUsedBot():
            """ 
            Avoid sending such notifications to users whose datasets are not up2date.
            """
            continue
        secondsPassedSinceLastAccountActivity = user.getSecondsPassedSinceLastAccountActivity()
        secondsPassedSinceLastAccountDeletionWarning = getCurrentDate().timestamp() - user.timestampLastTimeWarnedAboutUpcomingAutoAccountDeletion
        if secondsPassedSinceLastAccountActivity >= MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER and secondsPassedSinceLastAccountDeletionWarning > MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING and user.timesInformedAboutUpcomingAutoAccountDeletion < MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION:
            secondsUntilAccountDeletion = user.getSecondsUntilAccountDeletion()
            text = f'{SYMBOLS.WARNING}<b>Achtung!</b>'
            text += f'\nDu hast diesen Bot seit ca. {formatSeconds(seconds=secondsPassedSinceLastAccountActivity)} nicht mehr verwendet und keine Benachrichtigungen von ihm erhalten.'
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
            if text not in user.pendingNotifications:
                notificationlist = user.pendingNotifications + [text]
                user.pendingNotifications = notificationlist
            user.store(db=userDB)
            numberOfCollectedNotifications += 1
    logging.info('Number of users who will soon be informed about account deletion: ' + str(numberOfCollectedNotifications))


async def notifyAdminsAboutProblems(bkbot) -> None:
    adminIDs = bkbot.cfg.admin_ids
    if adminIDs is None or len(adminIDs) == 0:
        # There are no admins
        return
    infoDatabase = bkbot.crawler.getInfoDB()
    infoDBDoc = InfoEntry.load(infoDatabase, DATABASES.INFO_DB)
    timedeltaLastSuccessfulRun = datetime.now() - infoDBDoc.dateLastSuccessfulCrawlRun if infoDBDoc.dateLastSuccessfulCrawlRun is not None else None
    timedeltaLastSuccessfulChannelupdate = datetime.now() - infoDBDoc.dateLastSuccessfulChannelUpdate if infoDBDoc.dateLastSuccessfulChannelUpdate is not None else None
    text = ''
    if timedeltaLastSuccessfulRun is not None and timedeltaLastSuccessfulRun.seconds > 48 * 60 * 60:
        text += f'{SYMBOLS.WARNING} Letzter erfolgreicher Crawlvorgang war am {formatDateGermanHuman(infoDBDoc.dateLastSuccessfulCrawlRun)}'
    if timedeltaLastSuccessfulChannelupdate is not None and timedeltaLastSuccessfulChannelupdate.seconds > 48 * 60 * 60:
        text += f'\n{SYMBOLS.WARNING} Letztes erfolgreiches Channelupdate war am {formatDateGermanHuman(infoDBDoc.dateLastSuccessfulChannelUpdate)}'
    if len(text) == 0:
        # No notifications to send out
        return
    userDB = bkbot.userdb
    adminUsersToNotify = []
    for adminID in adminIDs:
        adminUser = User.load(userDB, adminID)
        if adminUser is not None and adminUser.settings.notifyMeAsAdminIfThereAreProblems:
            adminUsersToNotify.append(adminUser)
    if len(adminUsersToNotify) == 0:
        logging.info("There are no admins that want to be notified")
        return
    for adminUser in adminUsersToNotify:
        await bkbot.sendMessageWithUserBlockedHandling(user=adminUser, userDB=userDB, text=text, parse_mode='HTML', disable_web_page_preview=True)


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
    dateStart = datetime.now()
    logging.info("ChannelUpdateMode = " + updateMode.name)
    # Get last channel info from DB
    infoDB = bkbot.crawler.getInfoDB()
    infoDBDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    if infoDBDoc.dateLastSuccessfulChannelUpdate is not None:
        passedSeconds = (datetime.now() - infoDBDoc.dateLastSuccessfulChannelUpdate).total_seconds()
        logging.info("Passed seconds since last channel update: " + str(passedSeconds))
    activeCoupons = bkbot.crawler.getFilteredCouponsAsDict(
        CouponFilter(activeOnly=True, allowedCouponTypes=BotAllowedCouponTypes, sortCode=CouponSortModes.TYPE_MENU_PRICE.getSortCode()))
    channelDB = bkbot.couchdb[DATABASES.TELEGRAM_CHANNEL]
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
        logging.warning(f"Found {len(infoDBDoc.messageIDsToDelete)} leftover messageIDs to delete")
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
    else:
        # ChannelUpdateMode.RESUME_CHANNEL_UPDATE
        # Collect all coupons that haven't been sent into the channel at all or were sent into the channel more than X seconds ago (= "old" entries)
        allFromNowOn = False
        for coupon in activeCoupons.values():
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            if allFromNowOn or channelCoupon is None or channelCoupon.channelMessageID_image_and_qr_date_posted is None or (
                    datetime.now() - channelCoupon.channelMessageID_image_and_qr_date_posted).total_seconds() > 16 * 60 * 60 or channelCoupon.channelMessageID_text_date_posted is None or (
                    datetime.now() - channelCoupon.channelMessageID_text_date_posted).total_seconds() > 16 * 60 * 60:
                # Coupon has not been posted into channel yet or has been posted in there too long ago -> Add to list of coupons to re-send later
                couponsToSendOut[coupon.id] = coupon
                # One coupon was missing/incomplete? Re-send all after this one.
                allFromNowOn = True

    if numberOfCouponsNewToThisChannel != len(newCoupons):
        # During normal usage this should never happen
        logging.warning(
            "Developer mistake or DB has been updated without sending channel update in between for at least 2 days: Number of 'new' coupons to send into channel is: " + str(
                numberOfCouponsNewToThisChannel) + " but should be: " + str(len(newCoupons)))
    if len(couponsToSendOut) > 0:
        # Send relevant coupons into chat
        logging.info(f"Sending out {len(couponsToSendOut)}/{len(activeCoupons)} coupons...")
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
            # Update DB
            if coupon.id not in channelDB:
                channelDB[coupon.id] = {}
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            channelCoupon.uniqueIdentifier = coupon.getUniqueIdentifier()
            channelCoupon.channelMessageID_image = msgImage.message_id
            channelCoupon.channelMessageID_qr = msgImageQR.message_id
            channelCoupon.channelMessageID_image_and_qr_date_posted = datetime.now()
            # Update DB
            channelCoupon.store(channelDB)
            # Send coupon information as text (= last message for this coupon)
            logging.debug("Sending new coupon messages 2/2: Coupon text")
            couponTextMsg = await asyncio.create_task(bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=couponText, parse_mode='HTML', disable_notification=True,
                                                                        disable_web_page_preview=True))
            channelCoupon.channelMessageID_text = couponTextMsg.message_id
            channelCoupon.channelMessageID_text_date_posted = datetime.now()
            # Update DB
            channelCoupon.store(channelDB)

    await bkbot.sendCouponOverviewWithChannelLinks(chat_id=bkbot.getPublicChannelChatID(), coupons=activeCoupons, useLongCouponTitles=False, channelDB=channelDB, infoDB=infoDB,
                                                   infoDBDoc=infoDBDoc)

    notYetAvailableCouponsText = bkbot.crawler.cachedFutureCouponsText

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
        infoText += "\n---"
    if bkbot.maintenanceMode:
        infoText += '\n<b>' + SYMBOLS.DENY + 'Wartungsmodus!' + SYMBOLS.DENY
        infoText += '\nDie Funktionalität von Bot/Channel kann derzeit nicht gewährleistet werden!'
        infoText += '\nFalls vorhanden, bitte die angepinnten Infos im Channel beachten.'
        infoText += '</b>'
        infoText += "\n---"
    missingPaperCouponsText = bkbot.crawler.getMissingPaperCouponsText()
    if missingPaperCouponsText is not None:
        infoText += '\n<b>' + SYMBOLS.WARNING + 'Derzeit im Channel fehlende Papiercoupons:</b>' + missingPaperCouponsText
    if notYetAvailableCouponsText is not None:
        infoText += '\n' + notYetAvailableCouponsText
        infoText += "\n---"

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
    # Store old informationMessageID for later deletion
    if infoDBDoc.informationMessageID is not None:
        infoDBDoc.addMessageIDToDelete(infoDBDoc.informationMessageID)
    # Send channel update overview message
    newMsg = await asyncio.create_task(
        bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=infoText, parse_mode="HTML", disable_web_page_preview=True, disable_notification=True))
    # Store messageID of channel update overview message
    infoDBDoc.informationMessageID = newMsg.message_id
    infoDBDoc.dateLastSuccessfulChannelUpdate = datetime.now()
    infoDBDoc.store(infoDB)
    logging.info(f"Channel update done | Total time needed: {datetime.now() - dateStart}")


async def cleanupChannel(bkbot):
    logging.info("Channel cleanup started")
    dateStart = datetime.now()
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    await deleteLeftoverMessageIDsToDelete(bkbot, infoDB, infoDoc)
    logging.info(f"Channel cleanup done | Total time needed: {datetime.now() - dateStart}")


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
        logging.info(f"Deleting {len(channelDB)} coupons...")
        index = 0
        initialItemNumber = len(channelDB)
        for couponID in channelDB:
            index += 1
            logging.info(f"Working on coupon {index}/{initialItemNumber}")
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
    logging.info("Nuke channel DONE! --> Total time needed: " + getFormattedPassedTime(timestampStart))

