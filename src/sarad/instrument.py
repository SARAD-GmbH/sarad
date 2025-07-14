"""Classes describing a SARAD instrument"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional


@dataclass
class Gps:
    """GPS data"""

    valid: bool
    timestamp: int = 0
    latitude: float = 0
    longitude: float = 0
    altitude: float = 0
    deviation: float = 0


@dataclass
class Route:
    """Class to store the route directing to a SaradInst.

    rs485_address and zigbee_address are optional and may be None for the
    simple case that SardInst is directly and exclusively connected to a serial
    port.

    Args:
        port (str): Name of the serial port
        rs485_address (int): RS-485 bus address. None, if RS-485 addressing is not used.
        zigbee_address (int): Address of instrument on NETmonitors coordinator.
                              None, if ZigBee is not used.
        ip_address (str): IP address for socket communication.
        ip_port (int): Port for socket communication.

    """

    port: Optional[str] = None
    rs485_address: Optional[int] = None
    zigbee_address: Optional[int] = None
    ip_address: Optional[str] = None
    ip_port: Optional[int] = None


class Measurand:  # pylint: disable=too-many-instance-attributes
    """Class providing a measurand that is delivered by a sensor.

    Properties:
        id
        name
        operator
        value
        unit
        source
        time
        gps"""

    def __init__(
        self,
        measurand_id: int,
        measurand_name: str = "",
        measurand_unit=None,
        measurand_source=None,
    ) -> None:
        self.__id: int = measurand_id
        self.__name: str = measurand_name
        if measurand_unit is not None:
            self.__unit: str = measurand_unit
        else:
            self.__unit = ""
        if measurand_source is not None:
            self.__source: int = measurand_source
        else:
            self.__source = 0
        self.__value: Optional[float] = None
        self.__time: datetime = datetime.fromtimestamp(0)
        self.__operator: str = ""
        self.__gps: Gps = Gps(valid=False)
        self.__fetched: datetime = datetime.fromtimestamp(0)
        self.__interval: timedelta = timedelta(0)

    def __str__(self) -> str:
        output = f"MeasurandId: {self.measurand_id}\nMeasurandName: {self.name}\n"
        if self.value is not None:
            output += f"Value: {self.operator} {self.value} {self.unit}\n"
            output += f"Time: {self.time}\n"
            output += f"GPS: {self.gps}\n"
        else:
            output += f"MeasurandUnit: {self.unit}\n"
            output += f"MeasurandSource: {self.source}\n"
        return output

    @property
    def measurand_id(self) -> int:
        """Return the Id of this measurand."""
        return self.__id

    @measurand_id.setter
    def measurand_id(self, measurand_id: int) -> None:
        """Set the Id of this measurand."""
        self.__id = measurand_id

    @property
    def name(self) -> str:
        """Return the name of this measurand."""
        return self.__name

    @name.setter
    def name(self, name: str) -> None:
        """Set the name of this measurand."""
        self.__name = name

    @property
    def unit(self) -> str:
        """Return the physical unit of this measurand."""
        return self.__unit

    @unit.setter
    def unit(self, unit: str) -> None:
        """Set the physical unit of this measurand."""
        self.__unit = unit

    @property
    def source(self) -> int:
        """Return the source index belonging to this measurand.

        This index marks the position the measurand can be found in the
        list of recent values provided by the instrument
        as reply to the GetComponentResult or _gather_all_recent_values
        commands respectively."""
        return self.__source

    @source.setter
    def source(self, source: int) -> None:
        """Set the source index."""
        self.__source = source

    @property
    def operator(self) -> str:
        """Return the operator belonging to this measurand.

        Typical operators are '<', '>'"""
        return self.__operator

    @operator.setter
    def operator(self, operator: str) -> None:
        """Set the operator of this measurand."""
        self.__operator = operator

    @property
    def value(self) -> Optional[float]:
        """Return the value of the measurand."""
        return self.__value

    @value.setter
    def value(self, value: Optional[float]) -> None:
        """Set the value of the measurand."""
        self.__value = value

    @property
    def time(self) -> datetime:
        """Return the aquisition time (timestamp) of the measurand."""
        return self.__time

    @time.setter
    def time(self, time_stamp: datetime) -> None:
        """Set the aquisition time (timestamp) of the measurand."""
        self.__time = time_stamp

    @property
    def gps(self) -> Gps:
        """Return the GPS object of the measurand."""
        return self.__gps

    @gps.setter
    def gps(self, gps: Gps) -> None:
        """Set the GPS object of the measurand."""
        self.__gps = gps

    @property
    def fetched(self) -> datetime:
        """Return when the value was fetched the last time."""
        return self.__fetched

    @fetched.setter
    def fetched(self, fetched: datetime) -> None:
        """Set when the value was fetched the last time."""
        self.__fetched = fetched

    @property
    def interval(self) -> timedelta:
        """Return the measuring interval of this measurand."""
        return self.__interval

    @interval.setter
    def interval(self, interval: timedelta):
        """Set the measuring interval of this measurand."""
        self.__interval = interval


class Sensor:
    """Class describing a sensor that is part of a component.

    Properties:
        id
        name
        interval: Measuring interval in seconds
    Public methods:
        get_measurands()"""

    def __init__(self, sensor_id: int, sensor_name: str = "") -> None:
        self.__id: int = sensor_id
        self.__name: str = sensor_name
        self.__interval: timedelta = timedelta(0)
        self.__measurands: Dict[int, Measurand] = {}

    def __iter__(self):
        return iter(self.__measurands)

    def __str__(self) -> str:
        output = (
            f"SensorId: {self.sensor_id}\nSensorName: {self.name}\n"
            f"SensorInterval: {self.interval}\nMeasurands:\n"
        )
        for measurand in self.measurands:
            output += f"{measurand}\n"
        return output

    @property
    def sensor_id(self) -> int:
        """Return the Id of this sensor."""
        return self.__id

    @sensor_id.setter
    def sensor_id(self, sensor_id: int) -> None:
        """Set the Id of this sensor."""
        self.__id = sensor_id

    @property
    def name(self) -> str:
        """Return the name of this sensor."""
        return self.__name

    @name.setter
    def name(self, name: str) -> None:
        """Set the name of this sensor."""
        self.__name = name

    @property
    def interval(self) -> timedelta:
        """Return the measuring interval of this sensor."""
        return self.__interval

    @interval.setter
    def interval(self, interval: timedelta):
        """Set the measuring interval of this sensor."""
        self.__interval = interval

    @property
    def measurands(self) -> Dict[int, Measurand]:
        """Return the dict of measurands of this sensor."""
        return self.__measurands

    @measurands.setter
    def measurands(self, measurands: Dict[int, Measurand]):
        """Set the dict of measurands of this sensor."""
        self.__measurands = measurands


class Component:
    """Class describing a sensor or actor component built into an instrument"""

    def __init__(self, component_id: int, component_name: str = "") -> None:
        self.__id: int = component_id
        self.__name: str = component_name
        self.__sensors: Dict[int, Sensor] = {}

    def __iter__(self):
        return iter(self.__sensors)

    def __str__(self) -> str:
        output = (
            f"ComponentId: {self.component_id}\n"
            f"ComponentName: {self.name}\nSensors:\n"
        )
        for sensor in self.sensors:
            output += f"{sensor}\n"
        return output

    @property
    def component_id(self) -> int:
        """Return the Id of this component."""
        return self.__id

    @component_id.setter
    def component_id(self, component_id: int) -> None:
        """Set the Id of this component."""
        self.__id = component_id

    @property
    def name(self) -> str:
        """Return the name of this component."""
        return self.__name

    @name.setter
    def name(self, name: str):
        """Set the component name."""
        self.__name = name

    @property
    def sensors(self) -> Dict[int, Sensor]:
        """Return the dict of sensors belonging to this component."""
        return self.__sensors

    @sensors.setter
    def sensors(self, sensors: Dict[int, Sensor]):
        """Set the dict of sensors belonging to this component."""
        self.__sensors = sensors
