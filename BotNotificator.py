import logging
import time
import traceback
from datetime import datetime
from enum import Enum
from typing import Union, List

from telegram import InputMediaPhoto
from telegram.error import BadRequest

from BotUtils import getBotImpressum
from Helper import INFO_DB, DATABASES, getCurrentDate, SYMBOLS, getFormattedPassedTime
from Models import CouponFilter

from UtilsCouponsDB import couponDBGetUniqueIdentifier, User, ChannelCoupon, InfoEntry, CouponSortMode, \
    generateCouponLongTextFormattedWithDescription
from CouponCategory import BotAllowedCouponSources

WAIT_SECONDS_AFTER_EACH_MESSAGE_OPERATION = 0
""" For testing purposes only!! """
DEBUGNOTIFICATOR = False


def notifyUsersAboutNewCoupons(bkbot) -> None:
    logging.info("Checking for pending new coupons notifications")
    timestampStart = datetime.now().timestamp()
    userDB = bkbot.crawler.getUsersDB()
    newCoupons = bkbot.crawler.filterCoupons(CouponFilter(activeOnly=True, isNew=True, allowedCouponSources=BotAllowedCouponSources, sortMode=CouponSortMode.PRICE))
    if len(newCoupons) == 0:
        logging.info("No new coupons available to notify about")
        return
    postTextNewCoupons = "<b>" + SYMBOLS.NEW + str(len(newCoupons)) + " neue Coupons verfügbar:</b>" + bkbot.getNewCouponsTextWithChannelHyperlinks(newCoupons, 49)
    usersNotify = {}
    numberofFavoriteNotifications = 0
    numberofNewCouponsNotifications = 0
    for userIDStr in userDB:
        user = User.load(userDB, userIDStr)
        usertext = ""
        # Do not forget about Telegram entity limits...
        remainingEntitiesMax = 50
        remainingEntities = remainingEntitiesMax
        if user.settings.notifyWhenFavoritesAreBack:
            # Check if user has favorites that are new (back/valid again)
            userNewCoupons = {}
            for couponID in user.favoriteCoupons:
                newCoupon = newCoupons.get(couponID)
                if newCoupon is not None:
                    userNewCoupons[couponID] = newCoupon
            if len(userNewCoupons) > 0:
                usertext += "<b>" + SYMBOLS.STAR + str(
                    len(userNewCoupons)) + " deiner favorisierten Coupons sind wieder verfügbar:</b>" + bkbot.getNewCouponsTextWithChannelHyperlinks(userNewCoupons, 49)
                numberofFavoriteNotifications += 1
                remainingEntities -= 1
                remainingEntities -= len(userNewCoupons)
        # Check if user has enabled notifications for new coupons
        if user.settings.notifyWhenNewCouponsAreAvailable:
            if len(usertext) == 0:
                remainingEntities -= 1
            else:
                usertext += "\n---\n"
            usertext += postTextNewCoupons
            numberofNewCouponsNotifications += 1
            remainingEntities -= len(newCoupons)
        if len(usertext) > 0:
            # Complete user text and save it to send it later
            if bkbot.getPublicChannelName() is None:
                usertext += "\nMit /start gelangst du ins Hauptmenü des Bots."
            else:
                usertext += "\nPer Klick kommst du zu den jeweiligen Coupons im " + bkbot.getPublicChannelHyperlinkWithCustomizedText(
                    "Channel") + " und mit /start ins Hauptmenü des Bots."
            if remainingEntities < 0:
                usertext += "\n" + SYMBOLS.WARNING + "Wegen Telegram Limits konnten nicht alle Coupons verlinkt werden."
                usertext += "\nDas ist nicht weiter tragisch und du findest alle im Bot/Channel."
            # Store text to send to user and send it later
            usersNotify[userIDStr] = usertext
    if len(usersNotify) == 0:
        logging.info("No users available who want to be notified on new coupons")
        return
    logging.info("Notifying " + str(len(usersNotify)) + " users about favorites / new coupons")
    index = -1
    for userIDStr, postText in usersNotify.items():
        index += 1
        logging.info("Sending user notification " + str(index + 1) + " / " + str(len(usersNotify)) + " to user " + userIDStr)
        bkbot.send_message(chat_id=userIDStr, text=postText, parse_mode='HTML', disable_web_page_preview=True)
    logging.info("New coupons notifications done | Duration: " + getFormattedPassedTime(timestampStart))


