import io
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="EVScope Streamlit", page_icon="⚡", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Oxanium:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    .stApp { background: linear-gradient(135deg, #0b1220 0%, #081524 45%, #0c1e2e 100%); color: #dbe9ff; }
    h1,h2,h3,h4 { font-family: 'Oxanium', sans-serif; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .kpi-box { border: 1px solid rgba(0,194,255,0.25); background: rgba(0,194,255,0.08); border-radius: 14px; padding: 12px 14px; min-height: 100px; }
    .kpi-title { color: #7fb3dd; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; }
    .kpi-value { color: #ebf7ff; font-size: 1.7rem; font-weight: 700; margin-top: 3px; }
    .kpi-sig { color: #7da0be; font-size: 0.74rem; margin-top: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


@dataclass
class SignalDef:
    name: str
    start: int
    length: int
    is_intel: bool
    is_signed: bool
    scale: float
    offset: float


KPI_PATS = {
    "SOC": ["soc", "stateofcharge", "batterysoc", "batt_soc", "soc_pct", "bms_soc"],
    "Pack Voltage": ["packvolt", "battvolt", "batteryvoltage", "hvvolt", "voltage", "pack_volt", "batt_volt", "dcbusvoltage"],
    "Temperature": ["temp", "temperature", "celltemp", "packtemp", "maxtemp", "thermal", "bms_temp"],
    "Charge Power": ["chargepower", "chargepwr", "chgpwr", "chargingpower", "acpower", "dcpower", "kw"],
}
COLORS = ["#00c2ff", "#22d3a5", "#ffb700", "#ff4d6d", "#a78bfa", "#fb923c", "#34d399", "#f472b6"]


def parse_dbc(text: str) -> Dict[int, List[SignalDef]]:
    import re

    db: Dict[int, List[SignalDef]] = {}
    current_id = None
    for line in text.splitlines():
        t = line.strip()
        if t.startswith("BO_ "):
            m = re.match(r"^BO_\s+(\d+)\s+(\w+):", t)
            if m:
                current_id = int(m.group(1)) & 0x1FFFFFFF
                db[current_id] = []
        elif t.startswith("SG_ ") and current_id is not None:
            m = re.match(r"^SG_\s+(\w+)\s+.*:\s+(\d+)\|(\d+)@([01])([+-])\s*\(([^,]+),([^)]+)\)", t)
            if m:
                db[current_id].append(
                    SignalDef(
                        name=m.group(1),
                        start=int(m.group(2)),
                        length=int(m.group(3)),
                        is_intel=(m.group(4) == "1"),
                        is_signed=(m.group(5) == "-"),
                        scale=float(m.group(6)),
                        offset=float(m.group(7)),
                    )
                )
    return db


def parse_dbf(text: str) -> Dict[int, List[SignalDef]]:
    db: Dict[int, List[SignalDef]] = {}
    current_id = None
    for line in text.splitlines():
        t = line.strip()
        low = t.lower()
        if low.startswith("message="):
            parts = t.split(",")
            if len(parts) > 1:
                current_id = int(parts[1].replace("0x", ""), 16) & 0x1FFFFFFF
                db[current_id] = []
        elif low.startswith("signal=") and current_id is not None:
            parts = t.split(",")
            if len(parts) >= 7:
                db[current_id].append(
                    SignalDef(
                        name=parts[0].split("=")[1],
                        start=int(parts[1]),
                        length=int(parts[2]),
                        is_intel=True,
                        is_signed=False,
                        scale=float(parts[5]) if parts[5] else 1.0,
                        offset=float(parts[6]) if parts[6] else 0.0,
                    )
                )
    return db


def is_hex(value: str) -> bool:
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def parse_log_lines(content: str) -> List[dict]:
    frames = []
    for line in content.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        dir_idx = next((i for i, p in enumerate(parts) if p.lower() in {"rx", "tx"}), -1)
        if dir_idx == -1:
            continue
        try:
            if ":" in parts[0]:
                p = parts[0].split(":")
                if len(p) < 4:
                    continue
                ts = int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2]) + (int(p[3]) / 10000)
                can_id = int(parts[dir_idx + 2].replace("0x", ""), 16)
                data = [int(x, 16) for x in parts[dir_idx + 5 :] if is_hex(x)]
            else:
                ts = float(parts[0])
                can_id = int(parts[2].replace("x", ""), 16)
                dlc_idx = next((i for i, p in enumerate(parts) if i > dir_idx and p.isdigit() and len(p) == 1), -1)
                if dlc_idx == -1:
                    continue
                data = [int(x, 16) for x in parts[dlc_idx + 1 :] if is_hex(x)]
            if not math.isnan(ts):
                frames.append({"ts": ts, "id": can_id & 0x1FFFFFFF, "data": data})
        except Exception:
            continue
    return frames


def extract_signal(frame_data: List[int], sig: SignalDef) -> float:
    val = 0
    if sig.is_intel:
        for i in range(sig.length):
            bit = sig.start + i
            byte_i = bit // 8
            bit_i = bit % 8
            if byte_i < len(frame_data) and ((frame_data[byte_i] >> bit_i) & 1):
                val |= 1 << i
    else:
        for i in range(sig.length):
            bit = (sig.start // 8) * 8 + (7 - (sig.start % 8)) + i
            pos = (bit // 8) * 8 + (7 - (bit % 8))
            byte_i = pos // 8
            bit_i = pos % 8
            if byte_i < len(frame_data) and ((frame_data[byte_i] >> bit_i) & 1):
                val |= 1 << (sig.length - 1 - i)
    if sig.is_signed and (val & (1 << (sig.length - 1))):
        val -= 1 << sig.length
    return val * sig.scale + sig.offset


def decode_frames(frames: List[dict], database: Dict[int, List[SignalDef]]) -> pd.DataFrame:
    decoded = []
    for frame in sorted(frames, key=lambda x: x["ts"]):
        sig_defs = database.get(frame["id"])
        if not sig_defs:
            continue
        sigs = {}
        for sig in sig_defs:
            sigs[sig.name] = extract_signal(frame["data"], sig)
        decoded.append({"ts": frame["ts"], "sigs": sigs})
    if not decoded:
        return pd.DataFrame()
    state = {}
    rows = []
    for row in decoded:
        state.update(row["sigs"])
        rows.append({"timestamp": row["ts"], **state})
    return pd.DataFrame(rows)


def signal_stats(df: pd.DataFrame, sig: str) -> Optional[dict]:
    if sig not in df.columns:
        return None
    vals = pd.to_numeric(df[sig], errors="coerce").dropna()
    if vals.empty:
        return None
    return {
        "last": float(vals.iloc[-1]),
        "min": float(vals.min()),
        "max": float(vals.max()),
        "avg": float(vals.mean()),
        "std": float(vals.std(ddof=0)),
        "count": int(vals.count()),
    }


def match_kpi_signal(signals: List[str], patterns: List[str]) -> Optional[str]:
    low = [p.lower() for p in patterns]
    for sig in signals:
        s = sig.lower()
        if any(p in s for p in low):
            return sig
    return None


def detect_faults(df: pd.DataFrame, signals: List[str]) -> pd.DataFrame:
    fault_rows = []
    for sig in signals:
        vals = pd.to_numeric(df[sig], errors="coerce")
        valid = df.loc[vals.notna(), ["timestamp"]].copy()
        if valid.empty:
            continue
        valid["value"] = vals[vals.notna()].values
        avg = valid["value"].mean()
        std = valid["value"].std(ddof=0)
        if std and std > 0:
            zscores = ((valid["value"] - avg) / std).abs()
            outliers = valid.loc[zscores > 4]
            for _, r in outliers.iterrows():
                z = abs((r["value"] - avg) / std)
                fault_rows.append(
                    {
                        "severity": "crit" if z > 6 else "warn",
                        "signal": sig,
                        "condition": f"Outlier (Z={z:.1f})",
                        "value": float(r["value"]),
                        "timestamp": float(r["timestamp"]),
                    }
                )
        sig_low = sig.lower()
        if any(k in sig_low for k in ["fault", "error", "dtc", "warning", "alarm", "fail"]):
            for _, r in valid.loc[valid["value"] != 0].iterrows():
                fault_rows.append({"severity": "crit", "signal": sig, "condition": "Non-zero fault signal", "value": float(r["value"]), "timestamp": float(r["timestamp"])})
        if "volt" in sig_low:
            for _, r in valid.loc[(valid["value"] > 1000) | (valid["value"] < 0)].iterrows():
                fault_rows.append({"severity": "crit", "signal": sig, "condition": "Voltage out of range (0-1000V)", "value": float(r["value"]), "timestamp": float(r["timestamp"])})
        if "temp" in sig_low:
            for _, r in valid.loc[(valid["value"] > 80) | (valid["value"] < -40)].iterrows():
                fault_rows.append({"severity": "crit" if r["value"] > 80 else "warn", "signal": sig, "condition": "Temperature out of safe range (-40 to 80C)", "value": float(r["value"]), "timestamp": float(r["timestamp"])})
        if "soc" in sig_low:
            for _, r in valid.loc[(valid["value"] > 100) | (valid["value"] < 0)].iterrows():
                fault_rows.append({"severity": "crit", "signal": sig, "condition": "SOC out of range (0-100%)", "value": float(r["value"]), "timestamp": float(r["timestamp"])})
    out = pd.DataFrame(fault_rows)
    if out.empty:
        return out
    return out.sort_values(by="timestamp", ascending=True).reset_index(drop=True)


def dashboard_plot(df: pd.DataFrame, signals: List[str], use_fill: bool, use_markers: bool) -> go.Figure:
    fig = go.Figure()
    for i, sig in enumerate(signals):
        if sig not in df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df[sig],
                mode="lines+markers" if use_markers else "lines",
                name=sig,
                line={"width": 2, "color": COLORS[i % len(COLORS)]},
                marker={"size": 4, "color": COLORS[i % len(COLORS)]},
                fill="tozeroy" if use_fill and i == 0 else None,
                fillcolor="rgba(0,194,255,0.08)" if use_fill and i == 0 else None,
            )
        )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"t": 24, "b": 40, "l": 48, "r": 16},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.12},
        font={"family": "JetBrains Mono", "size": 11},
    )
    fig.update_xaxes(title="Time")
    fig.update_yaxes(title="Value")
    return fig


def single_plot(df: pd.DataFrame, sig: str, color: str) -> go.Figure:
    fig = go.Figure()
    if sig and sig in df.columns:
        fig.add_trace(go.Scatter(x=df["timestamp"], y=df[sig], mode="lines", name=sig, line={"width": 2, "color": color}))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"t": 12, "b": 36, "l": 40, "r": 8},
        hovermode="x unified",
        showlegend=False,
        height=260,
        font={"family": "JetBrains Mono", "size": 10},
    )
    fig.update_xaxes(title="Time")
    fig.update_yaxes(title=sig if sig else "Value")
    return fig


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def init_state() -> None:
    defaults = {"dataframe": pd.DataFrame(), "signals": [], "faults": pd.DataFrame(), "last_status": "Idle"}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()

