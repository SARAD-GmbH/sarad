"""Definitions of used types"""

from typing import Any, Dict, List, Literal, TypedDict

from sarad.instrument import Component


class CmdDict(TypedDict):
    """Type declaration for the result of the analysis of a binary command message."""

    cmd: bytes
    data: bytes


class MeasurandDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for Measurand dictionary."""
    measurand_operator: str
    measurand_value: float
    measurand_unit: str
    valid: bool


class ComponentDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for Component type dictionary"""
    component_id: int
    component: Component


class FeatureDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for hardware and firmware dependent features"""
    since: int
    value: str


class InstrumentDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for instrument type dictionary."""
    type_id: int
    type_name: str
    fw_features: Dict[str, FeatureDict]
    hw_features: Dict[str, FeatureDict]
    components: List[ComponentDict]
    battery_bytes: int
    battery_coeff: float


class SerialDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for dictionary containing parameters of serial interface."""
    baudrate: int
    parity: Literal["N", "E"]


class FamilyDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for Family dictionary."""
    family_id: int
    family_name: str
    serial: SerialDict
    get_id_cmd: List[bytes]
    length_of_reply: int
    tx_msg_delay: float
    tx_byte_delay: float
    ok_byte: int
    config_parameters: List[Dict[str, Any]]
    types: List[InstrumentDict]
    byte_order: Literal["little", "big"]
    allowed_cmds: List[bytes]


class CheckedAnswerDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for checked reply from instrument."""
    is_valid: bool
    is_control: bool
    is_last_frame: bool
    cmd: bytes
    data: bytes
    payload: bytes
    number_of_bytes_in_payload: int
    raw: bytes
    standard_frame: bytes
