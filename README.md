# Library to access SARAD instruments

- sari :: a class library to access SARAD instruments via their serial
          interfaces, comprises all recent SARAD instruments with their
          proprietary protocols
- radonscout :: a module for the adapter to the instruments of the Radon Scout family
- dacm :: a module for the adapter to the instruments of the DACM family
- doseman :: a module for the adapter to the instruments of the DOSEman family
             (uncomplete, since the DOSEman family is not suited for monitoring applications)

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

## Getting started
Requires Python 3.

Clone the repository to your local computer and move into the directory.
```
sudo pip install --editable ./
```

*Read the code!*
