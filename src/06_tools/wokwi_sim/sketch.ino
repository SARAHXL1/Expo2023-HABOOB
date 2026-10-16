/*
 * Habub (هبوب) — outdoor thermal-comfort sensing node · prototype firmware
 * Expo 2030 Riyadh Hackathon · Challenge 2.3
 *
 * Status : Verified in simulation (Wokwi) only — NOT yet verified on hardware.
 * Pinout : identical to "دليل بناء عقدة هبوب — الإصدار 2" (section 4.2).
 *
 * What it does
 *   - Reads DHT22 (Ta, RH), ADS1115 A0 (wind-motor voltage), MLX90614 (surface temp),
 *     VEML7700 (lux).
 *   - Converts motor voltage -> wind speed (K, B from calibration — placeholders now).
 *   - Computes a LOCAL UTCI for the display only (MRT = Ta, flagged "assumed").
 *     The server stays the authoritative source for MRT/UTCI (guide §5.4).
 *   - Prints one JSON line per cycle on Serial (115200) and can optionally POST it.
 *
 * Set SIM_WOKWI to 1 in Wokwi (ILI9341 stands in for the ST7789 1.69"),
 * and to 0 for the real board (ST7789V2 240x280).
 */

#define SIM_WOKWI 1

#include <Wire.h>
#include <SPI.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_VEML7700.h>
#include <Adafruit_GFX.h>
#if SIM_WOKWI
  #include <Adafruit_ILI9341.h>
#else
  #include <Adafruit_ST7789.h>
#endif
#include "habub_utci.h"

// Panel-independent colours (RGB565)
#define C_BLACK  0x0000
#define C_WHITE  0xFFFF
#define C_RED    0xF800
#define C_GREEN  0x07E0
#define C_YELLOW 0xFFE0
#define C_GREY   0x39E7

// ---------------------------------------------------------------- pins (guide §4.2)
constexpr uint8_t PIN_DHT      = 4;
constexpr uint8_t PIN_I2C_SDA  = 21;
constexpr uint8_t PIN_I2C_SCL  = 22;
constexpr uint8_t PIN_TFT_CS   = 5;
constexpr uint8_t PIN_TFT_DC   = 16;
constexpr uint8_t PIN_TFT_RST  = 17;
constexpr uint8_t PIN_TFT_BLK  = 32;
// SPI: SCK = GPIO18, MOSI = GPIO23 (ESP32 default VSPI). GPIO13 reserved for DS18B20.

// ---------------------------------------------------------------- configuration
const char *NODE_ID = "habub-01";

// Wind calibration: speed[m/s] = K * V + B  (guide §2.4).
// PLACEHOLDERS — replace with the values from the fan + handheld-anemometer calibration.
constexpr float WIND_K       = 8.0f;   // m/s per volt      (placeholder)
constexpr float WIND_B       = 0.4f;   // m/s start speed   (placeholder)
constexpr float WIND_V_START = 0.02f;  // below this voltage the rotor is considered stopped

// Height correction to 10 m (log profile, same as pythermalcomfort.scale_wind_speed_log)
constexpr float ANEMO_HEIGHT_M = 1.5f;   // OPEN: actual mast height of the cups
constexpr float ROUGHNESS_Z0_M = 0.01f;  // OPEN: terrain roughness length
constexpr float UTCI_V_MIN     = 0.5f;   // UTCI model lower limit (guide §5.4)
constexpr float UTCI_V_MAX     = 17.0f;

// Display backlight (0..255)
constexpr uint8_t BACKLIGHT = 200;

// Optional HTTP upload (off in Wokwi: the simulator cannot reach the laptop's LAN)
constexpr bool ENABLE_HTTP   = false;
const char *WIFI_SSID        = "Wokwi-GUEST";
const char *WIFI_PASS        = "";
const char *SERVER_URL       = "http://192.168.1.10:5000/api/reading";  // OPEN: laptop IP

// Task periods [ms] (guide §5.3)
constexpr uint32_t T_WIND_SAMPLE = 100;
constexpr uint32_t T_DHT         = 2500;
constexpr uint32_t T_AUX         = 5000;   // MLX90614 + VEML7700
constexpr uint32_t T_DISPLAY     = 2000;
constexpr uint32_t T_REPORT      = 5000;
constexpr uint32_t T_RETRY       = 10000;  // retry missing I2C sensors

