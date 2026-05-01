import pandas as pd
import streamlit as st
import plotly.express as px
import folium
from folium.plugins import MarkerCluster, MousePosition
import gspread
from google.oauth2.service_account import Credentials
import leafmap.foliumap as leafmap

# Setup page config
st.set_page_config(page_title="QoE SIGMON", page_icon="📊", layout="wide")

# Apply CSS styling
st.markdown(
    """
    <style>
    /* Base styles */
    div.stMultiSelect > label {
        background-color: #e1f5fe !important;
        padding: 5px;
        border-radius: 3px;
    }
    .stMultiSelect .css-15tx2eq {
        background-color: #4CAF50 !important;
        color: white !important;
    }
    .stMultiSelect .css-15tx2eq:hover {
        background-color: #367c39 !important;
    }
    
    /* Test type header colors */
    .route-test-header {
        background-color: #e0b0ff;
        padding: 5px 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: bold;
        color: #000;
    }
    .static-test-header {
        background-color: #ffc04d;
        padding: 5px 10px;
        border-radius: 5px;
        margin-bottom: 10px;
        font-weight: bold;
        color: #000;
    }
    
    /* Map styles */
    .leaflet-container {
        height: 500px !important;
        width: 100% !important;
    }
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.4; }
        100% { opacity: 1; }
    }
    .marker-pulse {
        animation: pulse 1.5s infinite;
    }
    
    /* Highlight styles */
    .highlight-best {
        background-color: #e6f4ea;
        padding: 3px 5px;
        border-radius: 3px;
        border-left: 3px solid #0f9d58;
    }
    .highlight-worst {
        background-color: #fce8e6;
        padding: 3px 5px;
        border-radius: 3px;
        border-left: 3px solid #d93025;
    }
    
    /* Coordinate display */
    .coordinate-display {
        background-color: rgba(255, 255, 255, 0.8);
        border-radius: 4px;
        padding: 4px 8px;
        font-weight: bold;
        color: #333;
        border: 1px solid #ccc;
    }
    .coords-highlight {
        background-color: #f0f0f0;
        border-left: 3px solid #2196F3;
        padding: 3px 6px;
        margin-top: 4px;
        font-weight: bold;
        font-family: monospace;
    }
    
    /* Container styles */
    .filter-container {
        border: 1px solid #ddd;
        border-radius: 5px;
        padding: 10px;
        margin-bottom: 15px;
    }
    .highlight {
        background-color: #f5f5f5;
        padding: 15px;
        border-radius: 5px;
        border-left: 4px solid #4CAF50;
        margin-top: 20px;
        margin-bottom: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Define color map for operators
OPERATOR_COLORS = {
    'Telkomsel': 'red',
    'XL Axiata': 'blue',
    'IOH': 'yellow'
}

# Operator list
OPERATORS = ['Telkomsel', 'IOH', 'XL Axiata']

# ====== UTILITY FUNCTIONS ======

def format_coordinates(lat, lon, format_type="decimal"):
    """Format coordinates as decimal or DMS"""
    if pd.isna(lat) or pd.isna(lon):
        return "Koordinat tidak tersedia"
    
    if format_type == "decimal":
        return f"{lat:.6f}, {lon:.6f}"
    else:  # DMS format
        lat_dms = decimal_to_dms(abs(lat)) + ("S" if lat < 0 else "N")
        lon_dms = decimal_to_dms(abs(lon)) + ("W" if lon < 0 else "E")
        return f"{lat_dms}, {lon_dms}"

def decimal_to_dms(decimal_coord):
    """Convert decimal coordinates to DMS format"""
    degrees = int(decimal_coord)
    minutes_float = (decimal_coord - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    return f"{degrees}°{minutes}'{seconds:.2f}\""

@st.cache_resource
def get_gsheet_credentials():
    """Get Google Sheets API credentials"""
    # Check if credentials are in Streamlit secrets
    if 'gcp_service_account' in st.secrets:
        credentials = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
        )
        return credentials
    else:
        # Allow user to upload credentials file
        try:
            credentials = Credentials.from_service_account_file(
                'credentials.json',
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
            return credentials
        except FileNotFoundError:
            st.warning("File kredensial Google API tidak ditemukan.")
            credentials_file = st.file_uploader(
                "Unggah file kredensial Google API (credentials.json)", 
                type=["json"], 
                key="credential_uploader"
            )
            if credentials_file is not None:
                import json
                creds_dict = json.loads(credentials_file.getvalue().decode())
                credentials = Credentials.from_service_account_info(
                    creds_dict,
                    scopes=[
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive"
                    ]
                )
                return credentials
            return None

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data_from_sheets(sheet_id, sheet_name="Sheet1"):
    """Load data from Google Sheets and process it"""
    credentials = get_gsheet_credentials()
    if credentials is None:
        st.error("Kredensial Google API diperlukan untuk mengakses data.")
        return None
    
    try:
        # Initialize gspread client
        gc = gspread.authorize(credentials)
        
        # Open spreadsheet by ID
        sh = gc.open_by_key(sheet_id)
        
        # Select worksheet by name
        worksheet = sh.worksheet(sheet_name)
        
        # Get all values and headers
        data = worksheet.get_all_records()
        
        # Convert to pandas DataFrame
        df = pd.DataFrame(data)
        
        # Process the DataFrame
        if df.empty:
            return None
            
        # Process coordinates
        if 'Latitude' in df.columns and 'Longitude' in df.columns:
            # Convert to numeric, handling both text and numbers
            df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
            df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
            
            # Add formatted coordinate columns
            df['Koordinat'] = df.apply(
                lambda row: format_coordinates(row['Latitude'], row['Longitude'], "decimal"), 
                axis=1
            )
            
            df['Koordinat_DMS'] = df.apply(
                lambda row: format_coordinates(row['Latitude'], row['Longitude'], "dms"), 
                axis=1
            )
        
        # Process date column
        if 'Tanggal' in df.columns:
            df['Tanggal'] = pd.to_datetime(df['Tanggal'], errors='coerce')
            df['Bulan'] = df['Tanggal'].dt.strftime('%B %Y')
            df['Tanggal_str'] = df['Tanggal'].dt.strftime('%d-%m-%Y')
        
        # Process operator columns - convert to appropriate types
        for operator in OPERATORS:
            if operator in df.columns:
                # Try to convert to numeric, but keep text values if conversion fails
                try:
                    # First attempt to replace common text representations
                    df[operator] = df[operator].replace(['Excellent', 'Good', 'Fair', 'Poor'], [4, 3, 2, 1])
                    # Then convert to numeric, keeping text values
                    df[operator] = pd.to_numeric(df[operator], errors='ignore')
                except:
                    pass  # Keep as is if conversion fails
        
        return df
        
    except Exception as e:
        st.error(f"Error saat mengakses Google Sheets: {str(e)}")
        return None

@st.cache_data(ttl=600)  # Cache for 10 minutes
def get_available_spreadsheets():
    """Get list of available Google Sheets"""
    credentials = get_gsheet_credentials()
    if credentials is None:
        return []
    
    try:
        gc = gspread.authorize(credentials)
        spreadsheets = gc.list_spreadsheet_files()
        return [(sheet['id'], sheet['name']) for sheet in spreadsheets]
    except Exception as e:
        st.error(f"Error saat mendapatkan daftar spreadsheet: {str(e)}")
        return []

@st.cache_data(ttl=600)  # Cache for 10 minutes
def get_worksheet_names(sheet_id):
    """Get list of worksheets in a spreadsheet"""
    credentials = get_gsheet_credentials()
    if credentials is None:
        return []
    
    try:
        gc = gspread.authorize(credentials)
        sh = gc.open_by_key(sheet_id)
        return [worksheet.title for worksheet in sh.worksheets()]
    except Exception as e:
        st.error(f"Error saat mendapatkan daftar worksheet: {str(e)}")
        return []

# ====== DATA VISUALIZATION FUNCTIONS ======

def create_barchart(df, parameter, title):
    """Create bar chart comparing operators for a specific parameter"""
    if df.empty or parameter not in df['Parameter'].values:
        st.write(f"Tidak ada data untuk {title}.")
        return None
    
    try:
        # Filter data for selected parameter
        df_param = df[df['Parameter'] == parameter]
        
        # Define columns to keep in melted dataframe
        id_vars = ['Alamat', 'Tanggal', 'Bulan', 'Jenis Pengukuran', 'Parameter', 
                  'Tanggal_str', 'Latitude', 'Longitude', 'Koordinat', 'Koordinat_DMS']
        
        # Add 'Kabupaten/Kota' if it exists
        if 'Kabupaten/Kota' in df.columns:
            id_vars.append('Kabupaten/Kota')
        
        # Filter operator columns that exist in the dataframe
        value_vars = [op for op in OPERATORS if op in df.columns]
        
        if not value_vars:
            st.write(f"Tidak ada kolom operator yang valid untuk {title}.")
            return None
        
        # Ensure operator columns are numeric where possible
        for op in value_vars:
            if op in df_param.columns:
                # Try to convert to numeric, preserve text values
                df_param[op] = pd.to_numeric(df_param[op], errors='ignore')
        
        # Reshape the dataframe for plotting
        df_plot = df_param.melt(
            id_vars=id_vars,
            value_vars=value_vars,
            var_name='Operator',
            value_name='Nilai'
        )
        
        if df_plot.empty:
            st.write(f"Tidak ada data untuk {title} setelah transformasi.")
            return None
        
        # Create color map
        color_discrete_map = {op: OPERATOR_COLORS.get(op, 'gray') for op in value_vars}
        
        # Create bar chart
        fig = px.bar(
            df_plot, 
            x='Alamat', 
            y='Nilai', 
            color='Operator', 
            barmode='group',
            title=f"{parameter} ({title})",
            hover_data=['Operator', 'Alamat', 'Tanggal_str', 'Nilai', 'Koordinat'],
            color_discrete_map=color_discrete_map
        )
        
        # Adjust layout
        fig.update_layout(
            xaxis_title="Lokasi",
            yaxis_title=parameter,
            legend_title="Operator"
        )
        
        # Display the chart
        st.plotly_chart(fig)
        
        # Show highest and lowest values
        try:
            # Get coordinate display format
            coord_format = st.session_state.get('coord_format_radio_sidebar', "Desimal (DD.DDDDDD)")
            
            # Filter to numeric values only for max/min analysis
            df_plot_numeric = df_plot[pd.to_numeric(df_plot['Nilai'], errors='coerce').notna()]
            
            if not df_plot_numeric.empty:
                # Find highest value
                max_idx = df_plot_numeric['Nilai'].idxmax()
                max_row = df_plot_numeric.loc[max_idx]
                
                # Find lowest value
                min_idx = df_plot_numeric['Nilai'].idxmin()
                min_row = df_plot_numeric.loc[min_idx]
                
                # Display highest value info
                st.markdown(f"**Nilai {parameter} Tertinggi:** {max_row['Operator']} di lokasi {max_row['Alamat']} ({max_row['Nilai']})")
                
                # Show coordinates in selected format
                coord_field = 'Koordinat' if coord_format == "Desimal (DD.DDDDDD)" else 'Koordinat_DMS'
                st.markdown(f"**Koordinat:** {max_row[coord_field]}")
                
                # Display lowest value info
                st.markdown(f"**Nilai {parameter} Terendah:** {min_row['Operator']} di lokasi {min_row['Alamat']} ({min_row['Nilai']})")
                st.markdown(f"**Koordinat:** {min_row[coord_field]}")
            else:
                st.info("Tidak dapat menentukan nilai tertinggi dan terendah.")
        except Exception as e:
            st.info(f"Nilai tertinggi dan terendah tidak dapat ditentukan: {str(e)}")
        
        return df_plot
    except Exception as e:
        st.error(f"Error saat membuat grafik {title}: {str(e)}")
        return None

def create_location_comparison(df, parameter, test_type):
    """Create comparison table showing best and worst locations per operator"""
    if df.empty or parameter not in df['Parameter'].values:
        return None
    
    try:
        df_param = df[df['Parameter'] == parameter].copy()
        
        # Prepare data structure for comparison
        comparison_data = []
        
        # Get coordinate format preference
        coord_format = st.session_state.get('coord_format_radio_sidebar', "Desimal (DD.DDDDDD)")
        coord_field = 'Koordinat' if coord_format == "Desimal (DD.DDDDDD)" else 'Koordinat_DMS'
        
        # Process each operator
        for op in [op for op in OPERATORS if op in df_param.columns]:
            # Get data for this operator
            op_data = df_param[['Alamat', 'Tanggal_str', 'Latitude', 'Longitude', 
                               'Koordinat', 'Koordinat_DMS', op]].copy()
            
            # Convert to numeric where possible, preserving text values
            op_data[op] = pd.to_numeric(op_data[op], errors='coerce')
            
            # Drop rows with NA values
            op_data_clean = op_data.dropna(subset=[op])
            
            if not op_data_clean.empty:
                try:
                    # Find highest value
                    max_idx = op_data_clean[op].idxmax()
                    max_row = op_data_clean.loc[max_idx]
                    
                    # Find lowest value
                    min_idx = op_data_clean[op].idxmin()
                    min_row = op_data_clean.loc[min_idx]
                    
                    # Add comparison data
                    comparison_data.append({
                        'Operator': op,
                        'Parameter': parameter,
                        'Jenis Test': test_type,
                        'Nilai Tertinggi': max_row[op],
                        'Lokasi Tertinggi': max_row['Alamat'],
                        'Koordinat Tertinggi': max_row[coord_field],
                        'Tanggal Tertinggi': max_row['Tanggal_str'],
                        'Nilai Terendah': min_row[op],
                        'Lokasi Terendah': min_row['Alamat'],
                        'Koordinat Terendah': min_row[coord_field],
                        'Tanggal Terendah': min_row['Tanggal_str']
                    })
                except Exception as e:
                    st.warning(f"Error saat menganalisis data operator {op}: {str(e)}")
        
        return pd.DataFrame(comparison_data) if comparison_data else None
    except Exception as e:
        st.error(f"Error saat membuat perbandingan lokasi: {str(e)}")
        return None

def create_combined_map(df_route, df_static, param_route, param_static):
    """Create a map displaying both Route Test and Static Test data"""
    # Check if there's data to display
    has_route_data = not df_route.empty and param_route in df_route['Parameter'].values
    has_static_data = not df_static.empty and param_static in df_static['Parameter'].values
   
    if not has_route_data and not has_static_data:
        st.write("Tidak ada data untuk ditampilkan pada peta.")
        return None
   
    # Filter data by selected parameters
    df_route_map = df_route[df_route['Parameter'] == param_route] if has_route_data else pd.DataFrame()
    df_static_map = df_static[df_static['Parameter'] == param_static] if has_static_data else pd.DataFrame()
   
    # Combine data to determine map center
    df_combined = pd.concat([df_route_map, df_static_map])
   
    if df_combined.empty:
        st.write("Tidak ada data untuk parameter yang dipilih.")
        return None
   
    # Calculate center coordinates
    center_lat = df_combined['Latitude'].mean()
    center_lon = df_combined['Longitude'].mean()
   
    # Create map
    m = leafmap.Map(center=[center_lat, center_lon], zoom=8)
    m.add_basemap("OpenStreetMap")
    m.add_basemap("Satellite")
    
    # Get coordinate display preference
    show_coordinates = st.session_state.get('show_coords_checkbox_sidebar', True)
    coordinate_format = st.session_state.get('coord_format_radio_sidebar', "Desimal (DD.DDDDDD)")
    
    # Add coordinate control to map
    if show_coordinates:
        # Format according to user choice
        if coordinate_format == "Desimal (DD.DDDDDD)":
            formatter = 'function(num) {return L.Util.formatNum(num, 6) + "°";}'
        else:
            formatter = '''
            function(num) {
                var deg = Math.floor(Math.abs(num));
                var min = Math.floor((Math.abs(num) - deg) * 60);
                var sec = ((Math.abs(num) - deg - min/60) * 3600).toFixed(2);
                var dir = num >= 0 ? "N" : "S";
                if (this.options.lngFirst) {
                    dir = num >= 0 ? "E" : "W";
                }
                return deg + "°" + min + "'" + sec + '"' + dir;
            }
            '''
            
        mouse_position = MousePosition(
            position='bottomright',
            separator=' | ',
            empty_string='',
            lng_first=False,
            num_digits=6,
            prefix='Koordinat:',
            lat_formatter=formatter,
            lng_formatter=formatter
        )
        m.add_child(mouse_position)
    
    # Add CSS for pulse animation
    folium.Element("""
    <style>
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.4; }
            100% { opacity: 1; }
        }
        .marker-pulse {
            animation: pulse 1.5s infinite;
        }
        .marker-pulse-fast {
            animation: pulse 0.8s infinite;
        }
        .coordinate-display {
            background-color: rgba(255, 255, 255, 0.8);
            border-radius: 4px;
            padding: 4px 8px;
            font-weight: bold;
            color: #333;
            border: 1px solid #ccc;
        }
        .coords-highlight {
            background-color: #f0f0f0;
            border-left: 3px solid #2196F3;
            padding: 3px 6px;
            margin-top: 4px;
            font-weight: bold;
            font-family: monospace;
        }
    </style>
    """).add_to(m)
   
    # Create marker cluster
    marker_cluster = MarkerCluster().add_to(m)
   
    # Function to create custom icon
    def create_custom_icon(jenis_test, operator, nilai):
        # Determine color based on operator
        color = OPERATOR_COLORS.get(operator, 'gray')
        
        # Create icon HTML based on test type
        if jenis_test == 'Route Test':
            icon_html = f"""
            <div class="marker-pulse" style="animation-delay: {(hash(operator) % 5) * 0.2}s;">
                <i class="fa fa-map-marker fa-2x" style="color:{color};"></i>
            </div>
            """
            return folium.DivIcon(
                html=icon_html,
                icon_size=(30, 30),
                icon_anchor=(15, 30)
            )
        else:
            icon_html = f"""
            <div class="marker-pulse-fast" style="animation-delay: {(hash(operator) % 3) * 0.3}s;">
                <i class="fa fa-wifi fa-2x" style="color:{color};"></i>
            </div>
            """
            return folium.DivIcon(
                html=icon_html,
                icon_size=(30, 30),
                icon_anchor=(15, 15)
            )
    
    # Helper function to get coordinate display
    def get_coordinate_display(row):
        if coordinate_format == "Desimal (DD.DDDDDD)":
            return row['Koordinat']
        else:
            return row['Koordinat_DMS']
   
    # Add Route Test markers
    if has_route_data:
        for op in [op for op in OPERATORS if op in df_route_map.columns]:
            # Convert to numeric where possible
            df_route_map[op] = pd.to_numeric(df_route_map[op], errors='coerce')
            df_route_map = df_route_map.dropna(subset=[op])
            
            # Filter data with non-null values
            op_data = df_route_map.copy()
            op_data = op_data[op_data[op].notna()]
           
            if not op_data.empty:
                for _, row in op_data.iterrows():
                    # Format value for display
                    nilai = row[op]
                    nilai_str = f"{nilai}" if isinstance(nilai, (int, float, str)) else str(nilai)
                    
                    # Get coordinates in selected format
                    coord_display = get_coordinate_display(row)
                   
                    # Create popup content
                    popup_content = f"""
                    <div style="font-family: Arial; font-size: 12px;">
                        <b>Jenis Pengukuran:</b> Route Test<br>
                        <b>Lokasi:</b> {row['Alamat']}<br>
                        <b>Operator:</b> {op}<br>
                        <b>Parameter:</b> {param_route}<br>
                        <b>Nilai:</b> {nilai_str}<br>
                        <b>Tanggal:</b> {row['Tanggal_str']}<br>
                        <b>Koordinat:</b> <div class="coords-highlight">{coord_display}</div>
                        {"<b>Kabupaten/Kota:</b> " + row['Kabupaten/Kota'] + "<br>" if 'Kabupaten/Kota' in op_data.columns else ""}
                    </div>
                    """
                   
                    # Create marker
                    folium.Marker(
                        location=[row['Latitude'], row['Longitude']],
                        icon=create_custom_icon('Route Test', op, nilai),
                        popup=folium.Popup(popup_content, max_width=300),
                        tooltip=f"Route Test: {op} - {row['Alamat']} | {coord_display}"
                    ).add_to(marker_cluster)
   
    # Add Static Test markers
    if has_static_data:
        for op in [op for op in OPERATORS if op in df_static_map.columns]:
            # Convert to numeric where possible
            df_static_map[op] = pd.to_numeric(df_static_map[op], errors='ignore')
            
            # Filter data with non-null values
            op_data = df_static_map.copy()
            op_data = op_data[op_data[op].notna()]
           
            if not op_data.empty:
                for _, row in op_data.iterrows():
                    # Format value for display
                    nilai = row[op]
                    nilai_str = f"{nilai}" if isinstance(nilai, (int, float, str)) else str(nilai)
                    
                    # Get coordinates in selected format
                    coord_display = get_coordinate_display(row)
                   
                    # Create popup content
                    popup_content = f"""
                    <div style="font-family: Arial; font-size: 12px;">
                        <b>Jenis Pengukuran:</b> Static Test<br>
                        <b>Lokasi:</b> {row['Alamat']}<br>
                        <b>Operator:</b> {op}<br>
                        <b>Parameter:</b> {param_static}<br>
                        <b>Nilai:</b> {nilai_str}<br>
                        <b>Tanggal:</b> {row['Tanggal_str']}<br>
                        <b>Koordinat:</b> <div class="coords-highlight">{coord_display}</div>
                        {"<b>Kabupaten/Kota:</b> " + row['Kabupaten/Kota'] + "<br>" if 'Kabupaten/Kota' in op_data.columns else ""}
                    </div>
                    """
                   
                    # Create marker
                    folium.Marker(
                        location=[row['Latitude'], row['Longitude']],
                        icon=create_custom_icon('Static Test', op, nilai),
                        popup=folium.Popup(popup_content, max_width=300),
                        tooltip=f"Static Test: {op} - {row['Alamat']} | {coord_display}"
                    ).add_to(marker_cluster)
   
    # Add legend
    legend_html = """
    <div style="position: fixed; bottom: 50px; right: 50px; z-index: 1000; background-color: white;
                padding: 10px; border: 2px solid grey; border-radius: 5px">
        <div style="margin-bottom: 5px;"><b>Operator:</b></div>
    """
   
    # Add operator legend
    for op in OPERATORS:
        legend_html += f"""
        <div style="margin-bottom: 3px;">
            <i style="background:{OPERATOR_COLORS.get(op, 'gray')}; width: 12px; height: 12px; display: inline-block; border: 1px solid black;" 
               class="marker-pulse"></i> {op}
        </div>
        """
   
    # Add test type legend
    legend_html += """
        <div style="margin-top: 10px; margin-bottom: 5px;"><b>Jenis Pengukuran:</b></div>
        <div style="margin-bottom: 3px;" class="marker-pulse"><i class="fa fa-map-marker" style="color:gray;"></i> Route Test</div>
        <div style="margin-bottom: 3px;" class="marker-pulse-fast"><i class="fa fa-wifi" style="color:gray;"></i> Static Test</div>
    </div>
    """
   
    m.add_html(html=legend_html, position="bottomright")
   
    return m

# ====== CONFIGURATION MANAGEMENT ======

def save_config():
    """Save current configuration"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("Simpan Konfigurasi")
    config_name = st.sidebar.text_input("Nama Konfigurasi:", "konfigurasi_default", key="config_name_input")
    
    if st.sidebar.button("Simpan Konfigurasi Saat Ini", key="save_config_button"):
        # Initialize config if not exists
        if 'configs' not in st.session_state:
            st.session_state['configs'] = {}
            
        try:
            # Get values from session state
            bulan_terpilih = st.session_state.get('process_data_month_select_primary', 'Semua')
            kabupaten_terpilih = st.session_state.get('district_multiselect_main', [])
            
            # Get locations for Route Test and Static Test
            lokasi_route_terpilih = st.session_state.get('location_multiselect_route', [])
            lokasi_static_terpilih = st.session_state.get('location_multiselect_static', [])
            
            # Get selected parameters
            parameter_terpilih_route = st.session_state.get('route_param_select_sidebar', '')
            parameter_terpilih_static = st.session_state.get('static_param_select_sidebar', '')
            
            # Get map options
            show_coordinates = st.session_state.get('show_coords_checkbox_sidebar', True)
            coordinate_format = st.session_state.get('coord_format_radio_sidebar', "Desimal (DD.DDDDDD)")
            
            # Save configuration
            st.session_state['configs'][config_name] = {
                'bulan': bulan_terpilih,
                'kabupaten': kabupaten_terpilih,
                'lokasi_route': lokasi_route_terpilih,
                'lokasi_static': lokasi_static_terpilih,
                'param_route': parameter_terpilih_route,
                'param_static': parameter_terpilih_static,
                'show_coordinates': show_coordinates,
                'coordinate_format': coordinate_format
            }
            st.sidebar.success(f"Konfigurasi '{config_name}' berhasil disimpan!")
        except Exception as e:
            st.sidebar.error(f"Error saat menyimpan konfigurasi: {str(e)}")

