"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import time
import logging
import pickle
import signal
import sys
import click
from filelock import Timeout, FileLock  # type: ignore
from pyzabbix import ZabbixMetric, ZabbixSender  # type: ignore
import schedule  # type: ignore
import click_log  # type: ignore
import paho.mqtt.client as client  # type: ignore
import sari
import nb_easy
logger = logging.getLogger()
FORMAT = "%(asctime)-15s %(levelname)-6s %(module)-15s %(message)s"
logging.basicConfig(format=FORMAT)

# * MQTT configuration:
# BROKER = '192.168.10.166'
BROKER = 'localhost'
CLIENT_ID = 'ap-strey'


def on_connect(client, userdata, flags, rc):
    """Will be carried out when the client connected to the MQTT broker."""
    if rc:
        logger.info('Connection to MQTT broker failed. rc=%s', rc)
    else:
        logger.info('Connected with MQTT broker.')

def on_disconnect(client, userdata, rc):
    """Will be carried out when the client disconnected from the MQTT broker."""
    if rc:
        logger.info('Disconnection from MQTT broker failed. rc=%s', rc)
    else:
        logger.info('Gracefully disconnected from MQTT broker.')

mqtt_client = client.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

# * Strings:
LOCK_HINT = "Another instance of this application currently holds the lock."


# * Handling of Ctrl+C:
def signal_handler(sig, frame):
    """On Ctrl+C:
    - stop all cycles
    - disconnect from MQTT broker"""
    logger.info('You pressed Ctrl+C!')
    for instrument in thiscluster:
        instrument.stop_cycle()
        logger.info('Device %s stopped.', instrument.device_id)
    mqtt_client.disconnect()
    mqtt_client.loop_stop()
    sys.exit(0)


thiscluster = None
signal.signal(signal.SIGINT, signal_handler)


# * Main group of commands:
@click.group()
@click_log.simple_verbosity_option(logger)
def cli():
    """Description for the group of commands"""


# * Single value output:
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
                with open(path, 'rb') as cluster_file:
                    mycluster = pickle.load(cluster_file)
            except Exception:   # pylint: disable=broad-except
                mycluster = sari.SaradCluster()
                mycluster.update_connected_instruments()
                with open(path, 'wb') as cluster_file:
                    mycluster.dump(cluster_file)
            logger.debug(mycluster.__dict__)
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.device_id == instrument:
                    my_instrument.get_config()
                    my_instrument.get_recent_value(component, sensor,
                                                   measurand)
                    logger.debug(my_instrument.components[component])
                    click.echo(my_instrument.components[component].
                               sensors[sensor].measurands[measurand].value)
    except Timeout:
        click.echo(LOCK_HINT)


# * List SARAD instruments:
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
            mycluster = sari.SaradCluster()
            mycluster.update_connected_instruments()
            logger.debug(mycluster.__dict__)
            for instrument in mycluster:
                click.echo(instrument)
            with open(path, 'wb') as cluster_file:
                mycluster.dump(cluster_file)
            return mycluster
    except Timeout:
        click.echo(LOCK_HINT)
        return False


# * List NB-IoT devices:
@cli.command()
@click.option('--path', type=click.Path(writable=True),
              default='iotcluster.pickle',
              help=('The path and file name to cache the list of available '
                    'IoT devices in a PICKLE file.'))
@click.option('--lock_path', type=click.Path(writable=True),
              default='iotcluster.lock',
              help='The path and file name of the lock file.')
def list_iot_devices(lock_path):
    """Show list of connected NB-IoT devices."""
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            iotcluster = nb_easy.IoTCluster()
            for device in iotcluster:
                click.echo(device)
    except Timeout:
        click.echo(LOCK_HINT)


# * Zabbix trapper:
def send_trap(component_mapping, host, instrument, zbx):
    """Send a Zabbix trap.

    component_mapping -- list of dictionaries defining a mapping
    between source (list index) and component_id, sensor_id, measurement_id
    and item name

    host -- Zabbix server

    instrument -- SARAD instrument as defined in sari.py

    zbx -- ZabbixSender object"""
    metrics = []
    for component_map in component_mapping:
        if instrument.get_all_recent_values() is True:
            zbx_value = instrument.components[component_map['component_id']].\
                sensors[component_map['sensor_id']].\
                measurands[component_map['measurand_id']].value
            zbx_key = component_map['item']
            metrics.append(ZabbixMetric(host, zbx_key, zbx_value))
    zbx.send(metrics)


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
            logger.debug("Path: %s", path)
            with open('last_session', 'w') as cluster_file:
                cluster_file.write(instrument + " " + host + " " + server + " " + path +
                        " " + lock_path + " " + str(period))

            try:
                with open(path, 'rb') as cluster_file:
                    mycluster = pickle.load(cluster_file)
            except Exception:   # pylint: disable=broad-except
                mycluster = sari.SaradCluster()
                mycluster.update_connected_instruments()
                with open(path, 'wb') as cluster_file:
                    mycluster.dump(cluster_file)
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.device_id == instrument:
                    while not once:
                        send_trap(component_mapping, host, my_instrument, zbx)
                        time.sleep(period - time.time() % period)
                    send_trap(component_mapping, host, my_instrument, zbx)
    except Timeout:
        click.echo(LOCK_HINT)