// ---------------------------------------------------------------- objects
DHT dht(PIN_DHT, DHT22);
Adafruit_ADS1115 ads;
Adafruit_MLX90614 mlx;
Adafruit_VEML7700 veml;
#if SIM_WOKWI
  Adafruit_ILI9341 tft(PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);
#else
  Adafruit_ST7789 tft(PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);
#endif

// Logical drawing area is always 240x280 (the real panel). Corners are rounded,
// so content keeps ~20 px top/bottom margin (guide §2.7).
constexpr int16_t SCR_W = 240, SCR_H = 280;

// ---------------------------------------------------------------- state
struct Readings {
  float ta = NAN, rh = NAN;          // DHT22
  float windV = NAN, windMs = NAN;   // averaged motor voltage, measured speed
  float wind10 = NAN;                // scaled to 10 m and clamped for UTCI
  bool  windClamped = false;
  float tSurf = NAN, tMlxAmb = NAN;  // MLX90614
  float lux = NAN;                   // VEML7700
  float utci = NAN;                  // local, MRT = Ta
  int   utciCat = -1;
} R;

struct Health { bool dht = false, ads = false, mlx = false, veml = false, tft = true; } H;

constexpr int WIND_N = 20;           // 20 x 100 ms = 2 s moving average
float windBuf[WIND_N];
int   windIdx = 0, windCount = 0;

uint32_t seq = 0;
uint32_t tWind = 0, tDht = 0, tAux = 0, tDisp = 0, tRep = 0, tRetry = 0;

// ---------------------------------------------------------------- UTCI categories
const char *CAT_NAME[10] = {
  "EXTREME COLD", "V.STRONG COLD", "STRONG COLD", "MODERATE COLD", "SLIGHT COLD",
  "NO STRESS", "MODERATE HEAT", "STRONG HEAT", "V.STRONG HEAT", "EXTREME HEAT"};
const char *CAT_KEY[10] = {
  "extreme_cold", "very_strong_cold", "strong_cold", "moderate_cold", "slight_cold",
  "no_thermal_stress", "moderate_heat", "strong_heat", "very_strong_heat", "extreme_heat"};
// Conventional UTCI colour scale (blue -> green -> red), RGB565
const uint16_t CAT_COLOR[10] = {
  0x000F, 0x001F, 0x041F, 0x05FF, 0x87FF, 0x07E0, 0xFE00, 0xFC00, 0xF800, 0x8000};

// ================================================================ sensors
bool initAds() {
  if (!ads.begin(0x48, &Wire)) return false;
  ads.setGain(GAIN_FOUR);                 // ±1.024 V (guide §2.3)
  ads.setDataRate(RATE_ADS1115_250SPS);
  return true;
}

bool initVeml() {
  if (!veml.begin(&Wire)) return false;
  veml.setGain(VEML7700_GAIN_1_8);        // fixed range: up to ~30 klx, no blocking auto-ranging
  veml.setIntegrationTime(VEML7700_IT_100MS);
  return true;
}

void initSensors() {
  dht.begin();
  H.ads  = initAds();
  H.mlx  = mlx.begin(MLX90614_I2CADDR, &Wire);
  H.veml = initVeml();
}

void retryMissing() {
  if (!H.ads)  H.ads  = initAds();
  if (!H.mlx)  H.mlx  = mlx.begin(MLX90614_I2CADDR, &Wire);
  if (!H.veml) H.veml = initVeml();
}

void i2cScan() {
  Serial.print(F("[I2C] scan:"));
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) { Serial.printf(" 0x%02X", a); n++; }
  }
  Serial.printf("  (%d device(s); expected 0x10 0x48 0x5A)\n", n);
}

void sampleWind() {
  if (!H.ads) return;
  int16_t raw = ads.readADC_SingleEnded(0);
  float v = ads.computeVolts(raw);
  if (v < 0) v = 0;                       // negative => motor wires reversed (guide §2.4)
  windBuf[windIdx] = v;
  windIdx = (windIdx + 1) % WIND_N;
  if (windCount < WIND_N) windCount++;
}

