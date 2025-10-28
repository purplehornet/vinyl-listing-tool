from __future__ import annotations
import logging, sys

def setup_logging(log_name: str = "vinyltool", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(log_name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(h)
    return logger
