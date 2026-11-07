from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WorkerHealthOut(BaseModel):
    status: Literal["active", "inactive"]
    active_workers: int
    checked_at: datetime
