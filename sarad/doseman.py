"""Module for the communication with instruments of the DOSEman family."""

from overrides import overrides  # type: ignore

from sarad.sari import CheckedAnswerDict, SaradInst, logger


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

    version = "0.3"

    ALLOWED_CMDS = [
        0x10,  # SetDeviceId
        0x11,
        0x12,
        0x13,
        0x14,
        0x15,
        0x20,
        0x21,
        0x22,
        0x23,
        0x24,
        0x25,
        0x25,
        0x26,
        0x30,  # SetTime
        0x31,  # DeviceSetup
        0x32,
        0x33,
        0x34,
        0x35,
        0x40,
        0x41,
        0x42,
        0x43,
        0x44,
        0x45,
        0x50,
        0x51,
        0x52,
        0x53,
        0x54,
        0x55,
        0x60,
        0x61,
        0x62,
        0x63,
        0x64,
        0x65,
        0x70,
        0x71,
        0x72,
        0x73,
        0xC2,  # SelectChannel
        0xFE,  # CoordinatorReset
    ]

    @overrides
    def __init__(self, family=SaradInst.products[0]):
        super().__init__(family)
        self._last_sampling_time = None

    @overrides
    def get_message_payload(self, message: bytes, timeout=0.1) -> CheckedAnswerDict:
        """Send a message to the instrument and give back the payload of the reply.

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
        if not self.check_cmd(message):
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
        # Run _check_message to get the payload of the sent message.
        checked_message = self._check_message(message, False)
        # If this is a get-data command, we expect multiple B-E frames.
        multiframe = checked_message["payload"] in [b"\x60", b"\x61"]
        answer = self._get_transparent_reply(message, timeout=timeout, keep=True)
        if answer == b"":
            # Workaround for firmware bug in SARAD instruments.
            logger().debug("Play it again, Sam!")
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
        """Stop the measuring cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x15", b""], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    @overrides
    def start_cycle(self, cycle_index):
        """Start a measuring cycle.
        TODO: rewrite or remove
        self.get_config()  # to set self.__interval
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self.__interval
        self._last_sampling_time = datetime.utcnow()
        return self.stop_cycle() and self._push_button()
        """
