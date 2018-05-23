"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import SarI
import click
import pickle
from filelock import Timeout, FileLock
from pyzabbix import ZabbixMetric, ZabbixSender
import time

@click.group()
def cli():
    """Description for the group of commands"""
    pass

@cli.command()
@click.option('--instrument', default=0, help='Instrument Id')
@click.option('--component', default=0, help='The id or the sensor component.')
@click.option('--measurand', default=0, help='The id or the measurand of the component.')
@click.option('--item', default=0, help='The id or the item of the measurand.')
@click.option('--path', default='mycluster.pickle', help='The path to cache the cluster.')
@click.option('--lock_path', default='mycluster.lock', help='The path to the lock file.')
def value(instrument, component, measurand, item, path, lock_path):
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
            print(mycluster.connected_instruments[instrument].\
                  get_recent_value(\
                                   component,\
                                   measurand,\
                                   item\
                  )['value'])
            with open(path, 'wb') as f:
                pickle.dump(mycluster, f, pickle.HIGHEST_PROTOCOL)
    except Timeout:
        print("Another instance of this application currently holds the lock.")

@cli.command()
def cluster():
    """Show list of connected SARAD instruments."""
    mycluster = SarI.SaradCluster()
    for connected_instrument in mycluster.connected_instruments:
        print(connected_instrument)
        print()

def send_trap(component_mapping, host, instrument, measurand, item, zbx, path, lock):
    try:
        metrics = []
        with lock.acquire(timeout=10):
            try:
                with open(path, 'rb') as f:
                    mycluster = pickle.load(f)
            except:
                mycluster = SarI.SaradCluster()
            for component_map in component_mapping:
                value = mycluster.connected_instruments[instrument].\
                      get_recent_value(\
                                       component_map['id'],\
                                       measurand,\
                                       item\
                      )['value']
                key = component_map['name']
                metrics.append(ZabbixMetric(host, key, value))
            zbx.send(metrics)
            with open(path, 'wb') as f:
                pickle.dump(mycluster, f, pickle.HIGHEST_PROTOCOL)
    except Timeout:
        print("Another instance of this application currently holds the lock.")

@cli.command()
@click.option('--instrument', default=0, help='Instrument Id')
@click.option('--host', default='localhost', help='Host name as defined in Zabbix')
@click.option('--server', default='127.0.0.1', help='Server IP address or name')
@click.option('--path', default='mycluster.pickle', help='The path to cache the cluster.')
@click.option('--lock_path', default='mycluster.lock', help='The path to the lock file.')
@click.option('--period', default=60, help='Time interval in seconds for the periodic retrieval of values.  Use CTRL+C to stop the program.')
@click.option('--once/--periodic', default=False, help='Retrieve only one set of data.')
def trapper(instrument, host, server, path, lock_path, once, period):
    """Start a Zabbix trapper service to provide all values from an instrument."""
    component_mapping = [
        dict(id = 0, name = 'radon'),
        dict(id = 1, name = 'thoron'),
        dict(id = 2, name = 'temperature'),
        dict(id = 3, name = 'humidity'),
        dict(id = 4, name = 'pressure'),
    ]
    measurand = 0
    item = 0
    zbx = ZabbixSender(server)
    lock = FileLock(lock_path)
    starttime = time.time()
    while not once:
        send_trap(component_mapping, host, instrument, measurand, item, zbx, path, lock)
        time.sleep(period - time.time() % period)
    send_trap(component_mapping, host, instrument, measurand, item, zbx, path, lock)
