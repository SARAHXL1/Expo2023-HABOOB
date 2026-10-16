/* ===========================================================================
   هبوب — عقدة استشعار الراحة الحرارية
   هاكثون إكسبو 2030 الرياض · تحدي 2.3

   يغطي المتطلبات FW-01 إلى FW-14، ويرسل عقد البيانات schema 3 (القسم 5).

   الإصدار 2 من المتطلبات:
     • الكرة الحرارية (DS18B20) والبطارية مؤجلتان — التقييم داخل القاعة لا في الشمس.
       تُرسلان بحالة disabled، وMRT تُفترض في الخادم مساوية لحرارة الهواء.
     • حساس الضوء VEML7700 على العنوان 0x10 بدل BH1750.
     • الشاشة ST7789V2 بدقة 240×280 (1.69 بوصة).
     • التغذية من USB مباشرة بجهد 5V.
     • لإعادة الكرة: شغّل ENABLE_GLOBE أدناه، وحوّل mrt_source إلى "globe"
       في ملف إعدادات الخادم.

   اللوحة   : ESP32 Dev Module (DevKit V1، 30 منفذًا)
   البيئة   : Arduino IDE 2 مع حزمة esp32 by Espressif Systems
   المراقبة : Serial Monitor بسرعة 115200

   المكتبات المطلوبة من Library Manager (القسم 4.2):
     DHT sensor library (Adafruit) + Adafruit Unified Sensor
     OneWire (Paul Stoffregen) + DallasTemperature (Miles Burton) — عند ENABLE_GLOBE فقط
     Adafruit ADS1X15
     Adafruit MLX90614 Library
     Adafruit VEML7700 Library
     Adafruit ST7735 and ST7789 Library + Adafruit GFX Library
     ArduinoJson (الإصدار 7)

   ملاحظة مهمة: هذا البرنامج لم يُختبر على العتاد بعد. راجع أرقام المنافذ
   على الطباعة الموجودة على لوحتك قبل التوصيل، واتبع خطة الاختبار المرحلية
   في القسم 10 من ملف المتطلبات: أضف حساسًا واحدًا في كل مرة.
   =========================================================================== */

#include <WiFi.h>
#include <HTTPClient.h>
#include <esp_system.h>
#include <Wire.h>
#include <SPI.h>
#include <time.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_VEML7700.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>

/* ===========================================================================
   FW-12 — كل الإعدادات في قسم واحد واضح. لا تعدّل شيئًا خارج هذا القسم
   إلا إذا كنت تغيّر سلوك البرنامج عمدًا.
   =========================================================================== */

// ---- الشبكة ----
// اسم الهوتسبوت وكلمة مروره في secrets.h بجانب هذا الملف (لا يُرفع إلى GitHub).
// أول مرة: انسخ secrets.example.h باسم secrets.h واكتب القيمتين فيه.
#include "secrets.h"
// عنوان اللابتوب: يطبعه الخادم عند تشغيله (SV-12)
const char* SERVER_URL = "http://172.20.10.4:5050/api/readings";
// ---- هوية العقدة ----
const char* NODE_ID     = "node-01";
const char* FW_VERSION  = "0.4.0";   // 0.4.0: الشاشة تعرض WBGT والعلم من رد الخادم 
const int   SCHEMA_VER  = 3;

// ---- الكرة الحرارية: مؤجلة في هذا الإصدار ----
// هذا هو المفتاح الوحيد في برنامج العقدة لإعادتها. بعد تشغيله:
//   1. وصّل DS18B20 على GPIO 13 مع مقاومة 4.7kΩ بين DATA و3V3.
//   2. أزل التعليق عن سطري OneWire وDallasTemperature أدناه.
//   3. حوّل mrt_source إلى "globe" في config.json على الخادم.
#define ENABLE_GLOBE 0

#if ENABLE_GLOBE
  #include <OneWire.h>
  #include <DallasTemperature.h>
#endif

