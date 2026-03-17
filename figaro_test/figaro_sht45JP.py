#!/usr/bin/env python3
"""
Unified TGS2603 + TGS2620 + SHT45 Monitor → InfluxDB
- Reads two gas sensors via MCP3002 (SPI)
- Reads temp/humidity via SHT45 (I²C)
- Calculates Rs, Rs/Ro, PPM ethanol approx for both sensors
- Logs everything to InfluxDB + prints to terminal

統合モニタープログラム：
・MCP3002（SPI）経由で2つのガスセンサーを読み取る
・SHT45（I2C）で温度・湿度を取得
・Rs、Rs/Ro、PPM（エタノール近似）を計算
・InfluxDBに送信しつつターミナルにも表示
"""

import csv
import os
import time
from datetime import datetime, timezone
import sys

import spidev              # SPI通信用（MCP3002用）
import board               # I2C用（Raspberry Piピン）
import adafruit_sht4x      # SHT45センサーライブラリ
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ────────────────────────────────────────────────
# Configuration（設定）
# ────────────────────────────────────────────────

# InfluxDB ローカル設定（未使用）
# INFLUX_URL    = "http://192.168.188.141:8086"
# INFLUX_TOKEN  = "..."

# InfluxDB Cloud 設定
INFLUX_URL    = "https://eu-central-1-1.aws.cloud2.influxdata.com/"
INFLUX_TOKEN  = "XwrLfZDuMGWQ9u2tl72X8X5gIMa-97SU5HLEfXizst_SAiubOwOTkrP5mTOTuZxpPbk2ALXa2UCET-dkmPnfJw=="    # アクセストークン（認証用）
INFLUX_ORG    = "free-tech"        # 組織名
INFLUX_BUCKET = "figaro_sht45"     # 保存先バケット名

# センサー関連パラメータ（キャリブレーション後に調整）
VREF = 5.0                # MCP3002の基準電圧
VC   = 5.0                # センサー回路の電源電圧
RL   = 2000.0             # 負荷抵抗（トリマ設定値）

# クリーンエア時の基準抵抗（Ro）→ 要キャリブレーション
RO_2603 = 2000.0
RO_2620 = 2000.0

PPM_EXPONENT = 0.55       # 感度カーブ調整（0.50～0.65が一般的）

READ_INTERVAL = 1.0       # 読み取り間隔（秒）

# -----------------------------
# ローカルCSV保存設定
# -----------------------------
CSV_FILE = "figaro_sht45.csv"

# ────────────────────────────────────────────────
# InfluxDB 初期化
# ────────────────────────────────────────────────
client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

# ────────────────────────────────────────────────
# SPI 設定（MCP3002用）
# ────────────────────────────────────────────────
try:
    spi = spidev.SpiDev()
    spi.open(0, 0)           # SPIバス0、CE0を使用
    spi.max_speed_hz = 500000  # 通信速度（安定性重視）
except Exception as e:
    print("SPI error:", e)
    sys.exit(1)

def read_mcp3002(channel=0):
    """MCP3002からCH0またはCH1を読み取る"""
    if channel not in (0, 1):
        return -1
    cmd = 0b10000000 if channel == 0 else 0b11000000
    try:
        reply = spi.xfer2([1, cmd, 0])
        value = ((reply[1] & 0x03) << 8) | reply[2]
        return value
    except Exception as e:
        print(f"SPI read error on CH{channel}: {e}")
        return -1

# ────────────────────────────────────────────────
# SHT45 設定（I2C）
# ────────────────────────────────────────────────
try:
    i2c = board.I2C()
    sht = adafruit_sht4x.SHT4x(i2c)
    sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
    print("SHT45 Serial No.:", hex(sht.serial_number))
    print("SHT45 running on:", adafruit_sht4x.Mode.string[sht.mode])
except Exception as e:
    print("SHT45 init error:", e)
    sht = None   # 初期化失敗時はNone

# ────────────────────────────────────────────────
# メインループ
# ────────────────────────────────────────────────
print("Unified TGS2603 + TGS2620 + SHT45 Logger")
print(f"Bucket: {INFLUX_BUCKET} | Interval: {READ_INTERVAL}s")
print("-" * 60)

