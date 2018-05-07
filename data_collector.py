#!/usr/bin/python

"""
* Naming convention
- Instrument :: a SARAD product with serial interface and at least one Sensor and
                maybe one or more Actors
- Component :: Sensor or Actor built into an Instrument
- Sensor :: Component delivering a Measurand (Messgröße)
- Actor :: Component receiving a parameter and doing something with the Instrument
- Measurand :: Value, Operator and Unit delivered by a Sensor
- Operator :: mathematical operator used on a measurand (e.g. '<', '+-')
- Cluster :: one or more Instruments connected with one Controller via one or more
             serial interfaces
             (RS232, RS485, USB, Zigbee connected to USB or RS232)
"""

import serial
import serial.tools.list_ports
import time
from datetime import datetime
import struct

class SaradInst(object):
    """Basic class for the serial communication protocol of SARAD instruments

    Properties:
        port: String containing the serial communication port
        family: Device family of the instrument expected to be at this port
        instrument_description: Dictionary with instrument type, software version,
                            and device number, components, measurands and items.
    Public methods:
        get_instrument_description(),
        set_instrument_description(),
        get_family(),
        set_family(),
        get_port(),
        set_port(),
        get_reply()"""

    __instrument_description = dict()

    def __init__(self, port, family):
        self.__port = port
        self.__family = family

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
            output['result_operator'] = ''
            output['result_value'] = ''
            output['result_unit'] = ''
        else:
            if ('<' in r)  or ('>' in r):
                output['result_operator'] = r[0]
                r1 = r[1:]
            else:
                output['result_operator'] = ''
                r1 = r
            output['result_value'] = float(r1.split()[0])
            try:
                output['result_unit'] = r1.split()[1]
            except:
                output['result_unit'] = ''
        return output


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


    # Public methods
    def get_instrument_description(self):
        """Returns a dictionary with instrument type, software version,\
 and device number."""
        baudrate = self.__family['baudrate']
        parity = self.__family['parity']
        write_sleeptime = self.__family['write_sleeptime']
        wait_for_reply = self.__family['wait_for_reply']
        get_version_msg = self.__make_command_msg(self.__family['get_id_cmd'])
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
                if self.__family['id'] == 5:  # DACM has big endian order of bytes
                    device_number = int.from_bytes(payload[3:5], \
                                                   byteorder='big', \
                                                   signed=False)
                else:
                    device_number = int.from_bytes(payload[3:5], \
                                                   byteorder='little', \
                                                   signed=False)
                for type_in_family in self.__family['types']:
                    if type_in_family['id'] == type_id:
                        type_name = type_in_family['name']
                return dict(type_name = type_name,
                            type_id = type_id,
                            software_version = software_version,
                            device_number = device_number)
            except:
                print("Error parsing the payload.")
        else:
            return False

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

    def get_family(self):
        return self.__family

    def set_family(self, family):
        self.__family = family

    port = property(get_port, set_port)
    family = property(get_family, set_family)
    instrument_description = property(get_instrument_description)

class DacmInst(SaradInst):
    """Instrument with DACM communication protocol

    Inherited properties:
        port
        family
        instrument_description
    Public methods:
        get_recent_values()
        get_recent_value(index)"""
    __item_names = ['recent sampling', \
                    'average of last completed interval', \
                    'minimum of last completed interval', \
                    'maximum of last completed interval']
    def __init__(self, port, family = None):
        if family is None:
            family = SaradCluster.f_dacm
        SaradInst.__init__(self, port, family)

    def get_all_recent_values(self):
        """Get a list of dictionaries with recent measuring values."""
        list_of_outputs = []
        measurand_id = 0        # fixed value, reserved for future use
        for component_id in range(34):
            for item_id in range(4):
                output = self.get_recent_value(component_id, measurand_id, item_id)
                list_of_outputs.append(output)
        return list_of_outputs

    def get_recent_value(self, component_id, measurand_id = 0, item_id = 0):
        """Get a dictionaries with recent measuring values from one sensor.
        component_id: one of the 34 sensors/actors of the DACM system
        item_id: 0 = recent sampling, 1 = average of last completed interval,
        2 = minimum of last completed interval, 3 = maximum
        measurand_id: only for sensors delivering multiple results"""
        reply = self.get_reply([b'\x1a', bytes([component_id]) + \
                                bytes([measurand_id]) + \
                                bytes([item_id])], 1000)
        output = dict()
        output['component_name'] = reply[1:17].split(b'\x00')[0].decode("ascii")
        output['item_id'] = item_id
        output['value_name'] = reply[18:34].split(b'\x00')[0].decode("ascii")
        output['result'] = reply[35:51].split(b'\x00')[0].strip().decode("ascii")
        r = self._parse_value_string(output['result'])
        output['result_operator'] = r['result_operator']
        output['result_value'] = r['result_value']
        output['result_unit'] = r['result_unit']
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

