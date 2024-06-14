"""
Module for the communication with instruments of the DOSEman family.
"""

from overrides import overrides  # type: ignore

from sarad.global_helpers import sarad_family
from sarad.logger import logger
from sarad.sari import SaradInst
from sarad.typedef import CheckedAnswerDict


class DosemanInst(SaradInst):
    """
    Instrument with Doseman communication protocol

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
        get_reply()
    """

    RET_INVALID = 1
    SER_TIMEOUT = 0.5

    @overrides
    def __init__(self, family=sarad_family(1)):
        super().__init__(family)
        self._last_sampling_time = None

    @overrides
    def get_description(self) -> bool:
        """Set instrument type, software version, and serial number."""
        id_cmd = self.family["get_id_cmd"]
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply(id_cmd, timeout=self.SER_TIMEOUT)
        if reply:
            if reply[0] == ok_byte:
                logger().debug("Get description successful.")
                try:
                    self._type_id = reply[1]
                    self._software_version = reply[2]
                    self._serial_number = int.from_bytes(
                        reply[3:5], byteorder="little", signed=False
                    )
                    if (self._type_id != 200) and (self.family["family_id"] == 4):
                        logger().info("This seemed like a Network device, but isn't.")
                        self._valid_family = False
                        return False
                    return True
                except (TypeError, ReferenceError, LookupError) as exception:
                    logger().error("Error when parsing the payload: %s", exception)
                    return False
            elif reply[0] == self.RET_INVALID:
                logger().info(
                    "DOSEman family with running measurement. Trying to stop."
                )
                self._type_id = 0
                self._software_version = 0
                self._serial_number = 0
                self._valid_family = True
                self.stop_cycle()
                return self.get_description()
        logger().debug("Get description failed. Instrument replied = %s", reply)
        return False

    @overrides
    def get_message_payload(self, message: bytes, timeout=0.1) -> CheckedAnswerDict:
        """
        Send a message to the instrument and give back the payload of the reply.

        Args:
            message:
                The message to send.
            timeout:
                Timeout for waiting for a reply from instrument.
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

        if message != b"":
            cmd_is_valid = self.check_cmd(message)
        else:
            cmd_is_valid = True
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
        if message == b"":
            multiframe = True
        else:
            # Run _check_message to get the payload of the sent message.
            checked_message = self._check_message(message, False)
            # If this is a get-data command, we expect multiple B-E frames.
            multiframe = checked_message["payload"] in [b"\x60", b"\x61"]
        answer = self._get_transparent_reply(message, timeout=timeout, keep=True)
        checked_answer = self._check_message(answer, multiframe)
        logger().debug(checked_answer)
        if answer == message:
            logger().debug("Echo. Get next frame!")
            answer = self._get_transparent_reply(b"", timeout=timeout, keep=True)
            checked_answer = self._check_message(answer, multiframe)
        return {
            "is_valid": checked_answer["is_valid"],
            "is_control": checked_answer["is_control"],
            "is_last_frame": checked_answer["is_last_frame"],
            "payload": checked_answer["payload"],
            "number_of_bytes_in_payload": checked_answer["number_of_bytes_in_payload"],
            "raw": answer,
            "standard_frame": checked_answer["standard_frame"],
        }

    @overrides
    def stop_cycle(self):
        """
        Stop the measuring cycle.
        """

        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x33", b""], timeout=self.SER_TIMEOUT + 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    @overrides
    def start_cycle(self, cycle):
        """
        Start a measuring cycle.

        TODO: rewrite or remove

        self.get_config()  # to set self._interval
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self._interval
        self._last_sampling_time = datetime.utcnow()
        return self.stop_cycle() and self._push_button()
        """
