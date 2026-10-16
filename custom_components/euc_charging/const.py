"""Constants for the EUC Charging integration."""

import re
from collections.abc import Mapping
from enum import Enum
from typing import Any

DOMAIN = "euc_charging"

# BLE UUIDs for different EUC brands
# KingSong UUIDs
KINGSONG_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
KINGSONG_READ_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Gotway/Begode UUIDs (same as KingSong)
GOTWAY_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
GOTWAY_READ_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Veteran/Leaperkim UUIDs (same as KingSong/Gotway)
VETERAN_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
VETERAN_READ_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# InMotion V1 UUIDs
INMOTION_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
INMOTION_READ_UUID = "0000ffe4-0000-1000-8000-00805f9b34fb"
INMOTION_WRITE_SERVICE_UUID = "0000ffe5-0000-1000-8000-00805f9b34fb"
INMOTION_WRITE_UUID = "0000ffe9-0000-1000-8000-00805f9b34fb"

# InMotion V2 UUIDs
INMOTION_V2_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
INMOTION_V2_READ_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
INMOTION_V2_WRITE_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Ninebot UUIDs (same as KingSong/Gotway)
NINEBOT_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
NINEBOT_READ_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
NINEBOT_WRITE_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Ninebot Z UUIDs (same as InMotion V2)
NINEBOT_Z_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NINEBOT_Z_READ_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
NINEBOT_Z_WRITE_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

# Descriptor UUID (common for all)
DESCRIPTOR_UUID = "00002902-0000-1000-8000-00805f9b34fb"

# Legacy constants (for backward compatibility)
SERVICE_UUID = VETERAN_SERVICE_UUID
NOTIFY_UUID = VETERAN_READ_UUID


class WheelBrand(Enum):
    """Supported EUC brands."""
    UNKNOWN = "unknown"
    KINGSONG = "kingsong"
    GOTWAY = "gotway"
    BEGODE = "begode"  # Alias for Gotway
    VETERAN = "veteran"
    LEAPERKIM = "leaperkim"  # Alias for Veteran
    INMOTION = "inmotion"
    INMOTION_V2 = "inmotion_v2"
    NINEBOT = "ninebot"
    NINEBOT_Z = "ninebot_z"


# Map service UUIDs to brands (for discovery)
SERVICE_UUID_TO_BRAND = {
    KINGSONG_SERVICE_UUID: [WheelBrand.KINGSONG, WheelBrand.GOTWAY, WheelBrand.VETERAN, WheelBrand.NINEBOT],
    INMOTION_SERVICE_UUID: [WheelBrand.INMOTION],
    INMOTION_V2_SERVICE_UUID: [WheelBrand.INMOTION_V2, WheelBrand.NINEBOT_Z],
}

# All unique service UUIDs for discovery
ALL_SERVICE_UUIDS = [
    KINGSONG_SERVICE_UUID,
    INMOTION_V2_SERVICE_UUID,
]

# Brand-specific device name patterns for discovery
BRAND_DEVICE_NAMES = {
    WheelBrand.KINGSONG: ["KS-", "KingSong", "King Song"],
    WheelBrand.GOTWAY: ["GW", "Gotway", "Begode", "MCM", "Monster", "MSX", "Nikola", "RS"],
    WheelBrand.VETERAN: ["LK", "Sherman", "Veteran", "Abrams", "Patton", "Lynx", "Sherman L", "Oryx"],
    WheelBrand.INMOTION: ["InMotion", "V5", "V8", "V10", "V11", "Glide"],
    WheelBrand.INMOTION_V2: ["InMotion", "V11", "V12", "V13", "V14"],
    WheelBrand.NINEBOT: ["Ninebot", "Nine", "A1", "C", "E+", "P", "S2", "miniPRO"],
    WheelBrand.NINEBOT_Z: ["Ninebot Z", "Ninebot-Z", "Z6", "Z8", "Z10"],
}

# All device names for discovery
DEVICE_NAMES = list({name for names in BRAND_DEVICE_NAMES.values() for name in names})

