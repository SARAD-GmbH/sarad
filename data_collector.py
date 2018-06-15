"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import SarI
import NbEasy
import click
import pickle
from filelock import Timeout, FileLock
from pyzabbix import ZabbixMetric, ZabbixSender
import time
from datetime import datetime
import logging

@click.group()
def cli():
    """Description for the group of commands"""
    logging.basicConfig(level=logging.DEBUG)

@cli.command()
@click.option('--instrument', default='j2hRuRDy', help='Instrument Id.  Run ~data_collector cluster~ to get the list of available instruments.')
@click.option('--component', default=0, type=click.IntRange(0, 63), help='The Id of the sensor component.')
@click.option('--sensor', default=0, type=click.IntRange(0, 255), help='The Id of the sensor of the component.')
@click.option('--measurand', default=0, type=click.IntRange(0, 3), help='The Id of the measurand of the sensor.')
@click.option('--path', type=click.Path(writable=True), default='mycluster.pickle', help='The path and file name to cache the cluster in a Python Pickle file.')
@click.option('--lock_path', type=click.Path(writable=True), default='mycluster.lock', help='The path and file name of the lock file.')
def value(instrument, component, sensor, measurand, path, lock_path):
    """Command line application that gives back the most recent value of a SARAD
    instrument whenever it is called.
    Made to be a data source for Zabbix agent."""
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            try:
                with open(path, 'rb') as f:
                    mycluster = pickle.load(f)
            except:
                mycluster = SarI.SaradCluster()
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.id == instrument:
                    my_instrument.get_recent_value(component, sensor, measurand)
                    print(my_instrument.components[component].sensors[sensor].\
                          measurands[measurand].value)
            with open(path, 'wb') as f:
                pickle.dump(mycluster, f, pickle.HIGHEST_PROTOCOL)
    except Timeout:
        print("Another instance of this application currently holds the lock.")

@cli.command()
@click.option('--path', type=click.Path(writable=True), default='mycluster.pickle', help='The path and file name to cache the cluster in a Python Pickle file.')
@click.option('--lock_path', type=click.Path(writable=True), default='mycluster.lock', help='The path and file name of the lock file.')
def cluster(path, lock_path):
    """Show list of connected SARAD instruments."""
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            mycluster = SarI.SaradCluster()
            for instrument in mycluster:
                print(instrument)
            with open(path, 'wb') as f:
                pickle.dump(mycluster, f, pickle.HIGHEST_PROTOCOL)
    except Timeout:
        print("Another instance of this application currently holds the lock.")

@cli.command()
@click.option('--path', type=click.Path(writable=True), default='iotcluster.pickle', help='The path and file name to cache the cluster in a Python Pickle file.')
@click.option('--lock_path', type=click.Path(writable=True), default='iotcluster.lock', help='The path and file name of the lock file.')
def list_iot_devices(path, lock_path):
    """Show list of connected NB-IoT devices."""
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            iotcluster = NbEasy.IoTCluster()
            for device in iotcluster:
                print(device)
            with open(path, 'wb') as f:
                pickle.dump(iotcluster, f, pickle.HIGHEST_PROTOCOL)
    except Timeout:
        print("Another instance of this application currently holds the lock.")

def send_trap(component_mapping, host, instrument, zbx, mycluster):
    metrics = []
    for component_map in component_mapping:
        if instrument.get_all_recent_values() == True:
            value = instrument.components[component_map['component_id']].\
                    sensors[component_map['sensor_id']].\
                    measurands[component_map['measurand_id']].value
            key = component_map['item']
            metrics.append(ZabbixMetric(host, key, value))
    zbx.send(metrics)