try:

    # ---- CSVファイルを開く ----
    file_exists = os.path.exists(CSV_FILE)
    file_empty = (not file_exists) or os.path.getsize(CSV_FILE) == 0

    csv_file = open(CSV_FILE, "a", newline="")
    writer = csv.writer(csv_file)

    # ヘッダーがない場合のみ追加
    if file_empty:
        writer.writerow([
            "timestamp_utc",
            "adc_2603",
            "adc_2620",
            "voltage_2603",
            "voltage_2620",
            "rs_kohm_2603",
            "rs_kohm_2620",
            "rs_ro_2603",
            "rs_ro_2620",
            "ppm_2603",
            "ppm_2620",
            "温度(°C)",
            "湿度(%)"
        ]);
        csv_file.flush();

    print("測定開始：InfluxDBへ送信＋ローカル保存中（Ctrl+Cで停止）")

    while True:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # ── ガスセンサー読み取り ─────────────────────────
        adc_2603 = read_mcp3002(0)
        adc_2620 = read_mcp3002(1)

        # ADC値 → 電圧変換
        voltage_2603 = (adc_2603 / 1023.0) * VREF if adc_2603 >= 0 else 0
        voltage_2620 = (adc_2620 / 1023.0) * VREF if adc_2620 >= 0 else 0

        # Rs計算（TGS2603）
        rs_2603 = RL * (voltage_2603 / (VC - voltage_2603)) if (VC - voltage_2603) > 0.01 else float('inf')
        rs_ro_2603 = rs_2603 / RO_2603 if RO_2603 > 0 else 1.0

        # PPM（近似）※Rs/Ro<1のときのみ有効
        ppm_2603 = (1.0 / rs_ro_2603) ** (1.0 / PPM_EXPONENT) if 0 < rs_ro_2603 < 1.0 else 0.0

        # Rs計算（TGS2620）
        rs_2620 = RL * (voltage_2620 / (VC - voltage_2620)) if (VC - voltage_2620) > 0.01 else float('inf')
        rs_ro_2620 = rs_2620 / RO_2620 if RO_2620 > 0 else 1.0
        ppm_2620 = (1.0 / rs_ro_2620) ** (1.0 / PPM_EXPONENT) if 0 < rs_ro_2620 < 1.0 else 0.0

        # ── 温湿度センサー ─────────────────────────────
        temp_c = 0.0
        hum_rh = 0.0
        if sht:
            try:
                temp_c, hum_rh = sht.measurements
            except Exception as e:
                print("SHT45読み取りエラー:", e)

        # ── InfluxDB送信 ─────────────────────────────
        p_gas = Point("gas_sensors") \
            .tag("location", "osaka") \
            .field("adc_2603", float(adc_2603)) \
            .field("voltage_2603", voltage_2603) \
            .field("rs_kohm_2603", rs_2603/1000.0) \
            .field("rs_ro_2603", rs_ro_2603) \
            .field("ppm_2603", ppm_2603) \
            .field("adc_2620", float(adc_2620)) \
            .field("voltage_2620", voltage_2620) \
            .field("rs_kohm_2620", rs_2620/1000.0) \
            .field("rs_ro_2620", rs_ro_2620) \
            .field("ppm_2620", ppm_2620)\
            .field("温度(°C)", temp_c)\
            .field("湿度(%)", hum_rh)

        p_env = Point("environment") \
            .tag("場所", "東京") \
            .field("温度_°C", temp_c) \
            .field("湿度_%", hum_rh)

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=[p_gas, p_env])

        # ── CSV保存 ─────────────────────────────
        writer.writerow([
            now_iso,
            adc_2603,
            adc_2620,
            voltage_2603,
            voltage_2620,
            rs_2603,
            rs_2620,
            rs_ro_2603,
            rs_ro_2620,
            ppm_2603,
            ppm_2620,
            temp_c,
            hum_rh
        ])
        csv_file.flush()

        # ── コンソール表示 ─────────────────────────
        print(
            f"ADC2603:{adc_2603:4d} V:{voltage_2603:5.3f} Rs:{rs_2603/1000:5.1f}k "
            f"Rs/Ro:{rs_ro_2603:5.2f} PPM:{ppm_2603:6.1f} | "
            f"ADC2620:{adc_2620:4d} V:{voltage_2620:5.3f} Rs:{rs_2620/1000:5.1f}k "
            f"Rs/Ro:{rs_ro_2620:5.2f} PPM:{ppm_2620:6.1f} | "
            f"T:{temp_c:5.1f}°C  H:{hum_rh:5.1f}%".replace("inf", "∞"),
            flush=True
        )

        time.sleep(READ_INTERVAL)

except KeyboardInterrupt:
    print("\nユーザーによって停止されました")

except Exception as e:
    print("\n致命的エラー:", e)

finally:
    spi.close()

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

    print("正常終了（クリーンシャットダウン）")
