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
    # Assumes data/metrics_data_new.csv and data/release_data_new.csv exist
    metrics = pd.read_csv("data/metrics_data_new.csv", parse_dates=["date_"])
    releases = pd.read_csv("data/release_data_new.csv", parse_dates=["updated", "created"])
    return metrics, releases

metrics_df, releases_df = load_data()

# -----------------------------------------------------------------------------
# 3. DERIVED METRICS (as percentages)
# -----------------------------------------------------------------------------
metrics_df = metrics_df.assign(
    ticket_rate = metrics_df["fd_tickets"]    / metrics_df["active_sessions"] * 100,
    msat        = metrics_df["happy"]         / metrics_df["feedback_given"]   * 100
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
    ).rename(columns={"date_": "period_start"})
    df_agg["time"] = df_agg["period_start"].dt.strftime("%a, %d %b")

elif gran == "Weekly":
    df["period_start"] = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    df["period_end"]   = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
    df_agg = df.groupby(["period_start","period_end"], as_index=False).agg(
        value=(metric_column, "mean")
    )
    df_agg["time"] = (
        df_agg["period_start"].dt.strftime("%b %d")
        + " - " +
        df_agg["period_end"].dt.strftime("%b %d")
    )

else:  # Monthly
    df["period_start"] = df["date_"].dt.to_period("M").apply(lambda p: p.start_time)
    df_agg = df.groupby("period_start", as_index=False).agg(
        value=(metric_column, "mean")
    )
    df_agg["time"] = df_agg["period_start"].dt.strftime("%b %y")

# ensure chronological order
df_agg = df_agg.sort_values("period_start")
axis_order = df_agg["time"].tolist()

# label values for display
if not df_agg.empty:
    df_agg["value_label"] = df_agg["value"].round(2).astype(str) + "%"

# -----------------------------------------------------------------------------
# 6. CHARTING (dark mode, white line + neon-blue releases)
# -----------------------------------------------------------------------------
st.title("Metrics vs. Releases")

# white line + dots
line = alt.Chart(df_agg).mark_line(point=True, color="white").encode(
    x=alt.X(
        "time:O",
        sort=axis_order,
        axis=alt.Axis(labelAngle=0, labelAlign="center", labelColor="white", titleColor="white")
    ),
    y=alt.Y(
        "value:Q",
        title=metric_label,
        axis=alt.Axis(labelColor="white", titleColor="white")
    )
)

# white labels under each point
text = alt.Chart(df_agg).mark_text(dy=15, color="white").encode(
    x=alt.X("time:O", sort=axis_order),
    y="value:Q",
    text=alt.Text("value_label:N")
)

# prepare releases for annotation
rel_filtered = releases_df[
    (releases_df["updated"] >= pd.to_datetime(start_date)) &
    (releases_df["updated"] <= pd.to_datetime(end_date))
].copy()

if gran == "Daily":
    rel_filtered["period_start"] = rel_filtered["updated"].dt.normalize()
elif gran == "Weekly":
    rel_filtered["period_start"] = rel_filtered["updated"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    rel_filtered["period_end"]   = rel_filtered["updated"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
else:
    rel_filtered["period_start"] = rel_filtered["updated"].dt.to_period("M").apply(lambda p: p.start_time)

# count & list issue_keys per period
rel_count = (
    rel_filtered
      .groupby([c for c in ["period_start","period_end"] if c in rel_filtered], dropna=False)
      .agg(
        releases_count=("issue_key", "count"),
        releases_keys =("issue_key", lambda keys: ", ".join(keys))
      )
      .reset_index()
)

# rebuild the display label
if gran == "Daily":
    rel_count["time"] = rel_count["period_start"].dt.strftime("%a, %d %b")
elif gran == "Weekly":
    rel_count["time"] = (
        rel_count["period_start"].dt.strftime("%b %d")
        + " - " +
        rel_count["period_end"].dt.strftime("%b %d")
    )
else:
    rel_count["time"] = rel_count["period_start"].dt.strftime("%b %y")

rel_count = rel_count.sort_values("period_start")

# neon-blue release markers
rules = alt.Chart(rel_count).mark_rule(color="#00FFFF").encode(
    x=alt.X("time:O", sort=axis_order)
)
points = alt.Chart(rel_count).mark_point(color="#00FFFF", size=100).encode(
    x=alt.X("time:O", sort=axis_order),
    tooltip=[
        alt.Tooltip("releases_count:Q", title="Release Count"),
        alt.Tooltip("releases_keys:N",    title="Issue Keys")
    ]
)

# combine all layers
chart = (
    (line + text + rules + points)
    .properties(width=800, height=400, background="#111111")
    .configure_view(strokeOpacity=0)
    .interactive()
)

if df_agg.empty:
    st.warning("No metric data available for the selected period.")
else:
    st.altair_chart(chart, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. RAW DATA (Optional)
# -----------------------------------------------------------------------------
with st.expander("Show raw aggregated data"):
    df_metrics = df.copy()
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

    agg = (
        df_metrics
          .groupby(group_cols, as_index=False)
          .agg(
            active_sessions=("active_sessions","sum"),
            fd_tickets      =("fd_tickets","sum"),
            feedback_given  =("feedback_given","sum"),
            happy           =("happy","sum")
          )
    )

    agg["MSAT %"] = (agg["happy"] / agg["feedback_given"] * 100).round(2).astype(str) + "%"
    agg["Ticket creation %"] = (agg["fd_tickets"] / agg["active_sessions"] * 100).round(2).astype(str) + "%"

    # attach our formatted time label
    agg = agg.merge(df_agg[["period_start","time"]], on="period_start", how="left")

    # custom K/M formatting
    def fmt(x):
        if x >= 1e6: return f"{x/1e6:.1f}M"
        if x >= 1e3: return f"{x/1e3:.1f}K"
        return str(int(x))

    display_df = agg[[
        "time","active_sessions","fd_tickets","feedback_given","MSAT %","Ticket creation %"
    ]].copy()
    display_df["Active sessions"] = display_df["active_sessions"].apply(fmt)
    display_df["FD Tickets"]      = display_df["fd_tickets"].apply(fmt)
    display_df["Feedback given"]  = display_df["feedback_given"].apply(fmt)
    display_df = (
        display_df
          .drop(columns=["active_sessions","fd_tickets","feedback_given"])
          .rename(columns={"time":"Time Period"})
    )
    st.dataframe(display_df)

with st.expander("Show release data"):
    rel_display = rel_filtered.copy()
    rel_display = rel_display[[
        "period_start","issue_key","summary","jira_link","issue_type","created"
    ]]
    rel_display["Release Date"] = rel_display["period_start"].dt.date
    rel_display = rel_display.rename(columns={
        "issue_key":"JIRA ID",
        "summary":"Summary",
        "jira_link":"JIRA Link",
        "issue_type":"Issue Type",
        "created":"Created On"
    })
    rel_display["JIRA Link"] = rel_display["JIRA Link"].apply(
        lambda url: f"<a href='{url}' target='_blank'>{url}</a>"
    )
    rel_display = rel_display[[
        "Release Date","JIRA ID","Summary","JIRA Link","Issue Type","Created On"
    ]].sort_values("Release Date", ascending=False)
    st.markdown(
        rel_display.to_html(index=False, escape=False),
        unsafe_allow_html=True
    )