st.title("EVScope - EV Analytics Platform")
st.caption("Upload DBC/DBF and ASC/LOG files, decode CAN signals, visualize KPIs, detect faults, and export reports.")

with st.sidebar:
    st.header("Data Input")
    dbc_files = st.file_uploader("DBC/DBF files", type=["dbc", "dbf"], accept_multiple_files=True)
    log_files = st.file_uploader("ASC/LOG files", type=["asc", "log"], accept_multiple_files=True)
    run_clicked = st.button("Parse and Analyze", type="primary", use_container_width=True)
    st.divider()
    st.caption(f"Status: {st.session_state['last_status']}")

if run_clicked:
    if not dbc_files or not log_files:
        st.session_state["last_status"] = "Please upload at least one DBC/DBF and one ASC/LOG file."
        st.warning(st.session_state["last_status"])
    else:
        with st.spinner("Parsing files and decoding signals..."):
            database: Dict[int, List[SignalDef]] = {}
            all_frames: List[dict] = []
            for f in dbc_files:
                txt = f.read().decode("utf-8", errors="ignore")
                parsed = parse_dbf(txt) if f.name.lower().endswith(".dbf") else parse_dbc(txt)
                for k, v in parsed.items():
                    database[k] = v
            for f in log_files:
                txt = f.read().decode("utf-8", errors="ignore")
                all_frames.extend(parse_log_lines(txt))
            df = decode_frames(all_frames, database)
            if df.empty:
                st.session_state["dataframe"] = pd.DataFrame()
                st.session_state["signals"] = []
                st.session_state["faults"] = pd.DataFrame()
                st.session_state["last_status"] = "No decodable signals found. Check file formats and CAN IDs."
                st.error(st.session_state["last_status"])
            else:
                signals = sorted([c for c in df.columns if c != "timestamp"])
                st.session_state["dataframe"] = df
                st.session_state["signals"] = signals
                st.session_state["faults"] = detect_faults(df, signals)
                st.session_state["last_status"] = f"Ready: {len(signals)} signals from {len(log_files)} log file(s)."
                st.success(st.session_state["last_status"])

