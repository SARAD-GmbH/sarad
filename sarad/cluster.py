"""Module to handle a cluster of SARAD instruments.

All instruments forming a cluster are connected to
the same instrument controller.
SaradCluster is used as singleton."""

import logging
import pickle
from datetime import datetime
from typing import IO, Any, Dict, Generic, Iterator, List, Optional

import hashids  # type: ignore
import serial.tools.list_ports  # type: ignore

from sarad.dacm import DacmInst
from sarad.doseman import DosemanInst
from sarad.radonscout import RscInst
from sarad.sari import SI, SaradInst

logger = logging.getLogger(__name__)


# * SaradCluster:
# ** Definitions:
class SaradCluster(Generic[SI]):
    """Class to define a cluster of SARAD instruments
    that are all connected to one controller

    Properties:
        native_ports
        active_ports
        connected_instruments
        start_time
    Public methods:
        set_native_ports()
        get_native_ports()
        get_active_ports()
        get_connected_instruments()
        update_connected_instruments()
        synchronize(): Stop all instruments, set time, start all measurings
        dump(): Save all properties to a Pickle file"""

    version: str = "0.1"

    def __init__(self, native_ports: Optional[List[int]] = None) -> None:
        if native_ports is None:
            native_ports = []
        self.__native_ports = native_ports
        self.__start_time = datetime.min
        self.__connected_instruments: List[SI] = []
        self.__active_ports: List[int] = []

    # ** Private methods:

    def __iter__(self) -> Iterator[SI]:
        return iter(self.__connected_instruments)

    # ** Public methods:
    # *** synchronize(self, cycles_dict):

    def synchronize(self, cycles_dict: Dict[str, int]) -> bool:
        """Stop measuring cycles of all connected instruments.
        Set instrument time to UTC on all instruments.
        Start measuring cycle on all instruments according to dictionary
        in cycles_dict."""
        for instrument in self.connected_instruments:
            try:
                instrument.stop_cycle()
            except Exception:  # pylint: disable=broad-except
                logger.error("Not all instruments have been stopped as intended.")
                return False
        self.__start_time = datetime.utcnow()
        for instrument in self.connected_instruments:
            try:
                instrument.set_real_time_clock(self.__start_time)
                logger.debug("Clock set to UTC on device %s", instrument.device_id)
                logger.debug("Cycles_dict = %s", cycles_dict)
                if instrument.device_id in cycles_dict:
                    cycle_index = cycles_dict[instrument.device_id]
                    logger.debug(
                        "Cycle_index for device %s is %d",
                        instrument.device_id,
                        cycle_index,
                    )
                else:
                    cycle_index = 0
                instrument.start_cycle(cycle_index)
                logger.debug(
                    "Device %s started with cycle_index %d",
                    instrument.device_id,
                    cycle_index,
                )
            except Exception:  # pylint: disable=broad-except
                logger.error("Failed to set time and start cycles on all instruments.")
                return False
        return True

    # *** update_connected_instruments(self):

    def update_connected_instruments(self, ports_to_test=None) -> List[SI]:
        """Update the list of connected instruments
        in self.__connected_instruments and return this list."""
        hid = hashids.Hashids()
        if ports_to_test is None:
            ports_to_test = self.active_ports
        logger.info("%d ports to test", len(ports_to_test))
        # We check every active port and try for a connected SARAD instrument.
        connected_instruments = []  # a list of instrument objects
        # NOTE: The order of tests is very important, because the only
        # difference between RadonScout and DACM GetId commands is the
        # length of reply. Since the reply for DACM is longer than that for
        # RadonScout, the test for RadonScout has always to be made before
        # that for DACM.
        # If ports_to_test is specified, only that list of ports
        # will be checked for instruments,
        # otherwise all available ports will be scanned.
        for family in SaradInst.products:
            if family["family_id"] == 1:
                family_class: Any = DosemanInst
            elif family["family_id"] == 2:
                family_class = RscInst
            elif family["family_id"] == 5:
                family_class = DacmInst
            else:
                continue
            test_instrument = family_class()
            test_instrument.family = family
            ports_with_instruments = []
            logger.info(ports_to_test)
            for port in ports_to_test:
                logger.info("Testing port %s for %s.", port, family["family_name"])
                test_instrument.port = port
                if test_instrument.type_id and test_instrument.serial_number:
                    device_id = hid.encode(
                        test_instrument.family["family_id"],
                        test_instrument.type_id,
                        test_instrument.serial_number,
                    )
                    test_instrument.device_id = device_id
                    logger.info("%s found on port %s.", family["family_name"], port)
                    connected_instruments.append(test_instrument)
                    ports_with_instruments.append(port)
                    if (ports_to_test.index(port) + 1) < len(ports_to_test):
                        test_instrument = family_class()
                        test_instrument.family = family
            for port in ports_with_instruments:
                ports_to_test.remove(port)
        self.__connected_instruments = connected_instruments
        return connected_instruments

    # *** dump(self, file):

    def dump(self, file: IO[bytes]) -> None:
        """Save the cluster information to a file."""
        logger.debug("Pickling mycluster into file.")
        pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)

    # ** Properties:
    # *** active_ports:

    @property
    def active_ports(self) -> List[int]:
        """SARAD instruments can be connected:
        1. by RS232 on a native RS232 interface at the computer
        2. via their built in FT232R USB-serial converter
        3. via an external USB-serial converter (Prolific, Prolific fake, FTDI)
        4. via the SARAD ZigBee coordinator with FT232R"""
        active_ports = []
        # Get the list of accessible native ports
        for port in serial.tools.list_ports.comports():
            if port.device in self.__native_ports:
                active_ports.append(port)
        # FTDI USB-to-serial converters
        active_ports.extend(serial.tools.list_ports.grep("0403"))
        # Prolific and no-name USB-to-serial converters
        active_ports.extend(serial.tools.list_ports.grep("067B"))
        # Actually we don't want the ports but the port devices.
        self.__active_ports = []
        for port in active_ports:
            self.__active_ports.append(port.device)
        return self.__active_ports

    # *** connected_instruments:

    @property
    def connected_instruments(self) -> List[SI]:
        """Return list of connected instruments."""
        return self.__connected_instruments

    # *** native_ports:

    @property
    def native_ports(self) -> List[int]:
        """Return the list of all native serial ports (RS-232 ports)
        available at the instrument controller."""
        return self.__native_ports

    @native_ports.setter
    def native_ports(self, native_ports: List[int]) -> None:
        """Set the list of native serial ports that shall be used."""
        self.__native_ports = native_ports

    # *** start_time:

    @property
    def start_time(self) -> datetime:
        """Get a pre-defined start time for all instruments in this cluster."""
        return self.__start_time

    @start_time.setter
    def start_time(self, start_time: datetime) -> None:
        """Set a start time for all instruments in this cluster."""
        self.__start_time = start_time


# * Initialize mycluster as a singleton # TODO: In Hauptprogramm übernehmen
#mycluster: SaradCluster = SaradCluster()
#mycluster.update_connected_instruments()
#logger.debug(mycluster.__dict__)

# * Test environment:
if __name__ == "__main__":

    for connected_instrument in mycluster:
        print(connected_instrument)

    # Example access on first device
    if len(mycluster.connected_instruments) > 0:
        inst = mycluster.connected_instruments[0]
