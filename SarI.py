"""Collection of classes to communicate with SARAD instruments about (virtual)
serial interfaces."""

import time
from datetime import datetime
from datetime import timedelta
import struct
from enum import Enum
import pickle
import logging
import os
import hashids  # type: ignore
import yaml
from BitVector import BitVector  # type: ignore
import serial  # type: ignore
import serial.tools.list_ports  # type: ignore

logger = logging.getLogger(__name__)


# * SaradInst:
# ** Definitions:
class SaradInst():
    """Basic class for the serial communication protocol of SARAD instruments

    Properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        device_id: Identifier for an individual instrument in a cluster
        type_id: Together with family, this Id identifys the instrument type.
        type_name: Identifys the instrument type.
        software_version: The version of the firmware.
        serial_number: Serial number of the connected instrument.
        components: List of sensor or actor components
    Public methods:
        get_family()
        set_family()
        get_id()
        set_id()
        get_port()
        set_port()
        get_type_id()
        get_software_version()
        get_serial_number()
        get_components()
        set_components()
        get_reply()"""
    class Lock(Enum):
        """Setting of the device. Lock the hardware button."""
        unlocked = 1
        locked = 2

    class RadonMode(Enum):
        """Setting of the device. Displayed radon values based on
        short living progeny only (fast)
        or on short and long living progeny (slow)"""
        slow = 1
        fast = 2

    class PumpMode(Enum):
        """Setting of the devices having a pump."""
        continuous = 1
        interval = 2

    class Units(Enum):
        """Setting of the device. Unit system used for display."""
        si = 1
        us = 2

    class Signal(Enum):
        """Setting of the device. When shall it give an audible signal?"""
        off = 1
        alarm = 2
        sniffer_po216 = 3
        po216_po218 = 4

    class ChamberSize(Enum):
        """Setting the chamber size (Radon Scout PMT only)."""
        small = 1
        medium = 2
        large = 3
        xl = 4

# ** Private methods:

# *** __init__():

    def __init__(self, port=None, family=None):
        self.__port = port
        self.__family = family
        if (port is not None) and (family is not None):
            self._initialize()
        self.__components = []
        self.__i = 0
        self.__n = len(self.__components)
        self.__interval = None
        self._type_id = None
        self._type_name = None
        self._software_version = None
        self._serial_number = None

# *** __iter__():

    def __iter__(self):
        return iter(self.__components)

# *** __make_command_msg():

    @staticmethod
    def __make_command_msg(cmd_data):
        """Encode the message to be sent to the SARAD instrument.
        Arguments are the one byte long command
        and the data bytes to be sent."""
        cmd = cmd_data[0]
        data = cmd_data[1]
        payload = cmd + data
        control_byte = len(payload) - 1
        if cmd:  # Control message
            control_byte = control_byte | 0x80  # set Bit 7
        neg_control_byte = control_byte ^ 0xff
        checksum = 0
        for byte in payload:
            checksum = checksum + byte
        checksum_bytes = (checksum).to_bytes(2, byteorder='little')
        output = b'B' + \
                 bytes([control_byte]) + \
                 bytes([neg_control_byte]) + \
                 payload + \
                 checksum_bytes + \
                 b'E'
        return output

