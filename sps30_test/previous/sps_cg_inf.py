#!/usr/bin/env python3
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

# -----------------------------
# InfluxDB settings
# -----------------------------
INFLUX_URL = "http://192.168.188.141:8086"
INFLUX_TOKEN = "fLR9lwuVna4BnodWtA05DP8JJbXGA91P3ORSOB0EvoFDDEIrF1XQQ2lbR_BbEgwvcX3nK9laKtzBZ1_xWd0MNg=="
INFLUX_ORG = "free-tech"
INFLUX_BUCKET = "sps30_data"

MEASUREMENT_NAME = "sps30"
SAMPLE_INTERVAL_SECONDS = 1

port = None
sensor = None
client = None

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
    print("Measuring and writing to InfluxDB... Press Ctrl+C to stop.")
    time.sleep(1)

    # ---- Connect to InfluxDB ----
    client = influxdb_client.InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )
    write_api = client.write_api(write_options=SYNCHRONOUS)

    while True:
        values = sensor.read_measurement_values_uint16()
        (
            pm1, pm25, pm4, pm10,
            nc05, nc1, nc25, nc4, nc10,
            tps
        ) = values

        tps_um = tps / 1000.0
        now = datetime.now(timezone.utc)

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

        print(
            f"{now.isoformat()} | "
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

    if client is not None:
        try:
            client.close()
        except Exception:
            pass
