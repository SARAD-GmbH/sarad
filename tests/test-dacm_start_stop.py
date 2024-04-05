"""
This test starts and stops a cycle on an instrument of the DACM family in
fast sequence. It requires a connected DACM instrument.
"""

import os
from datetime import datetime
from time import sleep

from sarad.cluster import SaradCluster

os.system("")  # enables ansi escape characters in terminal

COLOR = {
    "HEADER": "\033[95m",
    "BLUE": "\033[94m",
    "GREEN": "\033[92m",
    "RED": "\033[91m",
    "ENDC": "\033[0m",
}


def now():
    return datetime.now().strftime("%M:%S:%f")


def comment(text):
    print(f"{now()}  " + text)


def heading(text):
    print(f"\n{COLOR['HEADER']}{text}{COLOR['ENDC']}\n")


my_cluster = SaradCluster()
my_cluster.update_connected_instruments()
my_instr = my_cluster.connected_instruments[0]
no_of_attempts = 5
heading(f"1st Test -- {no_of_attempts} attempts of Start/Stop")
for i in range(5):
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)
    comment(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()

comment(f"Finally trying to start. You should hear the starting pump.")
my_instr.start_cycle(2)

sleep(15)
comment("Finally trying to stop")
my_instr.stop_cycle()

heading(f"2nd Test -- {no_of_attempts} attempts of Start/Stop/Start")
for i in range(no_of_attempts):
    if i:
        comment(f"In the next attempt to start we are expecting an error message.")
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)
    comment(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)

comment("Trying to stop")
my_instr.stop_cycle()

comment(f"Finally trying to start. You should hear the starting pump.")
my_instr.start_cycle(2)

sleep(15)
comment("Finally trying to stop")
my_instr.stop_cycle()

heading(f"3rd Test -- {no_of_attempts} attempts of Stop/Start/Stop")
for i in range(no_of_attempts):
    comment(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)
    comment(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()

comment(f"Finally trying to start. You should hear the starting pump.")
my_instr.start_cycle(2)

heading(f"4th Test -- {no_of_attempts} attempts of Stop/Start/Stop/Start")
for i in range(no_of_attempts):
    comment(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)
    comment(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)

sleep(15)
comment("Finally trying to stop")
my_instr.stop_cycle()

no_of_attempts = 100
heading(f"5th Test -- {no_of_attempts} attempts of Start/Stop/Start")
for i in range(no_of_attempts):
    if i:
        comment(f"In the next attempt to start we are expecting an error message.")
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)
    comment(f"Attempt {i + 1}: trying to stop")
    my_instr.stop_cycle()
    comment(f"Attempt {i + 1}: trying to start")
    my_instr.start_cycle(2)

comment("Trying to stop")
my_instr.stop_cycle()

comment(f"Finally trying to start. You should hear the starting pump.")
my_instr.start_cycle(2)

sleep(10)
comment("The instrument will stay running after the test.")
