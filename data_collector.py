"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import SarI
import NbEasy
import click
from filelock import Timeout, FileLock  # type: ignore
from pyzabbix import ZabbixMetric, ZabbixSender  # type: ignore
import time
import schedule  # type: ignore
import logging
import click_log  # type: ignore
import pickle
import paho.mqtt.client as client  # type: ignore
logger = logging.getLogger(__name__)
click_log.basic_config(logger)

# MQTT configuration
broker = 'localhost'
topic = 'Messdaten'

mqtt_client = client.Client()

# Strings
lock_hint = "Another instance of this application currently holds the lock."


@click.group()
@click_log.simple_verbosity_option(logger)
def cli():
    """Description for the group of commands"""
    pass


@cli.command()
@click.option('--instrument', default='j2hRuRDy',
              help=('Instrument Id.  Run ~data_collector cluster~ to get '
                    'the list of available instruments.'))
@click.option('--component', default=0, type=click.IntRange(0, 63),
              help='The Id of the sensor component.')
@click.option('--sensor', default=0, type=click.IntRange(0, 255),
              help='The Id of the sensor of the component.')
@click.option('--measurand', default=0, type=click.IntRange(0, 3),
              help='The Id of the measurand of the sensor.')
@click.option('--path', type=click.Path(writable=True),
              default='mycluster.pickle',
              help=('The path and file name to cache the cluster properties '
                    'in a PICKLE file.'))
@click.option('--lock_path', type=click.Path(writable=True),
              default='mycluster.lock',
              help='The path and file name of the lock file.')
def value(instrument, component, sensor, measurand, path, lock_path):
    """Command line application that gives back
    the most recent value of a SARAD instrument whenever it is called."""
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            try:
                with open(path, 'rb') as f:
                    mycluster = pickle.load(f)
            except Exception:
                mycluster = SarI.SaradCluster()
                mycluster.update_connected_instruments()
            logger.debug(mycluster.__dict__)
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.device_id == instrument:
                    my_instrument.get_config()
                    my_instrument.get_recent_value(component, sensor,
                                                   measurand)
                    logger.debug(my_instrument.components[component])
                    click.echo(my_instrument.components[component].
                               sensors[sensor].measurands[measurand].value)
            with open(path, 'wb') as f:
                mycluster.dump(f)
    except Timeout:
        click.echo(lock_hint)


@cli.command()
@click.option('--path', type=click.Path(writable=True),
              default='mycluster.pickle',
              help=('The path and file name to cache the cluster properties '
                    'in a PICKLE file.'))
@click.option('--lock_path', type=click.Path(writable=True),
              default='mycluster.lock',
              help='The path and file name of the lock file.')
def cluster(path, lock_path):
    """Show list of connected SARAD instruments."""
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            mycluster = SarI.SaradCluster()
            mycluster.update_connected_instruments()
            logger.debug(mycluster.__dict__)
            for instrument in mycluster:
                click.echo(instrument)
            with open(path, 'wb') as f:
                mycluster.dump(f)
    except Timeout:
        click.echo(lock_hint)


@cli.command()
@click.option('--path', type=click.Path(writable=True),
              default='iotcluster.pickle',
              help=('The path and file name to cache the list of available '
                    'IoT devices in a PICKLE file.'))
@click.option('--lock_path', type=click.Path(writable=True),
              default='iotcluster.lock',
              help='The path and file name of the lock file.')
def list_iot_devices(path, lock_path):
    """Show list of connected NB-IoT devices."""
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            iotcluster = NbEasy.IoTCluster()
            for device in iotcluster:
                click.echo(device)
            with open(path, 'wb') as f:
                iotcluster.dump(f)
    except Timeout:
        click.echo(lock_hint)


def send_trap(component_mapping, host, instrument, zbx, mycluster):
    metrics = []
    for component_map in component_mapping:
        if instrument.get_all_recent_values() is True:
            value = instrument.components[component_map['component_id']].\
                    sensors[component_map['sensor_id']].\
                    measurands[component_map['measurand_id']].value
            key = component_map['item']
            metrics.append(ZabbixMetric(host, key, value))
    zbx.send(metrics)


