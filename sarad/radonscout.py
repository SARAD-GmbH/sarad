"""Module for the communication with instruments of the Radon Scout family."""

from datetime import datetime
from datetime import timedelta
import logging
from sarad.sari import SaradInst, Component, Sensor, Measurand

logger = logging.getLogger(__name__)


# * RscInst:
# ** Definitions:
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
        get_all_recent_values()
        get_recent_value(index)
        set_real_time_clock(datetime)
        stop_cycle()
        start_cycle()
        get_config()
        set_config()"""

    version = '0.1'

    def __init__(self, port=None, family=None):
        if family is None:
            family = SaradInst.products[1]
        SaradInst.__init__(self, port, family)
        self._last_sampling_time = None
        self.__alarm_level = None
        self.lock = None
        self.__ssid = None
        self.__password = None
        self.__server_port = None
        self.__ip_address = None

# ** Private methods:
# *** _gather_all_recent_values(self):

    def _gather_all_recent_values(self):
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x14', b''], 33)
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
                source.append(round(self._bytes_to_float(reply[12:16]),
                                    2))  # 2
                source.append(reply[16])  # 3
                source.append(round(self._bytes_to_float(reply[17:21]),
                                    2))  # 4
                source.append(round(self._bytes_to_float(reply[21:25]),
                                    2))  # 5
                source.append(round(self._bytes_to_float(reply[25:29]),
                                    2))  # 6
                source.append(
                    int.from_bytes(reply[29:33], byteorder='big',
                                   signed=False))  # 7
                source.append(self._get_battery_voltage())  # 8
                device_time = datetime(device_time_y + 2000, device_time_m,
                                       device_time_d, device_time_h,
                                       device_time_min)
            except TypeError:
                logger.error("TypeError when parsing the payload.")
                return False
            except ReferenceError:
                logger.error("ReferenceError when parsing the payload.")
                return False
            except LookupError:
                logger.error("LookupError when parsing the payload.")
                return False
            except ValueError:
                logger.error("ValueError when parsing the payload.")
                return False
            except Exception:   # pylint: disable=broad-except
                logger.error("Unknown error when parsing the payload.")
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
                            logger.error(
                                "Can't get value for source %s in %s/%s/%s.",
                                measurand.source,
                                component.name, sensor.name, measurand.name)
            return True
        logger.error("Device %s doesn't reply.", self.device_id)
        return False

# ** Protected methods overriding methods of SaradInst:
# *** _build_component_list(self):

    def _build_component_list(self):
        logger.debug('Building component list for Radon Scout instrument.')
        for component_object in self.components:
            del component_object
        self.components = []
        component_dict = self._get_parameter('components')
        if not component_dict:
            return False
        for component in component_dict:
            component_object = Component(component['component_id'],
                                         component['component_name'])
            # build sensor list
            for sensor in component['sensors']:
                sensor_object = Sensor(sensor['sensor_id'],
                                       sensor['sensor_name'])
                # build measurand list
                for measurand in sensor['measurands']:
                    try:
                        unit = measurand['measurand_unit']
                    except Exception:  # pylint: disable=broad-except
                        unit = ''
                    try:
                        source = measurand['measurand_source']
                    except Exception:  # pylint: disable=broad-except
                        source = None
                    measurand_object = Measurand(measurand['measurand_id'],
                                                 measurand['measurand_name'],
                                                 unit, source)
                    sensor_object.measurands += [measurand_object]
                component_object.sensors += [sensor_object]
            self.components += [component_object]
        return len(self.components)

# ** Protected methods:
# *** _get_battery_voltage(self):

    def _get_battery_voltage(self):
        battery_bytes = self._get_parameter('battery_bytes')
        battery_coeff = self._get_parameter('battery_coeff')
        ok_byte = self.family['ok_byte']
        if not (battery_coeff and battery_bytes):
            return "This instrument type doesn't provide \
            battery voltage information"

        reply = self.get_reply([b'\x0d', b''], battery_bytes + 1)
        if reply and (reply[0] == ok_byte):
            try:
                voltage = battery_coeff * int.from_bytes(
                    reply[1:], byteorder='little', signed=False)
                return round(voltage, 2)
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
            else:
                pass
        else:
            logger.error("Device %s doesn't reply.", self.device_id)
            return False

# *** _push_button(self):

    def _push_button(self):
        reply = self.get_reply([b'\x12', b''], 1)
        ok_byte = self.family['ok_byte']
        if reply and (reply[0] == ok_byte):
            logger.debug('Push button simulated at device %s.', self.device_id)
            return True
        logger.error('Push button failed at device %s.', self.device_id)
        return False

# ** Public methods:

# *** get_all_recent_values(self):

    def get_all_recent_values(self):
        """Fill the component objects with recent readings."""
        # Do nothing as long as the previous values are valid.
        if self._last_sampling_time is None:
            logger.warning(
                'The gathered values might be invalid. '
                'You should use function start_cycle() in your application '
                'for a regular initialization of the measuring cycle.')
            return self._gather_all_recent_values()
        if (datetime.utcnow() - self._last_sampling_time) < self.__interval:
            logger.debug(
                'We do not have new values yet. Sample interval = %s.',
                self.__interval)
            return True
        return self._gather_all_recent_values()

# *** get_recent_value(component_id, sensor_id, measurand_id):

    def get_recent_value(self, component_id=None, sensor_id=None, _=None):
        """Fill component objects with recent measuring values.\
        This function does the same like get_all_recent_values()\
        and is only here to provide a compatible API to the DACM interface"""
        for measurand in self.components[component_id].sensors[
                sensor_id].measurands:
            logger.debug(measurand)
            if measurand.source == 8:  # battery voltage
                measurand.value = self._get_battery_voltage()
                measurand.time = datetime.utcnow().replace(microsecond=0)
                return measurand.value
        return self.get_all_recent_values()

# *** set_real_time_clock(datetime):

    def set_real_time_clock(self, date_time):
        """Set the instrument time."""
        ok_byte = self.family['ok_byte']
        instr_datetime = bytearray([date_time.second, date_time.minute,
                                    date_time.hour, date_time.day,
                                    date_time.month, date_time.year - 2000])
        reply = self.get_reply([b'\x05', instr_datetime], 1)
        if reply and (reply[0] == ok_byte):
            logger.debug("Time on device %s set to UTC.", self.device_id)
            return True
        logger.error(
            "Setting the time on device %s failed.", {self.device_id})
        return False

# *** stop_cycle(self):

    def stop_cycle(self):
        """Stop a measurement cycle."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x15', b''], 1)
        if reply and (reply[0] == ok_byte):
            logger.debug('Cycle stopped at device %s.', self.device_id)
            return True
        logger.error('stop_cycle() failed at device %s.', self.device_id)
        return False

