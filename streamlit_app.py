# app.py
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
# 3. DERIVED METRICS
# -----------------------------------------------------------------------------
metrics_df = metrics_df.assign(
    ticket_rate = metrics_df["fd_tickets"] / metrics_df["active_sessions"],
    msat        = metrics_df["happy"] / metrics_df["feedback_given"]
)

# -----------------------------------------------------------------------------
# 4. USER CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.header("Controls")

# Time granularity
gran = st.sidebar.selectbox(
    "Time Granularity",
    ["Daily", "Weekly", "Monthly", "Yearly"]
)

# Date range filter
min_date = metrics_df["date_"].min()
max_date = metrics_df["date_"].max()
start_date, end_date = st.sidebar.date_input(
    "Date Range",
    [min_date, max_date],
    min_value=min_date,
    max_value=max_date
)

# Metric selector
metric_name = st.sidebar.selectbox(
    "Metric to plot",
    ["ticket_rate", "msat"]
)

# -----------------------------------------------------------------------------
# 5. AGGREGATION
# -----------------------------------------------------------------------------
df = metrics_df[
    (metrics_df["date_"] >= pd.to_datetime(start_date)) &
    (metrics_df["date_"] <= pd.to_datetime(end_date))
].copy()

if gran == "Daily":
    df_agg = df.groupby("date_", as_index=False).agg(
        value=(metric_name, "mean")
    ).rename(columns={"date_":"time"})
elif gran == "Weekly":
    df["year_week"] = df["date_"].dt.to_period("W").astype(str)
    df_agg = df.groupby("year_week", as_index=False).agg(
        value=(metric_name, "mean")
    ).rename(columns={"year_week":"time"})
elif gran == "Monthly":
    df["year_month"] = df["date_"].dt.to_period("M").astype(str)
    df_agg = df.groupby("year_month", as_index=False).agg(
        value=(metric_name, "mean")
    ).rename(columns={"year_month":"time"})
else:  # Yearly
    df["year"] = df["date_"].dt.year
    df_agg = df.groupby("year", as_index=False).agg(
        value=(metric_name, "mean")
    ).rename(columns={"year":"time"})

# -----------------------------------------------------------------------------
# 6. CHARTING
# -----------------------------------------------------------------------------
st.title("Metrics vs. Releases")

# Base line chart
line = alt.Chart(df_agg).mark_line(point=True).encode(
    x=alt.X("time:T" if gran=="Daily" else "time:O", title="Time"),
    y=alt.Y("value:Q", title=metric_name.replace("_"," ").title())
)

# Prepare releases for annotation
# Filter releases within the selected date range
rel = releases_df[
    (releases_df["updated"] >= pd.to_datetime(start_date)) &
    (releases_df["updated"] <= pd.to_datetime(end_date))
].copy()

# For weekly/monthly/yearly we need to map release dates into the same 'time' domain
if gran == "Daily":
    rel["time"] = rel["updated"]
else:
    period = {"Weekly":"W","Monthly":"M","Yearly":"Y"}[gran]
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