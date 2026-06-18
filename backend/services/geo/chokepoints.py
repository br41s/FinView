"""Maritime chokepoints + ship-type classifiers (shared by the AIS collector
and the vessel-traffic analyst). Ported from WorldHawk's ais-analyst.ts.
"""

from dataclasses import dataclass

# AIS ship-type code ranges.
TANKER_RANGE = (80, 89)
CARGO_RANGE = (70, 79)


def is_tanker(ship_type: int) -> bool:
    return TANKER_RANGE[0] <= ship_type <= TANKER_RANGE[1]


def is_cargo(ship_type: int) -> bool:
    return CARGO_RANGE[0] <= ship_type <= CARGO_RANGE[1]


@dataclass(frozen=True)
class Chokepoint:
    id: str
    name: str
    region: str  # maps to GEO_REGIONS
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    normal_tankers: int
    normal_cargo: int
    drop_threshold: float  # % drop (0-1) to trigger
    spike_threshold: float  # % spike (0-1) to trigger


CHOKEPOINTS: tuple[Chokepoint, ...] = (
    Chokepoint("hormuz", "Strait of Hormuz", "strait_of_hormuz", 24, 28, 54, 58, 25, 15, 0.4, 0.6),
    Chokepoint("suez", "Suez Canal / Red Sea", "suez_red_sea", 12, 32, 32, 44, 20, 30, 0.4, 0.5),
    Chokepoint("malacca", "Malacca Strait", "malacca_strait", -2, 7, 98, 106, 30, 40, 0.4, 0.5),
    Chokepoint("panama", "Panama Canal", "panama_canal", 7, 10, -81, -78, 8, 12, 0.35, 0.6),
    Chokepoint("south-china-sea", "South China Sea", "south_china_sea", 4, 24, 105, 121, 40, 60, 0.35, 0.5),
    Chokepoint("cape-good-hope", "Cape of Good Hope", "cape_good_hope", -40, -32, 16, 22, 10, 15, 0.5, 0.8),
)
