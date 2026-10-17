"""
Runs on your laptop. Reads the ESP32 over USB, classifies each reading,
uploads it to Supabase, and keeps a local CSV copy as a backup.

    python forwarder.py                 # real hardware on the serial port
    python forwarder.py --simulate      # no hardware needed, fake readings
    python forwarder.py --simulate --fault   # fake a developing fault

Stop it with Ctrl+C.
"""

import argparse
import csv
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

# ----------------------------------------------------------------------
# Credentials
# ----------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit(
        "Missing credentials.\n"
        "Create a file called .env next to this script containing:\n\n"
        "SUPABASE_URL=https://yourproject.supabase.co\n"
        "SUPABASE_KEY=your-anon-public-key\n"
    )

ENDPOINT = f"{SUPABASE_URL}/rest/v1/{config.TABLE}"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}
if not SUPABASE_KEY.startswith("sb_"):  # new-style keys aren't JWTs
    HEADERS["Authorization"] = f"Bearer {SUPABASE_KEY}"


# ----------------------------------------------------------------------
# Reading sources
# ----------------------------------------------------------------------
def open_serial():
    """Open the USB connection to the ESP32."""
    try:
        import serial
    except ImportError:
        sys.exit("pyserial is not installed. Run:  pip install pyserial")

    try:
        port = serial.Serial(config.SERIAL_PORT, config.BAUD_RATE, timeout=2)
    except Exception as exc:
        sys.exit(
            f"Could not open {config.SERIAL_PORT}: {exc}\n"
            "Check the port name in config.py, and close the Arduino IDE's "
            "Serial Monitor if it is open — only one program can hold the port."
        )
    time.sleep(2)  # the ESP32 resets when the port opens
    port.reset_input_buffer()
    print(f"Listening on {config.SERIAL_PORT} at {config.BAUD_RATE} baud")
    return port


def read_serial_line(port):
    """Parse one line of 'vibration,temperature,voltage' from the ESP32."""
    raw = port.readline().decode("utf-8", errors="ignore").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) < 3:
        return None
    try:
        values = float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return None  # startup banner or debug text, ignore it
    # a failed sensor can print nan/inf; JSON can't carry them and one bad row
    # would block every later upload
    return values if all(math.isfinite(v) for v in values) else None


_sim_clock = {"t": 0.0}


def simulate_reading(fault=False):
    """Believable fake readings so you can build and demo before the rig works."""
    _sim_clock["t"] += config.LIVE_INTERVAL_SEC
    t = _sim_clock["t"]
    drift = min(t / 90.0, 1.0) if fault else 0.0

    normal_mid = (config.VIB_NORMAL_MIN + config.VIB_NORMAL_MAX) / 2
    fault_mid = (config.VIB_MISALIGN_MIN + config.VIB_MISALIGN_MAX) / 2
    vibration = normal_mid + drift * (fault_mid - normal_mid)
    vibration += math.sin(t / 4) + random.uniform(-0.2, 0.2)
    temperature = 33.3 - 0.4 * drift
    voltage = config.VOLT_NOMINAL if config.VOLTAGE_CALIBRATED else config.VOLT_REFERENCE

    return round(vibration, 3), round(temperature, 2), round(voltage, 3)


# ----------------------------------------------------------------------
# Outputs
# ----------------------------------------------------------------------
def append_local_csv(row):
    path = Path(config.LOCAL_CSV)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(
                ["ts", "vibration", "temperature", "voltage", "status", "health", "note"]
            )
        writer.writerow(
            [
                row["ts"],
                row["vibration"],
                row["temperature"],
                row["voltage"],
                row["status"],
                row["health"],
                row["note"],
            ]
        )


def upload(batch):
    """Send a batch of readings to Supabase. Returns True on success."""
    try:
        response = requests.post(ENDPOINT, headers=HEADERS, json=batch, timeout=10)
    except requests.RequestException as exc:
        print(f"  upload failed (network): {exc}")
        return False
    if response.status_code >= 300:
        print(f"  upload failed ({response.status_code}): {response.text[:200]}")
        # 400/422 = the data itself is rejected; retrying would block all later batches
        return response.status_code in (400, 422)
    # Report the newest confirmed upload, the same row the dashboard selects.
    # All samples (including those awaiting upload) remain in the local CSV.
    row = max(batch, key=lambda item: item["ts"])
    print(
        f"Uploaded {row['ts']} (UTC)  "
        f"{row['status']:<8} score {row['health']:>3}  "
        f"vib {row['vibration']:7.3f} mm/s  "
        f"temp {row['temperature']:5.1f} C  "
        f"volt {row['voltage']:6.3f} V",
        flush=True,
    )
    return True


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulate", action="store_true", help="run without hardware")
    parser.add_argument("--fault", action="store_true", help="simulate transition from healthy to faulty vibration")
    args = parser.parse_args()

    port = None if args.simulate else open_serial()
    if args.simulate:
        print("Simulation mode — no hardware required."
              + (" Fault injection ON." if args.fault else ""))

    buffer = []
    pending = []          # readings that failed to upload, retried next flush
    last_flush = time.monotonic()

    try:
        while True:
            if args.simulate:
                reading = simulate_reading(fault=args.fault)
                time.sleep(config.LIVE_INTERVAL_SEC)
            else:
                reading = read_serial_line(port)

            if reading:
                vibration, temperature, voltage = reading
                status, health, note = config.classify(vibration, temperature, voltage)
                row = {
                    "device_id": config.DEVICE_ID,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "vibration": vibration,
                    "temperature": temperature,
                    "voltage": voltage,
                    "status": status,
                    "health": health,
                    "note": note,
                }
                buffer.append(row)
                append_local_csv(row)

            if time.monotonic() - last_flush >= config.UPLOAD_INTERVAL_SEC and (buffer or pending):
                batch = pending + buffer
                if upload(batch):
                    pending = []
                else:
                    # keep the most recent 200 so memory can't run away
                    pending = batch[-200:]
                buffer = []
                last_flush = time.monotonic()

    except KeyboardInterrupt:
        print("\nStopping. Flushing anything left over...")
        if buffer or pending:
            upload(pending + buffer)
    finally:
        if port is not None:
            port.close()
        print(f"Local log saved to {config.LOCAL_CSV}")


if __name__ == "__main__":
    main()
