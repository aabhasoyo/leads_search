import streamlit as st
import pandas as pd
import numpy as np
import base64
from scipy.spatial import cKDTree

# Set Page Config
st.set_page_config(page_title="🏡 Discover Leads", layout="wide")

st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
    </style>
""", unsafe_allow_html=True)

# Hardcoded login credentials
VALID_CREDENTIALS = {"kapilraina": "kapil123", "aabhas": "aabhas123", "admin": "password123"}

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h2 style='text-align: center;'>🔑 Login to Access Leads</h2>", unsafe_allow_html=True)
    username = st.text_input("Username", placeholder="Enter username")
    password = st.text_input("Password", type="password", placeholder="Enter password")

    if st.button("Login"):
        if username in VALID_CREDENTIALS and password == VALID_CREDENTIALS[username]:
            st.session_state.authenticated = True
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Invalid username or password")

    st.stop()

# Load dataset (Cached)
@st.cache_data
def load_data():
    df = pd.read_csv("properties.csv", encoding="ISO-8859-1")
    return df

data = load_data()

# Cache KDTree for fast spatial search
@st.cache_data
def build_tree(df):
    coords = df[['Latitude', 'Longitude']].to_numpy()
    return cKDTree(coords)

tree = build_tree(data)

# Preprocess Clickable Links ONCE to avoid slow `.apply()`
if "Property Link" in data.columns:
    data["Source"] = data.apply(lambda row: f'<a href="{row["Property Link"]}" target="_blank">{row["Source"]}</a>' if pd.notna(row["Property Link"]) else row["Source"], axis=1)

if "Website" in data.columns:
    data["Website"] = data["Website"].apply(lambda x: f'<a href="{x}" target="_blank">🌐 Visit</a>' if pd.notna(x) else "")

data["Navigate"] = data.apply(lambda row: f'<a href="https://www.google.com/maps/dir/?api=1&destination={row["Latitude"]},{row["Longitude"]}" target="_blank">🗺️ Open in Maps</a>' if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]) else "", axis=1)

# UI: Title and Description
st.markdown("<h1 style='text-align: center; color: #4CAF50;'>Leads Search Portal</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center;'>Discover Leads Near You Effortlessly! 🔍</h3>", unsafe_allow_html=True)
st.divider()

results = data.copy()  # Default to all properties

# Button to Show Filters
if st.button("🔍 Open Filters", use_container_width=True):
    with st.expander("Filter Options", expanded=True):
        search_type = st.radio("Search by", ["📍 Latitude/Longitude", "🌍 Location"])

        if search_type == "📍 Latitude/Longitude":
            lat = st.number_input("Enter Latitude", value=46.94412, format="%f")
            lng = st.number_input("Enter Longitude", value=14.70255, format="%f")
            radius = st.slider("Search Radius (km)", 1, 50, 10)
            query_point = np.array([lat, lng])

            distances, indices = tree.query(query_point, k=10, distance_upper_bound=radius / 111)
            indices = indices[distances != np.inf]
            results = data.iloc[indices].copy()
            results["Distance (km)"] = np.round(distances[distances != np.inf] * 111, 2)
            results.sort_values(by="Distance (km)", inplace=True)

        elif search_type == "🌍 Location":
            country = st.selectbox("🌎 Select Country", sorted(data["Country"].dropna().unique()))
            region_options = ["All"] + sorted(data[data["Country"] == country]["Region"].dropna().unique())
            region = st.selectbox("🏙️ Select Region", region_options)
            results = data[data["Country"] == country].copy() if region == "All" else data[(data["Country"] == country) & (data["Region"] == region)].copy()

        # Additional Filters
        sources = sorted(data["Source"].dropna().unique())
        selected_source = st.selectbox("Filter by Source", ["All"] + sources)
        hide_nan_email = st.checkbox("Hide rows without Email")
        hide_nan_phone = st.checkbox("Hide rows without Phone Number")

        # Sorting
        sort_by = st.selectbox("Sort results by", ["Distance (km)", "Rating", "Review Count"])
        if sort_by in results.columns:
            results = results.sort_values(by=sort_by, ascending=(sort_by != "Rating"))

# Limit Number of Results to Improve Performance
max_results = 500
if len(results) > max_results:
    results = results.head(max_results)

st.markdown(f"<h3>✅ Found {len(results)} Properties</h3>", unsafe_allow_html=True)

# Display DataFrame using `st.dataframe()` instead of slow HTML rendering
st.dataframe(results, height=600)

# Export CSV Button
csv_data = results.to_csv(index=False).encode('utf-8')
b64 = base64.b64encode(csv_data).decode()
href = f'<a href="data:file/csv;base64,{b64}" download="filtered_results.csv">📥 Download CSV</a>'
st.markdown(href, unsafe_allow_html=True)

# Footer
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>🚀 Developed by Aabhas</p>", unsafe_allow_html=True)
