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

# Ensure sources is always defined
sources = data["Source"].unique().tolist() if "Source" in data.columns else []
selected_source = st.sidebar.selectbox("Filter by Source", ["All"] + sources, key="selected_source_filter")

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
    selected_source = st.sidebar.selectbox("Filter by Source", ["All"] + sources)
    hide_nan_email = st.sidebar.checkbox("Hide rows without Email")
    hide_nan_phone = st.sidebar.checkbox("Hide rows without Phone Number")

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

# Additional Filters
sources = sorted(data["Source"].dropna().unique())

# Sorting
sort_by = st.sidebar.selectbox("Sort results by", ["Distance (km)", "Rating", "Review Count"])
if sort_by in results.columns:
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
results["Navigate"] = results.apply(lambda row: f'<a href="https://www.google.com/maps/dir/?api=1&destination={row["Latitude"]},{row["Longitude"]}" target="_blank">🗺️ Open in Maps</a>' if pd.notna(row["Latitude"]) and pd.notna(row["Longitude"]) else "", axis=1)

st.markdown("""
    <style>
        table { width: 100%; border-collapse: collapse; border-radius: 8px; overflow: hidden; font-family: Arial, sans-serif; font-size: 14px; text-align: center !important; }
        th { background-color: #4CAF50; color: white; padding: 12px; text-align: center !important; vertical-align: middle !important; }
        td { padding: 10px; border-bottom: 1px solid #ddd; text-align: center !important; vertical-align: middle !important; }
        tr:hover { background-color: rgba(100, 100, 100, 0.4) !important; } /* Softer gray hover */
        
        a { color: #1E88E5; text-decoration: none; font-weight: bold; }
        a:hover { text-decoration: underline; }

        /* Dark Mode Handling */
        @media (prefers-color-scheme: dark) {
            table { color: #ddd; }  /* Light text in dark mode */
            th { background-color: #388E3C; } /* Darker green for dark mode */
            tr:hover { background-color: rgba(200, 200, 200, 0.2) !important; } /* Light gray hover for dark mode */
        }
    </style>
""", unsafe_allow_html=True)

# Display Table
# Ensure only existing columns are used
available_cols = [col for col in display_cols if col in results.columns]
styled_table = results[available_cols].to_html(escape=False, index=False)
st.markdown(styled_table, unsafe_allow_html=True)

# Export CSV Button
if not is_shared_view:
    st.subheader("📤 Export & Share")
    csv_data = results.to_csv(index=False).encode('utf-8')
    b64 = base64.b64encode(csv_data).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="filtered_results.csv">📥 Download CSV</a>'
    st.markdown(href, unsafe_allow_html=True)

    # Generate Shareable Link
    def generate_share_link():
        base_url = "https://leads-app.streamlit.app?"
        query_params = f"lat={lat}&lng={lng}&radius={radius}" if search_type == "📍 Latitude/Longitude" else f"country={country}&region={region}"
        return f"{base_url}{query_params}"

    share_link = generate_share_link()
    st.text_input("🔗 Shareable Link", share_link)

# Footer
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>🚀 Developed by Aabhas</p>", unsafe_allow_html=True)
