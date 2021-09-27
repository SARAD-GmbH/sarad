"""Module for the communication with instruments of the DOSEman family."""

import logging
from datetime import datetime

from sarad.sari import SaradInst

_LOGGER = None


def logger():
    """Returns the logger instance used in this module."""
    global _LOGGER
    _LOGGER = _LOGGER or logging.getLogger(__name__)
    return _LOGGER


# * DosemanInst:
# ** Definitions:
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

    # ** Private methods:
    def __init__(self, port=None, family=None):
        if family is None:
            family = SaradInst.products[0]
        SaradInst.__init__(self, port, family)
        self._last_sampling_time = None

    # ** Public methods:
    # *** stop_cycle(self):

    def stop_cycle(self):
        """Stop the measuring cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x15", b""], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    # *** start_cycle(self, cycle_index):

    def start_cycle(self, _):
        """Start a measuring cycle."""
        self.get_config()  # to set self.__interval
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self.__interval
        self._last_sampling_time = datetime.utcnow()
        return self.stop_cycle() and self._push_button()
