from __future__ import annotations

import uuid

from pydantic import BaseModel


class CancelRunOut(BaseModel):
    run_id: uuid.UUID
