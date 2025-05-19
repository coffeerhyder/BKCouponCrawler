import logging
from datetime import datetime

import couchdb
from typing import Dict

from utils.UtilsCouponsDB import removeDuplicatedCoupons, sortCoupons
from models.ChannelCoupon import ChannelCoupon
from utils.Config import Config
from utils.UserStats import UserStats
from models.Coupon import Coupon
from models.InfoEntry import InfoEntry
from models.User import User
from Helper import DATABASES
from utils.Filters import CouponFilter
from typing import Optional, Union, List, Set


class DBManager:

    def __init__(self, cfg: Config):
        self.cfg = cfg
        # Connect to CouchDB
        self.couchdb = couchdb.Server(self.cfg.db_url)
        # Ensure all required databases exist
        self._ensure_required_databases()

    def _ensure_required_databases(self):
        """Create all required databases if they don't exist."""
        required_dbs = [
            DATABASES.INFO_DB,
            DATABASES.TELEGRAM_USERS,
            DATABASES.COUPONS,
            DATABASES.OFFERS,
            DATABASES.PRODUCTS,
            DATABASES.TELEGRAM_CHANNEL
        ]

        for db_name in required_dbs:
            if db_name not in self.couchdb:
                logging.info(f"Creating missing DB: {db_name}")
                db = self.couchdb.create(db_name)

                # Special case for info DB
                if db_name == DATABASES.INFO_DB:
                    if DATABASES.INFO_DB not in db:
                        infoDoc = InfoEntry(id=DATABASES.INFO_DB)
                        infoDoc.store(db)

    # Database access methods
    def get_coupon_db(self):
        """Get the coupons database."""
        return self.couchdb[DATABASES.COUPONS]

    def get_offer_db(self):
        """Get the offers database."""
        return self.couchdb[DATABASES.OFFERS]

    def get_user_db(self):
        """Get the users database."""
        return self.couchdb[DATABASES.TELEGRAM_USERS]

    def get_info_db(self):
        """Get the info database."""
        return self.couchdb[DATABASES.INFO_DB]

    def get_products_db(self):
        """Get the products database."""
        return self.couchdb[DATABASES.PRODUCTS]

    def get_telegram_channel_db(self):
        """Get the telegram channel database."""
        return self.couchdb[DATABASES.TELEGRAM_CHANNEL]

    def get_channel_coupon(self, channel_coupon_id: str) -> Optional["ChannelCoupon"]:
        """Get a channel coupon by ID from the telegram channel database."""
        return ChannelCoupon.load(self.get_telegram_channel_db(), channel_coupon_id)

    def save_channel_coupon(self, channel_coupon_input: Union["ChannelCoupon", List["ChannelCoupon"], Set["ChannelCoupon"]]) -> None:
        """
        Save channel coupon(s) to the telegram channel database.

        Args:
            channel_coupon_input: Can be one of:
                - ChannelCoupon: A single ChannelCoupon object to save
                - List[ChannelCoupon]: Multiple ChannelCoupon objects to save
                - Set[ChannelCoupon]: Multiple ChannelCoupon objects to save (will be converted to list)
        """
        channel_db = self.get_telegram_channel_db()

        # Case 1: Single ChannelCoupon object
        if isinstance(channel_coupon_input, ChannelCoupon):
            channel_coupon_input.store(channel_db)

        # Case 2: List of ChannelCoupon objects
        elif isinstance(channel_coupon_input, list) and all(isinstance(c, ChannelCoupon) for c in channel_coupon_input):
            # Push all changes at once
            channel_db.update(channel_coupon_input)

        # Case 3: Set of ChannelCoupon objects
        elif isinstance(channel_coupon_input, set) and all(isinstance(c, ChannelCoupon) for c in channel_coupon_input):
            # Convert set to list and push all changes at once
            channel_db.update(list(channel_coupon_input))

        else:
            raise TypeError("Expected ChannelCoupon object, list of ChannelCoupon objects, or set of ChannelCoupon objects")

    def delete_channel_coupons(self, channel_coupon_input: Union[str, "ChannelCoupon", List[Union[str, "ChannelCoupon"]], Set[Union[str, "ChannelCoupon"]]]) -> None:
        """
        Delete channel coupon(s) from the telegram channel database.

        Args:
            channel_coupon_input: Can be one of:
                - str: The ID of a channel coupon to delete
                - ChannelCoupon: A ChannelCoupon object to delete
                - List[str/ChannelCoupon]: Multiple channel coupon IDs or objects to delete
                - Set[str/ChannelCoupon]: Multiple channel coupon IDs or objects to delete
        """
        channel_db = self.get_telegram_channel_db()

        # Case 1: Single channel coupon ID as string
        if isinstance(channel_coupon_input, str):
            if channel_coupon_input in channel_db:
                del channel_db[channel_coupon_input]

        # Case 2: Single ChannelCoupon object
        elif isinstance(channel_coupon_input, ChannelCoupon):
            if channel_coupon_input.id in channel_db:
                del channel_db[channel_coupon_input.id]

        # Case 3: List or Set of channel coupon IDs or ChannelCoupon objects
        elif isinstance(channel_coupon_input, (list, set)):
            delete_docs = {}

            for channel_coupon in channel_coupon_input:
                channel_coupon_id = channel_coupon if isinstance(channel_coupon, str) else channel_coupon.id
                if channel_coupon_id in channel_db:
                    # Get the document and its current revision
                    delete_docs[channel_coupon_id] = channel_db[channel_coupon_id]

            # Delete all channel coupons in one operation if there are any to delete
            if delete_docs:
                channel_db.purge(delete_docs.values())

        else:
            raise TypeError("Expected channel coupon ID (str), ChannelCoupon object, or list/set of channel coupon IDs/objects")

    def get_channel_coupons(self) -> List["ChannelCoupon"]:
        """Get all channel coupons from the telegram channel database."""
        channel_coupons = []
        channel_db = self.get_telegram_channel_db()
        for channel_coupon_id in channel_db:
            channel_coupon = ChannelCoupon.load(channel_db, channel_coupon_id)
            channel_coupons.append(channel_coupon)
        return channel_coupons

    # Coupon operations
    def get_coupon(self, coupon_id: str) -> Optional[Coupon]:
        return Coupon.load(self.get_coupon_db(), coupon_id)

    from typing import Union, List, Set

    def save_coupon(self, coupon_input: Union[Coupon, List[Coupon], Set[Coupon]]) -> None:
        """
        Save coupon(s) to the database.

        Args:
            coupon_input: Can be one of:
                - Coupon: A single Coupon object to save
                - List[Coupon]: Multiple Coupon objects to save
                - Set[Coupon]: Multiple Coupon objects to save (will be converted to list)
        """
        coupon_db = self.get_coupon_db()

        # Case 1: Single Coupon object
        if isinstance(coupon_input, Coupon):
            coupon_input.store(coupon_db)

        # Case 2: List of Coupon objects
        elif isinstance(coupon_input, list) and all(isinstance(c, Coupon) for c in coupon_input):
            # Push all changes at once
            coupon_db.update(coupon_input)

        # Case 3: Set of Coupon objects
        elif isinstance(coupon_input, set) and all(isinstance(c, Coupon) for c in coupon_input):
            # Convert set to list and push all changes at once
            coupon_db.update(list(coupon_input))

        else:
            raise TypeError("Expected Coupon object, list of Coupon objects, or set of Coupon objects")

    def delete_coupon(self, coupon_input: Union[str, Coupon, List[Union[str, Coupon]], Set[Union[str, Coupon]]]) -> None:
        """
        Delete coupon(s) from the database.

        Args:
            coupon_input: Can be one of:
                - str: The ID of a coupon to delete
                - Coupon: A Coupon object to delete
                - List[str/Coupon]: Multiple coupon IDs or objects to delete
                - Set[str/Coupon]: Multiple coupon IDs or objects to delete
        """
        coupon_db = self.get_coupon_db()

        # Case 1: Single coupon ID as string
        if isinstance(coupon_input, str):
            if coupon_input in coupon_db:
                del coupon_db[coupon_input]

        # Case 2: Single Coupon object
        elif isinstance(coupon_input, Coupon):
            if coupon_input.id in coupon_db:
                del coupon_db[coupon_input.id]

        # Case 3: List of coupon IDs or Coupon objects
        elif isinstance(coupon_input, (list, set)):
            delete_docs = {}

            for coupon in coupon_input:
                coupon_id = coupon if isinstance(coupon, str) else coupon.id
                if coupon_id in coupon_db:
                    # Get the document and its current revision
                    delete_docs[coupon_id] = coupon_db[coupon_id]

            # Delete all coupons in one operation if there are any to delete
            if delete_docs:
                coupon_db.purge(delete_docs.values())

        else:
            raise TypeError("Expected coupon ID (str), Coupon object, or list/set of coupon IDs/objects")

    def get_coupons(self) -> List[Coupon]:
        coupons = []
        coupon_db = self.get_coupon_db()
        for coupon_id in coupon_db:
            coupon = Coupon.load(coupon_db, coupon_id)
            coupons.append(coupon)
        return coupons

    def get_filtered_coupons_as_dict(
            self, coupon_filter: CouponFilter, sort_if_sort_code_given: bool = True
    ) -> Dict[str, Coupon]:
        coupon_db = self.get_coupon_db()
        desired_coupons = {}
        cf = coupon_filter
        # Log if developer is trying to use stupid filters
        if cf.isVeggie is False and cf.isPlantBased is True:
            logging.warning(f'Bad filter params: {cf.isVeggie=} and {cf.isPlantBased=}')
        elif cf.isMeat and (cf.isPlantBased or cf.isVeggie):
            logging.warning(f'Bad filter params: meat && veggie')

        for coupon_id in coupon_db:
            coupon = Coupon.load(coupon_db, coupon_id)

            # Apply filters
            if cf.activeOnly and not coupon.isValid():
                continue
            elif cf.isNotYetActive is not None and coupon.isNotYetActive() != cf.isNotYetActive:
                continue
            elif cf.allowedCouponTypes is not None and coupon.type not in cf.allowedCouponTypes:
                continue
            elif cf.containsFriesAndCoke is not None and coupon.isContainsFriesAndDrink() != cf.containsFriesAndCoke:
                continue
            elif cf.isNew is not None and coupon.isNewCoupon() != cf.isNew:
                continue
            elif cf.isHidden is not None and coupon.isHidden != cf.isHidden:
                continue
            elif cf.isEatable is not None and coupon.isEatable() != cf.isEatable:
                continue
            if cf.isMeat and coupon.isContainsMeat() != cf.isMeat:
                # print(f"Filtered non meat:{coupon.id} | {coupon.getTitle()}")
                continue
            elif cf.isVeggie is not None and coupon.isVeggie() != cf.isVeggie:
                # print(f"Filtered non veggie:{coupon.id} | {coupon.getTitle()}")
                continue
            elif cf.isPlantBased is not None and coupon.isPlantBased() != cf.isPlantBased:
                # print(f"Filtered non plant based:{coupon.id} | {coupon.getTitle()}")
                continue

            desired_coupons[coupon_id] = coupon

        # Remove duplicates if needed
        if cf.removeDuplicates is True and (
                cf.allowedCouponTypes is None or (
                cf.allowedCouponTypes is not None and
                len(cf.allowedCouponTypes) > 1
        )):
            desired_coupons = removeDuplicatedCoupons(desired_coupons)

        # Sort if requested
        if cf.sortCode is not None and sort_if_sort_code_given:
            filtered_and_sorted_coupons = sortCoupons(desired_coupons, cf.sortCode)
            return filtered_and_sorted_coupons
        else:
            return desired_coupons

    def get_filtered_coupons_as_list(
            self, coupon_filter: CouponFilter, sort_if_sort_code_given: bool = True
    ) -> List[Coupon]:
        filtered_coupons_dict = self.get_filtered_coupons_as_dict(
            coupon_filter, sort_if_sort_code_given=sort_if_sort_code_given
        )
        return list(filtered_coupons_dict.values())

    # User operations
    def get_user(self, user_id: Union[str, int]) -> Optional[User]:
        user_id = str(user_id)
        return User.load(self.get_user_db(), user_id)

    from typing import Union, Set

    def save_user(self, user_input: Union[User, List[User], Set[User]]) -> None:
        """
        Save user(s) to the database.

        Args:
            user_input: Can be one of:
                - User: A single User object to save
                - List[User]: Multiple User objects to save
                - Set[User]: Multiple User objects to save (will be converted to list)
        """
        user_db = self.get_user_db()

        # Case 1: Single User object
        if isinstance(user_input, User):
            user_input.store(user_db)

        # Case 2: List of User objects
        elif isinstance(user_input, list) and all(isinstance(u, User) for u in user_input):
            # Push all changes at once
            user_db.update(user_input)

        # Case 3: Set of User objects
        elif isinstance(user_input, set) and all(isinstance(u, User) for u in user_input):
            # Convert set to list and push all changes at once
            user_db.update(list(user_input))

        else:
            raise TypeError("Expected User object, list of User objects, or set of User objects")

    def delete_user(self, user_id: Union[User, str, int]) -> None:
        # Extract the user ID if a User object was provided
        user_id_str = user_id.id if isinstance(user_id, User) else str(user_id)

        # Get the database
        user_db = self.get_user_db()

        # Check if the user exists in the database
        if user_id_str in user_db:
            # Delete the user from the database
            del user_db[user_id_str]

    def get_users(self, withPendingNotifications: bool = None) -> List[User]:
        users = []
        user_db = self.get_user_db()
        for user_id in user_db:
            user = User.load(user_db, user_id)
            if withPendingNotifications and (user.pendingNotifications is None or len(user.pendingNotifications) == 0):
                continue
            users.append(user)
        return users

    def get_user_stats(self):
        return UserStats(self.get_user_db())

    # Info DB operations
    def get_info_entry(self) -> InfoEntry:
        return InfoEntry.load(self.get_info_db(), DATABASES.INFO_DB)

    def save_info_entry(self, info_entry: InfoEntry) -> None:
        info_entry.store(self.get_info_db())

    def update_last_successful_crawl(self) -> None:
        info_db = self.get_info_db()
        info_doc = InfoEntry.load(info_db, DATABASES.INFO_DB)
        info_doc.dateLastSuccessfulCrawlRun = datetime.now()
        info_doc.store(info_db)
