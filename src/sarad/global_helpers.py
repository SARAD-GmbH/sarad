"""Some globally used functions"""

import logging
import os

import yaml  # type: ignore

from sarad.dacm import DacmInst
from sarad.doseman import DosemanInst
from sarad.network import NetworkInst
from sarad.radonscout import RscInst

_LOGGER = None

id_family_mapping = {1: DosemanInst(), 2: RscInst(), 4: NetworkInst, 5: DacmInst()}


def logger():
    """Returns the logger instance used in this module."""
    global _LOGGER  # pylint: disable=global-statement
    _LOGGER = _LOGGER or logging.getLogger(__name__)
    return _LOGGER


def sarad_family(family_id):
    """Get dict of product features from instrument.yaml file.

    products (Dict): Dictionary holding a database containing the features
    of all SARAD products that cannot be gained from the instrument itself.
    """
    try:
        with open(
            os.path.dirname(os.path.realpath(__file__))
            + os.path.sep
            + "instruments.yaml",
            "r",
            encoding="utf-8",
        ) as __f:
            products = yaml.safe_load(__f)
        for family in products:
            if family.get("family_id") == family_id:
                return family
    except Exception as exception:  # pylint: disable=broad-exception-caught
        logger().error("Cannot get products dict from instruments.yaml. %s", exception)
    return None
