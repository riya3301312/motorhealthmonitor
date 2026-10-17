"""
The public dashboard. Deployed to Streamlit Community Cloud, it reads from
Supabase and shows the motor's live condition to anyone with the link.

Locally:  streamlit run cloud_dashboard.py
"""

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import config

IST = "Asia/Kolkata"

st.set_page_config(
    page_title="Motor Health — Live",
    page_icon="⚙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ----------------------------------------------------------------------
# Look and feel: an instrument panel, not a web app.
# Condensed signage type for labels, monospace for anything numeric.
# ----------------------------------------------------------------------
PALETTE = {
    "bg": "#0D1117",
    "panel": "#161B22",
    "line": "#252C36",
    "text": "#E6EDF3",
    "muted": "#7D8590",
    "normal": "#3FB950",
    "warning": "#D29922",
    "fault": "#F85149",
    "trace": "#58A6FF",
}

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500&display=swap');

.stApp {{ background: {PALETTE['bg']}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.2rem; max-width: 1280px; }}

.rig-title {{
  font-family: 'Barlow Condensed', sans-serif;
  font-size: 2.6rem; font-weight: 700; letter-spacing: .04em;
  text-transform: uppercase; color: {PALETTE['text']};
  line-height: 1; margin: 0;
}}
.rig-sub {{
  font-family: 'Inter', sans-serif; font-size: .82rem;
  color: {PALETTE['muted']}; margin-top: .45rem;
}}

.banner {{
  border: 1px solid {PALETTE['line']}; border-left-width: 5px;
  background: {PALETTE['panel']}; border-radius: 4px;
  padding: 1rem 1.25rem; margin: 1.4rem 0 1.1rem 0;
  display: flex; align-items: baseline; gap: 1.1rem; flex-wrap: wrap;
}}
.banner-word {{
  font-family: 'Barlow Condensed', sans-serif; font-size: 2rem;
  font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  line-height: 1;
}}
.banner-note {{
  font-family: 'Inter', sans-serif; font-size: .85rem;
  color: {PALETTE['muted']};
}}

.card {{
  border: 1px solid {PALETTE['line']}; background: {PALETTE['panel']};
  border-radius: 4px; padding: .95rem 1.1rem 1.05rem 1.1rem; height: 100%;
}}
.card-label {{
  font-family: 'Barlow Condensed', sans-serif; font-size: .95rem;
  font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
  color: {PALETTE['muted']};
}}
.card-value {{
  font-family: 'JetBrains Mono', monospace; font-size: 2.1rem;
  font-weight: 600; color: {PALETTE['text']}; margin: .3rem 0 .55rem 0;
  line-height: 1;
}}
.card-unit {{
  font-size: .8rem; color: {PALETTE['muted']}; margin-left: .4rem;
  font-weight: 400;
}}
.card-track {{
  height: 4px; background: {PALETTE['line']}; border-radius: 2px;
  overflow: hidden;
}}
.card-track span {{ display: block; height: 100%; }}
.card-foot {{
  font-family: 'JetBrains Mono', monospace; font-size: .68rem;
  color: {PALETTE['muted']}; margin-top: .5rem; letter-spacing: .02em;
}}

/* Signature element: the health meter, read like a panel gauge. */
.meter-wrap {{
  border: 1px solid {PALETTE['line']}; background: {PALETTE['panel']};
  border-radius: 4px; padding: 1.1rem 1.3rem 1.25rem 1.3rem; margin-top: .9rem;
}}
.meter-head {{
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: .8rem;
}}
.meter-head .lbl {{
  font-family: 'Barlow Condensed', sans-serif; letter-spacing: .14em;
  text-transform: uppercase; font-weight: 600; color: {PALETTE['muted']};
  font-size: .95rem;
}}
.meter-head .val {{
  font-family: 'JetBrains Mono', monospace; font-weight: 600;
  font-size: 1.6rem; color: {PALETTE['text']};
}}
.meter-track {{
  position: relative; height: 14px; border-radius: 2px;
  background: linear-gradient(90deg,
    {PALETTE['fault']} 0%, {PALETTE['fault']} 30%,
    {PALETTE['warning']} 30%, {PALETTE['warning']} 65%,
    {PALETTE['normal']} 65%, {PALETTE['normal']} 100%);
  opacity: .35;
}}
.meter-needle {{
  position: absolute; top: -6px; width: 3px; height: 26px;
  background: {PALETTE['text']}; transform: translateX(-1.5px);
  box-shadow: 0 0 6px rgba(230,237,243,.5);
}}
.meter-ticks {{
  display: flex; justify-content: space-between; margin-top: .5rem;
  font-family: 'JetBrains Mono', monospace; font-size: .66rem;
  color: {PALETTE['muted']};
}}

.sec-head {{
  font-family: 'Barlow Condensed', sans-serif; font-size: 1.25rem;
  font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
  color: {PALETTE['muted']}; margin: 2rem 0 .3rem 0;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].rstrip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "This dashboard needs its Supabase credentials. Add SUPABASE_URL and "
        "SUPABASE_KEY under Settings → Secrets on Streamlit Cloud, or in a local "
        "file at .streamlit/secrets.toml"
    )
    st.stop()


# Fetch fresh data on every refresh so the latest upload is immediately eligible.
def fetch_readings():
    url = f"{SUPABASE_URL}/rest/v1/{config.TABLE}"
    params = {
        "select": "ts,vibration,temperature,voltage,status,health,note",
        "device_id": f"eq.{config.DEVICE_ID}",
        "order": "ts.desc",
        "limit": config.HISTORY_POINTS,
    }
    headers = {"apikey": SUPABASE_KEY}
    if not SUPABASE_KEY.startswith("sb_"):
        headers["Authorization"] = f"Bearer {SUPABASE_KEY}"
    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    frame = pd.DataFrame(response.json())
    if frame.empty:
        return frame
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, format="mixed")
    return frame.sort_values("ts").reset_index(drop=True)


