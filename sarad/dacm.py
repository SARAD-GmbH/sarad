"""Module for the communication with instruments of the DACM family."""

from datetime import datetime
import logging
from BitVector import BitVector  # type: ignore
from sarad.sari import SaradInst

logger = logging.getLogger(__name__)


# * DacmInst:
# ** Definitions:
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
        get_family(),
        set_family(),
        get_id(),
        set_id(),
        get_port(),
        set_port(),
        get_type_id()
        get_software_version()
        get_serial_number()
        get_components()
        set_components()
        get_reply()
    Public methods:
        set_real_time_clock()
        stop_cycle()
        start_cycle()
        get_all_recent_values()
        get_recent_value(index)"""

    version = '0.1'

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

# ** Private methods:

# *** __str__(self):

    def __str__(self):
        output = "Id: " + str(self.device_id) + "\n"
        output += "SerialDevice: " + self.port + "\n"
        output += "Baudrate: " + str(self.family['baudrate']) + "\n"
        output += "FamilyName: " + str(self.family['family_name']) + "\n"
        output += "FamilyId: " + str(self.family['family_id']) + "\n"
        output += "TypName: " + self.type_name + "\n"
        output += "TypeId: " + str(self.type_id) + "\n"
        output += "SoftwareVersion: " + str(self.software_version) + "\n"
        output += "LastUpdate: " + str(self.date_of_update) + "\n"
        output += "SerialNumber: " + str(self.serial_number) + "\n"
        output += "DateOfManufacture: " + str(self.date_of_manufacture) + "\n"
        output += "Address: " + str(self.address) + "\n"
        output += "LastConfig: " + str(self.date_of_config) + "\n"
        output += "ModuleName: " + str(self.module_name) + "\n"
        output += "ConfigName: " + str(self.config_name) + "\n"
        return output

# ** Protected methods overriding methods of SaradInst:
# *** _get_description(self):

    def _get_description(self):
        """Get descriptive data about DACM instrument."""
        ok_byte = self.family['ok_byte']
        id_cmd = self.family['get_id_cmd']
        length_of_reply = self.family['length_of_reply']
        reply = self.get_reply(id_cmd, length_of_reply)
        if reply and (reply[0] == ok_byte):
            logger.debug('Get description successful.')
            try:
                self._type_id = reply[1]
                self._software_version = reply[2]
                self._serial_number = int.from_bytes(reply[3:5],
                                                     byteorder='big',
                                                     signed=False)
                manu_day = reply[5]
                manu_month = reply[6]
                manu_year = int.from_bytes(reply[7:9],
                                           byteorder='big',
                                           signed=False)
                self._date_of_manufacture = datetime(manu_year, manu_month,
                                                     manu_day)
                upd_day = reply[9]
                upd_month = reply[10]
                upd_year = int.from_bytes(reply[11:13],
                                          byteorder='big',
                                          signed=False)
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
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except Exception:   # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
                return False
        logger.debug('Get description failed.')
        return False

# ** Protected methods:
# *** _get_module_information(self):

    def _get_module_information(self):
        """Get descriptive data about DACM instrument."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x01', b''], 73)
        if reply and (reply[0] == ok_byte):
            logger.debug('Get module information successful.')
            try:
                self._address = reply[1]
                config_day = reply[2]
                config_month = reply[3]
                config_year = int.from_bytes(reply[4:6],
                                             byteorder='big',
                                             signed=False)
                self._date_of_config = datetime(config_year, config_month,
                                                config_day)
                self._module_name = reply[6:39].split(b'\x00')[0].decode(
                    "ascii")
                self._config_name = reply[39:].split(b'\x00')[0].decode(
                    "ascii")
                return True
            except TypeError:
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except Exception:   # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
                return False
        logger.debug('Get module information failed.')
        return False

