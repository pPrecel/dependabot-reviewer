import logging
from .server import mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")
