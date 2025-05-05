import os
import json
import base64
import io
from collections import defaultdict
from datetime import datetime, timedelta

import requests
import streamlit as st
from PIL import Image
from fuzzywuzzy import process

def airport_selector(label):
    st.markdown(f"**{label}**")
    search_input = st.text_input(f"{label} - Search by city, IATA, or ICAO", key=label)

    if search_input:
        choices = airports_df["label"].tolist()
        matches = process.extract(search_input, choices, limit=10)
        options = [match[0] for match in matches]
    else:
        options = airports_df["label"].tolist()

    if not options:
        st.warning("No matching airports.")
        return "", ""

    selected = st.selectbox(f"Matching results for {label}", options, key=f"select_{label}")

    try:
        code_part = selected.split("(")[-1].split(")")[0]
        iata, icao = [x.strip() for x in code_part.split("/")]
        return iata, icao
    except:
        return "", ""

import pandas as pd

# --------------------------- CONFIG --------------------------- #
API_KEY = st.secrets["AVIATIONSTACK_API_KEY"]
BASE_URL = "http://api.aviationstack.com/v1/flights"
AIRPORT_CSV_URL = "https://raw.githubusercontent.com/nickair1992/flightdelay/master/airlines-logos-dataset-master/airportlist.csv"


# --------------------- LOAD AIRPORT CSV ----------------------- #
@st.cache_data
def load_airports():
    df = pd.read_csv("https://raw.githubusercontent.com/nickair1992/flightdelay/master/airlines-logos-dataset-master/airportlist.csv")
    
    # Make sure columns are clean
    df.columns = [col.strip().lower() for col in df.columns]

    required_cols = {"city", "name", "iata", "icao"}
    if not required_cols.issubset(df.columns):
        st.error(f"Missing required columns: {required_cols - set(df.columns)}")
        st.stop()

    df["label"] = df.apply(
        lambda row: f"{row['city']} - {row['name']} ({row['iata']} / {row['icao']})",
        axis=1
    )
    return df

airports_df = load_airports()

def airport_selector(label):
    st.markdown(f"**{label}**")
    search_input = st.text_input(f"{label} - Search by city, IATA, or ICAO", key=label)

    if search_input:
        choices = airports_df["label"].tolist()
        matches = process.extract(search_input, choices, limit=10)
        options = [match[0] for match in matches]
    else:
        options = airports_df["label"].tolist()

    if not options:
        st.warning("No matching airports.")
        return "", ""

    selected = st.selectbox(f"Matching results for {label}", options, key=f"select_{label}")

    try:
        code_part = selected.split("(")[-1].split(")")[0]
        iata, icao = [x.strip() for x in code_part.split("/")]
        return iata, icao
    except:
        return "", ""


# ------------------------ LOAD LOGO MAP ----------------------- #
GITHUB_USERNAME = "nickair1992"
GITHUB_REPO_NAME = "flightdelay"
GITHUB_BRANCH = "master"
AIRLINES_JSON_PATH = "airlines-logos-dataset-master/airlines.json"
LOGO_IMAGE_PATH = "airlines-logos-dataset-master/images"
AIRLINES_JSON_URL = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}/{GITHUB_BRANCH}/{AIRLINES_JSON_PATH}"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}/{GITHUB_BRANCH}/{LOGO_IMAGE_PATH}/"

try:
    response = requests.get(AIRLINES_JSON_URL)
    response.raise_for_status()
    airline_json = response.json()["data"]
except requests.exceptions.RequestException as e:
    st.error(f"Error loading airlines.json from GitHub: {e}")
    airline_json = []

airline_logos = {}
for row in airline_json:
    logo_path = row.get("logo")
    if not logo_path:
        continue
    file_name = os.path.basename(logo_path)
    if row.get("iata_code"):
        airline_logos[row["iata_code"].upper()] = file_name
    if row.get("icao_code"):
        airline_logos[row["icao_code"].upper()] = file_name

