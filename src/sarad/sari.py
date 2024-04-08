"""Abstract class for all SARAD instruments

SaradInst comprises all attributes and methods
that all SARAD instruments have in common."""

import logging
import os
import struct
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from time import sleep
from typing import (Any, Collection, Dict, Generic, Iterator, List, Literal,
                    Optional, TypedDict, TypeVar)

import yaml  # type: ignore
from BitVector import BitVector  # type: ignore
from serial import STOPBITS_ONE  # type: ignore
from serial import PARITY_EVEN, PARITY_NONE, Serial, SerialException

_LOGGER = None


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


SI = TypeVar("SI", bound="SaradInst")


@dataclass
class Route:
    """Class to store the route directing to a SaradInst.

    rs485_address and zigbee_address are optional and may be None for the
    simple case that SardInst is directly and exclusively connected to a serial
    port.

    Args:
        port (str): Name of the serial port
        rs485_address (int): RS-485 bus address. None, if RS-485 addressing is not used.
        zigbee_address (int): Address of instrument on NETmonitors coordinator.
                              None, if ZigBee is not used.

    """

    port: Optional[str]
    rs485_address: Optional[int]
    zigbee_address: Optional[int]


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
    component_name: str


class InstrumentDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for instrument type dictionary."""
    type_id: int
    type_name: str
    components: List[ComponentDict]
    battery_bytes: int
    battery_coeff: float


class FamilyDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for Family dictionary."""
    family_id: int
    family_name: str
    baudrate: List[int]
    get_id_cmd: List[bytes]
    length_of_reply: int
    tx_msg_delay: float
    tx_byte_delay: float
    parity: str
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
    payload: bytes
    number_of_bytes_in_payload: int
    raw: bytes
    standard_frame: bytes


class Measurand:  # pylint: disable=too-many-instance-attributes
    """Class providing a measurand that is delivered by a sensor.

    Properties:
        id
        name
        operator
        value
        unit
        source
        time
        gps"""

    def __init__(
        self,
        measurand_id: int,
        measurand_name: str,
        measurand_unit=None,
        measurand_source=None,
    ) -> None:
        self.__id: int = measurand_id
        self.__name: str = measurand_name
        if measurand_unit is not None:
            self.__unit: str = measurand_unit
        else:
            self.__unit = ""
        if measurand_source is not None:
            self.__source: int = measurand_source
        else:
            self.__source = 0
        self.__value: Optional[float] = None
        self.__time: datetime = datetime.min
        self.__operator: str = ""
        self.__gps: str = ""

    def __str__(self) -> str:
        output = f"MeasurandId: {self.measurand_id}\nMeasurandName: {self.name}\n"
        if self.value is not None:
            output += f"Value: {self.operator} {self.value} {self.unit}\n"
            output += f"Time: {self.time}\n"
            output += f"GPS: {self.gps}\n"
        else:
            output += f"MeasurandUnit: {self.unit}\n"
            output += f"MeasurandSource: {self.source}\n"
        return output

    @property
    def measurand_id(self) -> int:
        """Return the Id of this measurand."""
        return self.__id

    @measurand_id.setter
    def measurand_id(self, measurand_id: int) -> None:
        """Set the Id of this measurand."""
        self.__id = measurand_id

    @property
    def name(self) -> str:
        """Return the name of this measurand."""
        return self.__name

    @name.setter
    def name(self, name: str) -> None:
        """Set the name of this measurand."""
        self.__name = name

    @property
    def unit(self) -> str:
        """Return the physical unit of this measurand."""
        return self.__unit

    @unit.setter
    def unit(self, unit: str) -> None:
        """Set the physical unit of this measurand."""
        self.__unit = unit

    @property
    def source(self) -> int:
        """Return the source index belonging to this measurand.

        This index marks the position the measurand can be found in the
        list of recent values provided by the instrument
        as reply to the GetComponentResult or _gather_all_recent_values
        commands respectively."""
        return self.__source

    @source.setter
    def source(self, source: int) -> None:
        """Set the source index."""
        self.__source = source

    @property
    def operator(self) -> str:
        """Return the operator belonging to this measurand.

        Typical operators are '<', '>'"""
        return self.__operator

    @operator.setter
    def operator(self, operator: str) -> None:
        """Set the operator of this measurand."""
        self.__operator = operator

    @property
    def value(self) -> Optional[float]:
        """Return the value of the measurand."""
        return self.__value

    @value.setter
    def value(self, value: Optional[float]) -> None:
        """Set the value of the measurand."""
        self.__value = value

    @property
    def time(self) -> datetime:
        """Return the aquisition time (timestamp) of the measurand."""
        return self.__time

    @time.setter
    def time(self, time_stamp: datetime) -> None:
        """Set the aquisition time (timestamp) of the measurand."""
        self.__time = time_stamp

    @property
    def gps(self) -> str:
        """Return the GPS string of the measurand."""
        return self.__gps

    @gps.setter
    def gps(self, gps: str) -> None:
        """Set the GPS string of the measurand."""
        self.__gps = gps


