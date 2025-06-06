import streamlit as st
import pandas as pd
import folium
from streamlit_folium import folium_static
from scipy.spatial import cKDTree
import numpy as np
import base64
import urllib.parse

import streamlit as st
import pandas as pd
from pathlib import Path
# from oyoms import WorkbookClient

# Load data from OYO MS Excel
# @st.cache_data
# def load_data():
#     # SharePoint Excel link
#     excel_link = (
#         "https://oyoenterprise-my.sharepoint.com/:x:/g/personal/aabhas_agrawal_oyorooms_com/ESaDPGPAZlRAltmi70oKMyEBxKh5geE_bykJIy7Fv2qBiQ?e=UfOGFe"
#     )

#     # Initialize workbook client
#     wb = WorkbookClient("aabhas.agrawal@oyorooms.com", excel_link)

#     # Read Excel data (modify sheet name/range if needed)
#     df = wb.get_range_data("Sheet1", "Sheet1!A1:O16000")

#     return df

@st.cache_data
def load_data():
    return pd.read_csv("properties.csv", encoding="ISO-8859-1")

data = load_data()

# If lead_status column doesn't exist, add it
if 'lead_status' not in data.columns:
    data['lead_status'] = 'Not Reviewed'
    data.to_csv("properties.csv", index=False)


# Build KDTree for fast spatial search
def build_tree(data):
    coords = data[['Latitude', 'Longitude']].to_numpy()
    return cKDTree(coords), coords

tree, coords = build_tree(data)

# Check if the user came from a shareable link
query_params = st.query_params.to_dict()
shared_mode = "shared" in query_params  # Example: ?shared=true in URL

# Ensure authentication state exists
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False  # Default to False

if shared_mode:
    st.session_state.authenticated = True  # Allow access from a shared link

    # Populate session state with URL parameters
    if "lat" in query_params:
        st.session_state["lat"] = float(query_params["lat"])
    if "lng" in query_params:
        st.session_state["lng"] = float(query_params["lng"])
    if "radius" in query_params:
        st.session_state["radius"] = int(query_params["radius"])
    if "country" in query_params:
        st.session_state["country"] = query_params["country"]
    if "region" in query_params:
        st.session_state["region"] = query_params["region"]

    # Set search type based on which parameters exist
    if "lat" in query_params and "lng" in query_params:
        st.session_state["search_type"] = "📍 Latitude/Longitude"
    elif "country" in query_params:
        st.session_state["search_type"] = "🌍 Location"

