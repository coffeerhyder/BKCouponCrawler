import os.path
import csv
import re
from os import listdir
from os.path import isfile, join

""" Quick and dirty script to delete all coupon images in folder "images" which are for coupons that are also available inside coupons.csv.
"""


class CleanCouponImagesBasedOnCouponsCSV:
    def __init__(self):
        pass

    def main(self):
        imagefolder = 'images'
        csvplus = []
        with open('coupons.csv', encoding='ANSI') as csvfile:
            csvreader = csv.DictReader(csvfile, dialect='excel',
                                      fieldnames=["PRODUCT", "MENU", "PLU", "PLU2", "TYPE", "PRICE", "PRICE_COMPARE", "START", "EXP"], delimiter=',')

            position = 0
            for row in csvreader:
                position += 1
                plu = row['PLU2'].strip()
                if plu is None:
                    # WTF should never happen
                    print(f'Skipping invalid row data {position}')
                    continue
                csvplus.append(plu)
        filenames = []
        for f in listdir(imagefolder):
            if isfile(join(imagefolder, f)):
                filenames.append(f)
        numberofDeletedFiles = 0
        imagesFolderPLUs = []
        for filename in filenames:
            pluFromFilename = re.compile(r'^(\d+)_').search(filename).group(1)
            if pluFromFilename in csvplus:
                filepath = join(imagefolder, filename)
                print('Deleting file: ' + filepath)
                os.remove(filepath)
                numberofDeletedFiles += 1
            else:
                imagesFolderPLUs.append(pluFromFilename)
        print(f'SUCCESS | Done | Number of deleted files in folder {imagefolder}: {numberofDeletedFiles}')
        return None


if __name__ == '__main__':
    cs = CleanCouponImagesBasedOnCouponsCSV()
    cs.main()
