from datetime import datetime

from Helper import getTimezone
from UtilsCouponsDB import CouponViews



allViews = CouponViews.__dict__

print(str(CouponViews.__dict__))

# 2022-09-17
dateformat = '%Y-%m-%dT%H:%M:%S.%fZ'
testDatetime = datetime.strptime('2022-09-26T21:59:00.000Z', dateformat)
testDatetime.astimezone(getTimezone())
print("Formatted: " + testDatetime.strftime('%Y-%m-%dT%H:%M:%S.%f'))

print('Timestamp: ' + str(testDatetime.timestamp()))
print('Timestamp2: ' + str(testDatetime.timestamp()))
print("utcoffset" + str(testDatetime.utcoffset()))


print("End")
