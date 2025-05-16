import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum

from telegram import InputMediaPhoto

from BotUtils import getBotImpressum, Commands, ImageCache
from Helper import getCurrentDate, SYMBOLS, getFormattedPassedTime, URLs, formatSeconds, formatDateGermanHuman, TEXT_NOTIFICATION_DISABLE, \
    CouponType
from models.InfoEntry import InfoEntry

from utils.UtilsCouponsDB import sortCouponsByPrice, getCouponTitleMapping, MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER, MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING, MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION, \
    MAX_SECONDS_WITHOUT_USAGE_UNTIL_AUTO_ACCOUNT_DELETION
from utils.CouponViews import CouponSortModes
from utils.Filters import CouponFilter
from models.User import User
from models.ChannelCoupon import ChannelCoupon


async def collectNewCouponsNotifications(bkbot) -> None:
    """
    Collects user notifications regarding new coupons and adds them to user document so they can be sent out later.
    """
    logging.info("Checking for pending new coupons notifications")
    timeStart = datetime.now()
    newCoupons = bkbot.getFilteredCouponsAsDict(CouponFilter(activeOnly=True, isNew=True, sortCode=CouponSortModes.PRICE.getSortCode()))
    if len(newCoupons) == 0:
        logging.info("No new coupons available to notify users about")
        return
    users = bkbot.db.get_users()
    if not users:
        logging.info("No users available to notify")
        return
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
    for user in users:
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
    bkbot.db.save_user(dbUserUpdateList)
    logging.info(f"New coupons notifications collector done | Duration: {(datetime.now() - timeStart)}")


async def collectUserDeleteNotifications(bkbot) -> None:
    numberOfCollectedNotifications = 0
    users = bkbot.db.get_users()
    for user in users:
        if not user.hasEverUsedBot():
            """
            Avoid sending such notifications to users whose datasets are not up2date.
            """
            continue

        secondsPassedSinceLastAccountActivity = user.getSecondsPassedSinceLastAccountActivity()
        secondsPassedSinceLastAccountDeletionWarning = getCurrentDate().timestamp() - user.timestampLastTimeWarnedAboutUpcomingAutoAccountDeletion

        # Early continue if conditions for sending warning aren't met
        if secondsPassedSinceLastAccountActivity < MAX_SECONDS_WITHOUT_USAGE_UNTIL_SEND_WARNING_TO_USER:
            continue
        if secondsPassedSinceLastAccountDeletionWarning <= MIN_SECONDS_BETWEEN_UPCOMING_AUTO_DELETION_WARNING:
            continue
        if user.timesInformedAboutUpcomingAutoAccountDeletion >= MAX_TIMES_INFORM_ABOUT_UPCOMING_AUTO_ACCOUNT_DELETION:
            continue

        # At this point, we know we need to send a notification
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

        await bkbot.sendMessageWithUserBlockedHandling(user=user, text=text, parse_mode='HTML', disable_web_page_preview=True, allowUpdateDB=False)

        if text not in user.pendingNotifications:
            notificationlist = user.pendingNotifications + [text]
            user.pendingNotifications = notificationlist

        bkbot.db.save_user(user)
        numberOfCollectedNotifications += 1

    logging.info('Number of users who will soon be informed about account deletion: ' + str(numberOfCollectedNotifications))


