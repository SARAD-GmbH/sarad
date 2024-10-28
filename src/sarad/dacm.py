"""Module for the communication with instruments of the DACM family."""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from BitVector import BitVector  # type: ignore
from overrides import overrides  # type: ignore

from sarad.global_helpers import sarad_family
from sarad.instrument import Component, Gps, Measurand, Sensor
from sarad.logger import logger
from sarad.sari import SaradInst


class DacmInst(SaradInst):
    # pylint: disable=too-many-instance-attributes
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

    @overrides
    def __init__(self, family=sarad_family(5)):
        super().__init__(family)
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
        self._date_of_config = None
        self._module_name = None
        self._config_name = None
        self._byte_order: Literal["little", "big"] = "big"
        self._cycle = 0

    def __str__(self):
        output = super().__str__() + (
            f"LastUpdate: {self.date_of_update}\n"
            f"DateOfManufacture: {self.date_of_manufacture}\n"
            f"Address: {self.address}\n"
            f"LastConfig: {self.date_of_config}\n"
            f"ModuleName: {self.module_name}\n"
            f"ConfigName: {self.config_name}\n"
        )
        return output

    def _build_component_dict(self) -> int:
        logger().debug("Building component dict for DACM instrument.")
        for _component_id, component_object in self.components.items():
            del component_object
        self.components = {}
        for component_id in range(34):
            component_object = Component(component_id)
            # build sensor dict
            for sensor_id in range(5):
                sensor_object = Sensor(sensor_id)
                # build measurand dict
                for measurand_id in range(4):
                    measurand_object = Measurand(measurand_id)
                    sensor_object.measurands[measurand_id] = measurand_object
                component_object.sensors[sensor_id] = sensor_object
            self.components[component_object.component_id] = component_object
        component_object = Component(255, "position")
        sensor_object = Sensor(0, "gps")
        measurand_object = Measurand(0, "recent")
        sensor_object.measurands[0] = measurand_object
        component_object.sensors[0] = sensor_object
        self.components[component_object.component_id] = component_object
        return len(self.components)

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
    def get_description(self) -> bool:
        """Get descriptive data about DACM instrument."""
        ok_byte = self.family["ok_byte"]
        id_cmd = self.family["get_id_cmd"]
        reply = self.get_reply(id_cmd, timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Get description successful.")
            try:
                if reply[29]:
                    self._byte_order = "little"
                    logger().debug("DACM-32 with Little-Endian")
                else:
                    self._byte_order = "big"
                    logger().debug("DACM-8 with Big-Endian")
                self._type_id = reply[1]
                self._software_version = reply[2]
                self._serial_number = int.from_bytes(
                    reply[3:5], byteorder=self._byte_order, signed=False
                )
                manu_day = reply[5]
                manu_month = reply[6]
                manu_year = int.from_bytes(
                    reply[7:9], byteorder=self._byte_order, signed=False
                )
                if manu_year == 65535:
                    raise ValueError("Manufacturing year corrupted.")
                self._date_of_manufacture = self._sanitize_date(
                    manu_year, manu_month, manu_day
                )
                upd_day = reply[9]
                upd_month = reply[10]
                upd_year = int.from_bytes(
                    reply[11:13], byteorder=self._byte_order, signed=False
                )
                if upd_year == 65535:
                    raise ValueError("Last Update year corrupted.")
                self._date_of_update = self._sanitize_date(upd_year, upd_month, upd_day)
                self._module_blocksize = reply[13]
                self._component_blocksize = reply[14]
                self._component_count = reply[15]
                self._bit_ctrl = BitVector(rawbytes=reply[16:20])
                self._value_ctrl = BitVector(rawbytes=reply[20:24])
                self._cycle_blocksize = reply[24]
                self._cycle_count_limit = reply[25]
                self._step_count_limit = reply[26]
                self._language = reply[27]
                logger().debug(
                    "type_id: %d, sw_ver: %d, sn: %d, manu: %s, update: %s",
                    self._type_id,
                    self._software_version,
                    self._serial_number,
                    self._date_of_manufacture,
                    self._date_of_update,
                )
                return True and self._get_module_information()
            except Exception as exception:  # pylint: disable=broad-except
                logger().debug(
                    "Instrument doesn't belong to DACM family or %s",
                    exception,
                )
                self._valid_family = False
                return False
        return False

    def _get_module_information(self):
        """Get descriptive data about DACM instrument."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x01", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Get module information successful.")
            try:
                self._route.rs485_address = reply[1]
                config_day = reply[2]
                config_month = reply[3]
                config_year = int.from_bytes(
                    reply[4:6], byteorder=self._byte_order, signed=False
                )
                self._date_of_config = self._sanitize_date(
                    config_year, config_month, config_day
                )
                self._module_name = reply[6:39].split(b"\x00")[0].decode("cp1252")
                self._config_name = reply[39:].split(b"\x00")[0].decode("cp1252")
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
        reply = self.get_reply(
            [b"\x03", bytes([component_index])], timeout=self._ser_timeout
        )
        if reply and (reply[0] == ok_byte):
            logger().debug("Get component information successful.")
            try:
                revision = reply[1]
                component_type = reply[2]
                availability = reply[3]
                ctrl_format = reply[4]
                conf_block_size = reply[5]
                data_record_size = int.from_bytes(
                    reply[6:8], byteorder=self._byte_order, signed=False
                )
                name = reply[8:16].split(b"\x00")[0].decode("cp1252")
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
        reply = self.get_reply(
            [b"\x04", bytes([component_index])], timeout=self._ser_timeout
        )
        if reply and (reply[0] == ok_byte):
            logger().debug("Get component configuration successful.")
            try:
                sensor_name = reply[8:16].split(b"\x00")[0].decode("cp1252")
                sensor_value = reply[8:16].split(b"\x00")[0].decode("cp1252")
                sensor_unit = reply[8:16].split(b"\x00")[0].decode("cp1252")
                input_config = int.from_bytes(
                    reply[6:8], byteorder=self._byte_order, signed=False
                )
                alert_level_lo = int.from_bytes(
                    reply[6:8], byteorder=self._byte_order, signed=False
                )
                alert_level_hi = int.from_bytes(
                    reply[6:8], byteorder=self._byte_order, signed=False
                )
                alert_output_lo = int.from_bytes(
                    reply[6:8], byteorder=self._byte_order, signed=False
                )
                alert_output_hi = int.from_bytes(
                    reply[6:8], byteorder=self._byte_order, signed=False
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
        reply = self.get_reply(
            [b"\x06", bytes([cycle_index])], timeout=self._ser_timeout
        )
        if reply and (reply[0] == ok_byte) and reply[1]:
            logger().debug("Get primary cycle information successful.")
            try:
                cycle_name = reply[2:19].split(b"\x00")[0].decode("cp1252")
                cycle_interval = timedelta(
                    seconds=int.from_bytes(
                        reply[19:21], byteorder="little", signed=False
                    )
                )
                cycle_steps = int.from_bytes(
                    reply[21:24], byteorder=self._byte_order, signed=False
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
        reply = self.get_reply([b"\x07", b""], timeout=self._ser_timeout)
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

    @overrides
    def set_real_time_clock(self, date_time) -> bool:
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
        instr_datetime.extend((date_time.year).to_bytes(2, byteorder=self._byte_order))
        reply = self.get_reply([b"\x10", instr_datetime], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Time on device %s set to UTC.", self.device_id)
            return True
        logger().error("Setting the time on device %s failed.", self.device_id)
        return False

    @overrides
    def stop_cycle(self):
        """Stop the measuring cycle."""
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x16", b""], timeout=self._ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle stopped at device %s.", self.device_id)
            return True
        logger().error("stop_cycle() failed at device %s.", self.device_id)
        return False

    @overrides
    def start_cycle(self, cycle=0):
        """Start a measuring cycle.

        Args:
            cycle (int): Cycle index

        """
        logger().debug("Trying to start measuring cycle %d", cycle)
        self.stop_cycle()
        self._cycle = cycle
        self._interval = self._read_cycle_start(cycle)["cycle_interval"]
        for _component_id, component in self.components.items():
            for _sensor_id, sensor in component.sensors.items():
                sensor.interval = self._interval
        ok_byte = self.family["ok_byte"]
        reply = self.get_reply([b"\x15", bytes([cycle])], timeout=self.ext_ser_timeout)
        if reply and (reply[0] == ok_byte):
            logger().debug("Cycle %s started at device %s.", cycle, self.device_id)
            return True
        logger().error("start_cycle() failed at device %s.", self.device_id)
        if reply[0] == 11:
            logger().error("DACM instrument replied with error code %s.", reply[1])
            logger().info("reply: %s", reply)
        return False

    @overrides
    def _new_rs485_address(self, raw_cmd):
        """Check whether raw_cmd changed the RS-485 bus address of the instrument.
        If this is the case, self._route will be changed.

        Args:
            raw_cmd (bytes): Command message to be analyzed.
        """
        message = self._rs485_filter(raw_cmd)
        payload = self._check_message(
            message,
            multiframe=False,
        )["payload"]
        cmd_dict = self._analyze_cmd_data(payload)
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

    @overrides
    def get_recent_value(self, component_id=None, sensor_id=None, measurand_id=None):
        """Get a dictionaries with recent measuring values from one sensor.
        component_id: one of the 34 sensor/actor modules of the DACM system
        measurand_id:
        0 = recent sampling,
        1 = average of last completed interval,
        2 = minimum of last completed interval,
        3 = maximum
        sensor_id: only for sensors delivering multiple measurands"""
        super().get_recent_value(component_id, sensor_id, measurand_id)
        interval = self._interval
        component = self.components[component_id]
        sensor = component.sensors[sensor_id]
        measurand = sensor.measurands[measurand_id]
        fetched = (
            self.components[component_id]
            .sensors[sensor_id]
            .measurands[measurand_id]
            .fetched
        )
        if fetched == datetime.min:
            logger().warning("The gathered value might be invalid.")
            output = self._gather_recent_value(component_id, sensor_id, measurand_id)
            try:
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].name = output["measurand_name"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].operator = output["measurand_operator"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].value = output["value"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].unit = output["measurand_unit"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].time = output["datetime"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].interval = output["sample_interval"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].gps = output["gps"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].fetched = output["fetched"]
            except KeyError as exception:
                logger().error(
                    "Key error in first fetch of (%d, %d, %d): %s; %s",
                    component_id,
                    sensor_id,
                    measurand_id,
                    exception,
                    output,
                )
                return {}
            return output
        in_recent_interval = bool(
            measurand_id == 0 and ((datetime.utcnow() - fetched) < timedelta(seconds=5))
        )
        in_main_interval = bool(
            measurand_id != 0 and ((datetime.utcnow() - fetched) < interval)
        )
        if not in_main_interval and not in_recent_interval:
            output = self._gather_recent_value(component_id, sensor_id, measurand_id)
            try:
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].name = output["measurand_name"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].operator = output["measurand_operator"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].value = output["value"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].unit = output["measurand_unit"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].time = output["datetime"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].interval = output["sample_interval"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].gps = output["gps"]
                self.components[component_id].sensors[sensor_id].measurands[
                    measurand_id
                ].fetched = output["fetched"]
            except KeyError as exception:
                logger().error("Key error in fetch: %s; %s", exception, output)
                return {}
            return output
        if in_main_interval:
            logger().info(
                "We do not have new values yet. Sample interval = %s.",
                interval,
            )
        elif in_recent_interval:
            logger().info(
                "We don't request recent values faster than every %s.",
                timedelta(seconds=5),
            )
        self._gps = Gps(valid=measurand.gps)
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
            "gps": measurand.gps,
        }

    def _gather_recent_value(self, component_id, sensor_id, measurand_id):
        repeat_counter = 2
        reply = b"\x00"
        while repeat_counter and (not reply[0]):
            logger().debug(
                "_gather_recent_value(%d, %d, %d), attempt %d",
                component_id,
                sensor_id,
                measurand_id,
                3 - repeat_counter,
            )
            reply = self.get_reply(
                [
                    b"\x1a",
                    bytes([component_id]) + bytes([sensor_id]) + bytes([measurand_id]),
                ],
                timeout=self.ext_ser_timeout,
            )
            logger().debug("reply: %s", reply)
            if not reply:
                logger().error(
                    "The instrument doesn't reply request for (%d, %d, %d)",
                    component_id,
                    sensor_id,
                    measurand_id,
                )
                return {}
            repeat_counter = repeat_counter - 1
        if reply[0]:
            return self._parse_recent_value_bin(reply, measurand_id)
        logger().error("Measurand not available.")
        return {}

    def _parse_recent_value_bin(self, reply: bytes, measurand_id: int):
        measurand_names = {0: "recent", 1: "average", 2: "minimum", 3: "maximum"}
        output = {}
        output["component_name"] = reply[1:17].split(b"\x00")[0].decode("cp1252")
        output["measurand_name"] = measurand_names[measurand_id]
        output["sensor_name"] = reply[18:34].split(b"\x00")[0].decode("cp1252")
        output["measurand"] = reply[35:51].split(b"\x00")[0].strip().decode("cp1252")
        measurand_dict = self._parse_value_string(output["measurand"])
        output["measurand_operator"] = measurand_dict["measurand_operator"]
        output["value"] = measurand_dict["measurand_value"]
        output["measurand_unit"] = measurand_dict["measurand_unit"]
        meas_time = reply[69:85].split(b"\x00")[0].split(b":")
        meas_date = reply[52:68].split(b"\x00")[0].split(b"/")
        if len(meas_date) == 3:
            year = int(meas_date[2])
            month = int(meas_date[0])
            day = int(meas_date[1])
        else:
            meas_date = reply[52:68].split(b"\x00")[0].split(b".")
            if len(meas_date) == 3:
                year = int(meas_date[2])
                month = int(meas_date[1])
                day = int(meas_date[0])
            else:
                year = 0
                month = 0
                day = 0
        logger().debug(meas_date)
        if meas_date != [b""]:
            meas_datetime = datetime(
                year,
                month,
                day,
                int(meas_time[0]),
                int(meas_time[1]),
                int(meas_time[2]),
                tzinfo=timezone.utc,
            )
            if self._utc_offset is None:
                self._utc_offset = self._calc_utc_offset(
                    self._interval, meas_datetime, datetime.now(timezone.utc)
                )
            output["sample_interval"] = self._interval
        else:
            meas_datetime = datetime.now(timezone.utc)
            output["sample_interval"] = timedelta(seconds=0)
        if self._utc_offset is None:
            output["datetime"] = meas_datetime.replace(microsecond=0)
        else:
            output["datetime"] = meas_datetime.replace(
                microsecond=0, tzinfo=timezone(timedelta(hours=self._utc_offset))
            )
        try:
            gps_list = re.split("[ ]+ |ø|M[ ]*", reply[86:].decode("cp1252"))
            gps = Gps(
                valid=True,
                timestamp=output["datetime"].timestamp(),
                latitude=(
                    float(gps_list[0]) if gps_list[1] == "N" else -float(gps_list[0])
                ),
                longitude=(
                    float(gps_list[2]) if gps_list[3] == "E" else -float(gps_list[2])
                ),
                altitude=float(gps_list[4]),
                deviation=float(gps_list[5]),
            )
        except Exception:  # pylint: disable=broad-except
            gps = Gps(valid=False)
        output["gps"] = gps
        output["fetched"] = datetime.utcnow()
        return output

    def get_date_of_config(self):
        """Return the date the configuration was made on."""
        return self._date_of_config

    def set_date_of_config(self, date_of_config):
        """Set the date of the configuration."""
        self._date_of_config = date_of_config
        if (self._route.port is not None) and (self.date_of_config is not None):
            self._initialize()

    def get_module_name(self):
        """Return the name of the DACM module."""
        return self._module_name

    def set_module_name(self, module_name):
        """Set the name of the DACM module."""
        self._module_name = module_name
        if (self._route.port is not None) and (self.module_name is not None):
            self._initialize()

    def get_config_name(self):
        """Return the name of the configuration."""
        return self._config_name

    def set_config_name(self, config_name):
        """Set the name of the configuration."""
        self._config_name = config_name
        if (self._route.port is not None) and (self.config_name is not None):
            self._initialize()

    def get_date_of_manufacture(self):
        """Return the date of manufacture."""
        return self._date_of_manufacture

    def get_date_of_update(self):
        """Return the date of firmware update."""
        return self._date_of_update

    module_name = property(get_module_name, set_module_name)
    date_of_config = property(get_date_of_config, set_date_of_config)
    config_name = property(get_config_name, set_config_name)
    date_of_manufacture = property(get_date_of_manufacture)
    date_of_update = property(get_date_of_update)

    @property
    def type_name(self) -> str:
        """Return the device type name."""
        if self.module_name is None:
            for type_in_family in self.family["types"]:
                if type_in_family["type_id"] == self.type_id:
                    return type_in_family["type_name"]
            return "unknown"
        return self.module_name

    @property
    def geopos(self) -> Gps:
        """Update the GPS object if requrired and give it back."""
        if (not self._gps.valid) or (
            datetime.now(timezone.utc).timestamp() - self._gps.timestamp > 1
        ):
            logger().info("Update geographic position")
            self._gps = self._gather_recent_value(0, 0, 0).get("gps", Gps(valid=False))
        return self._gps

    @geopos.setter
    def geopos(self, gps: Gps):
        """Set the geographic position of the instrument."""
        self._gps = gps
