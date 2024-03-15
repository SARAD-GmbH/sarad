"""Module for the communication with instruments of the Network family."""

from typing import Literal

from overrides import overrides  # type: ignore

from sarad.sari import SaradInst, logger


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

    CHANNELINFO = 0xD0
    ENDOFCHANNELLIST = 0xD1
    CHANNELSELECTED = 0xD2

    @overrides
    def __init__(self, family=SaradInst.products[2]):
        super().__init__(family)
        self._date_of_manufacture = None
        self._date_of_update = None
        self._byte_order: Literal["little", "big"] = "big"

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
        if reply and (reply[0] == self.CHANNELINFO):
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
        if reply and (reply[0] == self.ENDOFCHANNELLIST):
            return False
        logger().error("Unexpected reply to get_first_channel: %s", reply)
        return False

    def get_next_channel(self):
        """Get information about the instrument connected via next available channel."""
        reply = self.get_reply([b"\xC1", b""], timeout=3)
        if reply and (reply[0] == self.CHANNELINFO):
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
        if reply and (reply[0] == self.ENDOFCHANNELLIST):
            return False
        logger().error("Unexpected reply to get_next_channel: %s", reply)
        return False

    def get_address(self):
        """Return the address of the DACM module."""
        return self._route.rs485_address

    def set_address(self, address):
        """Set the address of the DACM module."""
        self.route.rs485_address = address
        if (self._route.port is not None) and (self._route.rs485_address is not None):
            self._initialize()

    address = property(get_address, set_address)

    @property
    def type_name(self) -> str:
        """Return the device type name."""
        for type_in_family in self.family["types"]:
            if type_in_family["type_id"] == self.type_id:
                return type_in_family["type_name"]
        return "unknown"
