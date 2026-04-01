#include <Arduino.h>
#include <ArduinoBLE.h>

namespace {
const char* kDeviceName = "NanoESP32-Lights";
const unsigned long kStatusIntervalMs = 2000;

// Simple custom service with one writable characteristic.
// UUID generated using https://www.uuidgenerator.net/version4
BLEService light_service("a3f8e58e-fdfe-4af9-95a0-d523dac030c5");
BLEByteCharacteristic command_characteristic(
    "a3f8e58e-fdfe-4af9-95a0-d523dac030c5", BLERead | BLEWrite);

unsigned long last_status_log_ms = 0;
bool printed_discoverable_msg = false;
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 4000) {
    // Wait for Serial Monitor on USB for a short time.
  }

  if (!BLE.begin()) {
    Serial.println("BLE init failed. Restart required.");
    while (true) {
      delay(1000);
    }
  }

  BLE.setLocalName(kDeviceName);
  BLE.setDeviceName(kDeviceName);
  BLE.setAdvertisedService(light_service);

  light_service.addCharacteristic(command_characteristic);
  BLE.addService(light_service);

  command_characteristic.writeValue((byte)0x00);

  BLE.advertise();
  Serial.println("BLE advertising started. Device is now discoverable.");
  printed_discoverable_msg = true;
}

void loop() {
  BLEDevice central = BLE.central();

  if (central) {
    Serial.print("Device found by central: ");
    Serial.println(central.address());
    Serial.println("Successful BLE connection started.");

    while (central.connected()) {
      if (command_characteristic.written()) {
        byte value = command_characteristic.value();
        Serial.print("Received command byte: ");
        Serial.println(value);
      }
      delay(10);
    }

    Serial.print("Central disconnected: ");
    Serial.println(central.address());

    BLE.advertise();
    Serial.println("Returned to advertising mode (discoverable again).");
    printed_discoverable_msg = true;
  }

  if (!printed_discoverable_msg) {
    Serial.println("Advertising enabled. Waiting to be found...");
    printed_discoverable_msg = true;
  }

  if (millis() - last_status_log_ms >= kStatusIntervalMs) {
    last_status_log_ms = millis();
    if (!BLE.connected()) {
      Serial.println("Waiting for BLE central to find and connect...");
    }
  }
}

