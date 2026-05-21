import datetime
import os
import sys

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
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import array_profiles  # noqa: E402
import protocol  # noqa: E402


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


STYLESHEET = """
QMainWindow {
    background-color: #1E1E1E;
    border-image: url('bg.jpg') 0 0 0 0 stretch stretch;
}
QWidget {
    font-family: "Microsoft YaHei UI", "Consolas";
    font-size: 14px;
    color: #E0E0E0;
}
QWidget#LeftPanel {
    background-color: rgba(20, 20, 25, 0.72);
    border-right: 1px solid rgba(64, 196, 255, 0.24);
}
QTabWidget::pane {
    border: 1px solid rgba(64, 196, 255, 0.25);
}
QTabBar::tab {
    background-color: rgba(255, 255, 255, 0.07);
    border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 8px 16px;
}
QTabBar::tab:selected {
    color: #00E5FF;
    border-color: rgba(0, 229, 255, 0.55);
}
QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: rgba(0, 0, 0, 0.42);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 4px;
    padding: 6px;
    color: #00E5FF;
}
QPushButton {
    background-color: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #E0E0E0;
    padding: 8px;
    border-radius: 6px;
}
QPushButton:hover {
    background-color: rgba(64, 196, 255, 0.25);
    border: 1px solid #40C4FF;
    color: #40C4FF;
}
QPushButton#btn_action {
    background-color: rgba(0, 188, 212, 0.50);
    border: 1px solid rgba(0, 229, 255, 0.60);
    font-weight: bold;
}
QPushButton#btn_danger {
    background-color: rgba(255, 87, 34, 0.55);
    border: 1px solid rgba(255, 87, 34, 0.70);
}
QGroupBox {
    border: 1px solid rgba(64, 196, 255, 0.30);
    border-radius: 8px;
    margin-top: 15px;
    padding-top: 20px;
    color: #40C4FF;
    font-weight: bold;
    background-color: rgba(0, 0, 0, 0.22);
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QSlider::groove:horizontal {
    border: 1px solid #777777;
    height: 8px;
    background: rgba(0, 0, 0, 0.50);
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #00E5FF;
    border: 1px solid #00E5FF;
    width: 18px;
    margin: -5px 0;
    border-radius: 9px;
}
QLabel.transducer {
    background-color: rgba(0, 229, 255, 0.08);
    border: 1px solid rgba(0, 229, 255, 0.30);
    border-radius: 6px;
    color: #FFFFFF;
    font-family: "Consolas";
    font-size: 10px;
}
"""


MOD_MODE_ITEMS = [
    ("Legacy SRAM", protocol.MOD_LEGACY_SRAM, 0),
    ("DSB-AM", protocol.MOD_DSB_AM, 0),
    ("SSB USB", protocol.MOD_SSB_USB, 0),
    ("SSB LSB", protocol.MOD_SSB_LSB, 1),
    ("MAM1", protocol.MOD_MAM1, 0),
]


class SerialLogic:
    def __init__(self):
        self.ser = None

    def open(self, port, baud):
        if serial is None:
            return False, "pyserial is not installed"
        if not port:
            return False, "no serial port selected"
        if self.ser and self.ser.is_open:
            return False, "already open"
        try:
            self.ser = serial.Serial(port=port.split(" ")[0], baudrate=int(baud), timeout=0)
            return True, "ok"
        except Exception as exc:
            return False, str(exc)

    def close(self):
        if self.ser:
            self.ser.close()

    def send(self, data):
        if not self.ser or not self.ser.is_open:
            return False, "not connected"
        try:
            self.ser.write(data)
            return True, "ok"
        except Exception as exc:
            return False, str(exc)


class PhasedArrayWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UltraAudio Phased Array Controller")
        self.resize(1280, 900)

        icon_path = resource_path("icon.jpg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.logic = SerialLogic()
        self.profile_name = array_profiles.PROFILE_N32
        self.current_amps = [255] * 32
        self.current_phases = [0] * 32
        self.transducer_labels = []

        self.auto_beam_timer = QTimer(self)
        self.auto_beam_timer.setSingleShot(True)
        self.auto_beam_timer.timeout.connect(self.send_beam_to_fpga)
        self.auto_mod_timer = QTimer(self)
        self.auto_mod_timer.setSingleShot(True)
        self.auto_mod_timer.timeout.connect(self.send_mod_debug_to_fpga)

        self.init_ui()
        self.refresh_ports()
        self.profile_changed()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left_panel = QWidget()
        left_panel.setObjectName("LeftPanel")
        left_panel.setFixedWidth(330)
        left_layout = QVBoxLayout(left_panel)

        lbl_logo = QLabel("ULTRAAUDIO LINK")
        lbl_logo.setStyleSheet("color: #00E5FF; font-weight: bold; font-size: 18px;")
        left_layout.addWidget(lbl_logo)

        self.cmb_port = QComboBox()
        self.cmb_baud = QComboBox()
        self.cmb_baud.addItems(["115200", "921600", "9600"])
        self.btn_open = QPushButton("Connect FPGA")
        self.btn_open.setObjectName("btn_action")
        self.btn_open.setMinimumHeight(44)
        self.btn_open.clicked.connect(self.toggle_serial)
        btn_refresh = QPushButton("Refresh ports")
        btn_refresh.clicked.connect(self.refresh_ports)
        self.chk_auto_send = QCheckBox("Auto sync changed packets")

        left_layout.addWidget(QLabel("Port:"))
        left_layout.addWidget(self.cmb_port)
        left_layout.addWidget(btn_refresh)
        left_layout.addWidget(QLabel("Baudrate:"))
        left_layout.addWidget(self.cmb_baud)
        left_layout.addWidget(self.btn_open)
        left_layout.addWidget(self.chk_auto_send)
        left_layout.addSpacing(12)
        left_layout.addWidget(QLabel("Packet preview:"))
        self.txt_preview = QTextEdit()
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setMinimumHeight(145)
        left_layout.addWidget(self.txt_preview)
        left_layout.addWidget(QLabel("Log:"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        left_layout.addWidget(self.txt_log)
        btn_clear = QPushButton("Clear log")
        btn_clear.clicked.connect(self.txt_log.clear)
        left_layout.addWidget(btn_clear)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_array_tab(), "Array")
        self.tabs.addTab(self.build_modulation_tab(), "Modulation")
        self.tabs.addTab(self.build_debug_tab(), "Debug")

        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.tabs, stretch=1)

    def build_array_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        grp_ctrl = QGroupBox("Focus and steering")
        ctrl_l = QVBoxLayout(grp_ctrl)

        row_profile = QHBoxLayout()
        row_profile.addWidget(QLabel("Array profile:"))
        self.cmb_profile = QComboBox()
        self.cmb_profile.addItems([array_profiles.PROFILE_N32, array_profiles.PROFILE_N60])
        self.cmb_profile.currentIndexChanged.connect(self.profile_changed)
        row_profile.addWidget(self.cmb_profile)
        row_profile.addWidget(QLabel("Amplitude mode:"))
        self.cmb_amp = QComboBox()
        self.cmb_amp.currentIndexChanged.connect(self.calculate_array)
        row_profile.addWidget(self.cmb_amp)
        ctrl_l.addLayout(row_profile)

        self.lbl_az = QLabel()
        self.sld_az = self.make_slider(-15, 15, 0)
        self.sld_az.valueChanged.connect(self.calculate_array)
        ctrl_l.addLayout(self.make_labeled_slider(self.lbl_az, self.sld_az))

        self.lbl_el = QLabel()
        self.sld_el = self.make_slider(-15, 15, 0)
        self.sld_el.valueChanged.connect(self.calculate_array)
        ctrl_l.addLayout(self.make_labeled_slider(self.lbl_el, self.sld_el))

        h_dist = QHBoxLayout()
        self.lbl_dist = QLabel()
        self.lbl_dist.setFixedWidth(220)
        self.sld_dist = QSlider(Qt.Orientation.Horizontal)
        self.sld_dist.valueChanged.connect(self.distance_slider_changed)
        self.spn_dist = QSpinBox()
        self.spn_dist.setSuffix(" mm")
        self.spn_dist.valueChanged.connect(self.distance_spin_changed)
        h_dist.addWidget(self.lbl_dist)
        h_dist.addWidget(self.sld_dist)
        h_dist.addWidget(self.spn_dist)
        ctrl_l.addLayout(h_dist)

        self.lbl_limited = QLabel()
        self.lbl_limited.setStyleSheet("color: #FFC107;")
        ctrl_l.addWidget(self.lbl_limited)
        layout.addWidget(grp_ctrl)

        grp_array = QGroupBox("Channel view")
        self.array_grid = QGridLayout(grp_array)
        self.array_grid.setSpacing(5)
        self.create_channel_labels(60)
        layout.addWidget(grp_array, stretch=1)

        h_buttons = QHBoxLayout()
        self.btn_send_beam = QPushButton("Sync beam packet")
        self.btn_send_beam.setObjectName("btn_action")
        self.btn_send_beam.setMinimumHeight(48)
        self.btn_send_beam.clicked.connect(self.send_beam_to_fpga)
        btn_preview = QPushButton("Preview beam packet")
        btn_preview.clicked.connect(lambda: self.preview_packet("beam", self.make_beam_packet()))
        h_buttons.addWidget(btn_preview)
        h_buttons.addWidget(self.btn_send_beam)
        layout.addLayout(h_buttons)
        return page

    def build_modulation_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        grp = QGroupBox("Realtime modulation")
        grid = QGridLayout(grp)

        self.cmb_source = QComboBox()
        self.cmb_source.addItems(["DDS/test", "I2S input"])
        self.cmb_mod_mode = QComboBox()
        self.cmb_mod_mode.addItems([item[0] for item in MOD_MODE_ITEMS])
        self.cmb_mod_mode.setCurrentText("MAM1")
        self.spn_mod_index = QDoubleSpinBox()
        self.spn_mod_index.setRange(0.0, 1.0)
        self.spn_mod_index.setSingleStep(0.05)
        self.spn_mod_index.setDecimals(3)
        self.spn_mod_index.setValue(0.6)
        self.spn_input_gain_q8 = self.make_spin(0, 8192, 256, " Q8")
        self.spn_envelope_scale_q8 = self.make_spin(0, 8192, 256, " Q8")
        self.spn_test_freq = self.make_spin(0, 20000, 1000, " Hz")
        self.spn_test_amp = self.make_spin(0, 32767, 8192, "")
        self.chk_output_enable = QCheckBox("Output enable")
        self.chk_output_enable.setChecked(True)
        self.chk_center_align = QCheckBox("PWM center aligned")
        self.chk_safe_clamp = QCheckBox("Safe clamp")
        self.chk_safe_clamp.setChecked(True)
        self.chk_fixed_duty_bypass = QCheckBox("Fixed duty debug bypass")
        self.chk_mark_debug = QCheckBox("Mark debug strobe")

        widgets = [
            self.cmb_source,
            self.cmb_mod_mode,
            self.spn_mod_index,
            self.spn_input_gain_q8,
            self.spn_envelope_scale_q8,
            self.spn_test_freq,
            self.spn_test_amp,
            self.chk_output_enable,
            self.chk_center_align,
            self.chk_safe_clamp,
            self.chk_fixed_duty_bypass,
            self.chk_mark_debug,
        ]
        for widget in widgets:
            self.connect_mod_widget(widget)

        grid.addWidget(QLabel("Audio source:"), 0, 0)
        grid.addWidget(self.cmb_source, 0, 1)
        grid.addWidget(QLabel("Modulation mode:"), 0, 2)
        grid.addWidget(self.cmb_mod_mode, 0, 3)
        grid.addWidget(QLabel("Mod index:"), 1, 0)
        grid.addWidget(self.spn_mod_index, 1, 1)
        grid.addWidget(QLabel("Input gain:"), 1, 2)
        grid.addWidget(self.spn_input_gain_q8, 1, 3)
        grid.addWidget(QLabel("Envelope scale:"), 2, 0)
        grid.addWidget(self.spn_envelope_scale_q8, 2, 1)
        grid.addWidget(QLabel("Test freq:"), 2, 2)
        grid.addWidget(self.spn_test_freq, 2, 3)
        grid.addWidget(QLabel("Test amp:"), 3, 0)
        grid.addWidget(self.spn_test_amp, 3, 1)
        grid.addWidget(self.chk_output_enable, 4, 0)
        grid.addWidget(self.chk_center_align, 4, 1)
        grid.addWidget(self.chk_safe_clamp, 4, 2)
        grid.addWidget(self.chk_fixed_duty_bypass, 5, 0)
        grid.addWidget(self.chk_mark_debug, 5, 1)

        h_presets = QHBoxLayout()
        btn_mam = QPushButton("Preset: MAM1 m=0.6")
        btn_mam.clicked.connect(self.apply_mam1_preset)
        btn_legacy = QPushButton("Preset: Legacy SRAM")
        btn_legacy.clicked.connect(self.apply_legacy_preset)
        btn_dsb = QPushButton("Preset: DSB-AM")
        btn_dsb.clicked.connect(self.apply_dsb_preset)
        h_presets.addWidget(btn_mam)
        h_presets.addWidget(btn_legacy)
        h_presets.addWidget(btn_dsb)
        layout.addWidget(grp)
        layout.addLayout(h_presets)

        h_send = QHBoxLayout()
        btn_preview = QPushButton("Preview modulation packet")
        btn_preview.clicked.connect(lambda: self.preview_packet("mod/debug v1", self.make_mod_debug_packet()))
        self.btn_send_mod = QPushButton("Sync modulation/debug v1")
        self.btn_send_mod.setObjectName("btn_action")
        self.btn_send_mod.setMinimumHeight(48)
        self.btn_send_mod.clicked.connect(self.send_mod_debug_to_fpga)
        h_send.addWidget(btn_preview)
        h_send.addWidget(self.btn_send_mod)
        layout.addLayout(h_send)
        layout.addStretch()
        return page

    def build_debug_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        grp = QGroupBox("Debug controls")
        grid = QGridLayout(grp)

        self.cmb_limiter = QComboBox()
        self.cmb_limiter.addItems(["0 none", "1 hard", "2 soft"])
        self.spn_limiter_threshold = self.make_spin(-32768, 32767, 32767, "")
        self.spn_dc_offset = self.make_spin(-32768, 32767, 0, "")
        self.spn_max_duty = self.make_spin(0, 1250, 1250, " ticks")
        self.spn_probe = self.make_spin(0, 255, 0, "")
        self.txt_output_mask = QLineEdit("00000000FFFFFFFF")
        self.spn_single_channel = self.make_spin(0, 59, 0, "")
        self.spn_unit = self.make_spin(0, 4, 0, "")

        for widget in (self.cmb_limiter, self.spn_limiter_threshold, self.spn_dc_offset, self.spn_max_duty, self.spn_probe, self.txt_output_mask):
            self.connect_mod_widget(widget)

        grid.addWidget(QLabel("Limiter:"), 0, 0)
        grid.addWidget(self.cmb_limiter, 0, 1)
        grid.addWidget(QLabel("Threshold:"), 0, 2)
        grid.addWidget(self.spn_limiter_threshold, 0, 3)
        grid.addWidget(QLabel("DC offset:"), 1, 0)
        grid.addWidget(self.spn_dc_offset, 1, 1)
        grid.addWidget(QLabel("Max duty:"), 1, 2)
        grid.addWidget(self.spn_max_duty, 1, 3)
        grid.addWidget(QLabel("Debug probe:"), 2, 0)
        grid.addWidget(self.spn_probe, 2, 1)
        grid.addWidget(QLabel("Output mask hex:"), 2, 2)
        grid.addWidget(self.txt_output_mask, 2, 3)
        grid.addWidget(QLabel("Single channel:"), 3, 0)
        grid.addWidget(self.spn_single_channel, 3, 1)
        grid.addWidget(QLabel("N60 unit:"), 3, 2)
        grid.addWidget(self.spn_unit, 3, 3)

        h_mask = QHBoxLayout()
        for label, fn in [
            ("All active", self.apply_all_mask),
            ("All off", self.apply_zero_mask),
            ("Single channel", self.apply_single_channel_mask),
            ("N60 unit", self.apply_unit_mask),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(fn)
            h_mask.addWidget(btn)

        h_send = QHBoxLayout()
        btn_legacy = QPushButton("Sync legacy debug 0x02")
        btn_legacy.clicked.connect(self.send_legacy_debug_to_fpga)
        btn_mod = QPushButton("Sync modulation/debug 0x04")
        btn_mod.setObjectName("btn_action")
        btn_mod.clicked.connect(self.send_mod_debug_to_fpga)
        h_send.addWidget(btn_legacy)
        h_send.addWidget(btn_mod)

        layout.addWidget(grp)
        layout.addLayout(h_mask)
        layout.addLayout(h_send)
        layout.addStretch()
        return page

    def create_channel_labels(self, count):
        for idx in range(count):
            label = QLabel()
            label.setProperty("class", "transducer")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedSize(58, 46)
            self.transducer_labels.append(label)
            self.array_grid.addWidget(label, idx // 12, idx % 12, alignment=Qt.AlignmentFlag.AlignCenter)

    def connect_mod_widget(self, widget):
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self.mod_param_changed)
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self.mod_param_changed)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self.mod_param_changed)
        else:
            widget.valueChanged.connect(self.mod_param_changed)

    def make_slider(self, low, high, value):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(value)
        return slider

    def make_labeled_slider(self, label, slider):
        layout = QHBoxLayout()
        label.setFixedWidth(220)
        layout.addWidget(label)
        layout.addWidget(slider)
        return layout

    def make_spin(self, low, high, value, suffix):
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def profile(self):
        return array_profiles.profile_for_name(self.profile_name)

    def profile_changed(self):
        self.profile_name = self.cmb_profile.currentText()
        profile = self.profile()

        self.cmb_amp.blockSignals(True)
        self.cmb_amp.clear()
        self.cmb_amp.addItems(profile.amplitude_modes)
        self.cmb_amp.setCurrentText(profile.default_mode)
        self.cmb_amp.blockSignals(False)

        steer = int(profile.max_steer_deg)
        for slider in (self.sld_az, self.sld_el):
            slider.blockSignals(True)
            slider.setRange(-steer, steer)
            slider.setValue(0)
            slider.blockSignals(False)

        self.sld_dist.blockSignals(True)
        self.spn_dist.blockSignals(True)
        self.sld_dist.setRange(profile.min_distance_mm, profile.max_distance_mm)
        self.spn_dist.setRange(profile.min_distance_mm, profile.max_distance_mm)
        default_distance = 1000 if profile.name == array_profiles.PROFILE_N32 else 2000
        default_distance = max(profile.min_distance_mm, min(profile.max_distance_mm, default_distance))
        self.sld_dist.setValue(default_distance)
        self.spn_dist.setValue(default_distance)
        self.sld_dist.blockSignals(False)
        self.spn_dist.blockSignals(False)

        self.spn_single_channel.setMaximum(profile.channel_count - 1)
        self.txt_output_mask.setText("%016X" % self.default_mask())
        self.calculate_array()

    def refresh_ports(self):
        self.cmb_port.clear()
        if serial is None:
            self.cmb_port.addItem("pyserial missing")
            return
        for port in serial.tools.list_ports.comports():
            self.cmb_port.addItem("{} ({})".format(port.device, port.description))

    def toggle_serial(self):
        if self.btn_open.text() == "Connect FPGA":
            ok, msg = self.logic.open(self.cmb_port.currentText(), self.cmb_baud.currentText())
            if ok:
                self.btn_open.setText("Disconnect FPGA")
                self.btn_open.setObjectName("btn_danger")
                self.btn_open.setStyleSheet("background-color: rgba(255, 87, 34, 0.6);")
                self.log("Connected to {}".format(self.cmb_port.currentText()), "green")
            else:
                QMessageBox.critical(self, "Serial error", "Open failed: {}".format(msg))
        else:
            self.logic.close()
            self.btn_open.setText("Connect FPGA")
            self.btn_open.setObjectName("btn_action")
            self.btn_open.setStyleSheet("")
            self.log("Disconnected", "red")

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

    def calculate_array(self):
        if not hasattr(self, "cmb_amp"):
            return
        result = array_profiles.calculate(
            self.profile_name,
            distance_mm=self.sld_dist.value(),
            az_deg=self.sld_az.value(),
            el_deg=self.sld_el.value(),
            amp_mode=self.cmb_amp.currentText(),
        )
        self.current_amps = list(result.amplitudes)
        self.current_phases = list(result.phases)
        self.update_array_labels(result)
        if self.chk_auto_send.isChecked():
            self.auto_beam_timer.start(120)

    def update_array_labels(self, result):
        profile = self.profile()
        self.lbl_az.setText("Azimuth: {} deg".format(self.sld_az.value()))
        self.lbl_el.setText("Elevation: {} deg".format(self.sld_el.value()))
        self.lbl_dist.setText("Focus distance: {:.3f} m".format(result.distance_mm / 1000.0))
        self.lbl_limited.setText(
            "Actual az={:.2f} deg, el={:.2f} deg, combined={:.2f} deg".format(
                result.actual_az_deg,
                result.actual_el_deg,
                result.combined_angle_deg,
            )
        )

        for ch, label in enumerate(self.transducer_labels):
            if ch >= profile.channel_count:
                label.hide()
                continue
            label.show()
            amp = self.current_amps[ch]
            phase = self.current_phases[ch]
            if profile.name == array_profiles.PROFILE_N60:
                prefix = "U{}E{}".format(ch // 12, ch % 12)
            else:
                prefix = "E{:02d}".format(ch)
            label.setText("{}\nA:{:03d}\nP:{:04d}".format(prefix, amp, phase))
            color = "rgba(0, 229, 255, {:.2f})".format(0.10 + 0.45 * max(20, amp) / 255.0)
            if amp == 0:
                color = "rgba(255, 255, 255, 0.04)"
            label.setStyleSheet("background-color: {}; border: 1px solid rgba(0,229,255,0.45); border-radius: 6px;".format(color))

    def mod_param_changed(self, *args):
        if self.chk_auto_send.isChecked():
            self.auto_mod_timer.start(120)

    def mod_mode_values(self):
        return MOD_MODE_ITEMS[self.cmb_mod_mode.currentIndex()]

    def mod_flags(self):
        flags = 0
        if self.chk_output_enable.isChecked():
            flags |= 1 << 0
        if self.chk_center_align.isChecked():
            flags |= 1 << 1
        if self.chk_safe_clamp.isChecked():
            flags |= 1 << 2
        if self.chk_fixed_duty_bypass.isChecked():
            flags |= 1 << 3
        if self.chk_mark_debug.isChecked():
            flags |= 1 << 4
        return flags

    def legacy_flags(self):
        flags = 0
        if self.chk_output_enable.isChecked():
            flags |= 1 << 0
        if self.cmb_source.currentIndex() == 1:
            flags |= 1 << 1
        if self.chk_center_align.isChecked():
            flags |= 1 << 2
        if self.cmb_mod_mode.currentText() == "Legacy SRAM" and not self.chk_fixed_duty_bypass.isChecked():
            flags |= 1 << 3
        return flags

    def mod_index_q15(self):
        return int(round(self.spn_mod_index.value() * 32768.0))

    def output_mask(self):
        text = self.txt_output_mask.text().strip().replace("_", "")
        if text.lower().startswith("0x"):
            text = text[2:]
        try:
            return int(text or "0", 16) & 0xFFFFFFFFFFFFFFFF
        except ValueError:
            return self.default_mask()

    def default_mask(self):
        count = self.profile().channel_count
        return (1 << count) - 1 if count < 64 else 0xFFFFFFFFFFFFFFFF

    def make_beam_packet(self):
        return array_profiles.build_beam_packet(self.profile_name, self.current_amps, self.current_phases)

    def make_legacy_debug_packet(self):
        return protocol.build_legacy_debug_packet(
            array_profile=self.profile().profile_id,
            flags=self.legacy_flags(),
            gain_q8=self.spn_input_gain_q8.value(),
            limiter_mode=self.cmb_limiter.currentIndex(),
            limiter_threshold=self.spn_limiter_threshold.value(),
            audio_depth_q8=self.spn_envelope_scale_q8.value(),
            dc_offset=self.spn_dc_offset.value(),
            test_ftw=protocol.ftw_from_hz(self.spn_test_freq.value()),
            test_amp=self.spn_test_amp.value(),
            max_duty=self.spn_max_duty.value(),
            output_mask=self.output_mask(),
        )

    def make_mod_debug_packet(self):
        _, mod_mode, sideband = self.mod_mode_values()
        return protocol.build_mod_debug_v1_packet(
            array_profile=self.profile().profile_id,
            flags=self.mod_flags(),
            source_select=self.cmb_source.currentIndex(),
            modulation_mode=mod_mode,
            sideband=sideband,
            debug_probe_select=self.spn_probe.value(),
            input_gain_q8=self.spn_input_gain_q8.value(),
            limiter_mode=self.cmb_limiter.currentIndex(),
            limiter_threshold=self.spn_limiter_threshold.value(),
            dc_offset=self.spn_dc_offset.value(),
            mod_index_q15=self.mod_index_q15(),
            envelope_scale_q8=self.spn_envelope_scale_q8.value(),
            test_ftw=protocol.ftw_from_hz(self.spn_test_freq.value()),
            test_amp=self.spn_test_amp.value(),
            max_duty=self.spn_max_duty.value(),
            output_mask=self.output_mask(),
        )

    def preview_packet(self, label, packet):
        self.txt_preview.setPlainText("{} [{} bytes]\n{}".format(label, len(packet), protocol.format_packet_hex(packet)))

    def send_packet(self, label, packet, color):
        self.preview_packet(label, packet)
        ok, msg = self.logic.send(packet)
        if ok:
            self.log("Sent {} [{} bytes]".format(label, len(packet)), color)
        else:
            self.log("{} send failed: {}".format(label, msg), "red")

    def send_beam_to_fpga(self):
        self.send_packet("{} beam".format(self.profile_name), self.make_beam_packet(), "#00E5FF")

    def send_legacy_debug_to_fpga(self):
        self.send_packet("legacy debug 0x02", self.make_legacy_debug_packet(), "#FFC107")

    def send_mod_debug_to_fpga(self):
        self.send_packet("mod/debug v1 0x04", self.make_mod_debug_packet(), "#FFC107")

    def apply_mam1_preset(self):
        self.cmb_mod_mode.setCurrentText("MAM1")
        self.spn_mod_index.setValue(0.6)
        self.chk_fixed_duty_bypass.setChecked(False)
        self.chk_safe_clamp.setChecked(True)
        self.spn_envelope_scale_q8.setValue(256)
        self.mod_param_changed()

    def apply_legacy_preset(self):
        self.cmb_mod_mode.setCurrentText("Legacy SRAM")
        self.spn_mod_index.setValue(0.7)
        self.chk_fixed_duty_bypass.setChecked(False)
        self.spn_envelope_scale_q8.setValue(256)
        self.mod_param_changed()

    def apply_dsb_preset(self):
        self.cmb_mod_mode.setCurrentText("DSB-AM")
        self.spn_mod_index.setValue(0.4)
        self.chk_fixed_duty_bypass.setChecked(False)
        self.spn_envelope_scale_q8.setValue(192)
        self.mod_param_changed()

    def apply_all_mask(self):
        self.txt_output_mask.setText("%016X" % self.default_mask())

    def apply_zero_mask(self):
        self.txt_output_mask.setText("%016X" % 0)

    def apply_single_channel_mask(self):
        ch = max(0, min(self.profile().channel_count - 1, self.spn_single_channel.value()))
        self.txt_output_mask.setText("%016X" % (1 << ch))

    def apply_unit_mask(self):
        if self.profile_name != array_profiles.PROFILE_N60:
            self.log("N60 unit mask is only valid for the N60 profile", "#FFC107")
            return
        unit = max(0, min(4, self.spn_unit.value()))
        mask = ((1 << 12) - 1) << (unit * 12)
        self.txt_output_mask.setText("%016X" % mask)

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
