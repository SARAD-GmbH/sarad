"""Module for the communication with instruments of the Network family."""

from datetime import date
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

    version = "1"

    ALLOWED_CMDS = [
        0x0C,  # GetId
        0xC0,  # GetFirstChannel
        0xC1,  # GetNextChannel
        0xC2,  # SelectChannel
        0xFE,  # CoordinatorReset
    ]

    CHANNELINFO = 0xD0
    ENDOFCHANNELLIST = 0xD1
    CHANNELSELECTED = 0xD2

    @overrides
    def __init__(self, family=SaradInst.products[2]):
        super().__init__(family)
        self._date_of_manufacture = None
        self._date_of_update = None
        self._byte_order: Literal["little", "big"] = "big"

    def __str__(self):
        output = super().__str__() + (
            f"LastUpdate: {self.date_of_update}\n"
            f"DateOfManufacture: {self.date_of_manufacture}\n"
            f"Address: {self.address}\n"
        )
        return output

    def _sanitize_date(self, year, month, day):
        """This is to handle date entries that don't exist."""
        try:
            return date(year, month, day)
        except ValueError as exception:
            logger().warning(exception)
            first_word = str(exception).split(" ", maxsplit=1)[0]
            if first_word == "year":
                self._sanitize_date(1971, month, day)
            elif first_word == "month":
                if 1 <= day <= 12:
                    sanitized_month = day
                    sanitized_day = month
                    self._sanitize_date(year, sanitized_month, sanitized_day)
                else:
                    self._sanitize_date(year, 1, day)
            elif first_word == "day":
                self._sanitize_date(year, month, 1)
        return None

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
        """Stop a measurement cycle."""
        ok_byte = self.CHANNELSELECTED
        reply = self.get_reply([b"\xC0", b""], 1)
        if reply and (reply[0] == ok_byte):
            return reply
        return False

    def get_address(self):
        """Return the address of the DACM module."""
        return self._route.rs485_address

    def set_address(self, address):
        """Set the address of the DACM module."""
        self.route.rs485_address = address
        if (self._route.port is not None) and (self._route.rs485_address is not None):
            self._initialize()

    def get_date_of_manufacture(self):
        """Return the date of manufacture."""
        return self._date_of_manufacture

    def get_date_of_update(self):
        """Return the date of firmware update."""
        return self._date_of_update

    address = property(get_address, set_address)
    date_of_manufacture = property(get_date_of_manufacture)
    date_of_update = property(get_date_of_update)

    @property
    def type_name(self) -> str:
        """Return the device type name."""
        for type_in_family in self.family["types"]:
            if type_in_family["type_id"] == self.type_id:
                return type_in_family["type_name"]
        return "unknown"
