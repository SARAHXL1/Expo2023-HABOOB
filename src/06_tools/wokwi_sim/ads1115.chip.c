// ADS1115 16-bit ADC emulator for Wokwi (Habub prototype simulation).
// Implements the register model used by Adafruit_ADS1X15:
//   pointer 0x00 = conversion, 0x01 = config, 0x02/0x03 = thresholds.
// Conversions complete instantly (OS bit always reads back as 1).
// A0 voltage comes from the "a0Voltage" slider; A1..A3 read 0 V.
#include "wokwi-api.h"
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>

#define ADS_ADDR 0x48

typedef struct {
  uint8_t  ptr;        // register pointer
  uint16_t reg[4];     // conversion, config, lo_thresh, hi_thresh
  uint8_t  wcount;     // bytes received in current write transaction
  uint8_t  rcount;     // bytes sent in current read transaction
  uint16_t wbuf;
  uint32_t a0_attr;
} chip_state_t;

static float input_voltage(chip_state_t *c, int ch) {
  return ch == 0 ? attr_read_float(c->a0_attr) : 0.0f;
}

static void do_conversion(chip_state_t *c) {
  uint16_t cfg = c->reg[1];
  int mux = (cfg >> 12) & 0x7;
  int pga = (cfg >> 9) & 0x7;
  static const float fsr_tab[8] = {6.144f, 4.096f, 2.048f, 1.024f, 0.512f, 0.256f, 0.256f, 0.256f};
  float fsr = fsr_tab[pga];
  float v;
  switch (mux) {
    case 0: v = input_voltage(c, 0) - input_voltage(c, 1); break;
    case 1: v = input_voltage(c, 0) - input_voltage(c, 3); break;
    case 2: v = input_voltage(c, 1) - input_voltage(c, 3); break;
    case 3: v = input_voltage(c, 2) - input_voltage(c, 3); break;
    default: v = input_voltage(c, mux - 4); break;  // single-ended AINx vs GND
  }
  float codef = v / fsr * 32768.0f;
  int32_t code = (int32_t)(codef >= 0 ? codef + 0.5f : codef - 0.5f);
  if (code > 32767) code = 32767;
  if (code < -32768) code = -32768;
  c->reg[0] = (uint16_t)(int16_t)code;
}

static bool on_connect(void *ud, uint32_t address, bool read) {
  chip_state_t *c = ud;
  c->wcount = 0;
  c->rcount = 0;
  return true;
}

static uint8_t on_read(void *ud) {
  chip_state_t *c = ud;
  uint16_t val = c->reg[c->ptr & 3];
  if ((c->ptr & 3) == 1) val |= 0x8000;  // OS = 1: conversion done
  uint8_t b = (c->rcount == 0) ? (val >> 8) : (val & 0xFF);  // MSB first
  c->rcount++;
  return b;
}

static bool on_write(void *ud, uint8_t data) {
  chip_state_t *c = ud;
  if (c->wcount == 0) {
    c->ptr = data & 3;
  } else if (c->wcount == 1) {
    c->wbuf = (uint16_t)data << 8;
  } else if (c->wcount == 2) {
    c->wbuf |= data;
    if (c->ptr == 1) {
      bool start = c->wbuf & 0x8000;
      c->reg[1] = c->wbuf & 0x7FFF;
      bool continuous = !(c->wbuf & 0x0100);
      if (start || continuous) do_conversion(c);
    } else if (c->ptr != 0) {
      c->reg[c->ptr] = c->wbuf;
    }
  }
  c->wcount++;
  return true;
}

static void on_disconnect(void *ud) {
  chip_state_t *c = ud;
  // In continuous mode keep the result fresh for the next read.
  if (!(c->reg[1] & 0x0100)) do_conversion(c);
}

void chip_init(void) {
  chip_state_t *c = calloc(1, sizeof(chip_state_t));
  c->reg[1] = 0x8583;  // datasheet reset value of config register
  c->reg[2] = 0x8000;
  c->reg[3] = 0x7FFF;
  c->a0_attr = attr_init_float("a0Voltage", 0.0f);
  const i2c_config_t cfg = {
    .user_data = c,
    .address = ADS_ADDR,
    .scl = pin_init("SCL", INPUT),
    .sda = pin_init("SDA", INPUT),
    .connect = on_connect,
    .read = on_read,
    .write = on_write,
    .disconnect = on_disconnect,
  };
  i2c_init(&cfg);
}
