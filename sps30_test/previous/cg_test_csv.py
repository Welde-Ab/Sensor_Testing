#!/usr/bin/env python3
import csv
import time
from datetime import datetime

from sensirion_shdlc_driver import ShdlcSerialPort
from sensirion_driver_adapters.shdlc_adapter.shdlc_channel import ShdlcChannel
from sensirion_uart_sps30.device import Sps30Device
from sensirion_uart_sps30.commands import OutputFormat

UART_PORT = "/dev/ttyAMA0"
BAUDRATE = 115200
CSV_FILE = "sps30_log.csv"

port = ShdlcSerialPort(port=UART_PORT, baudrate=BAUDRATE, additional_response_time=0.02)
channel = ShdlcChannel(port)
sensor = Sps30Device(channel)

try:
    print("Serial number:", sensor.read_serial_number())
    print("Product type :", sensor.read_product_type())

    try:
        sensor.stop_measurement()
        time.sleep(0.5)
    except Exception:
        pass

    sensor.start_measurement(OutputFormat(261))
    time.sleep(2)

    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.writer(f)

        writer.writerow([
            "timestamp", "pm1_0", "pm2_5", "pm4_0", "pm10",
            "nc0_5", "nc1_0", "nc2_5", "nc4_0", "nc10",
            "typical_particle_size_um"
        ])

        print("Logging... Press Ctrl+C to stop.")
        while True:
            values = sensor.read_measurement_values_uint16()
            (
                pm1, pm25, pm4, pm10,
                nc05, nc1, nc25, nc4, nc10,
                tps
            ) = values

            ts = datetime.now().isoformat(timespec="seconds")
            tps_um = tps / 1000.0

            writer.writerow([ts, pm1, pm25, pm4, pm10, nc05, nc1, nc25, nc4, nc10, tps_um])
            f.flush()

            print(f"{ts}  PM2.5={pm25}  PM10={pm10}  TPS={tps_um:.3f} µm")
            time.sleep(2)

except KeyboardInterrupt:
    print("\nStopping...")

finally:
    try:
        sensor.stop_measurement()
    except Exception:
        pass
    port.close()