st_autorefresh(interval=config.DASHBOARD_REFRESH_MS, key="tick")

# ----------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------
st.markdown(
    f"""
<div>
  <p class="rig-title">Rotor Health Monitor</p>
  <p class="rig-sub">Imbalance and shaft misalignment detection &nbsp;·&nbsp;
     Unit {config.DEVICE_ID} &nbsp;·&nbsp; refreshing every {config.LIVE_INTERVAL_SEC:g} s</p>
</div>
""",
    unsafe_allow_html=True,
)

try:
    data = fetch_readings()
except requests.RequestException as exc:
    st.error(f"Cannot reach Supabase right now: {exc}")
    st.stop()

if data.empty:
    st.markdown(
        f"""
<div class="banner" style="border-left-color:{PALETTE['muted']}">
  <span class="banner-word" style="color:{PALETTE['muted']}">No data yet</span>
  <span class="banner-note">Start forwarder.py on the laptop connected to the
  ESP32. Readings will appear here within a few seconds.</span>
</div>
""",
        unsafe_allow_html=True,
    )
    st.stop()

# Re-evaluate the displayed window without rewriting stored history.
for column in ("status", "health", "note"):
    data[f"stored_{column}"] = data[column]
classified = [config.classify(row.vibration, row.temperature, row.voltage)
              for row in data.itertuples()]
data[["status", "health", "note"]] = pd.DataFrame(classified, index=data.index)
data["classification_profile"] = config.CLASSIFICATION_PROFILE
st.info(
    f"Vibration bands: NORMAL = {config.VIB_NORMAL_MIN:.3f}–{config.VIB_NORMAL_MAX:.3f}; "
    f"FAULT = {config.VIB_MISALIGN_MIN:.3f}–{config.VIB_MISALIGN_MAX:.3f} or a temperature fault; "
    "WARNING = out of range or temperature warning. Not validated safety limits. "
    "Vibration units follow firmware output; physical calibration is unverified."
)
latest = data.iloc[-1]
st.caption(f"Latest uploaded reading (UTC): {latest['ts'].isoformat()}")
age = (datetime.now(timezone.utc) - latest["ts"].to_pydatetime()).total_seconds()
offline = age > config.STALE_AFTER_SEC

