import streamlit as st
import pandas as pd
import altair as alt

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG & LIGHT MODE STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Metrics & Releases Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# inject a bit of CSS so Streamlit’s background and text flip to light mode
st.markdown(
    """
    <style>
      /* main page background & text */
      .stApp, .css-18ni7ap {background-color: white; color: #111111;}
      /* sidebar background & text */
      .css-1d391kg {background-color: white; color: #111111;}
      /* table headers/text */
      .css-1lcbmhc, .css-1l02zno {color: #111111;}
    </style>
    """,
    unsafe_allow_html=True
)

# -----------------------------------------------------------------------------
# 2. DATA LOADING
# -----------------------------------------------------------------------------
@st.cache_data
def load_data():
    metrics = pd.read_csv("data/metrics_data.csv", parse_dates=["date_"])
    releases = pd.read_csv("data/release_data.csv", parse_dates=["updated"])
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

gran = st.sidebar.selectbox("Time Granularity", ["Daily", "Weekly", "Monthly"])

min_date = metrics_df["date_"].min().date()
max_date = metrics_df["date_"].max().date()

if gran == "Daily":
    default_start = max_date - pd.Timedelta(days=14)
elif gran == "Weekly":
    default_start = max_date - pd.Timedelta(weeks=5)
else:  # Monthly
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
metric_label  = st.sidebar.selectbox("Metric to plot", list(metric_options.keys()))
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
        active_sessions = ("active_sessions", "sum"),
        fd_tickets      = ("fd_tickets",     "sum"),
        feedback_given  = ("feedback_given", "sum"),
        happy_sum       = ("happy",          "sum")
    )
    df_agg["period_start"] = df_agg["date_"]
    df_agg["time"] = df_agg["date_"].dt.strftime("%a, %d %b")

elif gran == "Weekly":
    df["period_start"] = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
    df["period_end"]   = df["date_"].dt.to_period("W-SAT").apply(lambda p: p.end_time)
    df_agg = df.groupby("period_start", as_index=False).agg(
        active_sessions = ("active_sessions", "sum"),
        fd_tickets      = ("fd_tickets",     "sum"),
        feedback_given  = ("feedback_given", "sum"),
        happy_sum       = ("happy",          "sum")
    )
    df_agg["time"] = (
        df_agg["period_start"].dt.strftime("%b %d")
        + " - " +
        (df_agg["period_start"] + pd.Timedelta(days=6)).dt.strftime("%b %d")
    )

else:  # Monthly
    df["period_start"] = df["date_"].dt.to_period("M").apply(lambda p: p.start_time)
    df_agg = df.groupby("period_start", as_index=False).agg(
        active_sessions = ("active_sessions", "sum"),
        fd_tickets      = ("fd_tickets",     "sum"),
        feedback_given  = ("feedback_given", "sum"),
        happy_sum       = ("happy",          "sum")
    )
    df_agg["time"] = df_agg["period_start"].dt.strftime("%b %y")

# recompute MSAT% and Ticket% from sums
df_agg = df_agg.assign(
    msat_pct         = df_agg["happy_sum"]        / df_agg["feedback_given"] * 100,
    ticket_rate_pct  = df_agg["fd_tickets"]       / df_agg["active_sessions"] * 100
)

# formatted labels for the line
df_agg["value_label"] = df_agg[metric_column.replace("_", "") + "_pct" if metric_column=="fd_tickets" else metric_column + "_pct"]\
    .round(2).astype(str) + "%"

# -----------------------------------------------------------------------------
# 6. CHARTING (light mode)
# -----------------------------------------------------------------------------
st.title("Metrics vs. Releases")

# base line + dots
line = (
    alt.Chart(df_agg)
    .mark_line(point=True, color="black")
    .encode(
        x=alt.X("time:O", title="Time", axis=alt.Axis(labelAngle=0, labelAlign="center", labelColor="black", titleColor="black")),
        y=alt.Y(f"{metric_column}_pct:Q", title=metric_label, axis=alt.Axis(labelColor="black", titleColor="black"))
    )
)

# text labels under each dot
labels = (
    alt.Chart(df_agg)
    .mark_text(dy=15, color="black")
    .encode(
        x="time:O",
        y=alt.Y(f"{metric_column}_pct:Q"),
        text=alt.Text("value_label:N")
    )
)

# prepare releases count + keys per period
rel = releases_df.copy()
rel = rel[
    (rel["updated"] >= pd.to_datetime(start_date)) &
    (rel["updated"] <= pd.to_datetime(end_date))
].copy()

# aggregate releases by the same period_start
if gran == "Daily":
    rel["period_start"] = rel["updated"].dt.normalize()
elif gran == "Weekly":
    rel["period_start"] = rel["updated"].dt.to_period("W-SAT").apply(lambda p: p.start_time)
else:
    rel["period_start"] = rel["updated"].dt.to_period("M").apply(lambda p: p.start_time)

rel_agg = (
    rel.groupby("period_start", as_index=False)
       .agg(
         release_count = ("issue_key", "count"),
         issue_keys    = ("issue_key", lambda keys: ", ".join(keys))
       )
)

# map rel_agg.time for x-axis
rel_agg["time"] = (
    pd.merge(df_agg[["period_start","time"]], rel_agg, on="period_start", how="right")
      ["time"]
)

rules = (
    alt.Chart(rel_agg)
    .mark_rule(color="#ffd966")
    .encode(x="time:O")
)

points = (
    alt.Chart(rel_agg)
    .mark_point(color="#ffd966", size=100)
    .encode(
        x="time:O",
        tooltip=[
            alt.Tooltip("release_count:Q", title="Release Count"),
            alt.Tooltip("issue_keys:N",    title="Issue Keys")
        ]
    )
)

# combine all and force white bg
chart = (
    (line + labels + rules + points)
    .properties(width=800, height=400, background="white")
    .configure_view(strokeOpacity=0)  # remove border
    .configure_axis(gridColor="#ddd")
)

st.altair_chart(chart, use_container_width=True)

# -----------------------------------------------------------------------------
# 7. RAW DATA (Optional)
# -----------------------------------------------------------------------------
with st.expander("Show raw aggregated data"):
    display = df_agg[[
        "time",
        "active_sessions", "fd_tickets", "feedback_given",
        "msat_pct", "ticket_rate_pct"
    ]].copy()
    display.columns = [
        "Time Period",
        "Active sessions", "FD Tickets", "Feedback given",
        "MSAT %", "Ticket creation %"
    ]
    # custom number formatting
    fmt = lambda x: (
        f"{x/1e6:.1f}M" if x>=1e6 else
        f"{x/1e3:.1f}K" if x>=1e3 else str(int(x))
    )
    for col in ["Active sessions","FD Tickets","Feedback given"]:
        display[col] = display[col].apply(fmt)
    st.dataframe(display)

with st.expander("Show release data"):
    # pick only your six fields and rename
    rel_raw = rel[[
        "period_start","issue_key","summary","jira_link","issue_type","created"
    ]].copy()
    rel_raw.columns = [
        "Release Date", "JIRA ID", "Summary","JIRA Link","Issue Type","Created On"
    ]
    # date-only
    rel_raw["Release Date"] = rel_raw["Release Date"].dt.date
    # hyperlink column
    rel_raw["JIRA Link"] = rel_raw["JIRA Link"].apply(
        lambda url: f'<a href="{url}" target="_blank">{url}</a>'
    )
    # sort newest first
    rel_raw = rel_raw.sort_values("Release Date", ascending=False)
    # render with links
    st.markdown(rel_raw.to_html(escape=False, index=False), unsafe_allow_html=True)