class Sensor:
    """Class describing a sensor that is part of a component.

    Properties:
        id
        name
        interval: Measuring interval in seconds
    Public methods:
        get_measurands()"""

    def __init__(self, sensor_id: int, sensor_name: str) -> None:
        self.__id: int = sensor_id
        self.__name: str = sensor_name
        self.__interval: timedelta = timedelta(0)
        self.__measurands: List[Measurand] = []

    def __iter__(self):
        return iter(self.__measurands)

    def __str__(self) -> str:
        output = (
            f"SensorId: {self.sensor_id}\nSensorName: {self.name}\n"
            f"SensorInterval: {self.interval}\nMeasurands:\n"
        )
        for measurand in self.measurands:
            output += f"{measurand}\n"
        return output

    @property
    def sensor_id(self) -> int:
        """Return the Id of this sensor."""
        return self.__id

    @sensor_id.setter
    def sensor_id(self, sensor_id: int) -> None:
        """Set the Id of this sensor."""
        self.__id = sensor_id

    @property
    def name(self) -> str:
        """Return the name of this sensor."""
        return self.__name

    @name.setter
    def name(self, name: str) -> None:
        """Set the name of this sensor."""
        self.__name = name

    @property
    def interval(self) -> timedelta:
        """Return the measuring interval of this sensor."""
        return self.__interval

    @interval.setter
    def interval(self, interval: timedelta):
        """Set the measuring interval of this sensor."""
        self.__interval = interval

    @property
    def measurands(self) -> List[Measurand]:
        """Return the list of measurands of this sensor."""
        return self.__measurands

    @measurands.setter
    def measurands(self, measurands: List[Measurand]):
        """Set the list of measurands of this sensor."""
        self.__measurands = measurands


class Component:
    """Class describing a sensor or actor component built into an instrument"""

    def __init__(self, component_id: int, component_name: str) -> None:
        self.__id: int = component_id
        self.__name: str = component_name
        self.__sensors: List[Sensor] = []

    def __iter__(self):
        return iter(self.__sensors)

    def __str__(self) -> str:
        output = (
            f"ComponentId: {self.component_id}\n"
            f"ComponentName: {self.name}\nSensors:\n"
        )
        for sensor in self.sensors:
            output += f"{sensor}\n"
        return output

    @property
    def component_id(self) -> int:
        """Return the Id of this component."""
        return self.__id

    @component_id.setter
    def component_id(self, component_id: int) -> None:
        """Set the Id of this component."""
        self.__id = component_id

    @property
    def name(self) -> str:
        """Return the name of this component."""
        return self.__name

    @name.setter
    def name(self, name: str):
        """Set the component name."""
        self.__name = name

    @property
    def sensors(self) -> List[Sensor]:
        """Return the list of sensors belonging to this component."""
        return self.__sensors

    @sensors.setter
    def sensors(self, sensors: List[Sensor]):
        """Set the list of sensors belonging to this component."""
        self.__sensors = sensors