# If not shared mode and not authenticated, show login form
if not shared_mode and not st.session_state.authenticated:
    st.set_page_config(page_title="🏡 Discover Leads", layout="wide")
    
    st.markdown("<h2 style='text-align: center;'>🔑 Login to Access Leads</h2>", unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Enter username")
    password = st.text_input("Password", type="password", placeholder="Enter password")

    VALID_CREDENTIALS = {
    "kapilraina": "kapil123",
    "aabhas": "aabhas123",
    "admin": "password123"
    }

    if st.button("Login"):
        if username in VALID_CREDENTIALS and password == VALID_CREDENTIALS[username]:
            st.session_state.authenticated = True
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Invalid username or password")

    st.stop()  # Prevent further execution for unauthenticated users

# Set Page Config after authentication
st.set_page_config(page_title="🏡 Discover Leads", layout="wide")

# Initialize session state for authentication
if not st.session_state.authenticated:
    # Check if the user came from a shareable link
    query_params = st.query_params.to_dict()
    if "shared" in query_params:  # Example: ?shared=true in URL
        st.session_state.authenticated = True  # Allow access from a shared link

if not st.session_state.authenticated:
    st.warning("Please authenticate to view leads.")
    st.stop()

# Authentication form
import streamlit as st
import urllib.parse

query_params = st.query_params
shared_mode = bool(query_params)  # If URL has params, it's a shared link

if shared_mode:
    # Load data if not already defined
    if "data" not in globals():
        import pandas as pd
        data = pd.read_csv("properties.csv", encoding="ISO-8859-1")  # Update with correct file path

    # Extract query parameters using the updated method
    query_params = st.query_params.to_dict()
    
    results = pd.DataFrame()  # Ensure results is always defined

    if "lat" in query_params and "lng" in query_params:
        lat = float(query_params.get("lat", 0))
        lng = float(query_params.get("lng", 0))
        radius = float(query_params.get("radius", 10))
        
        query_point = np.array([lat, lng])

        # 🔹 Ensure `tree` is initialized before using it
        if "tree" not in globals():
            from scipy.spatial import KDTree
            coordinates = data[["Latitude", "Longitude"]].dropna().values
            tree = KDTree(coordinates)

        distances, indices = tree.query(query_point, k=10, distance_upper_bound=radius / 111)
        indices = indices[distances != np.inf]
        results = data.iloc[indices].copy()
        results["Distance (km)"] = np.round(distances[distances != np.inf] * 111, 2)
        results.sort_values(by="Distance (km)", inplace=True)

    if "country" in query_params:
        country = query_params.get("country", "")
        region = query_params.get("region", "All")

        # region = query_params.get("region", ["All"])[0]

        results = data[data["Country"] == country].copy() if region == "All" else data[
        (data["Country"] == country) & (data["Region"] == region)
        ]

    # If filters exist for Source, Email, or Phone
    if "source" in query_params:
        selected_source = query_params["source"][0]
        if selected_source != "All":
            results = results[results["Source"] == selected_source]

    if "hide_nan_email" in query_params and query_params["hide_nan_email"][0] == "true":
        results = results[results["Email"].notna()]

    if "hide_nan_phone" in query_params and query_params["hide_nan_phone"][0] == "true":
        results = results[results["Phone Number"].notna()]

if not shared_mode and not st.session_state.authenticated:
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

if not shared_mode:
    st.sidebar.header("🔎 Search & Filter Options")

    search_type = st.sidebar.radio("Search by", ["📍 Latitude/Longitude", "🌍 Location"])
    st.session_state["search_type"] = search_type  # Store search type

    if search_type == "📍 Latitude/Longitude":
        lat = st.sidebar.number_input("Enter Latitude", value=46.94412, format="%f")
        lng = st.sidebar.number_input("Enter Longitude", value=14.70255, format="%f")
        radius = st.sidebar.slider("Search Radius (km)", 1, 50, 10)

        # Store in session state
        st.session_state["lat"] = lat
        st.session_state["lng"] = lng
        st.session_state["radius"] = radius

        query_point = np.array([lat, lng])
        distances, indices = tree.query(query_point, k=10, distance_upper_bound=radius / 111)
        indices = indices[distances != np.inf]
        results = data.iloc[indices].copy()
        results["Distance (km)"] = np.round(distances[distances != np.inf] * 111, 2)
        results.sort_values(by="Distance (km)", inplace=True)

    elif search_type == "🌍 Location":
        country = st.sidebar.selectbox("🌎 Select Country", sorted(data["Country"].dropna().unique()))
        region_options = ["All"] + sorted(data[data["Country"] == country]["Region"].dropna().unique())
        region = st.sidebar.selectbox("🏙️ Select Region", region_options)

        # Store in session state
        st.session_state["country"] = country
        st.session_state["region"] = region

        results = data[data["Country"] == country].copy() if region == "All" else data[
            (data["Country"] == country) & (data["Region"] == region)
        ]
        
    # Additional Filters
    sources = sorted(data["Source"].dropna().unique())
    selected_source = st.sidebar.selectbox("Filter by Source", ["All"] + sources)
    hide_nan_email = st.sidebar.checkbox("Hide rows without Email")
    hide_nan_phone = st.sidebar.checkbox("Hide rows without Phone Number")
    
    # Sorting
    sort_by = st.sidebar.selectbox("Sort results by", ["Distance (km)", "Rating", "Review Count"])
    if sort_by in results.columns:
        results = results.sort_values(by=sort_by, ascending=(sort_by != "Rating"))

# Display Results
if shared_mode:
    st.markdown(f"<h2>📌 Shared {len(results)} Leads</h2>", unsafe_allow_html=True)
else:
    st.markdown(f"<h2>✅ Found {len(results)} Properties</h2>", unsafe_allow_html=True)

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
            td { colour:white; }
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
st.subheader("📤 Export & Share")
csv_data = results.to_csv(index=False).encode('utf-8')
b64 = base64.b64encode(csv_data).decode()
href = f'<a href="data:file/csv;base64,{b64}" download="filtered_results.csv" style="display: inline-block; padding: 5px 10px; font-size: 16px; font-weight: bold; color: white; background-color: #ff4b4b; text-decoration: none; border-radius: 5px; text-align: center;">⬇ Download CSV</a>'
st.markdown(href, unsafe_allow_html=True)

# Function to generate shareable link
def generate_share_link():
    base_url = "https://oyoleads.streamlit.app/?" 
    params = {}

    # Retrieve values from session state
    search_type = st.session_state.get("search_type")

    if search_type == "📍 Latitude/Longitude":
        lat = st.session_state.get("lat")
        lng = st.session_state.get("lng")
        radius = st.session_state.get("radius")

        if lat and lng and radius:
            params["lat"] = lat
            params["lng"] = lng
            params["radius"] = radius

    elif search_type == "🌍 Location":
        country = st.session_state.get("country")
        region = st.session_state.get("region")

        if country:
            params["country"] = country
        if region and region != "All":
            params["region"] = region

    if not params:
        return None 

    return base_url + urllib.parse.urlencode(params, doseq=True)

# Generate shareable link
share_link = generate_share_link()

if share_link:
    share_link = f"{share_link}&shared=true"  # ✅ Ensuring correct link format

    # Display shareable link
    st.markdown("### 🔗 Your Shareable Link")
    st.code(share_link, language="markdown")  # ✅ Neat display
else:
    st.warning("⚠️ No valid filters selected to generate a shareable link.")
    
# st.write("Debug:", st.session_state)  # Debugging info

    
# Footer
st.markdown("""
    <hr>
    <p style='text-align: center; font-size: 14px; margin-bottom: 2px;'>🚀 Powered by <strong>Belvilla</strong></p>
    <p style='text-align: center; font-size: 11px; color: gray; margin-top: -5px; opacity: 0.8;'>&nbsp;&nbsp;⚡Developed by Aabhas</p>
""", unsafe_allow_html=True)

