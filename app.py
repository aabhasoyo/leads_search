import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from scipy.spatial import cKDTree
import numpy as np
import base64

# Set Page Config
st.set_page_config(page_title="🏡 Discover Leads", layout="wide")

import streamlit as st
import pandas as pd
import numpy as np
from urllib.parse import urlparse, parse_qs

# Extract URL parameters
query_params = st.query_params
lat = query_params.get("lat")
lng = query_params.get("lng")
radius = query_params.get("radius")
country = query_params.get("country")
region = query_params.get("region")

# Convert numeric values
if lat and lng and radius:
    lat, lng, radius = float(lat), float(lng), float(radius)

# If parameters exist, set view mode to shared
is_shared_view = bool(lat and lng and radius) or bool(country)

# Hardcoded login credentials (Replace with a secure method later)
VALID_CREDENTIALS = {
    "kapilraina": "kapil123",
    "aabhas": "aabhas123",
    "admin": "password123"
}

# Initialize session state for authentication
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Authentication form
if not st.session_state.authenticated and not is_shared_view:
    # Show login form
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

# Load dataset
@st.cache_data
def load_data():
    return pd.read_csv("properties.csv", encoding="ISO-8859-1")

data = load_data()

# Build KDTree for fast spatial search
def build_tree(data):
    coords = data[['Latitude', 'Longitude']].to_numpy()
    return cKDTree(coords), coords

tree, coords = build_tree(data)

# Custom Styling
st.markdown("""
    <style>
        a { text-decoration: none !important; }
    </style>
""", unsafe_allow_html=True)

# Title and Description
st.markdown("<h1 style='text-align: center; color: #4CAF50;'>Leads Search Portal</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center;'>Discover Leads Near You Effortlessly! 🔍</h3>", unsafe_allow_html=True)
st.divider()

# Check if data is properly loaded
print(data.head())  

# Define sources safely
sources = data["Source"].unique().tolist() if "Source" in data.columns else []

# Ensure results is always initialized
results = pd.DataFrame()

if not is_shared_view:
    st.sidebar.header("🔎 Search & Filter Options")
    
    search_type = st.sidebar.radio("Search by", ["📍 Latitude/Longitude", "🌍 Location"])

    if search_type == "📍 Latitude/Longitude":
        lat = st.sidebar.number_input("Enter Latitude", value=46.94412, format="%f")
        lng = st.sidebar.number_input("Enter Longitude", value=14.70255, format="%f")
        radius = st.sidebar.slider("Search Radius (km)", 1, 50, 10)

    elif search_type == "🌍 Location":
        country = st.sidebar.selectbox("🌎 Select Country", sorted(data["Country"].dropna().unique()))
        region_options = ["All"] + sorted(data[data["Country"] == country]["Region"].dropna().unique())
        region = st.sidebar.selectbox("🏙️ Select Region", region_options)

    # Define filters only if not in shared view
    selected_source = st.sidebar.selectbox("Filter by Source", ["All"] + sources, key="selected_source_filter")
    hide_nan_email = st.sidebar.checkbox("Hide rows without Email", key="hide_email")
    hide_nan_phone = st.sidebar.checkbox("Hide rows without Phone Number", key="hide_phone")

# If shared view, set filters directly
if is_shared_view:
    if lat and lng and radius:
        query_point = np.array([lat, lng])
        distances, indices = tree.query(query_point, k=10, distance_upper_bound=radius / 111)
        indices = indices[distances != np.inf]
        results = data.iloc[indices].copy()
        results["Distance (km)"] = np.round(distances[distances != np.inf] * 111, 2)
        results.sort_values(by="Distance (km)", inplace=True)
    
    elif country:
        results = data[data["Country"] == country].copy() if region == "All" else data[(data["Country"] == country) & (data["Region"] == region)].copy()

# Sorting (Ensure results exist before sorting)
sort_by = st.sidebar.selectbox("Sort results by", ["Distance (km)", "Rating", "Review Count"], key="sort_by")
if not results.empty and sort_by in results.columns:
    results = results.sort_values(by=sort_by, ascending=(sort_by != "Rating"))

# Display Results
st.markdown(f"<h3>✅ Found {len(results)} Properties</h3>", unsafe_allow_html=True)

# Define Display Columns
display_cols = ["Source", "Name", "Address", "Navigate", "Rating", "Review Count", "Website", "Phone Number", "Email"]
if "Distance (km)" in results.columns:
    display_cols.insert(2, "Distance (km)")

# Make Source Clickable
if "Source" in results.columns and "Property Link" in results.columns:
    results["Source"] = results.apply(lambda row: f'<a href="{row["Property Link"]}" target="_blank">{row["Source"]}</a>' if pd.notna(row["Property Link"]) else row["Source"], axis=1)

# Make Website Clickable
if "Website" in results.columns:
    results["Website"] = results["Website"].apply(lambda x: f'<a href="{x}" target="_blank">🌐 Visit</a>' if pd.notna(x) else "")

# Add Google Maps Navigation Link
if "Latitude" in results.columns and "Longitude" in results.columns:
    results["Navigate"] = results.apply(lambda row: f'<a href="https://www.google.com/maps/search/?api=1&query={row["Latitude"]},{row["Longitude"]}" target="_blank">📍 Open in Maps</a>', axis=1)

# Apply Filters
if selected_source != "All":
    results = results[results["Source"] == selected_source]

if hide_nan_email:
    results = results[results["Email"].notna()]

if hide_nan_phone:
    results = results[results["Phone Number"].notna()]

# Display Filtered Results
st.write(results.to_html(escape=False, index=False), unsafe_allow_html=True)

# Map Display
if not results.empty:
    st.subheader("📍 Property Locations on Map")
    map_center = [results["Latitude"].mean(), results["Longitude"].mean()]
    m = folium.Map(location=map_center, zoom_start=6)

    for _, row in results.iterrows():
        folium.Marker(
            [row["Latitude"], row["Longitude"]],
            popup=f'<b>{row["Name"]}</b><br>{row["Address"]}<br><a href="{row["Property Link"]}" target="_blank">View Details</a>',
            tooltip=row["Name"]
        ).add_to(m)

    folium_static(m)

# Footer
st.markdown("<h4 style='text-align: center; color: #4CAF50;'>Powered by Belvilla</h4>", unsafe_allow_html=True)
