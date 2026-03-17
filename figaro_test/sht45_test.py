import time
import board
import adafruit_sht4x

i2c = board.I2C()
sht = adafruit_sht4x.SHT4x(i2c)

print("Found SHT4x serial:", hex(sht.serial_number))

sht.mode = adafruit_sht4x.Mode.NOHEAT_HIGHPRECISION
print("Mode:", adafruit_sht4x.Mode.string[sht.mode])

while True:
    temperature, humidity = sht.measurements
    print(f"Temperature: {temperature:.2f} C")
    print(f"Humidity: {humidity:.2f} %")
    print()
    time.sleep(1)