void updateWind() {
  if (!H.ads || windCount == 0) { R.windV = R.windMs = R.wind10 = NAN; return; }
  float s = 0;
  for (int i = 0; i < windCount; i++) s += windBuf[i];
  R.windV  = s / windCount;
  R.windMs = (R.windV < WIND_V_START) ? 0.0f : WIND_K * R.windV + WIND_B;
  float v10 = habub_wind_to_10m(R.windMs, ANEMO_HEIGHT_M, ROUGHNESS_Z0_M, 0.0);
  R.windClamped = (v10 < UTCI_V_MIN) || (v10 > UTCI_V_MAX);
  R.wind10 = constrain(v10, UTCI_V_MIN, UTCI_V_MAX);
}

void readDht() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  H.dht = !(isnan(t) || isnan(h));
  if (H.dht) { R.ta = t; R.rh = h; }
}

void readAux() {
  if (H.mlx) {
    double o = mlx.readObjectTempC(), a = mlx.readAmbientTempC();
    if (isnan(o) || isnan(a)) H.mlx = false;   // bus error -> retry later
    else { R.tSurf = o; R.tMlxAmb = a; }
  }
  if (H.veml) {
    float l = veml.readLux(VEML_LUX_NORMAL);
    if (l < 0) H.veml = false; else R.lux = l;
  }
}

void computeUtci() {
  if (!H.dht || isnan(R.wind10)) { R.utci = NAN; R.utciCat = -1; return; }
  double tr = R.ta;                          // MRT assumed = Ta (indoor evaluation, guide §5.4)
  R.utci = habub_utci(R.ta, tr, R.wind10, R.rh);
  R.utciCat = isnan(R.utci) ? -1 : habub_utci_category(R.utci);
}

// ================================================================ display
void drawStatic() {
  tft.fillScreen(C_BLACK);
#if SIM_WOKWI
  tft.drawRect(0, 0, SCR_W, SCR_H, 0x39E7);  // outline of the real 240x280 panel
  tft.setTextColor(0x7BEF);
  tft.setTextSize(1);
  tft.setCursor(4, SCR_H + 8);
  tft.print(F("sim: area below = outside real 1.69\" panel"));
#endif
  tft.setTextColor(C_WHITE);
  tft.setTextSize(2);
  tft.setCursor(20, 22);  tft.print(F("HABUB"));
  tft.setTextSize(1);
  tft.setCursor(150, 26); tft.print(NODE_ID);
  tft.drawFastHLine(20, 42, 200, 0x39E7);
  tft.setCursor(20, 50);  tft.print(F("UTCI (local, MRT=Ta)"));
  const char *lbl[5] = {"Air  Ta", "Hum  RH", "Wind", "Surf Ts", "Light"};
  for (int i = 0; i < 5; i++) { tft.setCursor(20, 150 + i * 18); tft.print(lbl[i]); }
}

void printField(int16_t x, int16_t y, const char *txt, uint8_t size, uint16_t fg, uint16_t bg, int16_t w) {
  tft.fillRect(x, y, w, 8 * size, bg);
  tft.setTextSize(size);
  tft.setTextColor(fg, bg);
  tft.setCursor(x, y);
  tft.print(txt);
}

void fmt(char *out, size_t n, float v, int dec, const char *unit) {
  if (isnan(v)) snprintf(out, n, "--");
  else snprintf(out, n, "%.*f %s", dec, v, unit);
}

void updateDisplay() {
  char b[32];
  // UTCI block
  uint16_t col = (R.utciCat >= 0) ? CAT_COLOR[R.utciCat] : 0x39E7;
  tft.fillRect(20, 62, 200, 6, col);
  if (isnan(R.utci)) snprintf(b, sizeof b, "--");
  else snprintf(b, sizeof b, "%.1fC", R.utci);
  printField(20, 74, b, 5, C_WHITE, C_BLACK, 200);
  printField(20, 120, R.utciCat >= 0 ? CAT_NAME[R.utciCat] : "NO DATA", 2, col, C_BLACK, 200);

  // Value list
  fmt(b, sizeof b, R.ta, 1, "C");      printField(100, 150, b, 1, C_WHITE, C_BLACK, 120);
  fmt(b, sizeof b, R.rh, 0, "%");      printField(100, 168, b, 1, C_WHITE, C_BLACK, 120);
  if (isnan(R.windMs)) snprintf(b, sizeof b, "--");
  else snprintf(b, sizeof b, "%.1f m/s%s", R.windMs, R.windClamped ? " (min)" : "");
  printField(100, 186, b, 1, R.windClamped ? C_YELLOW : C_WHITE, C_BLACK, 120);
  fmt(b, sizeof b, R.tSurf, 1, "C");   printField(100, 204, b, 1, C_WHITE, C_BLACK, 120);
  fmt(b, sizeof b, R.lux, 0, "lx");    printField(100, 222, b, 1, C_WHITE, C_BLACK, 120);

  // Health line
  snprintf(b, sizeof b, "DHT%c ADS%c MLX%c LUX%c  #%lu",
           H.dht ? '+' : 'x', H.ads ? '+' : 'x', H.mlx ? '+' : 'x', H.veml ? '+' : 'x',
           (unsigned long)seq);
  printField(20, 250, b, 1, (H.dht && H.ads && H.mlx && H.veml) ? 0x07E0 : C_RED,
             C_BLACK, 200);
}

