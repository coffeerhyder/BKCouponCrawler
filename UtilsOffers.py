import os

from Helper import getFilenameFromURL, couponOrOfferGetImageURL, getPathImagesOffers, getDatetimeFromString, getCurrentDate


def offerGetImagePath(offer) -> str:
    """ Returns path to image of given offer. """
    uniqueOfferIDStr = str(offer['id'])
    offerImageFilename = uniqueOfferIDStr + "_" + getFilenameFromURL(couponOrOfferGetImageURL(offer))
    return getPathImagesOffers() + "/" + offerImageFilename


def offerGetImage(offer):
    path = offerGetImagePath(offer)
    if os.path.exists(path):
        return open(path, mode='rb')
    else:
        return None


def offerIsValid(offer) -> bool:
    """ Checks whether or not an offer has expired or is still valid.
    Returns true if no 'expiration_date' field is present. """
    expiration_date = offer.get('expiration_date')
    if expiration_date is None:
        return True
    else:
        return getDatetimeFromString(expiration_date) > getCurrentDate()
