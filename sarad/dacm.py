"""Module for the communication with instruments of the DACM family."""

import logging
import re
from datetime import datetime, timedelta

from BitVector import BitVector  # type: ignore

from sarad.sari import Component, Measurand, SaradInst, Sensor

_LOGGER = None


def logger():
    """Returns the logger instance used in this module."""
    global _LOGGER
    _LOGGER = _LOGGER or logging.getLogger(__name__)
    return _LOGGER


class DacmInst(SaradInst):
    """Instrument with DACM communication protocol

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
        set_real_time_clock()
        stop_cycle()
        start_cycle()
        get_all_recent_values()
        get_recent_value(index)"""

    version = "0.1"

    def __init__(self, port=None, family=None):
        if family is None:
            family = SaradInst.products[2]
        SaradInst.__init__(self, port, family)
        self._date_of_manufacture = None
        self._date_of_update = None
        self._module_blocksize = None
        self._component_blocksize = None
        self._component_count = None
        self._bit_ctrl = None
        self._value_ctrl = None
        self._cycle_blocksize = None
        self._cycle_count_limit = None
        self._step_count_limit = None
        self._language = None
        self._address = None
        self._date_of_config = None
        self._module_name = None
        self._config_name = None

    def __str__(self):
        output = (
            f"Id: {self.device_id}\n"
            f"SerialDevice: {self.port}\n"
            f"Baudrate: {self.family['baudrate']}\n"
            f"FamilyName: {self.family['family_name']}\n"
            f"FamilyId: {self.family['family_id']}\n"
            f"TypName: {self.type_name}\n"
            f"TypeId: {self.type_id}\n"
            f"SoftwareVersion: {self.software_version}\n"
            f"LastUpdate: {self.date_of_update}\n"
            f"SerialNumber: {self.serial_number}\n"
            f"DateOfManufacture: {self.date_of_manufacture}\n"
            f"Address: {self.address}\n"
            f"LastConfig: {self.date_of_config}\n"
            f"ModuleName: {self.module_name}\n"
            f"ConfigName: {self.config_name}\n"
        )
        return output

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

    def _get_description(self):
        """Get descriptive data about DACM instrument."""
        ok_byte = self.family["ok_byte"]
        id_cmd = self.family["get_id_cmd"]
        length_of_reply = self.family["length_of_reply"]
        reply = self.get_reply(id_cmd, length_of_reply)
        if reply and (reply[0] == ok_byte):
            logger().debug("Get description successful.")
            try:
                self._type_id = reply[1]
                self._software_version = reply[2]
                self._serial_number = int.from_bytes(
                    reply[3:5], byteorder="big", signed=False
                )
                manu_day = reply[5]
                manu_month = reply[6]
                manu_year = int.from_bytes(reply[7:9], byteorder="big", signed=False)
                self._date_of_manufacture = datetime(manu_year, manu_month, manu_day)
                upd_day = reply[9]
                upd_month = reply[10]
                upd_year = int.from_bytes(reply[11:13], byteorder="big", signed=False)
                self._date_of_update = datetime(upd_year, upd_month, upd_day)
                self._module_blocksize = reply[13]
                self._component_blocksize = reply[14]
                self._component_count = reply[15]
                self._bit_ctrl = BitVector(rawbytes=reply[16:20])
                self._value_ctrl = BitVector(rawbytes=reply[20:24])
                self._cycle_blocksize = reply[24]
                self._cycle_count_limit = reply[25]
                self._step_count_limit = reply[26]
                self._language = reply[27]
                return True and self._get_module_information()
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
                self._valid_family = False
                return False
        logger().debug("Get description failed.")
        return False

    def _get_module_information(self):
        """Get descriptive data about DACM instrument."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x01", b""], 73)
        if reply and (reply[0] == ok_byte):
            logger().debug("Get module information successful.")
            try:
                self._address = reply[1]
                config_day = reply[2]
                config_month = reply[3]
                config_year = int.from_bytes(reply[4:6], byteorder="big", signed=False)
                self._date_of_config = datetime(config_year, config_month, config_day)
                self._module_name = reply[6:39].split(b"\x00")[0].decode("ascii")
                self._config_name = reply[39:].split(b"\x00")[0].decode("ascii")
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
        logger().debug("Get module information failed.")
        return False

    def _get_component_information(self, component_index):
        """Get information about one component of a DACM instrument."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x03", bytes([component_index])], 21)
        if reply and (reply[0] == ok_byte):
            logger().debug("Get component information successful.")
            try:
                revision = reply[1]
                component_type = reply[2]
                availability = reply[3]
                ctrl_format = reply[4]
                conf_block_size = reply[5]
                data_record_size = int.from_bytes(
                    reply[6:8], byteorder="big", signed=False
                )
                name = reply[8:16].split(b"\x00")[0].decode("ascii")
                hw_capability = BitVector(rawbytes=reply[16:20])
                return {
                    "revision": revision,
                    "component_type": component_type,
                    "availability": availability,
                    "ctrl_format": ctrl_format,
                    "conf_block_size": conf_block_size,
                    "data_record_size": data_record_size,
                    "name": name,
                    "hw_capability": hw_capability,
                }
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
        logger().debug("Get component information failed.")
        return False

    def _get_component_configuration(self, component_index):
        """Get information about the configuration of a component
        of a DACM instrument."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x04", bytes([component_index])], 73)
        if reply and (reply[0] == ok_byte):
            logger().debug("Get component configuration successful.")
            try:
                sensor_name = reply[8:16].split(b"\x00")[0].decode("ascii")
                sensor_value = reply[8:16].split(b"\x00")[0].decode("ascii")
                sensor_unit = reply[8:16].split(b"\x00")[0].decode("ascii")
                input_config = int.from_bytes(reply[6:8], byteorder="big", signed=False)
                alert_level_lo = int.from_bytes(
                    reply[6:8], byteorder="big", signed=False
                )
                alert_level_hi = int.from_bytes(
                    reply[6:8], byteorder="big", signed=False
                )
                alert_output_lo = int.from_bytes(
                    reply[6:8], byteorder="big", signed=False
                )
                alert_output_hi = int.from_bytes(
                    reply[6:8], byteorder="big", signed=False
                )
                return {
                    "sensor_name": sensor_name,
                    "sensor_value": sensor_value,
                    "sensor_unit": sensor_unit,
                    "input_config": input_config,
                    "alert_level_lo": alert_level_lo,
                    "alert_level_hi": alert_level_hi,
                    "alert_output_lo": alert_output_lo,
                    "alert_output_hi": alert_output_hi,
                }
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
        logger().debug("Get component configuration failed.")
        return False

    def _read_cycle_start(self, cycle_index=0):
        """Get description of a measuring cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x06", bytes([cycle_index])], 28)
        if reply and (reply[0] == ok_byte) and reply[1]:
            logger().debug("Get primary cycle information successful.")
            try:
                cycle_name = reply[2:19].split(b"\x00")[0].decode("ascii")
                cycle_interval = timedelta(
                    seconds=int.from_bytes(
                        reply[19:21], byteorder="little", signed=False
                    )
                )
                cycle_steps = int.from_bytes(
                    reply[21:24], byteorder="big", signed=False
                )
                cycle_repetitions = int.from_bytes(
                    reply[24:28], byteorder="little", signed=False
                )
                return {
                    "cycle_name": cycle_name,
                    "cycle_interval": cycle_interval,
                    "cycle_steps": cycle_steps,
                    "cycle_repetitions": cycle_repetitions,
                }
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
        logger().debug("Get primary cycle info failed.")
        return False

    def _read_cycle_continue(self):
        """Get description of subsequent cycle intervals."""
        reply = self.get_reply([b"\x07", b""], 16)
        if reply and not len(reply) < 16:
            logger().debug("Get information about cycle interval successful.")
            try:
                seconds = int.from_bytes(reply[0:4], byteorder="little", signed=False)
                bit_ctrl = BitVector(rawbytes=reply[4:8])
                value_ctrl = BitVector(rawbytes=reply[8:12])
                rest = BitVector(rawbytes=reply[12:16])
                return {
                    "seconds": seconds,
                    "bit_ctrl": bit_ctrl,
                    "value_ctrl": value_ctrl,
                    "rest": rest,
                }
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
        logger().debug("Get info about cycle interval failed.")
        return False

    def set_real_time_clock(self, date_time):
        """Set the instrument time."""
        ok_byte = self.family["ok_byte"]
        instr_datetime = bytearray(
            [
                date_time.second,
                date_time.minute,
                date_time.hour,
                date_time.day,
                date_time.month,
            ]
        )
        instr_datetime.extend((date_time.year).to_bytes(2, byteorder="big"))
        reply = self.get_reply([b"\x10", instr_datetime], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Time on device %s set to UTC.", self.device_id)
            return True
        logger().error("Setting the time on device %s failed.", self.device_id)
        return False

    def stop_cycle(self):
        """Stop the measuring cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x16", b""], 1)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    def start_cycle(self, cycle_index=0):
        """Start a measuring cycle."""
        self.__interval = self._read_cycle_start(cycle_index)["cycle_interval"]
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self.__interval
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x15", bytes([cycle_index])], 3, timeout=5)
        if reply and (reply[0] == ok_byte):
            logger().debug(
                "Cycle %s started at device %s.", cycle_index, self.device_id
            )
            return True
        logger().error("start_cycle() failed at device %s.", self.device_id)
        if reply[0] == 11:
            logger().error("DACM instrument replied with error code %s.", reply[1])
        return False

    @staticmethod
    def set_lock():
        """Lock the hardware button or switch at the device.
        This is a dummy since this locking function does not exist
        on DACM instruments."""
        return True

    def get_all_recent_values(self):
        """Get a list of dictionaries with recent measuring values."""
        list_of_outputs = []
        sensor_id = 0  # fixed value, reserved for future use
        for component_id in range(34):
            for measurand_id in range(4):
                output = self.get_recent_value(component_id, sensor_id, measurand_id)
                list_of_outputs.append(output)
        return list_of_outputs

    def get_recent_value(self, component, sensor=0, measurand=0):
        """Get a dictionaries with recent measuring values from one sensor.
        component_id: one of the 34 sensor/actor modules of the DACM system
        measurand_id:
        0 = recent sampling,
        1 = average of last completed interval,
        2 = minimum of last completed interval,
        3 = maximum
        sensor_id: only for sensors delivering multiple measurands"""
        component_id = self.components[component].id
        sensor_id = self.components[component].sensors[sensor].id
        measurand_id = (
            self.components[component].sensors[sensor].measurands[measurand].id
        )
        reply = self.get_reply(
            [
                b"\x1a",
                bytes([component_id]) + bytes([sensor_id]) + bytes([measurand_id]),
            ],
            1000,
        )
        if reply and (reply[0] > 0):
            output = {}
            output["component_name"] = reply[1:17].split(b"\x00")[0].decode("ascii")
            output["measurand_id"] = measurand_id
            output["sensor_name"] = reply[18:34].split(b"\x00")[0].decode("ascii")
            output["measurand"] = reply[35:51].split(b"\x00")[0].strip().decode("ascii")
            measurand_dict = self._parse_value_string(output["measurand"])
            output["measurand_operator"] = measurand_dict["measurand_operator"]
            output["value"] = measurand_dict["measurand_value"]
            output["measurand_unit"] = measurand_dict["measurand_unit"]
            date = reply[52:68].split(b"\x00")[0].split(b"/")
            meas_time = reply[69:85].split(b"\x00")[0].split(b":")
            if date != [b""]:
                output["datetime"] = datetime(
                    int(date[2]),
                    int(date[0]),
                    int(date[1]),
                    int(meas_time[0]),
                    int(meas_time[1]),
                    int(meas_time[2]),
                )
            else:
                output["datetime"] = None
            try:
                gps_list = re.split("[ ]+ |ø|M[ ]*", reply[86:].decode("latin_1"))
                gps_dict = {
                    "valid": True,
                    "latitude": float(gps_list[0])
                    if gps_list[1] == "N"
                    else -float(gps_list[0]),
                    "longitude": float(gps_list[2])
                    if gps_list[3] == "E"
                    else -float(gps_list[2]),
                    "altitude": float(gps_list[4]),
                    "deviation": float(gps_list[5]),
                }
                output["gps"] = gps_dict
            except Exception:
                gps_dict = {
                    "valid": False,
                    "latitude": None,
                    "longitude": None,
                    "altitude": None,
                    "deviation": None,
                }
            this_measurand = (
                self.components[component].sensors[sensor].measurands[measurand]
            )
            this_measurand.operator = measurand_dict["measurand_operator"]
            this_measurand.value = measurand_dict["measurand_value"]
            this_measurand.unit = measurand_dict["measurand_unit"]
            this_measurand.time = output["datetime"]
            this_measurand.gps = gps_dict
            return output
        if reply[0] == 0:
            logger().error("Measurand not available.")
            return False
        logger().error("The instrument doesn't reply.")
        return False

    def get_address(self):
        """Return the address of the DACM module."""
        return self._address

    def set_address(self, address):
        """Set the address of the DACM module."""
        self._address = address
        if (self.port is not None) and (self.address is not None):
            self._initialize()

    def get_date_of_config(self):
        """Return the date the configuration was made on."""
        return self._date_of_config

    def set_date_of_config(self, date_of_config):
        """Set the date of the configuration."""
        self._date_of_config = date_of_config
        if (self.port is not None) and (self.date_of_config is not None):
            self._initialize()

    def get_module_name(self):
        """Return the name of the DACM module."""
        return self._module_name

    def set_module_name(self, module_name):
        """Set the name of the DACM module."""
        self._module_name = module_name
        if (self.port is not None) and (self.module_name is not None):
            self._initialize()

    def get_config_name(self):
        """Return the name of the configuration."""
        return self._config_name

    def set_config_name(self, config_name):
        """Set the name of the configuration."""
        self._config_name = config_name
        if (self.port is not None) and (self.config_name is not None):
            self._initialize()

    def get_date_of_manufacture(self):
        """Return the date of manufacture."""
        return self._date_of_manufacture

    def get_date_of_update(self):
        """Return the date of firmware update."""
        return self._date_of_update

    module_name = property(get_module_name, set_module_name)
    address = property(get_address, set_address)
    date_of_config = property(get_date_of_config, set_date_of_config)
    config_name = property(get_config_name, set_config_name)
    date_of_manufacture = property(get_date_of_manufacture)
    date_of_update = property(get_date_of_update)
