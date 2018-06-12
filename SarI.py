"""Collection of classes to communicate with SARAD instruments about (virtual)
serial interfaces."""

import serial
import serial.tools.list_ports
import time
from datetime import datetime
from datetime import timedelta
import struct
import hashids
import yaml
import logging

class SaradInst(object):
    """Basic class for the serial communication protocol of SARAD instruments

    Properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        id: Identifier for an individual instrument in a cluster
        type_id: Together with family, this Id identifys the instrument type.
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

    def __init__(self, port = None, family = None):
        self.__port = port
        self.__family = family
        if (port is not None) and (family is not None):
            self.__description = self.__get_description()
            self._build_component_list()
        self.__components = []
        self.__i = 0
        self.__n = len(self.__components)

    def __iter__(self):
        return iter(self.__components)

    def next(self):
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__components[__i]
        else:
            self.__i = 0
            self.__n = len(self.__components)
            raise StopIteration()

    # Helper functions to be used here and in derived classes
    def _bytes_to_float(self, value_bytes):
        """Convert 4 bytes (little endian) from serial interface into floating point nummber according to IEEE 754"""
        byte_array = bytearray(value_bytes)
        byte_array.reverse()
        return struct.unpack('<f', bytes(byte_array))[0]

    def _parse_value_string(self, value_string):
        """Take a string containing a physical value with operator, value and unit and decompose it into its parts for further mathematical processing."""
        output = dict()
        r = value_string        # just an abbreviation for the following
        if r == 'No valid data!':
            output['measurand_operator'] = ''
            output['measurand_value'] = ''
            output['measurand_unit'] = ''
        else:
            try:
                if ('<' in r)  or ('>' in r):
                    output['measurand_operator'] = r[0]
                    r1 = r[1:]
                else:
                    output['measurand_operator'] = ''
                    r1 = r
                output['measurand_value'] = float(r1.split()[0])
                try:
                    output['measurand_unit'] = r1.split()[1]
                except:
                    output['measurand_unit'] = ''
            except:
                output['measurand_operator'] = ''
                output['measurand_value'] = ''
                output['measurand_unit'] = ''
        return output

    def _build_component_list(self):
        """Will be overriden by derived classes."""
        pass

    # Private methods
    def __make_command_msg(self, cmd_data):
        # Encode the message to be sent to the SARAD instrument.
        # Arguments are the one byte long command and the data bytes to be sent.
        cmd = cmd_data[0]
        data = cmd_data[1]
        payload = cmd + data
        control_byte = len(payload) - 1
        if cmd:          # Control message
            control_byte = control_byte | 0x80 # set Bit 7
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

    def __check_answer(self, answer):
        # Returns a dictionary of:
        #     is_valid: True if answer is valid, False otherwise
        #     is_control_message: True if control message
        #     payload: Payload of answer
        #     number_of_bytes_in_payload
        if answer.startswith(b'B') & answer.endswith(b'E'):
            control_byte = answer[1]
            neg_control_byte = answer[2]
            if (control_byte ^ 0xff) == neg_control_byte:
                control_byte_ok = True
            number_of_bytes_in_payload = (control_byte & 0x7f) + 1
            if control_byte & 0x80:
                is_control = True
            else:
                is_control = False
            status_byte = answer[3]
            payload = answer[3:3+number_of_bytes_in_payload]
            calculated_checksum = 0
            for byte in payload:
                calculated_checksum = calculated_checksum + byte
            received_checksum_bytes = answer[3 + number_of_bytes_in_payload:5 +
                                             number_of_bytes_in_payload]
            received_checksum = int.from_bytes(received_checksum_bytes,
                                               byteorder='little', signed=False)
            if received_checksum == calculated_checksum:
                checksum_ok = True
            is_valid = control_byte_ok & checksum_ok
        else:
            is_valid = False
        if not is_valid:
            is_control = False
            payload = b''
            number_of_bytes_in_payload = 0
        return dict(is_valid = is_valid,
                    is_control = is_control,
                    payload = payload,
                    number_of_bytes_in_payload = number_of_bytes_in_payload)

    def __get_message_payload(self, serial_port, baudrate, parity, write_sleeptime, wait_for_reply, message, expected_length_of_reply):
        """ Returns a dictionary of:
        is_valid: True if answer is valid, False otherwise
        is_control_message: True if control message
        payload: Payload of answer
        number_of_bytes_in_payload"""
        ser = serial.Serial(serial_port, baudrate, \
                            timeout=1, parity=parity, \
                            stopbits=serial.STOPBITS_ONE)
        for element in message:
            byte = (element).to_bytes(1,'big')
            ser.write(byte)
            time.sleep(write_sleeptime)
        time.sleep(wait_for_reply)
        answer = ser.read(expected_length_of_reply)
        ser.close()
        checked_answer = self.__check_answer(answer)
        return dict(is_valid = checked_answer['is_valid'],
                    is_control = checked_answer['is_control'],
                    payload = checked_answer['payload'],
                    number_of_bytes_in_payload = checked_answer['number_of_bytes_in_payload'])

    def __get_description(self):
        """Returns a dictionary with instrument type, software version,\
 and serial number."""
        baudrate = self.__family['baudrate']
        parity = self.__family['parity']
        write_sleeptime = self.__family['write_sleeptime']
        wait_for_reply = self.__family['wait_for_reply']
        get_version_msg = self.__make_command_msg(self.family['get_id_cmd'])
        length_of_reply = self.__family['length_of_reply']
        checked_payload = self.__get_message_payload(self.__port,\
                                                     baudrate,\
                                                     parity,\
                                                     write_sleeptime,\
                                                     wait_for_reply,\
                                                     get_version_msg,\
                                                     length_of_reply)
        if checked_payload['is_valid']:
            try:
                payload = checked_payload['payload']
                type_id = payload[1]
                software_version = payload[2]
                if self.__family['family_id'] == 5:  # DACM has big endian order of bytes
                    serial_number = int.from_bytes(payload[3:5], \
                                                   byteorder='big', \
                                                   signed=False)
                else:
                    serial_number = int.from_bytes(payload[3:5], \
                                                   byteorder='little', \
                                                   signed=False)
                return dict(type_id = type_id,
                            software_version = software_version,
                            serial_number = serial_number)
            except:
                logging.error("Error parsing the payload.")
        else:
            return False

    # Public methods
    def get_reply(self, cmd_data, reply_length = 50):
        """Returns a bytestring of the payload of the instruments reply \
