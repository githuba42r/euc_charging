# Smart charging automations

This guide shows how to combine the **EUC Charging Monitor** integration with a
Zigbee smart plug to manage your wheel's charging automatically:

- **Nightly top-up to 95%** — everyday charging that stops short of full to reduce cell wear
- **Ride-day charge to 100%** — full range when you need it, with a readiness check before the ride
- **Monthly extended balance charge** — hold at 100% for several hours so the BMS can balance the cells
- **Safety and convenience** — charger off when the wheel isn't charging, pause while you're away, and an optional button for manual control

Everything here is available three ways — pick whichever suits you:

| Option | Where | Best for |
|---|---|---|
| Blueprints | [`blueprints/automation/euc_charging/`](../blueprints/automation/euc_charging/) | Setting up in the UI with entity pickers |
| Blueprint usage examples | [`examples/blueprint_usage/automations.yaml`](../examples/blueprint_usage/automations.yaml) | YAML users who want the blueprints pre-filled |
| Complete package | [`examples/packages/euc_charging.yaml`](../examples/packages/euc_charging.yaml) | Copy one file: helpers + all automations |

---

## Hardware

### Charger smart plug (required)

The charger is switched with a Zigbee smart plug with energy monitoring:

| | |
|---|---|
| Device | Tuya **TS011F** Zigbee 16 A smart plug with power monitoring (tested: `_TZ3210_cehuw1lw`) |
| Buy | [AliExpress — Zigbee smart socket](https://www.aliexpress.com/item/1005009214185222.html) |
| Works with | ZHA (tested) and Zigbee2MQTT ([device page](https://www.zigbee2mqtt.io/devices/TS011F_plug_1.html)) |
| Entities | `switch.<plug>` plus `power`, `current`, `voltage` and energy sensors |

Any switch entity that powers the charger works — the automations only need to
turn it on and off. The plug's power sensor is useful for dashboards and for
spotting a charger that is drawing nothing.

> **Note:** TS011F plugs with firmware 1.0.5 or newer don't push power/voltage/current
> automatically; they need polling. ZHA and Zigbee2MQTT handle this, but readings
> may update less often. The automations here don't depend on power readings.

Use a plug rated for your charger. Typical EUC chargers draw 100–600 W; fast
chargers more. The TS011F is rated 16 A / 3680 W.

### Charger button (optional)

A battery-powered Zigbee button next to the charger for manual control —
short press toggles the charger, long press toggles the "full charge" request:

| | |
|---|---|
| Device | **HOBEIAN ZG-101ZL** Zigbee one-button scene switch |
| Buy | [AliExpress — Zigbee scene button](https://www.aliexpress.com/item/1005007344903520.html) |
| Blueprint | Community ZHA blueprint: [ZHA - 1-Button Scene Switch (HOBEIAN ZG-101ZL)](https://community.home-assistant.io/t/zha-1-button-scene-switch-hobeian-zg-101zl/920080) |

Example configuration: the `EUC: Charger button` entry in
[`examples/blueprint_usage/automations.yaml`](../examples/blueprint_usage/automations.yaml).

---

## Integration entities used

| Entity (name in HA) | Type | Used for |
|---|---|---|
| **Battery** | sensor (%) | Charge limits, 100% detection. Live — unavailable while the wheel is disconnected |
| **Last Battery** | sensor (%) | Readiness checks. Keeps the last known value when the wheel disconnects. *Disabled by default — enable it under the entity's settings* |
| **Charging** | binary_sensor | Charge-complete and idle-charger detection |
| **Charging Current** / **Charging Power** | sensor (A / W) | Dashboards; Leaperkim/Veteran wheels |
| **Time to 95% / 100%**, **Charge Rate** | sensor | Dashboards and notifications |

Entity IDs depend on your wheel's name, e.g. `sensor.euc_lk3336_battery_percent`.
Check them under **Settings → Devices & services → EUC Charging Monitor**.

### Helpers

Create these under **Settings → Devices & services → Helpers** (or copy the
helper section of the package file):

| Helper | Purpose |
|---|---|
| `input_boolean.euc_full_charge` | "Charge to 100% this time" — set on ride days or by the button |
| `input_boolean.euc_extended_balance_charge` | Balance mode — the next charge holds at 100% |
| `timer.euc_balance_charge` | Balance hold duration (8 h) |
| `counter.euc_full_charges_since_balance` | Full charges since the last balance |
| `input_datetime.euc_last_balance_charge` (date only) | When the last balance charge finished |
| `input_boolean.euc_paused_for_away`, `euc_resume_full_charge`, `euc_resume_balance_charge` | Away pause/resume (package only) |

---

## Charging strategies

### 1. Nightly top-up to 95%

Li-ion cells age fastest when held at 100%. For everyday riding the charger
starts overnight and is switched off once the battery has stayed above 95% for
5 minutes.

- **Scheduled charge start** — 00:15 every day
- **Stop charging at a limit** — 95%, overridden by the full-charge and balance booleans

### 2. Ride day charge to 100%

On ride days (Sun/Wed/Fri at 08:00 in the examples) the full-charge boolean is
turned on and the charger started, so the 95% limit is skipped and the wheel
charges to 100%.

- **Scheduled charge start** with *Request full charge* enabled
- **Charge complete** — once the wheel has stopped charging for 45 min the charger
  has finished (including its top-off); the plug is turned off and the
  full-charge request cleared, with an optional announcement
- **Ride day readiness check** — every 30 min between 08:15 and 16:00 on ride days,
  warn if the wheel is below 90% and the charger is off, or still below 60% after
  15:00 (it won't reach full before a 5 pm ride). Uses the **Last Battery** sensor
  and only trusts readings updated today

### 3. Extended balance charge (monthly)

The BMS balances cells only near full charge, and only slowly. Periodically
holding the pack at 100% for several hours keeps the cells matched, which
protects range and safety over the pack's life.

**Extended balance charge** blueprint:

1. Counts each completed full charge (battery above 99% for 15 min while the
   full-charge boolean is on)
2. Turns balance mode on after **20 full charges** or **30 days** since the last
   balance (checked daily at 07:00 and whenever the counter changes)
3. When the battery reaches 100% in balance mode, starts the **8 h** hold timer
4. When the timer finishes: charger off, modes cleared, counter reset and the
   date recorded
5. If you turn balance mode off by hand, the hold is cancelled and the date
   recorded so it isn't re-enabled immediately

While balance mode is on, the 95% limit, charge-complete and idle-charger
automations step aside.

### 4. Safety and convenience

- **Charger off when the wheel isn't charging** — plug on for 5 min but the wheel
  reports it isn't charging (not plugged in, or already full): turn the plug off
  and notify. Skipped during a balance charge
- **Pause while away** *(package example)* — if you've been away for 5 min with
  the charger on, remember the current mode and switch off; 15 min after you're
  home again, restore it and resume. Not provided as a blueprint because it
  depends on your presence setup
- **Charger button** — see [Hardware](#charger-button-optional)

---

## Blueprints

Import a blueprint with its button (requires Home Assistant with
[My Home Assistant](https://my.home-assistant.io/) links enabled), then create
an automation from it under **Settings → Automations & scenes → Blueprints**.

| Blueprint | Import |
|---|---|
| Scheduled charge start | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fscheduled_charge.yaml) |
| Stop charging at a limit | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fcharge_limit.yaml) |
| Charge complete | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fcharge_complete.yaml) |
| Extended balance charge | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fbalance_charge.yaml) |
| Charger off when the wheel isn't charging | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fcharger_idle_off.yaml) |
| Ride day readiness check | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgithuba42r%2Feuc_charging%2Fblob%2Fmaster%2Fblueprints%2Fautomation%2Feuc_charging%2Fride_ready_check.yaml) |

A typical setup uses: two **Scheduled charge start** automations (nightly + ride
days), one **Stop charging at a limit**, one **Charge complete**, one **Extended
balance charge**, one **Charger off when the wheel isn't charging** and, if you
ride on set days, one **Ride day readiness check**.

### Notification actions

Blueprints that notify take a list of actions, so you can use any notifier —
phone, TTS, Alexa:

```yaml
completion_actions:
  - action: notify.mobile_app_my_phone
    data:
      message: EUC charging complete - charger turned off.
  - action: notify.alexa_media
    data:
      message: The wheel is charged.
      target: media_player.office_echo
      data:
        type: tts
```

The readiness check exposes `{{ message }}` and `{{ battery }}` to its actions.

---

## Tips

- **Charge-complete timing:** many EUC chargers keep trickling after the BMS
  reports full. The 45 min "not charging" window avoids switching off during
  brief pauses; shorten it if your charger stops cleanly.
- **Which battery sensor:** use **Battery** (live) for triggers while charging and
  **Last Battery** for checks that may run while the wheel is disconnected.
- **Bluetooth range:** the wheel must be within range of Home Assistant's Bluetooth
  adapter or an ESPHome Bluetooth proxy while charging. Only one Bluetooth client
  can connect to a wheel at a time — close EUC World/WheelLog or turn off the
  integration's auto-connect switch to use the app.
- **Charging current** is currently decoded for Leaperkim/Veteran wheels only
  (the integration's Charging Current sensor), straight from the wheel's telemetry.
