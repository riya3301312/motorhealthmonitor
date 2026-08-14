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
SERIAL_PORT = "COM3"            # Windows: COM3, COM4 ... | Linux/Mac: /dev/ttyUSB0
BAUD_RATE = 115200
UPLOAD_INTERVAL_SEC = 2.0       # how often the forwarder flushes to Supabase

# ----------------------------------------------------------------------
# Thresholds
#
# Vibration values follow ISO 10816-1 severity zones for small machines
# (Class I, under 15 kW), measured as RMS velocity in mm/s:
#     up to 1.8   Zone A  newly commissioned
#     up to 4.5   Zone B  acceptable for long-term running
#     up to 11.2  Zone C  unsatisfactory, plan a repair
#     above       Zone D  damage is happening now
#
# We warn early (2.8) and fault before Zone D (7.1) so the demo shows a
# clear escalation rather than jumping straight from fine to broken.
# ----------------------------------------------------------------------
VIB_WARN = 2.8                  # mm/s RMS
VIB_FAULT = 7.1

TEMP_WARN = 60.0                # deg C on the bearing housing
TEMP_FAULT = 75.0

VOLT_NOMINAL = 12.0             # set to your motor's rated supply
VOLT_TOLERANCE = 0.15           # 15% swing either side is a warning
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


def _clamp(value, low, high):
    return max(low, min(high, value))


def classify(vibration, temperature, voltage):
    """Turn one raw reading into a status, a 0-100 health score and a reason.

    This is the rule-based stage. Once you have collected a few hours of
    labelled NORMAL and FAULT data in Supabase, you can train a model on
    that history and swap it in here without touching anything else.
    """
    reasons = []
    level = 0  # 0 normal, 1 warning, 2 fault

    # --- vibration: the primary indicator for imbalance and misalignment ---
    if vibration >= VIB_FAULT:
        level = max(level, 2)
        reasons.append(f"Vibration {vibration:.2f} mm/s above fault limit")
    elif vibration >= VIB_WARN:
        level = max(level, 1)
        reasons.append(f"Vibration {vibration:.2f} mm/s rising")

    # --- temperature: bearings heat up as misalignment loads them ---
    if temperature >= TEMP_FAULT:
        level = max(level, 2)
        reasons.append(f"Temperature {temperature:.1f} C above fault limit")
    elif temperature >= TEMP_WARN:
        level = max(level, 1)
        reasons.append(f"Temperature {temperature:.1f} C rising")

    # --- voltage: a sagging or spiking supply stresses the whole system ---
    deviation = abs(voltage - VOLT_NOMINAL) / VOLT_NOMINAL if VOLT_NOMINAL else 0
    if deviation >= VOLT_FAULT_TOLERANCE:
        level = max(level, 2)
        reasons.append(f"Supply {voltage:.2f} V is {deviation * 100:.0f}% off nominal")
    elif deviation >= VOLT_TOLERANCE:
        level = max(level, 1)
        reasons.append(f"Supply {voltage:.2f} V drifting")

    # --- health score: how much margin is left before a fault ---
    vib_penalty = _clamp(
        (vibration - VIB_WARN) / max(VIB_FAULT - VIB_WARN, 0.01) * 55, 0, 60
    )
    temp_penalty = _clamp(
        (temperature - TEMP_WARN) / max(TEMP_FAULT - TEMP_WARN, 0.01) * 30, 0, 35
    )
    volt_penalty = _clamp(deviation / max(VOLT_FAULT_TOLERANCE, 0.01) * 20, 0, 25)
    health = int(round(_clamp(100 - vib_penalty - temp_penalty - volt_penalty, 0, 100)))

    status = [STATUS_NORMAL, STATUS_WARNING, STATUS_FAULT][level]
    note = "; ".join(reasons) if reasons else "All readings within limits"
    return status, health, note