to the provided list of 1-byte command and data bytes."""
        msg = self.__make_command_msg(cmd_data)
        checked_payload = self.__get_message_payload(self.__port,\
                                        self.__family['baudrate'],\
                                        self.__family['parity'],\
                                        self.__family['write_sleeptime'],\
                                        self.__family['wait_for_reply'],\
                                        msg,\
                                        reply_length)
        if checked_payload['is_valid']:
            return checked_payload['payload']
        else:
            return False

    def get_port(self):
        return self.__port
    def set_port(self, port):
        self.__port = port
        if (self.port is not None) and (self.family is not None):
            self.__description = self.__get_description()
            self._build_component_list()
    port = property(get_port, set_port)

    def get_id(self):
        return self.__id
    def set_id(self, id):
        self.__id = id
    id = property(get_id, set_id)

    def get_family(self):
        return self.__family
    def set_family(self, family):
        self.__family = family
        if (self.port is not None) and (self.family is not None):
            self.__description = self.__get_description()
            self._build_component_list()
    family = property(get_family, set_family)

    def get_type_id(self):
        if self.__description:
            return self.__description['type_id']
    type_id = property(get_type_id)

    def get_software_version(self):
        if self.__description:
            return self.__description['software_version']
    software_version = property(get_software_version)

    def get_serial_number(self):
        if self.__description:
            return self.__description['serial_number']
    serial_number = property(get_serial_number)

    def get_components(self):
        return self.__components
    def set_components(self, components):
        self.__components = components
    components = property(get_components, set_components)

    def __str__(self):
        output = "Id: " + str(self.id) + "\n"
        output += "SerialDevice: " + self.port + "\n"
        output += "Baudrate: " + str(self.family['baudrate']) + "\n"
        output += "FamilyName: " + str(self.family['family_name']) + "\n"
        output += "FamilyId: " + str(self.family['family_id']) + "\n"
        for type_in_family in self.family['types']:
            if type_in_family['type_id'] == self.type_id:
                type_name = type_in_family['type_name']
                output += "TypName: " + type_name + "\n"
        output += "TypeId: " + str(self.type_id) + "\n"
        output += "SoftwareVersion: " + str(self.software_version) + "\n"
        output += "SerialNumber: " + str(self.serial_number) + "\n"
        return output

class DosemanInst(SaradInst):
    """Instrument with Doseman communication protocol

    Inherited properties:
        port
        id
        family
        type_id
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

    def __init__(self, port = None, family = None):
        if family is None:
            family = SaradCluster.products[0]
        SaradInst.__init__(self, port, family)

