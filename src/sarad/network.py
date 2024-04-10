"""Module for the communication with instruments of the Network family."""

from overrides import overrides  # type: ignore

from sarad.global_helpers import logger, sarad_family
from sarad.sari import SaradInst


class NetworkInst(SaradInst):
    # pylint: disable=too-many-instance-attributes
    """Devices for networking with SARAD instruments.
    Currently this is only the Zigbee Coordinator.

    Inherited properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        device_id: Identifier for an individual instrument in a cluster
        type_id
        software_version
        serial_number
        components: List of sensor or actor components
    Inherited methods from SaradInst:
        get_reply()
    Public methods:
    """

    CHANNEL_INFO = 0xD0
    END_OF_CHANNEL_LIST = 0xD1
    CHANNEL_SELECTED = 0xD2

    @overrides
    def __init__(self, family=sarad_family(4)):
        super().__init__(family)
        self._date_of_manufacture = None
        self._date_of_update = None
        self._channels = []

    @overrides
    def _new_rs485_address(self, raw_cmd):
        """Check whether raw_cmd changed the RS-485 bus address of the instrument.
        If this is the case, self._route will be changed.

        Args:
            raw_cmd (bytes): Command message to be analyzed.
        """
        cmd_dict = self._analyze_cmd_data(
            payload=self._check_message(
                message=raw_cmd,
                multiframe=False,
            )["payload"]
        )
        logger().debug("cmd_dict = %s", cmd_dict)
        if cmd_dict["cmd"] == b"\x02":  # set_module_information
            data_list = list(cmd_dict["data"])
            old_rs485_address = self._route.rs485_address
            self._route.rs485_address = data_list[0]
            logger().info(
                "Change RS-485 bus address from %d into %d",
                old_rs485_address,
                self._route.rs485_address,
            )

    def get_first_channel(self):
        """Get information about the instrument connected via first available channel."""
        reply = self.get_reply([b"\xC0", b""], timeout=3)
        if reply and (reply[0] == self.CHANNEL_INFO):
            return {
                "short_address": int.from_bytes(
                    reply[1:3], byteorder="little", signed=False
                ),
                "device_type": reply[3],
                "firmware_version": reply[4],
                "serial_number": int.from_bytes(
                    reply[5:7], byteorder="big", signed=False
                ),
                "family_id": reply[7],
            }
        if reply and (reply[0] == self.END_OF_CHANNEL_LIST):
            return False
        logger().error("Unexpected reply to get_first_channel: %s", reply)
        return False

    def get_next_channel(self):
        """Get information about the instrument connected via next available channel."""
        reply = self.get_reply([b"\xC1", b""], timeout=3)
        if reply and (reply[0] == self.CHANNEL_INFO):
            return {
                "short_address": int.from_bytes(
                    reply[1:3], byteorder="little", signed=False
                ),
                "device_type": reply[3],
                "firmware_version": reply[4],
                "serial_number": int.from_bytes(
                    reply[5:7], byteorder="big", signed=False
                ),
                "family_id": reply[7],
            }
        if reply and (reply[0] == self.END_OF_CHANNEL_LIST):
            return False
        logger().error("Unexpected reply to get_next_channel: %s", reply)
        return False

    def scan(self):
        """Scan for SARAD instruments connected via ZigBee end points"""
        reply = self.get_first_channel()
        while reply:
            self._channels.append(reply)
            reply = self.get_next_channel()
        return self._channels

    def coordinator_reset(self):
        """Restart the coordinator. Same as power off -> on."""
        reply = self.get_reply([b"\xFE", b"\x00\x00"], timeout=3)
        if reply and (reply[0] == self.CHANNEL_SELECTED):
            return reply
        logger().error("Unexpecte reply to coordinator_reset: %s", reply)
        return False

    @property
    def type_name(self) -> str:
        """Return the device type name."""
        for type_in_family in self.family["types"]:
            if type_in_family["type_id"] == self.type_id:
                return type_in_family["type_name"]
        return "unknown"
