import streamlit as st
import pandas as pd
import altair as alt

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Metrics & Releases Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# 2. DATA LOADING
# -----------------------------------------------------------------------------
@st.cache_data
def load_data():
    # Assumes data/metrics_data.csv and data/release_data.csv exist
    metrics = pd.read_csv("data/metrics_data.csv", parse_dates=["date_"])
    releases = pd.read_csv("data/release_data.csv", parse_dates=["updated"])
    return metrics, releases

metrics_df, releases_df = load_data()

# -----------------------------------------------------------------------------
# 3. DERIVED METRICS (as percentages)
# -----------------------------------------------------------------------------
metrics_df = metrics_df.assign(
    ticket_rate = metrics_df["fd_tickets"] / metrics_df["active_sessions"] * 100,
    msat        = metrics_df["happy"] / metrics_df["feedback_given"]   * 100
)

# -----------------------------------------------------------------------------
# 4. USER CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.header("Controls")

gran = st.sidebar.selectbox(
    "Time Granularity",
    ["Daily", "Weekly", "Monthly"]
)

min_date = metrics_df["date_"].min().date()
max_date = metrics_df["date_"].max().date()

if gran == "Daily":
    default_start = max_date - pd.Timedelta(days=14)
elif gran == "Weekly":
    default_start = max_date - pd.Timedelta(weeks=5)
else:
    default_start = (max_date - pd.DateOffset(months=4)).date()

start_date, end_date = st.sidebar.date_input(
    "Date Range",
    [default_start, max_date],
    min_value=min_date,
    max_value=max_date
)

metric_options = {
    "Ticket Creation Rate %": "ticket_rate",
    "MSAT":                    "msat"
}
metric_label  = st.sidebar.selectbox(
    "Metric to plot",
    list(metric_options.keys())
)
metric_column = metric_options[metric_label]

# Mapping for raw data column header
data_label_map = {
    "Ticket Creation Rate %": "Ticket creation %",
    "MSAT":                    "MSAT %"
}
data_label = data_label_map[metric_label]

# -----------------------------------------------------------------------------
# 5. AGGREGATION & FORMATTING
# -----------------------------------------------------------------------------

df = metrics_df[
    (metrics_df["date_"] >= pd.to_datetime(start_date)) &
    (metrics_df["date_"] <= pd.to_datetime(end_date))
].copy()

if gran == "Daily":
    df_agg = df.groupby("date_", as_index=False).agg(
        value=(metric_column, "mean")
    ).rename(columns={"date_":"time"})
    df_agg["time"] = df_agg["time"].dt.strftime("%a, %d %b")

elif gran == "Weekly":
    df["week_start"] = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    df["week_end"]   = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
    df_agg = df.groupby(["week_start","week_end"], as_index=False).agg(
        value=(metric_column, "mean")
    )
    df_agg["time"] = (
        df_agg["week_start"].dt.strftime("%b %d") + " - " +
        df_agg["week_end"].dt.strftime("%b %d")
    )

else:  # Monthly
    df["month_start"] = df["date_"].dt.to_period("M").apply(lambda p: p.start_time)
    df_agg = df.groupby("month_start", as_index=False).agg(
        value=(metric_column, "mean")
    )
    df_agg["time"] = df_agg["month_start"].dt.strftime("%b %y")

# Add labels for each point (rounded to 2 decimals)
if not df_agg.empty:
    df_agg["value_label"] = df_agg["value"].round(2).map(lambda v: f"{v:.2f}%")

# -----------------------------------------------------------------------------
# 6. CHARTING
# -----------------------------------------------------------------------------

st.title("Metrics vs. Releases")

# Line
line = alt.Chart(df_agg).mark_line(point=True, color="steelblue").encode(
    x=alt.X("time:O", title="Time", axis=alt.Axis(labelAngle=0, labelAlign="center")),
    y=alt.Y("value:Q", title=metric_label)
)
# Data labels below each point
text = alt.Chart(df_agg).mark_text(dy=10, color="white").encode(
    x="time:O",
    y=alt.Y("value:Q"),
    text=alt.Text("value_label:N")
)

# Prepare release annotations
rel = releases_df.copy()
rel = rel[
    (rel["updated"] >= pd.to_datetime(start_date)) &
    (rel["updated"] <= pd.to_datetime(end_date))
].copy()

if gran == "Daily":
    rel["time"] = rel["updated"].dt.strftime("%a, %d %b")
elif gran == "Weekly":
    rel["week_start"] = rel["updated"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    rel["week_end"]   = rel["updated"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
    rel["time"] = (
        rel["week_start"].dt.strftime("%b %d") + " - " +
        rel["week_end"].dt.strftime("%b %d")
    )
else:  # Monthly
    rel["time"] = rel["updated"].dt.to_period("M").to_timestamp().dt.strftime("%b %y")

# Neon blue release markers
rules = alt.Chart(rel).mark_rule(color="#00FFFF").encode(
    x="time:O"
)
points = alt.Chart(rel).mark_point(color="#00FFFF", size=100).encode(
    x="time:O",
    tooltip=[
        alt.Tooltip("issue_id",    title="Release ID"),
        alt.Tooltip("summary",     title="Release Name"),
        alt.Tooltip("status",      title="Status"),
        alt.Tooltip("issue_type",  title="Type"),
        alt.Tooltip("updated",     title="Date")
    ]
)

# Combine all layers
chart = (line + text + rules + points).properties(
    width=800, height=400
).interactive()

if df_agg.empty:
    st.warning("No metric data available for the selected period.")
else:
    st.altair_chart(chart, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. RAW DATA (Optional)
# -----------------------------------------------------------------------------
with st.expander("Show raw aggregated data"):
    display_df = df_agg.copy()
    display_df = display_df.drop(columns=["value"])
    display_df = display_df.rename(columns={"time":"Time Period", "value_label":data_label})
    st.dataframe(display_df)

with st.expander("Show release data"):
    st.dataframe(rel)