class RscInst(SaradInst):
    """Instrument with Radon Scout communication protocol

    Inherited properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        id: Identifier for an individual instrument in a cluster
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
        get_all_recent_values()
        get_recent_value(index)"""

    def _get_parameter(self, parameter_name):
        for inst_type in self.family['types']:
            if inst_type['type_id'] == self.type_id:
                try:
                    return inst_type[parameter_name]
                except:
                    pass
        try:
            return self.family[parameter_name]
        except:
            return False

    def _build_component_list(self):
        for component_object in self.components:
            del component_object
        self.components = []
        component_dict = self._get_parameter('components')
        if not component_dict:
            return False
        for component in component_dict:
            component_object = Component(component['component_id'], \
                                         component['component_name'])
            # build sensor list
            for sensor in component['sensors']:
                sensor_object = Sensor(sensor['sensor_id'], \
                                       sensor['sensor_name'])
                # build measurand list
                for measurand in sensor['measurands']:
                    try:
                        unit = measurand['measurand_unit']
                    except:
                        unit = ''
                    try:
                        source = measurand['measurand_source']
                    except:
                        source = None
                    measurand_object = Measurand(measurand['measurand_id'], \
                                                 measurand['measurand_name'], \
                                                 unit, \
                                                 source)
                    sensor_object.measurands += [measurand_object]
                component_object.sensors += [sensor_object]
            self.components += [component_object]
        return len(self.components)

    def __init__(self, port = None, family = None):
        if family is None:
            family = SaradCluster.products[1]
        SaradInst.__init__(self, port, family)

    def get_all_recent_values(self):
        """Fill the component objects with recent readings."""
        reply = self.get_reply([b'\x14', b''], 39)
        if reply and (reply[0] == 10):
            try:
                sample_interval = timedelta(seconds = reply[1])
                device_time_min = reply[2]
                device_time_h = reply[3]
                device_time_d = reply[4]
                device_time_m = reply[5]
                device_time_y = reply[6]
                source = []
                source.append(round(self._bytes_to_float(reply[7:11]), 2))  # 0
                source.append(reply[11])                                    # 1
                source.append(round(self._bytes_to_float(reply[12:16]), 2))  # 2
                source.append(reply[16])                                    # 3
                source.append(round(self._bytes_to_float(reply[17:21]), 2))  # 4
                source.append(round(self._bytes_to_float(reply[21:25]), 2))  # 5
                source.append(round(self._bytes_to_float(reply[25:29]), 2))  # 6
                source.append(int.from_bytes(reply[29:33], \
                                             byteorder='big', signed=False))  # 7
                source.append(self._get_battery_voltage())                  # 8
                device_time = datetime(device_time_y + 2000, device_time_m, \
                                       device_time_d, device_time_h, \
                                       device_time_min)
            except:
                logging.error("Error parsing the payload.")
                return False
            for component in self.components:
                for sensor in component.sensors:
                    sensor.interval = sample_interval
                    for measurand in sensor.measurands:
                        try:
                            measurand.value = source[measurand.source]
                            measurand.time = device_time
                        except:
                            logging.error("Can't get value for source " + \
                                          str(measurand.source) + " in " + \
                                          component.name + '/' + \
                                          sensor.name + '/' + \
                                          measurand.name + '.')
            return True
        else:
            logging.error("The instrument doesn't reply.")
            return False

    def get_recent_value(self, component_id = None, sensor_id = None, \
                         measurand_id = None):
        """Fill component objects with recent measuring values.  This function does the same like get_all_recent_values() and is only here to provide a compatible API to the DACM interface"""
        return self.get_all_recent_values()

    def _get_battery_voltage(self):
        battery_bytes = self._get_parameter('battery_bytes')
        battery_coeff = self._get_parameter('battery_coeff')
        if not (battery_coeff and battery_bytes):
            return "This instrument type doesn't provide \
            battery voltage information"
        reply = self.get_reply([b'\x0d', b''], battery_bytes + 7)
        if reply and (reply[0] == 10):
            try:
                voltage = battery_coeff * int.from_bytes(reply[1:], byteorder='little', signed=False)
                return round(voltage, 2)
            except ParsingError:
                logging.error("Error parsing the payload.")
                return None
        else:
            logging.error("The instrument doesn't reply.")
            return None

