#!/usr/bin/python

import serial
import serial.tools.list_ports
import time
from datetime import datetime
import struct

native_rs232_ports = ['COM1', 'COM2', 'COM3']
baudrates = [9600, 115200]

def print_port_parameters(port):
    print("Device: " + port.device)
    if not port.name:
        port.name = "n.a."
    print("Name: " + port.name)
    print("HWID: " + port.hwid)
    print("Description: " + port.description)

def print_instrument_version(instrument_version):
    print("Instrument: " + instrument_version['instrument_type'])
    print("Software version: " + str(instrument_version['software_version']))
    print("Instrument number: " + str(instrument_version['device_number']))

class SaradInstrument(object):
    """Basic class for the serial communication protocoll of SARAD instruments
    Public attributes:
        port: String containing the serial communication port
        instrument_version: Dictionary with instrument type, software version,
                            and device number
    Public methods:
        get_instrument_version(),
        set_instrument_version(),
        get_baudrate(),
        set_baudrate(),
        get_port(),
        set_port()"""

    # Device families
    f_nil = dict(name = 'no family', id = 0)
    f_doseman = dict(name = 'Doseman family', id = 1)
    f_radonscout = dict(name = 'Radon Scout family', id = 2)
    f_modem = dict(name = 'modem family', id = 3)
    f_network = dict(name = 'network interface family', id = 4)
    f_dacm = dict(name = 'DACM family', id = 5)
    device_families = [f_nil, f_doseman, f_radonscout, f_modem, f_network, f_dacm]

    # DOSEman device types
    t_doseman = dict(name = 'DOSEman', id = 1)
    t_dosemanpro = dict(name = 'DOSEman Pro', id = 2)
    t_myriam = dict(name = 'MyRIAM', id = 3)
    t_dm_rtm1688 = dict(name = 'RTM 1688', id = 4)
    t_radonsensor = dict(name = 'Analog Radon Sensor', id = 5)
    t_progenysensor = dict(name='Analog Progeny Sensor', id = 6)
    doseman_types = [t_doseman, t_dosemanpro, t_myriam, t_dm_rtm1688,\
                     t_radonsensor, t_progenysensor]

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
    radonscout_types = [t_radonscout1, t_radonscout2, t_radonscoutplus,\
                        t_rtm1688, t_radonscoutpmt, t_thoronscout,\
                        t_radonscouthome, t_radonscouthomep,\
                        t_radonscouthomeco2, t_rtm1688geo]

    # Network interface types
    t_zigbee = dict(name = 'ZigBee adapter', id = 200)
    network_types = [t_zigbee]

    __products = [device_families, doseman_types, radonscout_types, network_types]

    def __init__(self, port, baudrate):
        self.__port = port
        self.__baudrate = baudrate

    def __bytes_to_float(self, value_bytes):
        # Convert 4 bytes (little endian) from serial interface into floating point
        # nummber according to IEEE 754
        byte_array = bytearray(value_bytes)
        byte_array.reverse()
        return struct.unpack('<f', bytes(byte_array))[0]

    def __make_command_msg(self, cmd, data):
        # Encode the message to be sent to the SARAD instrument.
        # Arguments are the one byte long command and the data bytes to be sent.
        payload = cmd + data
        control_byte = len(payload) - 1
        if cmd:          # Control message
            control_byte = control_byte | 0x80 # set Bit 7
        neg_control_byte = control_byte ^ 0xff
        checksum = 0
        for byte in payload:
            checksum = checksum + byte
        checksum_bytes = bytes([checksum])
        if len(checksum_bytes) == 1:
            checksum_bytes = b'\x00' + checksum_bytes
        checksum_bytes = checksum_bytes[::-1]  # little endian order of bytes
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

    def __get_message_payload(self, serial_port, message, expected_length_of_reply):
        # Returns a dictionary of:
        #     is_valid: True if answer is valid, False otherwise
        #     is_control_message: True if control message
        #     payload: Payload of answer
        #     number_of_bytes_in_payload
        #
        ser = serial.Serial(serial_port, self.__baudrate, \
                            timeout=1, parity=serial.PARITY_NONE, \
                            stopbits=serial.STOPBITS_ONE)
        ser.write(message)
        answer = ser.read(expected_length_of_reply)
        ser.close()
        checked_answer = self.__check_answer(answer)
        return dict(is_valid = checked_answer['is_valid'],
                    is_control = checked_answer['is_control'],
                    payload = checked_answer['payload'],
                    number_of_bytes_in_payload = checked_answer['number_of_bytes_in_payload'])

    def get_instrument_version(self):
        """Returns a dictionary with instrument type, software version, and device
number."""
        get_version_msg = self.__make_command_msg(b'\x0c', b'')
        # get_version_msg = b'\x42\x80\x7f\x0c\x0c\x00\x45'
        reply_length_version_msg = 19
        checked_payload = self.__get_message_payload(self.__port,\
                                                     get_version_msg,\
                                                     reply_length_version_msg)
        if checked_payload['is_valid']:
            try:
                payload = checked_payload['payload']
                device_type = payload[1]
                software_version = payload[2]
                device_number = int.from_bytes(payload[3:5], byteorder='little', signed=False)
                for radonscout_type in self.__products[2]:
                    if radonscout_type['id'] == device_type:
                        instrument_type = radonscout_type['name']
                return dict(instrument_type = instrument_type,
                            software_version = software_version,
                            device_number = device_number)
            except ParsingError:
                print("Error parsing the payload.")
        else:
            return False

    def get_port(self):
        return self.__port

    def set_port(self, port):
        self.__port = port

    def get_baudrate(self):
        return self.__baudrate

    def set_baudrate(self, baudrate):
        self.__baudrate = baudrate

    port = property(get_port, set_port)
    instrument_version = property(get_instrument_version)
