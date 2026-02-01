# Agent Guidelines for euc-dump

This repository contains tools for reverse engineering and monitoring the Leaperkim Sherman S electric unicycle (EUC) via Bluetooth Low Energy (BLE).

## 1. Build, Lint, and Test

### Environment Setup
- **Python:** 3.11+
- **Virtual Environment:** Recommended (`python -m venv .venv && source .venv/bin/activate`)
- **Dependencies:** `pip install -r requirements.txt`

### Running Commands
- **Monitor:** `python monitor.py` (Main live dashboard)
- **Discovery:** `python discover.py` (Find services/UUIDs)
- **Client:** `python client.py` (Raw data capture)
- **Node.js Discovery:** `node discover.js` (Alternative discovery tool)

### Testing
There is no formal test runner (like pytest) configured yet.
- **Unit Tests:** `decoder.py` contains a `if __name__ == "__main__":` block with self-tests using captured hex data.
- **Run Tests:** `python decoder.py`
- **Future Tests:** If adding new logic, prefer creating a standard `tests/` directory and using `pytest`.

### Linting
- Follow PEP 8 standards.
- Type hints are strongly encouraged.
- Recommended command: `ruff check .` (if installed) or `python -m py_compile *.py` to check syntax.

## 2. Code Style & Conventions

### Python Style
- **Formatting:** 4 spaces for indentation. No tabs.
- **Line Length:** ~88-100 characters (follow generic black/ruff defaults).
- **Type Hints:** Use standard `typing` (e.g., `list[str]`, `dict[str, Any]`, `Optional[int]`).
- **Docstrings:** Required for all modules, classes, and complex functions. Use triple double-quotes `"""`.

### Naming Conventions
- **Classes:** `PascalCase` (e.g., `ShermanSDecoder`, `LiveMonitor`)
- **Functions/Variables:** `snake_case` (e.g., `decode_frame`, `voltage_raw`)
- **Constants:** `SCREAMING_SNAKE_CASE` (e.g., `TARGET_MAC`, `SERVICE_UUID`)
- **Private Members:** Prefix with `_` (e.g., `_notification_handler`)

### Imports
Group imports in the following order, separated by a blank line:
1. **Standard Library:** `sys`, `struct`, `asyncio`, `datetime`
2. **Third-Party:** `bleak`
3. **Local/Project:** `from decoder import ...`

### Error Handling
- Use `try/except` blocks for network (BLE) and parsing operations.
- Catch specific exceptions (`struct.error`, `asyncio.CancelledError`) rather than bare `Exception`.
- BLE connections should handle timeouts and disconnections gracefully.

## 3. Architecture & Patterns

- **Async/Await:** Heavy use of `asyncio` for BLE operations. Ensure functions interacting with `BleakClient` are `async`.
- **Byte Parsing:** Use `struct.unpack` for binary data. Be mindful of endianness (Sherman S uses Big Endian `>`).
- **Data Classes:** Use `@dataclass` for structured telemetry data (see `ShermanSTelemetry` in `decoder.py`).
- **Hardware Constants:** The target device MAC `88:25:83:F3:5D:30` and Service UUIDs are currently hardcoded constants. Preserve this pattern unless refactoring to a config file.

## 4. Key Files
- `monitor.py`: Main entry point for the TUI dashboard.
- `decoder.py`: Core logic for parsing raw BLE bytes into physics values.
- `requirements.txt`: Project dependencies.
