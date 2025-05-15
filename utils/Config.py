from typing import Optional, List

import pydantic
from pydantic import model_validator


class Config(pydantic.BaseModel):
    bot_token: str
    bot_name: str
    db_url: str
    admin_ids: Optional[List]
    public_channel_name: Optional[str]
    public_channel_post_id_faq: Optional[int]

    @model_validator(mode='after')
    def check_config_values(self):
        """ https://docs.pydantic.dev/usage/validators/ """
        if self.public_channel_name is not None and self.public_channel_post_id_faq is None:
            raise ValueError(f'Bad config: public channel name is given: {self.public_channel_name=} and at the same time {self.public_channel_post_id_faq=} | Your public channel is expected to have a permanent postID stickied as a FAQ!')
        return self