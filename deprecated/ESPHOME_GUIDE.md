# ESPHome Bluetooth Proxy Integration Guide

## Overview
Once you've identified the Bluetooth protocol used by your Leaperkim Sherman S unicycle, you can integrate it with Home Assistant using an ESPHome Bluetooth proxy.

## Prerequisites
- ESPHome capable device (ESP32 recommended)
- Home Assistant installation
- Bluetooth LE protocol documentation (from reverse engineering)
- Device MAC address: `88:25:83:F3:5D:30`

## Phase 1: ESPHome Bluetooth Proxy Setup

### Basic ESP32 Configuration
Create `esphome/leaperkim-proxy.yaml`:

```yaml
esphome:
  name: leaperkim-proxy
  friendly_name: "Leaperkim Bluetooth Proxy"

esp32:
  board: esp32-s3-devkitc-1
  framework:
    type: esp-idf

# Enable Bluetooth LE
bluetooth_proxy:
  active: true

# Web server for debugging
web_server:
  port: 80

# API for Home Assistant
api:

ota:
  password: !secret ota_password

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  fast_connect: true

logger:
  level: DEBUG

# Enable BLE scanner for debugging
esp32_ble_tracker:
  scan_parameters:
    interval: 1.1s
    window: 1.1s
```

Deploy with: `esphome run leaperkim-proxy.yaml`

## Phase 2: Custom BLE Service Implementation

Once you know the exact service/characteristic UUIDs, create a custom component:

### Create `esphome/components/leaperkim_battery/leaperkim_battery.h`

```cpp
#pragma once

#include "esphome/core/component.h"
#include "esphome/components/ble_client/ble_client.h"
#include "esphome/components/sensor/sensor.h"

namespace esphome {
namespace leaperkim_battery {

class LeaperkimBattery : public PollingComponent, public ble_client::BLEClientNode {
 public:
  LeaperkimBattery();
  
  void setup() override;
  void update() override;
  void gatt_read_callback(uint16_t conn_handle, const esp_gatt_rsp_t *rsp) override;
  void gatt_notify_callback(uint16_t conn_handle, uint16_t handle, 
                           esp_gatt_srvc_id_t srvc_id, esp_gatt_id_t char_id,
                           uint8_t *value, uint16_t length) override;

  void set_battery_level_sensor(sensor::Sensor *sensor) { battery_level_sensor_ = sensor; }
  void set_voltage_sensor(sensor::Sensor *sensor) { voltage_sensor_ = sensor; }
  void set_current_sensor(sensor::Sensor *sensor) { current_sensor_ = sensor; }

  void set_service_uuid(esp_uuid_t uuid) { service_uuid_ = uuid; }
  void set_characteristic_uuid(esp_uuid_t uuid) { characteristic_uuid_ = uuid; }

 protected:
  sensor::Sensor *battery_level_sensor_{nullptr};
  sensor::Sensor *voltage_sensor_{nullptr};
  sensor::Sensor *current_sensor_{nullptr};
  
  esp_uuid_t service_uuid_{};
  esp_uuid_t characteristic_uuid_{};
  uint16_t char_handle_{0};

  void decode_battery_data_(uint8_t *data, uint16_t length);
};

}  // namespace leaperkim_battery
}  // namespace esphome
```

### Create `esphome/components/leaperkim_battery/leaperkim_battery.cpp`

```cpp
#include "leaperkim_battery.h"
#include "esphome/core/log.h"

namespace esphome {
namespace leaperkim_battery {

static const char *const TAG = "leaperkim_battery";

LeaperkimBattery::LeaperkimBattery() : PollingComponent(5000) {}  // Update every 5s

void LeaperkimBattery::setup() {
  ESP_LOGD(TAG, "Setting up Leaperkim Battery sensor");
  // Subscriptions will be set up when connected
}

void LeaperkimBattery::update() {
  if (!this->node_state == ble_client::BLEClientNode::BLEClientState::ESTABLISHED) {
    ESP_LOGW(TAG, "Not connected to device");
    return;
  }
  
  // Read the battery characteristic
  auto status = esp_ble_gattc_read_char(
    this->parent_->get_gattc_if(),
    this->parent_->get_conn_id(),
    this->char_handle_,
    ESP_GATT_AUTH_REQ_NONE
  );
  
  if (status != ESP_GATT_OK) {
    ESP_LOGW(TAG, "Failed to read characteristic: %d", status);
  }
}

void LeaperkimBattery::gatt_notify_callback(uint16_t conn_handle,
                                           uint16_t handle,
                                           esp_gatt_srvc_id_t srvc_id,
                                           esp_gatt_id_t char_id,
                                           uint8_t *value,
                                           uint16_t length) {
  if (handle == this->char_handle_) {
    this->decode_battery_data_(value, length);
  }
}

void LeaperkimBattery::decode_battery_data_(uint8_t *data, uint16_t length) {
  // Decode based on your discovered format
  // Example for 5-byte format: [level, voltage_low, voltage_high, current_low, current_high]
  
  if (length < 5) {
    ESP_LOGW(TAG, "Data too short: %d bytes", length);
    return;
  }

  uint8_t battery_level = data[0];
  uint16_t voltage_mv = (data[2] << 8) | data[1];  // Little-endian
  int16_t current_ma = (int16_t)((data[4] << 8) | data[3]);  // Little-endian, signed

  float voltage_v = voltage_mv / 1000.0f;
  float current_a = current_ma / 1000.0f;

  ESP_LOGI(TAG, "Battery: %d%%, Voltage: %.2fV, Current: %.3fA",
           battery_level, voltage_v, current_a);

  if (battery_level_sensor_) {
    battery_level_sensor_->publish_state(battery_level);
  }
  if (voltage_sensor_) {
    voltage_sensor_->publish_state(voltage_v);
  }
  if (current_sensor_) {
    current_sensor_->publish_state(current_a);
  }
}

}  // namespace leaperkim_battery
}  // namespace esphome
```

