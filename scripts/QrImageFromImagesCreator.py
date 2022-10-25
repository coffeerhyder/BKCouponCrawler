import os.path
import re
from os import listdir
from os.path import isfile, join

import qrcode


""" Creates QR codes for all files in folder "images" in the following format: plu_blabla.ext. Example: 1234_Productname.png
"""
class QrImageFromImagesCreator:
    def __init__(self):
        pass

    def main(self):
        imagefolder = 'images'
        if not os.path.exists(imagefolder):
            print(f"Folder {imagefolder} does not exist -> Cannot do anything")
            return
        filenames = []
        for f in listdir(imagefolder):
            if isfile(join(imagefolder, f)):
                filenames.append(f)
        numberofCreatedQRCodeImages = 0
        numberofSkippedFiles = 0
        numberofSkippedQRCodeFiles = 0
        for filename in filenames:
            if '.' not in filename:
                print("Skipping invalid file:" + filename)
                numberofSkippedFiles += 1
                continue
            filenameWithoutExt = filename[0:filename.rindex('.')]
            pluregex = re.compile(r'^(\d+)_').search(filename)
            if pluregex is None:
                print("Skipping invalid file: " + filename)
                numberofSkippedFiles += 1
                continue
            plu = pluregex.group(1)
            # Now save file with same
            qrFilename = filenameWithoutExt + '_QR' + '.png'
            qrFilepath = join(imagefolder, qrFilename)
            if os.path.isfile(qrFilepath):
                print("Skipping already existing QR image: " + qrFilepath)
                numberofSkippedQRCodeFiles += 1
                continue
            # print('Writing file' + qrFilepath)
            qr = qrcode.QRCode(
                version=1,
                # 2021-05-02: This makes the image itself bigger but due to the border and the resize of Telegram, these QR codes might be suited better for usage in Telegram
                border=10
            )
            qr.add_data(plu)
            """ 2021-01-25: Use the same color they're using in their app. """
            img = qr.make_image(fill_color="#4A1E0D", back_color="white")
            img.save(qrFilepath)
            numberofCreatedQRCodeImages += 1
        print(f'Number of created QR code images: {numberofCreatedQRCodeImages}')
        if numberofSkippedFiles > 0:
            print(f'Number of skipped files: {numberofSkippedFiles}')
        if numberofSkippedQRCodeFiles > 0:
            print(f'Number of skipped QR code files: {numberofSkippedQRCodeFiles}')


if __name__ == '__main__':
    cs = QrImageFromImagesCreator()
    cs.main()
