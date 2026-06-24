"""Mapping between family_id and instrument class"""

from sarad.dacm import Dacm32Inst, DacmInst
from sarad.doseman import DosemanInst
from sarad.network import NetworkInst
from sarad.radonscout import RscInst

id_family_mapping = {
    1: DosemanInst(),
    2: RscInst(),
    4: NetworkInst(),
    5: DacmInst(),
    6: Dacm32Inst(),
}
