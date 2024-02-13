from PIL import Image
from pyzbar.pyzbar import decode
from pyzbar.wrapper import ZBarSymbol
import cv2

""" 2023-11-25: Playground for automated detection of BK coupons in image / PDF file
 Idea:
 1. Find all QR codes.
 2. Put a rectangle of a fixed size around the places where the QR codes are, then save those areas as separate images.
 3. OCR each image to find the remaining data.
 4. Put the data into our database so the bot can make use of it.
 """

imagepath = 'bk.png'

# pyzbar
img = Image.open(imagepath)
decoded_list = decode(img, symbols=[ZBarSymbol.QRCODE])
print(f'result 1: {decoded_list}')
# <class 'list'>

# img = cv2.imread(imagepath, cv2.IMREAD_GRAYSCALE)
# clean_im = cv2.medianBlur(img, 25)  # Apply median blur for reducing noise
# Show image for testing
# cv2.imshow('small_clean_im', clean_im)

image = cv2.imread(imagepath)
grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
height, width = image.shape[:2]
decoded_list = decode((grey.tobytes(), width, height))
print(f'result grey: {decoded_list}')



decoded_list = decode(img, symbols=[ZBarSymbol.QRCODE])
print(f'result 2: {decoded_list}')


qcd = cv2.QRCodeDetector()

retval, decoded_info, points, straight_qrcode = qcd.detectAndDecodeMulti(img)
print(f'result 3: {decoded_info=} | {points=}')

print("End")