class RscInst(SaradInst):
    """Instrument with Radon Scout communication protocol

    Inherited properties:
        instrument_description
    Public methods:
        get_all_recent_values()
        get_recent_value(index)"""

    __component_names = ['radon', 'thoron', 'temperature', 'humidity', \
                         'pressure', 'tilt']
    __item_names = ['measuring value', 'error']

    def __init__(self, port, family = None):
        if family is None:
            family = SaradCluster.f_radonscout
        SaradInst.__init__(self, port, family)

    def get_all_recent_values(self):
        reply = self.get_reply([b'\x14', b''], 39)
        if reply:
            try:
                sample_interval = reply[1]
                device_time_min = reply[2]
                device_time_h = reply[3]
                device_time_d = reply[4]
                device_time_m = reply[5]
                device_time_y = reply[6]
                radon = self._bytes_to_float(reply[7:11])
                radon_error = reply[11]
                thoron = self._bytes_to_float(reply[12:16])
                thoron_error = reply[16]
                temperature = self._bytes_to_float(reply[17:21])
                humidity = self._bytes_to_float(reply[21:25])
                pressure = self._bytes_to_float(reply[25:29])
                tilt = int.from_bytes(reply[29:], byteorder='little', signed=False)
                device_time = datetime(device_time_y + 2000, device_time_m,
                                       device_time_d, device_time_h, device_time_min)
            except:
                print("Error parsing the payload.")
                return False
            return [dict(sample_interval = sample_interval,
                         datetime = device_time,
                         item_id = 0,
                         component_name = self.__component_names[0],
                         result_value = radon,
                         result_unit = 'Bq/m³'
                         error = radon_error,
                         error_unit = '%'),
                    dict(sample_interval = sample_interval,
                         datetime = device_time,
                         item_id = 0,
                         component_name = self.__component_names[1],
                         result_value = thoron,
                         error = thoron_error),
                    dict(sample_interval = sample_interval,
                         datetime = device_time,
                         item_id = 0,
                         component_name = self.__component_names[2],
                         result_value = temperature),
                    dict(sample_interval = sample_interval,
                         datetime = device_time,
                         item_id = 0,
                         component_name = self.__component_names[3],
                         result_value = humidity),
                    dict(sample_interval = sample_interval,
                         datetime = device_time,
                         item_id = 0,
                         component_name = self.__component_names[4],
                         result_value = pressure),
                    dict(sample_interval = sample_interval,
                         datetime = device_time,
                         item_id = 0,
                         component_name = self.__component_names[5],
                         result_value = tilt)]
        else:
            print("The instrument doesn't reply.")
            return False

    def get_recent_value(self, component_id, item_id = 0, measurand_id = 0):
        """Get a dictionaries with recent measuring values from one sensor."""
        return self.get_all_recent_values()[component_id]

    def get_battery_voltage(self, serial_port):
        get_battery_msg = b'\x42\x80\x7f\x0d\x0d\x00\x45'
        reply_length_battery_msg = 39
        checked_payload = get_message_payload(serial_port, get_battery_msg, reply_length_battery_msg)
        if checked_payload['is_valid']:
            try:
                payload = checked_payload['payload']
                voltage = 0.00323 * int.from_bytes(payload[1:], byteorder='little', signed=False)
                print(voltage)
            except ParsingError:
                print("Error parsing the payload.")
        else:
            print("The instrument doesn't reply.")