// ---- فترات التشغيل (FW-06) ----
const bool          TEST_MODE        = true;   // true: إرسال كل 5 ث · false: كل 60 ث
const unsigned long SEND_MS_TEST     = 5000UL;
const unsigned long SEND_MS_LONG     = 60000UL;

// ---- معايرة مقياس الرياح (تُستبدل بنتيجة المعايرة الفعلية) ----
// سرعة الرياح = K × الجهد + B، وتساوي صفرًا إن كان الجهد أقل من V_MIN
const float K_WIND      = 20.0f;
const float B_WIND      = 0.5f;
const float V_MIN       = 0.02f;
// أعلى جهد حقيقي ممكن من الموتور. قِيس بالملتيميتر 0.24V مع أقوى نفخ، فأي عينة
// فوق 0.6V قراءة خاطئة من المحول (تظهر 4.03V عند السكون) وتُحسب صفرًا.
const float V_VALID_MAX = 0.6f;
const float WIND_H_M    = 1.8f;    // ارتفاع مقياس الرياح بالأمتار

// ---- مصدر الطاقة ----
// الإصدار 2: التغذية من USB بجهد 5V، ودائرة البطارية مؤجلة.
// المدخل A1 في ADS1115 غير مستخدم.
const char* POWER_SOURCE = "usb";

// ---- المنافذ (القسم 5.1 من دليل البناء) ----
#define PIN_DHT      4     // DATA في DHT22
#define PIN_DS      13     // DATA في DS18B20 (1-Wire)
#define PIN_I2C_SDA 21
#define PIN_I2C_SCL 22
#define TFT_CS       5
#define TFT_DC      16
#define TFT_RST     17
#define TFT_BL      32     // إضاءة الشاشة بـ PWM
// ناقل SPI للشاشة: CLK = GPIO 18 و MOSI = GPIO 23 (المنافذ القياسية VSPI)

// ---- عناوين I2C ----
// عناوين I2C المتوقعة
#define ADDR_VEML7700 0x10
#define ADDR_ADS1115  0x48
#define ADDR_MLX90614 0x5A

// ---- إضاءة الشاشة (0 إلى 255) ----
const int TFT_BRIGHTNESS = 200;

// ---- الوقت: الرياض UTC+3 (FW-14) ----
const long  GMT_OFFSET_SEC      = 3 * 3600;
const int   DAYLIGHT_OFFSET_SEC = 0;
const char* NTP_SERVER          = "pool.ntp.org";

/* ===========================================================================
   نهاية قسم الإعدادات
   =========================================================================== */

// ---- فترات القراءة الداخلية (القسم 6.3) ----
const unsigned long WIND_SAMPLE_MS = 100UL;    // FW-04
const unsigned long SENSOR_READ_MS = 5000UL;   // FW-05
const unsigned long DHT_MIN_MS     = 2000UL;   // FW-05: DHT22 لا يُقرأ أسرع من ثانيتين
const unsigned long SCREEN_MS      = 2000UL;
const unsigned long WIFI_RETRY_MS  = 30000UL;  // FW-08
const unsigned long DS_CONV_MS     = 800UL;    // زمن تحويل DS18B20 بدقة 12 بت

// ---- الحالات (الجدول 3.2) ----
const char* ST_OK        = "ok";
const char* ST_NOT_FOUND = "not_found";
const char* ST_READ_ERR  = "read_error";
const char* ST_ASSUMED   = "assumed";
const char* ST_DISABLED  = "disabled";

// ---- الكائنات ----
DHT dht(PIN_DHT, DHT22);
Adafruit_ADS1115 ads;
Adafruit_MLX90614 mlx;
Adafruit_VEML7700 veml = Adafruit_VEML7700();
Adafruit_ST7789 tft = Adafruit_ST7789(TFT_CS, TFT_DC, TFT_RST);

#if ENABLE_GLOBE
OneWire oneWire(PIN_DS);
DallasTemperature globeBus(&oneWire);
#endif

