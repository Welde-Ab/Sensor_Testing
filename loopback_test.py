#!/usr/bin/env python3
# loopback_test.py — run with TX shorted to RX, NO sensor connected
import serial, time

PORTS = ["/dev/serial0", "/dev/ttyAMA0", "/dev/ttyAMA2", "/dev/ttyS0"]

for port in PORTS:
    try:
        ser = serial.Serial(port, 115200, timeout=1)
        ser.write(b"\x7E\x00\xD3\x00\x2C\x7E")   # reset frame
        time.sleep(0.1)
        data = ser.read(32)
        ser.close()
        if data:
            print(f"✓ {port} — loopback working, received: {data.hex()}")
        else:
            print(f"✗ {port} — no loopback data received")
    except Exception as e:
        print(f"✗ {port} — {e}")
