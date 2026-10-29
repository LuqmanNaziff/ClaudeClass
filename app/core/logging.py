import logging
import json
from typing import Any

LOGGER_NAME = "supportops"
logger = logging.getLogger(LOGGER_NAME)

def configure_logging(level: str) -> None:
    level_value = getattr(
        logging, 
        level.upper(), 
        logging.INFO
    )

    logger.setLevel(level_value)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)

    logger.propagate = False


def log_event(
    event: str,
    *,
    level: str = logging.INFO,        
    **fields: Any,
) -> None:
    payload = {
        "event": event,
        **fields,
    }

    logger.log(
        level,
        json.dumps(
            payload, 
            ensure_ascii=False,
            default=str,
            sort_keys=True
        ),
    )