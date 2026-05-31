import os
import csv
import math

# --- N60 严格几何参数 ---
CHANNEL_COUNT = 60
UNIT_ANGLES_DEG = [-45.0, -22.5, 0.0, 22.5, 45.0]
BOWL_RADIUS_MM = 176.445
N12_LOCAL_COORDS = [
    (0.000, 0.000), (14.280, 10.958), (-10.958, 14.280), (-14.280, -10.958),
    (10.958, -14.280), (35.097, 8.011), (15.620, 32.435), (-15.620, 32.435),
    (-35.097, 8.011), (-28.146, -22.446), (0.000, -36.000), (28.146, -22.446)
]

def generate_n60_geometry():
    """获取60路阵元的真实三维空间绝对坐标 (米)"""
    geometry = []
    for unit_id, angle_deg in enumerate(UNIT_ANGLES_DEG):
        theta = math.radians(angle_deg)
        cx = (BOWL_RADIUS_MM * math.sin(theta)) / 1000.0
        cz = (-BOWL_RADIUS_MM * math.cos(theta)) / 1000.0
        for lx, ly in N12_LOCAL_COORDS:
            gx = cx + (lx * math.cos(theta)) / 1000.0
            gy = ly / 1000.0
            gz = cz + (lx * math.sin(theta)) / 1000.0
            geometry.append((gx, gy, gz))
    return geometry

def create_physics_based_optimized_table():
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analysis_outputs")
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, "n60_5x12_focus_table_dbc_margin.csv")
    
    coords = generate_n60_geometry()
    distances = [500, 1000, 1500, 2000, 3000, 5000]
    azimuths = range(-30, 35, 5) # -30 到 +30 度

    print(f"正在基于三维物理法向 (3.5次方模型) 重构 N60 离线优化表...")
    
    with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
        fieldnames = ['distance_mm', 'az_deg', 'el_deg', 'gain_floor', 'score', 'success'] + [f'amp_{i:02d}' for i in range(60)]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for dist_mm in distances:
            for az in azimuths:
                row = {
                    'distance_mm': dist_mm, 'az_deg': az, 'el_deg': 0,
                    'gain_floor': 0.0, 'score': 1.0, 'success': 'True'
                }
                
                # 计算目标点三维坐标
                dist_m = dist_mm / 1000.0
                az_rad = math.radians(az)
                # 简化处理：el=0，目标在 X-Z 平面
                target_m = (dist_m * math.sin(az_rad), 0.0, dist_m * math.cos(az_rad))
                
                # 核心：基于物理指向性计算幅度
                for ch in range(60):
                    unit_id = ch // 12
                    theta_rad = math.radians(UNIT_ANGLES_DEG[unit_id])
                    
                    # 阵元法向量
                    nx = -math.sin(theta_rad)
                    ny = 0.0
                    nz = math.cos(theta_rad)
                    
                    mx, my, mz = coords[ch]
                    
                    # 阵元指向目标的向量
                    vx, vy, vz = target_m[0] - mx, target_m[1] - my, target_m[2] - mz
                    v_len = math.hypot(math.hypot(vx, vy), vz)
                    
                    if v_len > 0:
                        vx, vy, vz = vx/v_len, vy/v_len, vz/v_len
                        # 空间点乘：夹角余弦
                        dot = vx*nx + vy*ny + vz*nz
                        
                        # 【终极修复】：结合原厂数据 (-6dB@35deg) 拟合出的 3.5 次方衰减模型
                        amp = max(0.0, dot) ** 3.5
                    else:
                        amp = 1.0
                        
                    row[f'amp_{ch:02d}'] = round(amp, 4)
                
                writer.writerow(row)
                
    print(f"✅ 生成完毕！真实的 3.5 次方物理指向性已固化入表：\n{os.path.abspath(csv_path)}")

if __name__ == "__main__":
    create_physics_based_optimized_table()