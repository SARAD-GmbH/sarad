"""
This test starts and stops a cycle on an instrument of the DACM family in
fast sequence. It requires a connected DACM instrument.
"""

from time import sleep

from sarad.cluster import SaradCluster

my_cluster = SaradCluster()
my_cluster.update_connected_instruments()
my_instr = my_cluster.connected_instruments[0]
print("1st Test\n")
for i in range(5):
    print(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)
    print(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()

print(f"Finally trying to start. You should hear the starting pump.")
my_instr.start_cycle(2)

sleep(15)
print("Finally trying to stop")
my_instr.stop_cycle()