# ----------------------------------------------------------------------
# Status banner
# ----------------------------------------------------------------------
if offline:
    colour, word = PALETTE["muted"], "Offline"
    note = (
        f"Last reading was {int(age)} s ago. The forwarder on the laptop has "
        "stopped, or the ESP32 is unplugged."
    )
else:
    colour = {
        config.STATUS_NORMAL: PALETTE["normal"],
        config.STATUS_WARNING: PALETTE["warning"],
        config.STATUS_FAULT: PALETTE["fault"],
    }[latest["status"]]
    word = latest["status"]
    note = latest["note"]

st.markdown(
    f"""
<div class="banner" style="border-left-color:{colour}">
  <span class="banner-word" style="color:{colour}">{word}</span>
  <span class="banner-note">{note}</span>
</div>
""",
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------
# Readout cards
# ----------------------------------------------------------------------
def card(label, value, unit, fraction, colour, footer):
    pct = max(0, min(100, fraction * 100))
    return f"""
<div class="card">
  <div class="card-label">{label}</div>
  <div class="card-value">{value}<span class="card-unit">{unit}</span></div>
  <div class="card-track"><span style="width:{pct:.0f}%;background:{colour}"></span></div>
  <div class="card-foot">{footer}</div>
</div>
"""


def band_colour(value, warn, fault):
    if value >= fault:
        return PALETTE["fault"]
    if value >= warn:
        return PALETTE["warning"]
    return PALETTE["normal"]


vib, temp, volt = latest["vibration"], latest["temperature"], latest["voltage"]
volt_dev = abs(volt - config.VOLT_NOMINAL) / config.VOLT_NOMINAL if config.VOLT_NOMINAL > 0 else 0

col_a, col_b, col_c = st.columns(3, gap="medium")
with col_a:
    st.markdown(
        card(
            "Vibration",
            f"{vib:.3f}",
            "mm/s RMS",
            vib / config.VIB_MISALIGN_MAX,
            PALETTE[config.vibration_status(vib).lower()],
            f"healthy {config.VIB_NORMAL_MIN:.3f}–{config.VIB_NORMAL_MAX:.3f} · faulty {config.VIB_MISALIGN_MIN:.3f}–{config.VIB_MISALIGN_MAX:.3f}",
        ),
        unsafe_allow_html=True,
    )
with col_b:
    st.markdown(
        card(
            "Temperature",
            f"{temp:.1f}",
            "°C",
            temp / (config.TEMP_FAULT * 1.3),
            band_colour(temp, config.TEMP_WARN, config.TEMP_FAULT),
            f"warn {config.TEMP_WARN}  ·  fault {config.TEMP_FAULT}",
        ),
        unsafe_allow_html=True,
    )
with col_c:
    st.markdown(
        card(
            "Supply voltage" if config.VOLTAGE_CALIBRATED else "Reported voltage",
            f"{volt:.3f}",
            "V",
            volt_dev / config.VOLT_FAULT_TOLERANCE if config.VOLTAGE_CALIBRATED else 0,
            band_colour(volt_dev, config.VOLT_TOLERANCE, config.VOLT_FAULT_TOLERANCE) if config.VOLTAGE_CALIBRATED else PALETTE["muted"],
            (f"nominal {config.VOLT_NOMINAL} V · drift {volt_dev * 100:.0f}%" if config.VOLTAGE_CALIBRATED else "Calibration unverified · supply faults not evaluated"),
        ),
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------
# Health meter
# ----------------------------------------------------------------------
health = int(latest["health"])
health_colour = (
    PALETTE["normal"] if health >= 65 else
    PALETTE["warning"] if health >= 30 else PALETTE["fault"]
)
st.markdown(
    f"""
<div class="meter-wrap">
  <div class="meter-head">
    <span class="lbl">Experimental status score</span>
    <span class="val" style="color:{health_colour}">{health}<span
      style="font-size:.9rem;color:{PALETTE['muted']}"> / 100</span></span>
  </div>
  <div class="meter-track">
    <div class="meter-needle" style="left:{health}%"></div>
  </div>
  <div class="meter-ticks">
    <span>20 · fault</span><span>60 · warning / unclassified</span><span>100 · normal reference</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# Trends
# ----------------------------------------------------------------------
st.markdown('<p class="sec-head">Trend</p>', unsafe_allow_html=True)

plot_data = data.copy()
plot_data["local"] = plot_data["ts"].dt.tz_convert(IST)


def trend(series_name, title, unit, warn=None, fault=None):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=plot_data["local"],
            y=plot_data[series_name],
            mode="lines",
            line=dict(color=PALETTE["trace"], width=2),
            fill="tozeroy",
            fillcolor="rgba(88,166,255,0.08)",
            hovertemplate="%{y:.2f} " + unit + "<extra></extra>",
        )
    )
    for level, colour, label in (
        (warn, PALETTE["warning"], "warn"),
        (fault, PALETTE["fault"], "fault"),
    ):
        if level is not None:
            fig.add_hline(
                y=level,
                line=dict(color=colour, width=1, dash="dot"),
                annotation_text=label,
                annotation_position="right",
                annotation_font=dict(size=10, color=colour),
            )
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color=PALETTE["muted"])),
        height=250,
        margin=dict(l=8, r=8, t=38, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=PALETTE["muted"], size=11),
        xaxis=dict(showgrid=False, title=None),
        yaxis=dict(gridcolor=PALETTE["line"], title=None, zeroline=False),
        showlegend=False,
    )
    if series_name == "vibration":
        for low, high, colour, label in (
            (config.VIB_NORMAL_MIN, config.VIB_NORMAL_MAX, PALETTE["normal"], "healthy"),
            (config.VIB_MISALIGN_MIN, config.VIB_MISALIGN_MAX, PALETTE["fault"], "faulty"),
        ):
            fig.add_hrect(y0=low, y1=high, fillcolor=colour, opacity=0.12,
                          line_width=0, annotation_text=label)
    return fig


t1, t2 = st.columns(2, gap="medium")
with t1:
    st.plotly_chart(
        trend("vibration", "Reported vibration · mm/s RMS", "mm/s"),
        use_container_width=True,
    )
with t2:
    st.plotly_chart(
        trend("temperature", "Temperature  ·  °C", "°C",
              config.TEMP_WARN, config.TEMP_FAULT),
        use_container_width=True,
    )

st.plotly_chart(
    trend("health", "Experimental status score  ·  score", "pts"),
    use_container_width=True,
)

# ----------------------------------------------------------------------
# Alerts and export
# ----------------------------------------------------------------------
st.markdown('<p class="sec-head">Recent alerts</p>', unsafe_allow_html=True)

alerts = data[data["status"] != config.STATUS_NORMAL].tail(12).iloc[::-1]
if alerts.empty:
    st.caption("Nothing raised in the last "
               f"{len(data)} readings. The motor has been running clean.")
else:
    table = pd.DataFrame(
        {
            "Time": alerts["ts"].dt.tz_convert(IST).dt.strftime("%d %b, %H:%M:%S"),
            "Status": alerts["status"],
            "Reason": alerts["note"],
        }
    )
    st.dataframe(table, use_container_width=True, hide_index=True)

st.markdown('<p class="sec-head">Training data</p>', unsafe_allow_html=True)
st.caption(
    "Export the displayed history window. Labels use the current experimental "
    "profile; stored_status, stored_health and stored_note retain upload-time labels. "
    "Automatic classifications are not verified training ground truth."
)
st.download_button(
    "Download history as CSV",
    data.to_csv(index=False).encode("utf-8"),
    file_name=f"{config.DEVICE_ID}_history.csv",
    mime="text/csv",
)