## Phase 3: YAML Configuration

Create a complete Home Assistant integration:

```yaml
esphome:
  name: leaperkim-battery
  friendly_name: "Leaperkim Battery Monitor"

esp32:
  board: esp32-s3-devkitc-1

ble_client:
  - mac_address: 88:25:83:F3:5D:30
    id: leaperkim_device

external_components:
  - source: github://yourusername/esphome-leaperkim
    components: [leaperkim_battery]

leaperkim_battery:
  ble_client_id: leaperkim_device
  # Replace with discovered UUIDs
  service_uuid: "180F"  # Battery Service (or custom)
  characteristic_uuid: "2A19"  # Battery Level (or custom)
  
  battery_level_sensor:
    name: "Unicycle Battery Level"
    unit_of_measurement: "%"
    device_class: battery
    
  voltage_sensor:
    name: "Unicycle Battery Voltage"
    unit_of_measurement: "V"
    device_class: voltage
    
  current_sensor:
    name: "Unicycle Charging Current"
    unit_of_measurement: "A"
    device_class: current

# Rest of your ESPHome config...
api:
ota:
wifi:
logger:
```

## Phase 4: Home Assistant Integration

### Automations
Create automations in Home Assistant based on battery metrics:

```yaml
# Alert when charging completes
- alias: Unicycle Charging Complete
  trigger:
    platform: numeric_state
    entity_id: sensor.unicycle_charging_current
    below: 0.1
    for:
      minutes: 5
  condition:
    condition: numeric_state
    entity_id: sensor.unicycle_battery_level
    above: 95
  action:
    service: notify.persistent_notification
    data:
      message: "Leaperkim charging completed"
      title: "Unicycle"

# Alert for low battery
- alias: Unicycle Low Battery
  trigger:
    platform: numeric_state
    entity_id: sensor.unicycle_battery_level
    below: 20
  action:
    service: notify.mobile_app
    data:
      message: "Unicycle battery low: {{ states('sensor.unicycle_battery_level') }}%"
```

### History Stats
Track charging sessions:

```yaml
sensor:
  - platform: history_stats
    name: Unicycle Daily Charging Time
    entity_id: binary_sensor.unicycle_charging
    state: "on"
    type: time
    period:
      days: 1
```

## Troubleshooting

### Device Not Connecting
1. Verify MAC address is correct
2. Ensure device is in BLE advertising range
3. Check ESP32 Bluetooth is enabled
4. Review logs: `esphome logs leaperkim-proxy`

### No Data Received
1. Verify characteristic UUID is correct
2. Check if device uses notifications vs reads
3. May need to send write command first to enable notifications
4. Review BLE sniffer output to confirm data is being sent

### Inaccurate Values
1. Verify data format matches discovered protocol
2. Check byte order (little-endian vs big-endian)
3. Verify scaling factors (mV vs V, mA vs A)
4. Compare against device's built-in display

## Advanced: Custom Notifications

Some devices require a "Client Characteristic Configuration Descriptor" write to enable notifications:

```cpp
// In your BLE client setup
uint8_t notify_enable = 0x01;
esp_ble_gattc_write_char_descr(
  gattc_if,
  conn_id,
  descr_handle,
  sizeof(notify_enable),
  &notify_enable,
  ESP_GATT_WRITE_TYPE_REQ,
  ESP_GATT_AUTH_REQ_NONE
);
```

## Resources

- [ESPHome BLE Client Documentation](https://esphome.io/components/ble_client.html)
- [Bluetooth GATT Services](https://www.bluetooth.com/specifications/gatt/services/)
- [ESP-IDF BLE Documentation](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/bluetooth/index.html)

## Next Steps

1. Complete reverse engineering (capture device data)
2. Build and test the Node.js client
3. Set up ESPHome device with Bluetooth proxy
4. Deploy custom component
5. Create Home Assistant automations and dashboard

---

**Notes for your setup:**

Service UUID: ___________________
Characteristic UUID: ___________________
Data Format: ___________________
Expected Update Frequency: ___________________
