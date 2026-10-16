// VEML7700 ambient light sensor emulator for Wokwi (Habub prototype simulation).
// 16-bit registers, LSB first. Reg 0x00 ALS_CONF (gain bits 12:11, IT bits 9:6),
// reg 0x04 ALS data. Raw count = lux / resolution, where resolution follows the
// same formula as Adafruit_VEML7700::getResolution():
//   0.0036 * (800 / IT_ms) * (2 / gain)
// The slider is linear lux (no non-linear correction is modelled).
#include "wokwi-api.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>

#define VEML_ADDR 0x10

typedef struct {
  uint8_t  ptr;
  uint16_t reg[8];
  uint8_t  wcount, rcount;
  uint16_t txval;
  uint32_t lux_attr;
} chip_state_t;

static float gain_value(uint16_t conf) {
  switch ((conf >> 11) & 3) {
    case 0: return 1.0f;
    case 1: return 2.0f;
    case 2: return 0.125f;
    default: return 0.25f;
  }
}

static float it_ms(uint16_t conf) {
  switch ((conf >> 6) & 0xF) {
    case 0x0: return 100;
    case 0x1: return 200;
    case 0x2: return 400;
    case 0x3: return 800;
    case 0x8: return 50;
    case 0xC: return 25;
    default:  return 100;
  }
}

static uint16_t als_count(chip_state_t *c) {
  uint16_t conf = c->reg[0];
  if (conf & 1) return 0;  // ALS_SD: shut down
  float res = 0.0036f * (800.0f / it_ms(conf)) * (2.0f / gain_value(conf));
  float n = attr_read_float(c->lux_attr) / res + 0.5f;
  if (n > 65535.0f) n = 65535.0f;
  if (n < 0) n = 0;
  return (uint16_t)n;
}

static bool on_connect(void *ud, uint32_t address, bool read) {
  chip_state_t *c = ud;
  c->wcount = 0;
  c->rcount = 0;
  if (read) {
    uint8_t r = c->ptr & 7;
    c->txval = (r == 4 || r == 5) ? als_count(c) : c->reg[r];
  }
  return true;
}

static uint8_t on_read(void *ud) {
  chip_state_t *c = ud;
  uint8_t b = (c->rcount == 0) ? (c->txval & 0xFF) : (c->txval >> 8);  // LSB first
  c->rcount++;
  return b;
}

static bool on_write(void *ud, uint8_t data) {
  chip_state_t *c = ud;
  if (c->wcount == 0) {
    c->ptr = data & 7;
  } else if (c->wcount == 1) {
    c->reg[c->ptr] = (c->reg[c->ptr] & 0xFF00) | data;
  } else if (c->wcount == 2) {
    c->reg[c->ptr] = (c->reg[c->ptr] & 0x00FF) | ((uint16_t)data << 8);
  }
  c->wcount++;
  return true;
}

void chip_init(void) {
  chip_state_t *c = calloc(1, sizeof(chip_state_t));
  c->reg[0] = 0x0001;  // power-on: shut down until the driver enables it
  c->lux_attr = attr_init_float("lux", 350.0f);
  const i2c_config_t cfg = {
    .user_data = c,
    .address = VEML_ADDR,
    .scl = pin_init("SCL", INPUT),
    .sda = pin_init("SDA", INPUT),
    .connect = on_connect,
    .read = on_read,
    .write = on_write,
    .disconnect = 0,
  };
  i2c_init(&cfg);
}