# *** start_cycle(self, cycle_index):

    def start_cycle(self, _):
        """Start a measurement cycle."""
        self.get_config()  # to set self.__interval
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self.__interval
        self._last_sampling_time = datetime.utcnow()
        return self.stop_cycle() and self._push_button()

# *** get_config(self):

    def get_config(self):
        """Get configuration from device."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x10', b''], 8)
        if reply and (reply[0] == ok_byte):
            logger.debug('Getting config. from device %s.', self.device_id)
            try:
                self.__interval = timedelta(minutes=reply[1])
                setup_word = reply[2:3]
                self._decode_setup_word(setup_word)
                self.__alarm_level = int.from_bytes(reply[4:8],
                                                    byteorder='little',
                                                    signed=False)
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
            return True
        logger.error("Get config. failed at device %s.", self.device_id)
        return False

# *** set_config(self):

    def set_config(self):
        """Upload a new configuration to the device."""
        ok_byte = self.family['ok_byte']
        setup_word = self._encode_setup_word()
        interval = int(self.__interval.seconds / 60)
        setup_data = (interval).to_bytes(1, byteorder='little') + \
            setup_word + \
            (self.__alarm_level).to_bytes(4, byteorder='little')
        logger.debug(setup_data)
        reply = self.get_reply([b'\x0f', setup_data], 1)
        if reply and (reply[0] == ok_byte):
            logger.debug(
                'Set config. successful at device %s.', self.device_id)
            return True
        logger.error("Set config. failed at device %s.", self.device_id)
        return False

# *** set_lock(self):

    def set_lock(self):
        """Lock the hardware button or switch at the device."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x01', b''], 1)
        if reply and (reply[0] == ok_byte):
            self.lock = self.Lock.locked
            logger.debug('Device %s locked.', self.device_id)
            return True
        logger.error('Locking failed at device %s.', self.device_id)
        return False

# *** set_unlock(self):

    def set_unlock(self):
        """Unlock the hardware button or switch at the device."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x02', b''], 1)
        if reply and (reply[0] == ok_byte):
            self.lock = self.Lock.unlocked
            logger.debug('Device %s unlocked.', self.device_id)
            return True
        logger.error('Unlocking failed at device %s.', self.device_id)
        return False

# *** set_long_interval(self):

    def set_long_interval(self):
        """Set the measuring interval to 3 h = 180 min = 10800 s"""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x03', b''], 1)
        if reply and (reply[0] == ok_byte):
            self.__interval = timedelta(hours=3)
            logger.debug('Device %s set to 3 h interval.', self.device_id)
            return True
        logger.error('Interval setup failed at device %s.', self.device_id)
        return False

# *** set_short_interval(self):

    def set_short_interval(self):
        """Set the measuring interval to 1 h = 60 min = 3600 s"""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x04', b''], 1)
        if reply and (reply[0] == ok_byte):
            self.__interval = timedelta(hours=1)
            logger.debug('Device %s set to 1 h interval.', self.device_id)
            return True
        logger.error('Interval setup failed at device %s.', self.device_id)
        return False

# *** get_wifi_access(self):

    def get_wifi_access(self):
        """Get the Wi-Fi access data from instrument."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x18', b''], 125)
        if reply and (reply[0] == ok_byte):
            try:
                logger.debug(reply)
                self.__ssid = reply[0:33].rstrip(b'0')
                self.__password = reply[33:97].rstrip(b'0')
                self.__ip_address = reply[97:121].rstrip(b'0')
                self.__server_port = int.from_bytes(reply[121:123], 'big')
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
            else:
                pass
        else:
            logger.error('Cannot get Wi-Fi access data from device %s.',
                         self.device_id)
            return False

# *** set_wifi_access(self):

    def set_wifi_access(self, ssid, password, ip_address, server_port):
        """Set the WiFi access data."""
        ok_byte = self.family['ok_byte']
        access_data = b''.join([
            bytes(ssid, 'utf-8').ljust(33, b'0'),
            bytes(password, 'utf-8').ljust(64, b'0'),
            bytes(ip_address, 'utf-8').ljust(24, b'0'),
            server_port.to_bytes(2, 'big')
        ])
        logger.debug(access_data)
        reply = self.get_reply([b'\x17', access_data], 118)
        if reply and (reply[0] == ok_byte):
            logger.debug("WiFi access data on device %s set.", self.device_id)
            return True
        logger.error("Setting WiFi access data on device %s failed.",
                     self.device_id)
        return False
