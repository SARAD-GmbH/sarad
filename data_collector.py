"""Command line application that gives back the most recent value of a SARAD
instrument whenever it is called.
Made to be a data source for Zabbix agent."""

import SarI
import click
# Test environment
if __name__=='__main__':

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

    mycluster = SarI.SaradCluster()
    for connected_instrument in mycluster.connected_instruments:
        print(connected_instrument)
        print()

    print(mycluster.connected_instruments[0].get_recent_value(0,0,0)['result_value'])
