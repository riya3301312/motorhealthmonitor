# Rotor Health Monitor — cloud dashboard

Live condition monitoring for rotor imbalance and shaft misalignment.

## How the pieces fit

```
ESP32 + vibration / temperature / voltage sensors
        |  USB serial, "vibration,temperature,voltage" once per 0.5 s
        v
forwarder.py            runs on your laptop
        |  classifies each reading, batches, HTTPS POST every 2 s
        v
Supabase (Postgres)     free, permanent, holds every reading
        |  HTTPS GET every 3 s
        v
cloud_dashboard.py      Streamlit Community Cloud, public URL
```

The laptop is in the loop only as a relay. The dashboard itself lives in the
cloud, so the link works on any phone anywhere — it just shows the motor as
`Offline` when the forwarder is not running.

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

## Fault logic

Vibration is the primary indicator — imbalance shows up as a rise at 1× shaft
speed, misalignment at 2×. Thresholds follow ISO 10816-1 Class I severity
zones for machines under 15 kW, in mm/s RMS velocity:

| Zone | mm/s RMS | Meaning |
|---|---|---|
| A | up to 1.8 | Newly commissioned |
| B | up to 4.5 | Fine for long-term running |
| C | up to 11.2 | Unsatisfactory, plan a repair |
| D | above 11.2 | Damage occurring |

Temperature and supply voltage act as corroborating evidence, since a
misaligned shaft loads the bearings and heats them.

## Next step: the AI part

Every reading is stored, so once the rig runs you can collect labelled data by
running the motor normally, then with a deliberate imbalance (a small weight on
the coupling) and a deliberate misalignment (shim one motor foot). Export the
history from the dashboard, train a classifier on it, and replace the rule
block in `config.classify()` — nothing else in the system has to change.