async def notifyAdminsAboutProblems(bkbot) -> None:
    adminIDs = bkbot.cfg.admin_ids
    if not adminIDs:
        # There are no admins
        return
    infoDBDoc: InfoEntry = bkbot.db.get_info_entry()
    if infoDBDoc is None:
        # First run and/or there has never been a crawl process
        return
    if infoDBDoc.dateLastSuccessfulCrawlRun is None or infoDBDoc.dateLastSuccessfulChannelUpdate is None:
        return
    test = False
    if test:
        infoDBDoc.dateLastSuccessfulCrawlRun = datetime.now() - timedelta(days=3)
    timedeltaLastSuccessfulRun = datetime.now() - infoDBDoc.dateLastSuccessfulCrawlRun
    timedeltaLastSuccessfulChannelupdate = datetime.now() - infoDBDoc.dateLastSuccessfulChannelUpdate
    text = ''
    if timedeltaLastSuccessfulRun.total_seconds() > 48 * 60 * 60:
        text += f'{SYMBOLS.WARNING} Crawler Fehler: Letzter erfolgreicher Crawlvorgang war am {formatDateGermanHuman(infoDBDoc.dateLastSuccessfulCrawlRun)}'
    if timedeltaLastSuccessfulChannelupdate.total_seconds() > 48 * 60 * 60:
        if len(text) > 0:
            text += '\n'
        text += f'{SYMBOLS.WARNING} Channelupdate Fehler: Letztes erfolgreiches Channelupdate war am {formatDateGermanHuman(infoDBDoc.dateLastSuccessfulChannelUpdate)}'
    if len(text) == 0:
        # No warning notifications to send out
        return
    userDB = bkbot.db.get_user_db()
    adminUsersNotified = []
    for adminID in adminIDs:
        adminUser = bkbot.db.get_user(adminID)
        if adminUser is None:
            # Id is not in DB anymore
            continue
        if not adminUser.settings.notifyMeAsAdminIfThereAreProblems:
            # Admin has disabled notifications
            continue
        adminUsersNotified.append(adminUser)
        await bkbot.sendMessageWithUserBlockedHandling(user=adminUser, userDB=userDB, text=text, parse_mode='HTML', disable_web_page_preview=True)
    logging.info(f"Number of notified admins: {len(adminUsersNotified)}")


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
    infoDoc = bkbot.crawler.db.get_info_entry()
    if infoDoc.dateLastSuccessfulChannelUpdate is not None:
        passedSeconds = (datetime.now() - infoDoc.dateLastSuccessfulChannelUpdate).total_seconds()
        logging.info("Passed seconds since last channel update: " + str(passedSeconds))
    activeCoupons = bkbot.getFilteredCouponsAsDict(
        CouponFilter(activeOnly=True, sortCode=CouponSortModes.TYPE_MENU_PRICE.getSortCode()))
    channelCoupons = bkbot.db.get_channel_coupons()
    channelCoupons_dict = {}
    for channelCoupon in channelCoupons:
        channelCoupons_dict[channelCoupon.id] = channelCoupon
    channelCouponsUpdated = {}
    # All coupons we want to send out this run
    couponsToSendOut = {}
    # All new coupons
    newCoupons = {}
    numberOfCouponsNewToThisChannel = 0
    # Collect new and updated items
    for coupon in activeCoupons.values():
        channelCoupon = channelCoupons_dict.get(coupon.id)
        if channelCoupon is None:
            # New coupon - save information into both dicts
            couponsToSendOut[coupon.id] = coupon
            if coupon.isNewCoupon():
                newCoupons[coupon.id] = coupon
            numberOfCouponsNewToThisChannel += 1
        elif channelCoupon.uniqueIdentifier != coupon.getUniqueIdentifier():
            # Current/new coupon data differs from coupon we've posted in channel (same unique ID but coupon data has changed)
            channelCouponsUpdated[coupon.id] = channelCoupon
    if len(infoDoc.messageIDsToDelete) > 0:
        # This can happen but should only be a rare occurance!
        logging.warning(f"Found {len(infoDoc.messageIDsToDelete)} leftover messageIDs to delete")

    # Collect coupons that need to be deleted from channel
    deletedChannelCoupons = []
    for coupon_id, channelCoupon in channelCoupons_dict.items():
        if coupon_id not in activeCoupons:
            infoDoc.addMessageIDsToDelete(channelCoupon.getMessageIDs())
            # Collect it here so we can delete it with only one DB request later.
            deletedChannelCoupons.append(channelCoupon)
    bkbot.db.delete_channel_coupons(deletedChannelCoupons)

    # Collect coupons to send out in this run.
    if updateMode == ChannelUpdateMode.RESEND_ALL:
        couponsToSendOut = activeCoupons
        infoDoc.coupon_ids_to_send = list(activeCoupons.keys())
    else:
        # ChannelUpdateMode.RESUME_CHANNEL_UPDATE
        # Collect all coupons that haven't been sent into the channel at all or were sent into the channel more than X seconds ago (= "old" entries)
        for coupon_id in infoDoc.coupon_ids_to_send:
            if coupon_id in activeCoupons:
                couponsToSendOut[coupon_id] = activeCoupons[coupon_id]
        logging.info(f"Resume channel update | Items to send: {len(couponsToSendOut)}/{len(activeCoupons)}")

    if numberOfCouponsNewToThisChannel != len(newCoupons):
        # During normal usage this should never happen
        logging.warning(
            "Developer mistake or DB has been updated without sending channel update in between for at least 2 days: Number of 'new' coupons to send into channel is: " + str(
                numberOfCouponsNewToThisChannel) + " but should be: " + str(len(newCoupons)))
    # Send relevant coupons into chat
    logging.info(f"Sending out {len(couponsToSendOut)}/{len(activeCoupons)} coupons...")
    # Collect all old messageIDs which need to be deleted by checking which of the ones we want to send out are already in our channel at this moment
    channelCouponsToUpdate = []
    for coupon in couponsToSendOut.values():
        channelCoupon = bkbot.db.get_channel_coupon(coupon.id)
        if channelCoupon is None:
            continue
        if not channelCoupon.getMessageIDs():
            continue
        infoDoc.addMessageIDsToDelete(channelCoupon.getMessageIDs())
        channelCoupon.deleteMessageIDs()
        channelCouponsToUpdate.append(channelCoupon)
    bkbot.db.save_channel_coupon(channelCouponsToUpdate)

    try:
        index = -1
        for coupon in couponsToSendOut.values():
            if bkbot.debugmode:
                break
            index += 1
            logging.info(f"Working on coupon {index + 1}/{len(couponsToSendOut)} | " + coupon.id)
            couponText = coupon.generateCouponLongTextFormattedWithDescription(highlightIfNew=True)
            photoAlbum = [InputMediaPhoto(media=bkbot.getCouponImage(coupon), caption=couponText, parse_mode='HTML'),
                          InputMediaPhoto(media=bkbot.getCouponImageQR(coupon), caption=couponText, parse_mode='HTML')
                          ]
            logging.debug("Sending new coupon messages 1/2: Coupon photos")
            chatMessages = await bkbot.sendMediaGroup(chat_id=bkbot.getPublicChannelChatID(), media=photoAlbum, disable_notification=True)

            msgImage = chatMessages[0]
            msgImageQR = chatMessages[1]
            # Update bot cache
            bkbot.couponImageCache[coupon.id] = ImageCache(fileID=msgImage.photo[0].file_id)
            bkbot.couponImageQRCache[coupon.id] = ImageCache(fileID=msgImageQR.photo[0].file_id)

            # Load item from DB if possible
            channelCoupon = bkbot.db.get_channel_coupon(coupon.id)
            if channelCoupon is None:
                # Create new item
                channelCoupon = ChannelCoupon(id=coupon.id)

            channelCoupon.uniqueIdentifier = coupon.getUniqueIdentifier()
            channelCoupon.channelMessageID_image = msgImage.message_id
            channelCoupon.channelMessageID_qr = msgImageQR.message_id
            channelCoupon.channelMessageID_image_and_qr_date_posted = datetime.now()

            # Update DB
            bkbot.db.save_channel_coupon(channelCoupon)

            # Send coupon text information
            logging.debug("Sending new coupon messages 2/2: Coupon text")
            couponTextMsg = await bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=couponText, parse_mode='HTML', disable_notification=True,
                                                                        disable_web_page_preview=True)
            channelCoupon.channelMessageID_text = couponTextMsg.message_id
            channelCoupon.channelMessageID_text_date_posted = datetime.now()

            # Update DB
            bkbot.db.save_channel_coupon(channelCoupon)

            # Update infoDoc
            if coupon.id in infoDoc.coupon_ids_to_send:
                infoDoc.coupon_ids_to_send.remove(coupon.id)
            else:
                logging.warning(f"WTF coupon_id {coupon.id} is not in infoDoc")
    finally:
        bkbot.db.save_info_entry(infoDoc)

    await bkbot.sendCouponOverviewWithChannelLinks(chat_id=bkbot.getPublicChannelChatID(), coupons=activeCoupons, useLongCouponTitles=False,
                                                   info_entry=infoDoc)


    """ Generate new information message text. """
    infoText = '<b>Heutiges Update:</b>'
    if len(deletedChannelCoupons) > 0:
        infoText += '\n' + SYMBOLS.DENY + ' ' + str(len(deletedChannelCoupons)) + ' Coupons gelöscht'
    if len(channelCouponsUpdated) > 0:
        infoText += '\n' + SYMBOLS.ARROW_UP_RIGHT + ' ' + str(len(channelCouponsUpdated)) + ' Coupons aktualisiert'
    if len(newCoupons) > 0:
        # Add detailed information about added coupons. Limit the max. number of that so our information message doesn't get too big.
        infoText += '\n<b>' + SYMBOLS.NEW + ' ' + str(len(newCoupons)) + ' Coupons hinzugefügt:</b>'
        infoText += bkbot.getNewCouponsTextWithChannelHyperlinks(newCoupons, 10)
    infoText += '\n' + SYMBOLS.WRENCH + ' Alle ' + str(len(activeCoupons)) + ' Coupons erneut in die Gruppe gesendet'
    infoText += '\n<b>------</b>'
    if bkbot.debugmode:
        infoText += '\n<b>' + SYMBOLS.WARNING + 'Debug Modus!!!' + SYMBOLS.WARNING + '</b>'
        infoText += "\n---"
    if bkbot.maintenanceMode:
        infoText += '\n<b>' + SYMBOLS.DENY + 'Wartungsmodus!' + SYMBOLS.DENY
        infoText += '\nDie Funktionalität von Bot/Channel kann derzeit nicht gewährleistet werden!'
        infoText += '\nFalls vorhanden, bitte die angepinnten Infos im Channel beachten.'
        infoText += '</b>'
        infoText += "\n---"
    if bkbot.crawler.cachedMissingPaperCouponsText is not None:
        infoText += f'\n<b>{SYMBOLS.WARNING}Derzeit im Channel fehlende Papiercoupons:</b>{bkbot.crawler.cachedMissingPaperCouponsText}'
    if bkbot.crawler.cachedFutureCouponsText is not None:
        infoText += '\n' + bkbot.crawler.cachedFutureCouponsText
        infoText += "\n---"

    infoText += "\nTechnisch bedingt werden die Coupons täglich erneut in diesen Channel geschickt."
    infoText += "\nStören dich die Benachrichtigungen?"
    infoText += "\nErstelle eine Verknüpfung: Drücke oben auf den Namen des Chats -> Rechts auf die drei Punkte -> Verknüpfung hinzufügen (funktioniert auch mit Bots)"
    infoText += "\nNun kannst du den Channel verlassen und ihn jederzeit wie eine App öffnen, ohne erneut beizutreten!"
    infoText += "\n... oder verwende <a href=\"https://t.me/" + bkbot.cfg.bot_name + "\">den Bot</a>."
    infoText += "\n<b>Der Bot kann außerdem deine Favoriten speichern, Coupons filtern und einiges mehr ;)</b>"
    infoText += "\nMöchtest du diesen Channel mit jemandem teilen, der kein Telegram verwendet?"
    infoText += "\nNimm <a href=\"https://t.me/s/" + bkbot.getPublicChannelName() + "\">diesen Link</a> oder <a href=\"" + URLs.ELEMENT + "\">Element per Matrix Bridge</a>."
    infoText += f"\nMehr Infos siehe <a href=\"{bkbot.getPublicChannelFAQLink()}\">FAQ</a>."
    infoText += "\n<b>Guten Wallraff!</b>"
    infoText += "\n" + getBotImpressum()
    """ 
    Did we only delete coupons and/or update existing ones while there were no new coupons coming in AND we were not forced to delete- and re-send all items?
    Edit our last message if existant so the user won't receive a new notification!
    """
    # Store old informationMessageID for later deletion
    if infoDoc.informationMessageID is not None:
        infoDoc.addMessageIDToDelete(infoDoc.informationMessageID)
    # Send channel update overview message
    newMsg = await bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=infoText, parse_mode="HTML", disable_web_page_preview=True, disable_notification=True)
    # Store messageID of channel update overview message
    infoDoc.informationMessageID = newMsg.message_id
    infoDoc.dateLastSuccessfulChannelUpdate = datetime.now()
    bkbot.db.save_info_entry(infoDoc)
    logging.info(f"Channel update done | Total time needed: {datetime.now() - dateStart}")