// ---- حالة القطع عند الإقلاع (FW-01، FW-02، FW-03) ----
bool has_ads = false, has_mlx = false, has_veml = false;
int  ds_count = 0;
const char* st_dht = ST_READ_ERR;     // FW-03: تُحدد من أول قراءة
String i2cFound = "";                  // نص العناوين المكتشفة للتشخيص

// ---- القراءات الحالية ----
float ta = NAN, rh = NAN, tg = NAN, tsurf = NAN, tamb = NAN, lux = NAN;
float windV = NAN, windMs = NAN;

// ---- تجميع عينات الرياح (FW-04) ----
double windSum = 0.0;
uint32_t windN = 0;

// ---- جدولة غير حاجزة (FW-09) ----
unsigned long tWind = 0, tSensors = 0, tDht = 0, tScreen = 0, tSend = 0;
unsigned long tWifiRetry = 0, tDsRequest = 0;
bool dsConverting = false;

// ---- رد الخادم (FW-11) ----
float  srvWbgt = NAN;
String srvFlag = "";          // white / green / yellow / red / black
bool srvOk = false;

// ---- ألوان ----
#define COL_BG      ST77XX_BLACK
#define COL_TEXT    ST77XX_WHITE
#define COL_DIM     0x8410
#define COL_OK      0x07E0
#define COL_WARN    0xFD20
#define COL_BAD     0xF800

unsigned long sendInterval() { return TEST_MODE ? SEND_MS_TEST : SEND_MS_LONG; }

/* ---------------------------------------------------------------------------
   إضاءة الشاشة: الدوال تغيّرت بين الإصدار 2 والإصدار 3 من حزمة ESP32
   --------------------------------------------------------------------------- */
void backlightInit() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && (ESP_ARDUINO_VERSION_MAJOR >= 3)
  ledcAttach(TFT_BL, 5000, 8);
  ledcWrite(TFT_BL, TFT_BRIGHTNESS);
#else
  ledcSetup(0, 5000, 8);
  ledcAttachPin(TFT_BL, 0);
  ledcWrite(0, TFT_BRIGHTNESS);
#endif
}

/* ---------------------------------------------------------------------------
   FW-01 / FW-13 — فحص ناقل I2C وطباعة العناوين الموجودة
   --------------------------------------------------------------------------- */
void scanI2C() {
  Serial.println("  فحص ناقل I2C…");
  i2cFound = "";
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      found++;
      char buf[8];
      snprintf(buf, sizeof(buf), "0x%02X", addr);
      if (i2cFound.length()) i2cFound += ",";
      i2cFound += buf;
      Serial.printf("    وجدت عنوانًا: %s\n", buf);
      if (addr == ADDR_ADS1115)  has_ads  = true;
      if (addr == ADDR_MLX90614) has_mlx  = true;
      if (addr == ADDR_VEML7700) has_veml = true;
    }
  }
  if (!found) Serial.println("    لا توجد أي قطعة على الناقل! تحقق من SDA وSCL والتغذية.");
}

const char* statusOf(bool present) { return present ? ST_OK : ST_NOT_FOUND; }

/* ---------------------------------------------------------------------------
   سبب آخر إعادة تشغيل — يظهر في لوحة التشخيص، ويساعد على تفسير الفحص CK-06
   (إعادة تشغيل متكررة تعني غالبًا مشكلة طاقة).
   --------------------------------------------------------------------------- */
const char* resetReasonStr() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  return "POWERON";    // توصيل الطاقة
    case ESP_RST_EXT:      return "EXT";        // زر إعادة التشغيل
    case ESP_RST_SW:       return "SW";         // إعادة تشغيل من البرنامج
    case ESP_RST_PANIC:    return "PANIC";      // خطأ في البرنامج
    case ESP_RST_INT_WDT:  return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT:      return "WDT";
    case ESP_RST_BROWNOUT: return "BROWNOUT";   // هبوط الجهد: راجع المكثف والمحول
    case ESP_RST_SDIO:     return "SDIO";
    case ESP_RST_DEEPSLEEP:return "DEEPSLEEP";
    default:               return "UNKNOWN";
  }
}

