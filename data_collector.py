#!/usr/bin/python

import serial
import serial.tools.list_ports
import time
from datetime import datetime
import struct

f_nil = dict(name = 'no family', id = 0)
f_doseman = dict(name = 'Doseman family', id = 1)
f_radonscout = dict(name = 'Radon Scout family', id = 2)
f_modem = dict(name = 'modem family', id = 3)
f_network = dict(name = 'network interface family', id = 4)
f_dacm = dict(name = 'DACM family', id = 5)
device_families = [f_nil, f_doseman, f_radonscout, f_modem, f_network, f_dacm]

#*************************** DOSEman Gerätetypen ******************************}
t_doseman = dict(name = 'DOSEman', id = 1)
t_dosemanpro = dict(name = 'DOSEman Pro', id = 2)
t_myriam = dict(name = 'MyRIAM', id = 3)
t_dm_rtm1688 = dict(name = 'RTM 1688', id = 4)
t_radonsensor = dict(name = 'Analog Radon Sensor', id = 5)
t_progenysensor = dict(name='Analog Progeny Sensor', id = 6)
doseman_types = [t_doseman, t_dosemanpro, t_myriam, t_dm_rtm1688, t_radonsensor, t_progenysensor]

#*************************** Radon-Scout Gerätetypen **************************}
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
radonscout_types = [t_radonscout1, t_radonscout2, t_radonscoutplus, t_rtm1688, t_radonscoutpmt, t_thoronscout, t_radonscouthome, t_radonscouthomep, t_radonscouthomeco2, t_rtm1688geo]

#************************** Netzwerk Interface Typen **************************}
t_zigbee = dict(name = 'ZigBee adapter', id = 200)
network_types = [t_zigbee]

native_rs232_ports = ['COM1', 'COM2', 'COM3']

def bytes_to_float(value_bytes):
    # Convert 4 bytes (little endian) from serial interface into floating point
    # nummber according to IEEE 754
    byte_array = bytearray(value_bytes)
    byte_array.reverse()
    return struct.unpack('<f', bytes(byte_array))[0]

def print_port_parameters(port):
    print("Device: " + port.device)
    if not port.name:
        port.name = "n.a."
    print("Name: " + port.name)
    print("HWID: " + port.hwid)
    print("Description: " + port.description + "\n")

def list_connected_instruments(native_rs232_ports):
    # SARAD instruments can be connected:
    # 1. by RS232 on a native RS232 interface at the computer
    # 2. via their built in FT232R USB-serial converter
    # 3. via an external USB-serial converter (Prolific, Prolific fake or FTDI)
    # 4. via the SARAD ZigBee coordinator with FT232R
    # 5. via a modem with AT command set
    for port in serial.tools.list_ports.comports():
        # native RS232 ports
        if port.device in native_rs232_ports:
            print_port_parameters(port)
    for port in serial.tools.list_ports.grep("0403"):
        # FTDI USB-serial converters
        print_port_parameters(port)
    for port in serial.tools.list_ports.grep("067B"):
        # Prolific USB-serial converters
        print_port_parameters(port)

def check_answer(answer):
    # Returns a dictionary of:
    #     is_valid: True if answer is valid, False otherwise
    #     is_control_message: True if control message
    #     payload: Payload of answer
    #     number_of_bytes_in_payload
    control_byte = answer[1]
    neg_control_byte = answer[2]
    print('Control byte = ' + hex(control_byte))
    print('negated control byte = ' + hex(neg_control_byte))
    if (control_byte ^ 0xff) == neg_control_byte:
        control_byte_ok = True
    number_of_bytes_in_payload = (control_byte & 0x7f) + 1
    print('Nr of data bytes = ' + str(number_of_bytes_in_payload))
    if control_byte & 0x80:
        is_control = True
    else:
        is_control = False
    status_byte = answer[3]
    print('Status byte = ' + hex(status_byte))
    payload = answer[3:3+number_of_bytes_in_payload]
    print(payload)
    calculated_checksum = 0
    for byte in payload:
        calculated_checksum = calculated_checksum + byte
    print(hex(calculated_checksum))
    received_checksum_bytes = answer[3 + number_of_bytes_in_payload:5 +
                                     number_of_bytes_in_payload]
    received_checksum = int.from_bytes(received_checksum_bytes,
                                       byteorder='little', signed=False)
    print(hex(received_checksum))
    if received_checksum == calculated_checksum:
        checksum_ok = True
    return dict(is_valid = control_byte_ok & checksum_ok,
                is_control = is_control,
                payload = payload,
                number_of_bytes_in_payload = number_of_bytes_in_payload)

def get_message_payload(serial_port, message, expected_length_of_reply):
    # Returns a dictionary of:
    #     is_valid: True if answer is valid, False otherwise
    #     is_control_message: True if control message
    #     payload: Payload of answer
    #     number_of_bytes_in_payload
    #
    ser = serial.Serial(serial_port, 9600, timeout=3, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE)
    print(ser.name)
    print(ser.get_settings())
    ser.write(message)
    answer = ser.read(expected_length_of_reply)
    ser.close()
    checked_answer = check_answer(answer)
    return dict(is_valid = checked_answer['is_valid'],
                is_control = checked_answer['is_control'],
                payload = checked_answer['payload'],
                number_of_bytes_in_payload = checked_answer['number_of_bytes_in_payload'])

def get_version(serial_port):
    get_version_msg = b'\x42\x80\x7f\x0c\x0c\x00\x45'
    reply_length_version_msg = 19
    checked_payload = get_message_payload(serial_port, get_version_msg, reply_length_version_msg)
    payload = checked_payload['payload']

    device_type = payload[1]
    software_version = payload[2]
    device_number = int.from_bytes(payload[3:5], byteorder='little', signed=False)
    for radonscout_type in radonscout_types:
        if radonscout_type['id'] == device_type:
            print(radonscout_type['name'])
    print('Software version = ' + str(software_version))
    print('Device number = ' + str(device_number))


serial_port = 'COM16'
get_recent_msg = b'\x42\x80\x7f\x14\x14\x00\x45'
reply_length_recent_msg = 39
checked_payload = get_message_payload(serial_port, get_recent_msg, reply_length_recent_msg)
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
tilt = bytes_to_float(payload[29:])
print(sample_interval)
device_time = datetime(device_time_y + 2000, device_time_m, device_time_d,
                       device_time_h, device_time_min)
print(device_time)
print(radon)
print(radon_error)
print(thoron)
print(thoron_error)
print(temperature)
print(humidity)
print(pressure)
print(tilt)

list_connected_instruments(native_rs232_ports)

