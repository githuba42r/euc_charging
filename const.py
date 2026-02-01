"""Constants for the EUC Charging integration."""

from enum import Enum

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
    WheelBrand.VETERAN: ["LK3336", "Sherman", "Veteran", "Abrams", "Patton", "Lynx", "Sherman L", "Oryx"],
    WheelBrand.INMOTION: ["InMotion", "V5", "V8", "V10", "V11", "Glide"],
    WheelBrand.INMOTION_V2: ["InMotion", "V11", "V12", "V13", "V14"],
    WheelBrand.NINEBOT: ["Ninebot", "Nine", "A1", "C", "E+", "P", "S2", "miniPRO"],
    WheelBrand.NINEBOT_Z: ["Ninebot Z", "Ninebot-Z", "Z6", "Z8", "Z10"],
}

# All device names for discovery
DEVICE_NAMES = list({name for names in BRAND_DEVICE_NAMES.values() for name in names})

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
