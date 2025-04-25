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
    releases = pd.read_csv("data/release_data.csv", parse_dates=["updated","created"])
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

# sort chronologically
df_agg = df_agg.sort_values("period_start")
axis_order = df_agg["time"].tolist()

# label values
if not df_agg.empty:
    df_agg["value_label"] = df_agg["value"].round(2).astype(str) + "%"

# -----------------------------------------------------------------------------
# 6. CHARTING
# -----------------------------------------------------------------------------
st.title("Metrics vs. Releases")
line = alt.Chart(df_agg).mark_line(point=True, color="steelblue").encode(
    x=alt.X("time:O", sort=axis_order, axis=alt.Axis(labelAngle=0, labelAlign="center")),
    y=alt.Y("value:Q", title=metric_label)
)
text = alt.Chart(df_agg).mark_text(dy=15, color="white").encode(
    x=alt.X("time:O", sort=axis_order),
    y="value:Q",
    text=alt.Text("value_label:N")
)

# Release aggregation
rel_filtered = releases_df[
    (releases_df["updated"] >= pd.to_datetime(start_date)) &
    (releases_df["updated"] <= pd.to_datetime(end_date))
].copy()
if gran == "Daily":
    rel_filtered["period_start"] = rel_filtered["updated"].dt.normalize()
    grp = ["period_start"]
elif gran == "Weekly":
    rel_filtered["period_start"] = rel_filtered["updated"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    rel_filtered["period_end"]   = rel_filtered["updated"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
    grp = ["period_start","period_end"]
else:
    rel_filtered["period_start"] = rel_filtered["updated"].dt.to_period("M").apply(lambda p: p.start_time)
    grp = ["period_start"]
rel_count = rel_filtered.groupby(grp).agg(
    releases_count=("issue_key","count"),
    releases_keys=("issue_key", lambda x: ", ".join(x))
).reset_index()
if gran == "Daily":
    rel_count["time"] = rel_count["period_start"].dt.strftime("%a, %d %b")
elif gran == "Weekly":
    rel_count["time"] = (
        rel_count["period_start"].dt.strftime("%b %d") + " - " +
        rel_count["period_end"].dt.strftime("%b %d")
    )
else:
    rel_count["time"] = rel_count["period_start"].dt.strftime("%b %y")
rel_count = rel_count.sort_values("period_start")
rules = alt.Chart(rel_count).mark_rule(color="#00FFFF").encode(x=alt.X("time:O", sort=axis_order))
points = alt.Chart(rel_count).mark_point(color="#00FFFF", size=100).encode(
    x=alt.X("time:O", sort=axis_order),
    tooltip=[alt.Tooltip("releases_count:Q", title="Release Count"), alt.Tooltip("releases_keys:N", title="Issue Keys")]
)
chart = alt.layer(line + rules + points, text).properties(width=800, height=400).interactive()
if df_agg.empty:
    st.warning("No metric data available for the selected period.")
else:
    st.altair_chart(chart, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. RAW DATA (Optional)
# -----------------------------------------------------------------------------
with st.expander("Show raw aggregated data"):
    df_metrics = df.copy()
    # group and aggregate metrics
    if gran == "Daily":
        df_metrics["period_start"] = df_metrics["date_"].dt.normalize()
        group_cols = ["period_start"]
    elif gran == "Weekly":
        df_metrics["period_start"] = df_metrics["date_"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
        df_metrics["period_end"]   = df_metrics["date_"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
        group_cols = ["period_start","period_end"]
    else:
        df_metrics["period_start"] = df_metrics["date_"].dt.to_period("M").apply(lambda p: p.start_time)
        group_cols = ["period_start"]
    agg = df_metrics.groupby(group_cols).agg(
        active_sessions=("active_sessions","sum"),
        fd_tickets=("fd_tickets","sum"),
        feedback_given=("feedback_given","sum"),
        happy=("happy","sum")
    ).reset_index()
    # recompute percentages
    agg["MSAT %"] = (agg["happy"] / agg["feedback_given"] * 100).round(2).astype(str) + "%"
    agg["Ticket creation %"] = (agg["fd_tickets"] / agg["active_sessions"] * 100).round(2).astype(str) + "%"
    # merge labels
    agg = agg.merge(df_agg[["period_start","time"]], on="period_start", how="left")
    # format large numbers
    def fmt(v): return f"{v/1_000_000:.1f}M" if v >= 1e6 else (f"{v/1_000:.1f}K" if v >= 1e3 else str(int(v)))
    # build display table
    display_df = agg[["time","active_sessions","fd_tickets","feedback_given","MSAT %","Ticket creation %"]].copy()
    display_df["Active sessions"] = display_df["active_sessions"].apply(fmt)
    display_df["FD Tickets"]     = display_df["fd_tickets"].apply(fmt)
    display_df["Feedback given"]  = display_df["feedback_given"].apply(fmt)
    display_df = display_df.drop(columns=["active_sessions","fd_tickets","feedback_given"])
    display_df = display_df.rename(columns={"time":"Time Period"})
    st.dataframe(display_df)

with st.expander("Show release data"):
    # select and rename fields
    rel_display = rel_filtered.copy()
    rel_display = rel_display.loc[:, ["period_start","issue_key","summary","jira_link","issue_type","created"]]
    rel_display = rel_display.rename(columns={
        "period_start":"Release Date",
        "issue_key":"JIRA ID",
        "summary":"Summary",
        "jira_link":"JIRA Link",
        "issue_type":"Issue Type",
        "created":"Created On"
    })
    # sort by Release Date descending
    rel_display = rel_display.sort_values("Release Date", ascending=False)
    st.dataframe(rel_display)
