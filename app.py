import streamlit as st
import pandas as pd
import geopandas as gpd
import networkx as nx
import math
import json
import folium
import requests
from pyproj import Transformer
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import os

# --- 1. 앱 설정 및 커스텀 CSS ---
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
        .block-container { padding: 0 !important; max-width: 430px !important; margin: 0 auto !important; background-color: #0A0A0F; min-height: 100vh; overflow-x: hidden;}
        header { display: none !important; }
        footer { display: none !important; }
        iframe { border: none !important; width: 100% !important; border-radius: 0 0 24px 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        
        /* 입력창(Selectbox, Radio) 좌우 여백 확보 (잘림 방지) */
        div[data-testid="stSelectbox"], div[data-testid="stRadio"] { 
            padding: 0 20px !important; 
            box-sizing: border-box; 
        }
        
        /* 버튼 디자인 차별화 및 고급화 */
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
        
        .stMarkdown h3 { color: #FFFFFF; padding: 20px 20px 10px 20px; font-size: 22px; font-weight: 800;}
        
        /* 💡 [핵심 수정] 라디오 버튼 타이틀과 옵션 텍스트 분리 및 시인성 강화 */
        .stRadio > label { color: #8A8AA0 !important; font-size: 12px; margin-bottom: 5px; }
        div[role="radiogroup"] label p { color: #FFFFFF !important; font-weight: 700 !important; font-size: 15px !important; }
        
        .stSelectbox > label { color: #8A8AA0; font-size: 12px; margin-bottom: -5px;}
    </style>
""", unsafe_allow_html=True)

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

hubs_info = {
    "옥수역": (37.5413498, 127.0171347), "왕십리역": (37.5616302, 127.0351177),
    "금호나들목": (37.5512902, 127.0356081), "성덕정나들목": (37.5375776, 127.0454704),
    "청구아파트나들목": (37.5348428, 127.0552105), "송정체육공원": (37.5536442, 127.0672346),
    "서울숲역": (37.5465240, 127.0429873), "성삼공원": (37.5420202, 127.0602789),
    "금옥공원": (37.5534649, 127.0213021), "꽃재공원": (37.5672965, 127.0282145),
    "용답마을마당": (37.5619688, 127.0517828), "향림소공원": (37.5467465, 127.0534440)
}
hub_names = list(hubs_info.keys())

# --- 3. 데이터 로드 엔진 ---
@st.cache_data
def load_boundary():
    try:
        url = "https://raw.githubusercontent.com/southkorea/seoul-maps/master/kostat/2013/json/seoul_municipalities_geo_simple.json"
        seoul_geo = requests.get(url).json()
        return {'type': 'FeatureCollection', 'features': [f for f in seoul_geo['features'] if f['properties']['name'] == '성동구']}
    except: return None

@st.cache_resource
def load_data():
    G = nx.Graph()
    node_coords = {}
    df_loop_merged = pd.DataFrame()
    geom_dict = {}

    try:
        df_network = pd.read_csv('soengdong_wellness_network.csv')
        gdf_network = gpd.read_file('zip://soengdong_wellness_network.zip').to_crs(epsg=4326)
        
        df_network.columns = df_network.columns.str.strip().str.upper()
        gdf_network.columns = [col.strip().upper() if col != 'geometry' else 'geometry' for col in gdf_network.columns]
        
        geo_fid_col = [col for col in gdf_network.columns if col.endswith('TARGET_FID')][0]
        csv_fid_col = 'TARGET_FID' if 'TARGET_FID' in df_network.columns else df_network.columns[0]
        
        df_network[csv_fid_col] = df_network[csv_fid_col].astype(str)
        gdf_network[geo_fid_col] = gdf_network[geo_fid_col].astype(str)
        
        geom_dict = dict(zip(gdf_network[geo_fid_col], gdf_network['geometry']))
        
        for _, row in df_network.iterrows():
            s_node, e_node = f"{row['START_X']:.1f}_{row['START_Y']:.1f}", f"{row['END_X']:.1f}_{row['END_Y']:.1f}"
            fid, smooth_geom = str(row[csv_fid_col]), geom_dict.get(str(row[csv_fid_col]))
            length, wellness = row.get('SHAPE_LENGTH', 1), row.get('ROUTE_COST', 1)
            
            G.add_edge(s_node, e_node, length=length, wellness=wellness, geom=smooth_geom)
            if smooth_geom and smooth_geom.geom_type == 'LineString':
                node_coords[s_node], node_coords[e_node] = smooth_geom.coords[0], smooth_geom.coords[-1]
                
        file_name = 'Seongdong_Loop_Routes_3k_5k (1).csv'
        if os.path.exists(file_name):
            df_routes = pd.read_csv(file_name)
            df_routes.columns = df_routes.columns.str.strip().str.upper()
            df_routes['TARGET_FID'] = df_routes['TARGET_FID'].astype(str)
            df_loop_merged = pd.merge(df_routes, df_network, on='TARGET_FID', how='inner')
    except Exception as e: st.error(f"데이터 로드 실패: {e}")

    return G, node_coords, df_loop_merged, geom_dict

with st.spinner("엔진 부팅 중..."):
    sd_boundary = load_boundary()
    G, node_coords, df_loop_merged, geom_dict = load_data()

def get_nearest_node(lon, lat):
    if not node_coords: return None
    return min(node_coords.keys(), key=lambda n: math.sqrt((node_coords[n][0]-lon)**2 + (node_coords[n][1]-lat)**2))

def get_nearest_hub(lat, lon):
    return min(hubs_info.keys(), key=lambda h: math.sqrt((hubs_info[h][0]-lat)**2 + (hubs_info[h][1]-lon)**2))

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

def get_pareto_optimal_path(G, source, target, min_ratio=1.2, max_ratio=2.0):
    try:
        shortest_path = nx.shortest_path(G, source=source, target=target, weight='length')
        min_dist = sum(G[u][v].get('length', 1) for u, v in zip(shortest_path[:-1], shortest_path[1:]))
        if min_dist == 0: return shortest_path

        min_allowed_dist = min_dist * min_ratio
        max_allowed_dist = min_dist * max_ratio
        
        candidate_paths = []
        for step in range(21):
            alpha = step * 0.05
            def weight_func(u, v, d): return (d.get('length', 1) * alpha) + (d.get('wellness', 1) * (1 - alpha))
            try:
                path = nx.shortest_path(G, source=source, target=target, weight=weight_func)
                path_len = sum(G[u][v].get('length', 1) for u, v in zip(path[:-1], path[1:]))
                if path_len <= max_allowed_dist:
                    path_well = sum(G[u][v].get('wellness', 1) for u, v in zip(path[:-1], path[1:]))
                    candidate_paths.append({'path': path, 'length': path_len, 'wellness': path_well})
            except: continue
            
        if candidate_paths:
            filtered_cands = [c for c in candidate_paths if c['length'] >= min_allowed_dist]
            if filtered_cands:
                return min(filtered_cands, key=lambda x: x['wellness'])['path']
            else:
                return max(candidate_paths, key=lambda x: x['length'])['path']
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
            <p style="margin: 0 0 16px 0; color: #8A8AA0; font-size: 13px; line-height: 1.4;">지도에서 <b>현재 위치</b>를 탭하여<br>최적의 웰니스 러닝 코스를 탐색하세요.</p>
            <div style="display: flex; gap: 8px;">
                <span style="background: rgba(57, 255, 20, 0.15); color: #39FF14; border: 1px solid rgba(57,255,20,0.3); padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 800;">🌤️ 18°C 맑음</span>
                <span style="background: rgba(255, 45, 120, 0.15); color: #FF2D78; border: 1px solid rgba(255,45,120,0.3); padding: 5px 10px; border-radius: 8px; font-size: 11px; font-weight: 800;">🍃 대기질 최고</span>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='padding: 0 20px;'>", unsafe_allow_html=True)
    
    m = folium.Map(location=[37.55, 127.04], zoom_start=14, tiles=None, zoom_control=False)
    folium.TileLayer('CartoDB dark_matter', attr=' ').add_to(m)
    css_injection = "<style>.leaflet-control-attribution { display: none !important; visibility: hidden !important; }</style>"
    m.get_root().header.add_child(folium.Element(css_injection))
    
    if sd_boundary:
        folium.GeoJson(sd_boundary, style_function=lambda x: {'color': 'white', 'fillColor': 'transparent', 'weight': 2, 'opacity': 0.6, 'dashArray':'5,5'}).add_to(m)

    for name, coords in hubs_info.items():
        folium.CircleMarker(location=coords, radius=5, color='#00F5FF', fill=True, fillOpacity=0.8, popup=name).add_to(m)
        
    map_data = st_folium(m, height=450, use_container_width=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    if map_data and map_data.get('last_clicked'):
        lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
        st.session_state.user_location = (lat, lon)
        st.session_state.nearest_hub = get_nearest_hub(lat, lon)
        st.session_state.page = 'step2_course'
        st.rerun()

elif st.session_state.page == 'step2_course':
    st.markdown("<h3>🏃‍♂️ 러닝 코스</h3>", unsafe_allow_html=True)
    
    with st.container():
        start_hub = st.selectbox("📍 출발 거점", hub_names, index=hub_names.index(st.session_state.nearest_hub))
        mode = st.radio("코스 모드", ["🚩 다른 거점으로 이동 (A to B)", "🔄 순환형 코스 (Loop)"])
        
        if mode == "🚩 다른 거점으로 이동 (A to B)":
            via1 = st.selectbox("🔹 경유지 1 (선택)", ["선택 안 함"] + hub_names)
            via2 = st.selectbox("🔹 경유지 2 (선택)", ["선택 안 함"] + hub_names)
            end_drop = st.selectbox("🏁 도착 거점", [h for h in hub_names if h != start_hub])
            
            if st.button("경로 탐색 🚀", type="primary"):
                with st.spinner("최적 경로 계산 중..."):
                    seq = [start_hub]
                    if via1 != "선택 안 함": seq.append(via1)
                    if via2 != "선택 안 함": seq.append(via2)
                    seq.append(end_drop)
                    
                    u_lat, u_lon = st.session_state.user_location
                    user_node = get_nearest_node(u_lon, u_lat)
                    first_hub_node = get_nearest_node(hubs_info[start_hub][1], hubs_info[start_hub][0])
                    
                    try: 
                        p_app = nx.shortest_path(G, source=user_node, target=first_hub_node, weight='length')
                        st.session_state.approach_segments = extract_real_geometry(p_app)
                    except: st.session_state.approach_segments = []
                    
                    opt_segs, sho_segs = [], []
                    for i in range(len(seq)-1):
                        s_node = get_nearest_node(hubs_info[seq[i]][1], hubs_info[seq[i]][0])
                        e_node = get_nearest_node(hubs_info[seq[i+1]][1], hubs_info[seq[i+1]][0])
                        try: 
                            p_o = get_pareto_optimal_path(G, s_node, e_node, min_ratio=1.2, max_ratio=2.0)
                            opt_segs.extend(extract_real_geometry(p_o))
                        except: pass
                        try: 
                            p_s = nx.shortest_path(G, s_node, e_node, 'length')
                            sho_segs.extend(extract_real_geometry(p_s))
                        except: pass
                        
                    st.session_state.main_opt_segments = opt_segs
                    st.session_state.main_sho_segments = sho_segs
                    
                    st.session_state.dist_app = calc_real_physical_distance(st.session_state.approach_segments)
                    st.session_state.dist_opt = calc_real_physical_distance(st.session_state.main_opt_segments)
                    st.session_state.dist_sho = calc_real_physical_distance(st.session_state.main_sho_segments)
                    st.session_state.route_mode = "A_TO_B"
                    
                    markers = [{"name": "현 위치", "lat": u_lat, "lon": u_lon, "color": "#FF9500"}]
                    for h in set(seq): markers.append({"name": h, "lat": hubs_info[h][0], "lon": hubs_info[h][1], "color": "#00F5FF" if h==start_hub else "#FF2D78"})
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
                        start_hub_node = get_nearest_node(hubs_info[start_hub][1], hubs_info[start_hub][0])
                        
                        try: 
                            p_app = nx.shortest_path(G, source=user_node, target=start_hub_node, weight='length')
                            st.session_state.approach_segments = extract_real_geometry(p_app)
                        except: st.session_state.approach_segments = []
                        
                        target_data = df_loop_merged[df_loop_merged['ROUTE_ID'] == selected_loop]
                        l_segs = []
                        for _, row in target_data.iterrows():
                            fid = str(row['TARGET_FID'])
                            geom = geom_dict.get(fid)
                            if geom and geom.geom_type == 'LineString':
                                l_segs.append([[lat, lon] for lon, lat in geom.coords])
                                
                        st.session_state.loop_segments = l_segs
                        st.session_state.dist_app = calc_real_physical_distance(st.session_state.approach_segments)
                        st.session_state.dist_loop = calc_real_physical_distance(st.session_state.loop_segments)
                        st.session_state.route_mode = "LOOP"
                        
                        st.session_state.marker_data = [
                            {"name": "현 위치", "lat": u_lat, "lon": u_lon, "color": "#FF9500"},
                            {"name": start_hub, "lat": hubs_info[start_hub][0], "lon": hubs_info[start_hub][1], "color": "#39FF14"}
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
    boundary_json = json.dumps(sd_boundary) if sd_boundary else "null"
    
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
            
            /* 💡 거점 이름 스타일 수정 (글씨 크기 축소 및 가로 정렬 강제) */
            .label-tooltip {
                background: transparent !important; border: none !important; box-shadow: none !important;
                color: #FFF !important; 
                font-weight: 800 !important; 
                font-size: 11px !important; 
                text-shadow: 0 0 5px #000, 0 0 10px #000 !important; 
                margin-top: -12px !important;
                white-space: nowrap !important;
                pointer-events: none;
            }

            .bottom-sheet { 
                position: absolute; bottom: 0; left: 0; width: 100%; 
                background: var(--bg-elevated); backdrop-filter: blur(20px); border-top: 1px solid rgba(255, 255, 255, 0.1); 
                border-radius: 32px 32px 0 0; z-index: 100; padding: 25px; box-sizing: border-box;
                max-height: 55vh; overflow-y: auto;
                -ms-overflow-style: none; scrollbar-width: none;
            }
            .bottom-sheet::-webkit-scrollbar { display: none; }
            
            .toggle-panel { display: flex; gap: 10px; margin-bottom: 15px; }
            .toggle-btn { flex: 1; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.2); color: #FFF; padding: 10px; border-radius: 12px; font-size: 12px; font-weight: bold; cursor: pointer; transition: 0.2s;}
            .toggle-btn.active { background: rgba(0,245,255,0.15); border-color: var(--neon-cyan); color: var(--neon-cyan); }
            
            .stats-grid { display: flex; justify-content: space-between; text-align: center; margin-bottom: 15px; }
            .stat-box { flex: 1; background: rgba(255,255,255,0.05); padding: 12px 5px; border-radius: 12px; margin: 0 5px; border: 1px solid rgba(255,255,255,0.05); }
            .stat-val { font-size: 18px; font-weight: 900; color: #FFF; margin-top: 5px; }
            .stat-label { font-size: 10px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 1px; }

            .compare-btn { width: 100%; background: rgba(255,45,120,0.1); border: 1px solid var(--neon-pink); color: var(--neon-pink); padding: 12px; border-radius: 12px; font-weight: bold; font-size: 14px; margin-bottom: 15px; cursor: pointer; transition: 0.3s;}
            .compare-btn:hover { background: var(--neon-pink); color: #FFF; }

            .compare-modal { display: none; background: rgba(0,0,0,0.6); padding: 15px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); margin-bottom: 15px; }
            .comp-row { display: flex; justify-content: space-between; border-bottom: 1px solid rgba(255,255,255,0.05); padding: 8px 0; font-size: 13px; }
            .comp-row:last-child { border: none; }
            .comp-col { width: 33%; text-align: center; }

            .primary-btn { background: linear-gradient(135deg, #00F5FF, #0080FF); color: #000; font-weight: 900; font-size: 16px; border: none; border-radius: 16px; padding: 16px; width: 100%; cursor: pointer;}
            .btn-back { position: absolute; top: 20px; left: 20px; z-index: 2000; background: rgba(0,0,0,0.7); border: 1px solid rgba(255,255,255,0.2); color: white; padding: 10px 15px; border-radius: 12px; cursor: pointer; font-weight: bold;}
        </style>
    </head>
    <body>
    <button class="btn-back" onclick="window.parent.location.reload()">⬅️ RE-PLAN</button>
    <div id="map"></div>
    
    <div class="bottom-sheet">
        <div class="toggle-panel">
            <button id="btn-app" class="toggle-btn active" onclick="toggleLayer('app')">🚶‍♂️ 접근경로</button>
            <button id="btn-main" class="toggle-btn active" onclick="toggleLayer('main')">🏃 러닝코스</button>
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
            <button class="compare-btn" onclick="toggleCompare()">📊 최적/최단 경로 상세 비교</button>
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
        </div>

        <button class="primary-btn">START RUNNING</button>
    </div>

    <script>
        var approachSegs = ___APP_JSON___;
        var optSegs = ___OPT_JSON___;
        var shoSegs = ___SHO_JSON___;
        var loopSegs = ___LOOP_JSON___;
        var markers = ___MARKERS_JSON___;
        var boundaryData = ___BOUNDARY_JSON___;
        var mode = "___MODE___";
        
        var dApp = ___DIST_APP___;
        var dOpt = ___DIST_OPT___;
        var dSho = ___DIST_SHO___;
        var dLoop = ___DIST_LOOP___;

        var map = L.map('map', { zoomControl: false, attributionControl: false }).setView([___U_LAT___, ___U_LON___], 15);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png').addTo(map);

        if(boundaryData) {
            L.geoJSON(boundaryData, {
                style: {color: '#FFFFFF', weight: 2, fillOpacity: 0, opacity: 0.6, dashArray: '5,5'}
            }).addTo(map);
        }

        var appLayer = L.featureGroup().addTo(map);
        var mainLayer = L.featureGroup().addTo(map);

        markers.forEach(m => {
            L.circleMarker([m.lat, m.lon], { color: m.color, radius: 7, fillOpacity: 1, weight: 2, fillColor: '#111' })
             .bindTooltip(m.name, { 
                permanent: true, 
                direction: 'top', 
                className: 'label-tooltip', 
                offset: [0, -10],
                opacity: 1.0
             })
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
        } else if (mode === "LOOP") {
            if (loopSegs.length > 0) {
                L.polyline(loopSegs, { color: '#39FF14', weight: 14, opacity: 0.15 }).addTo(mainLayer);
                L.polyline(loopSegs, { color: '#39FF14', weight: 6, opacity: 1.0 }).addTo(mainLayer);
            }
        }
        
        setTimeout(() => map.fitBounds(mainLayer.getBounds(), { paddingBottomRight: [0, 300], paddingTopLeft: [20, 50] }), 500);

        var appVis = true, mainVis = true;
        function toggleLayer(type) {
            if(type === 'app') {
                appVis = !appVis;
                appVis ? map.addLayer(appLayer) : map.removeLayer(appLayer);
                document.getElementById('btn-app').classList.toggle('active', appVis);
            } else {
                mainVis = !mainVis;
                mainVis ? map.addLayer(mainLayer) : map.removeLayer(mainLayer);
                document.getElementById('btn-main').classList.toggle('active', mainVis);
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
        }
        
        function toggleCompare() {
            let mod = document.getElementById('compare-modal');
            mod.style.display = mod.style.display === 'none' ? 'block' : 'none';
            if(mod.style.display === 'block') {
                let o = calc(dOpt), s = calc(dSho);
                document.getElementById('cmp-d-o').innerText = o.km;
                document.getElementById('cmp-d-s').innerText = s.km;
                document.getElementById('cmp-t-o').innerText = o.mins;
                document.getElementById('cmp-t-s').innerText = s.mins;
                document.getElementById('cmp-k-o').innerText = o.kcal;
                document.getElementById('cmp-k-s').innerText = s.kcal;
            }
        }
        
        updateStats();
    </script>
    </body>
    </html>
    """
    
