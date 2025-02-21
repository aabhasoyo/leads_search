import streamlit as st
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree
import base64

# Set Page Config
st.set_page_config(page_title="🏡 Discover Leads", layout="wide")

# Load dataset
@st.cache_data
def load_data():
    return pd.read_csv("properties.csv", encoding="ISO-8859-1")

data = load_data()

# Build KDTree for fast spatial search
def build_tree(df):
    coords = df[['Latitude', 'Longitude']].to_numpy()
    return cKDTree(coords), coords

tree, coords = build_tree(data)

# Title and Description
st.markdown("<h1 style='text-align: center; color: #4CAF50;'>Leads Search Portal</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center;'>Discover Leads Near You Effortlessly! 🔍</h3>", unsafe_allow_html=True)
st.divider()

# Floating Filters Button (Centered)
st.markdown("""
    <style>
        .floating-button {
            position: fixed;
            top: 15px;
            right: 20px;
            background-color: #4CAF50;
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            font-size: 16px;
            font-weight: bold;
            border: none;
            cursor: pointer;
            z-index: 999;
        }
        .floating-button:hover {
            background-color: #388E3C;
        }
    </style>
""", unsafe_allow_html=True)

# Create a placeholder for the button (opens filters)
filters_expander = st.expander("🔍 Filters", expanded=False)

# Filters inside Expander (Replaces Sidebar)
with filters_expander:
    st.subheader("🔎 Search & Filter Options")
    
    search_type = st.radio("Search by", ["📍 Latitude/Longitude", "🌍 Location"])

    if search_type == "📍 Latitude/Longitude":
        lat = st.number_input("Enter Latitude", value=46.94412, format="%f")
        lng = st.number_input("Enter Longitude", value=14.70255, format="%f")
        radius = st.slider("Search Radius (km)", 1, 50, 10)

        # Find nearest points
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

    st.write("Click outside the filters panel to close.")

# Display Results
st.markdown(f"<h3>✅ Found {len(results)} Properties</h3>", unsafe_allow_html=True)

# Display Data in a Table
st.dataframe(results)

# Export CSV Button
st.subheader("📤 Export & Share")
csv_data = results.to_csv(index=False).encode('utf-8')
b64 = base64.b64encode(csv_data).decode()
href = f'<a href="data:file/csv;base64,{b64}" download="filtered_results.csv">📥 Download CSV</a>'
st.markdown(href, unsafe_allow_html=True)

# Footer
st.markdown("<hr>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>🚀 Developed by Aabhas</p>", unsafe_allow_html=True)
