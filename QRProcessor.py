from PIL import Image
from pyzbar.pyzbar import decode
from pyzbar.wrapper import ZBarSymbol

""" 2023-11-25: Playground for automated detection of BK coupons in image / PDF file
 Idea:
 1. Find all QR codes.
 2. Put a rectangle of a fixed size around the places where the QR codes are, then save those areas as separate images.
 3. OCR each image to find the remaining data.
 4. Put the data into our database so the bot can make use of it.
 """
img = Image.open('bk.png')

decoded_list = decode(img, symbols=[ZBarSymbol.QRCODE])

print(type(decoded_list))
# <class 'list'>

print(f'Number of detected QR codes: {len(decoded_list)}')
print(f'{decoded_list}')

print("End")
