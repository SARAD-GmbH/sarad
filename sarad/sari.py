"""Abstract class for all SARAD instruments

SaradInst comprises all attributes and methods
that all SARAD instruments have in common.
"""

import time
import struct
import os
from enum import Enum
import logging
import yaml
from BitVector import BitVector  # type: ignore
import serial  # type: ignore

logger = logging.getLogger(__name__)


# * SaradInst:
# ** Definitions:
class SaradInst():
    """Basic class for the serial communication protocol of SARAD instruments

    Class attributes:
        products
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

    version = '0.1'

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

    with open(os.path.dirname(os.path.realpath(__file__)) +
              os.path.sep + 'instruments.yaml', 'r') as __f:
        products = yaml.safe_load(__f)

# ** Private methods:

# *** __init__():

    def __init__(self, port=None, family=None):
        self.__port = port
        self.__family = family
        if (port is not None) and (family is not None):
            self._initialize()
        self.__components = []
        self.__interval = None
        self._type_id = None
        self._type_name = None
        self._software_version = None
        self._serial_number = None
        self.signal = None
        self.radon_mode = None
        self.pump_mode = None
        self.units = None
        self.chamber_size = None
        self.__id = None

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
        return {"is_valid": is_valid,
                "is_control": is_control,
                "payload": payload,
                "number_of_bytes_in_payload": number_of_bytes_in_payload}

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
        return {"is_valid": checked_answer['is_valid'],
                "is_control": checked_answer['is_control'],
                "payload": checked_answer['payload'],
                "number_of_bytes_in_payload": checked_answer[
                    'number_of_bytes_in_payload']}

# *** __str__(self):

    def __str__(self):
        output = (f"Id: {self.device_id}\n"
                  f"SerialDevice: {self.port}\n"
                  f"Baudrate: {self.family['baudrate']}\n"
                  f"FamilyName: {self.family['family_name']}\n"
                  f"FamilyId: {self.family['family_id']}\n"
                  f"TypName: {self.type_name}\n"
                  f"TypeId: {self.type_id}\n"
                  f"SoftwareVersion: {self.software_version}\n"
                  f"SerialNumber: {self.serial_number}\n")
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
        logger.debug('Get description failed.')
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
        output = {}
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


# * Component:
# ** Definitions:
class Component():
    """Class describing a sensor or actor component built into an instrument"""

    version = '0.1'

    def __init__(self, component_id, component_name):
        self.__id = component_id
        self.__name = component_name
        self.__sensors = []

# ** Private methods:

    def __iter__(self):
        return iter(self.__sensors)

    def __str__(self):
        output = (f"ComponentId: {self.id}\n"
                  f"ComponentName: {self.name}\nSensors:\n")
        for sensor in self.sensors:
            output += f"{sensor}\n"
        return output

# ** Public methods:
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
        get_measurands()"""

    version = '0.1'

    def __init__(self, sensor_id, sensor_name):
        self.__id = sensor_id
        self.__name = sensor_name
        self.__interval = None
        self.__measurands = []

# ** Private methods:

    def __iter__(self):
        return iter(self.__measurands)

    def __str__(self):
        output = (f"SensorId: {self.id}\nSensorName: {self.name}\n"
                  f"SensorInterval: {self.interval}\nMeasurands:\n")
        for measurand in self.measurands:
            output += f"{measurand}\n"
        return output

# ** Public methods:
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
        gps"""

    version = '0.1'

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
        self.__gps = ''

# ** Private methods:

    def __str__(self):
        output = f"MeasurandId: {self.id}\nMeasurandName: {self.name}\n"
        if self.value is not None:
            output += f"Value: {self.operator} {self.value} {self.unit}\n"
            output += f"Time: {self.time}\n"
            output += f"GPS: {self.gps}\n"
        else:
            output += f"MeasurandUnit: {self.unit}\n"
            output += f"MeasurandSource: {self.source}\n"
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

# *** get/set_gps:

    def get_gps(self):
        """Return the GPS string of the measurand."""
        return self.__gps

    def set_gps(self, gps):
        """Set the GPS string of the measurand."""
        self.__gps = gps


# ** Properties:

    id = property(get_id, set_id)
    name = property(get_name, set_name)
    unit = property(get_unit, set_unit)
    source = property(get_source, set_source)
    operator = property(get_operator, set_operator)
    value = property(get_value, set_value)
    time = property(get_time, set_time)
    gps = property(get_gps, set_gps)
