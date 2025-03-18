from typing import List

from couchdb.mapping import Document, DateTimeField, TextField, DictField, ListField, IntegerField, BooleanField


class InfoEntry(Document):
    dateLastSuccessfulChannelUpdate = DateTimeField()
    dateLastSuccessfulCrawlRun = DateTimeField()
    informationMessageID = TextField()
    couponTypeOverviewMessageIDs = DictField(default={})
    messageIDsToDelete = ListField(IntegerField(), default=[])
    lastMaintenanceModeState = BooleanField()

    def addMessageIDToDelete(self, messageID: int) -> bool:
        # Avoid duplicates
        if messageID not in self.messageIDsToDelete:
            self.messageIDsToDelete.append(messageID)
            return True
        else:
            return False

    def addMessageIDsToDelete(self, messageIDs: List) -> bool:
        containsAtLeastOneNewID = False
        for messageID in messageIDs:
            if self.addMessageIDToDelete(messageID):
                containsAtLeastOneNewID = True
        return containsAtLeastOneNewID

    def addCouponCategoryMessageID(self, couponType: int, messageID: int):
        self.couponTypeOverviewMessageIDs.setdefault(couponType, []).append(messageID)

    def getMessageIDsForCouponCategory(self, couponType: int) -> List[int]:
        return self.couponTypeOverviewMessageIDs.get(str(couponType), [])

    def getAllCouponCategoryMessageIDs(self) -> List[int]:
        messageIDs = []
        for messageIDsTemp in self.couponTypeOverviewMessageIDs.values():
            messageIDs += messageIDsTemp
        return messageIDs

    def deleteCouponCategoryMessageIDs(self, couponType: int):
        if str(couponType) in self.couponTypeOverviewMessageIDs:
            del self.couponTypeOverviewMessageIDs[str(couponType)]

    def deleteAllCouponCategoryMessageIDs(self):
        self.couponTypeOverviewMessageIDs = {}
