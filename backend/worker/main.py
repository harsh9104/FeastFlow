"""Order worker entry point. P3 adds: poll orders-prime first, then orders-standard,
assign a free delivery partner, publish SNS notifications."""

import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    log.info("worker started (placeholder until P3)")
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()
