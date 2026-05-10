const byte BEND_PIN = A0;
const byte MOISTURE_PIN = A1;
const byte PIR_PIN = 2;

const unsigned long SAMPLE_INTERVAL_MS = 50;
const bool USE_INTERNAL_BEND_PULLUP = false;

const bool BEND_DECREASES_WHEN_BENT = true;
const bool PRESSURE_DECREASES_WHEN_PRESSED = true;

const int CALIBRATION_SAMPLES = 100;
const int BEND_DEADBAND_RAW = 3;
const int PRESSURE_DEADBAND_RAW = 2;
const int BEND_FULL_SCALE_RAW_DELTA = 250;
const int PRESSURE_FULL_SCALE_RAW_DELTA = 45;

unsigned long nextSampleAt = 0;
int bendBaselineRaw = 0;
int pressureBaselineRaw = 0;

int readAverageRaw(byte pin) {
  long total = 0;

  for (int sample = 0; sample < CALIBRATION_SAMPLES; sample++) {
    total += analogRead(pin);
  }

  return int(total / CALIBRATION_SAMPLES);
}

void calibrateRestValues() {
  bendBaselineRaw = readAverageRaw(BEND_PIN);
  pressureBaselineRaw = readAverageRaw(MOISTURE_PIN);
}

int directionalDelta(int baselineRaw, int currentRaw, bool decreasesWithAction) {
  if (decreasesWithAction) {
    return baselineRaw - currentRaw;
  }

  return currentRaw - baselineRaw;
}

int deltaToPercent(int deltaRaw, int deadbandRaw, int fullScaleRawDelta) {
  if (deltaRaw <= deadbandRaw) {
    return 0;
  }

  const int usableDelta = constrain(deltaRaw - deadbandRaw, 0, fullScaleRawDelta - deadbandRaw);
  return map(usableDelta, 0, fullScaleRawDelta - deadbandRaw, 0, 100);
}

void printSample() {
  const int bendRaw = analogRead(BEND_PIN);
  const int pressureRaw = analogRead(MOISTURE_PIN);
  const int bendDelta = directionalDelta(bendBaselineRaw, bendRaw, BEND_DECREASES_WHEN_BENT);
  const int pressureDelta = directionalDelta(pressureBaselineRaw, pressureRaw, PRESSURE_DECREASES_WHEN_PRESSED);
  const int bend = deltaToPercent(bendDelta, BEND_DEADBAND_RAW, BEND_FULL_SCALE_RAW_DELTA);
  const int moisture = deltaToPercent(pressureDelta, PRESSURE_DEADBAND_RAW, PRESSURE_FULL_SCALE_RAW_DELTA);
  const int pir = digitalRead(PIR_PIN);

  Serial.print(bend);
  Serial.print(',');
  Serial.print(moisture);
  Serial.print(',');
  Serial.print(pir);
  Serial.print('\n');
}

void setup() {
  Serial.begin(115200);
  if (USE_INTERNAL_BEND_PULLUP) {
    pinMode(BEND_PIN, INPUT_PULLUP);
  }
  pinMode(PIR_PIN, INPUT);
  calibrateRestValues();
  nextSampleAt = millis() + SAMPLE_INTERVAL_MS;
}

void loop() {
  const unsigned long now = millis();

  if ((long)(now - nextSampleAt) >= 0) {
    printSample();
    nextSampleAt += SAMPLE_INTERVAL_MS;

    if ((long)(now - nextSampleAt) >= 0) {
      nextSampleAt = now + SAMPLE_INTERVAL_MS;
    }
  }
}
