---
name: New EUC Model Support
about: Submit data to add support for a new EUC model
title: '[New Model] '
labels: new-model
assignees: ''
---

## EUC Information

- **Brand**: (e.g., Veteran, KingSong, InMotion, etc.)
- **Model**: (e.g., Sherman Max, V14, etc.)
- **Battery Configuration**: (e.g., 24S, 30S, 42S, etc.)
- **Firmware Version**: (if known)

## Data Capture

Please capture BLE data from your EUC using the `euc_logger.py` tool:

```bash
# Scan for your device
python3 euc_logger.py scan

# Capture data (60 seconds in each scenario)
python3 euc_logger.py capture --address XX:XX:XX:XX:XX:XX --duration 60
```

**Required Captures** (attach JSON files):
1. ☐ Idle (wheel sitting still, not charging)
2. ☐ Charging (actively charging)
3. ☐ Different battery levels (e.g., 50%, 80%, 100%)
4. ☐ Riding (optional but helpful)

## Attach Capture Files

Please attach the JSON capture files from `euc_captures/` directory, or provide a link to them (e.g., Google Drive, Dropbox).

## Additional Information

- Does your EUC work with WheelLog or other apps?
- Are there any special connection requirements?
- Any other relevant details about the model?

## Instructions

For detailed instructions on capturing and analyzing data, see:
- [DATA_CAPTURE_GUIDE.md](../../../DATA_CAPTURE_GUIDE.md)
- [DATA_ANALYSIS_GUIDE.md](../../../DATA_ANALYSIS_GUIDE.md)

Thank you for contributing to multi-brand support! 🎉