# *** __check_answer():

    @staticmethod
    def __check_answer(answer):
        # Returns a dictionary of:
        #     is_valid: True if answer is valid, False otherwise
        #     is_control_message: True if control message
        #     payload: Payload of answer
        #     number_of_bytes_in_payload
        logger.debug('Checking answer from serial port:')
        logger.debug('Raw answer: %s', answer)
        if answer.startswith(b'B') & answer.endswith(b'E'):
            control_byte = answer[1]
            neg_control_byte = answer[2]
            if (control_byte ^ 0xff) == neg_control_byte:
                control_byte_ok = True
            number_of_bytes_in_payload = (control_byte & 0x7f) + 1
            is_control = bool(control_byte & 0x80)
            status_byte = answer[3]
            logger.debug('Status byte: %s', status_byte)
            payload = answer[3:3 + number_of_bytes_in_payload]
            calculated_checksum = 0
            for byte in payload:
                calculated_checksum = calculated_checksum + byte
            received_checksum_bytes = answer[3 + number_of_bytes_in_payload:5 +
                                             number_of_bytes_in_payload]
            received_checksum = int.from_bytes(received_checksum_bytes,
                                               byteorder='little',
                                               signed=False)
            if received_checksum == calculated_checksum:
                checksum_ok = True
            is_valid = control_byte_ok & checksum_ok
        else:
            is_valid = False
        if not is_valid:
            is_control = False
            payload = b''
            number_of_bytes_in_payload = 0
        logger.debug('Payload: %s', payload)
        return dict(is_valid=is_valid,
                    is_control=is_control,
                    payload=payload,
                    number_of_bytes_in_payload=number_of_bytes_in_payload)

# *** __get_message_payload():

    def __get_message_payload(self, message, expected_length_of_reply,
                              timeout):
        """ Returns a dictionary of:
        is_valid: True if answer is valid, False otherwise
        is_control_message: True if control message
        payload: Payload of answer
        number_of_bytes_in_payload"""
        serial_port = self.__port
        baudrate = self.__family['baudrate']
        parity = self.__family['parity']
        write_sleeptime = self.__family['write_sleeptime']
        wait_for_reply = self.__family['wait_for_reply']
        ser = serial.Serial(serial_port,
                            baudrate,
                            bytesize=8,
                            xonxoff=0,
                            timeout=timeout,
                            parity=parity,
                            rtscts=0,
                            stopbits=serial.STOPBITS_ONE)
        for element in message:
            byte = (element).to_bytes(1, 'big')
            ser.write(byte)
            time.sleep(write_sleeptime)
        time.sleep(wait_for_reply)
        answer = ser.read(expected_length_of_reply)
        time.sleep(0.1)
        while ser.in_waiting:
            logger.debug('%s bytes waiting.', ser.in_waiting)
            ser.read(ser.in_waiting)
            time.sleep(0.5)
        ser.close()
        checked_answer = self.__check_answer(answer)
        return dict(is_valid=checked_answer['is_valid'],
                    is_control=checked_answer['is_control'],
                    payload=checked_answer['payload'],
                    number_of_bytes_in_payload=checked_answer[
                        'number_of_bytes_in_payload'])

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
        output += "SerialNumber: " + str(self.serial_number) + "\n"
        return output

# ** Protected methods:
# *** _initialize(self):

    def _initialize(self):
        self._get_description()
        self._build_component_list()
        self._last_sampling_time = None

# *** _get_description(self):

    def _get_description(self):
        """Set instrument type, software version, and serial number."""
        id_cmd = self.family['get_id_cmd']
        length_of_reply = self.family['length_of_reply']
        ok_byte = self.family['ok_byte']
        reply = self.get_reply(id_cmd, length_of_reply)
        if reply and (reply[0] == ok_byte):
            logger.debug('Get description successful.')
            try:
                self._type_id = reply[1]
                self._software_version = reply[2]
                self._serial_number = int.from_bytes(reply[3:5],
                                                     byteorder='little',
                                                     signed=False)
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
            logger.error('Get description failed.')
            return False

# *** _build_component_list(self):

    def _build_component_list(self):
        """Build up a list of components with sensors and measurands.
        Will be overriden by derived classes."""

# *** _bytes_to_float():

    @staticmethod
    def _bytes_to_float(value_bytes):
        """Convert 4 bytes (little endian) from serial interface into
        floating point nummber according to IEEE 754"""
        byte_array = bytearray(value_bytes)
        byte_array.reverse()
        return struct.unpack('<f', bytes(byte_array))[0]

