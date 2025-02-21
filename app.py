import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from scipy.spatial import cKDTree
import numpy as np

# Set Page Config
st.set_page_config(page_title="🏡 Discover Leads", layout="wide")

# Load dataset
@st.cache_data
def load_data():
    return pd.read_csv("properties.csv", encoding="ISO-8859-1")

data = load_data()

# Build KDTree for fast spatial search
def build_tree(data):
    coords = data[['Latitude', 'Longitude']].dropna().to_numpy()  # Ensure NaN values are removed
    return cKDTree(coords), coords

tree, coords = build_tree(data)

# Sidebar Filters
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

# Perform search
results = pd.DataFrame()  # Ensure results is always initialized

if search_type == "📍 Latitude/Longitude":
    query_point = np.array([lat, lng])
    distances, indices = tree.query(query_point, k=10, distance_upper_bound=radius / 111)
    indices = indices[distances != np.inf]  # Remove invalid results
    results = data.iloc[indices].copy()
    results["Distance (km)"] = np.round(distances[distances != np.inf] * 111, 2)
    results.sort_values(by="Distance (km)", inplace=True)

elif search_type == "🌍 Location":
    if region == "All":
        results = data[data["Country"] == country].copy()
    else:
        results = data[(data["Country"] == country) & (data["Region"] == region)].copy()

# Display Results
st.markdown(f"<h3>✅ Found {len(results)} Properties</h3>", unsafe_allow_html=True)

# Display Table
if not results.empty:
    st.dataframe(results)

# Map Display
if not results.empty and "Latitude" in results.columns and "Longitude" in results.columns:
    st.subheader("📍 Property Locations on Map")
    map_center = [results["Latitude"].mean(), results["Longitude"].mean()]
    m = folium.Map(location=map_center, zoom_start=6)

    for _, row in results.iterrows():
        folium.Marker(
            [row["Latitude"], row["Longitude"]],
            popup=row.get("Name", "Unknown"),
            tooltip=row.get("Name", "Unknown")
        ).add_to(m)

    folium_static(m)
