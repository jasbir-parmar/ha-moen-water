"""Constants for the Moen Smart Sump Pump Monitor integration."""

DOMAIN = "moen_sump_pump"

# Sensor Types
SENSOR_WATER_LEVEL = "water_level"
SENSOR_TEMPERATURE = "temperature"
SENSOR_HUMIDITY = "humidity"
SENSOR_PUMP_CAPACITY = "pump_capacity"
SENSOR_LAST_CYCLE = "last_cycle"

# Binary Sensor Types
BINARY_SENSOR_CONNECTIVITY = "connectivity"
BINARY_SENSOR_FLOOD_RISK = "flood_risk"
BINARY_SENSOR_POWER = "power"

# Device Classes
DEVICE_CLASS_WATER_LEVEL = "distance"

# Alert Code Mappings (from decompiled Moen app strings.xml and API exploration)
# These are the common NAB (Sump Pump Monitor) alert codes
ALERT_CODES = {
    "218": "Backup Test Scheduled",  # Backup pump test scheduled
    "224": "Unknown Alert",  # Found in API but not in app strings - appears with args
    "250": "Water Detected",  # Critical - Remote sensing cable detected water
    "252": "Water Was Detected",  # Warning - Water no longer detected
    "254": "Critical Flood Risk",  # Critical flood level
    "256": "High Flood Risk",  # High water level
    "258": "Primary Pump Failed",  # Primary pump failed to engage
    "260": "Backup Pump Failed",  # Backup pump failed to engage
    "262": "Primary Pump Lagging",  # Primary pump can't keep up
    "264": "Backup Pump Lagging",  # Backup pump can't keep up
    "266": "Backup Pump Test Failed",  # Backup pump test failed
    "268": "Power Outage",  # Device on battery power
    "298": "Main Pump Not Stopping",  # Main pump continues running (from alert 224 args)
    "299": "High Water Level",  # High water level (from alert 224 args)
}

# ---------------------------------------------------------------------------
# Classic Flo API constants (shutoff valve + leak detector "puck" devices).
# This is a *separate* backend from the NAB/sump-pump API above, but both
# use the same Cognito app client, so one username/password login covers
# both device families under this single integration.
# ---------------------------------------------------------------------------

FLO_AUTH_URL = "https://api.prod.iot.moen.com/v1/oauth2/token"
FLO_API_BASE = "https://api-gw.meetflo.com/api/v2"
CLIENT_ID = "6qn9pep31dglq6ed4fvlq6rp5t"
USER_AGENT = "Smartwater-iOS-prod-3.57.0"

# Device types as returned by the classic Flo API's "deviceType" field
DEVICE_TYPE_SHUTOFF = "flo_device_v2"
DEVICE_TYPE_PUCK = "puck_oem"

FLO_DEFAULT_SCAN_INTERVAL = 60  # seconds

CONF_FLO_LOCATION_ID = "flo_location_id"