@cli.command()
@click.option('--instrument', default='j2hRuRDy', help='Instrument Id.  Run ~data_collector cluster~ to get the list of available instruments.')
@click.option('--host', default='localhost', type=click.STRING, help='Host name as defined in Zabbix')
@click.option('--server', default='127.0.0.1', type=click.STRING, help='Server IP address or name')
@click.option('--path', default='mycluster.pickle', type=click.Path(writable=True), help='The path and file name to cache the cluster in a Python Pickle file.')
@click.option('--lock_path', default='mycluster.lock', type=click.Path(writable=True), help='The path and file name of the lock file.')
@click.option('--period', default=60, type=click.IntRange(30, 7200), help='Time interval in seconds for the periodic retrieval of values.  Use CTRL+C to stop the program.')
@click.option('--once', is_flag=True, help='Retrieve only one set of data.')
def trapper(instrument, host, server, path, lock_path, once, period):
    """Start a Zabbix trapper service to provide all values from an instrument."""
    # The component_mapping provides a mapping between
    # component/sensor/measurand and Zabbix items
    component_mapping = [
        dict(component_id = 1, sensor_id = 0, measurand_id = 0, item = 'radon'),
        dict(component_id = 1, sensor_id = 1, measurand_id = 0, item = 'thoron'),
        dict(component_id = 0, sensor_id = 0, measurand_id = 0, \
             item = 'temperature'),
        dict(component_id = 0, sensor_id = 1, measurand_id = 0, item = 'humidity'),
        dict(component_id = 0, sensor_id = 2, measurand_id = 0, item = 'pressure'),
        dict(component_id = 0, sensor_id = 3, measurand_id = 0, item = 'tilt'),
        dict(component_id = 0, sensor_id = 4, measurand_id = 0, item = 'battery'),
    ]
    zbx = ZabbixSender(server)
    lock = FileLock(lock_path)
    starttime = time.time()
    try:
        with lock.acquire(timeout=10):
            try:
                with open(path, 'rb') as f:
                    mycluster = pickle.load(f)
            except:
                mycluster = SarI.SaradCluster()
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.id == instrument:
                    while not once:
                        send_trap(component_mapping, host, my_instrument, zbx, \
                                  mycluster)
                        time.sleep(period - time.time() % period)
                    send_trap(component_mapping, host, my_instrument, zbx, mycluster)
                    with open(path, 'wb') as f:
                        pickle.dump(mycluster, f, pickle.HIGHEST_PROTOCOL)
    except Timeout:
        print("Another instance of this application currently holds the lock.")

def send_iot_trap(component_mapping, instrument, iot_device, mycluster):
    for component_map in component_mapping:
        if instrument.get_all_recent_values() == True:
            measurand = instrument.components[component_map['component_id']].\
                        sensors[component_map['sensor_id']].\
                        measurands[component_map['measurand_id']]
            value = measurand.value
            key = '{}/{}/{}'.format(component_map['component_id'], \
                                    component_map['sensor_id'], \
                                    component_map['measurand_id'])
            time = measurand.time.isoformat()
            message = key + ';' + str(value) + ';' + time
            iot_device.transmit(message)

@cli.command()
@click.option('--instrument', default='j2hRuRDy', help='Instrument Id.  Run ~data_collector cluster~ to get the list of available instruments.')
@click.option('--imei', default='357518080146079', help='International Mobile Equipment Identity of the NB-IoT device to be used.  Run ~data_collector list_iot_devices~ to get the list of available devices.')
@click.option('--ip_address', default='213.136.85.114', type=click.STRING, help='IP address of cloud server')
@click.option('--udp_port', default='9876', type=click.STRING, help='UDP port of cloud server')
@click.option('--path', default='mycluster.pickle', type=click.Path(writable=True), help='The path and file name to cache the cluster in a Python Pickle file.')
@click.option('--lock_path', default='mycluster.lock', type=click.Path(writable=True), help='The path and file name of the lock file.')
@click.option('--period', default=None, type=click.IntRange(30, 7200), help='Time interval in seconds for the periodic retrieval of values.  If this value is not provided, it will be set to the interval gained from the instrument.  Use CTRL+C to stop the program.')
@click.option('--once', is_flag=True, help='Retrieve only one set of data.')
def iot(instrument, imei, ip_address, udp_port, path, lock_path, once, period):
    """Start a trapper service to transmit all values from an instrument into an IoT cloud."""
    # The component_mapping provides a mapping between
    # component/sensor/measurand and items
    component_mapping = [
        dict(component_id = 1, sensor_id = 0, measurand_id = 0, item = 'radon'),
        dict(component_id = 1, sensor_id = 1, measurand_id = 0, item = 'thoron'),
        dict(component_id = 0, sensor_id = 0, measurand_id = 0, \
             item = 'temperature'),
        dict(component_id = 0, sensor_id = 1, measurand_id = 0, item = 'humidity'),
        dict(component_id = 0, sensor_id = 2, measurand_id = 0, item = 'pressure'),
        dict(component_id = 0, sensor_id = 3, measurand_id = 0, item = 'tilt'),
        dict(component_id = 0, sensor_id = 4, measurand_id = 0, item = 'battery'),
    ]
    iotcluster = NbEasy.IoTCluster()
    for iot_device  in iotcluster:
        if iot_device.imei == imei:
            break
    iot_device.attach()
    iot_device.ip_address = ip_address
    iot_device.udp_port = udp_port
    lock = FileLock(lock_path)
    starttime = time.time()
    try:
        with lock.acquire(timeout=10):
            try:
                with open(path, 'rb') as f:
                    mycluster = pickle.load(f)
            except:
                mycluster = SarI.SaradCluster()
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.id == instrument:
                    while not once:
                        send_iot_trap(component_mapping, my_instrument, iot_device, \
                                  mycluster)
                        time.sleep(period - time.time() % period)
                    send_iot_trap(component_mapping, my_instrument, iot_device, mycluster)
                    with open(path, 'wb') as f:
                        pickle.dump(mycluster, f, pickle.HIGHEST_PROTOCOL)
    except Timeout:
        print("Another instance of this application currently holds the lock.")