def load_config():
    """Load saved configuration"""
    if 'configs' in st.session_state and st.session_state['configs']:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Muat Konfigurasi")
        
        config_names = list(st.session_state['configs'].keys())
        selected_config = st.sidebar.selectbox("Pilih Konfigurasi:", config_names, key="load_config_select")
        
        if st.sidebar.button("Muat Konfigurasi", key="load_config_button"):
            try:
                config = st.session_state['configs'][selected_config]
                
                # Set values in session state
                st.session_state['process_data_month_select_primary'] = config.get('bulan', 'Semua')
                st.session_state['district_multiselect_main'] = config.get('kabupaten', [])
                st.session_state['location_multiselect_route'] = config.get('lokasi_route', [])
                st.session_state['location_multiselect_static'] = config.get('lokasi_static', [])
                st.session_state['route_param_select_sidebar'] = config.get('param_route', '')
                st.session_state['static_param_select_sidebar'] = config.get('param_static', '')
                st.session_state['show_coords_checkbox_sidebar'] = config.get('show_coordinates', True)
                st.session_state['coord_format_radio_sidebar'] = config.get('coordinate_format', "Desimal (DD.DDDDDD)")
                
                st.sidebar.success(f"Konfigurasi '{selected_config}' berhasil dimuat!")
                st.experimental_rerun()
            except Exception as e:
                st.sidebar.error(f"Error saat memuat konfigurasi: {str(e)}")

