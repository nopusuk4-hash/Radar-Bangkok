import numpy as np
import requests
import math
import os
import pandas as pd
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
import folium
from branca.element import Template, MacroElement

# --- ตั้งค่าเบื้องต้น ---
STEP_KM = 0.4
RADAR_RANGE_KM = 60.0
CONFIGS = {
    "Nong Chok (หนองจอก)": {"url": "https://weather.bangkok.go.th/Images/Radar/radar.gif", "lat": 13.861, "lon": 100.862},
    "Nong Khaem (หนองแขม)": {"url": "https://weather.bangkok.go.th/Images/Radar/nkradar.gif", "lat": 13.701, "lon": 100.338}
}

def rgb_to_dbz(r, g, b):
    r, g, b = int(r), int(g), int(b)
    rain_colors = [
        ((255, 0, 255), 60.0), ((255, 0, 0), 50.0), ((255, 128, 0), 45.0),
        ((255, 255, 0), 35.0), ((0, 255, 0), 20.0), ((0, 200, 0), 15.0)
    ]
    for target, dbz in rain_colors:
        tr, tg, tb = int(target[0]), int(target[1]), int(target[2])
        if math.sqrt((r-tr)**2 + (g-tg)**2 + (b-tb)**2) < 55: return dbz
    return 0

def get_dbz_color(dbz):
    if dbz >= 60: return '#FF00FF'
    if dbz >= 50: return '#FF0000'
    if dbz >= 40: return '#FF8000'
    if dbz >= 30: return '#FFFF00'
    if dbz >= 20: return '#00FF00'
    return '#008000'

# ดึงเวลาปัจจุบัน (ปรับเป็นเวลาไทย GMT+7)
now = datetime.utcnow() + timedelta(hours=7)
timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
date_str = now.strftime('%Y-%m-%d')

all_rain_data = []
csv_data = [] # สำหรับเตรียมบันทึกลง CSV

for name, conf in CONFIGS.items():
    try:
        res = requests.get(conf["url"], headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        gif = Image.open(BytesIO(res.content))
        gif.seek(gif.n_frames - 1)
        img = np.array(gif.convert('RGB'))
        px_per_km = 300.0 / 60.0
        grid = np.arange(-RADAR_RANGE_KM, RADAR_RANGE_KM + STEP_KM, STEP_KM)
        for y_km in grid:
            for x_km in grid:
                if math.sqrt(x_km**2 + y_km**2) > RADAR_RANGE_KM: continue
                px, py = int(425 + (x_km * px_per_km)), int(380 - (y_km * px_per_km))
                if 0 <= px < img.shape[1] and 0 <= py < img.shape[0]:
                    dbz = rgb_to_dbz(*img[py, px])
                    if dbz > 0:
                        lat = conf["lat"] + (y_km/111.0)
                        lon = conf["lon"] + (x_km/(111.0*math.cos(math.radians(conf["lat"]))))
                        all_rain_data.append([lat, lon, dbz])
                        csv_data.append([timestamp_str, name, lat, lon, dbz])
    except: pass

# ==========================================
# 1. แอบบันทึกข้อมูลดิบลงไฟล์ CSV (แยกตามวัน)
# ==========================================
if csv_data:
    os.makedirs("data", exist_ok=True) # สร้างโฟลเดอร์ชื่อ data
    csv_filename = f"data/radar_{date_str}.csv"
    df = pd.DataFrame(csv_data, columns=['Timestamp', 'Station', 'Latitude', 'Longitude', 'dBZ'])
    
    if os.path.exists(csv_filename):
        # ถ้ามีไฟล์ของวันนี้แล้ว ให้เอาไปต่อท้าย (Append)
        df.to_csv(csv_filename, mode='a', header=False, index=False)
    else:
        # ถ่ายังไม่มี (ขึ้นวันใหม่) ให้สร้างใหม่พร้อมหัวตาราง
        df.to_csv(csv_filename, index=False)

# ==========================================
# 2. สร้างแผนที่ (เพิ่มหมุดและรัศมี)
# ==========================================
# ซูมออกนิดนึง (zoom_start=10) เพื่อให้เห็นวงกลมชัดขึ้น
m = folium.Map(location=[13.75, 100.5], zoom_start=10, tiles='https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', attr='©CartoDB')

# วาดสถานีและวงกลมรัศมี 60 กม.
for name, conf in CONFIGS.items():
    folium.Marker(
        location=[conf["lat"], conf["lon"]],
        popup=f"<b>สถานีเรดาร์:</b> {name}",
        icon=folium.Icon(color='blue', icon='info-sign')
    ).add_to(m)
    
    folium.Circle(
        location=[conf["lat"], conf["lon"]],
        radius=RADAR_RANGE_KM * 1000, # รัศมี 60 กิโลเมตร
        color='blue', weight=1, fill=False, dash_array='5, 5',
        popup=f"ขอบเขต 60 กม. ({name})"
    ).add_to(m)

# พลอตจุดฝน
for p in all_rain_data:
    folium.CircleMarker(
        location=[p[0], p[1]], radius=2.5,
        color=get_dbz_color(p[2]), fill=True, weight=0, fill_opacity=0.75,
        popup=f"{p[2]} dBZ"
    ).add_to(m)

legend_html = """
{% macro html(this, kwargs) %}
<div style="position: fixed; bottom: 30px; left: 30px; width: 170px; background-color: white; border:2px solid #ccc; z-index:9999; font-size:12px; padding: 10px; border-radius: 8px;">
    <b>ความแรงฝน (dBZ)</b><br>
    <i style="background:#FF00FF;width:12px;height:12px;display:inline-block"></i> 60+ (หนักมาก)<br>
    <i style="background:#FF0000;width:12px;height:12px;display:inline-block"></i> 50-60 (หนัก)<br>
    <i style="background:#FF8000;width:12px;height:12px;display:inline-block"></i> 40-50 (กลาง)<br>
    <i style="background:#FFFF00;width:12px;height:12px;display:inline-block"></i> 30-40 (อ่อน)<br>
    <i style="background:#00FF00;width:12px;height:12px;display:inline-block"></i> 20-30 (เบา)
</div>
{% endmacro %}
"""
macro = MacroElement()
macro._template = Template(legend_html)
m.get_root().add_child(macro)

# บันทึกทับไฟล์
m.save("index.html")
