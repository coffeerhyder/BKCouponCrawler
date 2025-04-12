from typing import List, Union

from couchdb.mapping import Document, DateTimeField, TextField, DictField, ListField, IntegerField, BooleanField


class InfoEntry(Document):
    dateLastSuccessfulChannelUpdate = DateTimeField()
    dateLastSuccessfulCrawlRun = DateTimeField()
    coupon_ids_to_send = ListField(TextField(), default=[])
    informationMessageID = TextField()
    couponTypeOverviewMessageIDs = DictField(default={})
    messageIDsToDelete = ListField(IntegerField(), default=[])
    lastMaintenanceModeState = BooleanField()

    def addMessageIDToDelete(self, messageID: Union[int, str]) -> bool:
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

    def getMessageIDsForCouponCategory(self, couponType: Union[int, str]) -> List[int]:
        return self.couponTypeOverviewMessageIDs.get(str(couponType), [])

    def getAllCouponCategoryMessageIDs(self) -> List[int]:
        messageIDs = []
        for messageIDsTemp in self.couponTypeOverviewMessageIDs.values():
            messageIDs += messageIDsTemp
        return messageIDs

    def deleteCouponCategoryMessageIDs(self, couponType: Union[int, str]):
        if str(couponType) in self.couponTypeOverviewMessageIDs:
            del self.couponTypeOverviewMessageIDs[str(couponType)]

    def deleteAllCouponCategoryMessageIDs(self):
        self.couponTypeOverviewMessageIDs = {}
