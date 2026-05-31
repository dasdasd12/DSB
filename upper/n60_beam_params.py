import sys
import os
import math
import struct
import datetime
import csv

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ==============================================================================
# N60 碗状复合阵列 - 核心声学常量与几何定义
# ==============================================================================
CHANNEL_COUNT = 60
SOUND_SPEED_M_S = 343.0
CARRIER_HZ = 40000.0
PWM_PERIOD_TICKS = 2500

MIN_DISTANCE_MM = 500
MAX_DISTANCE_MM = 5000
MAX_STEER_DEG = 30.0

# 严格解耦的三种幅度模式
MODE_UNIT_COSINE = "unit_cosine (物理法向 3.5次方加权)"
MODE_OPTIMIZED_DBC = "optimized_dbc_margin (离线算法优化表)"
MODE_UNIFORM = "uniform (全通无衰减 - 仅测总功率)"
AMPLITUDE_MODES = (MODE_UNIT_COSINE, MODE_OPTIMIZED_DBC, MODE_UNIFORM)

# 5个子阵的水平偏角与基准半径
UNIT_ANGLES_DEG = [-45.0, -22.5, 0.0, 22.5, 45.0]
BOWL_RADIUS_MM = 176.445

# 子阵内部 12 个阵元的局部坐标 (mm)
N12_LOCAL_COORDS = [
    (0.000, 0.000), (14.280, 10.958), (-10.958, 14.280), (-14.280, -10.958),
    (10.958, -14.280), (35.097, 8.011), (15.620, 32.435), (-15.620, 32.435),
    (-35.097, 8.011), (-28.146, -22.446), (0.000, -36.000), (28.146, -22.446)
]

def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ==============================================================================
# N60 3D 空间声学解算核心函数
# ==============================================================================
def generate_n60_geometry():
    """动态解算 60 路阵元在三维空间中的绝对坐标 (x, y, z)，单位：毫米"""
    geometry = []
    for unit_id, angle_deg in enumerate(UNIT_ANGLES_DEG):
        theta = math.radians(angle_deg)
        cx = BOWL_RADIUS_MM * math.sin(theta)
        cy = 0.0
        cz = -BOWL_RADIUS_MM * math.cos(theta)
        for lx, ly in N12_LOCAL_COORDS:
            gx = cx + lx * math.cos(theta)
            gy = cy + ly
            gz = cz + lx * math.sin(theta)
            geometry.append((gx, gy, gz))
    return geometry

def limit_direction_n60(az_deg, el_deg):
    """将全空间合成指向角死死限制在 30° 以内"""
    sx = math.sin(math.radians(float(az_deg)))
    sy = math.sin(math.radians(float(el_deg)))
    max_s = math.sin(math.radians(MAX_STEER_DEG))
    sxy = math.hypot(sx, sy)
    if sxy > max_s and sxy > 0.0:
        scale = max_s / sxy
        sx *= scale
        sy *= scale
        sxy = max_s
    sz = math.sqrt(max(0.0, 1.0 - sx * sx - sy * sy))
    actual_az = math.degrees(math.asin(max(-1.0, min(1.0, sx))))
    actual_el = math.degrees(math.asin(max(-1.0, min(1.0, sy))))
    combined_angle = math.degrees(math.asin(max(0.0, min(1.0, sxy))))
    return sx, sy, sz, actual_az, actual_el, combined_angle

def load_optimized_table(distance_mm, az_deg):
    """从本地 CSV 检索最优降旁瓣幅度分布（最近邻查表）"""
    here = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(here, "..", "analysis_outputs", "n60_5x12_focus_table_dbc_margin.csv")
    if not os.path.exists(csv_path):
        return [1.0] * CHANNEL_COUNT
    min_diff = float("inf")
    matched_row = None
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d_row = float(row["distance_mm"])
                az_row = float(row["az_deg"])
                diff = math.hypot((distance_mm - d_row) / 1000.0, math.radians(az_deg - az_row))
                if diff < min_diff:
                    min_diff = diff
                    matched_row = row
        if matched_row:
            return [float(matched_row[f"amp_{i:02d}"]) for i in range(CHANNEL_COUNT)]
    except Exception:
        pass
    return [1.0] * CHANNEL_COUNT

