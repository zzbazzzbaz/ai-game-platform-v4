from __future__ import annotations

import asyncio
import logging

from app.job.reaper import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