# ---------------------  UTILITY FUNCTIONS  -------------------- #
def fetch_flights(dep, arr, date_str):
    try:
        r = requests.get(
            BASE_URL,
            params={"access_key": API_KEY, "dep_icao": dep, "arr_icao": arr, "flight_date": date_str},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("data", [])
    except requests.RequestException:
        pass
    return []

def calculate_delay(f):
    sched = f["arrival"].get("scheduled")
    actual = f["arrival"].get("actual")
    if sched and actual:
        s_dt = datetime.strptime(sched, "%Y-%m-%dT%H:%M:%S+00:00")
        a_dt = datetime.strptime(actual, "%Y-%m-%dT%H:%M:%S+00:00")
        return (a_dt - s_dt).total_seconds() / 60
    return None

def delay_color(val):
    if val is None:
        return "#6c757d"
    if val >= 45:
        return "#f94144"
    if val >= 15:
        return "#fcca46"
    return "#70d86b"

BADGE_COLORS = {"green": "#70d86b", "yellow": "#fcca46", "red": "#f94144", "grey": "#6c757d"}

def badge(label, clr):
    return f"<span style='background:{clr};padding:4px 8px;border-radius:6px;font-size:0.9rem;color:#fff;font-weight:500'>{label}</span>"

def get_logo(code):
    file_name = airline_logos.get(code.upper())
    if not file_name:
        return None
    image_url = GITHUB_RAW_URL + file_name
    try:
        response = requests.get(image_url, stream=True)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        return image
    except requests.exceptions.RequestException as e:
        st.warning(f"Could not load logo for {code}: {e}")
        return None

def img_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

def fmt_time(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S+00:00").strftime("%H:%M")
    except:
        return "--:--"

# ------------------------- STREAMLIT UI ----------------------- #
st.set_page_config(page_title="Flight Delay Advisor", layout="wide")
st.markdown("""
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap' rel='stylesheet'>
<style>
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.flight-container {
    border-left: 8px solid;
    border-radius: 5px;
    margin-bottom: 10px;
    padding: 16px;
    background-color: #f9f9f9;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}
.airline-info {
    display: flex;
    align-items: center;
    margin-bottom: 10px;
}
.airline-logo {
    max-height: 30px;
    width: auto;
    margin-right: 10px;
}
.flight-numbers {
    font-size: 1.1rem;
    font-weight: bold;
    color: #333;
}
.schedule-item {
    margin-left: 10px;
    margin-bottom: 8px;
    font-size: 0.95rem;
    color: #555;
}
.day-data {
    margin-left: 20px;
    margin-bottom: 4px;
    font-size: 0.9rem;
    color: #777;
}
.overall-info {
    margin-top: 10px;
    display: flex;
    gap: 20px;
    align-items: center;
    font-size: 0.9rem;
    color: #777;
    margin-left: 10px;
}
.delay-metric {
    font-size: 1rem;
    font-weight: bold;
    color: #333;
}
.risk-badge {
    font-size: 0.9rem !important;
}
</style>
""", unsafe_allow_html=True)

st.title("✈️ Flight Delay Advisor")

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    iata_dep, origin = airport_selector("Select Departure Airport")
with col2:
    iata_arr, destination = airport_selector("Select Arrival Airport")
with col3:
    days_back = st.slider("Past days (with flights)", 3, 30, 7)

# --------------------------- MAIN LOGIC --------------------------- #
if st.button("Fetch Flights"):
    grouped_flights_raw = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    all_delays = []
    checked, valid = 0, 0

    while valid < days_back and checked < 90:
        date_dt = datetime.utcnow() - timedelta(days=checked)
        checked += 1
        flights = fetch_flights(origin, destination, date_dt.strftime("%Y-%m-%d"))
        if not flights:
            continue
        valid += 1
        weekday = date_dt.strftime("%A")
        for f in flights:
            dep_s = f["departure"].get("scheduled")
            arr_s = f["arrival"].get("scheduled")
            if not (dep_s and arr_s and f["departure"].get("actual")):
                continue
            delay = calculate_delay(f)
            status = f.get("flight_status", "").lower()
            bad = status in {"cancelled", "diverted"}
            flight_num = f["flight"].get("iata")
            logo_code = f["airline"].get("iata") or f["airline"].get("icao")
            airline_name = f["airline"].get("name")
            dep_fmt = fmt_time(dep_s)
            arr_fmt = fmt_time(arr_s)
            sched_key = f"{dep_fmt} → {arr_fmt}"
            grouped_flights_raw[airline_name][flight_num][sched_key].append({
                "delay": None if bad else delay,
                "day": weekday,
                "logo": logo_code,
                "status": status,
                "airline_code": logo_code,
            })
            all_delays.append(999 if bad else delay or 0)

    if not grouped_flights_raw:
        st.warning("No flights found.")
        st.stop()

    st.subheader("📊 Summary")
    total = sum(len(daylist) for airline_flights in grouped_flights_raw.values() for flight_schedules in airline_flights.values() for sched in flight_schedules.values() for daylist in [sched])
    d15 = sum(1 for d in all_delays if d >= 15 and d < 45)
    d45 = sum(1 for d in all_delays if d >= 45)
    d0 = total - d15 - d45

    green_pct = d0 / total * 100
    yellow_pct = d15 / total * 100
    red_pct = d45 / total * 100

    st.markdown(
        f"""
    <div style='height:20px;width:100%;background:#eee;border-radius:6px;margin-bottom: 20px;overflow:hidden'>
      <div style='width:{green_pct:.0f}%;background:#70d86b;height:100%;float:left'></div>
      <div style='width:{yellow_pct:.0f}%;background:#fcca46;height:100%;float:left'></div>
      <div style='width:{red_pct:.0f}%;background:#f94144;height:100%;float:left'></div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Flights", total)
    c2.metric("Delays >15min", f"{d15} ({d15/total:.0%})")
    c3.metric("Delays >45min", f"{d45} ({d45/total:.0%})")

    st.subheader("🛫 Breakdown")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0

    sorted_airlines = sorted(grouped_flights_raw.keys())

    for airline in sorted_airlines:
        flights_for_airline = grouped_flights_raw[airline]
        sorted_flights = sorted(flights_for_airline.keys())

        for flight_num in sorted_flights:
            schedules = flights_for_airline[flight_num]
            all_delays_flight = [entry['delay'] for sched_entries in schedules.values() for entry in sched_entries if entry['delay'] is not None]
            avg_delay_flight = avg(all_delays_flight)
            box_border_color = delay_color(avg_delay_flight)
            first_airline_code = next(iter(next(iter(schedules.values()))))['airline_code'] if schedules else None
            logo_img = get_logo(first_airline_code)
            logo_html = f"<img src='data:image/png;base64,{img_b64(logo_img)}' class='airline-logo' style='margin-right: 10px;'>" if logo_img else ""

            st.markdown(
                f"""
                <div class='flight-container' style='border-left-color: {box_border_color};'>
                    <div class='airline-info'>
                        {logo_html} <strong class='flight-numbers'>{airline} {flight_num}</strong>
                    </div>
                """,
                unsafe_allow_html=True,
            )

            for sched_key, entries in schedules.items():
                delays_by_day = defaultdict(list)
                for entry in entries:
                    if entry["delay"] is not None:
                        delays_by_day[entry["day"]].append(entry["delay"])

                st.markdown(
                    f"""<div class='schedule-item'><strong>{sched_key}</strong></div>""",
                    unsafe_allow_html=True,
                )
                days_for_schedule = sorted(list(delays_by_day.keys()), key=day_order.index)
                for day in days_for_schedule:
                    avg_delay_day = avg(delays_by_day[day])
                    max_delay_day = max(delays_by_day[day])
                    st.markdown(
                        f"""
                        <div class='day-data'>
                            <span style='display: inline-block; width: 90px;'>{day}:</span>
                            Avg {badge(f'{avg_delay_day:.1f} min', delay_color(avg_delay_day))},
                            Max {badge(f'{max_delay_day:.1f} min', delay_color(max_delay_day))}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

            st.markdown(
                f"""
                        <div class='overall-info'>
                            <div>Overall Avg Delay: <span class='delay-metric'>{avg_delay_flight:.1f} min</span></div>
                            <div>Overall Max Delay: <span class='delay-metric'>{max(all_delays_flight) if all_delays_flight else 0:.1f} min</span></div>
                            <div>Overall Risk: <span class='risk-badge'>{badge({
                                "#70d86b": "Low Delay Risk",
                                "#fcca46": "Moderate Delay Risk",
                                "#f94144": "High Delay Risk",
                                "#6c757d": "No Data"
                            }.get(box_border_color, "Unknown Risk"), box_border_color)}</span></div>
                        </div>
                    </div>
                """,
                unsafe_allow_html=True,
            )

    st.caption("Data from Aviationstack")