# *** _get_component_information():

    def _get_component_information(self, component_index):
        """Get information about one component of a DACM instrument."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x03', bytes([component_index])], 21)
        if reply and (reply[0] == ok_byte):
            logger.debug('Get component information successful.')
            try:
                revision = reply[1]
                component_type = reply[2]
                availability = reply[3]
                ctrl_format = reply[4]
                conf_block_size = reply[5]
                data_record_size = int.from_bytes(reply[6:8],
                                                  byteorder='big',
                                                  signed=False)
                name = reply[8:16].split(b'\x00')[0].decode("ascii")
                hw_capability = BitVector(rawbytes=reply[16:20])
                return dict(revision=revision,
                            component_type=component_type,
                            availability=availability,
                            ctrl_format=ctrl_format,
                            conf_block_size=conf_block_size,
                            data_record_size=data_record_size,
                            name=name,
                            hw_capability=hw_capability)
            except TypeError:
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except Exception:   # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
                return False
        logger.debug('Get component information failed.')
        return False

# *** _get_component_configuration():

    def _get_component_configuration(self, component_index):
        """Get information about the configuration of a component
        of a DACM instrument."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x04', bytes([component_index])], 73)
        if reply and (reply[0] == ok_byte):
            logger.debug('Get component configuration successful.')
            try:
                sensor_name = reply[8:16].split(b'\x00')[0].decode("ascii")
                sensor_value = reply[8:16].split(b'\x00')[0].decode("ascii")
                sensor_unit = reply[8:16].split(b'\x00')[0].decode("ascii")
                input_config = int.from_bytes(reply[6:8],
                                              byteorder='big',
                                              signed=False)
                alert_level_lo = int.from_bytes(reply[6:8],
                                                byteorder='big',
                                                signed=False)
                alert_level_hi = int.from_bytes(reply[6:8],
                                                byteorder='big',
                                                signed=False)
                alert_output_lo = int.from_bytes(reply[6:8],
                                                 byteorder='big',
                                                 signed=False)
                alert_output_hi = int.from_bytes(reply[6:8],
                                                 byteorder='big',
                                                 signed=False)
                return dict(sensor_name=sensor_name,
                            sensor_value=sensor_value,
                            sensor_unit=sensor_unit,
                            input_config=input_config,
                            alert_level_lo=alert_level_lo,
                            alert_level_hi=alert_level_hi,
                            alert_output_lo=alert_output_lo,
                            alert_output_hi=alert_output_hi)
            except TypeError:
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except Exception:   # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
                return False
        logger.debug('Get component configuration failed.')
        return False

# *** _read_cycle_start(self):

    def _read_cycle_start(self, cycle_index=0):
        """Get description of a measuring cycle."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x06', bytes([cycle_index])], 28)
        if reply and (reply[0] == ok_byte) and reply[1]:
            logger.debug('Get primary cycle information successful.')
            try:
                cycle_name = reply[2:19].split(b'\x00')[0].decode("ascii")
                cycle_interval = int.from_bytes(reply[19:21],
                                                byteorder='little',
                                                signed=False)
                cycle_steps = int.from_bytes(reply[21:24],
                                             byteorder='big',
                                             signed=False)
                cycle_repetitions = int.from_bytes(reply[24:28],
                                                   byteorder='little',
                                                   signed=False)
                return dict(cycle_name=cycle_name,
                            cycle_interval=cycle_interval,
                            cycle_steps=cycle_steps,
                            cycle_repetitions=cycle_repetitions)
            except TypeError:
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except Exception:   # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
                return False
        logger.debug('Get primary cycle info failed.')
        return False

# *** _read_cycle_continue():

    def _read_cycle_continue(self):
        """Get description of subsequent cycle intervals."""
        reply = self.get_reply([b'\x07', b''], 16)
        if reply and not len(reply) < 16:
            logger.debug('Get information about cycle interval successful.')
            try:
                seconds = int.from_bytes(reply[0:4],
                                         byteorder='little',
                                         signed=False)
                bit_ctrl = BitVector(rawbytes=reply[4:8])
                value_ctrl = BitVector(rawbytes=reply[8:12])
                rest = BitVector(rawbytes=reply[12:16])
                return dict(seconds=seconds,
                            bit_ctrl=bit_ctrl,
                            value_ctrl=value_ctrl,
                            rest=rest)
            except TypeError:
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except Exception:   # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
                return False
        logger.debug('Get info about cycle interval failed.')
        return False

# ** Public methods:
# *** set_real_time_clock():

    def set_real_time_clock(self, date_time):
        """Set the instrument time."""
        ok_byte = self.family['ok_byte']
        instr_datetime = bytearray([date_time.second, date_time.minute,
                                    date_time.hour, date_time.day,
                                    date_time.month])
        instr_datetime.extend((date_time.year).to_bytes(2, byteorder='big'))
        reply = self.get_reply([b'\x10', instr_datetime], 1)
        if reply and (reply[0] == ok_byte):
            logger.debug("Time on device %s set to UTC.", self.device_id)
            return True
        logger.error("Setting the time on device %s failed.", self.device_id)
        return False

# *** stop_cycle():

    def stop_cycle(self):
        """Stop the measuring cycle."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x16', b''], 1)
        if reply and (reply[0] == ok_byte):
            logger.debug('Cycle stopped at device %s.', self.device_id)
            return True
        logger.error("stop_cycle() failed at device %s.", self.device_id)
        return False

