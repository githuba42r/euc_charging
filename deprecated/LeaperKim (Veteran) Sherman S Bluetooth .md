LeaperKim (Veteran) Sherman S Bluetooth Protocol Documentation
This documentation is based on reverse-engineered details from open-source EUC apps like WheelLog and community resources (e.g., electricunicycle.org forums and similar projects like EUC Dash and eucWatch). The Sherman S uses a Bluetooth Low Energy (BLE) protocol similar to older Veteran models (e.g., Sherman, Sherman Max), which is a variant of the Gotway/Begode protocol with minor differences for newer Leaperkim models (e.g., smart BMS support for cell voltages in some firmware). For charging monitoring, the key metrics are voltage, current (positive values indicate charging), battery percentage, and temperature.
The protocol is binary packet-based, with data sent via BLE notifications. No authentication is typically required for basic monitoring; the wheel broadcasts data when powered on. For Node.js, you can use libraries like noble or @abandonware/noble for BLE scanning/connection, or bleno if needed, but noble is sufficient for client-side connection.
1. BLE Connection Details

Device Discovery: Scan for BLE devices with name starting with "Sherman S" or "Veteran" (MAC address may be shown in app). The device advertises when powered on.
Service UUID: 0000fff0-0000-1000-8000-00805f9b34fb (standard for Veteran/Leaperkim; some apps use short "fff0").
Characteristics:
Notification (read/notify): 0000fff1-0000-1000-8000-00805f9b34fb (short "fff1"). Subscribe to this for data packets.
Write (optional): 0000fff2-0000-1000-8000-00805f9b34fb (short "fff2"). Used for commands like firmware version query or settings (e.g., byte array [0x5A, 0x5A] for basic poll, but not always needed as data is periodic).

Connection Steps in Node.js:
Scan for peripherals with the service UUID.
Connect to the peripheral.
Discover the service "fff0".
Discover the characteristic "fff1".
Set notification on "fff1" to true.
On 'data' event, parse the buffer (packets are 20 bytes long).
Optional: Write to "fff2" to request specific data if no packets are coming (e.g., buffer = Buffer.from([0x5A, 0x5A, 0x00, ...]) – see commands below).

Data Rate: Packets are sent every ~200-500ms when the wheel is on.

2. Packet Format
Packets are 20 bytes long, big-endian for multi-byte values. Header is always 0x55 0xAA. Checksum is not always validated in apps, but it's byte sum modulo 256 or similar (ignore for basic parsing).
Example packet structure for basic telemetry (from community reverse engineering; slight variations for smart BMS models like Sherman S):

Byte 0: 0x55 (header)
Byte 1: 0xAA (header)
Bytes 2-3: Voltage (unsigned 16-bit, divide by 100 for volts, e.g., 0x2A F0 = 11024 / 100 = 110.24V)
Bytes 4-5: Speed (signed 16-bit, divide by 100 for m/s, multiply by 3.6 for km/h; negative for reverse)
Bytes 6-9: Trip distance (unsigned 32-bit, divide by 1000 for km)
Bytes 10-11: Current (signed 16-bit, divide by 100 for amps; positive = charging, negative = discharge)
Bytes 12-13: Temperature (unsigned 16-bit, divide by 10 for °C; or (value - 32) for some models)
Bytes 14-15: Total distance (unsigned 16-bit, but often part of bytes 6-9 extension; divide by 1000 for km)
Byte 16: Mode/alarms (bitfield: e.g., 0x00 normal, 0x01 speed alarm)
Byte 17: PWM or firmware version (depending on packet type)
Byte 18: Battery percentage (0-100, but often calculated from voltage if not provided)
Byte 19: Checksum or padding (sum of bytes 2-18 XOR 0xFFFF or similar; optional check)

For Sherman S, newer firmware may send extended packets for smart BMS (cell voltages), but for charging, focus on basic packet.

Charging-Specific Parsing:
Voltage: (byte[2] << 8 | byte[3]) / 100. For Sherman S (84V system, 20s4p, 100.8V max), expect 80-100.8V during charge.
Current: (byte[10] << 8 | byte[11]) / 100 (signed). During charging, this is positive (e.g., 5.0A for charging at 5 amps). During ride, negative.
Battery Percentage: If not in packet, calculate as: ((voltage - minVoltage) / (maxVoltage - minVoltage)) * 100
minVoltage = 67.2V (3.36V per cell for 20s)
maxVoltage = 84V (4.2V per cell)
Clamp to 0-100.

Charging Status: Derived - if current > 0 and voltage rising, charging. Some apps set chargingStatus = 1 if current > 0.
Temperature: (byte[12] << 8 | byte[13]) / 10. Monitor for overheat during fast charge.


If the wheel has smart BMS, there may be a different packet type (e.g., by sending command to "fff2"), but for basic charging tracking, the standard telemetry is sufficient.
3. Commands (Write to "fff2")

Basic poll/data request: Buffer.from([0x5A, 0x5A])
Firmware version: Buffer.from([0x5A, 0x5A, 0x63, 0x00, ...]) – response in packet byte 17.
For smart BMS on Sherman S: Specific command to get cell voltages (e.g., [0x5B, 0x5B, 0x00, ...]), but not needed for charging.
No command needed for charging data; it's in the periodic packet.

4. Node.js Example Structure
To integrate with Home Assistant, use MQTT (e.g., mqtt library) to publish parsed data (e.g., to topic "homeassistant/sensor/euc/charging").
Sample code structure (using noble):
JavaScriptconst noble = require('@abandonware/noble');
const mqtt = require('mqtt');

const serviceUUID = 'fff0';
const notifyUUID = 'fff1';
const writeUUID = 'fff2';

noble.on('stateChange', state => if (state === 'poweredOn') noble.startScanning([serviceUUID]));

noble.on('discover', peripheral => {
  if (peripheral.advertisement.localName.includes('Sherman S')) {
    peripheral.connect(err => {
      peripheral.discoverServices([serviceUUID], (err, services) => {
        services[0].discoverCharacteristics([notifyUUID, writeUUID], (err, characteristics) => {
          const notifyChar = characteristics.find(c => c.uuid === notifyUUID);
          notifyChar.subscribe(err => {
            notifyChar.on('data', data => {
              if (data.length === 20 && data[0] === 0x55 && data[1] === 0xAA) {
                const voltage = ((data[2] << 8) | data[3]) / 100;
                const current = ((data[10] << 8) | data[11]) / 100; // signed, use if (current & 0x8000) current -= 0x10000;
                const battery = Math.min(100, Math.max(0, ((voltage - 67.2) / (84 - 67.2)) * 100));
                const charging = current > 0 ? 'charging' : 'not charging';

                // Publish to Home Assistant via MQTT
                const client = mqtt.connect('mqtt://your-ha-ip:1883');
                client.publish('homeassistant/sensor/euc_voltage', voltage.toString());
                client.publish('homeassistant/sensor/euc_current', current.toString());
                client.publish('homeassistant/sensor/euc_battery', battery.toString());
                client.publish('homeassistant/sensor/euc_charging', charging);
              }
            });
          });
        });
      });
    });
  }
});

Adjust signed values for current (two's complement).
Handle disconnection/reconnect.
For full accuracy, test with your wheel and adjust offsets if firmware differs (Sherman S firmware updates may tweak formats).
Dependencies: npm install @abandonware/noble mqtt.
Run on a device with Bluetooth (e.g., Raspberry Pi for always-on monitoring).

This should allow the AI agent to create a Node.js app. If you have the WheelLog source locally, check GotwayAdapter.java for Veteran-specific branches, as Veteran is often handled there due to protocol similarity. Ride safe, Phil!