# * Experimental NB-IoT trapper:
def send_iot_trap(component_mapping, instrument, iot_device):
    """Send a message via the NB-IoT module
    into the experimental Vodafone cloud."""
    for component_map in component_mapping:
        if instrument.get_all_recent_values() is True:
            measurand = instrument.components[component_map['component_id']].\
                        sensors[component_map['sensor_id']].\
                        measurands[component_map['measurand_id']]
            meas_value = measurand.value
            meas_key = (f"{component_map['component_id']}/"
                        f"{component_map['sensor_id']}/"
                        f"{component_map['measurand_id']}")
            meas_time = measurand.time.isoformat()
            iot_device.transmit(f'{meas_key};{meas_value};{meas_time}')


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
    # component/sensor/measurand and items.
    # Quick and dirty for Thoron Scout only!
    component_mapping = [
        dict(component_id=1, sensor_id=0, measurand_id=0, item='radon'),
        dict(component_id=1, sensor_id=1, measurand_id=0, item='thoron'),
        dict(component_id=0, sensor_id=0, measurand_id=0, item='temperature'),
        dict(component_id=0, sensor_id=1, measurand_id=0, item='humidity'),
        dict(component_id=0, sensor_id=2, measurand_id=0, item='pressure'),
        dict(component_id=0, sensor_id=3, measurand_id=0, item='tilt'),
        dict(component_id=0, sensor_id=4, measurand_id=0, item='battery'),
    ]
    iotcluster = nb_easy.IoTCluster()
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
                with open(path, 'rb') as cluster_file:
                    mycluster = pickle.load(cluster_file)
            except Exception:   # pylint: disable=broad-except
                mycluster = sari.SaradCluster()
                mycluster.update_connected_instruments()
                with open(path, 'wb') as cluster_file:
                    mycluster.dump(cluster_file)
            for my_instrument in mycluster.connected_instruments:
                if my_instrument.device_id == instrument:
                    while not once:
                        send_iot_trap(component_mapping, my_instrument,
                                      iot_device)
                        time.sleep(period - time.time() % period)
                    send_iot_trap(component_mapping, my_instrument, iot_device)
    except Timeout:
        click.echo(LOCK_HINT)


# * Transmit all values to a target:
def send(target, instrument, component, sensor):
    '''Define a function to be executed on scheduled times'''
    for measurand in sensor:
        c_idx = list(instrument).index(component)
        s_idx = list(component).index(sensor)
        m_idx = list(sensor).index(measurand)
        instrument.get_recent_value(c_idx, s_idx, m_idx)
        if target == 'screen':
            click.echo(sensor)
        elif target == 'mqtt':
            mqtt_client.publish(
                f'{CLIENT_ID}/status/{instrument.device_id}/{sensor.name}/'
                f'{measurand.name}',
                f'{{"val": {measurand.value}, "ts": {measurand.time}}}')
            logger.debug('MQTT message for %s published.', sensor.name)
        elif target == 'zabbix':
            pass
        else:
            logger.error(('Target must be either screen, mqtt or zabbix.'))


def set_send_scheduler(target, instrument, component, sensor):
    """Initialise the scheduler to perform the send function."""
    schedule.every(sensor.interval.seconds).\
        seconds.do(send, target, instrument, component, sensor)
    logger.debug('Poll sensor %s of device %s in intervals of %d s.',
                 sensor.name, instrument.device_id, sensor.interval.seconds)


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
    """General function to transmit all values gathered from the instruments
    in our cluster to a target.
    Target can be the output of the command on the command line (screen),
    an MQTT broker or a Zabbix server."""
    global thiscluster
    lock = FileLock(lock_path)
    try:
        with lock.acquire(timeout=10):
            logger.debug("Path: %s", path)
        # Get the list of instruments in the cluster
        try:
            with open(path, 'rb') as cluster_file:
                mycluster = pickle.load(cluster_file)
        except Exception:       # pylint: disable=broad-except
            mycluster = sari.SaradCluster()
            mycluster.update_connected_instruments()
            with open(path, 'wb') as cluster_file:
                mycluster.dump(cluster_file)
        thiscluster = mycluster
        # Connect to MQTT broker
        if target == 'mqtt':
            mqtt_client.connect(BROKER)
            mqtt_client.loop_start()
        # Start measuring cycles at all instruments
        mycluster.synchronize()
        for instrument in mycluster:
            instrument.set_lock()
            logger.info('Device %s started and locked.', instrument.device_id)
        # Build the scheduler
        for instrument in mycluster:
            for component in instrument:
                for sensor in component:
                    set_send_scheduler(target, instrument, component, sensor)
        print('Press Ctrl+C to abort.')
        while True:
            schedule.run_pending()
            time.sleep(1)
    except Timeout:
        click.echo(LOCK_HINT)


# * Re-start last Zabbix trapper session:
@cli.command()
def last_session():
    """Starts the last trapper session as continuous service"""
    try:
        with open('last_session') as session_file:
            last_args = session_file.read().split(" ")
            logger.debug("Using arguments from last run: %s", last_args)
            # def trapper(instrument -0, host - 1, server -2, path -3,
            # lock_path -4, once, period -5):
            trapper(last_args[0], last_args[1], last_args[2],
                    last_args[3], last_args[4], False, int(last_args[5]))
    except IOError:
        logger.debug(("No last run detected. Using defaults: ['j2hRuRDy', "
                      "'localhost', '127.0.0.1', 'mycluster.pickle', "
                      "'mycluster.lock', '60']"))
        trapper('j2hRuRDy', 'localhost', '127.0.0.1',
                'mycluster.pickle', 'mycluster.lock', False, 60)
