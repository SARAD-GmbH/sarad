Changelog
=========

Versions follow `Semantic Versioning <https://semver.org/>`_ (``<major>.<minor>.<patch>``).

.. towncrier release notes start

v1.0.21 (2025-10-27)
--------------------

Bugfixes
^^^^^^^^

- Permanent timeout error when calling `get_recent_value()` on DACM instruments.
  (critical error)

v1.0.20 (2025-09-04)
--------------------

Bugfixes
^^^^^^^^

- Exception handling when unplugging a device during data download.

Features
^^^^^^^^

- Improved support for new DACM-32 instruments.

Improvements
^^^^^^^^^^^^

- INCOMPATIBLE CHANGE -- Allow evaluation of return value in set_rtc.

v1.0.19 (2025-07-14)
--------------------

Bugfixes
^^^^^^^^

- Fetching recent values was sometimes to late.

v1.0.18 (2025-07-01)
--------------------

Bugfixes
^^^^^^^^

- Temperature, pressure and CO2 are always recent values.

v1.0.17 (2025-03-21)
--------------------

Features
^^^^^^^^

- Use computer time to set RTC of instrument, if `utc_offset > 13`

v1.0.16 (2025-01-28)
--------------------

Features
^^^^^^^^

- Additional commands for DACM-32

v1.0.15 (2025-01-16)
--------------------

Bugfixes
^^^^^^^^

- Accept addressed frames from DACM instrument, even if the RS-485 address is 0

v1.0.14 (2025-01-08)
--------------------

Features
^^^^^^^^

- Support for new device Radon Scout Everywhere

v1.0.13 (2024-12-19)
--------------------

Bugfixes
^^^^^^^^

- Handle virgin or corrupted DACM modules


v1.0.4 (2024-04-03)
-------------------

Bugfixes
^^^^^^^^

- Stop a running measurement on instruments of DOSEman family automatically. (#1)


v1.0.2 (2024-03-20)
-------------------

Bugfixes
^^^^^^^^

- Speed up device detection (#1)
- Improve performance at high baudrates (#2)


v1.0.1 (2024-03-15)
-------------------

Improved Documentation
^^^^^^^^^^^^^^^^^^^^^^

- Introduce CHANGELOG and Semantic Version.
