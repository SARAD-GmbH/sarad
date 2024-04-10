"""Setup of logging function"""

import logging

_LOGGER = None


def logger():
    """Returns the logger instance used in this module."""
    global _LOGGER  # pylint: disable=global-statement
    _LOGGER = _LOGGER or logging.getLogger(__name__)
    return _LOGGER
