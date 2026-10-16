/* ===========================================================================
   هبوب — اختبار قطع I2C واحدة واحدة
   يفحص الناقل كل ثانيتين، ويقرأ أي قطعة يجدها، ويطبع النتيجة في Serial Monitor.
   لا يحتاج واي فاي ولا خادم. بعد الانتهاء أعد رفع sensor_node.ino.

   المنافذ: SDA = GPIO 21 · SCL = GPIO 22
   Serial Monitor: 115200
   المكتبات (مثبتة مسبقًا لبرنامج العقدة):
     Adafruit ADS1X15 · Adafruit MLX90614 Library · Adafruit VEML7700 Library
   الحالة: غير مختبر على العتاد بعد.
   =========================================================================== */

#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <Adafruit_MLX90614.h>
#include <Adafruit_VEML7700.h>

#define PIN_SDA 21
#define PIN_SCL 22

Adafruit_ADS1115  ads;
Adafruit_MLX90614 mlx;
Adafruit_VEML7700 veml;

bool present(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000);            // MLX90614 يحتاج 100 kHz
  Serial.println();
  Serial.println("=== Habub I2C test  (SDA=21, SCL=22) ===");
  Serial.println("Expected: VEML7700=0x10  ADS1115=0x48  MLX90614=0x5A");
}

void loop() {
  // 1) مسح كل العناوين
  Serial.print("Scan:");
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    if (present(a)) { Serial.printf(" 0x%02X", a); n++; }
  }
  if (n == 0) Serial.print(" NONE  <-- no device answered");
  Serial.println();

  // 2) قراءة القطع الموجودة
  if (present(0x10)) {
    if (veml.begin()) Serial.printf("  VEML7700 OK   lux = %.1f\n", veml.readLux());
    else              Serial.println("  VEML7700 found at 0x10 but begin() failed");
  }
  if (present(0x5A)) {
    if (mlx.begin()) Serial.printf("  MLX90614 OK   object = %.1f C   ambient = %.1f C\n",
                                   mlx.readObjectTempC(), mlx.readAmbientTempC());
    else             Serial.println("  MLX90614 found at 0x5A but begin() failed");
  }
  if (present(0x48)) {
    if (ads.begin(0x48)) {
      ads.setGain(GAIN_ONE);        // مدى ±4.096V (آمن بدون الموتور)
      int16_t raw = ads.readADC_SingleEnded(0);
      Serial.printf("  ADS1115 OK   A0 = %.4f V\n", ads.computeVolts(raw));
    } else Serial.println("  ADS1115 found at 0x48 but begin() failed");
  }

  Serial.println();
  delay(2000);
}
