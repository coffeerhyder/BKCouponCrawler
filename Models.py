from pydantic import BaseModel
from typing import Optional, List, Union

from UtilsCouponsDB import CouponSortMode


class CouponFilter(BaseModel):
    activeOnly: Optional[bool] = True
    containsFriesAndCoke: Optional[Union[bool, None]] = None
    excludeCouponsByDuplicatedProductTitles: Optional[bool] = False
    allowedCouponSources: Optional[Union[List[int], None]] = None  # None = allow all sources!
    isNew: Optional[Union[bool, None]] = None
    isHidden: Optional[Union[bool, None]] = None
    sortMode: Optional[Union[None, CouponSortMode]]