class SaradInst(Generic[SI]):
    """Basic class for the serial communication protocol of SARAD instruments

    Properties:
        route: Route dataclass object containing the serial communication port,
               RS-485 bus address and ZigBee address if applicable
        family: Device family of the instrument expected to be at this port
        device_id: Identifier for an individual instrument in a cluster
        type_id: Together with family, this Id identifys the instrument type.
        type_name: Identifys the instrument type.
        software_version: The version of the firmware.
        serial_number: Serial number of the connected instrument.
        components: List of sensor or actor components
    """

    CHANNELSELECTED = 0xD2

    class Lock(Enum):
        """Setting of the device. Lock the hardware button."""

        UNLOCKED: int = 1
        LOCKED: int = 2

    class RadonMode(Enum):
        """Setting of the device. Displayed radon values based on
        short living progeny only (fast)
        or on short and long living progeny (slow)"""

        SLOW: int = 1
        FAST: int = 2

    class PumpMode(Enum):
        """Setting of the devices having a pump."""

        CONTINUOUS: int = 1
        INTERVAL: int = 2

    class Units(Enum):
        """Setting of the device. Unit system used for display."""

        SI: int = 1
        US: int = 2

    class Signal(Enum):
        """Setting of the device. When shall it give an audible signal?"""

        OFF: int = 1
        ALARM: int = 2
        SNIFFER_PO216: int = 3
        PO216_PO218: int = 4

    class ChamberSize(Enum):
        """Setting the chamber size (Radon Scout PMT only)."""

        SMALL: int = 1
        MEDIUM: int = 2
        LARGE: int = 3
        XL: int = 4

    def __init__(self: SI, family: FamilyDict) -> None:
        self._route: Route = Route(port=None, rs485_address=None, zigbee_address=None)
        self._family: FamilyDict = family
        self.__ser = None
        self.__components: Collection[Component] = []
        self._type_id: int = 0
        self._software_version: int = 0
        self._serial_number: int = 0
        self.signal = self.Signal.OFF
        self.radon_mode = self.RadonMode.SLOW
        self.pump_mode = self.PumpMode.CONTINUOUS
        self.units = self.Units.SI
        self.chamber_size = self.ChamberSize.SMALL
        self.lock = self.Lock.UNLOCKED
        self.__id: str = ""
        self._valid_family = True
        self._last_sampling_time = None
        self._possible_baudrates: deque = deque(family["baudrate"])
        self._allowed_cmds = family.get("allowed_cmds", [])

    def __iter__(self) -> Iterator[Component]:
        return iter(self.__components)

    def __hash__(self):
        return hash(self.device_id)

    def __eq__(self, other):
        if isinstance(other, SaradInst):
            return self.device_id == other.device_id
        if isinstance(other, str):
            return other == self.device_id
        return False

    @staticmethod
    def _make_command_msg(cmd_data: List[bytes]) -> bytes:
        """Encode the message to be sent to the SARAD instrument.

        Arguments are the one byte long command
        and the data bytes to be sent."""
        cmd: bytes = cmd_data[0]
        data: bytes = cmd_data[1]
        payload: bytes = cmd + data
        control_byte = len(payload) - 1
        if cmd:  # Control message
            control_byte = control_byte | 0x80  # set Bit 7
        neg_control_byte = control_byte ^ 0xFF
        checksum = 0
        for byte in payload:
            checksum = checksum + byte
        checksum_bytes = (checksum).to_bytes(2, byteorder="little")
        return (
            b"B"
            + bytes([control_byte])
            + bytes([neg_control_byte])
            + payload
            + checksum_bytes
            + b"E"
        )

    @staticmethod
    def _analyze_cmd_data(payload: bytes) -> CmdDict:
        payload_list = list(payload)
        if len(payload_list) > 1:
            data = bytes(payload_list[1:])
        else:
            data = b""
        return {"cmd": bytes(payload_list[0:1]), "data": data}

    def select_zigbee_channel(self, channel_idx):
        """Start the transparent mode to given channel."""
        reply = self.get_reply([b"\xC2", channel_idx.to_bytes(2, "little")], timeout=3)
        if reply and (reply[0] == self.CHANNELSELECTED):
            logger().info("Channel selected: %s", reply)
            return reply
        logger().error("Unexpecte reply to select_channel: %s", reply)
        return False

    def close_zigbee_channel(self):
        """Leave the transparent mode."""
        reply = self.get_reply([b"\xC2", b"\x00\x00"], timeout=3)
        if reply and (reply[0] == self.CHANNELSELECTED):
            return reply
        logger().error("Unexpecte reply to close_channel: %s", reply)
        return False

    def zigbee_coordinator_reset(self):
        """Restart the coordinator. Same as power off -> on."""
        reply = self.get_reply([b"\xFE", b"\x00\x00"], timeout=3)
        if reply and (reply[0] == self.CHANNELSELECTED):
            return reply
        logger().error("Unexpecte reply to coordinator_reset: %s", reply)
        return False

    def _check_message(self, message: bytes, multiframe: bool) -> CheckedAnswerDict:
        # pylint: disable=too-many-locals
        """Check the message

        Returns a dictionary of:
        is_valid: True if message is valid, False otherwise
        is_control_message: True if control message
        payload: Payload of message
        number_of_bytes_in_payload
        """
        if (self._route.rs485_address is None) or (self._route.rs485_address == 0):
            return self._check_standard_message(message, multiframe)
        return self._check_rs485_message(message, multiframe, self._route.rs485_address)

    def _check_standard_message(
        self, answer: bytes, multiframe: bool
    ) -> CheckedAnswerDict:
        if answer.startswith(b"B") and answer.endswith(b"E"):
            control_byte = answer[1]
            control_byte_ok = bool((control_byte ^ 0xFF) == answer[2])
            number_of_bytes_in_payload = (control_byte & 0x7F) + 1
            is_control = bool(control_byte & 0x80)
            _status_byte = answer[3]
            payload = answer[3 : 3 + number_of_bytes_in_payload]
            calculated_checksum = 0
            for byte in payload:
                calculated_checksum = calculated_checksum + byte
            received_checksum_bytes = answer[
                3 + number_of_bytes_in_payload : 5 + number_of_bytes_in_payload
            ]
            received_checksum = int.from_bytes(
                received_checksum_bytes, byteorder="little", signed=False
            )
            is_valid = bool(
                control_byte_ok and (received_checksum == calculated_checksum)
            )
            # is_rend is True if this is the last frame of a multiframe reply
            # (DOSEman data download)
            is_rend = bool(is_valid and is_control and (payload == b"\x04"))
            return {
                "is_valid": is_valid,
                "is_control": is_control,
                "is_last_frame": (not multiframe) or is_rend,
                "payload": payload,
                "number_of_bytes_in_payload": number_of_bytes_in_payload,
                "raw": answer,
                "standard_frame": self._rs485_filter(answer),
            }
        logger().debug("Invalid B-E frame")
        return {
            "is_valid": False,
            "is_control": False,
            "is_last_frame": True,
            "payload": b"",
            "number_of_bytes_in_payload": 0,
            "raw": answer,
            "standard_frame": self._rs485_filter(answer),
        }

    def _check_rs485_message(
        self, answer: bytes, multiframe: bool, rs485_address
    ) -> CheckedAnswerDict:
        # pylint: disable=too-many-locals
        """Check a RS-485 message

        Returns a dictionary of:
        is_valid: True if answer is valid, False otherwise
        is_control_message: True if control message
        payload: Payload of answer
        number_of_bytes_in_payload
        """
        if answer.startswith(b"b") and answer.endswith(b"E"):
            address_ok = bool(answer[1] == rs485_address)
            control_byte = answer[2]
            control_byte_ok = bool((control_byte ^ 0xFF) == answer[3])
            number_of_bytes_in_payload = (control_byte & 0x7F) + 1
            is_control = bool(control_byte & 0x80)
            payload = answer[4 : 4 + number_of_bytes_in_payload]
            calculated_checksum = 0
            for byte in payload:
                calculated_checksum = calculated_checksum + byte
            received_checksum_bytes = answer[
                4 + number_of_bytes_in_payload : 6 + number_of_bytes_in_payload
            ]
            received_checksum = int.from_bytes(
                received_checksum_bytes, byteorder="little", signed=False
            )
            checksum_ok = bool(received_checksum == calculated_checksum)
            is_valid = bool(control_byte_ok and checksum_ok and address_ok)
        else:
            logger().debug("Invalid b-E frame")
            is_valid = False
        if not is_valid:
            is_control = False
            payload = b""
            number_of_bytes_in_payload = 0
        # is_rend is True if that this is the last frame of a multiframe reply
        # (DOSEman data download)
        is_rend = bool(is_valid and is_control and (payload == b"\x04"))
        return {
            "is_valid": is_valid,
            "is_control": is_control,
            "is_last_frame": (not multiframe) or is_rend,
            "payload": payload,
            "number_of_bytes_in_payload": number_of_bytes_in_payload,
            "raw": answer,
            "standard_frame": self._rs485_filter(answer),
        }

    def _rs485_filter(self, frame):
        """Convert an addressed RS-485 'b-E' frame into a normal 'B-E' frame

        by simply replacing the first two bytes with 'B'."""
        if (self.route.rs485_address is None) or (self.route.rs485_address == 0):
            return frame
        frame_list = list(frame)
        frame_list[0:2] = [66]  # replace "bx\??" by "B"
        return bytes(frame_list)

    def _make_rs485(self, frame):
        """Convert a normal 'B-E' frame into an addressed 'b-E' frame for RS-485"""
        if (self.route.rs485_address is None) or (self.route.rs485_address == 0):
            return frame
        frame_list = list(frame)
        frame_list[0:1] = [98, self.route.rs485_address]  # replace "B by ""bx\??"
        return bytes(frame_list)

    def check_cmd(self, raw_cmd) -> bool:
        """Check an incomming command frame for validity"""
        checked_dict = self._check_message(raw_cmd, False)
        logger().debug("Checked dict: %s)", checked_dict)
        if checked_dict["is_valid"] and (len(checked_dict["payload"]) > 0):
            if not checked_dict["is_control"]:
                return True
            cmd_byte = checked_dict["payload"][0]
            return bool(cmd_byte in self._allowed_cmds)
        return False

    def get_message_payload(self, message: bytes, timeout=0.1) -> CheckedAnswerDict:
        """Send a message to the instrument and give back the payload of the reply.

        Args:
            message:
                The message to send.
            timeout:
                Timeout in seconds for waiting for a reply from instrument.
        Returns:
            A dictionary of
            is_valid: True if answer is valid, False otherwise,
            is_control_message: True if control message,
            is_last_frame: True if no follow-up B-E frame is expected,
            payload: Payload of answer,
            number_of_bytes_in_payload,
            raw: The raw byte string from _get_transparent_reply.
            standard_frame: standard B-E frame derived from b-e frame
        """
        cmd_is_valid = True
        if message:
            cmd_is_valid = self.check_cmd(message)
        if not cmd_is_valid:
            logger().error("Received invalid command %s", message)
            return {
                "is_valid": False,
                "is_control": False,
                "is_last_frame": True,
                "payload": b"",
                "number_of_bytes_in_payload": 0,
                "raw": b"",
                "standard_frame": b"",
            }
        message = self._make_rs485(message)
        answer = self._get_transparent_reply(message, timeout=timeout, keep=True)
        checked_answer = self._check_message(answer, False)
        return {
            "is_valid": checked_answer["is_valid"],
            "is_control": checked_answer["is_control"],
            "is_last_frame": checked_answer["is_last_frame"],
            "payload": checked_answer["payload"],
            "number_of_bytes_in_payload": checked_answer["number_of_bytes_in_payload"],
            "raw": checked_answer["raw"],
            "standard_frame": checked_answer["standard_frame"],
        }

    def __str__(self) -> str:
        output = (
            f"Id: {self.device_id}\n"
            f"SerialDevice: {self._route.port}\n"
            f"Baudrate: {self.family['baudrate']}\n"
            f"FamilyName: {self.family['family_name']}\n"
            f"FamilyId: {self.family['family_id']}\n"
            f"TypName: {self.type_name}\n"
            f"TypeId: {self.type_id}\n"
            f"SoftwareVersion: {self.software_version}\n"
            f"SerialNumber: {self.serial_number}\n"
        )
        return output

    def _initialize(self) -> None:
        if self._route.zigbee_address:
            self.select_zigbee_channel(self._route.zigbee_address)
            sleep(3)
        self.get_description()
        logger().debug("valid_family = %s", self._valid_family)
        if self._valid_family:
            self._build_component_list()
            self._last_sampling_time = None

    def get_description(self) -> bool:
        """Set instrument type, software version, and serial number."""
        id_cmd = self.family["get_id_cmd"]
        ok_byte = self.family["ok_byte"]
        msg = self._make_command_msg(id_cmd)
        checked_payload = self.get_message_payload(msg, timeout=0.5)
        if checked_payload["is_valid"]:
            reply = checked_payload["payload"]
        else:
            reply = b""
        if (
            checked_payload["number_of_bytes_in_payload"]
            == sarad_family(2)["length_of_reply"]
        ):
            self._family = sarad_family(2)
        elif (
            checked_payload["number_of_bytes_in_payload"]
            > sarad_family(2)["length_of_reply"]
        ):
            self._family = sarad_family(5)
        if reply and (reply[0] == ok_byte):
            logger().debug("Get description successful.")
            try:
                self._type_id = reply[1]
                self._software_version = reply[2]
                if self._type_id == 200:
                    logger().info("ZigBee Coordinator detected.")
                    self._family = sarad_family(4)
                if self._family["family_id"] == 5:
                    if reply[29]:
                        byte_order: Literal["little", "big"] = "little"
                        logger().debug("DACM-32 with Little-Endian")
                    else:
                        byte_order = "big"
                        logger().debug("DACM-8 with Big-Endian")
                else:
                    byte_order = self._family["byte_order"]
                self._serial_number = int.from_bytes(
                    reply[3:5], byteorder=byte_order, signed=False
                )
                return True
            except (TypeError, ReferenceError, LookupError) as exception:
                logger().error("Error when parsing the payload: %s", exception)
                return False
        logger().debug("Get description failed. Instrument replied = %s", reply)
        return False

    def _build_component_list(self) -> int:
        """Build up a list of components with sensors and measurands.

        Will be overriden by derived classes."""
        return len(self.components)

    @staticmethod
    def _bytes_to_float(value: bytes) -> float:
        """Convert 4 bytes (little endian)

        from serial interface into
        floating point nummber according to IEEE 754"""
        byte_array = bytearray(value)
        byte_array.reverse()
        return struct.unpack("<f", bytes(byte_array))[0]

    @staticmethod
    def _parse_value_string(value: str) -> MeasurandDict:
        """Parse the string containing a value.

        Take a string containing a physical value with operator,
        value and unit and decompose it into its parts
        for further mathematical processing."""
        measurand_operator: str = ""
        measurand_value: float = 0.0
        measurand_unit: str = ""
        valid: bool = False
        if value != "No valid data!":
            try:
                if ("<" in value) or (">" in value):
                    measurand_operator = value[0]
                    meas_with_unit = value[1:]
                else:
                    meas_with_unit = value
                measurand_value = float(meas_with_unit.split()[0])
                valid = True
                try:
                    measurand_unit = meas_with_unit.split()[1]
                except Exception:  # pylint: disable=broad-except
                    pass
            except Exception:  # pylint: disable=broad-except
                pass
        return {
            "measurand_operator": measurand_operator,
            "measurand_value": measurand_value,
            "measurand_unit": measurand_unit,
            "valid": valid,
        }

    def _encode_setup_word(self) -> bytes:
        """Compile the SetupWord for Doseman and RadonScout devices from its components.

        All used arguments from self are enum objects."""
        bv_signal = BitVector(intVal=self.signal.value - 1, size=2)
        bv_radon_mode = BitVector(intVal=self.radon_mode.value - 1, size=1)
        bv_pump_mode = BitVector(intVal=self.pump_mode.value - 1, size=1)
        bv_pump_mode = BitVector(bitstring="0")
        bv_units = BitVector(intVal=self.units.value - 1, size=1)
        bv_units = BitVector(bitstring="0")
        bv_chamber_size = BitVector(intVal=self.chamber_size.value - 1, size=2)
        bv_padding = BitVector(bitstring="000000000")
        bit_vector = (
            bv_padding
            + bv_chamber_size
            + bv_units
            + bv_pump_mode
            + bv_radon_mode
            + bv_signal
        )
        logger().debug(str(bit_vector))
        return bit_vector.get_bitvector_in_ascii().encode("utf-8")

    def _decode_setup_word(self, setup_word: bytes) -> None:
        bit_vector = BitVector(rawbytes=setup_word)
        signal_index = bit_vector[6:8].int_val()
        self.signal = list(self.Signal)[signal_index]
        radon_mode_index = bit_vector[5]
        self.radon_mode = list(self.RadonMode)[radon_mode_index]
        pump_mode_index = bit_vector[4]
        self.pump_mode = list(self.PumpMode)[pump_mode_index]
        units_index = bit_vector[3]
        self.units = list(self.Units)[units_index]
        chamber_size_index = bit_vector[1:3].int_val()
        self.chamber_size = list(self.ChamberSize)[chamber_size_index]

    def _get_parameter(
        self, parameter_name: Literal["components", "battery_bytes", "battery_coeff"]
    ) -> Any:
        for inst_type in self.family["types"]:
            if inst_type["type_id"] == self.type_id:
                try:
                    return inst_type[parameter_name]
                except Exception:  # pylint: disable=broad-except
                    pass
        try:
            return self.family[parameter_name]
        except Exception:  # pylint: disable=broad-except
            return False

    def get_reply(self, cmd_data: List[bytes], timeout=0.5) -> Any:
        """Send a command message and get a reply.

        Returns a bytestring of the payload of the instruments reply
        to the provided list of 1-byte command and data bytes."""
        msg = self._make_command_msg(cmd_data)
        checked_payload = self.get_message_payload(msg, timeout)
        if checked_payload["is_valid"]:
            return checked_payload["payload"]
        return False

    def _get_control_bytes(self, serial):
        """Read 3 or 4 Bytes from serial interface resp."""
        logger().debug("Trying to read the first 3 bytes")
        if (self.route.rs485_address is None) or (self.route.rs485_address == 0):
            offset = 3
            start_byte = b"B"
        else:
            offset = 4
            start_byte = b"b"
        try:
            answer = serial.read(offset)
        except SerialException as exception:
            logger().warning(exception)
            return b""
        if answer:
            while len(answer) < offset:
                sleep(0.001)
                answer_left = serial.read(offset - len(answer))
                answer = answer + answer_left
        if not answer.startswith(start_byte):
            if answer == b"":
                logger().debug(
                    "No reply in _get_control_bytes(%s, %s)",
                    serial.port,
                    serial.baudrate,
                )
                self._valid_family = False
                return answer
            logger().warning(
                "Message %s should start with b'B'. No SARAD instrument.", answer
            )
            self._valid_family = False
            return b""
        control_byte = answer[-2]
        neg_control_byte = answer[-1]
        if (control_byte ^ 0xFF) != neg_control_byte:
            logger().error("Message corrupted.")
            return answer
        _is_control = bool(control_byte & 0x80)
        self._valid_family = True
        return answer

    @staticmethod
    def _get_payload_length(first_bytes):
        """Read 3 Bytes from serial interface

        to get the length of payload from the control byte."""
        control_byte = first_bytes[-2]
        return (control_byte & 0x7F) + 1

    @staticmethod
    def _close_serial(serial, keep):
        if serial is not None and serial.is_open:
            try:
                serial.reset_input_buffer()
                serial.reset_output_buffer()
                if not keep:
                    serial.close()
                    while serial.is_open:
                        sleep(0.01)
                    logger().debug("Serial interface closed.")
                    return None
            except Exception:  # pylint: disable=broad-except
                logger().warning("Serial interface not available.")
                return None
            logger().debug("Keeping serial interface %s open.", serial)
            return serial
        logger().debug("Tried to close %s but nothing to do.", serial)
        return None

    def release_instrument(self):
        """Close serial port to release the reserved instrument"""
        logger().debug("Release serial interface %s", self.__ser)
        self.__ser = self._close_serial(self.__ser, False)

    def _get_be_frame(self, serial, keep):
        """Get one Rx B-E frame or one b-E frame resp."""
        first_bytes = self._get_control_bytes(serial)
        if first_bytes == b"":
            self.__ser = self._close_serial(serial, keep)
            return b""
        number_of_remaining_bytes = self._get_payload_length(first_bytes) + 3
        logger().debug(
            "Expecting %d bytes at timeouts of %f %f",
            number_of_remaining_bytes,
            serial.timeout,
            serial.inter_byte_timeout,
        )
        remaining_bytes = serial.read(number_of_remaining_bytes)
        if len(remaining_bytes) < number_of_remaining_bytes:
            logger().error("Uncomplete B-E frame. Trying to complete.")
            left_bytes = serial.read_until("E", None)
            return first_bytes + remaining_bytes + left_bytes
        return first_bytes + remaining_bytes

    def _get_transparent_reply(self, raw_cmd, timeout=0.5, keep=True):
        """Returns the raw bytestring of the instruments reply"""

        def _open_serial(baudrate):
            retry = True
            parity_options = {"N": PARITY_NONE, "E": PARITY_EVEN}
            logger().debug("Parity = %s", parity_options[self._family["parity"]])
            for _i in range(0, 1):
                while retry:
                    try:
                        ser = Serial(
                            self._route.port,
                            baudrate=baudrate,
                            bytesize=8,
                            xonxoff=0,
                            parity=parity_options[self._family["parity"]],
                            stopbits=STOPBITS_ONE,
                        )
                        retry = False
                    except BlockingIOError as exception:
                        logger().error(
                            "%s. Waiting 1 s and retrying to connect.", exception
                        )
                        sleep(1)
                    except (
                        Exception,
                        SerialException,
                    ) as exception:  # pylint: disable=broad-except
                        logger().critical(exception)
                        raise
            if retry:
                raise BlockingIOError
            while not ser.is_open:
                sleep(0.01)
            while ser.baudrate != baudrate:
                sleep(0.01)
            logger().debug("Serial ready @ %d baud", ser.baudrate)
            return ser

        def _try_baudrate(baudrate, keep_serial_open, timeout):
            if keep_serial_open:
                if self.__ser is None:
                    ser = _open_serial(baudrate)
                else:
                    try:
                        ser = self.__ser
                        ser.baudrate = baudrate
                        if not ser.is_open:
                            logger().debug("Serial interface is closed. Reopen.")
                            ser.open()
                            while not ser.is_open:
                                sleep(0.01)
                        logger().debug("Reuse stored serial interface")
                    except (AttributeError, SerialException, OSError):
                        logger().warning(
                            "Something went wrong with reopening -> Re-initialize"
                        )
                        self.__ser = None
            else:
                logger().debug("Open serial, don't keep.")
                ser = _open_serial(baudrate)
            try:
                ser.timeout = timeout
            except SerialException as exception:
                logger().error(exception)
                return b""
            logger().debug("Tx to %s: %s", ser.port, raw_cmd)
            ser.inter_byte_timeout = timeout
            if raw_cmd:
                sleep(self._family["tx_msg_delay"])
                for element in raw_cmd:
                    byte = (element).to_bytes(1, "big")
                    ser.write(byte)
                    sleep(self._family["tx_byte_delay"])
                self._new_rs485_address(raw_cmd)
            logger().debug("Read one BE frame")
            be_frame = self._get_be_frame(ser, True)
            answer = bytearray(be_frame)
            self.__ser = self._close_serial(ser, keep_serial_open)
            b_answer = bytes(answer)
            logger().debug("Rx from %s: %s", ser.port, b_answer)
            return b_answer

        logger().debug("Possible baudrates: %s", self._possible_baudrates)
        result = b""
        for _i in range(len(self._possible_baudrates)):
            baudrate = self._possible_baudrates[0]
            logger().debug("Try to send %s with %s baud", raw_cmd, baudrate)
            result = _try_baudrate(baudrate, keep, timeout)
            retry_counter = 1
            while not result and retry_counter:
                # Workaround for firmware bug in SARAD instruments.
                logger().debug("Play it again, Sam!")
                result = _try_baudrate(baudrate, keep, timeout)
                retry_counter = retry_counter - 1
            if result:
                logger().debug("Working with %s baud", baudrate)
                return result
            self.release_instrument()
            self._possible_baudrates.rotate(-1)
            sleep(1)  # Give the instrument time to reset its input buffer.
        return result

    def _new_rs485_address(self, raw_cmd):
        # pylint: disable = unused-argument
        """Check whether raw_cmd changed the RS-485 bus address of the Instrument.

        If this is the case, self._route will be changed.
        This function must be overriden in the instrumen family dependent implementations.

        Args:
            raw_cmd (bytes): Command message to be analyzed.
        """

    def start_cycle(self, cycle_index: int) -> None:
        """Start measurement cycle.  Place holder for subclasses."""

    def stop_cycle(self) -> None:
        """Stop measurement cycle.  Place holder for subclasses."""

    def set_real_time_clock(self, date_time: datetime) -> bool:
        # pylint: disable=unused-argument
        """Set RTC of instrument to datetime.  Place holder for subclasses."""
        return False

    @property
    def route(self) -> Route:
        """Return route to instrument (ser. port, RS-485 address, ZigBee address)."""
        return self._route

    @route.setter
    def route(self, route: Route):
        """Set route to instrument."""
        self._route = route
        if (self._route.port is not None) and (self._family is not None):
            self._initialize()

    @property
    def device_id(self) -> str:
        """Return device id."""
        return self.__id

    @device_id.setter
    def device_id(self, device_id: str):
        """Set device id."""
        self.__id = device_id

    @property
    def family(self) -> FamilyDict:
        """Return the instrument family."""
        return self._family

    @family.setter
    def family(self, family: FamilyDict):
        """Set the instrument family."""
        self._family = family
        if (self.route.port is not None) and (self._family is not None):
            self._initialize()

    @property
    def type_id(self) -> int:
        """Return the device type id."""
        return self._type_id

    @property
    def type_name(self) -> str:
        """Return the device type name."""
        for type_in_family in self.family["types"]:
            if type_in_family["type_id"] == self.type_id:
                return type_in_family["type_name"]
        return ""

    @property
    def software_version(self) -> int:
        """Return the firmware version of the device."""
        return self._software_version

    @property
    def serial_number(self) -> int:
        """Return the serial number of the device."""
        return self._serial_number

    @property
    def components(self) -> Collection[Component]:
        """Return the list of components of the device."""
        return self.__components

    @components.setter
    def components(self, components: Collection[Component]):
        """Set the list of components of the device."""
        self.__components = components

    @property
    def valid_family(self) -> bool:
        """True if the family set is correct for the connected instrument."""
        return self._valid_family