df = st.session_state["dataframe"]
signals = st.session_state["signals"]
faults_df = st.session_state["faults"]
if df.empty:
    st.info("Load and parse files to start analysis.")
    st.stop()

st.subheader("Key EV KPIs")
kpi_cols = st.columns(4)
for col, (kpi_name, patterns) in zip(kpi_cols, KPI_PATS.items()):
    sig = match_kpi_signal(signals, patterns)
    stats = signal_stats(df, sig) if sig else None
    with col:
        val = f"{stats['last']:.2f}" if stats else "--"
        sig_name = sig if sig else "No signal matched"
        st.markdown(f"<div class='kpi-box'><div class='kpi-title'>{kpi_name}</div><div class='kpi-value mono'>{val}</div><div class='kpi-sig mono'>{sig_name}</div></div>", unsafe_allow_html=True)

tab_dash, tab_sig, tab_multi, tab_faults, tab_export = st.tabs(["Dashboard", "Signal Viewer", "Multi-Plot", "Fault Decoder", "Export"])

with tab_dash:
    st.markdown("### Dashboard Plot")
    c1, c2, c3 = st.columns(3)
    with c1:
        s1 = st.selectbox("Signal 1", options=[""] + signals, index=min(1, len(signals)), key="dash_s1")
    with c2:
        s2 = st.selectbox("Signal 2", options=[""] + signals, index=min(2, len(signals)), key="dash_s2")
    with c3:
        s3 = st.selectbox("Signal 3", options=[""] + signals, index=min(3, len(signals)), key="dash_s3")
    use_fill = st.checkbox("Fill first signal", value=False)
    use_markers = st.checkbox("Show markers", value=False)
    selected = [s for s in [s1, s2, s3] if s]
    if selected:
        st.plotly_chart(dashboard_plot(df, selected, use_fill, use_markers), use_container_width=True)
    else:
        st.info("Select at least one signal.")

