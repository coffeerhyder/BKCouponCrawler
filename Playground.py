# import qrcode
#
# qr = qrcode.QRCode(
#     version=1,
#     border=8
# )
# qr.add_data("1234")
# """ 2021-01-25: Use the same color they're using in their app. """
# img = qr.make_image(fill_color="#4A1E0D", back_color="white")
# test1 = border=4
# test2 = border=10 -> Looks good
# test3 = border=8 -> Looks also good (?)
# img.save("test3.png")

from furl import furl, urllib
from urllib.parse import urlparse, parse_qs

from UtilsCouponsDB import Coupon, ChannelCoupon, InfoEntry

url = "?action=displaycoupons&which=favorites&page=3"
o = urlparse(url)
query = parse_qs(o.query)

print(o.query)

print(o.query)
print(query["which"])

urlquery = furl(url)
print(urlquery.args["action"])

quotedStr = urllib.parse.quote(url)

print(quotedStr)

urlquery.args['page'] = 3
print("furl url: " + urlquery.url)

test = Coupon(plu='', id="")
test.plu = "44"

print("plu=" + test.plu)
print("gettest=" + str(test.data.get(Coupon.priceCompare.name, 1337.77)))
print("varTest = " + test.data.get(Coupon.plu.name, "123456"))

array1 = [1, 2, 3]
array2 = [4, 5, 6]
array3 = array1 + array2
print(str(array3))


infoDoc = InfoEntry(messageIDsToDelete=[1, 2, 3])
cp = ChannelCoupon(messageIDs=[4, 5, 6])

# + operator on docs doesnt work
# infoDoc.messageIDsToDelete += cp.messageIDs
infoDoc[InfoEntry.messageIDsToDelete.name] += cp[ChannelCoupon.messageIDs.name]
print(str(infoDoc.messageIDsToDelete))