# *** _parse_value_string():

    @staticmethod
    def _parse_value_string(value_string):
        """Take a string containing a physical value with operator,
        value and unit and decompose it into its parts
        for further mathematical processing."""
        output = dict()
        if value_string == 'No valid data!':
            output['measurand_operator'] = ''
            output['measurand_value'] = ''
            output['measurand_unit'] = ''
        else:
            try:
                if ('<' in value_string) or ('>' in value_string):
                    output['measurand_operator'] = value_string[0]
                    meas_with_unit = value_string[1:]
                else:
                    output['measurand_operator'] = ''
                    meas_with_unit = value_string
                output['measurand_value'] = float(meas_with_unit.split()[0])
                try:
                    output['measurand_unit'] = meas_with_unit.split()[1]
                except Exception:   # pylint: disable=broad-except
                    output['measurand_unit'] = ''
            except Exception:   # pylint: disable=broad-except
                output['measurand_operator'] = ''
                output['measurand_value'] = ''
                output['measurand_unit'] = ''
        return output

# *** _encode_setup_word(self):

    def _encode_setup_word(self):
        """Compile the SetupWord for Doseman and RadonScout devices
        from its components.  All used arguments from self are enum objects."""
        bv_signal = BitVector(intVal=self.signal.value - 1, size=2)
        bv_radon_mode = BitVector(intVal=self.radon_mode.value - 1, size=1)
        bv_pump_mode = BitVector(intVal=self.pump_mode.value - 1, size=1)
        bv_pump_mode = BitVector(bitstring='0')
        bv_units = BitVector(intVal=self.units.value - 1, size=1)
        bv_units = BitVector(bitstring='0')
        bv_chamber_size = BitVector(intVal=self.chamber_size.value - 1, size=2)
        bv_padding = BitVector(bitstring='000000000')
        bit_vector = bv_padding + bv_chamber_size + bv_units + bv_pump_mode + \
            bv_radon_mode + bv_signal
        logger.debug(str(bit_vector))
        return bit_vector.get_bitvector_in_ascii().encode('utf-8')

# *** _decode_setup_word():

    def _decode_setup_word(self, setup_word):
        bit_vector = BitVector(rawbytes=setup_word)
        signal_index = bit_vector[6:8].int_val()
        self.signal = list(self.Signal)[signal_index]
        radon_mode_index = bit_vector[5]
        self.radon_mode = list(self.RadonMode)[radon_mode_index]
        pump_mode_index = bit_vector[4]
        self.pump_mode = list(self.PumpMode)[pump_mode_index]
        units_index = bit_vector[3]
        self.units = list(self.Units)[units_index]
        chamber_size_index = bit_vector[1:3].int_val()
        self.chamber_size = list(self.ChamberSize)[chamber_size_index]

# *** _get_parameter():

    def _get_parameter(self, parameter_name):
        for inst_type in self.family['types']:
            if inst_type['type_id'] == self.type_id:
                try:
                    return inst_type[parameter_name]
                except Exception:  # pylint: disable=broad-except
                    pass
        try:
            return self.family[parameter_name]
        except Exception:       # pylint: disable=broad-except
            return False

# ** Public methods:

# *** next(self):

    def next(self):
        """Return the next component of this instrument."""
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__components[__i]
        self.__i = 0
        self.__n = len(self.__components)
        raise StopIteration()

# *** get_reply():

    def get_reply(self, cmd_data, reply_length=50, timeout=1):
        """Returns a bytestring of the payload of the instruments reply
        to the provided list of 1-byte command and data bytes."""
        length = reply_length + 6
        msg = self.__make_command_msg(cmd_data)
        checked_payload = self.__get_message_payload(msg, length, timeout)
        if checked_payload['is_valid']:
            return checked_payload['payload']
        logger.debug(checked_payload['payload'])
        return False

