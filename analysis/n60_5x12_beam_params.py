import csv
import math
import os
from collections import namedtuple

import numpy as np

try:
    import design_n12_unit as n12_base
except ImportError:
    n12_base = None


CHANNEL_COUNT = 60
UNIT_COUNT = 5
ELEMENTS_PER_UNIT = 12
UNIT_ANGLES_DEG = (-45.0, -22.5, 0.0, 22.5, 45.0)

SOUND_SPEED_M_S = 343.0
CARRIER_HZ = 40000.0
PWM_PERIOD_TICKS = 2500
ELEMENT_DIAMETER_MM = 16.0
MIN_DISTANCE_MM = 500
MAX_DISTANCE_MM = 5000
MAX_STEER_DEG = 30.0

MODE_UNIFORM = "uniform"
MODE_UNIT_COSINE = "unit_cosine"
MODE_UNIT_COSINE_HAMMING = "unit_cosine_hamming"
MODE_OPTIMIZED_DBC_MARGIN = "optimized_dbc_margin"
MODE_OPTIMIZED_TABLE = "optimized_table"
MODE_OPTIMIZED_AGGRESSIVE = "optimized_aggressive"
AMPLITUDE_MODES = (
    MODE_UNIFORM,
    MODE_UNIT_COSINE,
    MODE_UNIT_COSINE_HAMMING,
    MODE_OPTIMIZED_DBC_MARGIN,
    MODE_OPTIMIZED_TABLE,
    MODE_OPTIMIZED_AGGRESSIVE,
)

DEFAULT_UNIT_GAIN_FLOOR = 0.15
DEFAULT_UNIT_GAIN_GAMMA = 2.0

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "analysis_outputs")
DEFAULT_LAYOUT_CSV = os.path.join(OUT_DIR, "agent_parametric_best.csv")
DEFAULT_DBC_MARGIN_OPT_TABLE_CSV = os.path.join(OUT_DIR, "n60_5x12_focus_table_dbc_margin.csv")
DEFAULT_OPT_TABLE_CSV = os.path.join(OUT_DIR, "n60_5x12_focus_table.csv")
DEFAULT_AGGRESSIVE_OPT_TABLE_CSV = os.path.join(OUT_DIR, "n60_5x12_focus_table_aggressive.csv")


BeamResult = namedtuple(
    "BeamResult",
    [
        "amplitudes",
        "phases",
        "raw_amplitudes",
        "distance_mm",
        "actual_az_deg",
        "actual_el_deg",
        "combined_angle_deg",
        "target_m",
        "mode",
    ],
)


def clamp(value, low, high):
    return max(low, min(high, value))


def load_n12_layout(path=None):
    csv_path = path or DEFAULT_LAYOUT_CSV
    points = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            points.append([float(row["X_mm"]), float(row["Y_mm"])])
    if len(points) != ELEMENTS_PER_UNIT:
        raise ValueError("N12 unit layout must contain exactly 12 elements")
    pts = np.asarray(points, dtype=float)
    return pts - np.mean(pts, axis=0)


def build_geometry(unit_layout_mm=None):
    unit_local = np.asarray(unit_layout_mm if unit_layout_mm is not None else load_n12_layout(), dtype=float)
    if len(unit_local) != ELEMENTS_PER_UNIT:
        raise ValueError("unit layout must contain 12 elements")

    angles_rad = np.deg2rad(np.asarray(UNIT_ANGLES_DEG, dtype=float))
    half_width_m = float(np.max(unit_local[:, 0]) - np.min(unit_local[:, 0])) * 0.5e-3
    delta_rad = abs(angles_rad[1] - angles_rad[0])
    radius_m = half_width_m / math.tan(delta_rad * 0.5)

    positions = []
    normals = []
    unit_ids = []
    element_ids = []
    for unit_id, alpha in enumerate(angles_rad):
        center = np.asarray([
            radius_m * math.sin(alpha),
            0.0,
            -radius_m * math.cos(alpha),
        ])
        x_local = np.asarray([math.cos(alpha), 0.0, math.sin(alpha)])
        y_local = np.asarray([0.0, 1.0, 0.0])
        normal = np.asarray([-math.sin(alpha), 0.0, math.cos(alpha)])

        for element_id, (x_mm, y_mm) in enumerate(unit_local):
            position = center + x_mm * 1e-3 * x_local + y_mm * 1e-3 * y_local
            positions.append(position)
            normals.append(normal)
            unit_ids.append(unit_id)
            element_ids.append(element_id)

    return {
        "positions": np.asarray(positions, dtype=float),
        "normals": np.asarray(normals, dtype=float),
        "unit_ids": np.asarray(unit_ids, dtype=int),
        "element_ids": np.asarray(element_ids, dtype=int),
        "unit_layout_mm": unit_local,
        "unit_angles_deg": np.asarray(UNIT_ANGLES_DEG, dtype=float),
        "radius_m": radius_m,
    }


