#!/usr/bin/env python3
"""
Unified TGS2603 + TGS2620 + SHT45 Monitor → InfluxDB
- Reads two gas sensors via MCP3002 (SPI)
- Reads temp/humidity via SHT45 (I²C)
- Calculates Rs, Rs/Ro, PPM ethanol approx for both sensors
- Logs everything to InfluxDB + prints to terminal
"""

import spidev
import time
import sys
import board
import adafruit_sht4x
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ────────────────────────────────────────────────
# Configuration
# ────────────────────────────────────────────────

# InfluxDB
INFLUX_URL    = "http://192.168.188.141:8086"
INFLUX_TOKEN  = "fLR9lwuVna4BnodWtA05DP8JJbXGA91P3ORSOB0EvoFDDEIrF1XQQ2lbR_BbEgwvcX3nK9laKtzBZ1_xWd0MNg=="    # ← replace!
INFLUX_ORG    = "free-tech"                   # ← replace!
INFLUX_BUCKET = "figaro_sht45"                    # your bucket

# Sensor parameters (adjust after calibration)
VREF = 5.0                # MCP3002 reference voltage
VC   = 5.0                # Circuit voltage for gas sensors
RL   = 10000.0            # Trimmer resistance (ohms) - same for both initially

RO_2603 = 17000.0         # Baseline Rs for TGS2603 in clean air (UPDATE!)
RO_2620 = 17000.0         # Baseline Rs for TGS2620 in clean air (UPDATE!)

PPM_EXPONENT = 0.55       # Tune: higher = flatter curve (0.50–0.65 typical)

READ_INTERVAL = 1.0       # seconds between readings

# ────────────────────────────────────────────────
# InfluxDB Setup
# ────────────────────────────────────────────────
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

# ────────────────────────────────────────────────
# SPI Setup (MCP3002)
# ────────────────────────────────────────────────
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)           # bus 0, CE0
    spi.max_speed_hz = 500000  # 500 kHz - more stable than 1 MHz
except Exception as e:
    print("SPI error:", e)
    sys.exit(1)

def read_mcp3002(channel=0):
    """Read from MCP3002 CH0 or CH1"""
    if channel not in (0, 1):
        return -1
    cmd = 0b10000000 if channel == 0 else 0b11000000
    try:
        reply = spi.xfer2([1, cmd, 0])
        value = ((reply[1] & 0x03) << 8) | reply[2]
        return value
    except Exception as e:
        print(f"SPI read error on CH{channel}: {e}")
        return -1

# ────────────────────────────────────────────────
# SHT45 Setup (I²C)
# ────────────────────────────────────────────────
try:
    i2c = board.I2C()
    sht = adafruit_sht4x.SHT4x(i2c)
    sht.mode = adafruit_sht4x.Mode.HIGH_PRECISION_HIGH_HEATER_OFF
    print("SHT45 detected")
except Exception as e:
    print("SHT45 init error:", e)
    sht = None

# ────────────────────────────────────────────────
# Main Loop
# ────────────────────────────────────────────────
print("Unified TGS2603 + TGS2620 + SHT45 Logger")
print(f"Bucket: {INFLUX_BUCKET} | Interval: {READ_INTERVAL}s")
print("-" * 60)

try:
    while True:
        timestamp = time.time()

        # ── Gas sensors ────────────────────────────────────────
        adc_2603 = read_mcp3002(0)
        adc_2620 = read_mcp3002(1)

        voltage_2603 = (adc_2603 / 1023.0) * VREF if adc_2603 >= 0 else 0
        voltage_2620 = (adc_2620 / 1023.0) * VREF if adc_2620 >= 0 else 0

        # Rs for TGS2603
        rs_2603 = RL * (voltage_2603 / (VC - voltage_2603)) if (VC - voltage_2603) > 0.01 else float('inf')
        rs_ro_2603 = rs_2603 / RO_2603 if RO_2603 > 0 else 1.0
        ppm_2603 = (1.0 / rs_ro_2603) ** (1.0 / PPM_EXPONENT) if 0 < rs_ro_2603 < 1.0 else 0.0

        # Rs for TGS2620
        rs_2620 = RL * (voltage_2620 / (VC - voltage_2620)) if (VC - voltage_2620) > 0.01 else float('inf')
        rs_ro_2620 = rs_2620 / RO_2620 if RO_2620 > 0 else 1.0
        ppm_2620 = (1.0 / rs_ro_2620) ** (1.0 / PPM_EXPONENT) if 0 < rs_ro_2620 < 1.0 else 0.0

        # ── Temperature & Humidity ─────────────────────────────
        temp_c = 0.0
        hum_rh = 0.0
        if sht:
            try:
                temp_c = sht.temperature
                hum_rh = sht.relative_humidity
            except Exception as e:
                print("SHT45 read error:", e)

        # ── InfluxDB Points ────────────────────────────────────
        p_gas = Point("gas_sensors") \
            .tag("location", "osaka") \
            .field("adc_2603", float(adc_2603)) \
            .field("voltage_2603", voltage_2603) \
            .field("rs_kohm_2603", rs_2603/1000.0) \
            .field("rs_ro_2603", rs_ro_2603) \
            .field("ppm_2603", ppm_2603) \
            .field("adc_2620", float(adc_2620)) \
            .field("voltage_2620", voltage_2620) \
            .field("rs_kohm_2620", rs_2620/1000.0) \
            .field("rs_ro_2620", rs_ro_2620) \
            .field("ppm_2620", ppm_2620)

        p_env = Point("environment") \
            .tag("location", "osaka") \
            .field("temperature_c", temp_c) \
            .field("humidity_percent", hum_rh)

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=[p_gas, p_env])

        # ── Console output ─────────────────────────────────────
        print(
            f"ADC2603:{adc_2603:4d} V:{voltage_2603:5.3f} Rs:{rs_2603/1000:5.1f}k "
            f"Rs/Ro:{rs_ro_2603:5.2f} PPM:{ppm_2603:6.1f} | "
            f"ADC2620:{adc_2620:4d} V:{voltage_2620:5.3f} Rs:{rs_2620/1000:5.1f}k "
            f"Rs/Ro:{rs_ro_2620:5.2f} PPM:{ppm_2620:6.1f} | "
            f"T:{temp_c:5.1f}°C  H:{hum_rh:5.1f}%".replace("inf", "∞"),
            flush=True
        )

        time.sleep(READ_INTERVAL)

except KeyboardInterrupt:
    print("\nStopped by user.")

except Exception as e:
    print("\nFatal error:", e)

finally:
    spi.close()
    client.close()
    print("Clean shutdown.")
