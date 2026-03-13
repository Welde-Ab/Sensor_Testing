#!/usr/bin/env python3
"""
Fixed SPS30 UART reader using sensirion_uart_sps30 (official Sensirion driver)
- Uses correct start_measurement argument (output format 0x03 = IEEE754 float)
- Reads float-based measurements
- Device info via read_product_type / read_serial_number / read_version
"""

import time
import serial
from sensirion_uart_sps30.device import Sps30Device

# Configuration
PORT = "/dev/serial0"      # Pi primary UART (GPIO 14 TX → sensor RX, GPIO 15 RX → sensor TX)
BAUDRATE = 115200
OUTPUT_FORMAT_FLOAT = 0x03  # IEEE754 floating point (recommended, matches most examples)

def main():
    sensor = None
    ser = None
    try:
        print(f"Opening serial port {PORT} at {BAUDRATE} baud...")
        ser = serial.Serial(
            port=PORT,
            baudrate=BAUDRATE,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        print("Serial port opened.")

        print("Initializing SPS30...")
        sensor = Sps30Device(ser)
        print("Connected to SPS30.")

        # Read device identification (replaces non-existent read_device_info)
        try:
            product_type = sensor.read_product_type()
            serial_number = sensor.read_serial_number()
            version = sensor.read_version()
            print("\nDevice Information:")
            print(f"  Product Type: {product_type}")
            print(f"  Serial Number: {serial_number}")
            print(f"  Version: {version}")
        except Exception as e:
            print(f"Could not read device info: {e}")

        print("\nStarting continuous measurement with float output format...")
        sensor.start_measurement(OUTPUT_FORMAT_FLOAT)  # Required argument here!

        print("Waiting 15–30 seconds for fan stabilization and valid data...")
        time.sleep(20)  # Usually needs more than 10 s for first good reading

        print("\nStreaming measurements (Ctrl+C to stop)\n")
        while True:
            try:
                data = sensor.read_measured_values_float()  # Use this for float format
                if data is not None:
                    print("\n" + "=" * 60)
                    print("Mass concentrations (µg/m³):")
                    print(f"  PM1.0     : {data.mass_concentration_pm1_0:.2f}")
                    print(f"  PM2.5     : {data.mass_concentration_pm2_5:.2f}")
                    print(f"  PM4.0     : {data.mass_concentration_pm4_0:.2f}")
                    print(f"  PM10      : {data.mass_concentration_pm10:.2f}")
                    print("Number concentrations (#/cm³):")
                    print(f"  PM0.5     : {data.number_concentration_pm0_5:.2f}")
                    print(f"  PM1.0     : {data.number_concentration_pm1_0:.2f}")
                    print(f"  PM2.5     : {data.number_concentration_pm2_5:.2f}")
                    print(f"  PM4.0     : {data.number_concentration_pm4_0:.2f}")
                    print(f"  PM10      : {data.number_concentration_pm10:.2f}")
                    print(f"Typical particle size (µm): {data.typical_particle_size:.2f}")
                else:
                    print("No valid data yet...")
            except Exception as e:
                print(f"Read error: {e}")
                time.sleep(2)

            time.sleep(5)  # SPS30 updates ~1 Hz; 5 s polling is fine

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if sensor is not None:
            try:
                sensor.stop_measurement()
                print("Measurement stopped.")
            except:
                pass
        if ser is not None:
            ser.close()
            print("Serial port closed.")

if __name__ == "__main__":
    main()
