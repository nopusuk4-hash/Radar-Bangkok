import numpy as np
import requests
import pandas as pd
import math
import os
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
import folium
from branca.element import Template, MacroElement

# ==========================================
# 1. ฟังก์ชันดึงภาพเรดาร์ล่าสุด (ตามต้นฉบับเป๊ะ)
# ==========================================
def get_latest_radar_rgb(url, station_name):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=15)
        gif = Image.open(BytesIO(res.content))
        frames = []
        try:
            while True:
                frames.append(gif.copy())
                gif.seek(gif.tell() + 1)
        except EOFError: pass
        return np.array(frames[-1].convert('RGB'))
    except: return None

# ==========================================
# 2. ฟังก์ชันวิเคราะห์ความแรงฝน (dBZ) (ตามต้นฉบับเป๊ะ)
# ==========================================
def rgb_to_dbz(r, g, b):
    r, g, b = int(r), int(g), int(b)
    # สเกลสีมาตรฐาน (ม่วง-แดง-ส้ม-เหลือง-เขียว)
    rain_colors = [
        ((255, 0, 255), 60.0), # หนักมาก
        ((255, 0, 0), 50.0),   # หนัก
        ((255, 128, 0), 45.0), # ปานกลาง-หนัก
        ((255, 255, 0), 35.0), # ปานกลาง
        ((0, 255, 0), 20.0),   # เบา
        ((0, 200, 0), 15.0)    # ละออง
    ]
    for target, dbz in rain_colors:
        tr, tg, tb = int(target[0]), int(target[1]), int(target[2])
        dist = math.sqrt((r - tr)**2 + (g - tg)**2 + (b - tb)**2)
        if dist < 55: return dbz
    return 0

def get_dbz_color(dbz):
    if dbz >= 60: return '#FF00FF'
    if dbz >= 50: return '#FF0000'
    if dbz >= 40: return '#FF8000'
    if dbz >= 30: return '#FFFF00'
    if dbz >= 20: return '#00FF00'
    return '#008000'

# ==========================================
# 3. ประมวลผลข้อมูลเรดาร์ (400m Grid)
# ==========================================
RADAR_RANGE_KM = 60.0
STEP_KM = 0.4 # ระยะ 400 เมตร
configs = {
    "Nong Chok": {"url": "https://weather.bangkok.go.th/Images/Radar/radar.gif", "lat": 13.861, "lon": 100.862},
    "Nong Khaem": {"url": "https://weather.bangkok.go.th/Images/Radar/nkradar.gif", "lat": 13.701, "lon": 100.338}
}

# เตรียมตัวแปรสำหรับเวลาและ CSV (จำเป็นสำหรับ GitHub Actions)
now = datetime.utcnow() + timedelta(hours=7)
timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
date_str = now.strftime('%Y-%m-%d')

all_rain_data = []
csv_data = [] # เก็บข้อมูลตารางสำหรับ GitHub

for name, conf in configs.items():
    img = get_latest_radar_rgb(conf["url"], name)
    if img is not None:
        print(f"📡 กำลังสแกนเรดาร์สถานี: {name}")
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

# ==========================================
# 4. เซฟข้อมูล CSV ให้ GitHub Actions รับรู้การเปลี่ยนแปลง
# ==========================================
os.makedirs("data", exist_ok=True)
csv_filename = f"data/radar_{date_str}.csv"
df = pd.DataFrame(csv_data, columns=['Timestamp', 'Station', 'Latitude', 'Longitude', 'dBZ'])

if os.path.exists(csv_filename):
    if not df.empty:
        df.to_csv(csv_filename, mode='a', header=False, index=False)
else:
    df.to_csv(csv_filename, index=False)

print(f"💾 ตรวจพบจุดฝนทั้งหมด: {len(csv_data)} จุด")

# ==========================================
# 5. สร้างแผนที่ (ใช้ CartoDB Voyager ดูง่ายกว่า)
# ==========================================
m = folium.Map(location=[13.75, 100.5], zoom_start=11, tiles='https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', attr='©CartoDB')

# วาดจุดฝน
for p in all_rain_data:
    folium.CircleMarker(
        location=[p[0], p[1]], radius=2.5,
        color=get_dbz_color(p[2]), fill=True, weight=0, fill_opacity=0.75,
        popup=f"Intensity: {p[2]} dBZ"
    ).add_to(m)

# 🎨 Legend (ตามที่คุณออกแบบไว้)
legend_html = """
{% macro html(this, kwargs) %}
<div style="
    position: fixed; bottom: 30px; left: 30px; width: 170px; 
    background-color: white; border:2px solid #ccc; z-index:9999; font-size:12px;
    padding: 10px; border-radius: 8px; box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
    ">
    <b style="font-size:13px;">ระดับความแรงฝน (dBZ)</b><br>
    <i style="background:#FF00FF;width:12px;height:12px;display:inline-block;margin-top:5px;"></i> 60+ (หนักมาก)<br>
    <i style="background:#FF0000;width:12px;height:12px;display:inline-block"></i> 50-60 (หนัก)<br>
    <i style="background:#FF8000;width:12px;height:12px;display:inline-block"></i> 40-50 (ปานกลาง)<br>
    <i style="background:#FFFF00;width:12px;height:12px;display:inline-block"></i> 30-40 (กำลังอ่อน)<br>
    <i style="background:#00FF00;width:12px;height:12px;display:inline-block"></i> 20-30 (เบา)<br>
    <i style="background:#008000;width:12px;height:12px;display:inline-block"></i> 15-20 (ละออง)
</div>
{% endmacro %}
"""
macro = MacroElement()
macro._template = Template(legend_html)
m.get_root().add_child(macro)

# บันทึกเป็น index.html แทน เพื่อให้ GitHub Pages แสดงผลได้
m.save("index.html")
print("🎉 เสร็จเรียบร้อย! แผนที่ปรับปรุงใหม่บันทึกที่: index.html")
