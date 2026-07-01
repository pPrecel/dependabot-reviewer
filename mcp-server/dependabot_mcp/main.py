import logging
import asyncio
from .server import mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(mcp.run_async())