# ==============================================================================
# UI 样式表定义
# ==============================================================================
STYLESHEET = """
QMainWindow { background-color: #1E1E1E; border-image: url('bg.jpg') 0 0 0 0 stretch stretch; }
QWidget { font-family: "Microsoft YaHei UI", "Consolas"; font-size: 16px; color: #E0E0E0; }
QWidget#LeftPanel { background-color: rgba(20, 20, 25, 0.72); border-right: 1px solid rgba(64, 196, 255, 0.24); }
QTextEdit, QComboBox, QSpinBox { background-color: rgba(0, 0, 0, 0.42); border: 1px solid rgba(255, 255, 255, 0.16); border-radius: 4px; padding: 6px; color: #00E5FF; }
QPushButton { background-color: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.12); color: #E0E0E0; padding: 8px; border-radius: 6px; }
QPushButton:hover { background-color: rgba(64, 196, 255, 0.25); border: 1px solid #40C4FF; color: #40C4FF; }
QPushButton#btn_action { background-color: rgba(0, 188, 212, 0.50); border: 1px solid rgba(0, 229, 255, 0.60); font-weight: bold; }
QPushButton#btn_danger { background-color: rgba(255, 87, 34, 0.55); border: 1px solid rgba(255, 87, 34, 0.70); }
QGroupBox { border: 1px solid rgba(64, 196, 255, 0.30); border-radius: 8px; margin-top: 15px; padding-top: 25px; color: #40C4FF; font-weight: bold; background-color: rgba(0, 0, 0, 0.22); }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QSlider::groove:horizontal { border: 1px solid #777777; height: 8px; background: rgba(0, 0, 0, 0.50); border-radius: 4px; }
QSlider::handle:horizontal { background: #00E5FF; border: 1px solid #00E5FF; width: 18px; margin: -5px 0; border-radius: 9px; }
QLabel.transducer { background-color: rgba(0, 229, 255, 0.08); border: 1px solid rgba(0, 229, 255, 0.30); border-radius: 6px; color: #FFFFFF; font-family: "Consolas"; font-size: 11px; }
"""

# ==============================================================================
# 串口通信底层类
# ==============================================================================
class SerialLogic:
    def __init__(self):
        self.ser = None

    def open(self, port, baud):
        if serial is None: return False, "未安装 pyserial 库"
        if not port: return False, "未选择串口"
        if self.ser and self.ser.is_open: return False, "串口已打开"
        try:
            self.ser = serial.Serial(port=port.split(" ")[0], baudrate=int(baud), timeout=0)
            return True, "成功"
        except Exception as exc: return False, str(exc)

    def close(self):
        if self.ser: self.ser.close()
        self.ser = None

    def send(self, data):
        if not self.ser or not self.ser.is_open: return False, "串口未连接"
        try:
            self.ser.write(data)
            return True, "成功"
        except Exception as exc: return False, str(exc)

