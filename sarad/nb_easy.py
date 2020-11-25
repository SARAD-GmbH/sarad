"""Collection of classes to communicate with NB-IoT modules from
Exelonix/Vodafone"""

import logging
import serial                   # type: ignore
import serial.tools.list_ports  # type: ignore


class Device():
    """Basic class for the EASY serial communication protocol
    for NB-IoT devices

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

    def __init__(self, port=None, ip_address='213.136.85.114',
                 udp_port='9876'):
        if port is not None:
            self.__port = port
            self.__get_imei()
        self.__ip_address = ip_address
        self.__udp_port = udp_port
        self.__module_descr = {
            'device_type': None, 'hardware_revision': None, 'firmware_version': None,
            'easy_if_version': None, 'imei': None}

    # Private methods
    @staticmethod
    def __make_request(operation_id, payload=None):
        # Encode the message to be sent to the NB-IoT device.
        if payload is not None:
            payload = ':' + payload
        else:
            payload = ''
        output = 'EASY+' + operation_id + payload + '\r'
        return output

    def __get_imei(self):
        reply = self.get_response('Device', no_of_response_lines=1)
        response = reply['response'][0]
        device_descr = response.split(':')[1].split(',')
        self.__module_descr['device_type'] = device_descr[0]
        self.__module_descr['hardware_revision'] = device_descr[1]
        self.__module_descr['firmware_version'] = device_descr[2]
        self.__module_descr['easy_if_version'] = device_descr[3]
        self.__module_descr['imei'] = device_descr[4]

    # Public methods
    def get_response(self, operation_id, payload=None,
                     no_of_response_lines=30):
        """Returns a list of response lines to operation message.
        'operation_id' and payload are string variables."""
        request = self.__make_request(operation_id, payload)
        with serial.Serial(self.port, 115200, timeout=5) as ser:
            ser.write(request.encode('utf-8'))
            response = []
            for _ in range(no_of_response_lines + 1):
                # remove \r\n
                received_line = ser.readline().decode('utf-8')[:-2]
                logging.info(received_line)
                if 'EASY#' in received_line:
                    confirm = received_line.split(':')[1]
                    return dict(response=response, confirm=confirm)
                if 'EASY-' in received_line:
                    response.append(received_line)
        return False

    def attach(self, plmn=0):
        """Attach the modem."""
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
        """Detach the modem."""
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
        """Send a message to the cloud."""
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
        """Returns the serial port the NB-IoT module is connected to."""
        return self.__port

    def set_port(self, port):
        """Set the serial port the NB-IoT module is connected to."""
        self.__port = port
        self.__get_imei()
    port = property(get_port, set_port)

    def get_imei(self):
        """Return the identifier of the NB-IoT module."""
        return self.__module_descr['imei']
    imei = property(get_imei)

    def get_device_type(self):
        """Return the device type of the NB-IoT module."""
        return self.__module_descr['device_type']
    device_type = property(get_device_type)

    def get_hardware_revision(self):
        """Return the hardware revision of the NB-IoT module."""
        return self.__module_descr['hardware_revision']

    def get_firmware_version(self):
        """Return the firmware version of the NB-IoT module."""
        return self.__module_descr['firmware_version']

    def get_easy_if_version(self):
        """Return the EASY version of the NB-IoT module."""
        return self.__module_descr['easy_if_version']

    def get_ip_address(self):
        """Return the IP address of the NB-IoT module."""
        return self.__ip_address

    def set_ip_address(self, ip_address):
        """Set the IP address of the NB-IoT module."""
        self.__ip_address = ip_address
    ip_address = property(get_ip_address, set_ip_address)

    def get_udp_port(self):
        """Return the UDP port of the NB-IoT module."""
        return self.__udp_port

    def set_udp_port(self, udp_port):
        """Set the UDP port of the NB-IoT module."""
        self.__udp_port = udp_port
    udp_port = property(get_udp_port, set_udp_port)

    def __str__(self):
        output = (
            f"IMEI: {self.imei} \nSerialDevice: {self.port}\n"
            f"DeviceType: {self.device_type}\n"
            f"HardwareRevision: {self.__module_descr['hardware_revision']}\n"
            f"FirmwareVersion: {self.__module_descr['firmware_version']}\n"
            f"EasyIfVersion: {self.__module_descr['easy_if_version']}\n")
        return output


class IoTCluster():
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
    """

    def __init__(self, native_ports=None):
        if native_ports is None:
            native_ports = []
        self.__native_ports = native_ports
        self.__connected_devices = self.update_connected_devices()
        self.__active_ports = []

    def __iter__(self):
        return iter(self.__connected_devices)

    def set_native_ports(self, native_ports):
        """Set a list of native (RS-232) serial ports."""
        self.__native_ports = native_ports

    def get_native_ports(self):
        """Return a list of native (RS-232) serial ports."""
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
        """Update the list of connected NB-IoT modules."""
        ports_to_test = self.active_ports
        logging.info('%d ports to test', len(ports_to_test))
        # We check every active port and try for a connected IoT device.
        connected_devices = []  # a list of device objects
        test_device = Device()
        logging.info(ports_to_test)
        for port in ports_to_test:
            logging.info('Testing port %s.', port)
            test_device.port = port
            if test_device.get_imei():
                logging.info('IoT device with IMEI %s found on port %s.',
                             test_device.imei, port)
                connected_devices.append(test_device)
        return connected_devices

    def get_connected_devices(self):
        """Return a list of connected NB-IoT modules."""
        return self.__connected_devices

    native_ports = property(get_native_ports, set_native_ports)
    active_ports = property(get_active_ports)
    connected_devices = property(get_connected_devices)


# * Test environment:
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    mycluster = IoTCluster()
    for connected_device in mycluster:
        print(connected_device)