# *** start_cycle():

    def start_cycle(self, cycle_index=0):
        """Start a measuring cycle."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x15', bytes([cycle_index])], 3, timeout=5)
        if reply and (reply[0] == ok_byte):
            logger.debug('Cycle %s started at device %s.',
                         cycle_index, self.device_id)
            return True
        logger.error("start_cycle() failed at device %s.", self.device_id)
        if reply[0] == 11:
            logger.error('DACM instrument replied with error code %s.',
                         reply[1])
        return False

# *** set_lock():

    @staticmethod
    def set_lock():
        """Lock the hardware button or switch at the device.
        This is a dummy since this locking function does not exist
        on DACM instruments."""
        return True

# *** get_all_recent_values(self):

    def get_all_recent_values(self):
        """Get a list of dictionaries with recent measuring values."""
        list_of_outputs = []
        sensor_id = 0  # fixed value, reserved for future use
        for component_id in range(34):
            for measurand_id in range(4):
                output = self.get_recent_value(component_id, sensor_id,
                                               measurand_id)
                list_of_outputs.append(output)
        return list_of_outputs

# *** get_recent_value():

    def get_recent_value(self, component_id, sensor_id=0, measurand_id=0):
        """Get a dictionaries with recent measuring values from one sensor.
        component_id: one of the 34 sensor/actor modules of the DACM system
        measurand_id:
        0 = recent sampling,
        1 = average of last completed interval,
        2 = minimum of last completed interval,
        3 = maximum
        sensor_id: only for sensors delivering multiple measurands"""
        reply = self.get_reply([
            b'\x1a',
            bytes([component_id]) + bytes([sensor_id]) + bytes([measurand_id])
        ], 1000)
        if reply and (reply[0] > 0):
            output = dict()
            output['component_name'] = reply[1:17].split(b'\x00')[0].decode(
                "ascii")
            output['measurand_id'] = measurand_id
            output['sensor_name'] = reply[18:34].split(b'\x00')[0].decode(
                "ascii")
            output['measurand'] = reply[35:51].split(
                b'\x00')[0].strip().decode("ascii")
            measurand = self._parse_value_string(output['measurand'])
            output['measurand_operator'] = measurand['measurand_operator']
            output['value'] = measurand['measurand_value']
            output['measurand_unit'] = measurand['measurand_unit']
            date = reply[52:68].split(b'\x00')[0].split(b'/')
            meas_time = reply[69:85].split(b'\x00')[0].split(b':')
            if date != [b'']:
                output['datetime'] = datetime(int(date[2]), int(date[0]),
                                              int(date[1]), int(meas_time[0]),
                                              int(meas_time[1]),
                                              int(meas_time[2]))
            else:
                output['datetime'] = None
            output['gps'] = reply[86:].split(b'\x00')[0].decode("ascii")
            return output
        if reply[0] == 0:
            logger.error("Measurand not available.")
            return False
        logger.error("The instrument doesn't reply.")
        return False

# *** get/set_address():

    def get_address(self):
        """Return the address of the DACM module."""
        return self._address

    def set_address(self, address):
        """Set the address of the DACM module."""
        self._address = address
        if (self.port is not None) and (self.address is not None):
            self._initialize()

# *** get/set_date_of_config():

    def get_date_of_config(self):
        """Return the date the configuration was made on."""
        return self._date_of_config

    def set_date_of_config(self, date_of_config):
        """Set the date of the configuration."""
        self._date_of_config = date_of_config
        if (self.port is not None) and (self.date_of_config is not None):
            self._initialize()

# *** get/set_module_name():

    def get_module_name(self):
        """Return the name of the DACM module."""
        return self._module_name

    def set_module_name(self, module_name):
        """Set the name of the DACM module."""
        self._module_name = module_name
        if (self.port is not None) and (self.module_name is not None):
            self._initialize()

# *** get/set_config_name():

    def get_config_name(self):
        """Return the name of the configuration."""
        return self._config_name

    def set_config_name(self, config_name):
        """Set the name of the configuration."""
        self._config_name = config_name
        if (self.port is not None) and (self.config_name is not None):
            self._initialize()

# *** get_date_of_manufacture(self):

    def get_date_of_manufacture(self):
        """Return the date of manufacture."""
        return self._date_of_manufacture

# *** get_date_of_update(self):

    def get_date_of_update(self):
        """Return the date of firmware update."""
        return self._date_of_update

# ** Properties:

    module_name = property(get_module_name, set_module_name)
    address = property(get_address, set_address)
    date_of_config = property(get_date_of_config, set_date_of_config)
    config_name = property(get_config_name, set_config_name)
    date_of_manufacture = property(get_date_of_manufacture)
    date_of_update = property(get_date_of_update)