# ==============================================================================
# 上位机主窗体类
# ==============================================================================
class PhasedArrayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("N60 5x12 相控阵控制器 (底层固件强制指令码: 0x01)")
        self.resize(1360, 860)

        icon_path = resource_path("icon.jpg")
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))

        self.logic = SerialLogic()
        self.coords_3d = generate_n60_geometry()
        self.current_amps = [255] * CHANNEL_COUNT
        self.current_phases = [0] * CHANNEL_COUNT
        self.transducer_labels = []
        
        # UI 通信防抖定时器
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(self.send_to_fpga)
        
        # 自动扫描专用定时器 (1秒间隔)
        self.sweep_timer = QTimer(self)
        self.sweep_timer.timeout.connect(self.handle_auto_sweep)
        self.sweep_direction = 1  # 1表示增加角度，-1表示减小角度

        self.init_ui()
        self.refresh_ports()
        self.calculate_array()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ----------------- 左侧控制面板 -----------------
        left_panel = QWidget()
        left_panel.setObjectName("LeftPanel")
        left_panel.setFixedWidth(315)
        left_layout = QVBoxLayout(left_panel)

        lbl_logo = QLabel("FPGA 硬件连接 (N60)")
        lbl_logo.setStyleSheet("color: #00E5FF; font-weight: bold; font-size: 20px;")
        left_layout.addWidget(lbl_logo)

        self.cmb_port = QComboBox()
        self.cmb_baud = QComboBox()
        self.cmb_baud.addItems(["115200", "921600", "9600"])
        self.cmb_baud.setCurrentText("921600")

        left_layout.addWidget(QLabel("串口号 (Port):"))
        left_layout.addWidget(self.cmb_port)
        btn_refresh = QPushButton("刷新串口")
        btn_refresh.clicked.connect(self.refresh_ports)
        left_layout.addWidget(btn_refresh)

        left_layout.addWidget(QLabel("波特率 (Baudrate):"))
        left_layout.addWidget(self.cmb_baud)

        self.btn_open = QPushButton("连接 FPGA")
        self.btn_open.setObjectName("btn_action")
        self.btn_open.setMinimumHeight(44)
        self.btn_open.clicked.connect(self.toggle_serial)
        left_layout.addWidget(self.btn_open)

        self.chk_auto_send = QCheckBox("参数修改后自动同步")
        left_layout.addWidget(self.chk_auto_send)

        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel("运行日志:"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        left_layout.addWidget(self.txt_log)

        btn_clear = QPushButton("清空日志")
        btn_clear.clicked.connect(self.txt_log.clear)
        left_layout.addWidget(btn_clear)

        # ----------------- 右侧计算面板 -----------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)

        self.grp_ctrl = QGroupBox("N60 空间聚焦与 3D 偏转控制")
        ctrl_l = QVBoxLayout(self.grp_ctrl)

        h_amp = QHBoxLayout()
        h_amp.addWidget(QLabel("幅度加窗模式:"))
        self.cmb_amp = QComboBox()
        self.cmb_amp.addItems(AMPLITUDE_MODES)
        self.cmb_amp.setCurrentText(MODE_UNIT_COSINE)
        self.cmb_amp.currentIndexChanged.connect(self.calculate_array)
        h_amp.addWidget(self.cmb_amp)
        h_amp.addStretch()
        ctrl_l.addLayout(h_amp)

        self.lbl_az = QLabel()
        self.sld_az = self.make_slider(-int(MAX_STEER_DEG), int(MAX_STEER_DEG), 0)
        self.sld_az.valueChanged.connect(self.calculate_array)
        ctrl_l.addLayout(self.make_labeled_slider(self.lbl_az, self.sld_az))

        self.lbl_el = QLabel()
        self.sld_el = self.make_slider(-int(MAX_STEER_DEG), int(MAX_STEER_DEG), 0)
        self.sld_el.valueChanged.connect(self.calculate_array)
        ctrl_l.addLayout(self.make_labeled_slider(self.lbl_el, self.sld_el))

        h_dist = QHBoxLayout()
        self.lbl_dist = QLabel()
        self.lbl_dist.setFixedWidth(240)
        self.sld_dist = QSlider(Qt.Orientation.Horizontal)
        self.sld_dist.setRange(MIN_DISTANCE_MM, MAX_DISTANCE_MM)
        self.sld_dist.setValue(1000)
        self.sld_dist.valueChanged.connect(self.distance_slider_changed)
        self.spn_dist = QSpinBox()
        self.spn_dist.setRange(MIN_DISTANCE_MM, MAX_DISTANCE_MM)
        self.spn_dist.setValue(1000)
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.valueChanged.connect(self.distance_spin_changed)
        h_dist.addWidget(self.lbl_dist)
        h_dist.addWidget(self.sld_dist)
        h_dist.addWidget(self.spn_dist)
        
        # 新增：自动扫描模式复选框
        self.chk_auto_sweep = QCheckBox("启用自动扫描模式 (水平角 ±30°, 步进 2°, 间隔 1s)")
        self.chk_auto_sweep.setStyleSheet("color: #FF9800; font-weight: bold;")
        self.chk_auto_sweep.stateChanged.connect(self.toggle_auto_sweep)
        ctrl_l.addWidget(self.chk_auto_sweep)
        
        # 增加提示：坐标原点位于曲率中心
        lbl_origin_tip = QLabel(f"注：空间坐标系原点(0,0,0)位于阵列中心前方 {-BOWL_RADIUS_MM:.1f}mm 的虚拟曲率中心处。")
        lbl_origin_tip.setStyleSheet("color: #777777; font-size: 12px;")
        ctrl_l.addWidget(lbl_origin_tip)

        self.lbl_limited = QLabel()
        self.lbl_limited.setStyleSheet("color: #FFC107;")
        ctrl_l.addWidget(self.lbl_limited)
        right_layout.addWidget(self.grp_ctrl)

        # ----------------- 硬件测试模块 -----------------
        self.grp_test = QGroupBox("硬件调试: 单通道扫描测试")
        self.grp_test.setStyleSheet("QGroupBox { border-color: #FF5722; color: #FF5722; }")
        test_l = QHBoxLayout(self.grp_test)
        
        self.chk_test_mode = QCheckBox("启用单通道测试 (幅度强制 255, 相位强制 0)")
        self.chk_test_mode.stateChanged.connect(self.toggle_test_mode)
        test_l.addWidget(self.chk_test_mode)
        
        test_l.addWidget(QLabel(f"   测试通道 (0-{CHANNEL_COUNT-1}):"))
        self.spn_test_ch = QSpinBox()
        self.spn_test_ch.setRange(0, CHANNEL_COUNT - 1)
        self.spn_test_ch.setEnabled(False)
        self.spn_test_ch.valueChanged.connect(self.update_test_state)
        test_l.addWidget(self.spn_test_ch)
        test_l.addStretch()
        right_layout.addWidget(self.grp_test)

        # ----------------- N60 5x12 碗状图形网格映射 -----------------
        grp_array = QGroupBox("N60 碗状物理阵列映射图 (U0E0..U4E11 对应 transducer_io[0..59])")
        array_l = QGridLayout(grp_array)
        array_l.setSpacing(4)
        
        positions = self.grid_positions()
        for ch in range(CHANNEL_COUNT):
            row, col = positions[ch]
            lbl = QLabel()
            lbl.setProperty("class", "transducer")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(64, 52)
            array_l.addWidget(lbl, row, col, alignment=Qt.AlignmentFlag.AlignCenter)
            self.transducer_labels.append(lbl)
            
        right_layout.addWidget(grp_array, stretch=1)

        self.btn_send = QPushButton("同步参数至 FPGA (强制 0x01 帧)")
        self.btn_send.setObjectName("btn_action")
        self.btn_send.setMinimumHeight(55)
        self.btn_send.setFont(QFont("Microsoft YaHei UI", 14, QFont.Weight.Bold))
        self.btn_send.clicked.connect(self.send_to_fpga)
        right_layout.addWidget(self.btn_send)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

    def make_slider(self, low, high, value):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        return slider

    def make_labeled_slider(self, label, slider):
        layout = QHBoxLayout()
        label.setFixedWidth(240)
        layout.addWidget(label)
        layout.addWidget(slider)
        return layout

    def grid_positions(self):
        """将 3D 全局平面坐标无损映射至 2D 密铺 UI 网格"""
        positions = []
        used = set()
        for ch in range(CHANNEL_COUNT):
            gx, gy, _ = self.coords_3d[ch]
            col0 = int(round((gx + 160.0) / 320.0 * 24))
            row0 = int(round((36.0 - gy) / 72.0 * 6))
            
            chosen = (row0, col0)
            offsets = [(0, 0), (0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, -1), (0, 2), (0, -2)]
            for dr, dc in offsets:
                row = max(0, min(8, row0 + dr))
                col = max(0, min(28, col0 + dc))
                if (row, col) not in used:
                    chosen = (row, col)
                    break
            used.add(chosen)
            positions.append(chosen)
        return positions

    def refresh_ports(self):
        self.cmb_port.clear()
        if serial is None:
            self.cmb_port.addItem("缺少 pyserial 库")
            return
        for port in serial.tools.list_ports.comports():
            self.cmb_port.addItem("{} ({})".format(port.device, port.description))

    def toggle_serial(self):
        if self.btn_open.text() == "连接 FPGA":
            ok, msg = self.logic.open(self.cmb_port.currentText(), self.cmb_baud.currentText())
            if ok:
                self.btn_open.setText("断开 FPGA")
                self.btn_open.setObjectName("btn_danger")
                self.btn_open.setStyleSheet("background-color: rgba(255, 87, 34, 0.6);")
                self.log("成功连接至 {}".format(self.cmb_port.currentText()), "green")
            else:
                QMessageBox.critical(self, "串口错误", "打开失败: {}".format(msg))
        else:
            self.logic.close()
            self.btn_open.setText("连接 FPGA")
            self.btn_open.setObjectName("btn_action")
            self.btn_open.setStyleSheet("")
            self.log("已断开连接", "red")

    def distance_slider_changed(self, value):
        self.spn_dist.blockSignals(True)
        self.spn_dist.setValue(value)
        self.spn_dist.blockSignals(False)
        self.calculate_array()

    def distance_spin_changed(self, value):
        self.sld_dist.blockSignals(True)
        self.sld_dist.setValue(value)
        self.sld_dist.blockSignals(False)
        self.calculate_array()
        
    def toggle_test_mode(self):
        is_test = self.chk_test_mode.isChecked()
        self.spn_test_ch.setEnabled(is_test)
        
        if is_test: 
            self.chk_auto_sweep.setChecked(False) # 开启测试时，强制关闭扫描
            self.grp_ctrl.setEnabled(False)
            self.update_test_state()
        else: 
            self.grp_ctrl.setEnabled(True)
            self.calculate_array()

    def update_test_state(self):
        if not self.chk_test_mode.isChecked(): return
        target_ch = self.spn_test_ch.value()
        self.current_amps = [255 if i == target_ch else 0 for i in range(CHANNEL_COUNT)]
        self.current_phases = [0] * CHANNEL_COUNT
        self.refresh_array_labels()
        if self.chk_auto_send.isChecked(): self.auto_timer.start(120)
        
    # ==========================================
    # 自动扫描模式逻辑
    # ==========================================
    def toggle_auto_sweep(self):
        if self.chk_auto_sweep.isChecked():
            # 1. 强制切换到 3.5次方物理法向加权模式
            self.cmb_amp.setCurrentText(MODE_UNIT_COSINE)
            # 2. 强制开启参数改变自动同步 FPGA，保证每一帧都下发
            self.chk_auto_send.setChecked(True)
            # 3. 禁用单通道测试以防干扰
            self.chk_test_mode.setChecked(False)
            self.grp_test.setEnabled(False)
            
            # 确定初始扫描方向 (如果在右边就往左扫，反之向右)
            if self.sld_az.value() >= 30:
                self.sweep_direction = -1
            elif self.sld_az.value() <= -30:
                self.sweep_direction = 1
                
            # 启动 1s 定时器
            self.sweep_timer.start(1000)
            self.log("▶ 已开启自动扫描模式 (1s间隔, 2°步进)", "#FF9800")
        else:
            self.sweep_timer.stop()
            self.grp_test.setEnabled(True)
            self.log("⏹ 已关闭自动扫描模式", "#FFFFFF")

    def handle_auto_sweep(self):
        # 提取当前水平角，加上方向步进值
        curr_az = self.sld_az.value()
        next_az = curr_az + (2 * self.sweep_direction)
        
        # 边界检测与方向翻转
        if next_az >= 30:
            next_az = 30
            self.sweep_direction = -1
        elif next_az <= -30:
            next_az = -30
            self.sweep_direction = 1
            
        # 设置滑块值 (触发 valueChanged -> calculate_array -> 发送串口包)
        self.sld_az.setValue(next_az)

    # ==========================================
    # N60 空间聚焦与幅度模式解耦计算
    # ==========================================
    def calculate_array(self):
        if self.chk_test_mode.isChecked(): return

        # 1. 角度超限压缩过滤
        sx, sy, sz, actual_az, actual_el, combined_angle = limit_direction_n60(
            self.sld_az.value(), self.sld_el.value()
        )
        distance_mm = self.sld_dist.value()
        distance_m = distance_mm / 1000.0
        target_m = (distance_m * sx, distance_m * sy, distance_m * sz)

        # 获取当前模式
        current_mode = self.cmb_amp.currentText()
        opt_amps = None
        if current_mode == MODE_OPTIMIZED_DBC:
            opt_amps = load_optimized_table(distance_mm, actual_az)

        # 2. 逐通道全空间近场声程结算与独立幅度分配
        for ch in range(CHANNEL_COUNT):
            mx, my, mz = self.coords_3d[ch]
            
            # --- [A] 相位计算：严格纠正为 (实际声程 - 参考距离)，较远阵元相位超前 ---
            path_m = math.sqrt((target_m[0] - mx/1000.0)**2 + (target_m[1] - my/1000.0)**2 + (target_m[2] - mz/1000.0)**2)
            phase_cycles = (path_m - distance_m) * CARRIER_HZ / SOUND_SPEED_M_S
            self.current_phases[ch] = int(round((phase_cycles % 1.0) * PWM_PERIOD_TICKS)) % PWM_PERIOD_TICKS
            
            # --- [B] 幅度计算：严格隔离的三种理论模型 ---
            final_amp = 1.0 
            
            if current_mode == MODE_UNIT_COSINE:
                unit_id = ch // 12
                theta_rad = math.radians(UNIT_ANGLES_DEG[unit_id])
                nx = -math.sin(theta_rad)
                ny = 0.0
                nz = math.cos(theta_rad)
                
                vx = target_m[0] - mx/1000.0
                vy = target_m[1] - my/1000.0
                vz = target_m[2] - mz/1000.0
                v_len = math.sqrt(vx**2 + vy**2 + vz**2)
                
                if v_len > 0:
                    vx, vy, vz = vx/v_len, vy/v_len, vz/v_len
                    dot_product = vx*nx + vy*ny + vz*nz
                    # 依据 HY40A16T12-1 实测参数 (-6dB@35deg) 修正的 3.5 次方衰减模型
                    final_amp = max(0.0, dot_product) ** 3.5
                else:
                    final_amp = 1.0

            elif current_mode == MODE_OPTIMIZED_DBC:
                final_amp = opt_amps[ch] if opt_amps else 1.0
                
            elif current_mode == MODE_UNIFORM:
                final_amp = 1.0
            
            self.current_amps[ch] = int(round(max(0.0, min(1.0, final_amp)) * 255.0))

        # 3. 更新前端状态描述
        self.lbl_az.setText("水平角 (Azimuth): {}°".format(self.sld_az.value()))
        self.lbl_el.setText("俯仰角 (Elevation): {}°".format(self.sld_el.value()))
        self.lbl_dist.setText("焦距 (Distance): {:.3f} 米".format(distance_m))

        limited = abs(actual_az - self.sld_az.value()) > 0.05 or abs(actual_el - self.sld_el.value()) > 0.05
        if limited:
            self.lbl_limited.setText(f"触发角度限幅: 水平={actual_az:.1f}°, 俯仰={actual_el:.1f}°, 综合偏转={combined_angle:.1f}°")
        else:
            self.lbl_limited.setText(f"当前综合偏转角: {combined_angle:.2f}°")

        self.refresh_array_labels()
        if self.chk_auto_send.isChecked(): self.auto_timer.start(120)

    def refresh_array_labels(self):
        for ch in range(CHANNEL_COUNT):
            unit_id = ch // 12
            elem_id = ch % 12
            amp = self.current_amps[ch]
            phase = self.current_phases[ch]
            label = self.transducer_labels[ch]
            
            label.setText(f"U{unit_id}E{elem_id}\nCH:{ch:02d}\n幅度:{amp:03d}\n相位:{phase:04d}")
            
            intensity = max(20, min(220, amp))
            if amp == 0:
                color = "rgba(0, 0, 0, 0.45)"
                border = "rgba(255, 255, 255, 0.1)"
            elif phase == 0 and self.chk_test_mode.isChecked():
                color = "rgba(255, 87, 34, 0.85)"
                border = "#FF5722"
            else:
                color = "rgba(0, 229, 255, {:.2f})".format(0.10 + 0.45 * intensity / 255.0)
                border = "rgba(0, 229, 255, 0.45)"
                
            label.setStyleSheet(f"background-color: {color}; border: 1px solid {border}; border-radius: 6px; color: #FFFFFF;")

    # ==========================================
    # 强制套用 0x01 指令码进行 FPGA 打包
    # ==========================================
    def make_packet(self):
        packet = bytearray([0xAA, 0xBB, 0x01])
        for amp in self.current_amps:
            packet.append(int(max(0, min(255, amp))) & 0xFF)
        for phase in self.current_phases:
            packet.extend(struct.pack("<H", int(phase) % PWM_PERIOD_TICKS))
        packet.append(sum(packet[2:]) & 0xFF)
        packet.extend([0x0D, 0x0A])
        return bytes(packet)

    def send_to_fpga(self):
        packet = self.make_packet()
        ok, msg = self.logic.send(packet)
        if ok:
            # 扫描模式或测试模式打上不同颜色的标签便于观察
            if self.chk_auto_sweep.isChecked():
                color = "#FF9800"
                tag = "[AUTO SWEEP] "
            elif self.chk_test_mode.isChecked():
                color = "#FF5722"
                tag = "[TEST MODE] "
            else:
                color = "#00E5FF"
                tag = ""
                
            self.log(f"{tag}成功下发 N60 帧 [{len(packet)} 字节]<br>" + 
                     " ".join(f"{b:02X}" for b in packet[:12]) + " ... " + 
                     " ".join(f"{b:02X}" for b in packet[-4:]), color)
        else:
            self.log("发送失败: {}".format(msg), "red")

    def log(self, text, color="#FFFFFF"):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.txt_log.append("<span style='color:{};'>[{}] {}</span>".format(color, ts, text))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    bg_path = resource_path("bg.jpg").replace("\\", "/")
    app.setStyleSheet(STYLESHEET.replace("bg.jpg", bg_path))
    win = PhasedArrayWindow()
    win.show()
    sys.exit(app.exec())