# Rotor Health Monitor — cloud dashboard

Live condition monitoring for rotor imbalance and shaft misalignment.

## How the pieces fit

```
ESP32 + vibration / temperature / voltage sensors
        |  USB serial, "vibration,temperature,voltage" once per 0.5 s
        v
forwarder.py            runs on your laptop
        |  classifies each reading, batches, HTTPS POST every 0.5 s
        v
Supabase (Postgres)     free, permanent, holds every reading
        |  HTTPS GET every 0.5 s (uncached)
        v
cloud_dashboard.py      Streamlit Community Cloud, public URL
```

The laptop is in the loop only as a relay. The dashboard itself lives in the
cloud, so the link works on any phone anywhere — it just shows the motor as
`Offline` when the forwarder is not running.

## Live timing

`config.LIVE_INTERVAL_SEC` sets the upload interval, dashboard refresh, and
simulation step to 0.5 seconds, matching the supplied ESP32 sketch. Restart
the forwarder and dashboard after changing this setting. The ESP32 sampling
interval is configured separately in `esp32_serial_output.ino`.

The terminal prints the newest reading only after each successful upload.
Its UTC timestamp matches the dashboard's "Latest uploaded reading" timestamp
when both show the same sample. All samples still go to the local CSV and
are included in uploads; failed uploads retain the existing 200-row retry
buffer. During an outage the terminal reports upload failures and the
dashboard continues showing its last stored reading.

Polling does not guarantee simultaneous screen updates or display every
sample in the live cards. Network requests, rendering, and browser timer
throttling can add delay; each dashboard refresh selects the newest stored
reading. A visible dashboard now requests data up to twice per second, so
multiple viewers increase Supabase traffic.

## Files

| File | Where it runs | What it does |
|---|---|---|
| `esp32_serial_output.ino` | ESP32 | Prints sensor readings over USB |
| `config.py` | both | Thresholds and the fault-classification rules |
| `forwarder.py` | your laptop | Serial → classify → Supabase → local CSV backup |
| `cloud_dashboard.py` | Streamlit Cloud | The public live dashboard |
| `schema.sql` | Supabase | Creates the `readings` table |
| `requirements.txt` | Streamlit Cloud | Python packages |

## Local test, no hardware needed

```bash
pip install -r requirements.txt
python forwarder.py --simulate          # or --simulate --fault
streamlit run cloud_dashboard.py        # in a second terminal
```

Credentials go in `.env` for the forwarder and `.streamlit/secrets.toml` for
the dashboard:

```
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_KEY=your-anon-public-key
```

Never commit either file to GitHub.

## Experimental reference profile (2026-10-17)

Ranges below were manually read from visible serial-monitor lines in the two
user videos, including lines already on screen at the start. Repeated serial
lines do not imply independent vibration measurements. These are observed
extrema, not statistical confidence intervals or validated safety thresholds.

| Video / setup | Reported vibration (firmware mm/s RMS) | Temperature | Reported voltage |
|---|---|---|---|
| 4.27.44 PM: 2–3 mm sheets below bearing | 66.409–116.635 | 32.90 C | approximately 1.345–1.454 V |
| 4.27.45 PM: original setup | 5.064–17.770 | 33.30 C | approximately 1.306–1.348 V |

The observed normal range remains 5.064–17.770. At the user's request,
the configured NORMAL band is expanded to 5.064–40.000; this extension is
not an observed video range.

`config.classify()` uses inclusive vibration reference bands: NORMAL in the
original band, FAULT in the shim band, WARNING elsewhere (including the gap,
values below the normal band and values above the shim band). A FAULT match
means resemblance to this induced-misalignment reference, not proof of cause.
These videos supersede the earlier photos, whose ranges were very different.
Use this profile only for the same speed, mounting, load and sensor processing.
The firmware's mm/s calibration has not been independently verified. No raw
values are scaled, clamped, replaced or changed to force a classification.

Existing temperature limits remain 60 C warning / 75 C fault and can escalate
the status. The two temperature values alone do not establish new thresholds.
Reported voltage is displayed to three decimals. Supply-voltage fault checks
are disabled (`VOLTAGE_CALIBRATED = False`) until the divider calibration and
actual supply are verified with a multimeter. 1.306 V must not be silently
treated as a new nominal 12 V supply. Enable the flag only after calibration.

The database `health` field remains for compatibility but now represents a
discrete experimental status score: NORMAL=100, WARNING=60, FAULT=20. It is
not measured motor health or a probability. The dashboard labels it accordingly.

The dashboard reclassifies the displayed history under the current profile,
without rewriting Supabase. CSV exports preserve upload-time labels in
`stored_status`, `stored_health`, `stored_note` and identify the current
`classification_profile`. Older recordings may use different conditions and
are not necessarily comparable. Automatic labels are not training ground truth.

Restart the forwarder and dashboard together to apply the settings. The live
cloud dashboard will not change until reviewed files are pushed and deployed.
No firmware change or database migration is needed. Keep the 0.5-second timing.

Simulation produces normal-band values; `--simulate --fault` moves through
the unclassified gap into the shim band over 90 simulated seconds. Wall-clock
time also includes network delays. Simulation writes to the configured table.