class ChannelUpdateMode(Enum):
    """ Different modes that can be used to perform a channel update """
    # This mode would only work if TG bots were able to delete messages older than 48 hours!
    UPDATE = 1
    # Delete- and re-send all coupons into our channel
    RESEND_ALL = 2
    # This will only re-send all items older than X hours - can be used to resume channel update if it was e.g. interrupted due to a connection loss
    RESUME_CHANNEL_UPDATE = 3


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
    activeCoupons = bkbot.crawler.filterCoupons(CouponFilter(activeOnly=True, allowedCouponSources=BotAllowedCouponSources, sortMode=CouponSortMode.SOURCE_MENU_PRICE))
    channelDB = bkbot.couchdb[DATABASES.TELEGRAM_CHANNEL]
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDBDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    couponsToSendOut = {}
    """ This contains only 'real' new items! Doesn't contain items that get re-sent for channel update! """
    newCoupons = {}
    updatedCoupons = {}
    # Collect new + updated items
    for coupon in activeCoupons.values():
        if coupon.id not in channelDB:
            # New coupon - save information into both dicts
            couponsToSendOut[coupon.id] = coupon
            newCoupons[coupon.id] = coupon
        elif ChannelCoupon.load(channelDB, coupon.id).uniqueIdentifier != couponDBGetUniqueIdentifier(coupon):
            # Current/new coupon data differs from coupon we've posted in channel (same unique ID but coupon data has changed)
            updatedCoupons[coupon.id] = coupon
    if len(infoDBDoc.messageIDsToDelete) > 0:
        # This can happen but should only be a rare occurance!
        logging.warning("Found " + str(len(infoDBDoc.messageIDsToDelete)) + " leftover messageIDs to delete")
    # Collect- and delete deleted coupons from channel
    deletedChannelCoupons = []
    for uniqueCouponID in channelDB:
        if uniqueCouponID not in activeCoupons:
            channelCoupon = ChannelCoupon.load(channelDB, uniqueCouponID)
            infoDBDoc[InfoEntry.messageIDsToDelete.name] += channelCoupon[ChannelCoupon.messageIDs.name]
            deletedChannelCoupons.append(channelCoupon)
    # Update DB
    if len(deletedChannelCoupons) > 0:
        channelDB.purge(deletedChannelCoupons)
        # Save this so we always remember which messageIDs we need to delete later on
        infoDBDoc.store(infoDB)
    # Collect coupons to send out in this run
    if updateMode == ChannelUpdateMode.RESEND_ALL:
        couponsToSendOut = activeCoupons
    elif updateMode == ChannelUpdateMode.RESUME_CHANNEL_UPDATE:
        # Collect all coupons that haven't been sent into the channel at all or were sent into the channel more than X seconds ago (= "old" entries)
        for coupon in activeCoupons.values():
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            if channelCoupon is None or datetime.now().timestamp() - channelCoupon.timestampMessagesPosted > 6 * 60 * 60:
                # Coupon has not been posted into channel yet or has been posted in there too long ago -> Add to list of coupons to re-send later
                couponsToSendOut[coupon.id] = coupon
    elif updateMode == ChannelUpdateMode.UPDATE:
        # TODO: Add functionality
        pass
    else:
        logging.warning("Unsupported ChannelUpdateMode! Developer mistake?!")
    # Send relevant coupons into chat
    if len(couponsToSendOut) > 0:
        logging.info("Sending out " + str(len(couponsToSendOut)) + " coupons...")
        # Collect all old messageIDs which need to be deleted by checking which of the ones we want to send out are already in our channel at this moment
        channelCouponDBUpdates = []
        for coupon in couponsToSendOut.values():
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            if channelCoupon is not None and len(channelCoupon.messageIDs) > 0:
                infoDBDoc[InfoEntry.messageIDsToDelete.name] += channelCoupon[ChannelCoupon.messageIDs.name]
                channelCoupon.messageIDs = ChannelCoupon().messageIDs  # Nuke array (default = [])
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
            if bkbot.getCouponImage(coupon) is None:
                # This should never happen
                raise Exception("WTF failed to find coupon image")
            elif bkbot.getCouponImageQR(coupon) is None:
                # This should never happen
                raise Exception("WTF failed to find QR image")
            if coupon.id not in channelDB:
                channelDB[coupon.id] = {}
            channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
            channelCoupon.uniqueIdentifier = couponDBGetUniqueIdentifier(coupon)
            couponText = generateCouponLongTextFormattedWithDescription(coupon)
            photoAlbum = [InputMediaPhoto(media=bkbot.getCouponImage(coupon), caption=couponText, parse_mode='HTML'),
                          InputMediaPhoto(media=bkbot.getCouponImageQR(coupon), caption=couponText, parse_mode='HTML')
                          ]
            channelCoupon.messageIDs = []
            logging.debug("Sending new coupon messages 1/2: Coupon photos")
            chatMessages = bkbot.sendMediaGroup(chat_id=bkbot.getPublicChannelChatID(), media=photoAlbum, disable_notification=True)
            for msg in chatMessages:
                channelCoupon.messageIDs.append(msg.message_id)
            # Update DB
            channelCoupon.store(channelDB)
            # Send coupon information as text (= last message for this coupon)
            logging.debug("Sending new coupon messages 2/2: Coupon text")
            couponTextMsg = bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=couponText, parse_mode='HTML', disable_notification=True,
                                              disable_web_page_preview=True)
            channelCoupon.messageIDs.append(couponTextMsg.message_id)
            # Update DB
            # Save timestamp so we roughly know when these messages have been posted
            channelCoupon.timestampMessagesPosted = datetime.now().timestamp()
            channelCoupon.store(channelDB)

    # Update channel if needed
    if len(updatedCoupons) > 0 or len(deletedChannelCoupons) > 0 or len(
            couponsToSendOut) > 0 or updateMode == ChannelUpdateMode.RESEND_ALL or updateMode == ChannelUpdateMode.RESUME_CHANNEL_UPDATE or DEBUGNOTIFICATOR:
        allowMessageEdit = len(newCoupons) > 0 and updateMode == ChannelUpdateMode.UPDATE and not DEBUGNOTIFICATOR
        try:
            bkbot.sendCouponOverviewWithChannelLinks(chat_id=bkbot.getPublicChannelChatID(), coupons=activeCoupons, useLongCouponTitles=False, channelDB=channelDB, infoDB=infoDB, infoDBDoc=infoDBDoc, allowMessageEdit=False)
        except:
            traceback.print_exc()

        """ Update/re-send coupon overview(s), spread this information over multiple pages if needed. """
        # for couponSourceIndex in range(len(BotAllowedCouponSources)):
        #     couponSource = BotAllowedCouponSources[couponSourceIndex]
        #     couponCategory = CouponCategory(couponSource)
        #     logging.info("Working on coupon overview update " + str(couponSourceIndex + 1) + "/" + str(len(BotAllowedCouponSources)) + " | " + couponCategory.nameSingular)
        #     hasAddedSeparatorAfterCouponsWithoutMenu = False
        #     listContainsAtLeastOneItemWithoutMenu = False
        #     dbKeyMessageIDsCouponType = INFO_DB.DB_INFO_channel_last_coupon_type_overview_message_ids + str(couponSource)
        #     messageIDsForThisCategory = infoDBDoc.setdefault(dbKeyMessageIDsCouponType, [])
        #     if couponSource in couponsSeparatedByType:
        #         # allowMessageEdit == True --> Handling untested!
        #         coupons = couponsSeparatedByType[couponSource]
        #         # Depends on the max entities per post limit of Telegram and we're not only using hyperlinks but also the "<b>" tag so we do not have 50 hyperlinks left but 49.
        #         maxCouponsPerPage = 49
        #         maxPage = math.ceil(len(coupons) / maxCouponsPerPage)
        #         if allowMessageEdit:
        #             # Delete pages if there are too many
        #             if len(messageIDsForThisCategory) > maxPage:
        #                 deleteStartIndex = (len(messageIDsForThisCategory) - (len(messageIDsForThisCategory) - maxPage)) - 1
        #                 for index in range(deleteStartIndex, len(messageIDsForThisCategory)):
        #                     infoDBDoc.messageIDsToDelete.append(messageIDsForThisCategory[index])
        #                 # Update our array as we fill it again later
        #                 del messageIDsForThisCategory[deleteStartIndex: len(messageIDsForThisCategory)]
        #                 # Update DB
        #                 infoDBDoc.store(infoDB)
        #         else:
        #             # Delete all old pages for current coupon type
        #             if len(messageIDsForThisCategory) > 0:
        #                 # Save old messages for deletion
        #                 infoDBDoc[InfoEntry.messageIDsToDelete.name] += messageIDsForThisCategory
        #                 messageIDsForThisCategory.clear()
        #                 # Update DB
        #                 infoDBDoc.store(infoDB)
        #         for page in range(1, maxPage + 1):
        #             logging.info("Sending category page: " + str(page) + "/" + str(maxPage))
        #             couponOverviewText = "<b>[" + str(len(coupons)) + " Stück] " + couponCategory.nameSingular + " Übersicht"
        #             if couponCategory.displayDescription:
        #                 couponOverviewText += "\n" + couponCategory.description
        #             if maxPage > 1:
        #                 couponOverviewText += " Teil " + str(page) + " / " + str(maxPage)
        #             couponOverviewText += "</b>"
        #             startIndex = page * maxCouponsPerPage - maxCouponsPerPage
        #             for couponIndex in range(startIndex, startIndex + maxCouponsPerPage):
        #                 coupon = coupons[couponIndex]
        #                 """ Add a little separator so it is easier for the user to distinguish between coupons with- and without menu.
        #                 This only works as "simple" as that because we pre-sorted these coupons!
        #                 """
        #                 if not coupon.containsFriesOrCoke:
        #                     listContainsAtLeastOneItemWithoutMenu = True
        #                 elif not hasAddedSeparatorAfterCouponsWithoutMenu and listContainsAtLeastOneItemWithoutMenu:
        #                     couponOverviewText += '\n<b>' + SYMBOLS.WHITE_DOWN_POINTING_BACKHAND + 'Coupons mit Menü' + SYMBOLS.WHITE_DOWN_POINTING_BACKHAND + '</b>'
        #                     hasAddedSeparatorAfterCouponsWithoutMenu = True
        #                 """ Generates e.g. "Y15 | 2Whopper+M🍟+0,4LCola | 8,99€"
        #                 Returns the same with hyperlink if a chat_id is given for this coupon e.g.:
        #                 "Y15 | 2Whopper+M🍟+0,4LCola (https://t.me/betterkingpublic/1054) | 8,99€"
        #                 """
        #                 if coupon.id in channelDB:
        #                     channelCoupon = ChannelCoupon.load(channelDB, coupon.id)
        #                     if len(channelCoupon.messageIDs) > 0:
        #                         couponText = bkbot.generateCouponShortTextFormattedWithHyperlinkToChannelPost(coupon, channelCoupon.messageIDs[0])
        #                     else:
        #                         # This should never happen but we'll allow it to
        #                         logging.warning("Can't hyperlink coupon because no messageIDs available: " + coupon.id)
        #                         couponText = bkbot.generateCouponShortTextFormatted(coupon)
        #                 else:
        #                     # This should never happen but we'll allow it to
        #                     logging.warning("Can't hyperlink coupon because it is not in channelDB: " + coupon.id)
        #                     couponText = bkbot.generateCouponShortTextFormatted(coupon)
        #
        #                 couponOverviewText += '\n' + couponText
        #                 # Exit loop after last coupon info has been added
        #                 if couponIndex == len(coupons) - 1:
        #                     break
        #             if allowMessageEdit and page - 1 <= len(messageIDsForThisCategory) - 1:
        #                 # Edit last post of current page
        #                 msgIDToEdit = messageIDsForThisCategory[page - 1]
        #                 editMessageAndWait(bkbot, msgIDToEdit, couponOverviewText)
        #             else:
        #                 # Send new post containing current page
        #                 msg = bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=couponOverviewText, parse_mode="HTML", disable_web_page_preview=True,
        #                                         disable_notification=True)
        #                 messageIDsForThisCategory.append(msg.message_id)
        #                 # Update DB
        #                 infoDBDoc.store(infoDB)
        #     elif len(messageIDsForThisCategory) > 0:
        #         """ Cleanup chat:
        #         Typically needed if a complete supported coupon type was there but is not existant anymore e.g. paper coupons were there but aren't existant anymore -> Delete old overview-message(s) """
        #         deleteMessageIDs(bkbot, messageIDsForThisCategory)
        #         del infoDBDoc[dbKeyMessageIDsCouponType]
        #         infoDBDoc.store(infoDB)
        #     else:
        #         # Rare case
        #         logging.info("Nothing to do: No coupons of this type available and no old ones to delete :)")

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
        if updateMode == ChannelUpdateMode.RESEND_ALL or updateMode == ChannelUpdateMode.RESUME_CHANNEL_UPDATE:
            infoText += '\n' + SYMBOLS.WRENCH + ' Alle ' + str(len(activeCoupons)) + ' Coupons erneut in die Gruppe gesendet'
        if DEBUGNOTIFICATOR:
            infoText += '\n<b>Debug Modus!!!</b>'
        infoText += '\n<b>------</b>'
        infoText += "\nTechnisch bedingt werden die Coupons täglich erneut in diesen Channel geschickt."
        infoText += "\nStören dich die Benachrichtigungen?"
        infoText += "\nErstelle eine Verknüpfung: Drücke oben auf den Namen des Chats -> Rechts auf die drei Punkte -> Verknüpfung hinzufügen (funktioniert auch mit Bots)"
        infoText += "\nNun kannst du den Channel verlassen und ihn jederzeit wie eine App öffnen, ohne erneut beizutreten!"
        infoText += "\n... oder verwende <a href=\"https://t.me/" + bkbot.botName + "\">den Bot</a>."
        infoText += "\n<b>Der Bot kann außerdem deine Favoriten speichern, Coupons filtern und einiges mehr ;)</b>"
        infoText += "\nMöchtest du diesen Channel mit jemandem teilen, der kein Telegram verwendet?"
        infoText += "\nNimm <a href=\"https://t.me/s/" + bkbot.getPublicChannelName() + "\">diesen Link</a> oder <a href=\"https://app.element.io/#/room/#BetterKingDE:matrix.org\">Element per Matrix Bridge</a>."
        infoText += "\n<b>Guten Hunger!</b>"
        infoText += "\n" + getBotImpressum()
        """ 
        Did we only delete coupons and/or update existing ones while there were no new coupons coming in AND we were not forced to delete- and re-send all items?
        Edit our last message if existant so the user won't receive a new notification!
        """
        oldInfoMsgID = infoDBDoc.get(INFO_DB.DB_INFO_channel_last_information_message_id)
        if allowMessageEdit and oldInfoMsgID is not None:
            # Edit previous message
            editMessageAndWait(bkbot, oldInfoMsgID, infoText)
        else:
            # Post new message and store old for later deletion
            if oldInfoMsgID is not None:
                infoDBDoc.messageIDsToDelete.append(oldInfoMsgID)
            newMsg = bkbot.sendMessage(chat_id=bkbot.getPublicChannelChatID(), text=infoText, parse_mode="HTML", disable_web_page_preview=True, disable_notification=True)
            infoDBDoc[INFO_DB.DB_INFO_channel_last_information_message_id] = newMsg.message_id
            infoDBDoc.store(infoDB)
    logging.info("Channel update done | Total time needed: " + getFormattedPassedTime(timestampStart))


