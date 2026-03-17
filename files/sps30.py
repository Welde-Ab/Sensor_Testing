"""
SPS30 Particulate Matter Sensor Driver for MicroPython (I2C)
Supports: PM1.0, PM2.5, PM4.0, PM10, number concentrations, typical particle size
I2C Address: 0x69
"""

import time
import struct


# ── SPS30 I2C Commands (2-byte) ──────────────────────────────────────────────
CMD_START_MEASUREMENT   = b'\x00\x10'
CMD_STOP_MEASUREMENT    = b'\x01\x04'
CMD_DATA_READY_FLAG     = b'\x02\x02'
CMD_READ_MEASUREMENT    = b'\x03\x00'
CMD_SLEEP               = b'\x10\x01'
CMD_WAKEUP              = b'\x11\x03'
CMD_CLEAN_FAN           = b'\x56\x07'
CMD_RESET               = b'\xD3\x04'
CMD_READ_SERIAL         = b'\xD0\x33'
CMD_READ_VERSION        = b'\xD1\x00'


def _crc8(data: bytes) -> int:
    """CRC-8 checksum used by SPS30 (poly=0x31, init=0xFF)."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def _check_crc(data: bytes, offset: int) -> int:
    """Verify CRC for a 2-byte word at offset; return the word value."""
    b0, b1, crc = data[offset], data[offset + 1], data[offset + 2]
    if _crc8(bytes([b0, b1])) != crc:
        raise ValueError(f"CRC mismatch at offset {offset}")
    return (b0 << 8) | b1


def _build_cmd_with_arg(cmd: bytes, arg: bytes) -> bytes:
    """Append a 2-byte argument + CRC to a command."""
    crc = _crc8(arg)
    return cmd + arg + bytes([crc])


class SPS30:
    """Driver for the Sensirion SPS30 particulate matter sensor (I2C mode)."""

    I2C_ADDR = 0x69

    def __init__(self, i2c, addr=I2C_ADDR):
        self._i2c = i2c
        self._addr = addr

    # ── Low-level helpers ────────────────────────────────────────────────────

    def _write(self, cmd: bytes):
        self._i2c.writeto(self._addr, cmd)

    def _read(self, n_bytes: int) -> bytes:
        return self._i2c.readfrom(self._addr, n_bytes)

    def _write_read(self, cmd: bytes, n_bytes: int, delay_ms: int = 5) -> bytes:
        self._write(cmd)
        time.sleep_ms(delay_ms)
        return self._read(n_bytes)

    # ── Sensor lifecycle ─────────────────────────────────────────────────────

    def reset(self):
        """Perform a software reset (sensor reboots in ~100 ms)."""
        self._write(CMD_RESET)
        time.sleep_ms(100)

    def start_measurement(self):
        """
        Start continuous measurement.
        Uses float output format (sub-cmd 0x03, dummy 0x00).
        Wait ≥1 s before the first valid reading.
        """
        # 0x0010  sub-cmd=0x03  dummy=0x00  CRC
        payload = b'\x03\x00'
        cmd = CMD_START_MEASUREMENT + payload + bytes([_crc8(payload)])
        self._write(cmd)
        time.sleep_ms(20)

    def stop_measurement(self):
        self._write(CMD_STOP_MEASUREMENT)
        time.sleep_ms(5)

    def sleep(self):
        self._write(CMD_SLEEP)
        time.sleep_ms(5)

    def wakeup(self):
        self._write(CMD_WAKEUP)
        time.sleep_ms(5)

    def fan_cleaning(self):
        """Trigger manual fan-cleaning (runs for ~10 s)."""
        self._write(CMD_CLEAN_FAN)
        time.sleep_ms(10)

    # ── Status / info ────────────────────────────────────────────────────────

    def data_ready(self) -> bool:
        """Return True if a new measurement is available."""
        raw = self._write_read(CMD_DATA_READY_FLAG, 3)
        return bool(_check_crc(raw, 0) & 0x01)

    def read_serial(self) -> str:
        """Read the 32-character ASCII serial number."""
        raw = self._write_read(CMD_READ_SERIAL, 48, delay_ms=20)
        chars = []
        for i in range(0, 48, 3):
            word = _check_crc(raw, i)
            chars.append(chr(word >> 8))
            chars.append(chr(word & 0xFF))
        return ''.join(chars).strip('\x00')

    def read_version(self) -> dict:
        """Return firmware and hardware version info."""
        raw = self._write_read(CMD_READ_VERSION, 3, delay_ms=20)
        word = _check_crc(raw, 0)
        return {
            'firmware_major': (word >> 8) & 0xFF,
            'firmware_minor': word & 0xFF,
        }

    # ── Measurement ──────────────────────────────────────────────────────────

    def read_measurement(self) -> dict | None:
        """
        Read all measurement values.

        Returns a dict with keys:
            pm1_0, pm2_5, pm4_0, pm10   – mass concentrations in µg/m³
            nc0_5, nc1_0, nc2_5, nc4_0, nc10 – number concentrations in #/cm³
            typical_size               – typical particle size in µm
        Returns None if data is not ready yet.
        """
        if not self.data_ready():
            return None

        # 10 float values × (4 bytes + 1 CRC per word-pair) = 60 bytes
        raw = self._write_read(CMD_READ_MEASUREMENT, 60, delay_ms=5)

        # Each IEEE-754 float is spread over 2 words (4 bytes + 2 CRCs = 6 bytes)
        floats = []
        for i in range(10):
            offset = i * 6
            # word 0
            w0 = _check_crc(raw, offset)
            # word 1
            w1 = _check_crc(raw, offset + 3)
            packed = struct.pack('>HH', w0, w1)
            floats.append(struct.unpack('>f', packed)[0])

        return {
            'pm1_0':        floats[0],
            'pm2_5':        floats[1],
            'pm4_0':        floats[2],
            'pm10':         floats[3],
            'nc0_5':        floats[4],
            'nc1_0':        floats[5],
            'nc2_5':        floats[6],
            'nc4_0':        floats[7],
            'nc10':         floats[8],
            'typical_size': floats[9],
        }

    def wait_and_read(self, timeout_s: int = 10) -> dict:
        """
        Block until data is ready (polling every 500 ms), then return measurement.
        Raises RuntimeError on timeout.
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            data = self.read_measurement()
            if data is not None:
                return data
            time.sleep_ms(500)
        raise RuntimeError("SPS30: timeout waiting for data")
