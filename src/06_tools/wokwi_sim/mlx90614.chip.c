// MLX90614 IR thermometer emulator for Wokwi (Habub prototype simulation).
// SMBus "read word" model used by Adafruit_MLX90614: write command byte,
// repeated start, read LSB, MSB, PEC. RAM 0x06 = Ta, 0x07 = Tobj1.
// Temperature encoding: raw = (T[°C] + 273.15) / 0.02.
#include "wokwi-api.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>

#define MLX_ADDR 0x5A

typedef struct {
  uint8_t cmd;
  uint8_t wcount;
  uint8_t rcount;
  uint8_t tx[3];
  uint32_t obj_attr, amb_attr;
} chip_state_t;

static uint8_t crc8_step(uint8_t crc, uint8_t data) {
  crc ^= data;
  for (int i = 0; i < 8; i++) crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
  return crc;
}

static uint16_t temp_raw(float t) {
  float r = (t + 273.15f) / 0.02f + 0.5f;
  if (r < 1) r = 1;
  if (r > 0x7FFF) r = 0x7FFF;
  return (uint16_t)r;
}

static void prepare(chip_state_t *c) {
  uint16_t v;
  switch (c->cmd) {
    case 0x06: v = temp_raw(attr_read_float(c->amb_attr)); break;
    case 0x07: v = temp_raw(attr_read_float(c->obj_attr)); break;
    case 0x08: v = temp_raw(attr_read_float(c->obj_attr)); break;  // Tobj2 (single-zone: same)
    case 0x24: v = 0xFFFF; break;                                  // EEPROM emissivity = 1.0
    case 0x2E: v = MLX_ADDR; break;                                // EEPROM SMBus address
    default: v = 0; break;
  }
  c->tx[0] = v & 0xFF;
  c->tx[1] = v >> 8;
  uint8_t crc = 0;
  crc = crc8_step(crc, MLX_ADDR << 1);
  crc = crc8_step(crc, c->cmd);
  crc = crc8_step(crc, (MLX_ADDR << 1) | 1);
  crc = crc8_step(crc, c->tx[0]);
  crc = crc8_step(crc, c->tx[1]);
  c->tx[2] = crc;
}

static bool on_connect(void *ud, uint32_t address, bool read) {
  chip_state_t *c = ud;
  c->wcount = 0;
  c->rcount = 0;
  if (read) prepare(c);
  return true;
}

static uint8_t on_read(void *ud) {
  chip_state_t *c = ud;
  uint8_t b = c->rcount < 3 ? c->tx[c->rcount] : 0xFF;
  c->rcount++;
  return b;
}

static bool on_write(void *ud, uint8_t data) {
  chip_state_t *c = ud;
  if (c->wcount == 0) c->cmd = data;  // EEPROM writes are acknowledged and ignored
  c->wcount++;
  return true;
}

void chip_init(void) {
  chip_state_t *c = calloc(1, sizeof(chip_state_t));
  c->obj_attr = attr_init_float("objectTemp", 38.0f);
  c->amb_attr = attr_init_float("ambientTemp", 30.0f);
  const i2c_config_t cfg = {
    .user_data = c,
    .address = MLX_ADDR,
    .scl = pin_init("SCL", INPUT),
    .sda = pin_init("SDA", INPUT),
    .connect = on_connect,
    .read = on_read,
    .write = on_write,
    .disconnect = 0,
  };
  i2c_init(&cfg);
}
