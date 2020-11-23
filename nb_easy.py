"""Collection of classes to communicate with NB-IoT modules from
Exelonix/Vodafone"""

import serial
import serial.tools.list_ports
import time
from datetime import datetime
from datetime import timedelta
import logging

class Device(object):
    """Basic class for the EASY serial communication protocol for NB-IoT devices

    Properties:
        port: String containing the serial communication port
        imei: Identifier for an individual IoT device
        device_type: device type of the Exelonix NB-IoT device
        hardware_revision
        firmware_version
        easy_if_version: EASY-IF version
        ip_address
        udp_port
    Public methods:
        get_response()
        attach()
        detach()
        transmit()
    """

    def __init__(self, port = None, ip_address = '213.136.85.114', \
                 udp_port = '9876'):
        if port is not None:
            self.__port = port
            self.__get_imei()
        self.__ip_address = ip_address
        self.__udp_port = udp_port

    # Private methods
    def __make_request(self, operation_id, payload=None):
        # Encode the message to be sent to the NB-IoT device.
        if payload is not None:
            payload = ':' + payload
        else:
            payload = ''
        output = 'EASY+' + operation_id + payload + '\r'
        return output

    def __get_imei(self):
        reply = self.get_response('Device', no_of_response_lines = 1)
        response = reply['response'][0]
        confirm = reply['confirm']
        device_descr = response.split(':')[1].split(',')
        self.__device_type = device_descr[0]
        self.__hardware_revision = device_descr[1]
        self.__firmware_version = device_descr[2]
        self.__easy_if_version = device_descr[3]
        self.__imei = device_descr[4]

    # Public methods
    def get_response(self, operation_id, payload = None, no_of_response_lines = 30):
        """Returns a list of response lines to operation message. 'operation_id' and payload are string variables."""
        request = self.__make_request(operation_id, payload)
        with serial.Serial(self.port, 115200, timeout=5) as ser:
            ser.write(request.encode('utf-8'))
            response = []
            for x in range(no_of_response_lines + 1):
                received_line = ser.readline().decode('utf-8')[:-2]  # remove \r\n
                logging.info(received_line)
                if 'EASY#' in received_line:
                    confirm = received_line.split(':')[1]
                    return dict(response = response, confirm = confirm)
                elif 'EASY-' in received_line:
                    response.append(received_line)

    def attach(self, plmn = 0):
        if self.get_response('ModemStatus')['response'][0] == \
           'EASY-ModemStatus:Attached':
            return 'NothingToDo'
        reply = self.get_response('Attach', str(plmn))
        response = reply['response']
        if response:
            for line in response:
                logging.info(line)
        confirm = reply['confirm']
        return confirm

    def detach(self):
        if self.get_response('ModemStatus')['response'][0] == \
           'EASY-ModemStatus:Detached':
            return 'NothingToDo'
        reply = self.get_response('Detach')
        response = reply['response']
        if response:
            for line in response:
                logging.info(line)
        confirm = reply['confirm']
        return confirm

    def transmit(self, message):
        data = '{}?b=[s="{}"]'.format(self.imei, message)
        logging.debug(data)
        data_length = len(data)
        payload = '{},{},{},{}'.\
                  format(self.ip_address, self.udp_port, data_length, data)
        logging.debug(payload)
        reply = self.get_response('TX', payload)
        response = reply['response']
        if response:
            for line in response:
                logging.info(line)
        confirm = reply['confirm']
        return confirm

    def get_port(self):
        return self.__port
    def set_port(self, port):
        self.__port = port
        self.__get_imei()
    port = property(get_port, set_port)

    def get_imei(self):
        return self.__imei
    def set_imei(self, imei):
        self.__imei = imei
    imei = property(get_imei, set_imei)

    def get_device_type(self):
        return self.__device_type
    def set_device_type(self, device_type):
        self.__device_type = device_type
    device_type = property(get_device_type, set_device_type)

    def get_hardware_revision(self):
        return self.__hardware_revision
    def set_hardware_revision(self, hardware_revision):
        self.__hardware_revision = hardware_revision
    hardware_revision = property(get_hardware_revision, set_hardware_revision)

    def get_firmware_version(self):
        return self.__firmware_version
    def set_firmware_version(self, firmware_version):
        self.__firmware_version = firmware_version
    firmware_version = property(get_firmware_version, set_firmware_version)

    def get_easy_if_version(self):
        return self.__easy_if_version
    def set_easy_if_version(self, easy_if_version):
        self.__easy_if_version = easy_if_version
    easy_if_version = property(get_easy_if_version, set_easy_if_version)

    def get_ip_address(self):
        return self.__ip_address
    def set_ip_address(self, ip_address):
        self.__ip_address = ip_address
    ip_address = property(get_ip_address, set_ip_address)

    def get_udp_port(self):
        return self.__udp_port
    def set_udp_port(self, udp_port):
        self.__udp_port = udp_port
    udp_port = property(get_udp_port, set_udp_port)

    def __str__(self):
        output = "IMEI: " + str(self.__imei) + "\n"
        output += "SerialDevice: " + self.port + "\n"
        output += "DeviceType: " + self.__device_type + "\n"
        output += "HardwareRevision: " + str(self.__hardware_revision) + "\n"
        output += "FirmwareVersion: " + str(self.__firmware_version) + "\n"
        output += "EasyIfVersion: " + str(self.__easy_if_version) + "\n"
        return output

