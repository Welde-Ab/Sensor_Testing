#!/usr/bin/env python3
"""
SPS30 UART/SHDLC Driver — Pi 5 hardened version
Fixes: auto port detection, wakeup pulse, longer timeouts
"""

import serial, serial.tools.list_ports
import struct, time, sys

UART_BAUD    = 115200
UART_TIMEOUT = 3.0        # increased from 2.0

START_STOP   = 0x7E
STUFF_BYTE   = 0x7D
STUFF_MAP    = {0x7E: 0x5E, 0x7D: 0x5D, 0x11: 0x31, 0x13: 0x33}
UNSTUFF_MAP  = {v: k for k, v in STUFF_MAP.items()}

CMD_START_MEAS = 0x00
CMD_STOP_MEAS  = 0x01
CMD_READ_MEAS  = 0x03
CMD_SLEEP      = 0x10
CMD_WAKEUP     = 0x11
CMD_RESET      = 0xD3
CMD_GET_SERIAL = 0xD0
CMD_GET_FW_VER = 0xD1

# Ports to try in order (Pi 5 may use ttyAMA0 or ttyAMA2)
CANDIDATE_PORTS = [
    "/dev/serial0",
    "/dev/ttyAMA0",
    "/dev/ttyAMA2",
    "/dev/ttyAMA3",
    "/dev/ttyS0",
]


# ── SHDLC helpers ────────────────────────────────────────────────────
def _checksum(data: list) -> int:
    return (~sum(data)) & 0xFF

def _stuff(data: list) -> list:
    out = []
    for b in data:
        if b in STUFF_MAP:
            out += [STUFF_BYTE, STUFF_MAP[b]]
        else:
            out.append(b)
    return out

def _unstuff(data: list) -> list:
    out, esc = [], False
    for b in data:
        if esc:
            out.append(UNSTUFF_MAP.get(b, b)); esc = False
        elif b == STUFF_BYTE:
            esc = True
        else:
            out.append(b)
    return out

def build_frame(cmd: int, data: list = None) -> bytes:
    data   = data or []
    raw    = [0x00, cmd, len(data)] + data
    raw   += [_checksum(raw)]
    return bytes([START_STOP] + _stuff(raw) + [START_STOP])

def parse_frame(raw: bytes) -> tuple:
    inner = list(raw)
    if inner and inner[0]  == START_STOP: inner = inner[1:]
    if inner and inner[-1] == START_STOP: inner = inner[:-1]
    u = _unstuff(inner)
    if len(u) < 5:
        raise ValueError(f"Frame too short: {u}")
    addr, cmd, state, length = u[0], u[1], u[2], u[3]
    data = u[4:4+length]
    chk  = u[4+length]
    if chk != _checksum([addr, cmd, state, length] + data):
        raise ValueError("Checksum mismatch")
    if state != 0:
        errors = {
            0x01:"Wrong data length", 0x02:"Unknown command",
            0x04:"Illegal parameter", 0x43:"Wrong state (already measuring?)"
        }
        raise RuntimeError(f"Sensor error: {errors.get(state, f'state={state:#04x}')}")
    return cmd, state, data


# ── Auto port detection ───────────────────────────────────────────────
def find_serial_port() -> str:
    """Try each candidate port, return first one that opens successfully."""
    print("[DIAG] Looking for serial port...")
    for port in CANDIDATE_PORTS:
        try:
            s = serial.Serial(port, UART_BAUD, timeout=0.5)
            s.close()
            print(f"  ✓ Found: {port}")
            return port
        except (serial.SerialException, FileNotFoundError):
            print(f"  ✗ Not available: {port}")

    print("\n✗ No serial port found. Fix steps:")
    print("  1. sudo raspi-config → Interface → Serial Port")
    print("     'Login shell over serial?' → No")
    print("     'Serial hardware enabled?' → Yes")
    print("  2. Add to /boot/firmware/config.txt:")
    print("       dtoverlay=disable-bt")
    print("       enable_uart=1")
    print("  3. sudo reboot")
    sys.exit(1)