# Patterns this short are model codes ("C", "P", "V8", "LK"); matching them
# anywhere in a name gives false positives (e.g. "JBL Tune 770NC").
_SHORT_PATTERN_LEN = 3


def _name_matches(name: str, pattern: str) -> bool:
    """Return True if a BLE device name matches a brand name pattern."""
    name, pattern = name.lower(), pattern.lower()
    if len(pattern) > _SHORT_PATTERN_LEN:
        return pattern in name
    # Short patterns must start the name. A pattern ending in a letter must not
    # run into more letters ("LK14132" matches LK, "LKQ Parts" and "Cardo" do
    # not); one ending in a digit or symbol may ("V8F-1234", "V12HS", "KS-S18").
    if not name.startswith(pattern):
        return False
    rest = name[len(pattern):]
    return not rest or not (pattern[-1].isalpha() and rest[0].isalpha())


def match_brand_by_name(name: str | None) -> WheelBrand | None:
    """Return the wheel brand whose name pattern best matches a BLE device name.

    The longest matching pattern wins, so "Ninebot Z10" is Ninebot Z, not Ninebot.
    """
    if not name:
        return None
    best: tuple[int, WheelBrand] | None = None
    for brand, patterns in BRAND_DEVICE_NAMES.items():
        for pattern in patterns:
            if _name_matches(name, pattern) and (best is None or len(pattern) > best[0]):
                best = (len(pattern), brand)
    return best[1] if best else None

# Battery cell configurations (number of cells in series)
CELL_CONFIG = {
    "16S": {"cells": 16, "max_voltage": 67.2, "nominal_voltage": 59.2},
    "20S": {"cells": 20, "max_voltage": 84.0, "nominal_voltage": 74.0},
    "24S": {"cells": 24, "max_voltage": 100.8, "nominal_voltage": 88.8},
    "30S": {"cells": 30, "max_voltage": 126.0, "nominal_voltage": 111.0},
    "36S": {"cells": 36, "max_voltage": 151.2, "nominal_voltage": 133.2},
    "42S": {"cells": 42, "max_voltage": 176.4, "nominal_voltage": 155.4},
}

CONF_RETRY_COUNT = "retry_count"
DEFAULT_RETRY_COUNT = 3
CONF_BRAND = "brand"

# Persistence of "last known" values across Home Assistant restarts.
# Stored in .storage/euc_charging.<entry_id>
STORAGE_VERSION = 1
# Telemetry arrives many times per second, so writes are debounced. Home Assistant
# flushes any pending delayed save on shutdown, so nothing is lost on a clean restart.
STORAGE_SAVE_DELAY = 30


def sanitize_wheel_id(device_name: str) -> str:
    """Extract and sanitize wheel identifier from Bluetooth device name.

    Examples:
        "LK3336" -> "lk3336"
        "Sherman-L" -> "sherman_l"
        "KS-16X" -> "ks_16x"
        "My Veteran Wheel" -> "my_veteran_wheel"

    Args:
        device_name: The Bluetooth device name

    Returns:
        Sanitized identifier suitable for entity IDs
    """
    if not device_name:
        return "euc"

    # Convert to lowercase
    sanitized = device_name.lower()

    # Replace spaces and hyphens with underscores
    sanitized = re.sub(r'[\s\-]+', '_', sanitized)

    # Remove any characters that aren't alphanumeric or underscore
    sanitized = re.sub(r'[^a-z0-9_]', '', sanitized)

    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')

    # If empty after sanitization, use default
    if not sanitized:
        return "euc"

    return sanitized


# TPMS (Motoeye "VD" BLE advertisement sensors)
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_TPMS = "tpms"
CONF_WHEEL_ADDRESS = "wheel_address"
CONF_MIN_PRESSURE_PSI = "min_pressure_psi"
DEFAULT_MIN_PRESSURE_PSI = 30.0
TPMS_MANUFACTURER_ID = 0x3000
TPMS_LOW_BATTERY_PERCENT = 20
KPA_PER_PSI = 6.894757


def is_tpms_entry(data: Mapping[str, Any]) -> bool:
    """Return True if config entry data describes a TPMS sensor."""
    return data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TPMS