# ====== MAIN APPLICATION ======

def main():
    """Main application function"""
    st.title("Visualisasi Data QoE SIGMON Operator Seluler")
    
    # Check credentials
    credentials = get_gsheet_credentials()
    
    if credentials is None:
        st.warning("Silakan upload file kredensial Google API (credentials.json) untuk mengakses spreadsheet.")
        return
    
    # Show spreadsheet selection options
    available_sheets = get_available_spreadsheets()
    
    if not available_sheets:
        st.warning("Tidak ada spreadsheet yang tersedia atau kredensial tidak memiliki akses ke spreadsheet.")
        
        # Optional: Allow direct spreadsheet ID input
        sheet_id = st.text_input(
            "Masukkan ID Spreadsheet Google Sheets:", 
            help="ID spreadsheet dapat ditemukan pada URL spreadsheet setelah '/d/'",
            key="sheet_id_input"
        )
        
        if sheet_id:
            worksheet_names = get_worksheet_names(sheet_id)
            if worksheet_names:
                sheet_name = st.selectbox("Pilih Worksheet:", worksheet_names, key="worksheet_select_direct")
            else:
                sheet_name = "Sheet1"  # Default
        else:
            return
    else:
        sheet_options = {name: id for id, name in available_sheets}
        selected_sheet_name = st.selectbox("Pilih Spreadsheet:", list(sheet_options.keys()), key="spreadsheet_select")
        sheet_id = sheet_options[selected_sheet_name]
        
        # Get worksheet list
        worksheet_names = get_worksheet_names(sheet_id)
        if worksheet_names:
            sheet_name = st.selectbox("Pilih Worksheet:", worksheet_names, key="worksheet_select")
        else:
            sheet_name = "Sheet1"  # Default
    
    # Load data button
    if st.button("Muat Data", key="load_data_button"):
        with st.spinner("Memuat data dari Google Sheets..."):
            df = load_data_from_sheets(sheet_id, sheet_name)
            
            if df is None or df.empty:
                st.error("Tidak dapat memuat data dari spreadsheet atau spreadsheet kosong.")
                return
            
            # Save DataFrame to session_state for access in other parts
            st.session_state['df'] = df
            
            # Display raw data
            st.subheader("Data mentah")
            st.dataframe(df)
            
            # Process data
            process_data(df)
    
    # If data was previously loaded, display it
    if 'df' in st.session_state:
        process_data(st.session_state['df'])

