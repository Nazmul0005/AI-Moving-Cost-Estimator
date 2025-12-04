import streamlit as st
import requests
import json
from typing import Optional

# Page configuration
st.set_page_config(
    page_title="Moving Cost Estimator",
    page_icon="🚚",
    layout="wide"
)

# API Base URL
try:
    API_BASE_URL = st.secrets["API_BASE_URL"]
except:
    API_BASE_URL = "http://localhost:8000"

# ============================================
# CUSTOM CSS
# ============================================

st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .step-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .cost-card {
        background-color: #e8f4f8;
        padding: 2rem;
        border-radius: 10px;
        border: 2px solid #1f77b4;
    }
    .item-card {
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 5px;
        margin: 0.5rem 0;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# HEADER
# ============================================

st.markdown('<div class="main-header">🚚 AI Moving Cost Estimator</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Get instant moving estimates from your home video</div>', unsafe_allow_html=True)

# ============================================
# SESSION STATE INITIALIZATION
# ============================================

if 'inventory' not in st.session_state:
    st.session_state.inventory = None
if 'cost_estimate' not in st.session_state:
    st.session_state.cost_estimate = None
if 'stage' not in st.session_state:
    st.session_state.stage = 1

# ============================================
# STAGE 1: VIDEO ANALYSIS
# ============================================

st.markdown("---")
st.markdown("## 📹 Stage 1: Video Analysis")

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown('<div class="step-card">', unsafe_allow_html=True)
    
    # Video input method selection
    input_method = st.radio(
        "Choose video input method:",
        ["Upload Video File", "YouTube URL"],
        horizontal=True
    )
    
    video_file = None
    youtube_url = None
    
    if input_method == "Upload Video File":
        video_file = st.file_uploader(
            "Upload your home video",
            type=['mp4', 'avi', 'mov', 'webm'],
            help="Video showing all rooms and furniture in your home"
        )
    else:
        youtube_url = st.text_input(
            "Enter YouTube URL",
            placeholder="https://www.youtube.com/watch?v=..."
        )
    
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="step-card">', unsafe_allow_html=True)
    
    home_type = st.selectbox(
        "Home Type",
        ["apartment", "house"],
        index=0
    )
    
    room_count = st.number_input(
        "Number of Rooms",
        min_value=1,
        max_value=10,
        value=3
    )
    
    st.markdown('</div>', unsafe_allow_html=True)

# Analyze button
if st.button("🔍 Analyze Video", type="primary", use_container_width=True):
    if not video_file and not youtube_url:
        st.error("Please upload a video or enter a YouTube URL")
    else:
        with st.spinner("Analyzing video... This may take a moment ⏳"):
            try:
                url = f"{API_BASE_URL}/api/v1/analyze-video"
                
                if youtube_url:
                    # YouTube URL
                    data = {
                        'youtube_url': youtube_url,
                        'home_type': home_type,
                        'room_count': room_count
                    }
                    response = requests.post(url, data=data)
                else:
                    # Video file upload
                    files = {'video_file': video_file}
                    data = {
                        'home_type': home_type,
                        'room_count': room_count
                    }
                    response = requests.post(url, files=files, data=data)
                
                if response.status_code == 200:
                    st.session_state.inventory = response.json()
                    st.session_state.stage = 2
                    st.success("✅ Video analysis complete!")
                    st.rerun()
                else:
                    st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                    
            except Exception as e:
                st.error(f"Error connecting to API: {str(e)}")
                st.info("Make sure the FastAPI server is running on http://localhost:8000")

# ============================================
# DISPLAY INVENTORY RESULTS
# ============================================

if st.session_state.inventory:
    st.markdown("---")
    st.markdown("## 📦 Inventory Results")
    
    inventory = st.session_state.inventory
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Items", len(inventory['items']))
    
    with col2:
        st.metric("Total Volume", f"{inventory['total_volume_cubic_feet']} cu ft")
    
    with col3:
        st.metric("Special Items", len(inventory['needs_special_handling']))
    
    # Items list
    st.markdown("### Items Found")
    
    # Group items by category
    categories = {}
    for item in inventory['items']:
        cat = item['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)
    
    for category, items in categories.items():
        with st.expander(f"📂 {category.upper()} ({len(items)} items)", expanded=True):
            for item in items:
                st.markdown(f"""
                <div class="item-card">
                    <strong>{item['name']}</strong> 
                    | Qty: {item['quantity']} 
                    | Size: {item['size']}
                </div>
                """, unsafe_allow_html=True)
    
    # Special handling items
    if inventory['needs_special_handling']:
        st.warning(f"⚠️ Special handling required for: {', '.join(inventory['needs_special_handling'])}")

# ============================================
# STAGE 2: COST ESTIMATION
# ============================================

if st.session_state.stage >= 2 and st.session_state.inventory:
    st.markdown("---")
    st.markdown("## 💰 Stage 2: Cost Estimation")
    
    st.markdown('<div class="step-card">', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📍 Move Details")
        
        distance_km = st.number_input(
            "Distance (km)",
            min_value=1,
            max_value=1000,
            value=45,
            help="Distance between origin and destination"
        )
        
        origin_floor = st.number_input(
            "Origin Floor",
            min_value=1,
            max_value=50,
            value=3
        )
        
        has_elevator_origin = st.checkbox(
            "Origin has elevator",
            value=False
        )
    
    with col2:
        st.markdown("### 🏠 Destination Details")
        
        st.write("")  # Spacing
        st.write("")
        
        destination_floor = st.number_input(
            "Destination Floor",
            min_value=1,
            max_value=50,
            value=2
        )
        
        has_elevator_destination = st.checkbox(
            "Destination has elevator",
            value=True
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Calculate cost button
    if st.button("💵 Calculate Moving Cost", type="primary", use_container_width=True):
        with st.spinner("Calculating cost estimate... ⏳"):
            try:
                url = f"{API_BASE_URL}/api/v1/estimate-cost"
                
                payload = {
                    "items": st.session_state.inventory['items'],
                    "total_volume_cubic_feet": st.session_state.inventory['total_volume_cubic_feet'],
                    "needs_special_handling": st.session_state.inventory['needs_special_handling'],
                    "distance_km": distance_km,
                    "origin_floor": origin_floor,
                    "destination_floor": destination_floor,
                    "has_elevator_origin": has_elevator_origin,
                    "has_elevator_destination": has_elevator_destination
                }
                
                response = requests.post(url, json=payload)
                
                if response.status_code == 200:
                    st.session_state.cost_estimate = response.json()
                    st.success("✅ Cost estimate complete!")
                    st.rerun()
                else:
                    st.error(f"Error: {response.json().get('detail', 'Unknown error')}")
                    
            except Exception as e:
                st.error(f"Error connecting to API: {str(e)}")

# ============================================
# DISPLAY COST RESULTS
# ============================================

if st.session_state.cost_estimate:
    st.markdown("---")
    st.markdown("## 📊 Cost Breakdown")
    
    cost = st.session_state.cost_estimate
    
    # Main cost display
    st.markdown('<div class="cost-card">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("💵 Total Cost", f"${cost['total_cost']:,.2f}")
    
    with col2:
        st.metric("Cost Range", f"${cost['cost_range'][0]:,.2f} - ${cost['cost_range'][1]:,.2f}")
    
    with col3:
        st.metric("Estimated Time", f"{cost['estimated_hours']} hours")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Resources needed
    st.markdown("### 🚚 Resources Needed")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info(f"👷 **Movers Required:** {cost['movers_needed']} people")
    
    with col2:
        st.info(f"🚛 **Truck Type:** {cost['truck_type'].upper()}")
    
    # Cost breakdown chart
    st.markdown("### 💳 Detailed Breakdown")
    
    breakdown = cost['breakdown']
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Cost Components:**")
        for key, value in breakdown.items():
            st.write(f"- {key.replace('_', ' ').title()}: ${value:,.2f}")
    
    with col2:
        # Create a simple bar chart
        import pandas as pd
        df = pd.DataFrame({
            'Category': [k.replace('_', ' ').title() for k in breakdown.keys()],
            'Amount': list(breakdown.values())
        })
        st.bar_chart(df.set_index('Category'))
    
    # Special notes
    if cost.get('special_notes'):
        st.warning(f"📌 **Note:** {cost['special_notes']}")
    
    # Download report button
    if st.button("📥 Download Full Report", use_container_width=True):
        report = {
            "inventory": st.session_state.inventory,
            "cost_estimate": st.session_state.cost_estimate
        }
        
        st.download_button(
            label="Download JSON Report",
            data=json.dumps(report, indent=2),
            file_name="moving_estimate_report.json",
            mime="application/json"
        )

# ============================================
# RESET BUTTON
# ============================================

if st.session_state.inventory or st.session_state.cost_estimate:
    st.markdown("---")
    if st.button("🔄 Start New Estimate", use_container_width=True):
        st.session_state.inventory = None
        st.session_state.cost_estimate = None
        st.session_state.stage = 1
        st.rerun()

# ============================================
# FOOTER
# ============================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 2rem;">
    <p>🚚 AI Moving Cost Estimator | Powered by Gemini AI</p>
    <p><small>Estimates are based on AI analysis and may vary from actual costs</small></p>
</div>
""", unsafe_allow_html=True)