class DacmInst(SaradInst):
    """Instrument with DACM communication protocol

    Inherited properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        id: Identifier for an individual instrument in a cluster
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
        get_recent_values()
        get_recent_value(index)"""
    __measurand_names = ['recent sampling', \
                    'average of last completed interval', \
                    'minimum of last completed interval', \
                    'maximum of last completed interval']
    def __init__(self, port = None, family = None):
        if family is None:
            family = SaradCluster.products[2]
        SaradInst.__init__(self, port, family)

    def get_all_recent_values(self):
        """Get a list of dictionaries with recent measuring values."""
        list_of_outputs = []
        sensor_id = 0        # fixed value, reserved for future use
        for component_id in range(34):
            for measurand_id in range(4):
                output = self.get_recent_value(component_id, sensor_id, measurand_id)
                list_of_outputs.append(output)
        return list_of_outputs

    def get_recent_value(self, component_id, sensor_id = 0, measurand_id = 0):
        """Get a dictionaries with recent measuring values from one sensor.
        component_id: one of the 34 sensor/actor modules of the DACM system
        measurand_id: 0 = recent sampling, 1 = average of last completed interval,
        2 = minimum of last completed interval, 3 = maximum
        sensor_id: only for sensors delivering multiple measurands"""
        reply = self.get_reply([b'\x1a', bytes([component_id]) + \
                                bytes([sensor_id]) + \
                                bytes([measurand_id])], 1000)
        if reply and (reply[0] > 0):
            output = dict()
            output['component_name'] = reply[1:17].split(b'\x00')[0].decode("ascii")
            output['measurand_id'] = measurand_id
            output['sensor_name'] = reply[18:34].split(b'\x00')[0].decode("ascii")
            output['measurand'] = reply[35:51].split(b'\x00')[0].strip().decode("ascii")
            r = self._parse_value_string(output['measurand'])
            output['measurand_operator'] = r['measurand_operator']
            output['value'] = r['measurand_value']
            output['measurand_unit'] = r['measurand_unit']
            date = reply[52:68].split(b'\x00')[0].split(b'/')
            time = reply[69:85].split(b'\x00')[0].split(b':')
            if date != [b'']:
                output['datetime'] = datetime(int(date[2]), int(date[0]),\
                                              int(date[1]),\
                                              int(time[0]), int(time[1]),\
                                              int(time[2]))
            else:
                output['datetime'] = None
            output['gps'] = reply[86:].split(b'\x00')[0].decode("ascii")
            return output
        elif reply[0] == 0:
            logging.error("Measurand not available.")
            return False
        else:
            logging.error("The instrument doesn't reply.")
            return False

