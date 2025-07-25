"""Abstract class for all SARAD instruments

SaradInst comprises all attributes and methods
that all SARAD instruments have in common."""

import socket
import struct
from collections import deque
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import ceil
from time import sleep
from typing import Any, Dict, Generic, Iterator, List, Literal, TypeVar, Union

from BitVector import BitVector  # type: ignore
from serial import STOPBITS_ONE  # type: ignore
from serial import PARITY_EVEN, PARITY_NONE, Serial, SerialException

from sarad.global_helpers import sarad_family
from sarad.instrument import Component, Gps, Route
from sarad.logger import logger
from sarad.typedef import (CheckedAnswerDict, FamilyDict, FeatureDict,
                           MeasurandDict)

SI = TypeVar("SI", bound="SaradInst")


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
        components: Dictionary of sensor or actor components
    """

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

    CHANNEL_SELECTED = 0xD2
    SOCKET_TIMEOUT = 10  # adds to self._ser_timeout at socket communication

    def __init__(self: SI, family: FamilyDict) -> None:
        self._route: Route = Route(
            port=None,
            rs485_address=None,
            zigbee_address=None,
            ip_address=None,
            ip_port=None,
        )
        self._socket = None
        self._family: FamilyDict = family
        self.__ser = None
        self.__components: Dict[int, Component] = {}
        self._type_id: int = 0
        self._software_version: int = 0
        self._serial_number: int = 0
        self.signal = self.Signal.OFF
        self.radon_mode = self.RadonMode.SLOW
        self.pump_mode = self.PumpMode.CONTINUOUS
        self.units = self.Units.SI
        self.chamber_size = self.ChamberSize.SMALL
        self.lock = self.Lock.UNLOCKED
        self._id: str = ""
        self._valid_family = True
        self._last_sampling_time = datetime.fromtimestamp(0)
        self._serial_param_sets: deque = deque(family["serial"])
        self._utc_offset: Union[None, int] = None
        self._interval = timedelta(seconds=0)
        self._gps = Gps(valid=False)
        self._ser_timeout = self._family.get("ser_timeout", 1)
        self.ext_ser_timeout = self._family.get("ext_ser_timeout", 6)

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
    def _calc_utc_offset(
        sample_interval: timedelta,
        timestamp_datetime: datetime,
        momentary_datetime: datetime,
    ) -> Union[None, int]:
        """This method tries to calculate the UTC offset of the RTC."""
        if sample_interval > timedelta(hours=1):
            return None
        t_diff = timestamp_datetime - momentary_datetime
        logger().debug("t_diff = %s", t_diff)
        return ceil(t_diff.total_seconds() / 3600)

    def _make_command_msg(self, cmd_data: List[bytes]) -> bytes:
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

    def _check_message(self, message: bytes, multiframe: bool) -> CheckedAnswerDict:
        # pylint: disable=too-many-locals
        """Check the message

        Returns a dictionary of:
        is_valid: True if message is valid, False otherwise
        is_control_message: True if control message
        payload: Payload of message
        number_of_bytes_in_payload
        """
        if message and message.startswith(b"B") and message.endswith(b"E"):
            control_byte = message[1]
            control_byte_ok = bool((control_byte ^ 0xFF) == message[2])
            number_of_bytes_in_payload = (control_byte & 0x7F) + 1
            is_control = bool(control_byte & 0x80)
            _status_byte = message[3]
            payload = message[3 : 3 + number_of_bytes_in_payload]
            payload_list = list(payload)
            if is_control:
                cmd = bytes(payload_list[0:1])
                data = bytes(payload_list[1:])
            else:
                cmd = b""
                data = payload
            calculated_checksum = 0
            for byte in payload:
                calculated_checksum = calculated_checksum + byte
            received_checksum_bytes = message[
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
                "cmd": cmd,
                "data": data,
                "payload": payload,
                "number_of_bytes_in_payload": number_of_bytes_in_payload,
                "raw": message,
                "standard_frame": self._rs485_filter(message),
            }
        logger().debug("Invalid B-E frame")
        return {
            "is_valid": False,
            "is_control": False,
            "is_last_frame": True,
            "cmd": b"",
            "data": b"",
            "payload": b"",
            "number_of_bytes_in_payload": 0,
            "raw": message,
            "standard_frame": self._rs485_filter(message),
        }

    def _rs485_filter(self, frame):
        """Convert an addressed RS-485 'b-E' frame into a normal 'B-E' frame

        by simply replacing the first two bytes with 'B'."""
        if (self.route.rs485_address is None) or not frame:
            return frame
        frame_list = list(frame)
        if frame_list[0] == 98:  # int representation of "b"
            frame_list[0:2] = [66]  # replace "bx\??" by "B"
        return bytes(frame_list)

    def _make_rs485(self, frame):
        """Convert a normal 'B-E' frame into an addressed 'b-E' frame for RS-485"""
        if (
            (self.route.rs485_address is None)
            or (self.route.rs485_address == 0)
            or (list(frame)[0] == 98)
        ):
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
            return bool(cmd_byte in self._family.get("allowed_cmds", []))
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
        cmd_is_valid = self.check_cmd(message)
        if cmd_is_valid:
            addr_message = self._make_rs485(message)
            logger().debug("To: %s", addr_message)
            addr_answer = self._get_transparent_reply(
                addr_message, timeout=timeout, keep=True
            )
            logger().debug("From: %s", addr_answer)
            answer = self._rs485_filter(addr_answer)
            checked_answer = self._check_message(answer, False)
            return {
                "is_valid": checked_answer["is_valid"],
                "is_control": checked_answer["is_control"],
                "is_last_frame": checked_answer["is_last_frame"],
                "cmd": checked_answer["cmd"],
                "data": checked_answer["data"],
                "payload": checked_answer["payload"],
                "number_of_bytes_in_payload": checked_answer[
                    "number_of_bytes_in_payload"
                ],
                "raw": checked_answer["raw"],
                "standard_frame": checked_answer["standard_frame"],
            }
        logger().error("Received invalid command %s", message)
        return {
            "is_valid": False,
            "is_control": False,
            "is_last_frame": True,
            "cmd": b"",
            "data": b"",
            "payload": b"",
            "number_of_bytes_in_payload": 0,
            "raw": b"",
            "standard_frame": b"",
        }

    def __str__(self) -> str:
        output = (
            f"Id: {self.device_id}\n"
            f"SerialDevice: {self._route.port}\n"
            f"Baudrate: {self.family['serial']['baudrate']}\n"
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
            self.select_channel(self._route.zigbee_address)
        self.get_description()
        if self._route.zigbee_address:
            self.close_channel()
        logger().debug("valid_family = %s", self._valid_family)
        if self._valid_family:
            self._build_component_dict()

    def get_description(self) -> bool:
        """Set instrument type, software version, and serial number."""
        try:
            if self.family["family_id"] == 4:
                self.close_channel()
        except (KeyError, TypeError):
            logger().error("Call of get_description() with undefined family")
            return False
        id_cmd = self.family["get_id_cmd"]
        ok_byte = self.family["ok_byte"]
        msg = self._make_command_msg(id_cmd)
        checked_payload = self.get_message_payload(msg, timeout=self._ser_timeout)
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
                    logger().debug("ZigBee Coordinator detected.")
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
            except (KeyError, TypeError, ReferenceError, LookupError) as exception:
                logger().error("Error when parsing the payload: %s", exception)
                return False
        logger().debug("Get description failed. Instrument replied = %s", reply)
        return False

    def _build_component_dict(self) -> int:
        """Build up a dict of components with sensors and measurands.

        Will be overriden by derived classes."""
        return len(self.components)

    def select_channel(self, channel_idx):
        """Start the transparent mode to given ZigBee channel."""
        reply = self.get_reply(
            [b"\xc2", channel_idx.to_bytes(2, "little")], timeout=self._ser_timeout
        )
        if reply and (reply[0] == self.CHANNEL_SELECTED):
            logger().debug("Channel selected: %s", reply)
            return reply
        logger().error("Unexpected reply to select_channel: %s", reply)
        return False

    def close_channel(self):
        """Leave the transparent ZigBee mode."""
        reply = self.get_reply([b"\xc2", b"\x00\x00"], timeout=self._ser_timeout)
        if reply and (reply[0] == self.CHANNEL_SELECTED):
            return reply
        logger().error("Unexpected reply to close_channel: %s", reply)
        return False

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
                    if measurand_unit == "øC":
                        measurand_unit = "°C"
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
        return None
        # try:
        #     return self.family[parameter_name]
        # except Exception:  # pylint: disable=broad-except
        #     return False

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
        if (self.route.rs485_address is None) or (self.route.rs485_address == 0):
            logger().debug("Trying to read the first 3 bytes on route %s", self.route)
            offset = 3
            start_byte = b"B"
        else:
            logger().debug("Trying to read the first 4 bytes on route %s", self.route)
            offset = 4
            start_byte = b"b"
        try:
            answer = serial.read(offset)
        except (SerialException, TypeError) as exception:
            logger().warning("SerialException in _get_control_bytes: %s", exception)
            logger().info("offset = %d, baudrate = %d", offset, serial.baudrate)
            return b""
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
                "Message %s should start with %s. No SARAD instrument.",
                answer,
                start_byte,
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
        if self._socket is not None:
            self._destroy_socket()
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
        try:
            remaining_bytes = serial.read(number_of_remaining_bytes)
        except SerialException as exception:
            logger().warning("SerialException in _get_be_frame: %s", exception)
            return b""
        if len(remaining_bytes) < number_of_remaining_bytes:
            logger().error("Uncomplete B-E frame. Trying to complete.")
            try:
                left_bytes = serial.read_until("E", None)
            except SerialException as exception:
                logger().warning("SerialException in _get_be_frame: %s", exception)
                return b""
            return first_bytes + remaining_bytes + left_bytes
        return first_bytes + remaining_bytes

    def _open_serial(self, serial_params):
        parity_options = {"N": PARITY_NONE, "E": PARITY_EVEN}
        parity_char = serial_params["parity"]
        parity = parity_options[parity_char]
        retry = True
        baudrate = serial_params["baudrate"]
        for _i in range(0, 1):
            while retry:
                try:
                    ser = Serial(
                        self._route.port,
                        baudrate=baudrate,
                        bytesize=8,
                        xonxoff=0,
                        parity=parity,
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

    def _try_baudrate(self, serial_params, keep_serial_open, timeout, raw_cmd):
        if keep_serial_open:
            if self.__ser is None:
                ser = self._open_serial(serial_params)
            else:
                try:
                    ser = self.__ser
                    ser.baudrate = serial_params["baudrate"]
                    ser.parity = serial_params["parity"]
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
            ser = self._open_serial(serial_params)
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
        # self._new_rs485_address(raw_cmd)
        return b_answer

    def _get_transparent_reply(self, raw_cmd, timeout=0.5, keep=True):
        """Returns the raw bytestring of the instruments reply"""
        result = b""
        use_socket = (self._route.ip_address is not None) and (
            self._route.ip_port is not None
        )
        if use_socket:
            if self._socket is None:
                self._establish_socket()
            if self._socket:
                if self._send_via_socket(raw_cmd):
                    try:
                        result = self._socket.recv(1024)
                    except (
                        TimeoutError,
                        socket.timeout,
                        ConnectionResetError,
                    ) as exception:
                        logger().error("Error in socket communication: %s", exception)
            self._destroy_socket()
            return result
        logger().debug("Possible parameter sets: %s", self._serial_param_sets)
        result = b""
        for _i in range(len(self._serial_param_sets)):
            logger().debug(
                "Try to send %s with %s", raw_cmd, self._serial_param_sets[0]
            )
            result = self._try_baudrate(
                self._serial_param_sets[0], keep, timeout, raw_cmd
            )
            if result:
                logger().debug("Working with %s", self._serial_param_sets[0])
                return result
            self.release_instrument()
            self._serial_param_sets.rotate(-1)
            sleep(2)  # Give the instrument time to reset its input buffer.
        return result

    def _new_rs485_address(self, raw_cmd):
        # pylint: disable = unused-argument
        """Check whether raw_cmd changed the RS-485 bus address of the Instrument.

        If this is the case, self._route will be changed.
        This function must be overriden in the instrumen family dependent implementations.

        Args:
            raw_cmd (bytes): Command message to be analyzed.
        """

    def start_cycle(self, cycle: int) -> None:
        """Start measurement cycle.  Place holder for subclasses.

        Args:
            cycle (int): For DACM instruments this is the cycle index.
                         For Radon Scout instruments 'cycle' is the interval in seconds.
        """

    def stop_cycle(self) -> None:
        """Stop measurement cycle.  Place holder for subclasses."""

    def set_real_time_clock(self, date_time: datetime) -> bool:
        # pylint: disable=unused-argument
        """Set RTC of instrument to datetime.  Place holder for subclasses."""
        return False

    def get_recent_value(self, component_id=None, sensor_id=None, measurand_id=None):
        """Fill component objects with recent measuring values.
        This function provides a compatible API to the DACM interface."""
        logger().debug(
            "Sample interval in get_recent_value(%d, %d, %d): %s",
            component_id,
            sensor_id,
            measurand_id,
            self._interval,
        )

    def _establish_socket(self):
        logger().debug("_establish_socket")
        try:
            if self._socket is None:
                socket.setdefaulttimeout(10)
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self._ser_timeout + self.SOCKET_TIMEOUT)
                retry_counter = 2
                while retry_counter:
                    try:
                        logger().debug(
                            "Trying to connect %s:%d",
                            self._route.ip_address,
                            self._route.ip_port,
                        )
                        self._socket.connect(
                            (self._route.ip_address, self._route.ip_port)
                        )
                        retry_counter = 0
                        logger().debug(
                            "Socket @ %s:%d established",
                            self._route.ip_address,
                            self._route.ip_port,
                        )
                        return
                    except ConnectionRefusedError:
                        retry_counter = retry_counter - 1
                        logger().debug(
                            "Connection refused. %d retries left", retry_counter
                        )
                        sleep(1)
                    except (
                        TimeoutError,
                        socket.timeout,
                        ConnectionResetError,
                        BlockingIOError,
                    ) as exception:
                        logger().error(
                            "Exception connecting %s: %s",
                            self._route.ip_address,
                            exception,
                        )
                        retry_counter = 0
                self._socket = None
        except OSError as re_exception:
            logger().error("Failed to re-establish socket: %s", re_exception)
            self._socket = None

    def _destroy_socket(self):
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
                self._socket.close()
            except OSError as exception:
                logger().warning("OSError in [_destroy_socket]: %s", exception)
            self._socket = None
            logger().debug("Socket shutdown and closed.")

    def _send_via_socket(self, msg) -> bool:
        retry_counter = 2
        success = False
        while retry_counter and (self._socket is not None):
            try:
                self._socket.sendall(msg)
                retry_counter = 0
                success = True
            except OSError as exception:
                logger().error("Exception in _send_via_socket %s", exception)
                self._destroy_socket()
                self._establish_socket()
                retry_counter = retry_counter - 1
                logger().info("%d retries left", retry_counter)
                sleep(1)
        return success

    @property
    def route(self) -> Route:
        """Return route to instrument (ser. port, RS-485 address, ZigBee address)."""
        return self._route

    @route.setter
    def route(self, route: Route):
        """Set route to instrument."""
        self._route = route
        if (self._route.ip_address is not None) and (self._route.ip_port is not None):
            self._establish_socket()
        if (
            (self._route.port is not None)
            or (
                (self._route.ip_address is not None)
                and (self._route.ip_port is not None)
            )
        ) and (self._family is not None):
            self._initialize()

    @property
    def address(self):
        """Return the RS-485 address of the instrument."""
        return self._route.rs485_address

    @address.setter
    def address(self, address):
        """Set the address of the DACM module."""
        self.route.rs485_address = address
        if (self._route.port is not None) and (self._route.rs485_address is not None):
            self._initialize()

    @property
    def device_id(self) -> str:
        """Return device id."""
        return self._id

    @device_id.setter
    def device_id(self, device_id: str):
        """Set device id."""
        self._id = device_id

    @property
    def family(self) -> FamilyDict:
        """Return the instrument family."""
        return self._family

    @family.setter
    def family(self, family: FamilyDict):
        """Set the instrument family."""
        self._family = family
        self._serial_param_sets = deque(family["serial"])
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
    def components(self) -> Dict[int, Component]:
        """Return the dict of components of the device."""
        return self.__components

    @components.setter
    def components(self, components: Dict[int, Component]):
        """Set the dict of components of the device."""
        self.__components = components

    @property
    def valid_family(self) -> bool:
        """True if the family set is correct for the connected instrument."""
        return self._valid_family

    @property
    def utc_offset(self) -> Union[None, int]:
        """Return the offset of the instruments RTC to UTC."""
        return self._utc_offset

    @utc_offset.setter
    def utc_offset(self, utc_offset: int):
        """Set the offset of the instruments RTC to UTC."""
        if utc_offset > 13:
            now = datetime.now(tz=None)
            self._utc_offset = (
                datetime.now(timezone.utc).astimezone().utcoffset().seconds / 3600
            )
        else:
            self._utc_offset = utc_offset
            now = datetime.now(timezone(timedelta(hours=utc_offset)))
        logger().info("Set RTC of %s to %s", self._id, now)
        self.set_real_time_clock(now)

    @property
    def sample_interval(self) -> int:
        """Return the duration of the sampling interval in seconds."""
        return round(self._interval.total_seconds())

    @sample_interval.setter
    def sample_interval(self, sample_interval: int):
        """Set the duration of the sampling interval in seconds."""
        self._interval = timedelta(seconds=sample_interval)

    @property
    def geopos(self) -> Gps:
        """Update the GPS object if requrired and give it back."""
        return self._gps

    @geopos.setter
    def geopos(self, gps: Gps):
        """Set the geographic position of the instrument."""
        self._gps = gps

    @property
    def features(self) -> Dict[str, Any]:
        """Get the list of features that depend on firmware version or serial number."""
        features = {}
        for instr_type in self._family["types"]:
            if instr_type["type_id"] == self._type_id:
                fw_features: Dict[str, FeatureDict] = instr_type.get("fw_features", {})
                for fw_feature, feature_descr in fw_features.items():
                    if not self._software_version < feature_descr.get("since", 1000000):
                        features[fw_feature] = feature_descr.get("value", False)
                hw_features: Dict[str, FeatureDict] = instr_type.get("hw_features", {})
                for hw_feature, feature_descr in hw_features.items():
                    if not self._software_version < feature_descr.get("since", 1000000):
                        features[hw_feature] = feature_descr.get("value", False)
        return features
