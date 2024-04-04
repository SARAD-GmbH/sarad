# Library to access SARAD instruments

## Modules

### sari
a class library to access SARAD instruments via their serial interfaces,
comprises all recent SARAD instruments with their proprietary protocols

### radonscout
a module for the adapter to the instruments of the Radon Scout family

### dacm
a module for the adapter to the instruments of the DACM family

### doseman
a module for the adapter to the instruments of the DOSEman family (uncomplete,
since the DOSEman family is not suited for monitoring applications)

## Caveat
Work in progress.
Code might be buggy, clumsy or uncomplete.
Be careful, feel free to improve things and come back to me with questions.

-- Michael Strey

## What is it about?
SARAD GmbH is a manufacturer of instruments for environmental measuring with a
focus on radioactivity, radon and gases. All instruments have a serial interface
-- usually a RS-232, RS-422 or USB creating a virtual serial port -- for remote
control, configuration, telemetry and data download. The protocol on the serial
interface is proprietary and differs from device family to device family and
even between device types. Up to now, the instruments can only be controlled
with the proprietary software applications provided by SARAD.

This package is an attempt to empower SARAD customers to make their own software
solutions to control SARAD instruments. It brings all proprietary SARAD
protocols and instruments together and allows to access them via a unique
software interface.

## Installation

```
pip install git+https://github.com/SARAD-GmbH/sarad.git
```

## Getting started

Clone this Git repository:

```
git clone https://github.com/SARAD-GmbH/sarad.git
```

Install the virtual environment:

```
pdm install
```

Connect a SARAD measuring instrument,
start the Python REPL in the virtual environment and try some methods:

```
➜  sarad git:(master) ✗ pdm run python
Python 3.9.18 (main, Nov  2 2023, 12:04:11)
[GCC 13.2.1 20230801] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> from sarad.cluster import SaradCluster
>>> mycluster = SaradCluster()
>>> mycluster.update_connected_instruments()
[<sarad.dacm.DacmInst object at 0x757a62d79760>]
>>> myinstr = mycluster.connected_instruments[0]
>>> print(myinstr)
Id: 08t2hLv
SerialDevice: /dev/ttyUSB0
Baudrate: [9600, 256000]
FamilyName: DACM family
FamilyId: 5
TypName: RTM 2200
TypeId: 2
SoftwareVersion: 4
SerialNumber: 342
LastUpdate: 2022-05-02
DateOfManufacture: 2023-03-29
Address: 0
LastConfig: 2023-09-15
ModuleName: RTM 2200
ConfigName: Bodenluft
```

**Read the code!***

Check out the sample project [*datacollector*](https://github.com/SARAD-GmbH/datacollector) as well!

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm-project.org)