class SaradCluster(object):
    """Class to define a cluster of SARAD instruments connected to one controller
    Class attributes:
        products
    Properties:
        native_ports
        active_ports
        connected_instruments
    Public methods:
        set_native_ports()
        get_native_ports()
        get_active_ports()
        get_connected_instruments()
        update_connected_instruments()
        next()
    """

    with open('instruments.yaml', 'r') as __f:
        products = yaml.load(__f)

    def __init__(self, native_ports=None):
        if native_ports is None:
            native_ports = []
        self.__native_ports = native_ports
        self.__connected_instruments = self.update_connected_instruments()
        self.__i = 0
        self.__n = len(self.__connected_instruments)

    def __iter__(self):
        return iter(self.__connected_instruments)

    def next(self):
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__connected_instruments[__i]
        else:
            self.__i = 0
            self.__n = len(self.__connected_instruments)
            raise StopIteration()

    def set_native_ports(self, native_ports):
        self.__native_ports = native_ports

    def get_native_ports(self):
        return self.__native_ports

    def get_active_ports(self):
        """SARAD instruments can be connected:
        1. by RS232 on a native RS232 interface at the computer
        2. via their built in FT232R USB-serial converter
        3. via an external USB-serial converter (Prolific, Prolific fake or FTDI)
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

    def update_connected_instruments(self):
        hid = hashids.Hashids()
        ports_to_test = self.active_ports
        logging.info(str(len(ports_to_test)) + ' ports to test')
        # We check every active port and try for a connected SARAD instrument.
        connected_instruments = []  # a list of instrument objects
        # NOTE: The order of tests is very important, because the only
        # difference between RadonScout and DACM GetId commands is the
        # length of reply. Since the reply for DACM is longer than that for
        # RadonScout, the test for RadonScout has always to be made before
        # that for DACM.
        for family in SaradCluster.products:
            if family['family_id'] == 1:
                family_class = DosemanInst
            elif family['family_id'] == 2:
                family_class = RscInst
            elif family['family_id'] == 5:
                family_class = DacmInst
            else:
                break
            test_instrument = family_class()
            test_instrument.family = family
            ports_with_instruments = []
            logging.info(ports_to_test)
            for port in ports_to_test:
                logging.info('Testing port ' + port + ' for ' + \
                             family['family_name'])
                test_instrument.port = port
                if test_instrument.type_id and \
                   test_instrument.serial_number:
                    id = hid.encode(test_instrument.family['family_id'],\
                                    test_instrument.type_id,\
                                    test_instrument.serial_number)
                    test_instrument.set_id(id)
                    logging.info(family['family_name'] + ' found on port ' + port)
                    connected_instruments.append(test_instrument)
                    ports_with_instruments.append(port)
                    if (ports_to_test.index(port) + 1) < len(ports_to_test):
                        test_instrument = family_class()
                        test_instrument.family = family
            for port in ports_with_instruments:
                ports_to_test.remove(port)
        return connected_instruments

    def get_connected_instruments(self):
        return self.__connected_instruments

    native_ports = property(get_native_ports, set_native_ports)
    active_ports = property(get_active_ports)
    connected_instruments = property(get_connected_instruments)

class Component(object):
    """Class describing a sensor or actor component built into an instrument"""
    def __init__(self, component_id, component_name):
        self.__id = component_id
        self.__name = component_name
        self.__sensors = []
        self.__i = 0
        self.__n = len(self.__sensors)

    def __iter__(self):
        return iter(self.__sensors)

    def __str__(self):
        output = "ComponentId: " + str(self.id) + "\n"
        output += "ComponentName: " + self.name + "\n"
        output += "Sensors:\n"
        for sensor in self.sensors:
            output += str(sensor)
        return output

    def next(self):
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__sensors[__i]
        else:
            self.__i = 0
            self.__n = len(self.__sensors)
            raise StopIteration()

    def get_id(self):
        return self.__id
    def set_id(self, id):
        self.__id = id
    id = property(get_id, set_id)

    def get_name(self):
        return self.__name
    def set_name(self, name):
        self.__name = name
    name = property(get_name, set_name)

    def get_sensors(self):
        return self.__sensors
    def set_sensors(self, sensors):
        self.__sensors = sensors
    sensors = property(get_sensors, set_sensors)

class Sensor(object):
    def __init__(self, sensor_id, sensor_name):
        self.__id = sensor_id
        self.__name = sensor_name
        self.__interval = None
        self.__measurands = []
        self.__i = 0
        self.__n = len(self.__measurands)

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

    def next(self):
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__measurands[__i]
        else:
            self.__i = 0
            self.__n = len(self.__measurands)
            raise StopIteration()

    def get_id(self):
        return self.__id
    def set_id(self, id):
        self.__id = id
    id = property(get_id, set_id)

    def get_name(self):
        return self.__name
    def set_name(self, name):
        self.__name = name
    name = property(get_name, set_name)

    def get_interval(self):
        return self.__interval
    def set_interval(self, interval):
        self.__interval = interval
    interval = property(get_interval, set_interval)

    def get_measurands(self):
        return self.__measurands
    def set_measurands(self, measurands):
        self.__measurands = measurands
    measurands = property(get_measurands, set_measurands)

class Measurand(object):
    def __init__(self, measurand_id, measurand_name, \
                 measurand_unit = None, measurand_source = None):
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

    def get_id(self):
        return self.__id
    def set_id(self, id):
        self.__id = id
    id = property(get_id, set_id)

    def get_name(self):
        return self.__name
    def set_name(self, name):
        self.__name = name
    name = property(get_name, set_name)

    def get_unit(self):
        return self.__unit
    def set_unit(self, unit):
        self.__unit = unit
    unit = property(get_unit, set_unit)

    def get_source(self):
        return self.__source
    def set_source(self, source):
        self.__source = source
    source = property(get_source, set_source)

    def get_operator(self):
        return self.__operator
    def set_operator(self, operator):
        self.__operator = operator
    operator = property(get_operator, set_operator)

    def get_value(self):
        return self.__value
    def set_value(self, value):
        self.__value = value
    value = property(get_value, set_value)

    def get_time(self):
        return self.__time
    def set_time(self, time):
        self.__time = time
    time = property(get_time, set_time)

# Test environment
if __name__=='__main__':
    logging.basicConfig(level=logging.DEBUG)

    mycluster = SaradCluster()
    for connected_instrument in mycluster:
        print(connected_instrument)
