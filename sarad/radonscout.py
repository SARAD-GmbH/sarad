"""Module for the communication with instruments of the Radon Scout family."""

from datetime import datetime, timedelta

from overrides import overrides  # type: ignore

from sarad.sari import Component, Measurand, SaradInst, Sensor, logger


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
        components: List of sensor or actor components
    Inherited methods from SaradInst:
        get_reply()
    Public methods:
        get_all_recent_values()
        get_recent_value(index)
        set_real_time_clock(datetime)
        stop_cycle()
        start_cycle()
        get_config()
        set_config()"""

    version = "0.3"

    ALLOWED_CMDS = [
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x06,
        0x07,
        0x08,
        0x09,
        0x0A,
        0x0B,
        0x0C,
        0x0D,
        0x0E,
        0x0F,
        0x10,  # GetSetup
        0x11,
        0x12,
        0x13,
        0x14,
        0x15,
        0x16,
        0x17,
        0x18,
        0x19,
        0x1A,
        0x1B,
        0x1C,
    ]

    @overrides
    def __init__(self, family=SaradInst.products[1]):
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
        self.__interval = None

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
        if cmd_dict["cmd"] == b"\x09":  # C_SetParameter
            data_list = list(cmd_dict["data"])
            old_rs485_address = self._route.rs485_address
            _device_type = data_list[0]
            software_version = data_list[1]
            unicon_4 = data_list[10]
            if self._type_id in [14, 15, 16]:
                rs485_address = unicon_4
            elif self._type_id in [4, 10]:
                rs485_address = software_version
            # TODO uncomment the following line as soon as addressable RS-485
            # with SARAD protocol is supported by Smart Radon Sensor and RTM-1688
            # self._route.rs485_address = rs485_address
            logger().info(
                "Change RS-485 bus address from %d into %d",
                old_rs485_address,
                self._route.rs485_address,
            )

    def _gather_all_recent_values(self):
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x14", b""], 33)
        self._last_sampling_time = datetime.utcnow()
        if reply and (reply[0] == ok_byte):
            try:
                sample_interval = timedelta(minutes=reply[1])
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
            except ValueError:
                logger().error("ValueError when parsing the payload.")
                return False
            except Exception:  # pylint: disable=broad-except
                logger().error("Unknown error when parsing the payload.")
                return False
            self.__interval = sample_interval
            for component in self.components:
                for sensor in component.sensors:
                    sensor.interval = sample_interval
                    for measurand in sensor.measurands:
                        try:
                            measurand.value = source[measurand.source]
                            measurand.time = device_time
                            if measurand.source == 8:  # battery voltage
                                sensor.interval = timedelta(seconds=5)
                        except Exception:  # pylint: disable=broad-except
                            logger().error(
                                "Can't get value for source %s in %s/%s/%s.",
                                measurand.source,
                                component.name,
                                sensor.name,
                                measurand.name,
                            )
            return True
        logger().error("Device %s doesn't reply.", self.device_id)
        return False

    def _build_component_list(self) -> int:
        logger().debug("Building component list for Radon Scout instrument.")
        for component_object in self.components:
            del component_object
        self.components = []
        component_dict = self._get_parameter("components")
        if not component_dict:
            return 0
        for component in component_dict:
            component_object = Component(
                component["component_id"], component["component_name"]
            )
            # build sensor list
            for sensor in component["sensors"]:
                sensor_object = Sensor(sensor["sensor_id"], sensor["sensor_name"])
                # build measurand list
                for measurand in sensor["measurands"]:
                    try:
                        unit = measurand["measurand_unit"]
                    except Exception:  # pylint: disable=broad-except
                        unit = ""
                    try:
                        source = measurand["measurand_source"]
                    except Exception:  # pylint: disable=broad-except
                        source = None
                    measurand_object = Measurand(
                        measurand["measurand_id"],
                        measurand["measurand_name"],
                        unit,
                        source,
                    )
                    sensor_object.measurands += [measurand_object]
                component_object.sensors += [sensor_object]
            self.components += [component_object]
        return len(self.components)

    def _get_battery_voltage(self):
        battery_bytes = self._get_parameter("battery_bytes")
        battery_coeff = self._get_parameter("battery_coeff")
        ok_byte = self.family["ok_byte"]
        if not (battery_coeff and battery_bytes):
            return "This instrument type doesn't provide \
            battery voltage information"

        reply = self.get_reply([b"\x0d", b""], battery_bytes + 1)
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
        reply = self.get_reply([b"\x12", b""], 1)
        ok_byte = self.family["ok_byte"]
        if reply and (reply[0] == ok_byte):
            logger().debug("Push button simulated at device %s.", self.device_id)
            return True
        logger().error("Push button failed at device %s.", self.device_id)
        return False

    def get_all_recent_values(self):
        """Fill the component objects with recent readings."""
        # Do nothing as long as the previous values are valid.
        if self._last_sampling_time is None:
            logger().warning(
                "The gathered values might be invalid. "
                "You should use function start_cycle() in your application "
                "for a regular initialization of the measuring cycle."
            )
            return self._gather_all_recent_values()
        if (datetime.utcnow() - self._last_sampling_time) < self.__interval:
            logger().debug(
                "We do not have new values yet. Sample interval = %s.", self.__interval
            )
            return True
        return self._gather_all_recent_values()

    def get_recent_value(self, component_id=None, sensor_id=None, measurand_id=None):
        """Fill component objects with recent measuring values.\
        This function does the same like get_all_recent_values()\
        and is only here to provide a compatible API to the DACM interface"""
        self.get_all_recent_values()
        component = self.components[component_id]
        sensor = component.sensors[sensor_id]
        measurand = sensor.measurands[measurand_id]
        return {
            "component_name": component.name,
            "sensor_name": sensor.name,
            "measurand_name": measurand.name,
            "measurand_operator": measurand.operator,
            "measurand": f"{measurand.operator} {measurand.value} {measurand.unit}",
            "value": measurand.value,
            "measurand_unit": measurand.unit,
            "datetime": measurand.time,
            "gps": {
                "valid": False,
                "latitude": None,
                "longitude": None,
                "altitude": None,
                "deviation": None,
            },
        }

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
        reply = self.get_reply([b"\x05", instr_datetime], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Time on device %s set to UTC.", self.device_id)
            return True
        logger().error("Setting the time on device %s failed.", {self.device_id})
        return False

    @overrides
    def stop_cycle(self):
        """Stop a measurement cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x15", b""], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    @overrides
    def start_cycle(self, cycle_index):
        """Start a measurement cycle."""
        self.get_config()  # to set self.__interval
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self.__interval
        success = self.stop_cycle() and self._push_button()
        if success:
            self._last_sampling_time = datetime.utcnow()
        return success

    def get_config(self):
        """Get configuration from device."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x10", b""], 8)
        if reply and (reply[0] == ok_byte):
            logger().debug("Getting config. from device %s.", self.device_id)
            try:
                self.__interval = timedelta(minutes=reply[1])
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

    def set_config(self):
        """Upload a new configuration to the device."""
        ok_byte = self.family["ok_byte"]
        setup_word = self._encode_setup_word()
        interval = int(self.__interval.seconds / 60)
        setup_data = (
            (interval).to_bytes(1, byteorder="little")
            + setup_word
            + (self.__alarm_level).to_bytes(4, byteorder="little")
        )
        logger().debug(setup_data)
        reply = self.get_reply([b"\x0f", setup_data], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Set config. successful at device %s.", self.device_id)
            return True
        logger().error("Set config. failed at device %s.", self.device_id)
        return False

    def set_lock(self):
        """Lock the hardware button or switch at the device."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x01", b""], 1)
        if reply and (reply[0] == ok_byte):
            self.lock = self.Lock.LOCKED
            logger().debug("Device %s locked.", self.device_id)
            return True
        logger().error("Locking failed at device %s.", self.device_id)
        return False

    def set_unlock(self):
        """Unlock the hardware button or switch at the device."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x02", b""], 1)
        if reply and (reply[0] == ok_byte):
            self.lock = self.Lock.UNLOCKED
            logger().debug("Device %s unlocked.", self.device_id)
            return True
        logger().error("Unlocking failed at device %s.", self.device_id)
        return False

    def set_long_interval(self):
        """Set the measuring interval to 3 h = 180 min = 10800 s"""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x03", b""], 1)
        if reply and (reply[0] == ok_byte):
            self.__interval = timedelta(hours=3)
            logger().debug("Device %s set to 3 h interval.", self.device_id)
            return True
        logger().error("Interval setup failed at device %s.", self.device_id)
        return False

    def set_short_interval(self):
        """Set the measuring interval to 1 h = 60 min = 3600 s"""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x04", b""], 1)
        if reply and (reply[0] == ok_byte):
            self.__interval = timedelta(hours=1)
            logger().debug("Device %s set to 1 h interval.", self.device_id)
            return True
        logger().error("Interval setup failed at device %s.", self.device_id)
        return False

    def get_wifi_access(self):
        """Get the Wi-Fi access data from instrument."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x18", b""], 125)
        if reply and (reply[0] == ok_byte):
            try:
                logger().debug(reply)
                self.__wifi["ssid"] = reply[0:33].rstrip(b"0")
                self.__wifi["password"] = reply[33:97].rstrip(b"0")
                self.__wifi["ip_address"] = reply[97:121].rstrip(b"0")
                self.__wifi["server_port"] = int.from_bytes(reply[121:123], "big")
                return True
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
                return False
            else:
                pass
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
        reply = self.get_reply([b"\x17", access_data], 118)
        if reply and (reply[0] == ok_byte):
            logger().debug("WiFi access data on device %s set.", self.device_id)
            return True
        logger().error("Setting WiFi access data on device %s failed.", self.device_id)
        return False
