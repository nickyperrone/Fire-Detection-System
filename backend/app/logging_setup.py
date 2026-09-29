import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # httpx logs every request URL at INFO, and the FIRMS URL contains the map key.
    logging.getLogger("httpx").setLevel(logging.WARNING)
