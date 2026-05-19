import streamlit as st
import pandas as pd
import geopandas as gpd
import networkx as nx
import math
import json
import folium
import requests
import base64
from pyproj import Transformer
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import os

# --- 1. 앱 설정 및 커스텀 CSS ---
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

# 💡 이미지를 안전하게 불러오는 함수 (images 폴더 경로 포함)
def get_base64_image(image_filename):
    image_path = os.path.join("images", image_filename)
    try:
        with open(image_path, "rb") as img_file:
            return "data:image/jpeg;base64," + base64.b64encode(img_file.read()).decode()
    except:
        return "https://via.placeholder.com/300x200/1E1E2E/FFFFFF?text=Image+Not+Found"

st.markdown("""
    <style>
        .block-container { padding: 0 !important; max-width: 430px !important; margin: 0 auto !important; background-color: #0A0A0F; min-height: 100vh; overflow-x: hidden;}
        header { display: none !important; }
        footer { display: none !important; }
        iframe { border: none !important; width: 100% !important; border-radius: 0 0 24px 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        
        /* 💡 스트림릿 실행(로딩) 중 화면 어두워짐 및 깜빡임 원천 차단 */
        div[data-testid="stAppViewBlockContainer"] { opacity: 1 !important; transition: none !important; }
        div[data-testid="stAppViewContainer"] > div:first-child { background: transparent !important; }
        div[data-testid="stStatusWidget"] { display: none !important; }
        
        div[data-testid="stSelectbox"], div[data-testid="stRadio"] { padding: 0 20px !important; box-sizing: border-box; }
        
        div.stButton { padding: 0 20px !important; }
        div.stButton > button { width: 100%; border-radius: 16px !important; font-weight: 800 !important; transition: 0.3s; display: flex; justify-content: center;}
        
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #00F5FF, #0080FF) !important;
            color: #000 !important; border: none !important; padding: 16px !important; font-size: 16px !important;
            box-shadow: 0 4px 15px rgba(0, 245, 255, 0.3) !important;
        }
        div.stButton > button[kind="secondary"] {
            background-color: rgba(255,255,255,0.05) !important;
            color: #F0F0FF !important; border: 1px solid rgba(255,255,255,0.1) !important;
            padding: 14px !important; font-size: 15px !important; margin-top: 10px !important;
        }
        
        .stMarkdown h3 { color: #FFFFFF; padding: 20px 20px 10px 20px; font-size: 22px; font-weight: 800; margin-bottom: 0;}
        .stRadio > label { color: #8A8AA0 !important; font-size: 12px; margin-bottom: 5px; }
        div[role="radiogroup"] label p { color: #FFFFFF !important; font-weight: 700 !important; font-size: 15px !important; }
        .stSelectbox > label { color: #8A8AA0; font-size: 12px; margin-bottom: -5px;}
        
        div[data-testid="stExpander"] { padding: 0 20px !important; }
        div[data-testid="stExpander"] details { background: transparent !important; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; }
        div[data-testid="stExpander"] summary { color: #FFF; font-weight: 800; }
        
        .gallery-fac { font-size: 11px; color: #FFF; line-height: 1.6; }
        .fac-badge { background: rgba(255,255,255,0.1); padding: 4px 8px; border-radius: 6px; display: inline-block; margin: 2px 2px 2px 0;}
    </style>
""", unsafe_allow_html=True)

criteria_cols = ['교차로', '보도폭', '대기질', '유동인구', '보도재질', '교통사고', 'CCTV', '녹지및그늘', '편의점', '경사', '하천', '신호등', '소음']

# --- 2. 상태 관리 ---
if 'page' not in st.session_state: st.session_state.page = 'step1_location'
if 'user_location' not in st.session_state: st.session_state.user_location = None
if 'nearest_hub' not in st.session_state: st.session_state.nearest_hub = None

if 'approach_segments' not in st.session_state: st.session_state.approach_segments = []
if 'main_opt_segments' not in st.session_state: st.session_state.main_opt_segments = []
if 'main_sho_segments' not in st.session_state: st.session_state.main_sho_segments = []
if 'loop_segments' not in st.session_state: st.session_state.loop_segments = []
if 'route_mode' not in st.session_state: st.session_state.route_mode = ""
if 'marker_data' not in st.session_state: st.session_state.marker_data = []

if 'dist_app' not in st.session_state: st.session_state.dist_app = 0
if 'dist_opt' not in st.session_state: st.session_state.dist_opt = 0
if 'dist_sho' not in st.session_state: st.session_state.dist_sho = 0
if 'dist_loop' not in st.session_state: st.session_state.dist_loop = 0

if 'opt_stats' not in st.session_state: st.session_state.opt_stats = {c: 0.0 for c in criteria_cols}
if 'sho_stats' not in st.session_state: st.session_state.sho_stats = {c: 0.0 for c in criteria_cols}
if 'opt_len' not in st.session_state: st.session_state.opt_len = 0
if 'sho_len' not in st.session_state: st.session_state.sho_len = 0
if 'opt_well' not in st.session_state: st.session_state.opt_well = 0
if 'sho_well' not in st.session_state: st.session_state.sho_well = 0