def start_trapper(instrument, host, server, path, lock_path, once, period):
    # The component_mapping provides a mapping between
    # component/sensor/measurand and Zabbix items
    component_mapping = [
        dict(component_id=1, sensor_id=0, measurand_id=0, item='radon'),
        dict(component_id=1, sensor_id=1, measurand_id=0, item='thoron'),
        dict(component_id=0, sensor_id=0, measurand_id=0, item='temperature'),
        dict(component_id=0, sensor_id=1, measurand_id=0, item='humidity'),
        dict(component_id=0, sensor_id=2, measurand_id=0, item='pressure'),
        dict(component_id=0, sensor_id=3, measurand_id=0, item='tilt'),
        dict(component_id=0, sensor_id=4, measurand_id=0, item='battery'),
    ]
    zbx = ZabbixSender(server)
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            logger.debug("Path: " + path)
            with open('last_session', 'w') as f:
                f.write(instrument + " " + host + " " + server + " " + path +
                        " " + lock_path + " " + str(period))

            try:
                with open(path, 'rb') as f:
                    mycluster = pickle.load(f)
            except Exception:
                mycluster = SarI.SaradCluster()
                mycluster.update_connected_instruments()
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.device_id == instrument:
                    while not once:
                        send_trap(component_mapping, host, my_instrument, zbx,
                                  mycluster)
                        time.sleep(period - time.time() % period)
                    send_trap(component_mapping, host, my_instrument, zbx,
                              mycluster)
                    with open(path, 'wb') as f:
                        mycluster.dump(f)
    except Timeout:
        click.echo(lock_hint)


@cli.command()
@click.option('--instrument', default='j2hRuRDy',
              help=('Instrument Id.  Run ~data_collector cluster~ to get '
                    'the list of available instruments.'))
@click.option('--host', default='localhost', type=click.STRING,
              help='Host name as defined in Zabbix')
@click.option('--server', default='127.0.0.1', type=click.STRING,
              help='Server IP address or name')
@click.option('--path', type=click.Path(writable=True),
              default='mycluster.pickle',
              help=('The path and file name to cache the cluster properties '
                    'in a PICKLE file.'))
@click.option('--lock_path', default='mycluster.lock',
              type=click.Path(writable=True),
              help='The path and file name of the lock file.')
@click.option('--period', default=60, type=click.IntRange(30, 7200),
              help=('Time interval in seconds for the periodic '
                    'retrieval of values.  Use CTRL+C to stop the program.'))
@click.option('--once', is_flag=True, help='Retrieve only one set of data.')
def trapper(instrument, host, server, path, lock_path, once, period):
    """Start a Zabbix trapper service to provide
    all values from an instrument."""
    start_trapper(instrument, host, server, path, lock_path, once, period)


def send_iot_trap(component_mapping, instrument, iot_device, mycluster):
    for component_map in component_mapping:
        if instrument.get_all_recent_values() is True:
            measurand = instrument.components[component_map['component_id']].\
                        sensors[component_map['sensor_id']].\
                        measurands[component_map['measurand_id']]
            value = measurand.value
            key = '{}/{}/{}'.format(component_map['component_id'],
                                    component_map['sensor_id'],
                                    component_map['measurand_id'])
            time = measurand.time.isoformat()
            message = key + ';' + str(value) + ';' + time
            iot_device.transmit(message)


@cli.command()
@click.option('--instrument', default='j2hRuRDy',
              help=('Instrument Id.  Run ~data_collector cluster~ to get '
                    'the list of available instruments.'))
@click.option('--imei', default='357518080146079',
              help=('International Mobile Equipment Identity '
                    'of the NB-IoT device to be used. '
                    'Run ~data_collector list_iot_devices~ '
                    'to get the list of available devices.'))
@click.option('--ip_address', default='213.136.85.114', type=click.STRING,
              help='IP address of cloud server')
@click.option('--udp_port', default='9876', type=click.STRING,
              help='UDP port of cloud server')
@click.option('--path', type=click.Path(writable=True),
              default='mycluster.pickle',
              help=('The path and file name to cache '
                    'the cluster properties in a PICKLE file.'))
@click.option('--lock_path', default='mycluster.lock',
              type=click.Path(writable=True),
              help='The path and file name of the lock file.')
@click.option('--period', default='auto',
              help=('Time interval in seconds for the periodic retrieval '
                    'of values.  If this value is not provided, '
                    'it will be set to the interval '
                    'gained from the instrument. '
                    'Use CTRL+C to stop the program.'))
