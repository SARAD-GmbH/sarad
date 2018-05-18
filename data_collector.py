"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import SarI
import click
import pickle
from filelock import Timeout, FileLock


@click.command()
@click.option('--instrument', default=0, help='Instrument Id')
@click.option('--component', default=0, help='The id or the sensor component.')
@click.option('--measurand', default=0, help='The id or the measurand of the component.')
@click.option('--item', default=0, help='The id or the item of the measurand.')
@click.option('--path', default='mycluster.pickle', help='The path to cache the cluster.')
@click.option('--lock_path', default='mycluster.lock', help='The path to the lock file.')
def get_value(instrument, component, measurand, item, path, lock_path):
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

# mycluster = SarI.SaradCluster()
# for connected_instrument in mycluster.connected_instruments:
#     print(connected_instrument)
#     print()

