"""Some globally used functions"""

import os
from typing import Tuple

import yaml  # type: ignore
from hashids import Hashids  # type: ignore

from sarad.logger import logger


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


def encode_instr_id(family_id: int, type_id: int, serial_number: int) -> str:
    """Make a unique string out of the three given values"""
    return f"{family_id}-{type_id}-{serial_number}"


def decode_instr_id(instr_id: str) -> Tuple:
    """Detect what kind of instr_id was presented and decode it accordingly
    into family_id, type_id and serial_number.

    Args:
        instr_id: instrument id identifying a SARAD instrument. This may bei
                  either a hash or a concatenation of three strings.
    Returns: tuple of family_id, type_id, serial_number
    """
    try:
        instr_id_tuple = Hashids().decode(instr_id)
        assert instr_id_tuple is not None
        assert len(instr_id_tuple) == 3
        return instr_id_tuple
    except (IndexError, AssertionError):
        try:
            instr_id_tuple = tuple(int(x) for x in instr_id.split("-"))
            assert len(instr_id_tuple) == 3
            return instr_id_tuple
        except AssertionError:
            logger().critical("Error decoding instr_id %s", instr_id)
            return ()


def get_sarad_type(instr_id) -> str:
    """Return the SARAD type from a given instr_id"""
    family_id = decode_instr_id(instr_id)[0]
    if family_id == 5:
        return "sarad-dacm"
    if family_id in [1, 2]:
        return "sarad-1688"
    return "unknown"
