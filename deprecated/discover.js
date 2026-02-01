#!/usr/bin/env node

/**
 * Bluetooth Device Discovery - Using D-Bus Backend
 * Works without sudo when proper permissions are set
 */

const Noble = require('@abandonware/noble');

const TARGET_MAC = '88:25:83:F3:5D:30';
const TARGET_NAMES = ['LK3336', 'Sherman S', 'Veteran', 'Sherman'];
let targetPeripheral = null;

function normalizeAddress(address) {
  return address.toLowerCase().replace(/:/g, '');
}

function matchesTarget(address, name) {
  // Match by MAC address
  if (normalizeAddress(address) === normalizeAddress(TARGET_MAC)) {
    return true;
  }
  // Match by device name
  if (name && TARGET_NAMES.some(n => name.includes(n))) {
    return true;
  }
  return false;
}

console.log('Leaperkim Sherman S - Bluetooth LE Discovery');
console.log('============================================\n');
console.log('Target Device: ' + TARGET_MAC + ' or name containing: ' + TARGET_NAMES.join(', '));
console.log('Starting scan...\n');

// Handle state changes
Noble.on('stateChange', (state) => {
  console.log(`[Bluetooth] State: ${state}`);

  if (state === 'poweredOn') {
    console.log('Bluetooth is ready. Scanning for devices...\n');
    Noble.startScanning([], true);
  } else {
    console.log('Bluetooth is not available.');
    if (state === 'unauthorized') {
      console.log('ERROR: Bluetooth access denied. Try:');
      console.log('  sudo usermod -a -G bluetooth $USER');
      console.log('  # Log out and back in');
    }
  }
});

// Handle discovered devices
Noble.on('discover', (peripheral) => {
  const address = peripheral.address;
  const name = peripheral.advertisement.localName || '(unknown)';

  // Log all discovered devices
  console.log(`Found: ${name} (${address}) RSSI: ${peripheral.rssi}`);

  if (matchesTarget(address, name)) {
    if (!targetPeripheral) {
      console.log(`\n✓ TARGET DEVICE FOUND!\n`);
      console.log(`MAC Address:    ${address}`);
      console.log(`Device Name:    ${name}`);
      console.log(`RSSI:           ${peripheral.rssi} dBm`);
      console.log(`Advertisement: ${JSON.stringify(peripheral.advertisement)}\n`);

      targetPeripheral = peripheral;
      Noble.stopScanning();

      setTimeout(() => {
        connectAndDiscover(peripheral);
      }, 500);
    }
  }
});

async function connectAndDiscover(peripheral) {
  try {
    console.log('Connecting to device...');

    await new Promise((resolve, reject) => {
      peripheral.connect((err) => {
        if (err) reject(err);
        else {
          console.log('✓ Connected\n');
          resolve();
        }
      });
    });

    console.log('Discovering services and characteristics...\n');

    const result = await new Promise((resolve, reject) => {
      peripheral.discoverAllServicesAndCharacteristics((err, services, characteristics) => {
        if (err) reject(err);
        else resolve({ services, characteristics });
      });
    });

    const { services, characteristics } = result;

    console.log(`Found ${services.length} services:\n`);

    services.forEach((service) => {
      console.log(`Service: ${service.uuid}`);
      const serviceChars = characteristics.filter(c => c._serviceUuid === service.uuid);

      serviceChars.forEach((char) => {
        console.log(`  ├─ ${char.uuid}`);
        console.log(`  │  Properties: ${char.properties.join(', ')}`);
      });
      console.log('');
    });

    console.log('Disconnecting...');
    await new Promise((resolve) => {
      peripheral.disconnect(() => {
        console.log('✓ Disconnected\n');
        resolve();
      });
    });

    console.log('SUCCESS! Device discovery complete.');
    process.exit(0);

  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

// Error handling
Noble.on('warning', (message) => {
  console.warn(`[Warning] ${message}`);
});

// Timeout
setTimeout(() => {
  if (!targetPeripheral) {
    console.log('\n⚠ Device not found after 30 seconds.');
    console.log('\nTroubleshooting:');
    console.log('  1. Make sure device is powered on');
    console.log('  2. Make sure device is in range (< 10m)');
    console.log('  3. Try: bluetoothctl scan on');
    console.log('  4. Check for permission issues - see HARDWARE_SETUP.md');
    process.exit(1);
  }
}, 30000);
