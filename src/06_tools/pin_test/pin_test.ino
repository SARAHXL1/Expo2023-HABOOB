/* ===========================================================================
   هبوب — اختبار مسار السلك من ESP32 إلى القطعة (بدون ملتيميتر)
   يجعل GPIO 21 وGPIO 22 مدخلين مع مقاومة سحب داخلية، ويطبع حالتهما كل نصف ثانية.
     1 = الطرف حر (طبيعي)
     0 = الطرف موصول بالأرضي
   الطريقة: سلك واحد طرفه في GND، والطرف الآخر تلمس به النقطة المراد فحصها.
   إذا تحولت القراءة إلى 0 فالمسار من تلك النقطة إلى رجل ESP32 سليم.
   Serial Monitor: 115200 · الحالة: غير مختبر على العتاد بعد.
   =========================================================================== */

#define PIN_SDA 21
#define PIN_SCL 22

void setup() {
  Serial.begin(115200);
  delay(500);
  pinMode(PIN_SDA, INPUT_PULLUP);
  pinMode(PIN_SCL, INPUT_PULLUP);
  Serial.println();
  Serial.println("=== Habub pin test: 1 = free, 0 = touched to GND ===");
}

void loop() {
  int sda = digitalRead(PIN_SDA);
  int scl = digitalRead(PIN_SCL);
  Serial.printf("GPIO21(SDA)=%d   GPIO22(SCL)=%d   %s\n", sda, scl,
                (sda == 0 && scl == 0) ? "<-- BOTH low: SDA and SCL shorted together or to GND?" : "");
  delay(500);
}
