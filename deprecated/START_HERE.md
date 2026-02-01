# 🚀 START HERE - Leaperkim Sherman S Bluetooth LE Client

## Welcome! 👋

You now have a complete Node.js application to connect to your Leaperkim Sherman S Electric Unicycle and monitor its battery charging status.

### ⚠️ Important: Hardware Required

This project requires:
- **Linux computer** with **Bluetooth 4.0+ hardware** (built-in or USB adapter)
- **Leaperkim Sherman S** device (powered on, in range)

**If running in a cloud/demo environment** (no Bluetooth hardware):
- See **HARDWARE_SETUP.md** for instructions
- Test the decoder with: `node test-decoder.js`
- Once you have real hardware, return here and run the 3 steps below

---

## ⚡ Quick Start (3 Steps)

### Step 1: Run Device Discovery (30 seconds)
```bash
cd /home/philg/working/euc-dump
sudo node discover.js
```
**What it does:** Finds your device and shows all available Bluetooth services

**Expected output:**
```
Service: 180F
  Characteristic: 2A19 (Battery Level)
    Properties: read, notify
```

---

### Step 2: Capture Battery Data (5-10 minutes)
```bash
sudo node client.js
```
**What it does:**
- Connects to your device
- Subscribes to battery notifications
- Logs all data to `battery_data.log`
- Shows real-time updates in console

**Keep your device charging during this step!**

Stop with: `Ctrl+C`

---

### Step 3: Analyze the Data (immediate)
```bash
node test-decoder.js
```
**What it does:**
- Parses your captured data
- Shows possible battery metrics
- Matches data against known patterns

---

## 📖 Documentation

After the quick start, read:

1. **INDEX.md** - Complete project overview
2. **GETTING_STARTED.md** - Detailed step-by-step guide
3. **QUICK_REFERENCE.md** - Command cheat sheet

For advanced topics:
- **REVERSE_ENGINEERING.md** - How to understand the protocol
- **ESPHOME_GUIDE.md** - How to integrate with Home Assistant (future)

---

## 🎯 What You'll Discover

The three steps above will help you:

✅ **Identify** which Bluetooth services your device uses
✅ **Capture** real battery data while charging
✅ **Decode** voltage, current, and battery level values

---

## 💡 Tips for Success

1. **Device must be powered on** - Make sure Leaperkim is turned on
2. **Plug it in** - Best results when device is actually charging
3. **Be patient** - Discovery takes ~30 seconds
4. **Let it run** - Capture data for at least 5-10 minutes
5. **Keep notes** - Write down service/characteristic UUIDs you find

---

## ⚠️ Permissions

Some commands need `sudo`:
```bash
sudo node discover.js
sudo node client.js
```

If you don't want to use sudo:
```bash
sudo usermod -a -G bluetooth $USER
# Log out and back in, then commands work without sudo
```

---

## 🔧 What's Installed

- **noble** - Bluetooth LE library (handles all BLE communication)
- **Node.js modules** - Everything needed to run the scripts

All automatically installed. No additional setup needed!

---

## 📁 Key Files

```
discover.js      ← Run this first
client.js        ← Run this second (with device charging)
test-decoder.js  ← Run this third (analyze results)
decoder.js       ← Library (imported by other scripts)
config.js        ← Configuration template
```

---

## 🎓 What You'll Learn

- How Bluetooth LE (BLE) works
- How to discover BLE devices and services
- How to parse binary data
- How to reverse-engineer device protocols
- How to integrate with Home Assistant

---

## 🆘 If Something Goes Wrong

**"Device not found"**
- Make sure device is powered on
- Make sure it's within 10 meters
- Try: `bluetoothctl scan on` (in another terminal)

**"Permission denied"**
- Either use `sudo node discover.js`
- Or run the setup command to add your user to bluetooth group

**"No data received"**
- Device might not be in BLE range
- Device might need pairing first
- Try with: `bluetoothctl connect 88:25:83:F3:5D:30`

More help: See **REVERSE_ENGINEERING.md**

---

## 🌍 Future Integration

Once you've successfully captured battery data, you can:

1. **Integrate with Home Assistant** using ESPHome Bluetooth proxy
2. **Monitor charging** in real-time
3. **Set up alerts** (e.g., battery low, charging complete)
4. **Track battery health** over time

See: **ESPHOME_GUIDE.md**

---

## ✅ You're Ready!

Everything is set up and ready to go.

**Next action:**
```bash
sudo node discover.js
```

Then come back here and follow the other two steps.

---

**Questions?** Check:
- **QUICK_REFERENCE.md** for commands
- **GETTING_STARTED.md** for detailed explanations
- **INDEX.md** for complete overview

Good luck! 🎉