// ================================================================ reporting
void addNum(JsonDocument &d, const char *k, float v, int dec) {
  if (isnan(v)) d[k] = nullptr;
  else { float p = powf(10, dec); d[k] = roundf(v * p) / p; }
}

void report() {
  JsonDocument d;
  d["node"]   = NODE_ID;
  d["seq"]    = seq;
  d["uptime_s"] = millis() / 1000;
  addNum(d, "ta", R.ta, 1);
  addNum(d, "rh", R.rh, 1);
  addNum(d, "wind_v", R.windV, 4);
  addNum(d, "wind_ms", R.windMs, 2);
  addNum(d, "t_surface", R.tSurf, 1);
  addNum(d, "t_mlx_ambient", R.tMlxAmb, 1);
  addNum(d, "lux", R.lux, 0);
  addNum(d, "utci_local", R.utci, 1);
  d["utci_cat_local"] = (R.utciCat >= 0) ? CAT_KEY[R.utciCat] : nullptr;
  d["mrt_assumed"]  = true;
  d["wind_clamped"] = R.windClamped;
  JsonObject ok = d["ok"].to<JsonObject>();
  ok["dht"] = H.dht; ok["ads"] = H.ads; ok["mlx"] = H.mlx; ok["veml"] = H.veml;

  serializeJson(d, Serial);
  Serial.println();

  if (ENABLE_HTTP && WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.setTimeout(3000);
    if (http.begin(SERVER_URL)) {
      http.addHeader("Content-Type", "application/json");
      String body; serializeJson(d, body);
      int code = http.POST(body);
      if (code != 200) Serial.printf("[HTTP] POST failed: %d\n", code);
      http.end();
    }
  }
}

// ================================================================ setup / loop
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println(F("\n=== Habub node — prototype firmware ==="));

  ledcAttach(PIN_TFT_BLK, 5000, 8);   // ESP32 Arduino core 3.x API
  ledcWrite(PIN_TFT_BLK, BACKLIGHT);
#if SIM_WOKWI
  tft.begin();
#else
  tft.init(240, 280);                 // ST7789V2 1.69": verify size/offset on first boot
#endif
  tft.setRotation(0);
  drawStatic();

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(100000);              // MLX90614 limits the whole bus to 100 kHz
  i2cScan();
  initSensors();
  Serial.printf("[INIT] ADS1115:%s MLX90614:%s VEML7700:%s\n",
                H.ads ? "ok" : "MISSING", H.mlx ? "ok" : "MISSING", H.veml ? "ok" : "MISSING");

  if (ENABLE_HTTP) {
    WiFi.begin(WIFI_SSID, WIFI_PASS);  // non-blocking; loop() keeps running
  }

  readDht();
  readAux();
}

void loop() {
  uint32_t now = millis();

  if (now - tWind >= T_WIND_SAMPLE) { tWind = now; sampleWind(); }
  if (now - tDht  >= T_DHT)         { tDht  = now; readDht(); }
  if (now - tAux  >= T_AUX)         { tAux  = now; readAux(); }
  if (now - tRetry >= T_RETRY)      { tRetry = now; retryMissing(); }

  if (now - tDisp >= T_DISPLAY) {
    tDisp = now;
    updateWind();
    computeUtci();
    updateDisplay();
  }
  if (now - tRep >= T_REPORT) {
    tRep = now;
    seq++;
    report();
  }
}