# End of definition of class SaradInstrument

def list_connected_instruments(native_rs232_ports):
    # SARAD instruments can be connected:
    # 1. by RS232 on a native RS232 interface at the computer
    # 2. via their built in FT232R USB-serial converter
    # 3. via an external USB-serial converter (Prolific, Prolific fake or FTDI)
    # 4. via the SARAD ZigBee coordinator with FT232R
    # 5. via a modem with AT command set
    unknown_instrument = SaradInstrument('', 9600)
    # Get the list of accessible native ports
    ports_to_test = []
    # Native ports
    for port in serial.tools.list_ports.comports():
        if port.device in native_rs232_ports:
            ports_to_test.append(port)
    # FTDI USB-to-serial converters
    ports_to_test.extend(serial.tools.list_ports.grep("0403"))
    # Prolific and no-name USB-to-serial converters
    ports_to_test.extend(serial.tools.list_ports.grep("067B"))

    ports_with_instruments = []
    for baudrate in baudrates:
        # Ports with already detected devices shall not be tested with other
        # baud rates
        for port in ports_to_test:
            if port.device in ports_with_instruments:
                ports_to_test.remove(port)
                print('Remove ' + port.device)
        for port in ports_to_test:
            unknown_instrument.port = port.device
            if unknown_instrument.instrument_version:
                ports_with_instruments.append(port.device)
                print_port_parameters(port)
                print_instrument_version(unknown_instrument.instrument_version)
                print()
    print(ports_with_instruments)


list_connected_instruments(native_rs232_ports)


def get_recent_readings(serial_port):
    get_recent_msg = b'\x42\x80\x7f\x14\x14\x00\x45'
    reply_length_recent_msg = 39
    checked_payload = get_message_payload(serial_port, get_recent_msg, reply_length_recent_msg)
    if checked_payload['is_valid']:
        try:
            payload = checked_payload['payload']
            sample_interval = payload[1]
            device_time_min = payload[2]
            device_time_h = payload[3]
            device_time_d = payload[4]
            device_time_m = payload[5]
            device_time_y = payload[6]
            radon = bytes_to_float(payload[7:11])
            radon_error = payload[11]
            thoron = bytes_to_float(payload[12:16])
            thoron_error = payload[16]
            temperature = bytes_to_float(payload[17:21])
            humidity = bytes_to_float(payload[21:25])
            pressure = bytes_to_float(payload[25:29])
            tilt = int.from_bytes(payload[29:], byteorder='little', signed=False)
            device_time = datetime(device_time_y + 2000, device_time_m,
                                   device_time_d, device_time_h, device_time_min)
            print(sample_interval)
            print(device_time)
            print(radon)
            print(radon_error)
            print(thoron)
            print(thoron_error)
            print(temperature)
            print(humidity)
            print(pressure)
            print(tilt)
        except ParsingError:
            print("Error parsing the payload.")
    else:
        print("The instrument doesn't reply.")

def get_battery_voltage(serial_port):
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
