from machine import I2C, Pin
import time

class TMAG5273:
    # Default 7-bit I2C address is 0x35 (factory). :contentReference[oaicite:1]{index=1}
    ADDR_DEFAULT = 0x35

    # Register map (offsets) :contentReference[oaicite:2]{index=2}
    REG_DEVICE_CONFIG_1      = 0x00
    REG_DEVICE_CONFIG_2      = 0x01
    REG_SENSOR_CONFIG_1      = 0x02
    REG_SENSOR_CONFIG_2      = 0x03
    REG_T_CONFIG             = 0x07

    REG_DEVICE_ID            = 0x0D
    REG_MANUF_ID_LSB         = 0x0E
    REG_MANUF_ID_MSB         = 0x0F

    REG_T_MSB_RESULT         = 0x10
    REG_T_LSB_RESULT         = 0x11
    REG_X_MSB_RESULT         = 0x12
    REG_X_LSB_RESULT         = 0x13
    REG_Y_MSB_RESULT         = 0x14
    REG_Y_LSB_RESULT         = 0x15
    REG_Z_MSB_RESULT         = 0x16
    REG_Z_LSB_RESULT         = 0x17
    REG_CONV_STATUS          = 0x18

    # Manufacturer ID bytes (TI) are 0x49 and 0x54. :contentReference[oaicite:3]{index=3}
    MANUF_LSB_EXPECTED = 0x49
    MANUF_MSB_EXPECTED = 0x54

    # Temp conversion constants from datasheet electrical characteristics:
    # TSENS_T0 = 25°C, TADC_T0 = 17508, TADC_RES = 60.1 LSB/°C :contentReference[oaicite:4]{index=4}
    TSENS_T0 = 25.0
    TADC_T0  = 17508
    TADC_RES = 60.1

    def __init__(self, i2c: I2C, addr: int = ADDR_DEFAULT):
        self.i2c = i2c
        self.addr = addr

    # ---------- Low-level I2C helpers ----------
    def _read_u8(self, reg: int) -> int:
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def _write_u8(self, reg: int, val: int) -> None:
        self.i2c.writeto_mem(self.addr, reg, bytes([val & 0xFF]))

    def _read_i16(self, reg_msb: int) -> int:
        # Read MSB then LSB (two registers in a row)
        b = self.i2c.readfrom_mem(self.addr, reg_msb, 2)
        raw = (b[0] << 8) | b[1]
        # Convert unsigned -> signed 16-bit (2's complement)
        if raw & 0x8000:
            raw -= 0x10000
        return raw

    # ---------- Connection / ID ----------
    def is_connected(self) -> bool:
        try:
            mid_lsb = self._read_u8(self.REG_MANUF_ID_LSB)
            mid_msb = self._read_u8(self.REG_MANUF_ID_MSB)
            return (mid_lsb == self.MANUF_LSB_EXPECTED) and (mid_msb == self.MANUF_MSB_EXPECTED)
        except OSError:
            return False

    def _device_variant_base_range_mt(self) -> int:
        """
        DEVICE_ID.VER tells you if the part is:
          1 = ±40/±80 mT family (A1/B1/C1/D1)
          2 = ±133/±266 mT family (A2/B2/C2/D2)
        :contentReference[oaicite:5]{index=5}
        """
        dev_id = self._read_u8(self.REG_DEVICE_ID)
        ver = dev_id & 0x03
        if ver == 1:
            return 40
        if ver == 2:
            return 133
        # Fallback if something unexpected:
        return 40

    def _ranges_mt(self):
        """
        SENSOR_CONFIG_2:
          bit1 = X_Y_RANGE (0 => base, 1 => 2*base)
          bit0 = Z_RANGE   (0 => base, 1 => 2*base)
        :contentReference[oaicite:6]{index=6}
        """
        base = self._device_variant_base_range_mt()
        sc2 = self._read_u8(self.REG_SENSOR_CONFIG_2)
        xy = base * (2 if (sc2 & 0b10) else 1)
        z  = base * (2 if (sc2 & 0b01) else 1)
        return xy, z

    # ---------- Init (your Arduino begin translated) ----------
    def begin(self) -> bool:
        # 1) Make sure device ACKs and IDs match
        if self.addr not in self.i2c.scan():
            return False
        if not self.is_connected():
            return False

        # 2) Configure per your Arduino begin()
        # SENSOR_CONFIG_1 (0x02):
        #   MAG_CH_EN (bits7-4) = 0x7 => X,Y,Z enabled
        #   SLEEPTIME (bits3-0) = 0x0 (doesn't matter for continuous mode)
        # :contentReference[oaicite:7]{index=7}
        self._write_u8(self.REG_SENSOR_CONFIG_1, 0x70)

        # T_CONFIG (0x07):
        #   bit0 T_CH_EN = 1 => temperature enabled :contentReference[oaicite:8]{index=8}
        self._write_u8(self.REG_T_CONFIG, 0x01)

        # DEVICE_CONFIG_2 (0x01):
        #   bit4 LP_LN = 0 => low active current mode
        #   bits1-0 OPERATING_MODE = 2 => continuous measure mode
        # :contentReference[oaicite:9]{index=9}
        self._write_u8(self.REG_DEVICE_CONFIG_2, 0x02)

        # SENSOR_CONFIG_2 (0x03):
        #   bits3-2 ANGLE_EN = 0 => no angle calculation
        #   bit1 X_Y_RANGE = 1 => larger range (±80mT or ±266mT)
        #   bit0 Z_RANGE   = 1 => larger range (±80mT or ±266mT)
        # :contentReference[oaicite:10]{index=10}
        self._write_u8(self.REG_SENSOR_CONFIG_2, 0x03)

        # 3) Read back and verify key settings (like your Arduino code)
        sc1 = self._read_u8(self.REG_SENSOR_CONFIG_1)
        dc2 = self._read_u8(self.REG_DEVICE_CONFIG_2)
        tc  = self._read_u8(self.REG_T_CONFIG)
        sc2 = self._read_u8(self.REG_SENSOR_CONFIG_2)

        mag_ch_en = (sc1 >> 4) & 0x0F
        operating_mode = dc2 & 0x03
        low_power_mode = (dc2 >> 4) & 0x01
        temp_en = tc & 0x01
        angle_en = (sc2 >> 2) & 0x03

        if mag_ch_en != 0x7:
            return False
        if operating_mode != 0x2:
            return False
        if low_power_mode != 0x0:
            return False
        if temp_en != 0x1:
            return False
        if angle_en != 0x0:
            return False

        return True

    # ---------- Data reading ----------
    def data_ready(self) -> bool:
        # CONV_STATUS bit0 RESULT_STATUS (1 => ready) :contentReference[oaicite:11]{index=11}
        st = self._read_u8(self.REG_CONV_STATUS)
        return (st & 0x01) != 0

    def read_xyz_mT(self):
        x_raw = self._read_i16(self.REG_X_MSB_RESULT)
        y_raw = self._read_i16(self.REG_Y_MSB_RESULT)
        z_raw = self._read_i16(self.REG_Z_MSB_RESULT)

        xy_range, z_range = self._ranges_mt()

        # Datasheet equation for 16-bit magnetic data:
        # B(mT) = signed16 * BR / 32768  :contentReference[oaicite:12]{index=12}
        x = x_raw * xy_range / 32768.0
        y = y_raw * xy_range / 32768.0
        z = z_raw * z_range  / 32768.0
        return x, y, z

    def read_temp_C(self):
        t_raw = self._read_i16(self.REG_T_MSB_RESULT)

        # Datasheet temperature conversion (16-bit):
        # T = 25 + (TADC_T - 17508) / 60.1  :contentReference[oaicite:13]{index=13}
        return self.TSENS_T0 + (t_raw - self.TADC_T0) / self.TADC_RES


# -------------------- Your "setup()" + "loop()" equivalent --------------------

# Pico physical pin 4 = GP2 (SDA), physical pin 5 = GP3 (SCL)
i2c = I2C(1, sda=Pin(1), scl=Pin(2), freq=400_000)

sensor = TMAG5273(i2c, addr=TMAG5273.ADDR_DEFAULT)

time.sleep(1.0)
print("")
print("------------------------------------------------------------------")
print("TMAG5273 MicroPython Example: Basic Readings (Pico)")
print("------------------------------------------------------------------")
print("")

if sensor.begin():
    print("Begin")
else:
    print("Device failed to setup - freezing code.")
    while True:
        time.sleep(1)

while True:
    # In continuous mode you can read any time; optionally gate on data_ready()
    # if not sensor.data_ready():
    #     time.sleep_ms(5)
    #     continue

    x, y, z = sensor.read_xyz_mT()
    '''
    To be impelemented: use x, y, z as input to determine servo output
    '''
    t = sensor.read_temp_C()

    print("Data -  Magnetic: [ X: {:.3f}, Y: {:.3f}, Z: {:.3f} ] mT,    Temp: {:.2f} C".format(x, y, z, t))
    time.sleep_ms(300)

