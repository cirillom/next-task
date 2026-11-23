"""Standalone background notifier worker process."""

import logging
import signal
import threading

from app.config import get_settings
from app.database import SessionLocal
from app.services.notifications import run_notifier_once

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_args: stop.set())

    interval = max(5, get_settings().notifier_interval_seconds)
    logger.info("Starting notifier worker (interval=%ss)", interval)
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                run_notifier_once(db)
        except Exception:
            logger.exception("Notifier tick failed")
        stop.wait(interval)


if __name__ == "__main__":
    main()
