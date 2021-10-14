"""Module for the communication with instruments of the DOSEman family."""

import logging
from datetime import datetime
from time import perf_counter, sleep

from overrides import overrides  # type: ignore
from serial import STOPBITS_ONE, Serial  # type: ignore

from sarad.sari import SaradInst

_LOGGER = None


def logger():
    """Returns the logger instance used in this module."""
    global _LOGGER
    _LOGGER = _LOGGER or logging.getLogger(__name__)
    return _LOGGER


class DosemanInst(SaradInst):
    """Instrument with Doseman communication protocol

    Inherited properties:
        port
        device_id
        family
        type_id
        type_name
        software_version
        serial_number
        components: List of sensor or actor components
    Inherited Public methods:
        get_reply()"""

    version = "0.1"

    def __init__(self, port=None, family=None):
        if family is None:
            family = SaradInst.products[0]
        SaradInst.__init__(self, port, family)
        self._last_sampling_time = None

    @staticmethod
    def _close_serial(serial, keep):
        serial.flush()
        if not keep:
            serial.close()
            logger().debug("Serial interface closed.")
            return None
        logger().debug("Store serial interface")
        return serial

    def __get_be_frame(self, serial, keep):
        """Get one Rx B-E frame"""
        first_bytes = self._get_control_bytes(serial)
        if first_bytes == b"":
            self.__ser = self._close_serial(serial, keep)
            return b""
        number_of_remaining_bytes = self._get_payload_length(first_bytes) + 3
        remaining_bytes = serial.read(number_of_remaining_bytes)
        return first_bytes + remaining_bytes

    @overrides
    def _get_transparent_reply(self, raw_cmd, timeout=0.1, keep=True):
        """Returns the raw bytestring of the instruments reply"""
        if not keep:
            ser = Serial(
                self._port,
                self._family["baudrate"],
                bytesize=8,
                xonxoff=0,
                timeout=timeout,
                parity=self._family["parity"],
                rtscts=0,
                stopbits=STOPBITS_ONE,
            )
            if not ser.is_open:
                ser.open()
            logger().debug("Open serial, don't keep.")
        else:
            try:
                ser = self.__ser
                logger().debug("Reuse stored serial interface")
                if not ser.is_open:
                    logger().debug("Port is closed. Reopen.")
                    ser.open()
            except AttributeError:
                ser = Serial(
                    self._port,
                    self._family["baudrate"],
                    bytesize=8,
                    xonxoff=0,
                    timeout=timeout,
                    parity=self._family["parity"],
                    rtscts=0,
                    stopbits=STOPBITS_ONE,
                    exclusive=True,
                )
                if not ser.is_open:
                    ser.open()
                logger().debug("Open serial")
        perf_time_0 = perf_counter()
        for element in raw_cmd:
            byte = (element).to_bytes(1, "big")
            ser.write(byte)
            sleep(self._family["write_sleeptime"])
        perf_time_1 = perf_counter()
        logger().debug(
            "Writing command %s to serial took me %f s",
            raw_cmd,
            perf_time_1 - perf_time_0,
        )
        sleep(self._family["wait_for_reply"])
        be_frame = self.__get_be_frame(ser, True)
        answer = bytearray(be_frame)
        logger().warning(be_frame)
        while ser.in_waiting:
            logger().warning("%d bytes waiting", ser.in_waiting)
            be_frame = self.__get_be_frame(ser, True)
            logger().warning(be_frame)
            answer.extend(be_frame)
            sleep(0.2)
        perf_time_2 = perf_counter()
        logger().debug(
            "Receiving %s from serial took me %f s",
            bytes(answer),
            perf_time_2 - perf_time_1,
        )
        self.__ser = self._close_serial(ser, keep)
        return bytes(answer)

    def stop_cycle(self):
        """Stop the measuring cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x15", b""], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    def start_cycle(self, _):
        """Start a measuring cycle."""
        self.get_config()  # to set self.__interval
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self.__interval
        self._last_sampling_time = datetime.utcnow()
        return self.stop_cycle() and self._push_button()
