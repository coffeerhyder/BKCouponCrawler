import os.path
import csv
import re

import qrcode


""" Quick and dirty script to create QR Codes for all items of CSV exported data from: https://www.mydealz.de/gutscheine/burger-king-bk-plu-code-sammlung-uber-270-bkplucs-822614
Usage:
1. Download said excel table here: https://www.mydealz.de/gutscheine/burger-king-bk-plu-code-sammlung-uber-270-bkplucs-822614
2. Export it as .csv file and make sure there is no unnecessary line break in line 1.
3. Run this script and find its output in folder 'bkplucs_qrimages'.
"""
class CsvToQrcodesImagesScript:
    def __init__(self):
        pass

    def main(self):
        imagefolder = 'bkplucs_qrimages'
        if not os.path.exists(imagefolder):
            os.makedirs(imagefolder)
        with open('bkplucs.csv', encoding='utf-8') as csvfile:
            csvreader = csv.DictReader(csvfile, dialect='excel',
                                        fieldnames=["PLU", "Rabatt-Preis", "Normal -preis", "Rabatt", "Artikel/Menü", "Zuletzt funktionierend /Gültig bis", "Quelle",
                                                    "Saison /Promotion", "Kommentar"], delimiter=';')

            position = 0
            for row in csvreader:
                position += 1
                print(f"Working on row {position}")
                plu = row['PLU'].strip()
                price = row['Rabatt-Preis']
                articlename = row['Artikel/Menü']
                season = row['Saison /Promotion']
                if plu is None or price is None or articlename is None or season is None:
                    # WTF should never happen
                    print(f'Skipping invalid row data {position}')
                    continue
                pluregex = re.compile(r'^(\d+)').search(plu.strip())
                # This is how we easily determine wrong/invalid datarows
                if pluregex is None:
                    # Typically that is the table header
                    print(f'Skipping pos {position} because: Invalid plu data: {row}')
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
                # print('Writing file ' + filename)
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
    cs = CsvToQrcodesImagesScript()
    cs.main()
