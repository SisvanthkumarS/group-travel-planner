from typing import Literal

from pydantic import BaseModel


class TestEmailResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    message_id: str
