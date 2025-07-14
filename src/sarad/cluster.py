"""Module to handle a cluster of SARAD instruments.

All instruments forming a cluster are connected to
the same instrument controller.
SaradCluster is used as singleton."""

import logging
import logging.config
import pickle
from datetime import datetime, timezone
from typing import IO, Dict, Generic, Iterator, List, Optional, Set

from serial.serialutil import SerialException
from serial.tools import list_ports  # type: ignore

from sarad.doseman import DosemanInst
from sarad.global_helpers import decode_instr_id, encode_instr_id, sarad_family
from sarad.mapping import id_family_mapping
from sarad.sari import SI, Route, SaradInst

_LOGGER = None


def logger():
    """Returns the logger instance used in this module."""
    global _LOGGER
    _LOGGER = _LOGGER or logging.getLogger(__name__)
    return _LOGGER


class SaradCluster(Generic[SI]):
    """Class to define a cluster of SARAD instruments
    that are all connected to one controller

    Properties:
        native_ports
        ignore_ports
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

    @staticmethod
    def get_instrument(device_id, route: Route) -> Optional[SaradInst]:
        """Get the instrument object for an instrument
        with know device_id that can be reached over a known route

        Args:
            device_id (str): device id of the instrument encoding
                family, type and serial number
            route (Route): serial interface, RS-485 address, ZigBee address
                the instrument is connected to

        Returns:
            SaradInst object
        """
        family_id = decode_instr_id(device_id)[0]
        instrument = id_family_mapping[family_id]
        instrument.device_id = device_id
        instrument.route = route
        return instrument

    def __init__(
        self,
        native_ports: Optional[List[str]] = None,
        ignore_ports: Optional[List[str]] = None,
        rs485_ports: Optional[Dict[str, List[int]]] = None,
    ) -> None:
        if native_ports is None:
            native_ports = []
        self.__native_ports = set(native_ports)
        if ignore_ports is None:
            ignore_ports = []
        self.__ignore_ports = set(ignore_ports)
        if rs485_ports is None:
            rs485_ports = {}
        self.__rs485_ports = rs485_ports
        self.__start_time = datetime.fromtimestamp(0)
        self.__connected_instruments: List[SaradInst] = []
        self.__active_ports: Set[str] = set()

    def __iter__(self) -> Iterator[SaradInst]:
        return iter(self.__connected_instruments)

    def _guess_family(self, this_port):
        family_mapping = [
            (r"(?i)irda", 1),
            (r"(?i)monitor", 5),
            (r"(?i)scout|(?i)smart", 2),
            (r"(?i)ft232", 4),
        ]
        for mapping in family_mapping:
            for port in list_ports.grep(mapping[0]):
                if this_port == port.device:
                    guessed_family = mapping[1]
                    logger().info(
                        "%s, %s, #%d",
                        port.device,
                        port.description,
                        guessed_family,
                    )
        if guessed_family is None:
            guessed_family = 1  # DOSEman family is the default
            for port in list_ports.comports():
                if this_port == port.device:
                    logger().info(
                        "%s, %s, #%d",
                        port.device,
                        port.description,
                        guessed_family,
                    )
        return guessed_family

    def synchronize(self, cycles_dict: Dict[str, int]) -> bool:
        """Stop measuring cycles of all connected instruments.
        Set instrument time to UTC on all instruments.
        Start measuring cycle on all instruments according to dictionary
        in cycles_dict."""
        for instrument in self.connected_instruments:
            try:
                instrument.stop_cycle()
            except Exception:  # pylint: disable=broad-except
                logger().error("Not all instruments have been stopped as intended.")
                raise
        self.__start_time = datetime.now(tzinfo=timezone.utc)
        for instrument in self.connected_instruments:
            try:
                instrument.set_real_time_clock(self.__start_time)
                logger().debug("Clock set to UTC on device %s", instrument.device_id)
                logger().debug("Cycles_dict = %s", cycles_dict)
                if instrument.device_id in cycles_dict:
                    cycle_index = cycles_dict[instrument.device_id]
                    logger().debug(
                        "Cycle_index for device %s is %d",
                        instrument.device_id,
                        cycle_index,
                    )
                else:
                    cycle_index = 0
                instrument.start_cycle(cycle_index)
                logger().debug(
                    "Device %s started with cycle_index %d",
                    instrument.device_id,
                    cycle_index,
                )
            except Exception:  # pylint: disable=broad-except
                logger().error(
                    "Failed to set time and start cycles on all instruments."
                )
                raise
        return True

    def _test_ports(self, ports_to_test):
        """Take a list of ports and test them for connected SARAD instruments.

        Args:
            ports_to_test: List of serial ports

        Returns:
            Set[SaradInst]: Set of detected SARAD instruments
        """
        added_instruments = set()
        logger().debug("%d port(s) to test: %s", len(ports_to_test), ports_to_test)
        # We check every port in ports_to_test and try for a connected SARAD instrument.
        for port in reversed(ports_to_test):
            # remove an instrument maybe preexisting on this port
            for instrument in self.__connected_instruments:
                if instrument.route.port == port:
                    logger().debug(
                        "Remove %s on %s from instrument list", instrument, port
                    )
                    self.__connected_instruments.remove(instrument)
            if self._guess_family(port) in (2, 4, 5):
                instruments_to_test = (SaradInst(family=sarad_family(0)), DosemanInst())
            else:
                instruments_to_test = (DosemanInst(), SaradInst(family=sarad_family(0)))
            route = Route(port=port, rs485_address=None, zigbee_address=None)
            for test_instrument in instruments_to_test:
                try:
                    test_instrument.route = route
                    if not test_instrument.valid_family:
                        logger().debug(
                            "Family %s not valid on port %s",
                            test_instrument.family["family_name"],
                            route.port,
                        )
                        test_instrument.release_instrument()
                        continue
                    logger().debug(
                        "type_id = %d, serial_number = %d",
                        test_instrument.type_id,
                        test_instrument.serial_number,
                    )
                    if test_instrument.type_id and test_instrument.serial_number:
                        instr_id = encode_instr_id(
                            test_instrument.family["family_id"],
                            test_instrument.type_id,
                            test_instrument.serial_number,
                        )
                        test_instrument.device_id = instr_id
                        logger().debug(
                            "%s found on route %s.",
                            test_instrument.family["family_name"],
                            route,
                        )
                        test_instrument.release_instrument()
                        break
                    test_instrument.release_instrument()
                except (SerialException, OSError) as exception:
                    logger().error("%s not accessible: %s", route, exception)
                    break
            if instr_id is not None:
                added_instruments.add(test_instrument)
        return added_instruments

    def _test_rs485(self):
        """Take a list of ports from self.__rs485_ports and
        test them for SARAD instruments connected via addressable RS-485.

        Returns:
            Set[SaradInst]: Set of detected SARAD instruments

        """
        added_instruments = set()
        logger().debug(
            "%d port(s) to test for RS-485: %s",
            len(self.__rs485_ports),
            self.__rs485_ports,
        )
        # We check every port in ports_to_test and try for a connected SARAD instrument.
        for port in self.__rs485_ports:
            if port in self.__ignore_ports:
                break
            for rs485_address in self.__rs485_ports[port]:
                # remove an instrument maybe preexisting on this port
                for instrument in self.__connected_instruments:
                    if instrument.route.port == port:
                        logger().debug(
                            "Remove %s on %s from instrument list", instrument, port
                        )
                        self.__connected_instruments.remove(instrument)

                instruments_to_test = (DosemanInst(), SaradInst(family=sarad_family(0)))
                route = Route(
                    port=port, rs485_address=rs485_address, zigbee_address=None
                )
                for test_instrument in instruments_to_test:
                    try:
                        test_instrument.route = route
                        if not test_instrument.valid_family:
                            logger().debug(
                                "Family %s not valid on port %s",
                                test_instrument.family["family_name"],
                                route.port,
                            )
                            test_instrument.release_instrument()
                            continue
                        logger().debug(
                            "type_id = %d, serial_number = %d",
                            test_instrument.type_id,
                            test_instrument.serial_number,
                        )
                        if test_instrument.type_id and test_instrument.serial_number:
                            instr_id = encode_instr_id(
                                test_instrument.family["family_id"],
                                test_instrument.type_id,
                                test_instrument.serial_number,
                            )
                            test_instrument.device_id = instr_id
                            logger().debug(
                                "%s found on route %s.",
                                test_instrument.family["family_name"],
                                route,
                            )
                            test_instrument.release_instrument()
                            break
                        test_instrument.release_instrument()
                    except (SerialException, OSError) as exception:
                        logger().error("%s not accessible: %s", route, exception)
                        break
                if instr_id is not None:
                    added_instruments.add(test_instrument)
        return added_instruments

    def _remove_occupied_ports(self, ports_to_test, active_instruments):
        """Return a new list of ports_to_test where all ports of
        active_instruments are removed."""
        active_ports = []
        for instrument in active_instruments:
            active_ports.append(instrument.route.port)
        return list(set(ports_to_test).difference(set(active_ports)))

    def update_connected_instruments(
        self, ports_to_test=None, ports_to_skip=None
    ) -> List[SaradInst]:
        """Update the list of connected instruments
        in self.__connected_instruments and return this list.

        Args:
            ports_to_test (List[str]): list of serial device ids to test.
                If None, the function will test all serial devices in self.active_ports.
                If given, the function will test serial devices in ports_to_test
                and add newly detected instruments to self.__connected_instruments.
                If no instrument can be found on one of the ports, the instrument
                will be removed from self.__connected_instruments.
            ports_to_skip (List[str]): list of serial device ids that shall be skipped.
                The difference between ports_to_test and ports_to_skip
                gives the list of ports that will be used
                to look for newly connected instruments.

        Returns:
            List of instruments added to self.__connected_instruments.
            [] if instruments have been removed.
        """
        logger().debug("[update_connected_instruments]")
        if ports_to_test is None:
            ports_to_test = self.active_ports
        if ports_to_skip is not None:
            logger().debug("Test: %s, Skip: %s", ports_to_test, ports_to_skip)
            ports_to_test = list(set(ports_to_test).difference(set(ports_to_skip)))
            logger().debug("Difference: %s", ports_to_test)
            if not ports_to_test:
                logger().warning(
                    "Nothing to do. "
                    "Set of serial ports to skip is equal to set of active ports."
                )
                return []
        added_instruments = self._test_ports(ports_to_test)
        ports_to_test = self._remove_occupied_ports(ports_to_test, added_instruments)
        lagged_instruments = self._test_ports(ports_to_test)
        added_instruments = added_instruments.union(lagged_instruments)
        added_rs485_instruments = self._test_rs485()
        added_instruments = added_instruments.union(added_rs485_instruments)
        # remove duplicates
        self.__connected_instruments = list(
            added_instruments.union(self.__connected_instruments)
        )
        logger().debug("Connected instruments: %s", self.__connected_instruments)
        for instrument in self.__connected_instruments:
            try:
                instrument.release_instrument()
            except SerialException:
                logger().critical("Cannot release %s", instrument.route.port)
                raise
        return list(added_instruments)

    def dump(self, file: IO[bytes]) -> None:
        """Save the cluster information to a file."""
        logger().debug("Pickling mycluster into file.")
        pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)

    @property
    def active_ports(self) -> List[str]:
        """SARAD instruments can be connected:
        1. by RS232 on a native RS232 interface at the computer
        2. via their built in FT232R USB-serial converter
        3. via an external USB-serial converter (Prolific, Prolific fake, FTDI)
        4. via the SARAD ZigBee coordinator with FT232R"""
        active_ports = []
        # Get the list of accessible native ports
        for port in list_ports.comports():
            if port.device in self.__native_ports:
                active_ports.append(port)
        # FTDI USB-to-serial converters
        active_ports.extend(list_ports.grep("0403"))
        # Prolific and no-name USB-to-serial converters
        active_ports.extend(list_ports.grep("067B"))
        # Actually we don't want the ports but the port devices.
        set_of_ports = set()
        for port in active_ports:
            set_of_ports.add(port.device)
        self.__active_ports = set()
        for port in set_of_ports:
            if port not in self.__ignore_ports:
                self.__active_ports.add(port)
        logger().debug("Native ports: %s", self.__native_ports)
        logger().debug("Ignored ports: %s", self.__ignore_ports)
        logger().debug("Active ports: %s", self.__active_ports)
        return list(self.__active_ports)

    @property
    def connected_instruments(self) -> List[SaradInst]:
        """Return list of connected instruments."""
        return self.__connected_instruments

    @property
    def native_ports(self) -> Optional[List[str]]:
        """Return the list of all native serial ports (RS-232 ports)
        available at the instrument controller."""
        return list(self.__native_ports)

    @native_ports.setter
    def native_ports(self, native_ports: List[str]) -> None:
        """Set the list of native serial ports that shall be used."""
        self.__native_ports = set(native_ports)

    @property
    def ignore_ports(self) -> Optional[List[str]]:
        """Return the list of all serial ports
        at the instrument controller that shall be ignored."""
        return list(self.__ignore_ports)

    @ignore_ports.setter
    def ignore_ports(self, ignore_ports: List[str]) -> None:
        """Set the list of serial ports that shall be ignored."""
        self.__ignore_ports = set(ignore_ports)

    @property
    def start_time(self) -> datetime:
        """Get a pre-defined start time for all instruments in this cluster."""
        return self.__start_time

    @start_time.setter
    def start_time(self, start_time: datetime) -> None:
        """Set a start time for all instruments in this cluster."""
        self.__start_time = start_time


if __name__ == "__main__":
    mycluster: SaradCluster = SaradCluster()
    mycluster.update_connected_instruments()
    logger().debug(mycluster.__dict__)

    for connected_instrument in mycluster:
        print(connected_instrument)
        # print(f"Coordinator_reset: {connected_instrument.coordinator_reset()}")
        print(f"Get_first_channel: {connected_instrument.get_first_channel()}")
        # print(f"Get_next_channel: {connected_instrument.get_next_channel()}")
        # print(f"Close_channel: {connected_instrument.close_channel()}")

    # Example access on first device
    if len(mycluster.connected_instruments) > 0:
        inst = mycluster.connected_instruments[0]