async def cleanupChannel(bkbot):
    logging.info("Channel cleanup started")
    dateStart = datetime.now()
    infoDoc = bkbot.crawler.db.get_info_entry()
    await deleteLeftoverMessageIDsToDelete(bkbot, infoDoc)
    logging.info(f"Channel cleanup done | Total time needed: {datetime.now() - dateStart}")


async def nukeChannel(bkbot):
    """ This will simply delete all message in the TG channel. """
    timestampStart = datetime.now().timestamp()
    logging.info("Nuking channel...")
    infoDoc = bkbot.crawler.db.get_info_entry()
    channelCoupons = bkbot.db.get_channel_coupons()
    if channelCoupons:
        # Delete all coupons that are currently posted in our channel
        logging.info(f"Deleting {len(channelCoupons)} coupons...")
        position = 1
        for channelCoupon in channelCoupons:
            logging.info(f"Deleting channel coupon {position}/{len(channelCoupons)}")
            messageIDs = channelCoupon.getMessageIDs()
            for messageID in messageIDs:
                await bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=messageID)
            bkbot.db.delete_channel_coupons(channelCoupon)
            position += 1
    # Delete coupon overview messages
    updateInfoDoc = False
    numberofDeletedCouponOverviewMessageIDs = 0
    for messageIDs in infoDoc.couponTypeOverviewMessageIDs.values():
        if len(messageIDs) == 0:
            continue
        await bkbot.deleteMessages(chat_id=bkbot.getPublicChannelChatID(), messageIDs=messageIDs)
        updateInfoDoc = True
        numberofDeletedCouponOverviewMessageIDs += len(messageIDs)
    infoDoc.couponTypeOverviewMessageIDs.clear()
    logging.info(f"Deleted {numberofDeletedCouponOverviewMessageIDs} information messages...")
    # Delete coupon information message
    if infoDoc.informationMessageID is not None:
        logging.info(f'Deleting channel overview message with ID {infoDoc.informationMessageID}')
        await bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=infoDoc.informationMessageID)
        infoDoc.informationMessageID = None
        updateInfoDoc = True
    if updateInfoDoc:
        # Update DB if changes were made
        bkbot.db.save_info_entry(infoDoc)
    await deleteLeftoverMessageIDsToDelete(bkbot, infoDoc)
    logging.info("Nuke channel DONE! --> Total time needed: " + getFormattedPassedTime(timestampStart))


async def deleteLeftoverMessageIDsToDelete(bkbot, infoDoc) -> int:
    """ Deletes all channel messages which were previously flagged for deletion.
     @:returns Number of deleted messages
      """
    numberOfMsgsToDelete = len(infoDoc.messageIDsToDelete)
    logging.info(f"Deleting {numberOfMsgsToDelete} old messages...")
    if numberOfMsgsToDelete == 0:
        # Do nothing
        return 0
    await bkbot.deleteMessages(chat_id=bkbot.getPublicChannelChatID(), messageIDs=infoDoc.messageIDsToDelete)
    # Update DB
    infoDoc.messageIDsToDelete = []
    bkbot.db.save_info_entry(infoDoc)
    return numberOfMsgsToDelete

