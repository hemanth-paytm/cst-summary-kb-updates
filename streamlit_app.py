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
    ).rename(columns={"date_":"period_start"})
    df_agg["time"] = df_agg["period_start"].dt.strftime("%a, %d %b")

elif gran == "Weekly":
    df["period_start"] = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    df["period_end"]   = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
    df_agg = df.groupby(["period_start","period_end"], as_index=False).agg(
        value=(metric_column, "mean")
    )
    df_agg["time"] = (
        df_agg["period_start"].dt.strftime("%b %d") + " - " +
        df_agg["period_end"].dt.strftime("%b %d")
    )

else:  # Monthly
    df["period_start"] = df["date_"].dt.to_period("M").apply(lambda p: p.start_time)
    df_agg = df.groupby("period_start", as_index=False).agg(
        value=(metric_column, "mean")
    )
    df_agg["time"] = df_agg["period_start"].dt.strftime("%b %y")

# sort chronologically by period_start
df_agg = df_agg.sort_values("period_start")
# domain order for x-axis
sort_list = df_agg["time"].tolist()

# add labels for each point
if not df_agg.empty:
    df_agg["value_label"] = df_agg["value"].round(2).astype(str) + "%"

# -----------------------------------------------------------------------------
# 6. CHARTING
# -----------------------------------------------------------------------------
st.title("Metrics vs. Releases")

# Base line + point markers
line = alt.Chart(df_agg).mark_line(point=True, color="steelblue").encode(
    x=alt.X("time:O", title="Time", sort=sort_list,
            axis=alt.Axis(labelAngle=0, labelAlign="center")),
    y=alt.Y("value:Q", title=metric_label)
)
# Data labels under points
text = alt.Chart(df_agg).mark_text(dy=15, color="white").encode(
    x=alt.X("time:O", sort=sort_list),
    y=alt.Y("value:Q"),
    text=alt.Text("value_label:N")
)

# -----------------------------------------------------------------------------
# Release aggregation per period
# -----------------------------------------------------------------------------
rel_filtered = releases_df[
    (releases_df["updated"] >= pd.to_datetime(start_date)) &
    (releases_df["updated"] <= pd.to_datetime(end_date))
].copy()

if gran == "Daily":
    rel_filtered["period_start"] = rel_filtered["updated"].dt.normalize()
    grouping = ["period_start"]
elif gran == "Weekly":
    rel_filtered["period_start"] = rel_filtered["updated"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    rel_filtered["period_end"]   = rel_filtered["updated"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
    grouping = ["period_start","period_end"]
else:
    rel_filtered["period_start"] = rel_filtered["updated"].dt.to_period("M").apply(lambda p: p.start_time)
    grouping = ["period_start"]

# count releases and concatenate keys
rel_agg = rel_filtered.groupby(grouping).agg(
    releases_count=("issue_key","count"),
    releases_keys=("issue_key", lambda x: ", ".join(x))
).reset_index()

# format time labels
if gran == "Daily":
    rel_agg["time"] = rel_agg["period_start"].dt.strftime("%a, %d %b")
elif gran == "Weekly":
    rel_agg["time"] = (
        rel_agg["period_start"].dt.strftime("%b %d") + " - " +
        rel_agg["period_end"].dt.strftime("%b %d")
    )
else:
    rel_agg["time"] = rel_agg["period_start"].dt.strftime("%b %y")

# sort for chart order
rel_agg = rel_agg.sort_values("period_start")

# neon-blue release rule & points with aggregated tooltip
rules = alt.Chart(rel_agg).mark_rule(color="#00FFFF").encode(
    x=alt.X("time:O", sort=sort_list)
)
points = alt.Chart(rel_agg).mark_point(color="#00FFFF", size=100).encode(
    x=alt.X("time:O", sort=sort_list),
    tooltip=[
        alt.Tooltip("releases_count:Q", title="Release Count"),
        alt.Tooltip("releases_keys:N",   title="Issue Keys")
    ]
)

# combine layers
temp = line + rules + points
chart = alt.layer(temp, text).properties(width=800, height=400).interactive()

if df_agg.empty:
    st.warning("No metric data available for the selected period.")
else:
    st.altair_chart(chart, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. RAW DATA (Optional)
# -----------------------------------------------------------------------------
with st.expander("Show raw aggregated data"):
    display_df = df_agg.copy()
    drop_cols = ["value","period_start"] + (["period_end"] if gran=="Weekly" else [])
    display_df = display_df.drop(columns=drop_cols)
    display_df = display_df.rename(columns={"time":"Time Period","value_label":data_label})
    st.dataframe(display_df)

with st.expander("Show release data"):
    # all releases in filtered period, descending by updated
    rel_details = rel_filtered.sort_values("updated", ascending=False)
    st.dataframe(rel_details)
