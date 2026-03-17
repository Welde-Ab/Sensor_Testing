"""
config.py  –  Edit this file before flashing to your Pico 2W.
"""

# ── Wi-Fi ────────────────────────────────────────────────────────────────────
WIFI_SSID     = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
WIFI_TIMEOUT  = 30          # seconds to wait for connection

# ── InfluxDB ─────────────────────────────────────────────────────────────────
# For InfluxDB Cloud (v2):
INFLUX_HOST   = "us-east-1-1.aws.cloud2.influxdata.com"   # Cloud hostname
INFLUX_PORT   = 443
INFLUX_SSL    = True
INFLUX_TOKEN  = "YOUR_INFLUXDB_API_TOKEN"
INFLUX_ORG    = "YOUR_ORG_NAME"
INFLUX_BUCKET = "air_quality"

# For local InfluxDB OSS v2 (comment out the Cloud block and uncomment this):
# INFLUX_HOST   = "192.168.1.100"
# INFLUX_PORT   = 8086
# INFLUX_SSL    = False
# INFLUX_TOKEN  = "YOUR_API_TOKEN"
# INFLUX_ORG    = "home"
# INFLUX_BUCKET = "air_quality"

# For InfluxDB v1 / local (set INFLUX_TOKEN = None):
# INFLUX_HOST     = "192.168.1.100"
# INFLUX_PORT     = 8086
# INFLUX_SSL      = False
# INFLUX_TOKEN    = None
# INFLUX_ORG      = None
# INFLUX_BUCKET   = "air_quality"
# INFLUX_USERNAME = "admin"
# INFLUX_PASSWORD = "secret"

# ── SPS30 I2C pins (Pico 2W) ─────────────────────────────────────────────────
I2C_ID  = 0       # I2C bus number (0 or 1)
I2C_SDA = 4       # GPIO4  → SDA
I2C_SCL = 5       # GPIO5  → SCL
I2C_FREQ = 100_000  # 100 kHz (SPS30 supports up to 400 kHz)

# ── Measurement settings ──────────────────────────────────────────────────────
MEASUREMENT_NAME    = "air_quality"
SAMPLE_INTERVAL_S   = 10       # seconds between samples
WARMUP_S            = 5        # seconds after start_measurement before reading
LOCATION_TAG        = "office" # InfluxDB tag: location
SENSOR_TAG          = "sps30"  # InfluxDB tag: sensor model

# ── Retry / error handling ────────────────────────────────────────────────────
MAX_WIFI_RETRIES    = 3        # reconnect attempts before hard reset
INFLUX_RETRY_COUNT  = 3        # retries on failed HTTP write
INFLUX_RETRY_DELAY  = 5        # seconds between retries