def limit_direction(az_deg, el_deg, max_angle_deg=MAX_STEER_DEG):
    sx = math.sin(math.radians(float(az_deg)))
    sy = math.sin(math.radians(float(el_deg)))
    max_s = math.sin(math.radians(max_angle_deg))
    sxy = math.hypot(sx, sy)
    if sxy > max_s and sxy > 0.0:
        scale = max_s / sxy
        sx *= scale
        sy *= scale
        sxy = max_s
    sz = math.sqrt(max(0.0, 1.0 - sx * sx - sy * sy))
    actual_az = math.degrees(math.asin(clamp(sx, -1.0, 1.0)))
    actual_el = math.degrees(math.asin(clamp(sy, -1.0, 1.0)))
    combined = math.degrees(math.asin(clamp(sxy, 0.0, 1.0)))
    return sx, sy, sz, actual_az, actual_el, combined


def focal_point(distance_mm, az_deg, el_deg):
    distance_mm = int(round(clamp(distance_mm, MIN_DISTANCE_MM, MAX_DISTANCE_MM)))
    distance_m = distance_mm / 1000.0
    sx, sy, sz, actual_az, actual_el, combined = limit_direction(az_deg, el_deg)
    return distance_mm, np.asarray([distance_m * sx, distance_m * sy, distance_m * sz]), actual_az, actual_el, combined


def unit_cosine_gains(az_deg, floor=DEFAULT_UNIT_GAIN_FLOOR, gamma=DEFAULT_UNIT_GAIN_GAMMA):
    gains = []
    for angle in UNIT_ANGLES_DEG:
        delta = math.radians(abs(float(angle) - float(az_deg)))
        gains.append(floor + (1.0 - floor) * max(0.0, math.cos(delta)) ** gamma)
    return np.asarray(gains, dtype=float)


def radial_hamming_apodization(unit_layout_mm):
    pts = np.asarray(unit_layout_mm, dtype=float)
    radii = np.linalg.norm(pts, axis=1)
    max_r = max(float(np.max(radii)), 1e-9)
    return np.clip(0.54 + 0.46 * np.cos(math.pi * radii / max_r), 0.0, 1.0)


def mode_amplitudes(geometry, az_deg, mode=MODE_UNIFORM, optimized_table=None, distance_mm=2000, el_deg=0.0):
    if mode == MODE_UNIFORM:
        return np.ones(CHANNEL_COUNT, dtype=float)

    unit_gains = unit_cosine_gains(az_deg)
    local = np.ones(ELEMENTS_PER_UNIT, dtype=float)
    if mode == MODE_UNIT_COSINE_HAMMING:
        local = radial_hamming_apodization(geometry["unit_layout_mm"])
    elif mode in (MODE_OPTIMIZED_DBC_MARGIN, MODE_OPTIMIZED_TABLE, MODE_OPTIMIZED_AGGRESSIVE):
        if optimized_table is None:
            table_path = DEFAULT_OPT_TABLE_CSV
            if mode == MODE_OPTIMIZED_DBC_MARGIN:
                table_path = DEFAULT_DBC_MARGIN_OPT_TABLE_CSV
            elif mode == MODE_OPTIMIZED_AGGRESSIVE:
                table_path = DEFAULT_AGGRESSIVE_OPT_TABLE_CSV
            optimized_table = load_optimized_table(table_path)
        if optimized_table:
            return nearest_optimized_amplitudes(optimized_table, az_deg, distance_mm=distance_mm, el_deg=el_deg)
        mode = MODE_UNIT_COSINE_HAMMING

    amps = np.zeros(CHANNEL_COUNT, dtype=float)
    for ch, unit_id in enumerate(geometry["unit_ids"]):
        elem_id = geometry["element_ids"][ch]
        amps[ch] = unit_gains[unit_id] * local[elem_id]
    return np.clip(amps, 0.0, 1.0)