# 💡 거점 데이터
hubs_info = {
    "옥수역": {"coords": (37.5413498, 127.0171347), "type": "교통 요충지형", "icon": "🚇", "color": "#39FF14", "bg": "rgba(57,255,20,0.15)", "image": "oksu.jpg", "facilities": ["스트레칭존", "음수대", "물품보관함", "휴식 라운지"]},
    "왕십리역": {"coords": (37.5616302, 127.0351177), "type": "교통 요충지형", "icon": "🚉", "color": "#39FF14", "bg": "rgba(57,255,20,0.15)", "image": "wang.jpg", "facilities": ["스트레칭존", "음수대", "물품보관함"]},
    "금호나들목": {"coords": (37.5512902, 127.0356081), "type": "수변 관문형", "icon": "🌊", "color": "#00F5FF", "bg": "rgba(0,245,255,0.15)", "image": "ho.jpg", "facilities": ["야외 운동기구", "음수대", "물품보관함"]},
    "성덕정나들목": {"coords": (37.5375776, 127.0454704), "type": "수변 관문형", "icon": "🌉", "color": "#00F5FF", "bg": "rgba(0,245,255,0.15)", "image": "duck.jpg", "facilities": ["야외 운동기구", "음수대", "물품보관함", "야간 조명"]},
    "청구아파트나들목": {"coords": (37.5348428, 127.0552105), "type": "수변 관문형", "icon": "🌊", "color": "#00F5FF", "bg": "rgba(0,245,255,0.15)", "image": "gu.jpg", "facilities": ["음수대", "물품보관함", "야간 조명", "쿨링 미스트"]},
    "송정체육공원": {"coords": (37.5536442, 127.0672346), "type": "수변 관문형", "icon": "🌉", "color": "#00F5FF", "bg": "rgba(0,245,255,0.15)", "image": "song.jpg", "facilities": ["스트레칭존", "음수대", "물품보관함"]},
    "서울숲역": {"coords": (37.5465240, 127.0429873), "type": "상권 / 트렌드형", "icon": "🛍️", "color": "#FF2D78", "bg": "rgba(255,45,120,0.15)", "image": "forest.jpg", "facilities": ["파클릿", "음수대", "물품보관함"]},
    "성삼공원": {"coords": (37.5420202, 127.0602789), "type": "상권 / 트렌드형", "icon": "☕", "color": "#FF2D78", "bg": "rgba(255,45,120,0.15)", "image": "sam.jpg", "facilities": ["파클릿", "음수대", "물품보관함"]},
    "금옥공원": {"coords": (37.5534649, 127.0213021), "type": "주거 밀착형", "icon": "🏘️", "color": "#FFD700", "bg": "rgba(255,215,0,0.15)", "image": "gold.jpg", "facilities": ["스트레칭존", "음수대", "물품보관함", "휴식 라운지"]},
    "꽃재공원": {"coords": (37.5672965, 127.0282145), "type": "주거 밀착형", "icon": "🏡", "color": "#FFD700", "bg": "rgba(255,215,0,0.15)", "image": "flower.jpg", "facilities": ["스트레칭존", "음수대", "물품보관함"]},
    "용답마을마당": {"coords": (37.5619688, 127.0517828), "type": "주거 밀착형", "icon": "🏘️", "color": "#FFD700", "bg": "rgba(255,215,0,0.15)", "image": "yong.jpg", "facilities": ["스트레칭존", "음수대", "물품보관함", "휴식 라운지"]},
    "향림소공원": {"coords": (37.5467465, 127.0534440), "type": "주거 밀착형", "icon": "🏡", "color": "#FFD700", "bg": "rgba(255,215,0,0.15)", "image": "lim.jpg", "facilities": ["운동시설", "음수대", "물품보관함"]}
}
hub_names = list(hubs_info.keys())

# --- 3. 데이터 로드 엔진 ---
@st.cache_data
def load_boundary():
    try:
        url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
        seoul_geo = requests.get(url).json()
        sd_features = [f for f in seoul_geo['features'] if f['properties']['name'] == '성동구']
        
        lon_shift = -0.0037 
        lat_shift = 0.0028      
        
        def shift_coords(coords):
            if isinstance(coords[0], (int, float)):
                return [coords[0] + lon_shift, coords[1] + lat_shift]
            return [shift_coords(c) for c in coords]
        
        for feature in sd_features:
            feature['geometry']['coordinates'] = shift_coords(feature['geometry']['coordinates'])
            
        return {'type': 'FeatureCollection', 'features': sd_features}
    except Exception as e: 
        return None

@st.cache_data
def load_fountain_data():
    try:
        try:
            df = pd.read_csv('성동구_공원음수대.csv', encoding='utf-8')
        except:
            df = pd.read_csv('성동구_공원음수대.csv', encoding='cp949')
            
        df['Y좌표(LAT)'] = pd.to_numeric(df['Y좌표(LAT)'], errors='coerce')
        df['X좌표(LNG)'] = pd.to_numeric(df['X좌표(LNG)'], errors='coerce')
        df = df.dropna(subset=['X좌표(LNG)', 'Y좌표(LAT)'])
        
        fountains = []
        for _, row in df.iterrows():
            addr1 = str(row.get('지번주소', ''))
            addr2 = str(row.get('도로명주소', ''))
            cid = str(row.get('컨텐츠 아이디', ''))
            
            if '성동구' in addr1 or '성동구' in addr2 or '성동구' in cid:
                fountains.append({
                    'lat': float(row['Y좌표(LAT)']),
                    'lon': float(row['X좌표(LNG)'])
                })
        return fountains
    except Exception as e:
        return []

@st.cache_resource
def load_data():
    G = nx.Graph()
    node_coords = {}
    df_loop_merged = pd.DataFrame()
    geom_dict = {}

    try:
        df_network = pd.read_csv('soengdong_wellness_network.csv')
        if os.path.exists('soengdong_wellness_network.zip'):
            gdf_network = gpd.read_file('zip://soengdong_wellness_network.zip').to_crs(epsg=4326)
        else:
            gdf_network = gpd.read_file('soengdong_wellness_network.geojson').to_crs(epsg=4326)
        
        df_network.columns = df_network.columns.str.strip().str.upper()
        gdf_network.columns = [col.strip().upper() if col != 'geometry' else 'geometry' for col in gdf_network.columns]
        
        geo_fid_col = [col for col in gdf_network.columns if col.endswith('TARGET_FID')][0]
        csv_fid_col = 'TARGET_FID' if 'TARGET_FID' in df_network.columns else df_network.columns[0]
        
        def clean_id(x):
            s = str(x).strip()
            if s.endswith('.0'): s = s[:-2]
            return s

        df_network['MATCH_ID'] = df_network[csv_fid_col].apply(clean_id)
        gdf_network['MATCH_ID'] = gdf_network[geo_fid_col].apply(clean_id)
        
        geom_dict = dict(zip(gdf_network['MATCH_ID'], gdf_network['geometry']))
        
        for _, row in df_network.iterrows():
            s_node = f"{row['START_X']:.1f}_{row['START_Y']:.1f}"
            e_node = f"{row['END_X']:.1f}_{row['END_Y']:.1f}"
            fid = str(row['MATCH_ID'])
            smooth_geom = geom_dict.get(fid)
            
            shape_len = row.get('SHAPE_LENGTH', 1)
            cost_val = row.get('ROUTE_COST', shape_len)
            
            attr_dict = {c: row[c] if c in df_network.columns else 0 for c in criteria_cols}
            G.add_edge(s_node, e_node, length=shape_len, wellness=cost_val, geom=smooth_geom, **attr_dict)
            
            if smooth_geom is not None and smooth_geom.geom_type == 'LineString':
                coords = list(smooth_geom.coords)
                node_coords[s_node] = coords[0]
                node_coords[e_node] = coords[-1]
                
        file_name = 'Seongdong_Loop_Routes_3k_5k (1).csv'
        if os.path.exists(file_name):
            df_routes = pd.read_csv(file_name)
            df_routes.columns = df_routes.columns.str.strip().str.upper()
            df_routes['MATCH_ID'] = df_routes.get('TARGET_FID', df_routes.iloc[:,0]).apply(clean_id)
            df_loop_merged = pd.merge(df_routes, df_network, on='MATCH_ID', how='inner')
    except Exception as e: st.error(f"데이터 로드 실패: {e}")

    return G, node_coords, df_loop_merged, geom_dict

