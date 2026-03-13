#!/usr/bin/env python3
import csv
import os
import time
from datetime import datetime, timezone

import influxdb_client
from influxdb_client import Point
from influxdb_client.client.write_api import SYNCHRONOUS

from sensirion_shdlc_driver import ShdlcSerialPort
from sensirion_driver_adapters.shdlc_adapter.shdlc_channel import ShdlcChannel
from sensirion_uart_sps30.device import Sps30Device
from sensirion_uart_sps30.commands import OutputFormat

# -----------------------------
# SPS30 settings
# -----------------------------
UART_PORT = "/dev/ttyAMA0"
BAUDRATE = 115200
SAMPLE_INTERVAL_SECONDS = 1

# -----------------------------
# InfluxDB settings
# -----------------------------
INFLUX_URL = "http://192.168.188.141:8086"
INFLUX_TOKEN = "fLR9lwuVna4BnodWtA05DP8JJbXGA91P3ORSOB0EvoFDDEIrF1XQQ2lbR_BbEgwvcX3nK9laKtzBZ1_xWd0MNg=="
INFLUX_ORG = "free-tech"
INFLUX_BUCKET = "sps30_data"
MEASUREMENT_NAME = "sps30"

# -----------------------------
# Local file settings
# -----------------------------
CSV_FILE = "sps30_log.csv"

port = None
sensor = None
client = None
csv_file = None

try:
    # ---- Connect to SPS30 ----
    port = ShdlcSerialPort(
        port=UART_PORT,
        baudrate=BAUDRATE,
        additional_response_time=0.02
    )
    channel = ShdlcChannel(port)
    sensor = Sps30Device(channel)

    serial_number = sensor.read_serial_number()
    product_type = sensor.read_product_type()

    print("Serial number:", serial_number)
    print("Product type :", product_type)

    # Stop previous measurement if already running
    try:
        sensor.stop_measurement()
        time.sleep(0.5)
    except Exception:
        pass

    sensor.start_measurement(OutputFormat(261))
    time.sleep(1)

    # ---- Connect to InfluxDB ----
    client = influxdb_client.InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    # ---- Open local CSV file ----
    file_exists = os.path.exists(CSV_FILE)
    file_empty = (not file_exists) or os.path.getsize(CSV_FILE) == 0

    csv_file = open(CSV_FILE, "a", newline="")
    writer = csv.writer(csv_file)

    if file_empty:
        writer.writerow([
            "timestamp_utc",
            "serial_number",
            "product_type",
            "pm1_0",
            "pm2_5",
            "pm4_0",
            "pm10",
            "nc0_5",
            "nc1_0",
            "nc2_5",
            "nc4_0",
            "nc10",
            "typical_particle_size_um"
        ])
        csv_file.flush()

    print("Measuring, writing to InfluxDB, and saving locally... Press Ctrl+C to stop.")

    while True:
        values = sensor.read_measurement_values_uint16()
        (
            pm1, pm25, pm4, pm10,
            nc05, nc1, nc25, nc4, nc10,
            tps
        ) = values

        tps_um = tps / 1000.0
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # ---- Write to InfluxDB ----
        point = (
            Point(MEASUREMENT_NAME)
            .tag("sensor", "SPS30")
            .tag("serial_number", str(serial_number))
            .tag("product_type", str(product_type))
            .field("pm1_0", float(pm1))
            .field("pm2_5", float(pm25))
            .field("pm4_0", float(pm4))
            .field("pm10", float(pm10))
            .field("nc0_5", float(nc05))
            .field("nc1_0", float(nc1))
            .field("nc2_5", float(nc25))
            .field("nc4_0", float(nc4))
            .field("nc10", float(nc10))
            .field("typical_particle_size_um", float(tps_um))
            .time(now)
        )

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

        # ---- Save locally to CSV ----
        writer.writerow([
            now_iso,
            serial_number,
            product_type,
            pm1,
            pm25,
            pm4,
            pm10,
            nc05,
            nc1,
            nc25,
            nc4,
            nc10,
            tps_um
        ])
        csv_file.flush()

        print(
            f"{now_iso} | "
            f"PM1.0={pm1} PM2.5={pm25} PM4.0={pm4} PM10={pm10} "
            f"TPS={tps_um:.3f} µm"
        )

        time.sleep(SAMPLE_INTERVAL_SECONDS)

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    if sensor is not None:
        try:
            sensor.stop_measurement()
        except Exception:
            pass

    if port is not None:
        try:
            port.close()
        except Exception:
            pass

    if csv_file is not None:
        try:
            csv_file.close()
        except Exception:
            pass

    if client is not None:
        try:
            client.close()
        except Exception:
            pass