class SaradCluster(object):
    """Class to define a cluster of SARAD instruments connected to one controller

    Public attributes:
        t_<product>
        f_<product family>
    Properties:
        native_ports
        products
    Public methods:
        set_native_ports()
        get_native_ports()
        set_products()
        get_products()
        get_connected_instruments()
    """

    # DOSEman device types
    t_doseman = dict(name = 'DOSEman', id = 1)
    t_dosemanpro = dict(name = 'DOSEman Pro', id = 2)
    t_myriam = dict(name = 'MyRIAM', id = 3)
    t_dm_rtm1688 = dict(name = 'RTM 1688', id = 4)
    t_radonsensor = dict(name = 'Analog Radon Sensor', id = 5)
    t_progenysensor = dict(name='Analog Progeny Sensor', id = 6)

    # Radon Scout device types
    t_radonscout1 = dict(name = 'Radon Scout 1', id = 1)
    t_radonscout2 = dict(name = 'Radon Scout 2', id = 2)
    t_radonscoutplus = dict(name = 'Radon Scout Plus', id = 3)
    t_rtm1688 = dict(name = 'RTM 1688', id = 4)
    t_radonscoutpmt = dict(name = 'Radon Scout PMT', id = 5)
    t_thoronscout = dict(name='Thoron Scout', id = 6)
    t_radonscouthome = dict(name = 'Radon Scout Home', id = 7)
    t_radonscouthomep = dict(name = 'Radon Scout Home - P', id = 8)
    t_radonscouthomeco2 = dict(name = 'Radon Scout Home - CO2', id = 9)
    t_rtm1688geo = dict(name = 'RTM 1688 Geo', id = 10)

    # DACM device types
    t_rtm2200 = dict(name = 'RTM 2200', id = 2)

    # Network interface types
    t_zigbee = dict(name = 'ZigBee adapter', id = 200)
    __network_types = [t_zigbee]

    # Device families
    f_doseman = dict(name = 'Doseman family', id = 1, baudrate = 115200, \
                     parity = serial.PARITY_EVEN, write_sleeptime = 0.001, \
                     wait_for_reply = 0.1, \
                     get_id_cmd = [b'\x40', b''], \
                     length_of_reply = 11, \
                     types = [t_doseman, \
                              t_dosemanpro, t_myriam, t_dm_rtm1688,\
                              t_radonsensor, t_progenysensor])
    f_radonscout = dict(name = 'Radon Scout family', id = 2, baudrate = 9600, \
                        parity = serial.PARITY_NONE, write_sleeptime = 0, \
                        wait_for_reply = 0, \
                        get_id_cmd = [b'\x0c', b'\xff\x00\x00'], \
                        length_of_reply = 19, \
                        types = [t_radonscout1, t_radonscout2,\
                                 t_radonscoutplus, t_rtm1688,\
                                 t_radonscoutpmt, t_thoronscout,\
                                 t_radonscouthome, t_radonscouthomep,\
                                 t_radonscouthomeco2, t_rtm1688geo])
    f_dacm = dict(name = 'DACM family', id = 5, baudrate = 9600, \
                  parity = serial.PARITY_NONE, write_sleeptime = 0, \
                  wait_for_reply = 0, \
                  get_id_cmd = [b'\x0c', b'\xff\x00\x00'], \
                  length_of_reply = 50, \
                  types = [t_rtm2200])

    def __init__(self, native_ports=None, products=None):
        if native_ports is None:
            native_ports = []
        self.__native_ports = native_ports
        if products is None:
            products = [self.f_doseman, self.f_radonscout, self.f_dacm]
        self.__products = products

    def set_native_ports(self, native_ports):
        self.__native_ports = native_ports

    def set_products(self, products):
        self.__products = products

    def get_native_ports(self):
        return self.__native_ports

    def get_products(self):
        return self.__products

    def get_connected_instruments(self):
        """SARAD instruments can be connected:
        1. by RS232 on a native RS232 interface at the computer
        2. via their built in FT232R USB-serial converter
        3. via an external USB-serial converter (Prolific, Prolific fake or FTDI)
        4. via the SARAD ZigBee coordinator with FT232R"""
        unknown_instrument = SaradInst('', 9600)
        # Get the list of accessible native ports
        ports_to_test = []
        # Native ports
        for port in serial.tools.list_ports.comports():
            if port.device in self.__native_ports:
                ports_to_test.append(port)
        # FTDI USB-to-serial converters
        ports_to_test.extend(serial.tools.list_ports.grep("0403"))
        # Prolific and no-name USB-to-serial converters
        ports_to_test.extend(serial.tools.list_ports.grep("067B"))

        ports_with_instruments = []
        connected_instruments = []  # a list of dictionaries containing
                                    # information about connected instruments
                                    # and the ports they are connected to
        for family in self.__products:
            # Ports with already detected devices shall not be tested with other
            # device families
            unknown_instrument.family = family
            for port in ports_with_instruments:
                try:
                    ports_to_test.remove(port)
                except:
                    pass
            for port in ports_to_test:
                unknown_instrument.port = port.device
                instrument_description = unknown_instrument.instrument_description
                if instrument_description:
                    ports_with_instruments.append(port)
                    connected_instrument = \
                       dict(\
                            port_device = port.device,\
                            port_hwid = port.hwid,\
                            port_description = port.description,\
                            baudrate = unknown_instrument.family['baudrate'],\
                            family_name = unknown_instrument.family['name'],\
                            family_id = unknown_instrument.family['id'],\
                            type_name = instrument_description['type_name'],\
                            type_id = instrument_description['type_id'],\
                            software_version = instrument_description['software_version'],\
                            device_number = instrument_description['device_number'],\
                       )
                    connected_instruments.append(connected_instrument)
        return connected_instruments

    native_ports = property(get_native_ports, set_native_ports)
    products = property(get_products, set_products)
    connected_instruments = property(get_connected_instruments)


