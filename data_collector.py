"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import SarI
import click
import pickle
from filelock import Timeout, FileLock

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
