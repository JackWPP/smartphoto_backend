import logging
from pythonjsonlogger import jsonlogger


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)

    root.setLevel(logging.INFO)
    root.addHandler(handler)
