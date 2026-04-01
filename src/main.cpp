#include <Arduino.h>
#include <ArduinoBLE.h>

namespace {
constexpr char device_name[] = "NanoESP32-Lights";
constexpr unsigned long status_interval_ms = 2000;

BLEService light_service("a3f8e58e-fdfe-4af9-95a0-d523dac030c5");
BLEStringCharacteristic state_characteristic(
    "0de4cb4f-9d0f-4e4d-a6dd-49fbd2dc6b4a", BLERead | BLEWrite, 256);

unsigned long last_status_log_ms = 0;
bool printed_discoverable_msg = false;
}

void setup() {
  Serial.begin(115200);
  while (!Serial && millis() < 4000) {
    delay(10);
  }

  if (!BLE.begin()) {
    Serial.println("BLE init failed. Restart required.");
    while (true) {
      delay(1000);
    }
  }

  BLE.setLocalName(device_name);
  BLE.setDeviceName(device_name);
  BLE.setAdvertisedService(light_service);

  light_service.addCharacteristic(state_characteristic);
  BLE.addService(light_service);
  state_characteristic.writeValue("{}");

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
      if (state_characteristic.written()) {
        Serial.print("Received state payload: ");
        Serial.println(state_characteristic.value());
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

  if (millis() - last_status_log_ms >= status_interval_ms) {
    last_status_log_ms = millis();
    if (!BLE.connected()) {
      Serial.println("Waiting for BLE central to find and connect...");
    }
  }
}