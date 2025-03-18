from typing import Optional, Union, List

from pydantic import BaseModel


class CouponFilter(BaseModel):
    """ removeDuplicates: Enable to filter duplicated coupons for same products - only returns cheapest of all
     If the same product is available as paper- and app coupon, App coupon is preferred."""
    activeOnly: Optional[bool] = True
    isNotYetActive: Optional[Union[bool, None]] = None
    containsFriesAndCoke: Optional[Union[bool, None]] = None
    # Enable to filter duplicated coupons for same products - only returns cheapest of all
    removeDuplicates: Optional[Union[bool, None]] = None
    allowedCouponTypes: Optional[Union[List[int], None]] = None  # None = allow all sources!
    isNew: Optional[Union[bool, None]] = None
    isHidden: Optional[Union[bool, None]] = None
    isVeggie: Optional[Union[bool, None]] = None
    isPlantBased: Optional[Union[bool, None]] = None
    isEatable: Optional[Union[bool, None]] = None
    sortCode: Optional[Union[None, int]]