@click.option('--once', is_flag=True, help='Retrieve only one set of data.')
def iot(instrument, imei, ip_address, udp_port, path, lock_path, once, period):
    """Start a trapper service to transmit all values from an instrument
    into an experimental IoT cloud (Vodafone NB-IoT cloud)."""
    # The component_mapping provides a mapping between
    # component/sensor/measurand and items
    component_mapping = [
        dict(component_id=1, sensor_id=0, measurand_id=0, item='radon'),
        dict(component_id=1, sensor_id=1, measurand_id=0, item='thoron'),
        dict(component_id=0, sensor_id=0, measurand_id=0, item='temperature'),
        dict(component_id=0, sensor_id=1, measurand_id=0, item='humidity'),
        dict(component_id=0, sensor_id=2, measurand_id=0, item='pressure'),
        dict(component_id=0, sensor_id=3, measurand_id=0, item='tilt'),
        dict(component_id=0, sensor_id=4, measurand_id=0, item='battery'),
    ]
    iotcluster = NbEasy.IoTCluster()
    for iot_device in iotcluster:
        if iot_device.imei == imei:
            break
    iot_device.attach()
    iot_device.ip_address = ip_address
    iot_device.udp_port = udp_port
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            try:
                with open(path, 'rb') as f:
                    mycluster = pickle.load(f)
            except Exception:
                mycluster = SarI.SaradCluster()
                mycluster.update_connected_instruments()
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.device_id == instrument:
                    while not once:
                        send_iot_trap(component_mapping, my_instrument,
                                      iot_device, mycluster)
                        time.sleep(period - time.time() % period)
                    send_iot_trap(component_mapping, my_instrument, iot_device,
                                  mycluster)
                    with open(path, 'wb') as f:
                        mycluster.dump(f)
    except Timeout:
        click.echo(lock_hint)


@cli.command()
@click.option('--path', type=click.Path(writable=True),
              default='mycluster.pickle',
              help=('The path and file name to cache the cluster properties '
                    'in a PICKLE file.'))
@click.option('--lock_path', default='mycluster.lock',
              type=click.Path(writable=True),
              help='The path and file name of the lock file.')
@click.option('--target', default='screen',
              help=('Where the values shall go to? '
                    '(screen, mqtt, zabbix).'))
def transmit(path, lock_path, target):
    # Define a function to be executed on scheduled times
    def send(target, instrument, component, sensor):
        for measurand in sensor:
            c_idx = list(instrument).index(component)
            s_idx = list(component).index(sensor)
            m_idx = list(sensor).index(measurand)
        instrument.get_recent_value(c_idx, s_idx, m_idx)
        if target == 'screen':
            click.echo(sensor)
        elif target == 'mqtt':
            mqtt_client.publish('Messdaten', str(sensor))
        elif target == 'zabbix':
            pass
        else:
            logger.error(('Target must be either screen, mqtt or zabbix.'))

    # Get the list of instruments in the cluster
    try:
        with open(path, 'rb') as f:
            mycluster = pickle.load(f)
    except Exception:
        mycluster = SarI.SaradCluster()
        mycluster.update_connected_instruments()
    # Connect to MQTT broker
    if target == 'mqtt':
        mqtt_client.connect(broker)
        mqtt_client.loop_start()
    # Start measuring cycles at all instruments
    mycluster.synchronize()
    for instrument in mycluster:
        instrument.set_lock()
    # Build the scheduler
    for instrument in mycluster:
        for component in instrument:
            for sensor in component:
                schedule.every(sensor.interval.seconds).\
                    seconds.do(send, target, instrument, component, sensor)
                logger.debug(sensor.interval.seconds)
    while True:
        schedule.run_pending()
        time.sleep(1)


@cli.command()
def last_session():
    """Starts the last trapper session as continuous service"""
    try:
        with open('last_session') as f:
            last_args = f.read().split(" ")
            logger.debug("Using arguments from last run:" + str(last_args))
            # def trapper(instrument -0, host - 1, server -2, path -3,
            # lock_path -4, once, period -5):
            start_trapper(last_args[0], last_args[1], last_args[2],
                          last_args[3], last_args[4], False, int(last_args[5]))
    except IOError:
        logger.debug(("No last run detected. Using defaults: ['j2hRuRDy', "
                      "'localhost', '127.0.0.1', 'mycluster.pickle', "
                      "'mycluster.lock', '60']"))
        start_trapper('j2hRuRDy', 'localhost', '127.0.0.1',
                      'mycluster.pickle', 'mycluster.lock', False, 60)
