"""Abstract class for all SARAD instruments

SaradInst comprises all attributes and methods
that all SARAD instruments have in common."""

import logging
import os
import struct
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import (Any, Collection, Dict, Generic, Iterator, List, Optional,
                    TypedDict, TypeVar)

import yaml
from BitVector import BitVector  # type: ignore
from serial import STOPBITS_ONE, Serial  # type: ignore

logger = logging.getLogger(__name__)

SI = TypeVar("SI", bound="SaradInst")


class MeasurandDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for Measurand dictionary."""
    measurand_operator: str
    measurand_value: float
    measurand_unit: str
    valid: bool


class InstrumentDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for instrument type dictionary."""
    type_id: int
    type_name: str


class FamilyDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for Family dictionary."""
    family_id: int
    family_name: str
    baudrate: int
    get_id_cmd: List[bytes]
    length_of_reply: int
    wait_for_reply: float
    write_sleeptime: float
    parity: str
    ok_byte: int
    config_parameters: List[Dict[str, Any]]
    types: List[InstrumentDict]


class CheckedAnswerDict(TypedDict):
    # pylint: disable=inherit-non-class, too-few-public-methods
    """Type declaration for checked reply from instrument."""
    is_valid: bool
    is_control: bool
    payload: bytes
    number_of_bytes_in_payload: int


# * Measurand:
# ** Definitions:
class Measurand:
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

    version: str = "0.1"

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

    # ** Private methods:

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

    # ** Properties:
    # *** measurand_id:

    @property
    def measurand_id(self) -> int:
        """Return the Id of this measurand."""
        return self.__id

    @measurand_id.setter
    def measurand_id(self, measurand_id: int) -> None:
        """Set the Id of this measurand."""
        self.__id = measurand_id

    # *** name:

    @property
    def name(self) -> str:
        """Return the name of this measurand."""
        return self.__name

    @name.setter
    def name(self, name: str) -> None:
        """Set the name of this measurand."""
        self.__name = name

    # *** unit:

    @property
    def unit(self) -> str:
        """Return the physical unit of this measurand."""
        return self.__unit

    @unit.setter
    def unit(self, unit: str) -> None:
        """Set the physical unit of this measurand."""
        self.__unit = unit

    # *** source:

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

    # *** operator:

    @property
    def operator(self) -> str:
        """Return the operator belonging to this measurand.
        Typical operators are '<', '>'"""
        return self.__operator

    @operator.setter
    def operator(self, operator: str) -> None:
        """Set the operator of this measurand."""
        self.__operator = operator

    # *** value:

    @property
    def value(self) -> Optional[float]:
        """Return the value of the measurand."""
        return self.__value

    @value.setter
    def value(self, value: Optional[float]) -> None:
        """Set the value of the measurand."""
        self.__value = value

    # *** time:

    @property
    def time(self) -> datetime:
        """Return the aquisition time (timestamp) of the measurand."""
        return self.__time

    @time.setter
    def time(self, time_stamp: datetime) -> None:
        """Set the aquisition time (timestamp) of the measurand."""
        self.__time = time_stamp

    # *** gps:

    @property
    def gps(self) -> str:
        """Return the GPS string of the measurand."""
        return self.__gps

    @gps.setter
    def gps(self, gps: str) -> None:
        """Set the GPS string of the measurand."""
        self.__gps = gps


# * Sensor:
# ** Definitions:
class Sensor:
    """Class describing a sensor that is part of a component.

    Properties:
        id
        name
        interval: Measuring interval in seconds
    Public methods:
        get_measurands()"""

    version: str = "0.1"

    def __init__(self, sensor_id: int, sensor_name: str) -> None:
        self.__id: int = sensor_id
        self.__name: str = sensor_name
        self.__interval: timedelta = timedelta(0)
        self.__measurands: List[Measurand] = []

    # ** Private methods:

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

    # ** Properties:
    # *** id:

    @property
    def sensor_id(self) -> int:
        """Return the Id of this sensor."""
        return self.__id

    @sensor_id.setter
    def sensor_id(self, sensor_id: int) -> None:
        """Set the Id of this sensor."""
        self.__id = sensor_id

    # *** name:

    @property
    def name(self) -> str:
        """Return the name of this sensor."""
        return self.__name

    @name.setter
    def name(self, name: str) -> None:
        """Set the name of this sensor."""
        self.__name = name

    # *** interval:

    @property
    def interval(self) -> timedelta:
        """Return the measuring interval of this sensor."""
        return self.__interval

    @interval.setter
    def interval(self, interval: timedelta):
        """Set the measuring interval of this sensor."""
        self.__interval = interval

    # *** measurands:

    @property
    def measurands(self) -> List[Measurand]:
        """Return the list of measurands of this sensor."""
        return self.__measurands

    @measurands.setter
    def measurands(self, measurands: List[Measurand]):
        """Set the list of measurands of this sensor."""
        self.__measurands = measurands


# * Component:
# ** Definitions:
class Component:
    """Class describing a sensor or actor component built into an instrument"""

    version = "0.1"

    def __init__(self, component_id: int, component_name: str) -> None:
        self.__id: int = component_id
        self.__name: str = component_name
        self.__sensors: List[Sensor] = []

    # ** Private methods:

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

    # ** Properties:
    # *** id:

    @property
    def component_id(self) -> int:
        """Return the Id of this component."""
        return self.__id

    @component_id.setter
    def component_id(self, component_id: int) -> None:
        """Set the Id of this component."""
        self.__id = component_id

    # *** name:

    @property
    def name(self) -> str:
        """Return the name of this component."""
        return self.__name

    @name.setter
    def name(self, name: str):
        """Set the component name."""
        self.__name = name

    # *** sensors:

    @property
    def sensors(self) -> List[Sensor]:
        """Return the list of sensors belonging to this component."""
        return self.__sensors

    @sensors.setter
    def sensors(self, sensors: List[Sensor]):
        """Set the list of sensors belonging to this component."""
        self.__sensors = sensors


# * SaradInst:
# ** Definitions:
class SaradInst(Generic[SI]):
    """Basic class for the serial communication protocol of SARAD instruments

    Class attributes:
        products
    Properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        device_id: Identifier for an individual instrument in a cluster
        type_id: Together with family, this Id identifys the instrument type.
        type_name: Identifys the instrument type.
        software_version: The version of the firmware.
        serial_number: Serial number of the connected instrument.
        components: List of sensor or actor components
    Public methods:
        get_reply()
        get_message_payload()"""

    version = "1.0"

    class Lock(Enum):
        """Setting of the device. Lock the hardware button."""

        unlocked: int = 1
        locked: int = 2

    class RadonMode(Enum):
        """Setting of the device. Displayed radon values based on
        short living progeny only (fast)
        or on short and long living progeny (slow)"""

        slow: int = 1
        fast: int = 2

    class PumpMode(Enum):
        """Setting of the devices having a pump."""

        continuous: int = 1
        interval: int = 2

    class Units(Enum):
        """Setting of the device. Unit system used for display."""

        si: int = 1
        us: int = 2

    class Signal(Enum):
        """Setting of the device. When shall it give an audible signal?"""

        off: int = 1
        alarm: int = 2
        sniffer_po216: int = 3
        po216_po218: int = 4

    class ChamberSize(Enum):
        """Setting the chamber size (Radon Scout PMT only)."""

        small: int = 1
        medium: int = 2
        large: int = 3
        xl: int = 4

    with open(
        os.path.dirname(os.path.realpath(__file__)) + os.path.sep + "instruments.yaml",
        "r",
    ) as __f:
        products = yaml.safe_load(__f)

    # ** Private methods:

    # *** __init__():

    def __init__(self: SI, port=None, family=None) -> None:
        self.__port: str = port
        self.__family: FamilyDict = family
        if (port is not None) and (family is not None):
            self._initialize()
        self.__components: Collection[Component] = []
        self.__interval: timedelta = timedelta(0)
        self._type_id: int = 0
        self._type_name: str = ""
        self._software_version: int = 0
        self._serial_number: int = 0
        self.signal = self.Signal.off
        self.radon_mode = self.RadonMode.slow
        self.pump_mode = self.PumpMode.continuous
        self.units = self.Units.si
        self.chamber_size = self.ChamberSize.small
        self.lock = self.Lock.unlocked
        self.__id: str = ""
        self.__ser = None

    # *** __iter__():

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

    # *** __make_command_msg():

    @staticmethod
    def __make_command_msg(cmd_data: List[bytes]) -> bytes:
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
        output = (
            b"B"
            + bytes([control_byte])
            + bytes([neg_control_byte])
            + payload
            + checksum_bytes
            + b"E"
        )
        return output

    # *** __check_answer():

    @staticmethod
    def __check_answer(answer: bytes) -> CheckedAnswerDict:
        # Returns a dictionary of:
        #     is_valid: True if answer is valid, False otherwise
        #     is_control_message: True if control message
        #     payload: Payload of answer
        #     number_of_bytes_in_payload
        logger.debug("Checking answer from serial port:")
        logger.debug("Raw answer: %s", answer)
        if answer.startswith(b"B") & answer.endswith(b"E"):
            control_byte = answer[1]
            neg_control_byte = answer[2]
            if (control_byte ^ 0xFF) == neg_control_byte:
                control_byte_ok = True
            number_of_bytes_in_payload = (control_byte & 0x7F) + 1
            is_control = bool(control_byte & 0x80)
            status_byte = answer[3]
            logger.debug("Status byte: %s", status_byte)
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
            if received_checksum == calculated_checksum:
                checksum_ok = True
            is_valid = control_byte_ok & checksum_ok
        else:
            is_valid = False
        if not is_valid:
            is_control = False
            payload = b""
            number_of_bytes_in_payload = 0
        logger.debug("Payload: %s", payload)
        return {
            "is_valid": is_valid,
            "is_control": is_control,
            "payload": payload,
            "number_of_bytes_in_payload": number_of_bytes_in_payload,
        }

    # *** get_message_payload():

    def get_message_payload(self, message: bytes, timeout: int) -> CheckedAnswerDict:
        """Returns a dictionary of:
        is_valid: True if answer is valid, False otherwise
        is_control_message: True if control message
        payload: Payload of answer
        number_of_bytes_in_payload"""
        answer = self._get_transparent_reply(message, timeout=timeout, keep=False)
        if answer == b"":
            # Workaround for firmware bug in SARAD instruments.
            logger.debug("Play it again, Sam!")
            answer = self._get_transparent_reply(message, timeout=timeout, keep=False)
        checked_answer = self.__check_answer(answer)
        return {
            "is_valid": checked_answer["is_valid"],
            "is_control": checked_answer["is_control"],
            "payload": checked_answer["payload"],
            "number_of_bytes_in_payload": checked_answer["number_of_bytes_in_payload"],
            "raw": answer,
        }

    # *** __str__(self):

    def __str__(self) -> str:
        output = (
            f"Id: {self.device_id}\n"
            f"SerialDevice: {self.port}\n"
            f"Baudrate: {self.family['baudrate']}\n"
            f"FamilyName: {self.family['family_name']}\n"
            f"FamilyId: {self.family['family_id']}\n"
            f"TypName: {self.type_name}\n"
            f"TypeId: {self.type_id}\n"
            f"SoftwareVersion: {self.software_version}\n"
            f"SerialNumber: {self.serial_number}\n"
        )
        return output

    # ** Protected methods:
    # *** _initialize():

    def _initialize(self) -> None:
        self._get_description()
        self._build_component_list()
        self._last_sampling_time = None

    # *** _get_description():

    def _get_description(self) -> bool:
        """Set instrument type, software version, and serial number."""
        id_cmd = self.family["get_id_cmd"]
        length_of_reply = self.family["length_of_reply"]
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply(id_cmd, length_of_reply, timeout=0.5)
        if reply and (reply[0] == ok_byte):
            logger.debug("Get description successful.")
            try:
                self._type_id = reply[1]
                self._software_version = reply[2]
                self._serial_number = int.from_bytes(
                    reply[3:5], byteorder="little", signed=False
                )
                return True
            except TypeError:
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except Exception:  # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
                return False
        logger.debug("Get description failed.")
        return False

    # *** _build_component_list():

    def _build_component_list(self) -> int:
        """Build up a list of components with sensors and measurands.
        Will be overriden by derived classes."""
        return len(self.components)

    # *** _bytes_to_float():

    @staticmethod
    def _bytes_to_float(value: bytes) -> float:
        """Convert 4 bytes (little endian) from serial interface into
        floating point nummber according to IEEE 754"""
        byte_array = bytearray(value)
        byte_array.reverse()
        return struct.unpack("<f", bytes(byte_array))[0]

    # *** _parse_value_string():

    @staticmethod
    def _parse_value_string(value: str) -> MeasurandDict:
        """Take a string containing a physical value with operator,
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

    # *** _encode_setup_word():

    def _encode_setup_word(self) -> bytes:
        """Compile the SetupWord for Doseman and RadonScout devices
        from its components.  All used arguments from self are enum objects."""
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
        logger.debug(str(bit_vector))
        return bit_vector.get_bitvector_in_ascii().encode("utf-8")

    # *** _decode_setup_word(setup_word):

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

    # *** _get_parameter():

    def _get_parameter(self, parameter_name: str) -> Any:
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

    # ** Public methods:
    # *** get_reply():

    def get_reply(self, cmd_data: List[bytes], _reply_length=50, timeout=0.1) -> Any:
        """Returns a bytestring of the payload of the instruments reply
        to the provided list of 1-byte command and data bytes."""
        msg = self.__make_command_msg(cmd_data)
        checked_payload = self.get_message_payload(msg, timeout)
        if checked_payload["is_valid"]:
            return checked_payload["payload"]
        logger.debug(checked_payload["payload"])
        return False

    # *** _get_transparent_reply():
    @staticmethod
    def __get_control_bytes(serial):
        """Read 3 Bytes from serial interface"""
        perf_time_0 = time.perf_counter()
        answer = serial.read(3)
        perf_time_1 = time.perf_counter()
        logging.debug(
            "Receiving %s from serial took me %f s",
            answer,
            perf_time_1 - perf_time_0,
        )
        try:
            assert answer != b""
        except AssertionError:
            logging.warning("The instrument did not reply.")
            return answer
        try:
            assert answer.startswith(b"B") is True
        except AssertionError:
            logging.warning("This seems to be no SARAD instrument.")
            answer = b""
            return answer
        control_byte = answer[1]
        neg_control_byte = answer[2]
        try:
            assert (control_byte ^ 0xFF) == neg_control_byte
        except AssertionError:
            logging.error("Message corrupted.")
            answer = b""
            return answer
        is_control = bool(control_byte & 0x80)
        logging.debug("is_control: %s, control_byte: %s", is_control, control_byte)
        # try:
        #     assert is_control is False
        # except AssertionError:
        #     logging.error("Data message expected, but this is a control message.")
        #     answer = b""
        #     return answer
        return answer

    @staticmethod
    def __get_payload_length(first_bytes):
        """Read 3 Bytes from serial interface
        to get the length of payload from the control byte."""
        control_byte = first_bytes[1]
        return (control_byte & 0x7F) + 1

    def _get_transparent_reply(self, raw_cmd, timeout=0.1, keep=True):
        """Returns the raw bytestring of the instruments reply"""
        if not keep:
            ser = Serial(
                self.__port,
                self.__family["baudrate"],
                bytesize=8,
                xonxoff=0,
                timeout=timeout,
                parity=self.__family["parity"],
                rtscts=0,
                stopbits=STOPBITS_ONE,
            )
            if not ser.is_open:
                ser.open()
            logging.debug("Open serial, don't keep.")
        else:
            try:
                ser = self.__ser
                logging.debug("Reuse stored serial interface")
                if not ser.is_open:
                    logging.debug("Port is closed. Reopen.")
                    ser.open()
            except AttributeError:
                ser = Serial(
                    self.__port,
                    self.__family["baudrate"],
                    bytesize=8,
                    xonxoff=0,
                    timeout=timeout,
                    parity=self.__family["parity"],
                    rtscts=0,
                    stopbits=STOPBITS_ONE,
                    exclusive=True,
                )
                if not ser.is_open:
                    ser.open()
                logging.debug("Open serial")
        perf_time_0 = time.perf_counter()
        for element in raw_cmd:
            byte = (element).to_bytes(1, "big")
            ser.write(byte)
            time.sleep(self.__family["write_sleeptime"])
        perf_time_1 = time.perf_counter()
        logging.debug(
            "Writing command %s to serial took me %f s",
            raw_cmd,
            perf_time_1 - perf_time_0,
        )
        # time.sleep(self.__family["wait_for_reply"])
        first_bytes = self.__get_control_bytes(ser)
        try:
            assert first_bytes != b""
        except AssertionError:
            return b""
        payload_length = self.__get_payload_length(first_bytes)
        number_of_remaining_bytes = payload_length + 3
        remaining_bytes = ser.read(number_of_remaining_bytes)
        while ser.in_waiting:
            logging.debug("%d bytes waiting", ser.in_waiting)
            ser.read(ser.in_waiting)
            time.sleep(0.1)
        perf_time_2 = time.perf_counter()
        answer = first_bytes + remaining_bytes
        logging.debug(
            "Receiving %s from serial took me %f s",
            answer,
            perf_time_2 - perf_time_1,
        )
        if not keep:
            ser.close()
            logging.debug("Serial interface closed.")
        else:
            logging.debug("Store serial interface")
            self.__ser = ser
        return answer

    # *** start_cycle():

    def start_cycle(self, cycle_index: int) -> None:
        """Start measurement cycle.  Place holder for subclasses."""

    # *** stop_cycle():

    def stop_cycle(self) -> None:
        """Stop measurement cycle.  Place holder for subclasses."""

    # *** set_real_time_clock(rtc_datetime):

    def set_real_time_clock(self, _: datetime) -> bool:
        # pylint: disable=no-self-use
        """Set RTC of instrument to datetime.  Place holder for subclasses."""
        return False

    # ** Properties:

    # *** port:

    @property
    def port(self) -> str:
        """Return serial port."""
        return self.__port

    @port.setter
    def port(self, port: str):
        """Set serial port."""
        self.__port = port
        if (self.port is not None) and (self.family is not None):
            self._initialize()

    # *** device_id:

    @property
    def device_id(self) -> str:
        """Return device id."""
        return self.__id

    @device_id.setter
    def device_id(self, device_id: str):
        """Set device id."""
        self.__id = device_id

    # *** family:

    @property
    def family(self) -> FamilyDict:
        """Return the instrument family."""
        return self.__family

    @family.setter
    def family(self, family: FamilyDict):
        """Set the instrument family."""
        self.__family = family
        if (self.port is not None) and (self.family is not None):
            self._initialize()

    # *** type_id:

    @property
    def type_id(self) -> int:
        """Return the device type id."""
        return self._type_id

    # *** type_name:

    @property
    def type_name(self) -> str:
        """Return the device type name."""
        for type_in_family in self.family["types"]:
            if type_in_family["type_id"] == self.type_id:
                return type_in_family["type_name"]
        return ""

    # *** software_version:

    @property
    def software_version(self) -> int:
        """Return the firmware version of the device."""
        return self._software_version

    # *** serial_number:

    @property
    def serial_number(self) -> int:
        """Return the serial number of the device."""
        return self._serial_number

    # *** components:

    @property
    def components(self) -> Collection[Component]:
        """Return the list of components of the device."""
        return self.__components

    @components.setter
    def components(self, components: Collection[Component]):
        """Set the list of components of the device."""
        self.__components = components
