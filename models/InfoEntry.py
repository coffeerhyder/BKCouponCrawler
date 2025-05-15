from typing import List, Union

from couchdb.mapping import Document, DateTimeField, TextField, DictField, ListField, IntegerField, BooleanField

from Helper import CouponType


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

    def addCouponCategoryMessageID(self, couponType: CouponType, messageID: int):
        self.couponTypeOverviewMessageIDs.setdefault(int(couponType), []).append(messageID)

    def getMessageIDsForCouponCategory(self, couponType: CouponType) -> List[int]:
        return self.couponTypeOverviewMessageIDs.get(str(int(couponType)), [])

    def getAllCouponCategoryMessageIDs(self) -> List[int]:
        messageIDs = []
        for messageIDsTemp in self.couponTypeOverviewMessageIDs.values():
            messageIDs += messageIDsTemp
        return messageIDs

    def deleteCouponCategoryMessageIDs(self, couponType: Union[int, str]) -> bool:
        if str(couponType) not in self.couponTypeOverviewMessageIDs:
            return False
        else:
            del self.couponTypeOverviewMessageIDs[str(couponType)]
            return True

    def deleteAllCouponCategoryMessageIDs(self):
        self.couponTypeOverviewMessageIDs = {}
