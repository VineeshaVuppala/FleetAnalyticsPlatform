import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Fleet Analysis Platform", layout="wide")
st.title("Fleet Operations Data Analysis")

st.sidebar.header("📂 Upload Your Fleet Data File")

# Upload the Excel file
excel_file = st.sidebar.file_uploader("Upload Excel File with All Sheets (Trips, Vehicles, Drivers, etc.)", type=["xlsx"])

@st.cache_data
def load_excel_sheets(file):
    xls = pd.ExcelFile(file)
    sheets = {sheet_name: xls.parse(sheet_name) for sheet_name in xls.sheet_names}
    return sheets

if excel_file:
    data = load_excel_sheets(excel_file)

    # Extract sheets into individual dataframes
    trips_df = data.get('Trips')
    vehicles_df = data.get('Vehicles')
    drivers_df = data.get('Drivers')
    hubs_df = data.get('Hubs')
    clients_df = data.get('Clients')

    # Preprocess Trips
    if trips_df is not None:
        trips_df['Trip Date'] = pd.to_datetime(trips_df['Trip Date'], errors='coerce')
        trips_df['Start Time'] = pd.to_datetime(trips_df['Start Time'], errors='coerce')
        trips_df['End Time'] = pd.to_datetime(trips_df['End Time'], errors='coerce')
        trips_df['Trip DateTime'] = pd.to_datetime(trips_df['Trip Date'].dt.strftime('%Y-%m-%d') + ' ' + trips_df['Start Time'].dt.strftime('%H:%M:%S'), errors='coerce')
        trips_df['Duration (hrs)'] = (trips_df['End Time'] - trips_df['Start Time']).dt.total_seconds() / 3600

    st.sidebar.success("✅ All sheets loaded!")
    st.subheader("📊 Select analysis type from the sidebar")

    analysis_option = st.sidebar.selectbox(
        "Select Analysis Type",
        [
            "Underutilized vehicles",
            "Allocated vs available vehicles",
            "High idle time (vehicle or driver)",
            "Peak usage hours or days",
            "High/low driver trip counts",
            "Long trip vs expected duration"
        ]
    )


    # 1. Underutilized vehicles
    if analysis_option == "Underutilized vehicles":
        st.info("Analyze vehicles with low utilization based on trip count or distance.")

        # User input for selection and thresholds
        metric_option = st.radio("Select metric for short-term analysis:", ["Trip Count", "Distance"], horizontal=True)

        if metric_option == "Trip Count":
            trip_threshold = st.number_input("Enter minimum trips threshold (suggested: 3)", value=3, min_value=0)
            distance_threshold = None  # Not used
        else:
            distance_threshold = st.number_input("Enter minimum distance threshold in km (suggested: 100)", value=100, min_value=0)
            trip_threshold = None  # Not used

        # Filter recent trips
        date_cutoff = datetime.now() - timedelta(days=7)
        recent_trips = trips_df[trips_df['Trip Date'] >= date_cutoff]

        summary = recent_trips.groupby('Vehicle ID').agg({
            'Trip ID': 'count',
            'Distance': 'sum'
        }).reset_index().rename(columns={'Trip ID': 'Trips (7 days)', 'Distance': 'Distance (7 days)'})

        st.subheader("📉 Underutilized Vehicles (Last 7 Days)")

        # Conditional filtering based on selected metric
        if metric_option == "Trip Count":
            filtered = summary[summary['Trips (7 days)'] < trip_threshold]
            st.markdown(f"Showing vehicles with **< {trip_threshold} trips** in the last 7 days.")
        else:
            filtered = summary[summary['Distance (7 days)'] < distance_threshold]
            st.markdown(f"Showing vehicles with **< {distance_threshold} km** distance covered in the last 7 days.")

        st.dataframe(filtered)
        st.download_button("📥 Download CSV (7-day)", filtered.to_csv(index=False), "underutilized_7days.csv")

        st.markdown("---")


        # Long-term utilization analysis
        st.subheader("📊 Consistent Underutilization Over Time")

        trips_df['Trip Date'] = pd.to_datetime(trips_df['Trip Date'])
        full_summary = trips_df.groupby('Vehicle ID').agg({
            'Trip ID': 'count',
            'Distance': 'sum',
            'Trip Date': ['min', 'max']
        })

        full_summary.columns = ['Total Trips', 'Total Distance (km)', 'First Trip Date', 'Last Trip Date']
        full_summary = full_summary.reset_index()

        # Compute days active and avg trips/week
        full_summary['Days Active'] = (full_summary['Last Trip Date'] - full_summary['First Trip Date']).dt.days + 1
        full_summary['Avg Trips/Week'] = full_summary['Total Trips'] / (full_summary['Days Active'] / 7)

        # Remove very new vehicles (e.g., active < 28 days)
        filtered_summary = full_summary[full_summary['Days Active'] >= 28]

        # Compute fleet average trips/week
        fleet_avg = filtered_summary['Avg Trips/Week'].mean()

        # Mark underutilized vehicles
        filtered_summary['Status'] = filtered_summary['Avg Trips/Week'].apply(
            lambda x: 'Underutilized' if x < fleet_avg else 'Utilized'
        )

        # Mark "Too New" in original summary
        full_summary['Status'] = full_summary.apply(
            lambda row: 'Too New' if row['Days Active'] < 28 else (
                'Underutilized' if row['Avg Trips/Week'] < fleet_avg else 'Utilized'
            ), axis=1
        )

        st.dataframe(full_summary[['Vehicle ID', 'Days Active', 'Total Trips', 'Avg Trips/Week', 'Status']])
        st.download_button("📥 Download CSV (Long-term)", full_summary.to_csv(index=False), "underutilized_longterm.csv")

        st.markdown(f"**ℹ️ Vehicles with < average trips/week ({fleet_avg:.2f}) over at least 28 days are considered underutilized.**")

        st.markdown("---")

        # Histogram of trip count
        st.subheader("📈 Trip Count Distribution")
        fig = px.histogram(full_summary, x='Total Trips', nbins=20, title="Distribution of Total Trips per Vehicle")
        fig.add_vline(x=full_summary['Total Trips'].mean(), line_dash='dash', line_color='red',
                    annotation_text='Fleet Avg', annotation_position='top right')
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**This chart shows how many trips each vehicle made. Those far left of the average are likely underutilized unless they're newly added.**")


    # 2. Allocated vs available vehicles
    elif analysis_option == "Allocated vs available vehicles":
        allocated = vehicles_df[vehicles_df['Status'].str.lower() == 'allocated']
        available = vehicles_df[vehicles_df['Status'].str.lower() == 'available']

        st.metric("Allocated Vehicles", len(allocated))
        st.metric("Available Vehicles", len(available))

        usage = trips_df.groupby('Vehicle ID').size().reset_index(name='Trip Count')
        merged = pd.merge(vehicles_df, usage, on='Vehicle ID', how='left').fillna(0)
        st.dataframe(merged[['Vehicle ID', 'Status', 'Trip Count']])

        pct = (len(allocated) / max(len(available), 1)) * 100
        st.write(f"**Allocated vs Available Ratio:** {pct:.2f}%")

    # 3. High idle time (vehicle or driver)
    elif analysis_option == "High idle time (vehicle or driver)":
        trips_sorted = trips_df.sort_values(['Vehicle ID', 'Trip DateTime'])
        trips_sorted['Idle Time (hrs)'] = trips_sorted.groupby('Vehicle ID')['Trip DateTime'].diff().dt.total_seconds() / 3600
        high_idle = trips_sorted[trips_sorted['Idle Time (hrs)'] > 6]
        st.dataframe(high_idle[['Vehicle ID', 'Trip ID', 'Idle Time (hrs)']].dropna())
        st.write("Idle time greater than 6 hours between trips.")

    # 4. Peak usage hours or days
    elif analysis_option == "Peak usage hours or days":
        trips_df['Hour'] = trips_df['Trip DateTime'].dt.hour
        trips_df['Day of Week'] = trips_df['Trip DateTime'].dt.day_name()

        hour_fig = px.histogram(trips_df, x='Hour', title="Trips by Hour of Day")
        day_fig = px.histogram(trips_df, x='Day of Week', 
                               category_orders={'Day of Week': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']},
                               title="Trips by Day of Week")

        st.plotly_chart(hour_fig, use_container_width=True)
        st.plotly_chart(day_fig, use_container_width=True)

    # 5. High/low driver trip counts
    elif analysis_option == "High/low driver trip counts":
        driver_stats = trips_df.groupby('Driver ID').agg({
            'Trip ID': 'count',
            'Duration (hrs)': 'sum'
        }).reset_index().rename(columns={'Trip ID': 'Trip Count', 'Duration (hrs)': 'Duty Hours'})

        top_10 = driver_stats.sort_values(by='Trip Count', ascending=False).head(10)
        bottom_10 = driver_stats.sort_values(by='Trip Count').head(10)

        st.subheader("Top 10 Drivers by Trips")
        st.dataframe(top_10)
        st.subheader("Bottom 10 Drivers by Trips")
        st.dataframe(bottom_10)

    # 6. Long trip vs expected duration
    elif analysis_option == "Long trip vs expected duration":
        trips_df['Expected Duration (hrs)'] = trips_df['Distance'] / 40  # Assuming average speed = 40 km/h
        trips_df['Speed (km/h)'] = trips_df['Distance'] / trips_df['Duration (hrs)']
        long_trips = trips_df[trips_df['Speed (km/h)'] < 10]

        st.dataframe(long_trips[['Trip ID', 'Vehicle ID', 'Distance', 'Duration (hrs)', 'Expected Duration (hrs)', 'Speed (km/h)']])
        st.write("Trips where actual speed < 10 km/h (possibly delayed or stuck).")
