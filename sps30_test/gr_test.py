#!/usr/bin/env python3
"""
SPS30 UART Test – robust version
"""

import time

from sensirion_uart_driver import UartPort
from sensirion_uart_sps30 import Sps30Device

UART_PORT = "/dev/serial0"   # Try /dev/ttyAMA0 or /dev/ttyS0 if needed
BAUDRATE = 9600
TIMEOUT = 3.0
WARMUP_SECONDS = 15
MAX_READ_ATTEMPTS = 5
RETRY_DELAY = 2

port = None
sps30 = None

try:
    print(f"Opening UART: {UART_PORT} @ {BAUDRATE} baud...")
    port = UartPort(port=UART_PORT, baudrate=BAUDRATE, timeout=TIMEOUT)

    print("Creating SPS30 device...")
    sps30 = Sps30Device(port)

    print("Starting continuous measurement...")
    sps30.start_measurement()

    print(f"Waiting {WARMUP_SECONDS} seconds for fan spin-up and first valid reading...")
    time.sleep(WARMUP_SECONDS)

    reading = None
    for attempt in range(1, MAX_READ_ATTEMPTS + 1):
        print(f"Reading measurement... (attempt {attempt}/{MAX_READ_ATTEMPTS})")
        reading = sps30.read_measurement()
        if reading is not None:
            break
        time.sleep(RETRY_DELAY)

    if reading is not None:
        print("Success! First reading received:")
        print(f"  PM1.0  = {reading.mass_concentration_pm1_0:6.2f} µg/m³")
        print(f"  PM2.5  = {reading.mass_concentration_pm2_5:6.2f} µg/m³")
        print(f"  PM4.0  = {reading.mass_concentration_pm4_0:6.2f} µg/m³")
        print(f"  PM10   = {reading.mass_concentration_pm10:6.2f} µg/m³")
        print(f"  Typical particle size = {reading.typical_particle_size:5.2f} µm")
    else:
        print("No valid reading received.")
        print("Check wiring, UART config, SPS30 power, and try a longer warm-up.")

except Exception as e:
    print(f"Communication error: {e}")

finally:
    if sps30 is not None:
        try:
            sps30.stop_measurement()
            print("Measurement stopped.")
        except Exception as e:
            print(f"Could not stop measurement: {e}")

    if port is not None:
        try:
            port.close()
            print("UART port closed.")
        except Exception as e:
            print(f"Could not close UART port: {e}")