def cleanupChannel(bkbot):
    logging.info("Channel cleanup started")
    timestampStart = datetime.now().timestamp()
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    deleteLeftoverCouponMessageIDsToDelete(bkbot, infoDB, infoDoc)
    logging.info("Channel cleanup done | Total time needed: " + getFormattedPassedTime(timestampStart))


def deleteLeftoverCouponMessageIDsToDelete(bkbot, infoDB, infoDoc):
    if len(infoDoc.messageIDsToDelete) > 0:
        initialNumberofMsgsToDelete = len(infoDoc.messageIDsToDelete)
        logging.info("Deleting " + str(initialNumberofMsgsToDelete) + " old messages...")
        index = 0
        for messageID in infoDoc.messageIDsToDelete[:]:
            logging.info("Deleting messageID " + str(index + 1) + "/" + str(initialNumberofMsgsToDelete) + " | " + str(messageID))
            bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=messageID)
            infoDoc.messageIDsToDelete.remove(messageID)
            # Save current state to DB
            infoDoc.store(infoDB)
            index += 1


def nukeChannel(bkbot):
    """ This will simply delete all message in the TG channel. """
    timestampStart = datetime.now().timestamp()
    logging.info("Nuking channel...")
    channelDB = bkbot.couchdb[DATABASES.TELEGRAM_CHANNEL]
    justDeletedMessageIDs = []
    infoDB = bkbot.couchdb[DATABASES.INFO_DB]
    infoDoc = InfoEntry.load(infoDB, DATABASES.INFO_DB)
    if len(channelDB) > 0:
        # Delete all coupons that are currently posted in our channel
        logging.info("Deleting " + str(len(channelDB)) + " coupons...")
        index = 0
        initialItemNumber = len(channelDB)
        for couponID in channelDB:
            index += 1
            logging.info("Working on coupon " + str(index) + " / " + str(initialItemNumber))
            channelCoupon = ChannelCoupon.load(channelDB, couponID)
            for messageID in channelCoupon.messageIDs:
                bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=messageID)
            justDeletedMessageIDs += channelCoupon.messageIDs
            del channelDB[couponID]
    # Delete coupon overview messages
    logging.info("Deleting information messages...")
    for couponSource in BotAllowedCouponSources:
        couponOverviewDBKey = INFO_DB.DB_INFO_channel_last_coupon_type_overview_message_ids + str(couponSource)
        couponOverviewMessageIDs = infoDoc.get(couponOverviewDBKey, [])
        if len(couponOverviewMessageIDs) > 0:
            deleteMessageIDs(bkbot, couponOverviewMessageIDs)
            del infoDoc[couponOverviewDBKey]
    # Delete coupon information message
    if infoDoc.informationMessageID is not None:
        logging.info("Deleting channel overview message")
        bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=infoDoc.informationMessageID)
        infoDoc.informationMessageID = None
        # Update DB
        infoDoc.store(infoDB)
    deleteLeftoverCouponMessageIDsToDelete(bkbot, infoDB, infoDoc)

    logging.info("Cleanup channel DONE! --> Total time needed: " + getFormattedPassedTime(timestampStart))


def deleteMessageIDs(bkbot, messageIDs: Union[List[int], None]):
    """ Deletes array of messageIDs. """
    if messageIDs is None:
        return
    index = 0
    for msgID in messageIDs:
        logging.info("Deleting message " + str(index + 1) + " / " + str(len(messageIDs)) + " | " + str(msgID))
        bkbot.deleteMessage(chat_id=bkbot.getPublicChannelChatID(), messageID=msgID)
        index += 1


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
