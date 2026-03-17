# SPS30 → Raspberry Pi Pico 2W → InfluxDB

Read particulate matter (PM) data from a Sensirion SPS30 sensor and push it to
InfluxDB in real time using a Raspberry Pi Pico 2W running MicroPython.

---

## Hardware required

| Component | Notes |
|-----------|-------|
| Raspberry Pi Pico 2W | Must be flashed with MicroPython ≥ 1.23 |
| Sensirion SPS30 | PM1.0 / PM2.5 / PM4.0 / PM10 sensor |
| JST ZHR-5 cable (1.5 mm) | SPS30 connector (or bare wires) |

---

## Wiring (I2C mode)

```
SPS30 Pin → Pico 2W GPIO
─────────────────────────────────────────
Pin 1 VDD  → 3.3V  (Pico physical pin 36)
Pin 2 SDA  → GPIO4 (Pico physical pin 6 ) ← default, edit config.py
Pin 3 SCL  → GPIO5 (Pico physical pin 7 ) ← default, edit config.py
Pin 4 SEL  → GND   (selects I2C mode!)
Pin 5 GND  → GND   (Pico physical pin 38)
```

> **Important:** SEL pin **must** be tied to GND to enable I2C mode.
> Leaving it floating selects UART mode and the driver will not work.

---

## Project structure

```
sps30_pico2w/
├── config.py      ← Wi-Fi + InfluxDB credentials (edit this!)
├── sps30.py       ← SPS30 I2C driver
├── influxdb.py    ← InfluxDB Line Protocol HTTP writer
└── main.py        ← Application entry point (auto-run on boot)
```

---

## Setup

### 1. Flash MicroPython onto the Pico 2W

Download the latest **Pico 2 W** MicroPython UF2 from:
https://micropython.org/download/RPI_PICO2_W/

Hold BOOTSEL, plug in USB, drag-and-drop the UF2 file.

### 2. Install urequests (if not bundled)

Open a REPL (via Thonny or mpremote) and run:

```python
import mip
mip.install("urequests")
```

### 3. Edit config.py

Fill in your Wi-Fi credentials and InfluxDB connection details:

```python
WIFI_SSID     = "MyNetwork"
WIFI_PASSWORD = "MyPassword"

# InfluxDB Cloud v2:
INFLUX_HOST   = "us-east-1-1.aws.cloud2.influxdata.com"
INFLUX_PORT   = 443
INFLUX_SSL    = True
INFLUX_TOKEN  = "my-very-long-api-token=="
INFLUX_ORG    = "my-org"
INFLUX_BUCKET = "air_quality"
```

### 4. Upload files to the Pico

Using **mpremote**:

```bash
pip install mpremote
mpremote cp config.py    :config.py
mpremote cp sps30.py     :sps30.py
mpremote cp influxdb.py  :influxdb.py
mpremote cp main.py      :main.py
```

Using **Thonny**: open each file and use *File → Save as … → MicroPython device*.

### 5. Run

Reset the Pico (or press the RUN button in Thonny).  
The onboard LED blinks 3× on successful Wi-Fi and flashes once per InfluxDB write.

---

## InfluxDB data schema

**Measurement:** `air_quality`

| Field | Unit | Description |
|-------|------|-------------|
| `pm1_0` | µg/m³ | PM1.0 mass concentration |
| `pm2_5` | µg/m³ | PM2.5 mass concentration |
| `pm4_0` | µg/m³ | PM4.0 mass concentration |
| `pm10`  | µg/m³ | PM10 mass concentration |
| `nc0_5` | #/cm³ | Particle count (>0.5 µm) |
| `nc1_0` | #/cm³ | Particle count (>1.0 µm) |
| `nc2_5` | #/cm³ | Particle count (>2.5 µm) |
| `nc4_0` | #/cm³ | Particle count (>4.0 µm) |
| `nc10`  | #/cm³ | Particle count (>10 µm) |
| `typical_size` | µm | Typical particle size |

**Tags:** `location`, `sensor`

### Example Flux query

```flux
from(bucket: "air_quality")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "air_quality")
  |> filter(fn: (r) => r._field == "pm2_5")
  |> aggregateWindow(every: 1m, fn: mean)
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `SPS30 not found at 0x69` | Wrong pins or SEL not grounded | Check wiring table above |
| `CRC mismatch` | Noisy I2C bus | Add 4.7 kΩ pull-ups on SDA/SCL, reduce `I2C_FREQ` to 50 000 |
| `HTTP 401` | Wrong API token | Regenerate token in InfluxDB UI |
| `HTTP 404` | Wrong bucket/org | Double-check `INFLUX_BUCKET` and `INFLUX_ORG` |
| Wi-Fi keeps dropping | Weak signal | Move closer to AP; increase `WIFI_TIMEOUT` |
| Readings are 0 after boot | Sensor not warmed up | Increase `WARMUP_S` (default 5 s) |

---

## Sensor notes

- The SPS30 needs **≥ 1 second** after `start_measurement()` before data is valid.
- Sensirion recommends running the **fan cleaning** every week (~168 h of operation).  
  Call `sensor.fan_cleaning()` and wait 10 s — add this to your scheduler if needed.
- Accuracy spec: ±10 µg/m³ or ±10 % for PM2.5 (whichever is larger).
