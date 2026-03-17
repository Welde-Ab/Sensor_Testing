"""
main.py  –  SPS30 → Raspberry Pi Pico 2W → InfluxDB

Wiring (I2C):
    SPS30 Pin 1 (VDD)  →  3.3V (Pico pin 36)
    SPS30 Pin 2 (SDA)  →  GPIO4  (Pico pin 6)   ← configure in config.py
    SPS30 Pin 3 (SCL)  →  GPIO5  (Pico pin 7)   ← configure in config.py
    SPS30 Pin 4 (SEL)  →  GND   (selects I2C mode)
    SPS30 Pin 5 (GND)  →  GND   (Pico pin 38)
"""

import time
import machine
import network
import sys

import config
from sps30 import SPS30
from influxdb import InfluxDBWriter


# ── LED helper ───────────────────────────────────────────────────────────────

led = machine.Pin("LED", machine.Pin.OUT)

def blink(n=1, on_ms=100, off_ms=100):
    for _ in range(n):
        led.on()
        time.sleep_ms(on_ms)
        led.off()
        time.sleep_ms(off_ms)


# ── Wi-Fi ─────────────────────────────────────────────────────────────────────

def connect_wifi(retries: int = config.MAX_WIFI_RETRIES) -> bool:
    """Connect to Wi-Fi; return True on success."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    for attempt in range(1, retries + 1):
        if wlan.isconnected():
            return True

        print(f"[WiFi] Connecting (attempt {attempt}/{retries}) …")
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)

        deadline = time.time() + config.WIFI_TIMEOUT
        while not wlan.isconnected() and time.time() < deadline:
            time.sleep_ms(500)

        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print(f"[WiFi] Connected – IP: {ip}")
            blink(3, 200, 100)
            return True

        print(f"[WiFi] Attempt {attempt} failed.")
        wlan.disconnect()
        time.sleep(2)

    return False


def ensure_wifi():
    """Reconnect Wi-Fi; hard-reset the Pico if it fails."""
    if not connect_wifi():
        print("[WiFi] Could not connect – resetting in 5 s …")
        blink(10, 50, 50)
        time.sleep(5)
        machine.reset()


# ── InfluxDB writer ───────────────────────────────────────────────────────────

def write_with_retry(writer: InfluxDBWriter, data: dict, ts: int) -> bool:
    """Write measurement data to InfluxDB with retries."""
    tags = {
        "location": config.LOCATION_TAG,
        "sensor":   config.SENSOR_TAG,
    }

    for attempt in range(1, config.INFLUX_RETRY_COUNT + 1):
        ok = writer.write(
            measurement=config.MEASUREMENT_NAME,
            fields=data,
            tags=tags,
            timestamp=ts,
        )
        if ok:
            return True
        print(f"[InfluxDB] Write failed (attempt {attempt}/{config.INFLUX_RETRY_COUNT})")
        if attempt < config.INFLUX_RETRY_COUNT:
            time.sleep(config.INFLUX_RETRY_DELAY)

    return False


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 48)
    print("  SPS30 → InfluxDB  |  Pico 2W")
    print("=" * 48)

    # 1. Wi-Fi
    ensure_wifi()

    # 2. I2C + SPS30
    i2c = machine.I2C(
        config.I2C_ID,
        sda=machine.Pin(config.I2C_SDA),
        scl=machine.Pin(config.I2C_SCL),
        freq=config.I2C_FREQ,
    )

    # Scan bus to confirm sensor is present
    devices = i2c.scan()
    print(f"[I2C] Devices found: {[hex(d) for d in devices]}")
    if SPS30.I2C_ADDR not in devices:
        print(f"[ERROR] SPS30 not found at 0x{SPS30.I2C_ADDR:02X} – check wiring!")
        blink(10, 500, 200)
        sys.exit(1)

    sensor = SPS30(i2c)
    sensor.reset()
    time.sleep_ms(200)

    try:
        ver = sensor.read_version()
        serial = sensor.read_serial()
        print(f"[SPS30] Firmware v{ver['firmware_major']}.{ver['firmware_minor']}")
        print(f"[SPS30] Serial: {serial}")
    except Exception as e:
        print(f"[SPS30] Info read failed (non-fatal): {e}")

    sensor.start_measurement()
    print(f"[SPS30] Measurement started – warming up {config.WARMUP_S} s …")
    time.sleep(config.WARMUP_S)

    # 3. InfluxDB writer
    writer_kwargs = dict(
        host=config.INFLUX_HOST,
        port=config.INFLUX_PORT,
        bucket=config.INFLUX_BUCKET,
        ssl=config.INFLUX_SSL,
    )
    if config.INFLUX_TOKEN:
        writer_kwargs.update(token=config.INFLUX_TOKEN, org=config.INFLUX_ORG)
    else:
        writer_kwargs.update(
            username=getattr(config, "INFLUX_USERNAME", None),
            password=getattr(config, "INFLUX_PASSWORD", None),
        )

    influx = InfluxDBWriter(**writer_kwargs)
    print(f"[InfluxDB] Target: {config.INFLUX_HOST}:{config.INFLUX_PORT}/{config.INFLUX_BUCKET}")

    # 4. Sampling loop
    print(f"[Loop] Sampling every {config.SAMPLE_INTERVAL_S} s …\n")
    consecutive_errors = 0

    while True:
        loop_start = time.ticks_ms()

        # ── Read sensor ──
        try:
            data = sensor.wait_and_read(timeout_s=8)
        except RuntimeError as e:
            print(f"[SPS30] Read timeout: {e}")
            consecutive_errors += 1
            if consecutive_errors >= 5:
                print("[SPS30] Too many errors – resetting sensor …")
                sensor.reset()
                time.sleep(2)
                sensor.start_measurement()
                time.sleep(config.WARMUP_S)
                consecutive_errors = 0
            time.sleep(config.SAMPLE_INTERVAL_S)
            continue

        consecutive_errors = 0

        # Pretty-print to serial
        print(
            f"PM1.0={data['pm1_0']:.1f}  PM2.5={data['pm2_5']:.1f}  "
            f"PM4.0={data['pm4_0']:.1f}  PM10={data['pm10']:.1f}  "
            f"TypSize={data['typical_size']:.2f} µm"
        )

        # ── Write to InfluxDB ──
        ts = time.time()
        ok = write_with_retry(influx, data, ts)

        if ok:
            led.on()
            time.sleep_ms(50)
            led.off()
            print(f"[InfluxDB] ✓ written at t={ts}")
        else:
            blink(5, 50, 50)
            print("[InfluxDB] ✗ write failed – continuing …")

            # Attempt Wi-Fi reconnect in case we lost the link
            wlan = network.WLAN(network.STA_IF)
            if not wlan.isconnected():
                print("[WiFi] Connection lost – reconnecting …")
                ensure_wifi()

        # ── Wait until next interval ──
        elapsed_ms = time.ticks_diff(time.ticks_ms(), loop_start)
        wait_ms = max(0, config.SAMPLE_INTERVAL_S * 1000 - elapsed_ms)
        time.sleep_ms(wait_ms)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Main] Stopped by user.")
    except Exception as e:
        import sys
        sys.print_exception(e)
        print("[Main] Unhandled exception – rebooting in 10 s …")
        time.sleep(10)
        machine.reset()