# ── Driver ───────────────────────────────────────────────────────────
class SPS30:
    def __init__(self, port: str = None, baud: int = UART_BAUD):
        port = port or find_serial_port()
        self.ser = serial.Serial(
            port=port, baudrate=baud,
            bytesize=8, parity='N', stopbits=1,
            timeout=UART_TIMEOUT,
            xonxoff=False, rtscts=False, dsrdtr=False,
        )
        self._measuring = False
        print(f"[SPS30] Opened {port}")

    def _transact(self, cmd: int, data: list = None, rbytes: int = 64) -> list:
        frame = build_frame(cmd, data)
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        resp = self._read_frame()
        _, _, rdata = parse_frame(resp)
        return rdata

    def _read_frame(self) -> bytes:
        buf      = bytearray()
        in_frame = False
        deadline = time.time() + UART_TIMEOUT

        while time.time() < deadline:
            b = self.ser.read(1)
            if not b:
                continue
            byte = b[0]
            if byte == START_STOP:
                if not in_frame:
                    in_frame = True
                    buf = bytearray([START_STOP])
                else:
                    buf.append(START_STOP)
                    return bytes(buf)
            elif in_frame:
                buf.append(byte)

        # ── Timeout: give useful diagnostics ─────────────────────────
        print("\n✗ Timeout waiting for response frame.")
        print("  Bytes received so far:", buf.hex() if buf else "none")
        if not buf:
            print("  → Pi is not receiving ANYTHING from sensor")
            print("  → Most likely causes:")
            print("    1. TX/RX wires are SWAPPED — try swapping them")
            print("    2. Sensor not powered — check VDD and shared GND")
            print("    3. SEL not at 3.3V — required for UART mode")
            print("    4. Run loopback_test.py to verify UART hardware works")
        else:
            print("  → Partial frame received — possible baud rate mismatch or noise")
        raise TimeoutError("No complete frame received")

    # ── Wakeup ────────────────────────────────────────────────────────
    def wakeup(self):
        """
        Pi 5 wakeup sequence:
          1. Send 0xFF byte (breaks any sleep state)
          2. Wait 100ms
          3. Send wakeup SHDLC frame (response is often silently ignored)
        """
        print("[SPS30] Waking up...")
        self.ser.reset_input_buffer()
        self.ser.write(bytes([0xFF]))     # wakeup pulse
        time.sleep(0.1)
        self.ser.write(build_frame(CMD_WAKEUP))
        time.sleep(0.1)
        self.ser.reset_input_buffer()     # discard any partial response
        print("[SPS30] Wakeup done")

    def reset(self):
        self._transact(CMD_RESET)
        self._measuring = False
        time.sleep(0.1)
        print("[SPS30] Reset OK")

    def start(self):
        self._transact(CMD_START_MEAS, [0x01, 0x03, 0x00])
        self._measuring = True
        print("[SPS30] Measurement started")

    def stop(self):
        try: self._transact(CMD_STOP_MEAS)
        except Exception: pass
        self._measuring = False

    def get_serial(self) -> str:
        d = self._transact(CMD_GET_SERIAL)
        return bytes(d).decode("ascii", errors="replace").strip("\x00")

    def get_firmware(self) -> str:
        d = self._transact(CMD_GET_FW_VER)
        return f"{d[0]}.{d[1]}" if len(d) >= 2 else "unknown"

    def read(self) -> dict:
        if not self._measuring:
            raise RuntimeError("Call start() first")
        data = self._transact(CMD_READ_MEAS)
        if len(data) < 40:
            raise ValueError(f"Short response: {len(data)} bytes, expected 40")
        f = lambda i: round(struct.unpack(">f", bytes(data[i:i+4]))[0], 2)
        return {
            "pm1_0":        f(0),
            "pm2_5":        f(4),
            "pm4_0":        f(8),
            "pm10":         f(12),
            "nc0_5":        f(16),
            "nc1_0":        f(20),
            "nc2_5":        f(24),
            "nc4_0":        f(28),
            "nc10":         f(32),
            "typical_size": f(36),
        }

    def close(self):
        self.stop()
        self.ser.close()


# ── Display ───────────────────────────────────────────────────────────
AQI = [(5,"Good","🟢"),(15,"Moderate","🟡"),(25,"Unhealthy","🟠"),
       (50,"Very Unhealthy","🔴"),(float("inf"),"Hazardous","🟣")]

def aqi_label(pm25):
    for limit, label, emoji in AQI:
        if pm25 <= limit: return label, emoji
    return "Hazardous", "🟣"

def print_data(d):
    label, emoji = aqi_label(d["pm2_5"])
    print(f"\n{'─'*48}")
    print(f"  Air Quality : {emoji}  {label}")
    print(f"{'─'*48}")
    print("  Mass Concentration  (µg/m³)")
    for k in ("pm1_0","pm2_5","pm4_0","pm10"):
        print(f"    {k:10s} : {d[k]:8.2f}")
    print("  Number Concentration  (#/cm³)")
    for k in ("nc0_5","nc1_0","nc2_5","nc4_0","nc10"):
        print(f"    {k:10s} : {d[k]:8.2f}")
    print(f"  Typical Size: {d['typical_size']:.2f} µm")


# ── Main ──────────────────────────────────────────────────────────────
def main():
    WARMUP_SEC   = 30
    INTERVAL_SEC = 5

    sensor = SPS30()   # auto-detects port
    try:
        sensor.wakeup()
        sensor.reset()
        print(f"  Serial  : {sensor.get_serial()}")
        print(f"  Firmware: v{sensor.get_firmware()}")
        sensor.start()
        print(f"  Warming up {WARMUP_SEC}s…")
        time.sleep(WARMUP_SEC)
        print("  Reading (Ctrl-C to stop)")
        while True:
            print_data(sensor.read())
            time.sleep(INTERVAL_SEC)
    except KeyboardInterrupt:
        print("\nStopped.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        raise
    finally:
        sensor.close()
        print("[SPS30] Closed.")

if __name__ == "__main__":
    main()

## Decision tree for your error

"No complete frame received"
