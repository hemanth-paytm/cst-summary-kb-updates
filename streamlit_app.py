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
    # Paths assume your repo has data/metrics_data.csv and data/release_data.csv
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

# Time granularity (no Yearly)
gran = st.sidebar.selectbox(
    "Time Granularity",
    ["Daily", "Weekly", "Monthly"]
)

# Absolute min/max dates
min_date = metrics_df["date_"].min().date()
max_date = metrics_df["date_"].max().date()

# Default window: last 15 days / 5 weeks / 4 months
if gran == "Daily":
    default_start = max_date - pd.Timedelta(days=14)
elif gran == "Weekly":
    default_start = max_date - pd.Timedelta(weeks=5)
else:  # Monthly
    default_start = (max_date - pd.DateOffset(months=4)).date()

# Date range picker
start_date, end_date = st.sidebar.date_input(
    "Date Range",
    [default_start, max_date],
    min_value=min_date,
    max_value=max_date
)

# Metric selector (friendly names → column keys)
metric_options = {
    "Ticket Creation Rate %": "ticket_rate",
    "MSAT":                    "msat"
}
metric_label  = st.sidebar.selectbox(
    "Metric to plot",
    list(metric_options.keys())
)
metric_column = metric_options[metric_label]

# -----------------------------------------------------------------------------
# 5. AGGREGATION
# -----------------------------------------------------------------------------
df = metrics_df[
    (metrics_df["date_"] >= pd.to_datetime(start_date)) &
    (metrics_df["date_"] <= pd.to_datetime(end_date))
].copy()

if gran == "Daily":
    df_agg = df.groupby("date_", as_index=False).agg(
        value=(metric_column, "mean")
    ).rename(columns={"date_":"time"})
elif gran == "Weekly":
    df["year_week"] = df["date_"].dt.to_period("W").astype(str)
    df_agg = df.groupby("year_week", as_index=False).agg(
        value=(metric_column, "mean")
    ).rename(columns={"year_week":"time"})
else:  # Monthly
    df["year_month"] = df["date_"].dt.to_period("M").astype(str)
    df_agg = df.groupby("year_month", as_index=False).agg(
        value=(metric_column, "mean")
    ).rename(columns={"year_month":"time"})

# -----------------------------------------------------------------------------
# 6. CHARTING
# -----------------------------------------------------------------------------
st.title("Metrics vs. Releases")

# Base line chart
line = alt.Chart(df_agg).mark_line(point=True).encode(
    x=alt.X("time:T" if gran=="Daily" else "time:O", title="Time"),
    y=alt.Y("value:Q", title=metric_label)
)

# Prepare releases for annotation
rel = releases_df[
    (releases_df["updated"] >= pd.to_datetime(start_date)) &
    (releases_df["updated"] <= pd.to_datetime(end_date))
].copy()

if gran == "Daily":
    rel["time"] = rel["updated"]
else:
    period = {"Weekly":"W","Monthly":"M"}[gran]
    rel["time"] = rel["updated"].dt.to_period(period).astype(str)

# Release markers
rules = alt.Chart(rel).mark_rule(color="red").encode(
    x="time:T" if gran=="Daily" else "time:O"
)
points = alt.Chart(rel).mark_point(color="red", size=100).encode(
    x="time:T" if gran=="Daily" else "time:O",
    tooltip=[
        alt.Tooltip("issue_id", title="Release ID"),
        alt.Tooltip("summary", title="Release Name"),
        alt.Tooltip("status", title="Status"),
        alt.Tooltip("issue_type", title="Type"),
        alt.Tooltip("updated", title="Date")
    ]
)

# Combine
chart = (line + rules + points).properties(
    width=800, height=400
).interactive()

st.altair_chart(chart, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. RAW DATA (Optional)
# -----------------------------------------------------------------------------
with st.expander("Show raw aggregated data"):
    st.dataframe(df_agg)

with st.expander("Show release data"):
    st.dataframe(rel)