def process_data(df):
    """Process and display data visualizations"""
    # Ensure date column is available and properly formatted
    if 'Tanggal' not in df.columns:
        st.warning("Kolom 'Tanggal' tidak ditemukan dalam data.")
        return
        
    # Ensure measurement type column is available
    if 'Jenis Pengukuran' not in df.columns:
        st.warning("Kolom 'Jenis Pengukuran' tidak ditemukan dalam data.")
        return
       
    # Ensure coordinate columns are available
    if 'Latitude' not in df.columns or 'Longitude' not in df.columns:
        st.warning("Kolom 'Latitude' dan/atau 'Longitude' tidak ditemukan dalam data.")
        return
    
    # Month filter
    bulan_unik = ['Semua'] + sorted(df['Bulan'].unique().tolist())
    #bulan_terpilih = st.selectbox("Pilih Bulan:", bulan_unik, index=0, key="process_data_month_select_primary")
    # Ganti nama key agar unik, misalnya dengan menambah akhiran '_new' atau sesuai fungsinya
    bulan_terpilih = st.selectbox("Pilih Bulan:", bulan_unik, index=0, key="process_data_month_select_unique")
    
    if bulan_terpilih == 'Semua':
        df_filtered = df.copy()
    else:
        df_filtered = df[df['Bulan'] == bulan_terpilih]
        
    # District/City filter
    if 'Kabupaten/Kota' in df.columns:
        kabupaten_unik = sorted(df_filtered['Kabupaten/Kota'].unique().tolist())
        kabupaten_terpilih = st.multiselect("Pilih Kabupaten/Kota:", kabupaten_unik, default=kabupaten_unik, key="district_multiselect_main")
        
        if kabupaten_terpilih:
            df_filtered = df_filtered[df_filtered['Kabupaten/Kota'].isin(kabupaten_terpilih)]
    else:
        st.warning("Kolom 'Kabupaten/Kota' tidak ditemukan dalam data.")
    
    # Split data by measurement type
    df_route_all = df_filtered[df_filtered['Jenis Pengukuran'] == 'Route Test'].copy()
    df_static_all = df_filtered[df_filtered['Jenis Pengukuran'] == 'Static Test'].copy()
    
    # Location filters for Route Test and Static Test
    st.subheader("Filter Lokasi")
    
    col_lokasi1, col_lokasi2 = st.columns(2)
    
    with col_lokasi1:
        st.markdown('<div class="route-test-header">Route Test</div>', unsafe_allow_html=True)
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        
        lokasi_route_unik = sorted(df_route_all['Alamat'].unique().tolist()) if not df_route_all.empty else []
        lokasi_route_terpilih = st.multiselect(
            "Pilih Lokasi Route Test:", 
            lokasi_route_unik, 
            default=lokasi_route_unik, 
            key="location_multiselect_route"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col_lokasi2:
        st.markdown('<div class="static-test-header">Static Test</div>', unsafe_allow_html=True)
        st.markdown('<div class="filter-container">', unsafe_allow_html=True)
        
        lokasi_static_unik = sorted(df_static_all['Alamat'].unique().tolist()) if not df_static_all.empty else []
        lokasi_static_terpilih = st.multiselect(
            "Pilih Lokasi Static Test:", 
            lokasi_static_unik, 
            default=lokasi_static_unik, 
            key="location_multiselect_static"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Filter data by selected locations
    df_route_test = df_route_all[df_route_all['Alamat'].isin(lokasi_route_terpilih)] if lokasi_route_terpilih else pd.DataFrame()
    df_static_test = df_static_all[df_static_all['Alamat'].isin(lokasi_static_terpilih)] if lokasi_static_terpilih else pd.DataFrame()
    
    # Parameter selection for Route Test
    st.sidebar.subheader("Parameter Route Test")
    parameter_unik_route = sorted(df_route_test['Parameter'].unique().tolist()) if not df_route_test.empty else []
    parameter_terpilih_route = st.sidebar.selectbox(
        "Pilih Parameter Route Test:", 
        parameter_unik_route if parameter_unik_route else ['Tidak ada data'], 
        key="route_param_select_sidebar"
    )
    
    # Parameter selection for Static Test
    st.sidebar.subheader("Parameter Static Test")
    parameter_unik_static = sorted(df_static_test['Parameter'].unique().tolist()) if not df_static_test.empty else []
    parameter_terpilih_static = st.sidebar.selectbox(
        "Pilih Parameter Static Test:", 
        parameter_unik_static if parameter_unik_static else ['Tidak ada data'], 
        key="static_param_select_sidebar"
    )
    
    # Map display options
    st.sidebar.subheader("Opsi Peta")
    show_coordinates = st.sidebar.checkbox("Tampilkan Koordinat pada Peta", value=True, key="show_coords_checkbox_sidebar")
    coordinate_format = st.sidebar.radio(
        "Format Koordinat", 
        ["Desimal (DD.DDDDDD)", "Derajat-Menit-Detik (DD°MM'SS\")"], 
        index=0, 
        key="coord_format_radio_sidebar"
    )
    
    # Create two columns for charts
    col1, col2 = st.columns(2)
    
    # Display Route Test chart
    with col1:
        st.subheader(f"Grafik {parameter_terpilih_route} (Route Test)")
        df_plot_route = create_barchart(df_route_test, parameter_terpilih_route, "Route Test")
        
    # Display Static Test chart
    with col2:
        st.subheader(f"Grafik {parameter_terpilih_static} (Static Test)")
        df_plot_static = create_barchart(df_static_test, parameter_terpilih_static, "Static Test")
    
    # Display combined map
    st.subheader("Peta Lokasi QoE SIGMON (Route Test & Static Test)")
    combined_map = create_combined_map(df_route_test, df_static_test, parameter_terpilih_route, parameter_terpilih_static)
    if combined_map:
        combined_map.to_streamlit(height=500)
    else:
        st.write("Tidak ada data untuk ditampilkan pada peta gabungan.")
        
    # Location comparison summary
    st.subheader("Ringkasan Perbandingan Parameter Antar Operator")
    
    # Route Test comparison
    if not df_route_test.empty and parameter_terpilih_route in df_route_test['Parameter'].values:
        route_comparison = create_location_comparison(df_route_test, parameter_terpilih_route, "Route Test")
        if route_comparison is not None:
            st.markdown(f"##### Perbandingan {parameter_terpilih_route} (Route Test)")
            st.dataframe(route_comparison)
        else:
            st.info(f"Tidak dapat membuat perbandingan untuk {parameter_terpilih_route} (Route Test).")
    
    # Static Test comparison
    if not df_static_test.empty and parameter_terpilih_static in df_static_test['Parameter'].values:
        static_comparison = create_location_comparison(df_static_test, parameter_terpilih_static, "Static Test")
        if static_comparison is not None:
            st.markdown(f"##### Perbandingan {parameter_terpilih_static} (Static Test)")
            st.dataframe(static_comparison)
        else:
            st.info(f"Tidak dapat membuat perbandingan untuk {parameter_terpilih_static} (Static Test).")

# ====== APPLICATION ENTRY POINT ======

if __name__ == "__main__":
    main()
    
    # Add configuration options
    save_config()
    load_config()
    
    # Add usage instructions
    st.markdown("""
    <div class='highlight'>
        <h4>Petunjuk Penggunaan:</h4>
        <ol>
            <li>Pilih file pada Menu <b>Pilih Spreadsheet</b> untuk memilih file yang ada, kemudian Klik Tombol <b>Muat Data</b></li>
            <li>Klik Menu Filter pada Parameter Route Test maupun Static Test untuk memilih Hasil Pengukuran QoE yang telah dilakukan</li>
            <li>Lakukan filter pada Menu <b>Pilih Bulan</b> untuk memilih bulan yang di inginkan</li>
            <li>Lakukan filter pada Menu <b>Pilih Kabupaten/Kota</b> untuk memilih Kabupaten/Kota yang di inginkan</li>
            <li>Gunakan area <b>Filter Lokasi</b> untuk memilih lokasi yang berbeda untuk <b>Route Test</b> dan <b>Static Test</b></li>
            <li>Untuk melihat lokasi yang telah dilakukan pengukuran QoE bisa melakukan zoom in / out pada menu <b>Peta</b></li>
            <li>Untuk data <b>Route Test</b> pada Peta bukan merupakan hasil aktual karena menggunaka data koordinat dari <b>Static test</b> yang berfungsi untuk menampilkan data pada aplikasi</li>
            <li>Data <b>Static Test</b> merupakan aktual berdasarkan hasil inputan data dari pengukuran QoE yang telah dilakukan</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)
    
    # Footer
    st.markdown("""
    <div style='text-align: center; margin-top: 30px; padding: 10px; color: #888;'>
        <p>© <b>2025 Aplikasi Visualisasi QoE Kualitas Layanan | Loka Monitor SFR Kendari</b></p>
    </div>
    """, unsafe_allow_html=True)