def calculate_phases(geometry, target_m):
    positions = geometry["positions"]
    distances = np.linalg.norm(target_m[None, :] - positions, axis=1)
    reference = np.linalg.norm(target_m)
    phase_cycles = (distances - reference) * CARRIER_HZ / SOUND_SPEED_M_S
    return np.mod(np.rint(np.mod(phase_cycles, 1.0) * PWM_PERIOD_TICKS), PWM_PERIOD_TICKS).astype(int)


def calculate_focus_params(distance_mm=2000, az_deg=0.0, el_deg=0.0, mode=MODE_UNIT_COSINE_HAMMING, geometry=None, optimized_table=None):
    if mode not in AMPLITUDE_MODES:
        raise ValueError("unknown N60 amplitude mode: %s" % mode)

    geometry = geometry or build_geometry()
    distance_mm, target, actual_az, actual_el, combined = focal_point(distance_mm, az_deg, el_deg)
    raw_amps = mode_amplitudes(
        geometry,
        actual_az,
        mode,
        optimized_table=optimized_table,
        distance_mm=distance_mm,
        el_deg=actual_el,
    )
    amp_u8 = [int(round(clamp(v, 0.0, 1.0) * 255.0)) for v in raw_amps]
    phases = calculate_phases(geometry, target).tolist()
    return BeamResult(
        amplitudes=amp_u8,
        phases=phases,
        raw_amplitudes=raw_amps.tolist(),
        distance_mm=distance_mm,
        actual_az_deg=actual_az,
        actual_el_deg=actual_el,
        combined_angle_deg=combined,
        target_m=tuple(float(v) for v in target),
        mode=mode,
    )


def write_geometry_csv(path, geometry):
    with open(path, "w", newline="") as f:
        fields = ["global_id", "unit_id", "element_id", "unit_angle_deg", "x_m", "y_m", "z_m", "nx", "ny", "nz"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i in range(CHANNEL_COUNT):
            p = geometry["positions"][i]
            n = geometry["normals"][i]
            u = int(geometry["unit_ids"][i])
            writer.writerow({
                "global_id": i,
                "unit_id": u,
                "element_id": int(geometry["element_ids"][i]),
                "unit_angle_deg": "%.3f" % UNIT_ANGLES_DEG[u],
                "x_m": "%.9f" % p[0],
                "y_m": "%.9f" % p[1],
                "z_m": "%.9f" % p[2],
                "nx": "%.9f" % n[0],
                "ny": "%.9f" % n[1],
                "nz": "%.9f" % n[2],
            })


def load_optimized_table(path=None):
    table_path = path or DEFAULT_OPT_TABLE_CSV
    if not os.path.exists(table_path):
        return []
    rows = []
    with open(table_path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append({
                "distance_mm": int(row["distance_mm"]),
                "az_deg": float(row["az_deg"]),
                "el_deg": float(row["el_deg"]),
                "amplitudes": [float(row["amp_%02d" % i]) for i in range(CHANNEL_COUNT)],
            })
    return rows


def nearest_optimized_amplitudes(table, az_deg, distance_mm=2000, el_deg=0.0):
    if not table:
        return np.ones(CHANNEL_COUNT, dtype=float)
    best = min(
        table,
        key=lambda row: (
            abs(row["az_deg"] - float(az_deg)) / 30.0
            + abs(row["el_deg"] - float(el_deg)) / 15.0
            + abs(row["distance_mm"] - int(distance_mm)) / 5000.0
        ),
    )
    return np.asarray(best["amplitudes"], dtype=float)


def piston_from_cos(cos_theta):
    if n12_base is not None:
        return n12_base.piston_from_cos(cos_theta)
    cos_theta = np.asarray(cos_theta)
    return np.where(cos_theta > 0.0, 1.0, 0.0)
