"""
Shared settings and fault logic.

Both the local forwarder and the cloud dashboard import from here, so the
thresholds shown on the charts can never drift away from the thresholds
actually used to raise a fault.
"""

# ----------------------------------------------------------------------
# Device / serial
# ----------------------------------------------------------------------
DEVICE_ID = "motor-01"          # change if you ever monitor a second motor
SERIAL_PORT = "COM5"            # Windows: COM3, COM4 ... | Linux/Mac: /dev/ttyUSB0
BAUD_RATE = 115200
# Match the ESP32 SAMPLE_INTERVAL_MS (500 ms) in esp32_serial_output.ino.
LIVE_INTERVAL_SEC = 0.5
UPLOAD_INTERVAL_SEC = LIVE_INTERVAL_SEC
DASHBOARD_REFRESH_MS = round(LIVE_INTERVAL_SEC * 1000)

# ----------------------------------------------------------------------
# Experimental ranges read from the user's 2026-10-17 videos.
# Bounds are inclusive; these are observed ranges, not validated safety limits.
# Firmware reports mm/s RMS, but its physical calibration is unverified.
# ----------------------------------------------------------------------
VIB_NORMAL_MIN = 5.064
VIB_NORMAL_MAX = 50.000
VIB_MISALIGN_MIN = 66.409
VIB_MISALIGN_MAX = 200.000
CLASSIFICATION_PROFILE = "shim-reference-2026-10-17"

TEMP_WARN = 60.0                # existing limits, not inferred from these clips
TEMP_FAULT = 75.0

# The videos show sensor-reported voltage, not a verified 12 V supply reading.
VOLT_REFERENCE = 1.306
VOLTAGE_CALIBRATED = False      # enable only after divider/multimeter calibration
VOLT_NOMINAL = 12.0
VOLT_TOLERANCE = 0.15
VOLT_FAULT_TOLERANCE = 0.25

# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------
TABLE = "readings"
LOCAL_CSV = "readings_log.csv"  # offline backup + your future training set
HISTORY_POINTS = 400            # rows the dashboard pulls for its charts
STALE_AFTER_SEC = 20            # no new reading for this long = device offline

STATUS_NORMAL = "NORMAL"
STATUS_WARNING = "WARNING"
STATUS_FAULT = "FAULT"


def vibration_status(value):
    """Compare with the two observed ranges; do not extrapolate a diagnosis."""
    if VIB_NORMAL_MIN <= value <= VIB_NORMAL_MAX:
        return STATUS_NORMAL
    if VIB_MISALIGN_MIN <= value <= VIB_MISALIGN_MAX:
        return STATUS_FAULT
    return STATUS_WARNING


def classify(vibration, temperature, voltage):
    """Return experimental status, category score, and explanation.

    The legacy database field `health` stores a category score, not health %.
    """
    import math

    if not all(isinstance(v, (int, float)) and math.isfinite(v)
               for v in (vibration, temperature, voltage)):
        return STATUS_WARNING, 60, "Invalid sensor reading; cannot classify setup"

    status = vibration_status(vibration)
    level = {STATUS_NORMAL: 0, STATUS_WARNING: 1, STATUS_FAULT: 2}[status]
    if status == STATUS_NORMAL:
        reasons = ["Matches original-setup vibration reference (provisional)"]
    elif status == STATUS_FAULT:
        reasons = ["Matches 2-3 mm shim misalignment reference (provisional)"]
    else:
        reasons = ["Outside both recorded vibration ranges; unclassified"]

    if temperature >= TEMP_FAULT:
        level = 2
        reasons.append(f"Temperature {temperature:.1f} C above existing fault limit")
    elif temperature >= TEMP_WARN:
        level = max(level, 1)
        reasons.append(f"Temperature {temperature:.1f} C above existing warning limit")

    if VOLTAGE_CALIBRATED and VOLT_NOMINAL > 0:
        deviation = abs(voltage - VOLT_NOMINAL) / VOLT_NOMINAL
        if deviation >= VOLT_FAULT_TOLERANCE:
            level = 2
            reasons.append(f"Supply {voltage:.3f} V outside fault tolerance")
        elif deviation >= VOLT_TOLERANCE:
            level = max(level, 1)
            reasons.append(f"Supply {voltage:.3f} V outside warning tolerance")
    else:
        reasons.append("Voltage calibration unverified; supply faults not evaluated")

    # Explicit category scores only; no unsupported physical health estimate.
    return [STATUS_NORMAL, STATUS_WARNING, STATUS_FAULT][level], [100, 60, 20][level], "; ".join(reasons)
