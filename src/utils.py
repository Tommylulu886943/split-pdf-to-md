import logging
import re
import sys


def setup_logging(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("split-pdf")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger


def sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames, collapse whitespace to underscore."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f/]', "", name)
    name = name.replace("..", "")
    name = re.sub(r"\s+", "_", name.strip())
    return name or "unnamed"