# *** get/set_port():

    def get_port(self):
        """Return serial port."""
        return self.__port

    def set_port(self, port):
        """Set serial port."""
        self.__port = port
        if (self.port is not None) and (self.family is not None):
            self._initialize()

# *** get/set_id():

    def get_id(self):
        """Return device id."""
        return self.__id

    def set_id(self, device_id):
        """Set device id."""
        self.__id = device_id

# *** get/set_family():

    def get_family(self):
        """Return the instrument family."""
        return self.__family

    def set_family(self, family):
        """Set the instrument family."""
        self.__family = family
        if (self.port is not None) and (self.family is not None):
            self._initialize()

# *** get_type_id():

    def get_type_id(self):
        """Return the device type id."""
        return self._type_id

# *** get_type_name():

    def get_type_name(self):
        """Return the device type name."""
        for type_in_family in self.family['types']:
            if type_in_family['type_id'] == self.type_id:
                return type_in_family['type_name']
            return None

# *** get_software_version():

    def get_software_version(self):
        """Return the firmware version of the device."""
        return self._software_version

# *** get_serial_number():

    def get_serial_number(self):
        """Return the serial number of the device."""
        return self._serial_number

# *** get/set_components():

    def get_components(self):
        """Return the list of components of the device."""
        return self.__components

    def set_components(self, components):
        """Set the list of components of the device."""
        self.__components = components