/* ---------------------------------------------------------------------------
   الاتصال بالواي فاي — لا يحجز الحلقة (FW-08، FW-09)
   --------------------------------------------------------------------------- */
void wifiBegin() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  tWifiRetry = millis();
}

void wifiMaintain() {
  if (WiFi.status() == WL_CONNECTED) return;
  if (millis() - tWifiRetry < WIFI_RETRY_MS) return;
  tWifiRetry = millis();
  Serial.println("  الواي فاي غير متصل — إعادة المحاولة…");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
}

/* ---------------------------------------------------------------------------
   القراءات
   --------------------------------------------------------------------------- */

// FW-04 — عينة سريعة من جهد الموتور
void sampleWind() {
  if (!has_ads) return;
  ads.setGain(GAIN_ONE);                        // مدى ±4.096V
  int16_t raw = ads.readADC_SingleEnded(0);
  float v = ads.computeVolts(raw);
  if (v < 0.0f || v > V_VALID_MAX) v = 0.0f;    // عينة غير منطقية: الموتور واقف
  windSum += v;
  windN++;
}

// FW-03 — حالة DHT22 تُحدد من القراءة نفسها
void readDht() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) {
    st_dht = ST_READ_ERR;
    ta = NAN; rh = NAN;
  } else {
    st_dht = ST_OK;
    ta = t; rh = h;
  }
}

// DS18B20 بتحويل غير حاجز: نطلب القراءة، ونعود إليها بعد 800 ملي ثانية (FW-09)
// مؤجلة في هذا الإصدار؛ تعمل عند تشغيل ENABLE_GLOBE.
void requestGlobe() {
#if ENABLE_GLOBE
  if (ds_count <= 0) { tg = NAN; return; }
  globeBus.requestTemperatures();
  dsConverting = true;
  tDsRequest = millis();
#else
  tg = NAN;
#endif
}

void collectGlobe() {
#if ENABLE_GLOBE
  if (!dsConverting) return;
  if (millis() - tDsRequest < DS_CONV_MS) return;
  dsConverting = false;
  float t = globeBus.getTempCByIndex(0);
  tg = (t == DEVICE_DISCONNECTED_C) ? NAN : t;
#endif
}

void readOthers() {
  if (has_mlx) {
    float o = mlx.readObjectTempC();
    float a = mlx.readAmbientTempC();
    tsurf = isnan(o) ? NAN : o;
    tamb  = isnan(a) ? NAN : a;
  } else { tsurf = NAN; tamb = NAN; }

  if (has_veml) {
    float l = veml.readLux();
    lux = (isnan(l) || l < 0) ? NAN : l;
  } else lux = NAN;
}

/* ---------------------------------------------------------------------------
   بناء رسالة JSON — عقد البيانات schema 2 (القسم 5)
   DS-02: القيمة غير المتوفرة تُرسل null، لا تُحذف ولا تُرسل كرقم وهمي.
   ArduinoJson يكتب NaN على شكل null تلقائيًا، ونؤكد ذلك بدالة صريحة.
   --------------------------------------------------------------------------- */
void putNum(JsonObject obj, const char* key, float value, int decimals = 2) {
  if (isnan(value)) obj[key] = nullptr;
  else obj[key] = serialized(String(value, decimals));
}