# Test environment
if __name__=='__main__':
    def print_instrument_description(instrument_description):
        print("SerialDevice: " + instrument_description['port_device'])
        print("HWIDofPort: " + instrument_description['port_hwid'])
        print("PortDescription: " + instrument_description['port_description'])
        print("Baudrate: " + str(instrument_description['baudrate']))
        print("FamilyName: " + str(instrument_description['family_name']))
        print("FamilyId: " + str(instrument_description['family_id']))
        print("Instrument: " + instrument_description['type_name'])
        print("TypeId: " + str(instrument_description['type_id']))
        print("SoftwareVersion: " + str(instrument_description['software_version']))
        print("InstrumentNumber: " + str(instrument_description['device_number']))

    def print_dacm_value(dacm_value):
        print("ComponentName: " + dacm_value['component_name'])
        print("ValueName: " + dacm_value['value_name'])
        print(DacmInst.item_names[dacm_value['item_id']] + \
              ": " + dacm_value['result'])
        if dacm_value['datetime'] is not None:
            print("DateTime: " + dacm_value['datetime'].strftime("%c"))
        print("GPS: " + dacm_value['gps'])

    def print_radon_scout_value(radon_scout_value):
        print(repr(("Radon: " + str(radon_scout_value['radon']) + " Bq/m³")))
        if radon_scout_value['datetime'] is not None:
            print("DateTime: " + radon_scout_value['datetime'].strftime("%c"))

    mycluster = SaradCluster()
    for connected_instrument in mycluster.get_connected_instruments():
        print_instrument_description(connected_instrument)
        print()

    thoronscout = RscInst('COM16')
    # print(thoronscout.get_reply([b'\x0c', b''], 1000))

    # rtm2200 = DacmInst('COM18')
