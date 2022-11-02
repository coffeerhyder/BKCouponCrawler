import os.path
import csv
import re

import qrcode

""" Quick and dirty script to create QR Codes for all items of CSV exported data from crawler for old BK API.
Usage:
1. Put "coupons.csv" file into directory where this script is.
2. Run this script and find its output in folder 'coupons_csv_images'.
"""


class CsvToQrcodesImagesScript2:
    def __init__(self):
        pass

    def main(self):
        imagefolder = 'coupons_csv_images'
        if not os.path.exists(imagefolder):
            os.makedirs(imagefolder)
        menuRowAllowedValue = None
        # Set this to false if you only want this script to output only non-menu items or to true if you want only menu items
        # menuRowAllowedValue = False
        # menuRowAllowedValue = True
        with open('coupons.csv', encoding='ANSI') as csvfile:
            csvreader = csv.DictReader(csvfile, dialect='excel',
                                      fieldnames=["PRODUCT", "MENU", "PLU", "PLU2", "TYPE", "PRICE", "PRICE_COMPARE", "START", "EXP"], delimiter=',')

            position = 0
            for row in csvreader:
                position += 1
                print(f"Working on row {position}")
                plu = row['PLU2'].strip()
                price = row['PRICE']
                articlename = row['PRODUCT']
                startDate = row['START']
                if plu is None or price is None or articlename is None or startDate is None:
                    # WTF should never happen
                    print(f'Skipping invalid row data {position}')
                    continue
                yearRegex = re.compile(r'^\d{2}\.\d{2}.(\d{4})').search(startDate)
                if yearRegex is None:
                    # Typically that is the table header
                    print(f'Skipping pos {position} because: Invalid plu data: {row}')
                    continue
                menuStr = row['MENU']
                menu = True if menuStr.lower() in ['true', 'WAHR'] else False
                if menuRowAllowedValue is not None and menu != menuRowAllowedValue:
                    print(f'Skipping that row because: menu != {menuRowAllowedValue}')
                    continue
                year = yearRegex.group(1)
                # Beautify/fix data
                price = price.strip()
                priceCents = int(price)
                price = f'{priceCents:04d}EUR'
                articlename = articlename.strip().replace(' ', '')
                filename = year + '_' + price + '_' + plu + '_' + articlename + '.png'
                # Quickly stolen from: https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename/38766141#38766141
                filename = re.sub('[^\\w_.)( -]', '', filename)
                # print(str(row))
                print('Writing file' + filename)
                qr = qrcode.QRCode(
                    version=1,
                    border=10
                )
                qr.add_data(plu)
                """ 2021-01-25: Use the same color they're using in their app. """
                img = qr.make_image(fill_color="#4A1E0D", back_color="white")
                img.save(os.path.join(imagefolder, filename))
        print('SUCCESS | Done')
        return None


if __name__ == '__main__':
    cs = CsvToQrcodesImagesScript2()
    cs.main()