String buildJson(float wv, float wms) {
  JsonDocument doc;

  doc["schema"]    = SCHEMA_VER;
  doc["node_id"]   = NODE_ID;
  doc["fw"]        = FW_VERSION;

  // FW-14 — وقت NTP، أو null ليضع الخادم وقت الاستلام (SV-03)
  time_t now = time(nullptr);
  if (now > 1600000000) doc["ts"] = (long)now;
  else                  doc["ts"] = nullptr;

  doc["uptime_s"]     = (uint32_t)(millis() / 1000UL);
  doc["reset_reason"] = resetReasonStr();
  doc["heap_free"]    = (uint32_t)ESP.getFreeHeap();
  doc["power_source"] = POWER_SOURCE;          // الإصدار 2: التغذية من USB
  doc["send_interval_s"] = (uint32_t)(sendInterval() / 1000UL);

  JsonObject wifi = doc["wifi"].to<JsonObject>();
  bool connected = (WiFi.status() == WL_CONNECTED);
  wifi["connected"] = connected;
  if (connected) {
    wifi["rssi"] = WiFi.RSSI();
    wifi["ip"]   = WiFi.localIP().toString();
  } else {
    wifi["rssi"] = nullptr;
    wifi["ip"]   = nullptr;
  }

  JsonArray i2c = doc["i2c_found"].to<JsonArray>();
  if (has_veml) i2c.add("0x10");
  if (has_ads)  i2c.add("0x48");
  if (has_mlx)  i2c.add("0x5A");

  JsonObject s = doc["sensors"].to<JsonObject>();

  JsonObject o_dht = s["dht22"].to<JsonObject>();
  o_dht["status"] = st_dht;
  putNum(o_dht, "ta_c", ta, 1);
  putNum(o_dht, "rh_pct", rh, 1);

  // الكرة الحرارية والبطارية مؤجلتان: تُرسلان بحالة disabled مع null (DS-02)
  JsonObject o_ds = s["ds18b20"].to<JsonObject>();
#if ENABLE_GLOBE
  o_ds["status"] = (ds_count <= 0) ? ST_NOT_FOUND : (isnan(tg) ? ST_READ_ERR : ST_OK);
  putNum(o_ds, "tg_c", tg, 1);
  o_ds["count"] = ds_count;
#else
  o_ds["status"] = ST_DISABLED;
  o_ds["tg_c"]   = nullptr;
  o_ds["count"]  = 0;
#endif

  JsonObject o_ads = s["ads1115"].to<JsonObject>();
  o_ads["status"] = statusOf(has_ads);

  JsonObject o_an = s["anemometer"].to<JsonObject>();
  o_an["status"] = !has_ads ? ST_NOT_FOUND : (isnan(wv) ? ST_READ_ERR : ST_OK);
  putNum(o_an, "wind_v", wv, 4);
  putNum(o_an, "wind_ms", wms, 2);
  putNum(o_an, "height_m", WIND_H_M, 2);
  o_an["samples"] = windN;

  JsonObject o_bat = s["battery"].to<JsonObject>();
  o_bat["status"] = ST_DISABLED;
  o_bat["bat_v"]  = nullptr;

  JsonObject o_mlx = s["mlx90614"].to<JsonObject>();
  o_mlx["status"] = !has_mlx ? ST_NOT_FOUND : (isnan(tsurf) ? ST_READ_ERR : ST_OK);
  putNum(o_mlx, "tsurf_c", tsurf, 1);
  putNum(o_mlx, "tamb_c", tamb, 1);

  JsonObject o_veml = s["veml7700"].to<JsonObject>();
  o_veml["status"] = !has_veml ? ST_NOT_FOUND : (isnan(lux) ? ST_READ_ERR : ST_OK);
  putNum(o_veml, "lux", lux, 0);

  JsonObject o_tft = s["tft"].to<JsonObject>();
  o_tft["status"] = ST_ASSUMED;        // لا طريقة للتحقق من الشاشة

  String out;
  serializeJson(doc, out);
  return out;
}

/* ---------------------------------------------------------------------------
   FW-07 — الإرسال بالطريقتين معًا: HTTP عبر الواي فاي، وسطر DATA: على USB
   FW-11 — قراءة UTCI من رد الخادم
   --------------------------------------------------------------------------- */
