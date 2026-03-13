#!/usr/bin/env python3
"""
SPS30 via UART → InfluxDB 2.x
Using the correct API from sensirion-uart-sps30 documentation
"""

import time
import sys
from datetime import datetime

# Correct imports for sensirion-uart-sps30
from sensirion_shdlc_driver import ShdlcSerialPort
from sensirion_driver_adapters.shdlc_adapter.shdlc_channel import ShdlcChannel
from sensirion_uart_sps30.device import Sps30Device
from sensirion_uart_sps30.commands import OutputFormat

# InfluxDB 2.x
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ────────────────────────────────────────────────
# CONFIGURATION – CHANGE THESE
# ────────────────────────────────────────────────

# UART port on Raspberry Pi
UART_PORT     = "/dev/ttyAMA0"      # or "/dev/ttyAMA0" or "/dev/ttyS0"
BAUDRATE      = 9600

# InfluxDB
INFLUX_URL    = "http://192.168.188.141:8086"
INFLUX_TOKEN  = "fLR9lwuVna4BnodWtA05DP8JJbXGA91P3ORSOB0EvoFDDEIrF1XQQ2lbR_BbEgwvcX3nK9laKtzBZ1_xWd0MNg=="          # ← REQUIRED
INFLUX_ORG    = "free-tech"                 # ← REQUIRED
INFLUX_BUCKET = "sps30_data"                       # your bucket

# Measurement interval (seconds)
INTERVAL      = 1.0

LOCATION      = "Numazu"

# ────────────────────────────────────────────────
# InfluxDB Client
# ────────────────────────────────────────────────
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

# ────────────────────────────────────────────────
# SPS30 UART Setup
# ────────────────────────────────────────────────
try:
    port = ShdlcSerialPort(port=UART_PORT, baudrate=BAUDRATE)
    channel = ShdlcChannel(port)
    sps30 = Sps30Device(channel)

    print("SPS30 connected via UART")

    # Start continuous measurement (using float format)
    sps30.start_measurement(OutputFormat(261))  # 261 = float

    print("Measurement started – waiting for first valid reading...")
    time.sleep(5)  # Give time to stabilize

except Exception as e:
    print(f"SPS30 initialization failed: {e}")
    sys.exit(1)

# ────────────────────────────────────────────────
# Main Loop
# ────────────────────────────────────────────────
print(f"Logging SPS30 data to InfluxDB every {INTERVAL:.1f}s...")
print("Press Ctrl+C to stop\n")

try:
    while True:
        try:
            # Read latest measurement (float values)
            (mc_1p0, mc_2p5, mc_4p0, mc_10p0, nc_0p5, nc_1p0, nc_2p5, nc_4p0, nc_10p0, typical_particle_size) = sps30.read_measurement_values_float()

            data = {
                "pm1_0":     mc_1p0,
                "pm2_5":     mc_2p5,
                "pm4_0":     mc_4p0,
                "pm10":      mc_10p0,
                "nc0_5":     nc_0p5,
                "nc1_0":     nc_1p0,
                "nc2_5":     nc_2p5,
                "nc4_0":     nc_4p0,
                "nc10":      nc_10p0,
                "typical_size": typical_particle_size,
            }

            # Build InfluxDB point
            point = Point("sps30") \
                .tag("sensor", "SPS30_UART") \
                .tag("location", LOCATION) \
                .field("pm1_0_ugm3",    data["pm1_0"]) \
                .field("pm2_5_ugm3",    data["pm2_5"]) \
                .field("pm4_0_ugm3",    data["pm4_0"]) \
                .field("pm10_ugm3",     data["pm10"]) \
                .field("nc0_5_cm3",     data["nc0_5"]) \
                .field("nc1_0_cm3",     data["nc1_0"]) \
                .field("nc2_5_cm3",     data["nc2_5"]) \
                .field("nc4_0_cm3",     data["nc4_0"]) \
                .field("nc10_cm3",      data["nc10"]) \
                .field("typical_size_um", data["typical_size"])

            # Write
            write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

            # Console print
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] PM2.5: {data['pm2_5']:5.2f} µg/m³ | PM10: {data['pm10']:5.2f} µg/m³")

        except Exception as e:
            print(f"Read/write error: {e}")

        time.sleep(INTERVAL)

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    # Clean shutdown
    try:
        sps30.stop_measurement()
        print("SPS30 measurement stopped")
    except:
        pass

    port.close()
    client.close()
    print("Clean shutdown.")
