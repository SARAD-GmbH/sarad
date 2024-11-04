"""Module for the communication with instruments of the Radon Scout family."""

import socket
from datetime import datetime, timedelta, timezone
from time import sleep

from overrides import overrides  # type: ignore

from sarad.global_helpers import sarad_family
from sarad.instrument import Component, Measurand, Sensor
from sarad.logger import logger
from sarad.sari import SaradInst


class RscInst(SaradInst):
    """Instrument with Radon Scout communication protocol

    Inherited properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        device_id: Identifier for an individual instrument in a cluster
        type_id
        type_name
        software_version
        serial_number
        components: Dict of sensor or actor components
    Inherited methods from SaradInst:
        get_reply()
    Public methods:
        get_all_recent_values()
        get_recent_value(index)
        set_real_time_clock(datetime)
        stop_cycle()
        start_cycle()
    """

    @overrides
    def __init__(self, family=sarad_family(2)):
        super().__init__(family)
        self._last_sampling_time = None
        self.__alarm_level = None
        self.lock = None
        self.__wifi = {
            "ssid": None,
            "password": None,
            "ip_address": None,
            "server_port": None,
        }

    ## This method can be activated as soon as RTM 1688-2 and SRS support
    ## addressable SARAD protocol with RS-485
    # @overrides
    # def _new_rs485_address(self, raw_cmd):
    #     """Check whether raw_cmd changed the RS-485 bus address of the instrument.
    #     If this is the case, self._route will be changed.

    #     Args:
    #         raw_cmd (bytes): Command message to be analyzed.
    #     """
    #     message = self._rs485_filter(raw_cmd)
    #     checked_dict = self._check_message(message, multiframe=False)
    #     cmd = checked_dict["cmd"]
    #     data = checked_dict["data"]
    #     if cmd:
    #         logger().debug("cmd = %s", cmd)
    #         if cmd == b"\x09":  # C_SetParameter
    #             data_list = list(data)
    #             old_rs485_address = self._route.rs485_address
    #             _device_type = data_list[0]
    #             software_version = data_list[1]
    #             unicon_4 = data_list[10]
    #             if self._type_id in [14, 15, 16]:
    #                 rs485_address = unicon_4
    #             else:
    #                 rs485_address = software_version
    #             self._route.rs485_address = rs485_address
    #             logger().info(
    #                 "Change RS-485 bus address from %s into %s",
    #                 old_rs485_address,
    #                 self._route.rs485_address,
    #             )

    @overrides
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
                        logger().error(
                            "Exception in get_transparent_reply: %s", exception
                        )
            self._destroy_socket()
            return result
        logger().debug("Possible parameter sets: %s", self._serial_param_sets)
        for _i in range(len(self._serial_param_sets)):
            logger().debug(
                "Try to send %s with %s", raw_cmd, self._serial_param_sets[0]
            )
            result = self._try_baudrate(
                self._serial_param_sets[0], keep, timeout, raw_cmd
            )
            retry_counter = 1
            while not result and retry_counter and not self.route.zigbee_address:
                # Workaround for firmware bug in SARAD instruments.
                # This shall only be used, if the instrument is connected directly
                # to the COM port.
                logger().info("Play it again, Sam!")
                sleep(1)
                result = self._try_baudrate(
                    self._serial_param_sets[0], keep, timeout, raw_cmd
                )
                retry_counter = retry_counter - 1
            if result:
                logger().debug("Working with %s", self._serial_param_sets[0])
                return result
            self.release_instrument()
            self._serial_param_sets.rotate(-1)
            sleep(1)  # Give the instrument time to reset its input buffer.
        return result

    def _build_component_dict(self) -> int:
        logger().debug("Building component dict for Radon Scout instrument.")
        for _component_id, component_object in self.components.items():
            del component_object
        self.components = {}
        comp_list = self._get_parameter("components")
        if not comp_list:
            return 0
        for component in comp_list:
            component_object = Component(
                component["component_id"], component["component_name"]
            )
            # build sensor dict
            for sensor in component["sensors"]:
                sensor_object = Sensor(sensor["sensor_id"], sensor["sensor_name"])
                # build measurand dict
                for measurand in sensor["measurands"]:
                    try:
                        unit = measurand["measurand_unit"]
                    except Exception:  # pylint: disable=broad-except
                        unit = ""
                    try:
                        source = measurand["measurand_source"]
                    except Exception:  # pylint: disable=broad-except
                        source = None
                    measurand_obj = Measurand(
                        measurand["measurand_id"],
                        measurand["measurand_name"],
                        unit,
                        source,
                    )
                    sensor_object.measurands[measurand_obj.measurand_id] = measurand_obj
                component_object.sensors[sensor_object.sensor_id] = sensor_object
            self.components[component_object.component_id] = component_object
        return len(self.components)

    def _get_battery_voltage(self):
        battery_bytes = self._get_parameter("battery_bytes")
        battery_coeff = self._get_parameter("battery_coeff")
        ok_byte = self.family["ok_byte"]
        if not (battery_coeff and battery_bytes):
            return "This instrument type doesn't provide battery voltage information"

        reply = self.get_reply([b"\x0d", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            try:
                voltage = battery_coeff * int.from_bytes(
                    reply[1:], byteorder="little", signed=False
                )
                return round(voltage, 2)
            except TypeError:
                logger().error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger().error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger().error("LookupError when parsing the payload.")
                return False
            except Exception:  # pylint: disable=broad-except
                logger().error("Unknown error when parsing the payload.")
                raise
            else:
                pass
        else:
            logger().error("Device %s doesn't reply.", self.device_id)
            return False

    def _push_button(self):
        reply = self.get_reply([b"\x12", b""], timeout=self._ser_timeout)
        ok_byte = self.family["ok_byte"]
        if reply and (reply[0] == ok_byte):
            logger().debug("Push button simulated at device %s.", self.device_id)
            return True
        logger().error("Push button failed at device %s.", self.device_id)
        return False

    def get_all_recent_values(self):
        """Fill the component objects with recent readings."""
        logger().debug(
            "get_all_recent_values. Sample interval = %s. Last sampling time = %s",
            self._interval,
            self._last_sampling_time,
        )
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x14", b""], timeout=self._ser_timeout)
        self._last_sampling_time = datetime.utcnow()
        success = True
        if reply and (reply[0] == ok_byte):
            try:
                self._interval = timedelta(minutes=reply[1])
                device_time_min = reply[2]
                device_time_h = reply[3]
                device_time_d = reply[4]
                device_time_m = reply[5]
                device_time_y = reply[6]
                source = []  # measurand_source
                source.append(round(self._bytes_to_float(reply[7:11]), 2))  # 0
                source.append(reply[11])  # 1
                source.append(round(self._bytes_to_float(reply[12:16]), 2))  # 2
                source.append(reply[16])  # 3
                source.append(round(self._bytes_to_float(reply[17:21]), 2))  # 4
                source.append(round(self._bytes_to_float(reply[21:25]), 2))  # 5
                source.append(round(self._bytes_to_float(reply[25:29]), 2))  # 6
                source.append(
                    int.from_bytes(reply[29:33], byteorder="big", signed=False)
                )  # 7
                source.append(self._get_battery_voltage())  # 8
                device_time = datetime(
                    device_time_y + 2000,
                    device_time_m,
                    device_time_d,
                    device_time_h,
                    device_time_min,
                    tzinfo=timezone.utc,
                )
                self._fill_component_tree(source, device_time)
            except (TypeError, ReferenceError, LookupError, ValueError) as exception:
                logger().error("Error when parsing the payload: %s", exception)
                success = False
        else:
            logger().error("Device %s doesn't reply.", self.device_id)
            success = False
        return success

    def _fill_component_tree(self, source, device_time):
        for component_id, component in self.components.items():
            for _sensor_id, sensor in component.sensors.items():
                for _measurand_id, measurand in sensor.measurands.items():
                    try:
                        if component_id == 255:  # GPS
                            measurand.value = 0
                        else:
                            measurand.value = source[measurand.source]
                        if measurand.measurand_id == 0:  # momentary values
                            meas_datetime = datetime.now(timezone.utc)
                            measurand.interval = timedelta(seconds=0)
                        else:
                            meas_datetime = device_time
                            measurand.interval = self._interval
                        if self._utc_offset is None:
                            self._utc_offset = self._calc_utc_offset(
                                self._interval, device_time, datetime.now(timezone.utc)
                            )
                        if self._utc_offset is None:
                            measurand.time = meas_datetime.replace(
                                microsecond=0,
                            )
                        else:
                            measurand.time = meas_datetime.replace(
                                microsecond=0,
                                tzinfo=timezone(timedelta(hours=self._utc_offset)),
                            )
                    except Exception:  # pylint: disable=broad-except
                        logger().error(
                            "Can't get value for source %s in %s/%s/%s.",
                            measurand.source,
                            component.name,
                            sensor.name,
                            measurand.name,
                        )

    @overrides
    def get_recent_value(self, component_id=None, sensor_id=None, measurand_id=None):
        super().get_recent_value(component_id, sensor_id, measurand_id)
        if self._last_sampling_time is None:
            logger().warning("The gathered values might be invalid.")
            if not self.get_all_recent_values():
                return {}
        else:
            in_recent_interval = bool(
                measurand_id == 0
                and (
                    (datetime.utcnow() - self._last_sampling_time)
                    < timedelta(seconds=5)
                )
            )
            in_main_interval = bool(
                measurand_id != 0
                and ((datetime.utcnow() - self._last_sampling_time) < self._interval)
            )
            if in_main_interval:
                logger().debug(
                    "We do not have new values yet. Sample interval = %s. Last sampling time = %s",
                    self._interval,
                    self._last_sampling_time,
                )
            elif in_recent_interval:
                logger().debug(
                    "We don't request recent values faster than every %s.",
                    timedelta(seconds=5),
                )
            else:
                if not self.get_all_recent_values():
                    return {}
        component = self.components.get(component_id)
        if component is not None:
            sensor = component.sensors.get(sensor_id)
            if sensor is not None:
                measurand = sensor.measurands.get(measurand_id)
                if measurand is not None:
                    return {
                        "component_name": component.name,
                        "sensor_name": sensor.name,
                        "measurand_name": measurand.name,
                        "measurand_operator": measurand.operator,
                        "measurand": f"{measurand.operator} {measurand.value} {measurand.unit}",
                        "value": measurand.value,
                        "measurand_unit": measurand.unit,
                        "datetime": measurand.time,
                        "sample_interval": measurand.interval,
                        "gps": self._gps,
                    }
        return {}

    @overrides
    def set_real_time_clock(self, date_time) -> bool:
        ok_byte = self.family["ok_byte"]
        instr_datetime = bytearray(
            [
                date_time.second,
                date_time.minute,
                date_time.hour,
                date_time.day,
                date_time.month,
                date_time.year - 2000,
            ]
        )
        reply = self.get_reply([b"\x05", instr_datetime], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Time on device %s set.", self.device_id)
            return True
        logger().error("Setting the time on device %s failed.", self.device_id)
        return False

    @overrides
    def stop_cycle(self):
        """Stop a measurement cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x15", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    @overrides
    def start_cycle(self, cycle):
        """Start a measurement cycle.

        Args:
            cycle (int): interval length in seconds.
        """
        self._get_config()  # to set self._interval
        self._interval = timedelta(seconds=cycle)
        self._set_config()
        for _component_id, component in self.components.items():
            for _sensor_id, sensor in component.sensors.items():
                sensor.interval = self._interval
        success = True
        for instr_type in self.family["types"]:
            if instr_type["type_id"] == self.type_id:
                if "stop_cycle" in instr_type.get("allowed_methods", []):
                    success = self.stop_cycle() and self._push_button()
                break
        return success

    def _get_config(self):
        """Get configuration from device."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x10", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Getting config. from device %s.", self.device_id)
            try:
                self._interval = timedelta(minutes=reply[1])
                setup_word = reply[2:3]
                self._decode_setup_word(setup_word)
                self.__alarm_level = int.from_bytes(
                    reply[4:8], byteorder="little", signed=False
                )
            except TypeError:
                logger().error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger().error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger().error("LookupError when parsing the payload.")
                return False
            except Exception:  # pylint: disable=broad-except
                logger().debug(
                    "The connected instrument does not belong to the RadonScout family."
                )
                self._valid_family = False
                return False
            return True
        logger().error("Get config. failed at device %s.", self.device_id)
        return False

    def _set_config(self):
        """Upload a new configuration to the device."""
        ok_byte = self.family["ok_byte"]
        setup_word = self._encode_setup_word()
        interval = int(self._interval.seconds / 60)
        setup_data = (
            (interval).to_bytes(1, byteorder="little")
            + setup_word
            + (self.__alarm_level).to_bytes(4, byteorder="little")
        )
        logger().debug(setup_data)
        reply = self.get_reply([b"\x0f", setup_data], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Set config. successful at device %s.", self.device_id)
            return True
        logger().error("Set config. failed at device %s.", self.device_id)
        return False

    def set_lock(self):
        """Lock the hardware button or switch at the device."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x01", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            self.lock = self.Lock.LOCKED
            logger().debug("Device %s locked.", self.device_id)
            return True
        logger().error("Locking failed at device %s.", self.device_id)
        return False

    def set_unlock(self):
        """Unlock the hardware button or switch at the device."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x02", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            self.lock = self.Lock.UNLOCKED
            logger().debug("Device %s unlocked.", self.device_id)
            return True
        logger().error("Unlocking failed at device %s.", self.device_id)
        return False

    def set_long_interval(self):
        """Set the measuring interval to 3 h = 180 min = 10800 s"""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x03", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            self._interval = timedelta(hours=3)
            logger().debug("Device %s set to 3 h interval.", self.device_id)
            return True
        logger().error("Interval setup failed at device %s.", self.device_id)
        return False

    def set_short_interval(self):
        """Set the measuring interval to 1 h = 60 min = 3600 s"""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x04", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            self._interval = timedelta(hours=1)
            logger().debug("Device %s set to 1 h interval.", self.device_id)
            return True
        logger().error("Interval setup failed at device %s.", self.device_id)
        return False

    def get_wifi_access(self):
        """Get the Wi-Fi access data from instrument."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x18", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            try:
                logger().debug(reply)
                self.__wifi["ssid"] = reply[0:33].rstrip(b"0")
                self.__wifi["password"] = reply[33:97].rstrip(b"0")
                self.__wifi["ip_address"] = reply[97:121].rstrip(b"0")
                self.__wifi["server_port"] = int.from_bytes(reply[121:123], "big")
                return True
            except (TypeError, ReferenceError, LookupError) as exception:
                logger().error("Error when parsing the payload: %s", exception)
                return False
        else:
            logger().error(
                "Cannot get Wi-Fi access data from device %s.", self.device_id
            )
            return False

    def set_wifi_access(self, ssid, password, ip_address, server_port):
        """Set the WiFi access data."""
        ok_byte = self.family["ok_byte"]
        access_data = b"".join(
            [
                bytes(ssid, "utf-8").ljust(33, b"0"),
                bytes(password, "utf-8").ljust(64, b"0"),
                bytes(ip_address, "utf-8").ljust(24, b"0"),
                server_port.to_bytes(2, "big"),
            ]
        )
        logger().debug(access_data)
        reply = self.get_reply([b"\x17", access_data], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("WiFi access data on device %s set.", self.device_id)
            return True
        logger().error("Setting WiFi access data on device %s failed.", self.device_id)
        return False