with st.spinner("엔진 부팅 중..."):
    sd_boundary = load_boundary()
    fountains_data = load_fountain_data() 
    G, node_coords, df_loop_merged, geom_dict = load_data()

def get_nearest_node(lon, lat):
    if not node_coords: return None
    return min(node_coords.keys(), key=lambda n: math.sqrt((node_coords[n][0]-lon)**2 + (node_coords[n][1]-lat)**2))

def get_nearest_hub(lat, lon):
    return min(hubs_info.keys(), key=lambda h: math.sqrt((hubs_info[h]['coords'][0]-lat)**2 + (hubs_info[h]['coords'][1]-lon)**2))

def extract_real_geometry(path):
    segments = []
    if not path: return segments
    for u, v in zip(path[:-1], path[1:]):
        geom = G.get_edge_data(u, v).get('geom')
        if geom and geom.geom_type == 'LineString':
            segments.append([[lat, lon] for lon, lat in geom.coords])
    return segments

def calc_real_physical_distance(segments):
    total_dist = 0
    R = 6371000 
    for segment in segments:
        for i in range(len(segment) - 1):
            lat1, lon1 = segment[i]
            lat2, lon2 = segment[i+1]
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlam = math.radians(lon2 - lon1)
            a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
            total_dist += R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return total_dist

def get_stats_for_segment(path):
    length = 0
    well = 0.0
    stats = {c: 0.0 for c in criteria_cols}
    if not path or len(path) < 2: return length, stats, well
    for u, v in zip(path[:-1], path[1:]):
        d = G.get_edge_data(u, v)
        l = d.get('length', 0)
        w = d.get('wellness', l)
        length += l
        well += w
        for c in criteria_cols:
            val = d.get(c, 0)
            if pd.isna(val): val = 0
            stats[c] += val * l
    return length, stats, well

def get_pareto_optimal_path(G, source, target, min_ratio=1.0, max_ratio=1.5):
    try:
        shortest_path = nx.shortest_path(G, source=source, target=target, weight='length')
        min_dist = sum(G[u][v].get('length', 1) for u, v in zip(shortest_path[:-1], shortest_path[1:]))
        if min_dist == 0: return shortest_path

        max_allowed_dist = min_dist * max_ratio
        s_len, s_stats, _ = get_stats_for_segment(shortest_path)
        s_avg = {c: (s_stats[c] / s_len if s_len > 0 else 0) for c in criteria_cols}

        candidate_paths = []
        for step in range(21):
            alpha = step * 0.05
            def weight_func(u, v, d): return (d.get('length', 1) * alpha) + (d.get('wellness', 1) * (1 - alpha))
            try:
                path = nx.shortest_path(G, source=source, target=target, weight=weight_func)
                path_len = sum(G[u][v].get('length', 1) for u, v in zip(path[:-1], path[1:]))
                path_well = sum(G[u][v].get('wellness', 1) for u, v in zip(path[:-1], path[1:]))
                if path_len <= max_allowed_dist:
                    if not any(c['path'] == path for c in candidate_paths):
                        candidate_paths.append({'path': path, 'length': path_len, 'wellness': path_well})
            except: continue
            
        valid_candidates = []
        for cand in candidate_paths:
            c_len, c_stats, _ = get_stats_for_segment(cand['path'])
            if c_len == 0: continue
            improvement_score = sum((c_stats[c] / c_len) - s_avg[c] for c in criteria_cols)
            if improvement_score >= -0.01:
                valid_candidates.append(cand)
                
        if valid_candidates:
            best_candidate = min(valid_candidates, key=lambda x: x['wellness'])
            return best_candidate['path']
        return shortest_path
    except: return []

# --- 4. 화면 제어 ---