with tab_sig:
    st.markdown("### Signal Table")
    search = st.text_input("Search signals", placeholder="Filter by name...")
    picked = st.multiselect("Signals to compare", options=signals, default=signals[:3] if signals else [])
    filtered = [s for s in signals if search.lower() in s.lower()] if search else signals
    rows = []
    for sig in filtered:
        stats = signal_stats(df, sig)
        if stats:
            rows.append({"signal": sig, "last": round(stats["last"], 4), "min": round(stats["min"], 4), "max": round(stats["max"], 4), "avg": round(stats["avg"], 4), "std": round(stats["std"], 4), "count": stats["count"]})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)
    if picked:
        st.plotly_chart(dashboard_plot(df, picked[:8], False, False), use_container_width=True)

with tab_multi:
    st.markdown("### Multi-Plot")
    cols = st.columns(2)
    panel_signals: List[str] = []
    for i in range(4):
        with cols[i % 2]:
            sig = st.selectbox(f"Panel {i+1}", options=[""] + signals, index=(i + 1 if i < len(signals) else 0), key=f"mp_{i}")
            panel_signals.append(sig)
            if sig:
                st.plotly_chart(single_plot(df, sig, COLORS[i % len(COLORS)]), use_container_width=True)
            else:
                st.info("No signal selected.")

with tab_faults:
    st.markdown("### Fault Decoder")
    if faults_df.empty:
        st.success("No anomalies detected.")
    else:
        st.metric("Detected Faults", len(faults_df))
        st.dataframe(faults_df.head(500), use_container_width=True, height=420)

with tab_export:
    st.markdown("### Export")
    filter_txt = st.text_input("Signal filter for CSV", placeholder="e.g. BattVolt, Temp")
    include_ts = st.checkbox("Include timestamp column", value=True)
    include_stats = st.checkbox("Append summary statistics", value=False)
    export_signals = [s for s in signals if filter_txt.lower() in s.lower()] if filter_txt else signals
    export_df = df[["timestamp"] + export_signals] if include_ts else df[export_signals]
    if include_stats and not export_df.empty:
        stats_rows = []
        for sig in export_signals:
            stats = signal_stats(df, sig)
            if stats:
                stats_rows.append({"signal": sig, "min": stats["min"], "max": stats["max"], "avg": stats["avg"], "std": stats["std"], "count": stats["count"]})
        out = io.StringIO()
        export_df.to_csv(out, index=False)
        out.write("\n# Summary Statistics\n")
        pd.DataFrame(stats_rows).to_csv(out, index=False)
        data = out.getvalue().encode("utf-8")
    else:
        data = csv_bytes(export_df)
    st.download_button("Download EV data CSV", data=data, file_name="evscope_data.csv", mime="text/csv")
    if not faults_df.empty:
        st.download_button("Download faults CSV", data=csv_bytes(faults_df), file_name="evscope_faults.csv", mime="text/csv")
    fig_options = {"Dashboard": dashboard_plot(df, signals[:3], False, False), "Panel 1": single_plot(df, panel_signals[0] if panel_signals and panel_signals[0] else signals[0], COLORS[0])}
    chosen = st.selectbox("Plot for PNG export", options=list(fig_options.keys()))
    wh = st.selectbox("PNG resolution", options=[(1280, 720), (1920, 1080), (2560, 1440)], index=0)
    try:
        png = fig_options[chosen].to_image(format="png", width=wh[0], height=wh[1], scale=1)
        st.download_button("Download plot PNG", data=png, file_name="evscope_plot.png", mime="image/png")
    except Exception:
        st.warning("PNG export needs plotly+kaleido in your environment. Install requirements and rerun.")