void sendMessage(const String& body) {
  // DS-05 — سطر USB دائمًا، حتى لو كان الواي فاي يعمل
  Serial.print("DATA:");
  Serial.println(body);

  if (WiFi.status() != WL_CONNECTED) {
    srvOk = false;
    return;
  }

  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(4000);
  if (!http.begin(SERVER_URL)) {
    Serial.println("  تعذر تهيئة الاتصال بالخادم؛ تحقق من SERVER_URL.");
    srvOk = false;
    return;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Transport", "wifi");

  int code = http.POST(body);
  if (code == 200) {
    String reply = http.getString();
    JsonDocument r;
    if (deserializeJson(r, reply) == DeserializationError::Ok) {
      srvOk = r["accepted"] | false;
      // الإصدار 0.4.0: المؤشر الرئيسي WBGT والعلم (دليل علم البيانات v3)
      srvWbgt = r["wbgt_c"].isNull() ? NAN : r["wbgt_c"].as<float>();
      srvFlag = r["flag"].isNull() ? String("") : r["flag"].as<String>();
      Serial.printf("  POST 200 · WBGT %.1f · %s\n", srvWbgt, srvFlag.c_str());
    } else {
      Serial.println("  POST 200 لكن رد الخادم غير مقروء.");
    }
  } else {
    srvOk = false;
    Serial.printf("  POST فشل (%d) — %s\n", code,
                  http.errorToString(code).c_str());
  }
  http.end();
}

/* ---------------------------------------------------------------------------
   FW-10 — الشاشة
   ملاحظة: مكتبة Adafruit GFX لا تحتوي حروفًا عربية، فالعناوين بالإنجليزي،
   ولون بطاقة WBGT يأتي من العلم الذي يرجعه الخادم.
   --------------------------------------------------------------------------- */
// ألوان الأعلام الخمسة لـ WBGT، ولون الكتابة المقروء فوق كل منها
uint16_t flagColor(const String& f) {
  if (f == "white")  return 0xFFFF;
  if (f == "green")  return 0x07E0;
  if (f == "yellow") return 0xFFE0;
  if (f == "red")    return 0xF800;
  if (f == "black")  return 0x2104;   // رمادي داكن مع إطار أبيض، لأن خلفية الشاشة سوداء
  return COL_DIM;
}

uint16_t flagInk(const String& f) {
  return (f == "white" || f == "yellow" || f == "green") ? ST77XX_BLACK : ST77XX_WHITE;
}

// هامش 20 بكسل يحمي النص من الزوايا الدائرية في شاشة 1.69 بوصة
#define M 20
#define SCR_W 240
#define SCR_H 280
#define INNER_W (SCR_W - 2 * M)

void drawValue(int x, int y, const char* label, float v, const char* unit, int dec) {
  tft.setTextSize(1);
  tft.setTextColor(COL_DIM, COL_BG);
  tft.setCursor(x, y);
  tft.print(label);

  tft.setTextSize(2);
  tft.setTextColor(isnan(v) ? COL_BAD : COL_TEXT, COL_BG);
  tft.setCursor(x, y + 12);
  if (isnan(v)) tft.print("--    ");
  else {
    tft.print(v, dec);
    tft.setTextSize(1);
    tft.print(" ");
    tft.print(unit);
    tft.print("   ");
  }
}

/* ---------------------------------------------------------------------------
   FW-10 — تخطيط شاشة 240×280:
     بطاقة WBGT كبيرة بلون العلم، ثم حرارة الهواء والرطوبة والرياح،
     ثم سطر الاتصال. كل شيء داخل هامش 20 بكسل.
   الكرة والبطارية لا تظهران، لأنهما مؤجلتان في هذا الإصدار.
   --------------------------------------------------------------------------- */
void drawScreen() {
  // بطاقة WBGT بلون العلم
  uint16_t bc  = isnan(srvWbgt) ? 0x2104 : flagColor(srvFlag);
  uint16_t ink = isnan(srvWbgt) ? COL_TEXT : flagInk(srvFlag);
  tft.fillRect(M, M, INNER_W, 96, bc);
  if (srvFlag == "black") tft.drawRect(M, M, INNER_W, 96, ST77XX_WHITE);

  tft.setTextColor(ink, bc);
  tft.setTextSize(1);
  tft.setCursor(M + 8, M + 8);
  tft.print("WBGT");

  tft.setTextSize(5);
  tft.setCursor(M + 8, M + 26);
  if (isnan(srvWbgt)) tft.print("--.-");
  else                tft.print(srvWbgt, 1);

  tft.setTextSize(1);
  tft.setCursor(M + 8, M + 76);
  if (srvFlag.length()) {
    String up = srvFlag;
    up.toUpperCase();
    tft.print(up + " FLAG        ");
  } else {
    tft.print("waiting for server");
  }

  // القيم الأساسية
  int y = M + 110;
  drawValue(M,      y,      "AIR TEMP", ta,     "C",   1);
  drawValue(M + 100, y,     "HUMIDITY", rh,     "%",   0);
  y += 44;
  drawValue(M,      y,      "WIND",     windMs, "m/s", 2);
  drawValue(M + 100, y,     "WIND RAW", windV,  "V",   3);
  y += 44;
  drawValue(M,      y,      "SURFACE",  tsurf,  "C",   1);
  drawValue(M + 100, y,     "LUX",      lux,    "lx",  0);

  // سطر الاتصال أسفل الشاشة
  bool wifiUp = (WiFi.status() == WL_CONNECTED);
  tft.setTextSize(1);
  tft.setTextColor(wifiUp ? COL_OK : COL_BAD, COL_BG);
  tft.setCursor(M, SCR_H - M - 8);
  tft.print(wifiUp ? "WiFi OK " : "USB only");
  tft.setTextColor(COL_DIM, COL_BG);
  tft.printf("  %s  up %lus   ", NODE_ID, millis() / 1000UL);
}

/* ===========================================================================
   setup
   =========================================================================== */
void setup() {
  Serial.begin(115200);
  delay(300);                                  // انتظار قصير مرة واحدة فقط عند الإقلاع

  Serial.println();
  Serial.println("══════════════════════════════════════════════");
  Serial.printf("  عقدة الاستشعار %s — الإصدار %s\n", NODE_ID, FW_VERSION);
  Serial.printf("  سبب آخر إعادة تشغيل: %s\n", resetReasonStr());
  Serial.println("══════════════════════════════════════════════");

  // الشاشة أولًا، حتى تظهر رسالة أثناء بقية الإقلاع
  backlightInit();
  // ST7789V2 مقاس 1.69 بوصة: 240×280. بعض الوحدات تحتاج إزاحة،
  // فإن ظهرت الصورة مقصوصة أو مزاحة جرّب init(240, 280, SPI_MODE2)
  // أو setRowColStart حسب وحدتك.
  tft.init(240, 280);
  tft.setRotation(0);                          // عمودي: 240 عرضًا × 280 ارتفاعًا
  tft.fillScreen(COL_BG);
  tft.setTextColor(COL_TEXT);
  tft.setTextSize(2);
  tft.setCursor(10, 100);
  tft.println("Booting...");

  // I2C — السرعة 100 kHz لأن MLX90614 يفرضها على الناقل كله
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  Wire.setClock(100000);
  scanI2C();                                   // FW-01

  // تهيئة القطع المكتشفة
  if (has_ads) {
    if (!ads.begin(ADDR_ADS1115)) { has_ads = false; Serial.println("  ADS1115 لم يستجب للتهيئة."); }
    else Serial.println("  ADS1115 جاهز.");
  } else Serial.println("  ADS1115 غير موجود (0x48).");

  if (has_mlx) {
    if (!mlx.begin()) { has_mlx = false; Serial.println("  MLX90614 لم يستجب للتهيئة."); }
    else Serial.println("  MLX90614 جاهز.");
  } else Serial.println("  MLX90614 غير موجود (0x5A).");

  if (has_veml) {
    if (!veml.begin()) { has_veml = false; Serial.println("  VEML7700 لم يستجب للتهيئة."); }
    else {
      veml.setGain(VEML7700_GAIN_1);
      veml.setIntegrationTime(VEML7700_IT_100MS);
      Serial.println("  VEML7700 جاهز.");
    }
  } else Serial.println("  VEML7700 غير موجود (0x10).");

  dht.begin();                                 // FW-03

  // FW-02 — عدّ مجسات DS18B20 (عند تفعيل الكرة فقط)
#if ENABLE_GLOBE
  globeBus.begin();
  globeBus.setWaitForConversion(false);        // تحويل غير حاجز (FW-09)
  ds_count = globeBus.getDeviceCount();
  Serial.printf("  عدد مجسات DS18B20: %d%s\n", ds_count,
                ds_count == 0 ? "  (تحقق من مقاومة 4.7kΩ بين DATA و3V3)" : "");
#else
  Serial.println("  الكرة الحرارية مؤجلة (ENABLE_GLOBE = 0): تُرسل بحالة disabled،");
  Serial.println("  والخادم يفترض MRT مساوية لحرارة الهواء.");
#endif
  Serial.printf("  مصدر الطاقة: %s\n", POWER_SOURCE);

  // الواي فاي والوقت
  wifiBegin();
  Serial.printf("  الاتصال بالشبكة %s …\n", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) {
    delay(250);                                // انتظار محدود عند الإقلاع فقط
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("  WiFi connected · IP: %s · RSSI: %d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);   // FW-14
  } else {
    Serial.println("  تعذر الاتصال بالواي فاي. سيستمر القياس والطباعة على USB (FW-08).");
    Serial.println("  استخدم جسر USB: python3 03_usb_bridge/serial_bridge.py");
  }

  Serial.printf("  الخادم: %s\n", SERVER_URL);
  Serial.printf("  فترة الإرسال: %lu ثانية (%s)\n",
                sendInterval() / 1000UL, TEST_MODE ? "وضع الاختبار" : "وضع القياس الطويل");
  Serial.println("══════════════════════════════════════════════\n");

  tft.fillScreen(COL_BG);

  // قراءة أولى فورية حتى لا تبقى الشاشة فارغة
  readDht();
  requestGlobe();
  readOthers();

  unsigned long now = millis();
  tWind = tSensors = tDht = tScreen = tSend = now;
}

/* ===========================================================================
   loop — بلا أي delay، كل مهمة لها جدولتها (FW-09)
   =========================================================================== */
void loop() {
  unsigned long now = millis();

  wifiMaintain();                              // FW-08
  collectGlobe();                              // يلتقط قراءة الكرة عند جاهزيتها

  // FW-04 — عينة رياح كل 100 ملي ثانية
  if (now - tWind >= WIND_SAMPLE_MS) {
    tWind = now;
    sampleWind();
  }

  // FW-05 — DHT22 يُقرأ مع بقية الحساسات، لكن لا أسرع من مرة كل ثانيتين مهما
  // صغّرت SENSOR_READ_MS، لأن القراءة الأسرع من ذلك ترجع NaN.
  if (now - tDht >= max(DHT_MIN_MS, SENSOR_READ_MS)) {
    tDht = now;
    readDht();
  }

  // FW-05 — بقية الحساسات كل 5 ثوانٍ
  if (now - tSensors >= SENSOR_READ_MS) {
    tSensors = now;
    requestGlobe();
    readOthers();
  }

  // FW-10 — تحديث الشاشة كل ثانيتين
  if (now - tScreen >= SCREEN_MS) {
    tScreen = now;
    drawScreen();
  }

  // FW-06 / FW-07 — الإرسال
  if (now - tSend >= sendInterval()) {
    tSend = now;

    if (windN > 0) {
      windV = (float)(windSum / (double)windN);
    } else if (!has_ads) {
      windV = NAN;
    }
    // DS-04 — العقدة ترسل القيم الخام، والخادم يحسب MRT وUTCI.
    // سرعة الرياح تُحسب هنا للعرض على الشاشة فقط، ويعيد الخادم حسابها
    // من wind_v بمعاملات المعايرة المحفوظة فيه (SV-15).
    if (isnan(windV))       windMs = NAN;
    else if (windV < V_MIN) windMs = 0.0f;
    else                    windMs = K_WIND * windV + B_WIND;

    String body = buildJson(windV, windMs);
    sendMessage(body);

    windSum = 0.0;
    windN = 0;
  }
}