if st.session_state.page == 'step1_location':
    
    st.markdown("""
        <div style="padding: 20px 20px 10px 20px; display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="width: 45px; height: 45px; border-radius: 50%; background: url('https://cdn-icons-png.flaticon.com/512/3135/3135715.png') center/cover; border: 2px solid #00F5FF; box-shadow: 0 0 10px rgba(0,245,255,0.4);"></div>
                <div>
                    <div style="font-size: 13px; color: #8A8AA0; font-weight: 600;">Good Day,</div>
                    <div style="font-size: 18px; color: #FFF; font-weight: 900; letter-spacing: -0.5px;">Runner 🏃‍♂️</div>
                </div>
            </div>
            <div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.1);">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFF" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
            </div>
        </div>
        
        <div style="margin: 5px 20px 20px 20px; background: linear-gradient(135deg, rgba(0,245,255,0.15) 0%, rgba(0,0,0,0) 100%); border: 1px solid rgba(0,245,255,0.2); border-radius: 20px; padding: 22px; position: relative; overflow: hidden; box-shadow: 0 10px 20px rgba(0,0,0,0.2);">
            <div style="position: absolute; right: -15px; bottom: -20px; font-size: 110px; opacity: 0.1; transform: rotate(-15deg);">👟</div>
            <h2 style="margin: 0 0 8px 0; color: #FFF; font-size: 26px; font-weight: 900; letter-spacing: -1px;">Ready to Run?</h2>
            <p style="margin: 0 0 16px 0; color: #8A8AA0; font-size: 13px; line-height: 1.4;">지도에서 <b>현재 위치</b>를 탭하여<br>최적의 웰니스 러닝 코스를 탐색하세요.<br>거점 마커를 누르면 상세정보가 뜹니다.</p>
            <div style="display: flex; gap: 8px;">
                <span style="background: rgba(57, 255, 20, 0.15); color: #39FF14; border: 1px solid rgba(57,255,20,0.3); padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 800;">🌤️ 18°C 맑음</span>
                <span style="background: rgba(255, 45, 120, 0.15); color: #FF2D78; border: 1px solid rgba(255,45,120,0.3); padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 800;">🍃 대기질 최고</span>
            </div>
        </div>

        <div style="margin: 0 20px 15px 20px; display: flex; flex-wrap: wrap; gap: 6px; justify-content: center;">
            <div style="background: rgba(57,255,20,0.15); border: 1px solid #39FF14; color: #39FF14; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 800;">🟢 교통 요충지형</div>
            <div style="background: rgba(0,245,255,0.15); border: 1px solid #00F5FF; color: #00F5FF; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 800;">🔵 수변 관문형</div>
            <div style="background: rgba(255,45,120,0.15); border: 1px solid #FF2D78; color: #FF2D78; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 800;">🔴 상권/트렌드형</div>
            <div style="background: rgba(255,215,0,0.15); border: 1px solid #FFD700; color: #FFD700; padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: 800;">🟡 주거 밀착형</div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='padding: 0 20px;'>", unsafe_allow_html=True)
    
    m = folium.Map(location=[37.553, 127.042], zoom_start=13.5, tiles=None, zoom_control=False)
    folium.TileLayer('CartoDB dark_matter', attr=' ').add_to(m)
    
    css_injection = """
    <style>
        .leaflet-control-attribution { display: none !important; visibility: hidden !important; }
        .leaflet-popup-content-wrapper { background: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
        .leaflet-popup-tip { display: none !important; }
        .leaflet-popup-content { margin: 0 !important; width: auto !important; }
    </style>
    """
    m.get_root().header.add_child(folium.Element(css_injection))
    
    if sd_boundary:
        folium.GeoJson(sd_boundary, style_function=lambda x: {'color': 'white', 'fillColor': 'transparent', 'weight': 2, 'opacity': 0.6, 'dashArray':'5,5'}).add_to(m)

    for name, info in hubs_info.items():
        coords = info['coords']
        color = info['color']
        
        popup_html = f"""
        <div style="background: rgba(20,20,30,0.95); border: 1px solid {color}; padding: 12px; border-radius: 12px; color: #FFF; width: 170px; box-shadow: 0 4px 15px rgba(0,0,0,0.6);">
            <div style="font-weight: 900; font-size: 15px; margin-bottom: 8px; text-align: center; color: {color};">{name}</div>
            <img src="{get_base64_image(info['image'])}" style="width: 100%; height: 85px; object-fit: cover; border-radius: 6px; margin-bottom: 8px;">
            <div style="font-size: 11px; color: #CCC; margin-bottom: 4px;"><b>유형:</b> {info['type']}</div>
            <div style="font-size: 11px; color: #CCC; line-height: 1.4;"><b>시설:</b> {", ".join(info['facilities'])}</div>
        </div>
        """
        
        marker = folium.CircleMarker(location=coords, radius=7, color=color, fill=True, fillOpacity=0.9, weight=2)
        marker.add_child(folium.Popup(popup_html))
        marker.add_to(m)
        
    # 💡 핵심 수정 파트: returned_objects를 "last_clicked"로 묶어서 팝업 클릭 시 재실행되는 현상 방지
    map_data = st_folium(m, height=450, use_container_width=True, returned_objects=["last_clicked"])
    st.markdown("</div>", unsafe_allow_html=True)
    
    if map_data and map_data.get('last_clicked'):
        lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
        st.session_state.user_location = (lat, lon)
        st.session_state.nearest_hub = get_nearest_hub(lat, lon)
        st.session_state.page = 'step2_course'
        st.rerun()

elif st.session_state.page == 'step2_course':
    st.markdown("<h3>🎯 어디로 달려볼까요?</h3>", unsafe_allow_html=True)
    
    with st.expander("거점 정보 보기 🔍"):
        for h in hub_names:
            info = hubs_info[h]
            img_base64 = get_base64_image(info['image'])
            facs = " ".join([f"<span class='fac-badge'>• {f}</span>" for f in info['facilities']])
            
            st.markdown(f"""
            <div style="background: #1E1E2E; border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 12px; margin-bottom: 12px; display: flex; gap: 12px;">
                <img src="{img_base64}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 8px;">
                <div style="flex: 1;">
                    <div style="color: #FFF; font-size: 16px; font-weight: 900; margin-bottom: 4px;">{h}</div>
                    <div style="font-size: 11px; font-weight: 800; margin-bottom: 8px; display: inline-block; padding: 3px 6px; border-radius: 4px; background: {info['bg']}; color: {info['color']};">{info['type']}</div>
                    <div style="font-size: 11px; color: #CCC; line-height: 1.4;">{facs}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<hr style='border: 1px dashed rgba(255,255,255,0.1); margin: 10px 20px 20px 20px;'>", unsafe_allow_html=True)
    
    with st.container():
        start_hub = st.selectbox("📍 출발 거점", hub_names, index=hub_names.index(st.session_state.nearest_hub))
        mode = st.radio("🏃 코스 형태 선택", ["🚩 다른 거점으로 이동 (A to B)", "🔄 순환형 코스 (Loop)"])
        
        if mode == "🚩 다른 거점으로 이동 (A to B)":
            end_drop = st.selectbox("🏁 도착 거점", [h for h in hub_names if h != start_hub])
            via1 = st.selectbox("🔹 경유지 1 (선택)", ["선택 안 함"] + hub_names)
            via2 = st.selectbox("🔹 경유지 2 (선택)", ["선택 안 함"] + hub_names)
            
            if st.button("경로 탐색 🚀", type="primary"):
                with st.spinner("최적 경로 계산 중..."):
                    seq = [start_hub]
                    if via1 != "선택 안 함": seq.append(via1)
                    if via2 != "선택 안 함": seq.append(via2)
                    seq.append(end_drop)
                    
                    u_lat, u_lon = st.session_state.user_location
                    user_node = get_nearest_node(u_lon, u_lat)
                    first_hub_node = get_nearest_node(hubs_info[start_hub]['coords'][1], hubs_info[start_hub]['coords'][0])
                    
                    try: 
                        p_app = nx.shortest_path(G, source=user_node, target=first_hub_node, weight='length')
                        st.session_state.approach_segments = extract_real_geometry(p_app)
                    except: st.session_state.approach_segments = []
                    
                    opt_segs, sho_segs = [], []
                    
                    opt_len_acc, sho_len_acc = 0, 0
                    opt_well_acc, sho_well_acc = 0, 0
                    opt_stats_acc = {c: 0.0 for c in criteria_cols}
                    sho_stats_acc = {c: 0.0 for c in criteria_cols}
                    
                    for i in range(len(seq)-1):
                        s_node = get_nearest_node(hubs_info[seq[i]]['coords'][1], hubs_info[seq[i]]['coords'][0])
                        e_node = get_nearest_node(hubs_info[seq[i+1]]['coords'][1], hubs_info[seq[i+1]]['coords'][0])
                        
                        try: 
                            p_o = get_pareto_optimal_path(G, s_node, e_node, min_ratio=1.0, max_ratio=1.5)
                            opt_segs.extend(extract_real_geometry(p_o))
                            l, s, w = get_stats_for_segment(p_o)
                            opt_len_acc += l; opt_well_acc += w
                            for c in criteria_cols: opt_stats_acc[c] += s[c]
                        except: pass
                        
                        try: 
                            p_s = nx.shortest_path(G, s_node, e_node, 'length')
                            sho_segs.extend(extract_real_geometry(p_s))
                            l, s, w = get_stats_for_segment(p_s)
                            sho_len_acc += l; sho_well_acc += w
                            for c in criteria_cols: sho_stats_acc[c] += s[c]
                        except: pass
                        
                    st.session_state.main_opt_segments = opt_segs
                    st.session_state.main_sho_segments = sho_segs
                    
                    st.session_state.dist_app = calc_real_physical_distance(st.session_state.approach_segments)
                    st.session_state.dist_opt = calc_real_physical_distance(st.session_state.main_opt_segments)
                    st.session_state.dist_sho = calc_real_physical_distance(st.session_state.main_sho_segments)
                    st.session_state.route_mode = "A_TO_B"
                    
                    st.session_state.opt_stats = opt_stats_acc
                    st.session_state.sho_stats = sho_stats_acc
                    st.session_state.opt_len = opt_len_acc
                    st.session_state.sho_len = sho_len_acc
                    st.session_state.opt_well = opt_well_acc
                    st.session_state.sho_well = sho_well_acc
                    
                    markers = [{"name": "현 위치", "lat": u_lat, "lon": u_lon, "color": "#FF9500"}]
                    for h in set(seq): markers.append({"name": h, "lat": hubs_info[h]['coords'][0], "lon": hubs_info[h]['coords'][1], "color": hubs_info[h]['color']})
                    st.session_state.marker_data = markers
                    
                    st.session_state.page = 'result'
                    st.rerun()
                    
        elif mode == "🔄 순환형 코스 (Loop)":
            if df_loop_merged.empty:
                st.error("데이터가 없습니다.")
            else:
                loop_list = sorted(df_loop_merged[df_loop_merged['ROUTE_ID'].str.startswith(start_hub)]['ROUTE_ID'].unique().tolist())
                selected_loop = st.selectbox('순환 코스 선택', loop_list, format_func=lambda x: x.replace("_초급","").replace("_중급",""))
                
                if st.button("순환 경로 생성 🚀", type="primary"):
                    with st.spinner("경로 계산 중..."):
                        u_lat, u_lon = st.session_state.user_location
                        user_node = get_nearest_node(u_lon, u_lat)
                        start_hub_node = get_nearest_node(hubs_info[start_hub]['coords'][1], hubs_info[start_hub]['coords'][0])
                        
                        try: 
                            p_app = nx.shortest_path(G, source=user_node, target=start_hub_node, weight='length')
                            st.session_state.approach_segments = extract_real_geometry(p_app)
                        except: st.session_state.approach_segments = []
                        
                        target_data = df_loop_merged[df_loop_merged['ROUTE_ID'] == selected_loop]
                        l_segs = []
                        for _, row in target_data.iterrows():
                            fid = str(row['MATCH_ID'])
                            geom = geom_dict.get(fid)
                            if geom and geom.geom_type == 'LineString':
                                l_segs.append([[lat, lon] for lon, lat in geom.coords])
                                
                        st.session_state.loop_segments = l_segs
                        st.session_state.dist_app = calc_real_physical_distance(st.session_state.approach_segments)
                        st.session_state.dist_loop = calc_real_physical_distance(st.session_state.loop_segments)
                        st.session_state.route_mode = "LOOP"
                        
                        st.session_state.marker_data = [
                            {"name": "현 위치", "lat": u_lat, "lon": u_lon, "color": "#FF9500"},
                            {"name": start_hub, "lat": hubs_info[start_hub]['coords'][0], "lon": hubs_info[start_hub]['coords'][1], "color": hubs_info[start_hub]['color']}
                        ]
                        
                        st.session_state.page = 'result'
                        st.rerun()

        if st.button("⬅️ 현재 위치 변경", type="secondary"):
            st.session_state.page = 'step1_location'
            st.rerun()

elif st.session_state.page == 'result':
    app_json = json.dumps(st.session_state.approach_segments)
    opt_json = json.dumps(st.session_state.main_opt_segments)
    sho_json = json.dumps(st.session_state.main_sho_segments)
    loop_json = json.dumps(st.session_state.loop_segments)
    markers_json = json.dumps(st.session_state.marker_data)
    fountains_json = json.dumps(fountains_data) 
    boundary_json = json.dumps(sd_boundary) if sd_boundary else "null"
    
    opt_stats_json = json.dumps(st.session_state.get('opt_stats', {c: 0.0 for c in criteria_cols}))
    sho_stats_json = json.dumps(st.session_state.get('sho_stats', {c: 0.0 for c in criteria_cols}))
    opt_len_val = st.session_state.get('opt_len', 0)
    sho_len_val = st.session_state.get('sho_len', 0)
    opt_well_val = st.session_state.get('opt_well', 0)
    sho_well_val = st.session_state.get('sho_well', 0)
    
    u_lat, u_lon = st.session_state.user_location
    mode = st.session_state.route_mode

    app_html = """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            :root {
                --bg-base: #0A0A0F; --bg-elevated: rgba(20, 20, 30, 0.95);
                --neon-cyan: #00F5FF; --neon-pink: #FF2D78; --neon-green: #39FF14;
                --text-primary: #F0F0FF; --text-secondary: #8A8AA0;
            }
            body { margin: 0; padding: 0; font-family: sans-serif; overflow: hidden; color: var(--text-primary); }
            #map { width: 100%; height: 100vh; position: absolute; z-index: 1; top: 0; }
            .leaflet-control-attribution { display: none !important; }
            .leaflet-layer, .leaflet-control-zoom-in, .leaflet-control-zoom-out { filter: invert(100%) hue-rotate(180deg) brightness(95%) contrast(90%); }
            
            .label-tooltip {
                background: transparent !important; border: none !important; box-shadow: none !important;
                color: #FFFFFF !important; font-weight: 800 !important; font-size: 10px !important;
                text-shadow: 0 0 5px #000, 0 0 10px #000 !important; margin-top: -5px !important;
                white-space: nowrap !important; text-align: center !important; pointer-events: none;
            }
            .label-tooltip::before, .label-tooltip::after { display: none !important; }

            .custom-water-icon { 
                display: flex !important; 
                justify-content: center !important; 
                align-items: center !important;
                font-size: 10px !important;
                background: none !important;
                border: none !important;
                box-shadow: none !important;
            }

            .bottom-sheet { 
                position: absolute; bottom: 0; left: 0; width: 100%; 
                background: var(--bg-elevated); backdrop-filter: blur(20px); border-top: 1px solid rgba(255, 255, 255, 0.1); 
                border-radius: 32px 32px 0 0; z-index: 100; padding: 25px; box-sizing: border-box;
                max-height: 60vh; overflow-y: auto;
                -ms-overflow-style: none; scrollbar-width: none;
            }
            .bottom-sheet::-webkit-scrollbar { display: none; }
            
            .toggle-panel { display: flex; gap: 8px; margin-bottom: 15px; }
            .toggle-btn { flex: 1; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: #FFF; padding: 10px 5px; border-radius: 12px; font-size: 12px; font-weight: bold; cursor: pointer; transition: 0.2s;}
            .toggle-btn.active { background: rgba(0,245,255,0.15); border-color: var(--neon-cyan); color: var(--neon-cyan); }
            
            .stats-grid { display: flex; justify-content: space-between; text-align: center; margin-bottom: 15px; }
            .stat-box { flex: 1; background: rgba(255,255,255,0.05); padding: 12px 5px; border-radius: 12px; margin: 0 5px; border: 1px solid rgba(255,255,255,0.05); }
            .stat-val { font-size: 18px; font-weight: 900; color: #FFF; margin-top: 5px; }
            .stat-label { font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; }

            .compare-modal { display: block; background: rgba(0,0,0,0.6); padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); margin-bottom: 15px; }
            
            .comp-row { display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.05); padding: 8px 0; font-size: 13px; }
            .comp-row:last-child { border: none; }
            .comp-col { width: 33%; text-align: center; }

            .compare-btn { width: 100%; background: rgba(255,45,120,0.1); border: 1px solid var(--neon-cyan); color: var(--neon-cyan); padding: 12px; border-radius: 12px; font-weight: bold; font-size: 14px; margin-bottom: 15px; cursor: pointer; transition: 0.3s;}
            .compare-btn:hover { background: var(--neon-cyan); color: #000; }

            .primary-btn { background: linear-gradient(135deg, #00F5FF, #0080FF); color: #000; font-weight: 900; font-size: 16px; border: none; border-radius: 16px; padding: 16px; width: 100%; cursor: pointer;}
            .btn-back { position: absolute; top: 20px; left: 20px; z-index: 2000; background: rgba(0,0,0,0.7); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 10px 15px; border-radius: 12px; cursor: pointer; font-weight: bold;}
            
            .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 3000; justify-content: center; align-items: center; padding: 20px; box-sizing: border-box; backdrop-filter: blur(5px); }
            .modal-content { background: var(--bg-elevated); border: 1px solid var(--neon-cyan); border-radius: 20px; width: 100%; max-width: 400px; max-height: 85vh; padding: 20px; overflow-y: auto; color: #FFF; box-shadow: 0 10px 30px rgba(0,245,255,0.2);}
            .modal-content::-webkit-scrollbar { display: none; }
            .table-row { display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.1); padding: 10px 0; font-size: 13px;}
        </style>
    </head>
    <body>
    <button class="btn-back" onclick="window.parent.location.reload()">⬅️ RE-PLAN</button>
    <div id="map"></div>
    
    <div class="bottom-sheet">
        <div class="toggle-panel">
            <button id="btn-app" class="toggle-btn active" onclick="toggleLayer('app')">🚶‍♂️ 접근</button>
            <button id="btn-main" class="toggle-btn active" onclick="toggleLayer('main')">🏃 코스</button>
            <button id="btn-water" class="toggle-btn" onclick="toggleLayer('water')">💧 음수대</button>
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-label">거리</div>
                <div class="stat-val" id="val-dist">--</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">시간</div>
                <div class="stat-val" id="val-time">--</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">칼로리</div>
                <div class="stat-val" id="val-kcal">--</div>
            </div>
        </div>

        <div id="compare-section" style="display: none;">
            
            <div id="imp-text" style="text-align: center; color: var(--neon-cyan); font-size: 13px; font-weight: 800; margin-bottom: 12px; background: rgba(0, 245, 255, 0.1); padding: 10px; border-radius: 12px; border: 1px solid rgba(0,245,255,0.3);">
                ✨ 계산 중...
            </div>
            
            <div class="compare-modal" id="compare-modal">
                <div class="comp-row" style="font-weight: 800; border-bottom: 1px solid #444; padding-bottom: 10px;">
                    <div class="comp-col">항목</div>
                    <div class="comp-col" style="color: var(--neon-cyan);">✨ 웰니스</div>
                    <div class="comp-col" style="color: var(--neon-pink);">⚡ 최단</div>
                </div>
                <div class="comp-row">
                    <div class="comp-col" style="color: var(--text-secondary);">총 거리</div>
                    <div class="comp-col" id="cmp-d-o" style="font-weight:bold;">--</div>
                    <div class="comp-col" id="cmp-d-s" style="font-weight:bold;">--</div>
                </div>
                <div class="comp-row">
                    <div class="comp-col" style="color: var(--text-secondary);">예상 시간</div>
                    <div class="comp-col" id="cmp-t-o" style="font-weight:bold;">--</div>
                    <div class="comp-col" id="cmp-t-s" style="font-weight:bold;">--</div>
                </div>
                <div class="comp-row">
                    <div class="comp-col" style="color: var(--text-secondary);">소모 칼로리</div>
                    <div class="comp-col" id="cmp-k-o" style="font-weight:bold;">--</div>
                    <div class="comp-col" id="cmp-k-s" style="font-weight:bold;">--</div>
                </div>
            </div>
            
            <button class="compare-btn" onclick="openDetailsModal()">📊 웰니스 데이터 상세 보기</button>
        </div>

        <button class="primary-btn">START RUNNING</button>
    </div>
    
    <div id="details-modal" class="modal-overlay">
        <div class="modal-content">
            <h3 style="margin-top: 0; text-align: center; font-weight: 900; letter-spacing: -0.5px;">🌱 웰니스 지수 상세 분석</h3>
            <p style="text-align:center; color: var(--text-secondary); font-size: 11px; margin-bottom: 20px;">각 가중치 지표별 1m당 평균 수치 비교입니다.</p>
            
            <div class="table-row" style="font-weight: 800; border-bottom: 2px solid #555; color: var(--text-secondary);">
                <div style="width: 30%;">항목</div>
                <div style="width: 20%; text-align:center;">최단</div>
                <div style="width: 25%; text-align:center; color: var(--neon-cyan);">웰니스</div>
                <div style="width: 25%; text-align:right;">증감</div>
            </div>
            
            <div id="details-table-body">
                </div>
            
            <button class="primary-btn" style="margin-top: 20px; background: rgba(255,255,255,0.1); color: #FFF;" onclick="closeDetailsModal()">닫기</button>
        </div>
    </div>

    <script>
        var approachSegs = ___APP_JSON___;
        var optSegs = ___OPT_JSON___;
        var shoSegs = ___SHO_JSON___;
        var loopSegs = ___LOOP_JSON___;
        var markers = ___MARKERS_JSON___;
        var fountainsData = ___FOUNTAINS_JSON___; 
        var boundaryData = ___BOUNDARY_JSON___;
        var mode = "___MODE___";
        
        var dApp = ___DIST_APP___;
        var dOpt = ___DIST_OPT___;
        var dSho = ___DIST_SHO___;
        var dLoop = ___DIST_LOOP___;
        
        var optStats = ___OPT_STATS_JSON___;
        var shoStats = ___SHO_STATS_JSON___;
        var optLen = ___OPT_LEN_VAL___;
        var shoLen = ___SHO_LEN_VAL___;
        var optWell = ___OPT_WELL_VAL___;
        var shoWell = ___SHO_WELL_VAL___;
        var criteria = ['교차로', '보도폭', '대기질', '유동인구', '보도재질', '교통사고', 'CCTV', '녹지및그늘', '편의점', '경사', '하천', '신호등', '소음'];

        var map = L.map('map', { zoomControl: false, attributionControl: false }).setView([___U_LAT___, ___U_LON___], 15);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png').addTo(map);

        if(boundaryData) {
            L.geoJSON(boundaryData, {
                style: {color: '#FFFFFF', weight: 2, fillOpacity: 0, opacity: 0.6, dashArray: '5,5'}
            }).addTo(map);
        }

        var appLayer = L.featureGroup().addTo(map);
        var mainLayer = L.featureGroup().addTo(map);
        var waterLayer = L.featureGroup();

        var waterIcon = L.divIcon({
            html: '💧',
            className: 'custom-water-icon',
            iconSize: [12, 12],
            iconAnchor: [6, 6]
        });

        fountainsData.forEach(f => {
            L.marker([f.lat, f.lon], { icon: waterIcon, interactive: false }).addTo(waterLayer);
        });

        markers.forEach(m => {
            L.circleMarker([m.lat, m.lon], { color: m.color, radius: 7, fillOpacity: 1, weight: 2, fillColor: '#111' })
             .bindTooltip(
                m.name, 
                { permanent: true, direction: 'top', className: 'label-tooltip', offset: [0, -5], noHide: true }
             )
             .addTo(map);
        });

        if (approachSegs.length > 0) L.polyline(approachSegs, { color: '#FF9500', weight: 4, dashArray: '6, 8', opacity: 0.9 }).addTo(appLayer);

        if (mode === "A_TO_B") {
            document.getElementById('compare-section').style.display = 'block';
            if (shoSegs.length > 0) L.polyline(shoSegs, { color: '#FF2D78', weight: 4, opacity: 0.4, dashArray: '5,5' }).addTo(mainLayer);
            if (optSegs.length > 0) {
                L.polyline(optSegs, { color: '#00F5FF', weight: 14, opacity: 0.15 }).addTo(mainLayer);
                L.polyline(optSegs, { color: '#00F5FF', weight: 6, opacity: 1.0 }).addTo(mainLayer);
            }
            
            var impPct = 0;
            if (shoWell > 0 && shoWell > optWell) {
                impPct = ((shoWell - optWell) / shoWell) * 100;
            }
            var impDiv = document.getElementById('imp-text');
            if (impPct > 0) {
                impDiv.innerHTML = "✨ 최단 경로보다 <b>약 " + Math.round(impPct) + "%</b> 더 쾌적한 웰니스 코스입니다!";
            } else {
                impDiv.innerHTML = "✨ 최단 거리이면서 동시에 쾌적한 최적의 웰니스 코스입니다!";
            }
            
            var tbody = document.getElementById("details-table-body");
            criteria.forEach(function(c) {
                var o_val = optLen > 0 ? (optStats[c] / optLen) : 0;
                var s_val = shoLen > 0 ? (shoStats[c] / shoLen) : 0;
                var diff = o_val - s_val;
                
                var diffStr = "-";
                if (Math.abs(diff) > 0.01) {
                    if (diff > 0) diffStr = "<span style='color:#39FF14; font-weight:bold;'>▲ " + diff.toFixed(2) + "</span>";
                    else diffStr = "<span style='color:#FF2D78; font-weight:bold;'>▼ " + Math.abs(diff).toFixed(2) + "</span>";
                }

                var displayName = (c === '편의점') ? '야간 조명' : c;

                var tr = "<div class='table-row'>" +
                         "<div style='width: 30%; font-weight:bold;'>" + displayName + "</div>" +
                         "<div style='width: 20%; text-align:center; color: var(--text-secondary);'>" + s_val.toFixed(2) + "</div>" +
                         "<div style='width: 25%; text-align:center; color: var(--neon-cyan); font-weight:bold;'>" + o_val.toFixed(2) + "</div>" +
                         "<div style='width: 25%; text-align:right;'>" + diffStr + "</div>" +
                         "</div>";
                tbody.insertAdjacentHTML('beforeend', tr);
            });
            
        } else if (mode === "LOOP") {
            if (loopSegs.length > 0) {
                L.polyline(loopSegs, { color: '#39FF14', weight: 14, opacity: 0.15 }).addTo(mainLayer);
                L.polyline(loopSegs, { color: '#39FF14', weight: 6, opacity: 1.0 }).addTo(mainLayer);
            }
        }
        
        setTimeout(() => map.fitBounds(mainLayer.getBounds(), { paddingBottomRight: [0, 300], paddingTopLeft: [20, 50] }), 500);

        var appVis = true, mainVis = true, waterVis = false;
        
        function toggleLayer(type) {
            if(type === 'app') {
                appVis = !appVis;
                appVis ? map.addLayer(appLayer) : map.removeLayer(appLayer);
                document.getElementById('btn-app').classList.toggle('active', appVis);
            } else if (type === 'main') {
                mainVis = !mainVis;
                mainVis ? map.addLayer(mainLayer) : map.removeLayer(mainLayer);
                document.getElementById('btn-main').classList.toggle('active', mainVis);
            } else if (type === 'water') {
                waterVis = !waterVis;
                waterVis ? map.addLayer(waterLayer) : map.removeLayer(waterLayer);
                document.getElementById('btn-water').classList.toggle('active', waterVis);
            }
            updateStats(); 
        }

        function calc(meters) {
            let km = (meters / 1000).toFixed(2);
            let mins = Math.round((meters / 1000) * 6);
            let kcal = Math.round((meters / 1000) * 65);
            return { km: km + ' km', mins: mins + ' 분', kcal: kcal + ' kcal' };
        }

        function updateStats() {
            let totalDist = 0;
            if(appVis) totalDist += dApp;
            if(mainVis) totalDist += (mode === "A_TO_B" ? dOpt : dLoop);
            
            let st = calc(totalDist);
            document.getElementById('val-dist').innerText = st.km;
            document.getElementById('val-time').innerText = st.mins;
            document.getElementById('val-kcal').innerText = st.kcal;
            
            if(mode === "A_TO_B") {
                let o = calc(dOpt), s = calc(dSho);
                document.getElementById('cmp-d-o').innerText = o.km;
                document.getElementById('cmp-d-s').innerText = s.km;
                document.getElementById('cmp-t-o').innerText = o.mins;
                document.getElementById('cmp-t-s').innerText = s.mins;
                document.getElementById('cmp-k-o').innerText = o.kcal;
                document.getElementById('cmp-k-s').innerText = s.kcal;
            }
        }
        
        function openDetailsModal() { document.getElementById('details-modal').style.display = 'flex'; }
        function closeDetailsModal() { document.getElementById('details-modal').style.display = 'none'; }
        
        updateStats();
    </script>
    </body>
    </html>
    """
    
    app_html = app_html.replace("___APP_JSON___", app_json)
    app_html = app_html.replace("___OPT_JSON___", opt_json)
    app_html = app_html.replace("___SHO_JSON___", sho_json)
    app_html = app_html.replace("___LOOP_JSON___", loop_json)
    app_html = app_html.replace("___MARKERS_JSON___", markers_json)
    app_html = app_html.replace("___FOUNTAINS_JSON___", fountains_json)
    app_html = app_html.replace("___BOUNDARY_JSON___", boundary_json)
    app_html = app_html.replace("___MODE___", mode)
    app_html = app_html.replace("___U_LAT___", str(u_lat))
    app_html = app_html.replace("___U_LON___", str(u_lon))
    app_html = app_html.replace("___DIST_APP___", str(st.session_state.dist_app))
    app_html = app_html.replace("___DIST_OPT___", str(st.session_state.dist_opt))
    app_html = app_html.replace("___DIST_SHO___", str(st.session_state.dist_sho))
    app_html = app_html.replace("___DIST_LOOP___", str(st.session_state.dist_loop))
    
    app_html = app_html.replace("___OPT_STATS_JSON___", opt_stats_json)
    app_html = app_html.replace("___SHO_STATS_JSON___", sho_stats_json)
    app_html = app_html.replace("___OPT_LEN_VAL___", str(opt_len_val))
    app_html = app_html.replace("___SHO_LEN_VAL___", str(sho_len_val))
    app_html = app_html.replace("___OPT_WELL_VAL___", str(opt_well_val))
    app_html = app_html.replace("___SHO_WELL_VAL___", str(sho_well_val))

    components.html(app_html, height=900, scrolling=False)
