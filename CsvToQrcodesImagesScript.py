import os.path
import csv
import re

import qrcode


""" Quick and dirty script to create QR Codes for all items of CSV exported darta from: https://www.mydealz.de/gutscheine/burger-king-bk-plu-code-sammlung-uber-270-bkplucs-822614
Usage:
1. Download said 
"""
class CsvToQrcodesImagesScript:
    def __init__(self):
        pass

    def main(self):
        imagefolder = 'bkplucs_qrimages'
        if not os.path.exists(imagefolder):
            os.makedirs(imagefolder)
        with open('bkplucs.csv', encoding='utf-8') as csvfile:
            spamreader = csv.DictReader(csvfile, dialect='excel',
                                        fieldnames=["PLU", "Rabatt-Preis", "Normal -preis", "Rabatt", "Artikel/Menü", "Zuletzt funktionierend /Gültig bis", "Quelle",
                                                    "Saison /Promotion", "Kommentar"], delimiter=';')

            position = 0
            for row in spamreader:
                position += 1
                print(f"Working on row {position}")
                if position == 1:
                    # Skip table header
                    continue
                plu = row['PLU'].strip()
                price = row['Rabatt-Preis']
                articlename = row['Artikel/Menü']
                season = row['Saison /Promotion']

                pluregex = re.compile(r'^(\d+)').search(plu.strip())
                # This is how we easily determine wrong/invalid datarows
                if pluregex is None:
                    print(f'Skipping pos {position} because: Invalid plu data')
                    continue
                # Beautify/fix data
                plu = pluregex.group(1)
                price = price.strip()
                priceEuroRegex = re.compile(r'^(\d+,\d+)').search(price)
                if priceEuroRegex is not None:
                    price = priceEuroRegex.group(1).replace(',', '')
                    priceCents = int(price)
                    price = f'{priceCents:04d}EUR'
                elif '50%' in price:
                    # Fix e.g. '[50%]'
                    price = '50%'
                else:
                    # Other/unknown format
                    price = price.replace('€', '').strip()
                articlename = articlename.strip().replace(' ', '')
                # Year field is quite dirty and year is not always given
                seasonregex = re.compile(r'^(\d{4})').search(season.strip())
                if seasonregex is not None:
                    year = seasonregex.group(1)
                else:
                    year = 'UNKNOWNYEAR'
                filename = year + '_' + price + '_' + plu + '_' + articlename + '.png'
                # Quickly stolen from: https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename/38766141#38766141
                filename = re.sub('[^\\w_.)( -]', '', filename)
                # print(str(row))
                print('Writing file' + filename)
                qr = qrcode.QRCode(
                    version=1,
                    # 2021-05-02: This makes the image itself bigger but due to the border and the resize of Telegram, these QR codes might be suited better for usage in Telegram
                    border=10
                )
                qr.add_data(plu)
                """ 2021-01-25: Use the same color they're using in their app. """
                img = qr.make_image(fill_color="#4A1E0D", back_color="white")
                img.save(os.path.join(imagefolder, filename))
            print('SUCCESS | Done')
            return None


if __name__ == '__main__':
    cs = CsvToQrcodesImagesScript()
    cs.main()