# ** Properties:

    port = property(get_port, set_port)
    device_id = property(get_id, set_id)
    family = property(get_family, set_family)
    type_id = property(get_type_id)
    type_name = property(get_type_name)
    software_version = property(get_software_version)
    serial_number = property(get_serial_number)
    components = property(get_components, set_components)


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
        get_family()
        set_family()
        get_id()
        set_id()
        get_port()
        set_port()
        get_type_id()
        get_software_version()
        get_serial_number()
        get_components()
        set_components()
        get_reply()"""

    # ** Private methods:
    def __init__(self, port=None, family=None):
        if family is None:
            family = SaradCluster.products[0]
        SaradInst.__init__(self, port, family)

# ** Public methods:
# *** stop_cycle(self):

    def stop_cycle(self):
        """Stop the measuring cycle."""
        ok_byte = self.family['ok_byte']
        reply = self.get_reply([b'\x15', b''], 1)
        if reply and (reply[0] == ok_byte):
            logger.debug('Cycle stopped at device %s.', self.device_id)
            return True
        logger.error('stop_cycle() failed at device %s.', self.device_id)
        return False

# *** start_cycle(self):

    def start_cycle(self):
        """Start a measuring cycle."""
        self.get_config()  # to set self.__interval
        for component in self.components:
            for sensor in component.sensors:
                sensor.interval = self.__interval
        self._last_sampling_time = datetime.utcnow()
        return self.stop_cycle() and self._push_button()


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
    def __init__(self, port=None, family=None):
        if family is None:
            family = SaradCluster.products[1]
        SaradInst.__init__(self, port, family)

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

    def get_recent_value(self, component_id=None, sensor_id=None, measurand_id=None):
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

# *** start_cycle(self):

    def start_cycle(self):
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
    def __init__(self, port=None, family=None):
        if family is None:
            family = SaradCluster.products[2]
        SaradInst.__init__(self, port, family)

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
        logger.error('Get description failed.')
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
        logger.error('Get description failed.')
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
            else:
                pass
        else:
            logger.error('Get component information failed.')
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
            else:
                pass
        else:
            logger.error('Get component configuration failed.')
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
            else:
                pass
        else:
            logger.error('Get primary cycle info failed.')
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
                                    date_time.month, date_time.year - 2000])
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
            logger.error('DACM instrument replied with error code %s.', reply[1])
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
                                              int(meas_time[1]), int(meas_time[2]))
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


# * SaradCluster:
# ** Definitions:
class SaradCluster():
    """Class to define a cluster of SARAD instruments
    that are all connected to one controller

    Class attributes:
        products
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
        next()
        synchronize(): Stop all instruments, set time, start all measurings
        dump(): Save all properties to a Pickle file
    """

    # with open(os.path.dirname(os.path.realpath(__file__)) +
    with open(os.getcwd() +
              os.path.sep + 'instruments.yaml', 'r') as __f:
        products = yaml.safe_load(__f)

    def __init__(self, native_ports=None):
        if native_ports is None:
            native_ports = []
        self.__native_ports = native_ports
        self.__i = 0
        self.__n = 0
        self.__start_time = 0
        self.__connected_instruments = []

# ** Private methods:

    def __iter__(self):
        return iter(self.__connected_instruments)

# ** Public methods:
# *** next(self):

    def next(self):
        """Iterate to next connected instrument."""
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__connected_instruments[__i]
        self.__i = 0
        self.__n = len(self.__connected_instruments)
        raise StopIteration()

# *** synchronize(self):

    def synchronize(self):
        """Stop measuring cycles of all connected instruments.
        Set instrument time to UTC on all instruments.
        Start measuring cycle on all instruments."""
        for instrument in self.connected_instruments:
            try:
                instrument.stop_cycle()
            except Exception:   # pylint: disable=broad-except
                logger.error(
                    'Not all instruments have been stopped as intended.')
                return False
        self.__start_time = datetime.utcnow()
        for instrument in self.connected_instruments:
            try:
                instrument.set_real_time_clock(self.__start_time)
                instrument.start_cycle()
            except Exception:   # pylint: disable=broad-except
                logger.error(
                    'Failed to set time and start cycles on all instruments.')
                return False
        return True

# *** get_active_ports(self):

    def get_active_ports(self):
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

    def update_connected_instruments(self, ports_to_test=[]):
        """Update the list of connected instruments
        in self.__connected_instruments and return this list."""
        hid = hashids.Hashids()
        if not ports_to_test:
            ports_to_test = self.active_ports
        logger.info('%d ports to test', len(ports_to_test))
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
        for family in SaradCluster.products:
            if family['family_id'] == 1:
                family_class = DosemanInst
            elif family['family_id'] == 2:
                family_class = RscInst
            elif family['family_id'] == 5:
                family_class = DacmInst
            else:
                continue
            test_instrument = family_class()
            test_instrument.family = family
            ports_with_instruments = []
            logger.info(ports_to_test)
            for port in ports_to_test:
                logger.info(
                    "Testing port %s for %s.", port, family['family_name'])
                test_instrument.port = port
                if test_instrument.type_id and test_instrument.serial_number:
                    device_id = hid.encode(test_instrument.family['family_id'],
                                           test_instrument.type_id,
                                           test_instrument.serial_number)
                    test_instrument.set_id(device_id)
                    logger.info('%s found on port %s.', family['family_name'],
                                port)
                    connected_instruments.append(test_instrument)
                    ports_with_instruments.append(port)
                    if (ports_to_test.index(port) + 1) < len(ports_to_test):
                        test_instrument = family_class()
                        test_instrument.family = family
            for port in ports_with_instruments:
                ports_to_test.remove(port)
        self.__connected_instruments = connected_instruments
        self.__n = len(connected_instruments)
        return connected_instruments

# *** get_connected_instruments(self):

    def get_connected_instruments(self):
        """Return list of connected instruments."""
        return self.__connected_instruments

# *** get/set_native_ports(self):

    def get_native_ports(self):
        """Return the list of all native serial ports (RS-232 ports)
        available at the instrument controller."""
        return self.__native_ports

    def set_native_ports(self, native_ports):
        """Set the list of native serial ports that shall be used."""
        self.__native_ports = native_ports

# *** get/set_start_time():

    def get_start_time(self):
        """Get a pre-defined start time for all instruments in this cluster."""
        return self.__start_time

    def set_start_time(self, start_time):
        """Set a start time for all instruments in this cluster."""
        self.__start_time = start_time

# *** dump:

    def dump(self, file):
        """Save the cluster information to a file."""
        logger.debug('Pickling mycluster into file.')
        pickle.dump(self, file, pickle.HIGHEST_PROTOCOL)

# ** Properties:

    native_ports = property(get_native_ports, set_native_ports)
    active_ports = property(get_active_ports)
    connected_instruments = property(get_connected_instruments)
    start_time = property(get_start_time, set_start_time)


# * Component:
# ** Definitions:
class Component():
    """Class describing a sensor or actor component built into an instrument"""
    def __init__(self, component_id, component_name):
        self.__id = component_id
        self.__name = component_name
        self.__sensors = []
        self.__i = 0
        self.__n = len(self.__sensors)

# ** Private methods:

    def __iter__(self):
        return iter(self.__sensors)

    def __str__(self):
        output = "ComponentId: " + str(self.id) + "\n"
        output += "ComponentName: " + self.name + "\n"
        output += "Sensors:\n"
        for sensor in self.sensors:
            output += str(sensor)
        return output

# ** Public methods:
# *** next(self):

    def next(self):
        """Iterate to the next sensor of this component."""
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__sensors[__i]
        self.__i = 0
        self.__n = len(self.__sensors)
        raise StopIteration()

# *** get/set_id:

    def get_id(self):
        """Return the Id of this component."""
        return self.__id

    def set_id(self, component_id):
        """Set the Id of this component."""
        self.__id = component_id

# *** get/set_name:

    def get_name(self):
        """Return the name of this component."""
        return self.__name

    def set_name(self, name):
        """Set the component name."""
        self.__name = name

# *** get/set_sensor:

    def get_sensors(self):
        """Return the list of sensors belonging to this component."""
        return self.__sensors

    def set_sensors(self, sensors):
        """Set the list of sensors belonging to this component."""
        self.__sensors = sensors

# ** Properties:

    id = property(get_id, set_id)
    name = property(get_name, set_name)
    sensors = property(get_sensors, set_sensors)


# * Sensor:
# ** Definitions:


class Sensor():
    """Class describing a sensor that is part of a component.

    Properties:
        id
        name
        interval: Measuring interval in seconds
    Public methods:
        get_measurands()
    """
    def __init__(self, sensor_id, sensor_name):
        self.__id = sensor_id
        self.__name = sensor_name
        self.__interval = None
        self.__measurands = []
        self.__i = 0
        self.__n = len(self.__measurands)

# ** Private methods:

    def __iter__(self):
        return iter(self.__measurands)

    def __str__(self):
        output = "SensorId: " + str(self.id) + "\n"
        output += "SensorName: " + self.name + "\n"
        output += "SensorInterval: " + str(self.interval) + "\n"
        output += "Measurands:\n"
        for measurand in self.measurands:
            output += str(measurand)
        return output

# ** Public methods:
# *** next(self):

    def next(self):
        """Iterate to the next measurand of this sensor."""
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__measurands[__i]
        self.__i = 0
        self.__n = len(self.__measurands)
        raise StopIteration()

# *** get/set_id():

    def get_id(self):
        """Return the Id of this sensor."""
        return self.__id

    def set_id(self, sensor_id):
        """Set the Id of this sensor."""
        self.__id = sensor_id

# *** get/set_name():

    def get_name(self):
        """Return the name of this sensor."""
        return self.__name

    def set_name(self, name):
        """Set the name of this sensor."""
        self.__name = name

# *** get/set_interval():

    def get_interval(self):
        """Return the measuring interval of this sensor."""
        return self.__interval

    def set_interval(self, interval):
        """Set the measuring interval of this sensor."""
        self.__interval = interval

# *** get/set_measurands():

    def get_measurands(self):
        """Return the list of measurands of this sensor."""
        return self.__measurands

    def set_measurands(self, measurands):
        """Set the list of measurands of this sensor."""
        self.__measurands = measurands

# ** Properties:

    id = property(get_id, set_id)
    name = property(get_name, set_name)
    interval = property(get_interval, set_interval)
    measurands = property(get_measurands, set_measurands)


# * Measurand:
# ** Definitions:
class Measurand():
    """Class providing a measurand that is delivered by a sensor.

    Properties:
        id
        name
        operator
        value
        unit
        source
        time
    """
    def __init__(self,
                 measurand_id,
                 measurand_name,
                 measurand_unit=None,
                 measurand_source=None):
        self.__id = measurand_id
        self.__name = measurand_name
        if measurand_unit is not None:
            self.__unit = measurand_unit
        else:
            self.__unit = ''
        if measurand_source is not None:
            self.__source = measurand_source
        else:
            self.__source = ''
        self.__value = None
        self.__time = None
        self.__operator = ''

# ** Private methods:

    def __str__(self):
        output = "MeasurandId: " + str(self.id) + "\n"
        output += "MeasurandName: " + self.name + "\n"
        if self.value is not None:
            output += "Value: " + self.operator + str(self.value) + ' ' + \
                      self.unit + "\n"
            output += "Time: " + str(self.time) + "\n"
        else:
            output += "MeasurandUnit: " + self.unit + "\n"
            output += "MeasurandSource: " + str(self.source) + "\n"
        return output

# ** Public methods:
# *** get/set_id:

    def get_id(self):
        """Return the Id of this measurand."""
        return self.__id

    def set_id(self, measurand_id):
        """Set the Id of this measurand."""
        self.__id = measurand_id

# *** get/set_name:

    def get_name(self):
        """Return the name of this measurand."""
        return self.__name

    def set_name(self, name):
        """Set the name of this measurand."""
        self.__name = name

# *** get/set_unit:

    def get_unit(self):
        """Return the physical unit of this measurand."""
        return self.__unit

    def set_unit(self, unit):
        """Set the physical unit of this measurand."""
        self.__unit = unit

# *** get/set_source:

    def get_source(self):
        """Return the source index belonging to this measurand.
        This index marks the position the measurand can be found in the
        list of recent values provided by the instrument
        as reply to the GetComponentResult or _gather_all_recent_values
        commands respectively."""
        return self.__source

    def set_source(self, source):
        """Set the source index."""
        self.__source = source

# *** get/set_operator:

    def get_operator(self):
        """Return the operator belonging to this measurand.
        Typical operators are '<', '>'"""
        return self.__operator

    def set_operator(self, operator):
        """Set the operator of this measurand."""
        self.__operator = operator

# *** get/set_value:

    def get_value(self):
        """Return the value of the measurand."""
        return self.__value

    def set_value(self, value):
        """Set the value of the measurand."""
        self.__value = value

# *** get/set_time:

    def get_time(self):
        """Return the aquisition time (timestamp) of the measurand."""
        return self.__time

    def set_time(self, time_stamp):
        """Set the aquisition time (timestamp) of the measurand."""
        self.__time = time_stamp

# ** Properties:

    id = property(get_id, set_id)
    name = property(get_name, set_name)
    unit = property(get_unit, set_unit)
    source = property(get_source, set_source)
    operator = property(get_operator, set_operator)
    value = property(get_value, set_value)
    time = property(get_time, set_time)


# * Test environment:
if __name__ == '__main__':

    mycluster = SaradCluster()
    mycluster.update_connected_instruments()
    for connected_instrument in mycluster:
        print(connected_instrument)

    # Example access on first device
    if len(mycluster.connected_instruments) > 0:
        ts = mycluster.next()
        ts.signal = ts.Signal.off
        ts.pump_mode = ts.Pump_mode.continuous
        ts.radon_mode = ts.Radon_mode.fast
        ts.units = ts.Units.si
        ts.chamber_size = ts.Chamber_size.xl
