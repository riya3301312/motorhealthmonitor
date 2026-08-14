/*
 * ESP32 -> USB serial output for the rotor health monitor.
 *
 * Prints one line per reading in the exact format forwarder.py expects:
 *
 *     vibration,temperature,voltage
 *     1.24,38.60,12.03
 *
 * Replace the three read functions with your real sensor code. Everything
 * else can stay as it is.
 */

const unsigned long SAMPLE_INTERVAL_MS = 500;   // two readings per second
unsigned long lastSample = 0;

void setup() {
  Serial.begin(115200);
  delay(500);
  // Do not print banners or debug text on this port once running --
  // the forwarder ignores unparseable lines, but a clean port is easier.
}

float readVibrationMmPerSec() {
  // TODO: replace with your accelerometer code.
  // Typical approach: sample the accelerometer at a few hundred Hz for one
  // window, remove the DC offset, integrate to velocity, then take the RMS
  // so the number is comparable against the ISO 10816 limits.
  return 1.2 + (random(-100, 100) / 1000.0);
}

float readTemperatureC() {
  // TODO: replace with your DS18B20 / LM35 / thermistor read.
  return 38.0 + (random(-40, 40) / 100.0);
}

float readVoltage() {
  // TODO: replace with your voltage divider read.
  // float raw = analogRead(VOLTAGE_PIN);
  // return raw * (3.3 / 4095.0) * DIVIDER_RATIO;
  return 12.0 + (random(-15, 15) / 100.0);
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL_MS) return;
  lastSample = now;

  float vibration   = readVibrationMmPerSec();
  float temperature = readTemperatureC();
  float voltage     = readVoltage();

  Serial.print(vibration, 3);   Serial.print(',');
  Serial.print(temperature, 2); Serial.print(',');
  Serial.println(voltage, 3);
}