class IoTCluster(object):
    """Class to define a cluster of IoT devices connected to one controller.  \
    The devices may be connected via USB, UART, or RS232 respectively.
    Properties:
        native_ports
        active_ports
        connected_devices
    Public methods:
        set_native_ports()
        get_native_ports()
        get_active_ports()
        get_connected_devices()
        update_connected_devices()
        next()
    """

    def __init__(self, native_ports=None):
        if native_ports is None:
            native_ports = []
        self.__native_ports = native_ports
        self.__connected_devices = self.update_connected_devices()
        self.__i = 0
        self.__n = len(self.__connected_devices)

    def __iter__(self):
        return iter(self.__connected_devices)

    def next(self):
        if self.__i < self.__n:
            __i = self.__i
            self.__i += 1
            return self.__connected_devices[__i]
        else:
            self.__i = 0
            self.__n = len(self.__connected_devices)
            raise StopIteration()

    def set_native_ports(self, native_ports):
        self.__native_ports = native_ports

    def get_native_ports(self):
        return self.__native_ports

    def get_active_ports(self):
        """NB-IoT devices can be connected:
        1. by UART on a native RS232 or UART interface at the computer
        2. via their built in SiLabs USB-UART bridge"""
        active_ports = []
        # Get the list of accessible native ports
        for port in serial.tools.list_ports.comports():
            if port.device in self.__native_ports:
                active_ports.append(port)
        # SiLab USB-to-serial bridge
        active_ports.extend(serial.tools.list_ports.grep("10C4"))
        # Actually we don't want the ports but the port devices.
        self.__active_ports = []
        for port in active_ports:
            self.__active_ports.append(port.device)
        return self.__active_ports

    def update_connected_devices(self):
        ports_to_test = self.active_ports
        logging.info(str(len(ports_to_test)) + ' ports to test')
        # We check every active port and try for a connected IoT device.
        connected_devices = []  # a list of device objects
        test_device = Device()
        logging.info(ports_to_test)
        for port in ports_to_test:
            logging.info('Testing port ' + port)
            test_device.port = port
            if test_device.get_imei():
                logging.info('IoT device with IMEI' + test_device.imei + ' found on port ' + port)
                connected_devices.append(test_device)
        return connected_devices

    def get_connected_devices(self):
        return self.__connected_devices

    native_ports = property(get_native_ports, set_native_ports)
    active_ports = property(get_active_ports)
    connected_devices = property(get_connected_devices)

# Test environment
if __name__=='__main__':
    logging.basicConfig(level=logging.DEBUG)

    mycluster = IoTCluster()
    for connected_device in mycluster:
        print(connected_device)
