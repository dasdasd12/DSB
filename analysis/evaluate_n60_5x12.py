import csv
import math
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize

import n60_5x12_beam_params as n60


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "analysis_outputs")
DB_FLOOR = -55.0
PROBE_SPAN_DEG = 18.0
PROBE_N_EVAL = 23
PROBE_N_OPT = 17
MAIN_EXCLUDE_DEG = 8.0
SMOOTH_BETA = 35.0
GAIN_FLOORS = (0.25, 0.35, 0.50, 0.70)

DISTANCES_M = (0.5, 1.0, 2.0, 3.0, 5.0)
AZIMUTHS_DEG = tuple(float(v) for v in range(-30, 31, 5))
ELEVATIONS_DEG = (0.0,)
PLOT_CASES = tuple(
    (distance_m, az_deg, 0.0)
    for distance_m in (0.5, 2.0, 5.0)
    for az_deg in (-30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0)
)
PEAK_DIRECTION_LIMIT_DEG = 3.0

MODES = (
    n60.MODE_UNIFORM,
    n60.MODE_UNIT_COSINE,
    n60.MODE_UNIT_COSINE_HAMMING,
    n60.MODE_OPTIMIZED_DBC_MARGIN,
    n60.MODE_OPTIMIZED_TABLE,
    n60.MODE_OPTIMIZED_AGGRESSIVE,
)


def ensure_out_dir():
    os.makedirs(OUT_DIR, exist_ok=True)


def probe_grid(distance_m, az_deg, el_deg, span_deg, n):
    offsets = np.linspace(-span_deg, span_deg, n)
    ox, oy = np.meshgrid(offsets, offsets)
    abs_az = az_deg + ox
    abs_el = el_deg + oy
    sx = np.sin(np.deg2rad(abs_az))
    sy = np.sin(np.deg2rad(abs_el))
    sz = np.sqrt(np.maximum(0.0, 1.0 - sx * sx - sy * sy))
    probes = np.column_stack([
        (distance_m * sx).ravel(),
        (distance_m * sy).ravel(),
        (distance_m * sz).ravel(),
    ])
    sep = np.sqrt(ox * ox + oy * oy).ravel()
    return probes, ox, oy, sep > MAIN_EXCLUDE_DEG


def build_case_matrix(geometry, distance_m, az_deg, el_deg, probe_n):
    distance_mm, target, actual_az, actual_el, combined = n60.focal_point(distance_m * 1000.0, az_deg, el_deg)
    probes, ox, oy, outside = probe_grid(distance_m, actual_az, actual_el, PROBE_SPAN_DEG, probe_n)
    positions = geometry["positions"]
    normals = geometry["normals"]

    delta = probes[:, None, :] - positions[None, :, :]
    dist = np.maximum(np.linalg.norm(delta, axis=2), 1e-6)
    direction = delta / dist[:, :, None]
    cos_theta = np.sum(direction * normals[None, :, :], axis=2)
    element = n60.piston_from_cos(cos_theta)

    focal_delta = target[None, :] - positions
    focal_dist = np.maximum(np.linalg.norm(focal_delta, axis=1), 1e-6)
    focus_phase = np.exp(-1j * n60.CARRIER_HZ * 2.0 * math.pi / n60.SOUND_SPEED_M_S * focal_dist)
    h = element * np.exp(1j * n60.CARRIER_HZ * 2.0 * math.pi / n60.SOUND_SPEED_M_S * dist) / dist * focus_phase[None, :]

    focal_dir = focal_delta / focal_dist[:, None]
    focal_cos = np.sum(focal_dir * normals, axis=1)
    focal_element = n60.piston_from_cos(focal_cos)
    focal_resp_per_elem = focal_element / focal_dist

    return {
        "h": h,
        "focal_resp_per_elem": focal_resp_per_elem,
        "outside": outside,
        "ox": ox,
        "oy": oy,
        "distance_mm": distance_mm,
        "distance_m": distance_mm / 1000.0,
        "az_deg": actual_az,
        "el_deg": actual_el,
        "combined_angle_deg": combined,
        "probe_shape": ox.shape,
    }


def metrics_for_amplitudes(case, amplitudes, reference_target=None):
    amp = np.asarray(amplitudes, dtype=float)
    resp = case["h"].dot(amp)
    focal = complex(case["focal_resp_per_elem"].dot(amp))
    target = max(abs(focal), 1e-18)
    ref = target if reference_target is None else max(reference_target, 1e-18)
    db = 20.0 * np.log10(np.abs(resp) / target + 1e-12)
    outside_db = db[case["outside"]]
    return {
        "max_sidelobe_db": float(np.max(outside_db)),
        "p99_sidelobe_db": float(np.percentile(outside_db, 99.0)),
        "p95_sidelobe_db": float(np.percentile(outside_db, 95.0)),
        "target_gain_delta_db": float(20.0 * math.log10(target / ref + 1e-12)),
        "mean_amp": float(np.mean(amp)),
        "min_amp": float(np.min(amp)),
        "max_amp": float(np.max(amp)),
        "db_grid": db.reshape(case["probe_shape"]),
        "target_abs": target,
    }


def direction_check_for_metrics(case, metrics):
    db_grid = metrics["db_grid"]
    ox = case["ox"]
    oy = case["oy"]
    outside = case["outside"].reshape(case["probe_shape"])

    peak_flat = int(np.argmax(db_grid))
    peak_idx = np.unravel_index(peak_flat, db_grid.shape)
    peak_offset_x = float(ox[peak_idx])
    peak_offset_y = float(oy[peak_idx])
    peak_offset_deg = float(math.hypot(peak_offset_x, peak_offset_y))

    outside_grid = np.where(outside, db_grid, -1e12)
    side_flat = int(np.argmax(outside_grid))
    side_idx = np.unravel_index(side_flat, db_grid.shape)
    side_offset_x = float(ox[side_idx])
    side_offset_y = float(oy[side_idx])
    side_offset_deg = float(math.hypot(side_offset_x, side_offset_y))

    return {
        "peak_offset_az_deg": peak_offset_x,
        "peak_offset_el_deg": peak_offset_y,
        "peak_offset_deg": peak_offset_deg,
        "peak_db": float(db_grid[peak_idx]),
        "max_sidelobe_offset_az_deg": side_offset_x,
        "max_sidelobe_offset_el_deg": side_offset_y,
        "max_sidelobe_offset_deg": side_offset_deg,
        "max_sidelobe_db": float(db_grid[side_idx]),
        "peak_direction_pass": peak_offset_deg <= PEAK_DIRECTION_LIMIT_DEG,
    }


def smooth_max(values, beta=SMOOTH_BETA):
    values = np.asarray(values, dtype=float)
    peak = float(np.max(values))
    return peak + float(np.log(np.mean(np.exp(beta * (values - peak)))) / beta)


def candidate_starts(geometry, case):
    base = [
        np.ones(n60.CHANNEL_COUNT, dtype=float),
        n60.mode_amplitudes(geometry, case["az_deg"], n60.MODE_UNIT_COSINE),
        n60.mode_amplitudes(geometry, case["az_deg"], n60.MODE_UNIT_COSINE_HAMMING),
    ]
    unit_gains = n60.unit_cosine_gains(case["az_deg"], floor=0.45, gamma=1.0)
    mild = np.asarray([unit_gains[unit_id] for unit_id in geometry["unit_ids"]], dtype=float)
    base.append(mild)
    return [np.clip(v, 0.0, 1.0) for v in base]


def optimize_case_amplitudes(case, starts, gain_floors=GAIN_FLOORS):
    h = case["h"][case["outside"]]
    focal = case["focal_resp_per_elem"]
    ref_target = max(float(focal.dot(np.ones(n60.CHANNEL_COUNT))), 1e-18)
    best_by_floor = {}
    all_candidates = []

    def sidelobe_objective(x):
        amp = np.clip(x, 0.0, 1.0)
        side = np.abs(h.dot(amp))
        target = max(float(abs(focal.dot(amp))), 1e-18)
        rel = side / target
        p995 = float(np.percentile(rel, 99.5))
        return 0.72 * smooth_max(rel) + 0.28 * p995 + 0.0005 * float(np.mean((amp - 0.65) ** 2))

    def margin_objective(x):
        amp = np.clip(x, 0.0, 1.0)
        side = np.abs(h.dot(amp))
        target = max(float(abs(focal.dot(amp))), 1e-18)
        rel = np.maximum(side / target, 1e-12)
        smooth_sl_db = 20.0 * math.log10(max(smooth_max(rel), 1e-12))
        p99_sl_db = 20.0 * math.log10(max(float(np.percentile(rel, 99.0)), 1e-12))
        gain_delta_db = 20.0 * math.log10(target / ref_target + 1e-12)
        gain_loss_db = max(0.0, -gain_delta_db)
        amp_shape_penalty = 0.001 * float(np.mean((amp - 0.70) ** 2))
        return smooth_sl_db + gain_loss_db + 0.25 * (p99_sl_db + gain_loss_db) + amp_shape_penalty

    def make_candidate(result, amp, score, gain_floor, kind):
        metrics = metrics_for_amplitudes(case, amp, reference_target=ref_target)
        return {
            "amplitudes": amp,
            "success": bool(result.success),
            "objective": float(result.fun),
            "score": float(score),
            "gain_floor": float(gain_floor),
            "kind": kind,
            "metrics": metrics,
        }

    margin_candidates = []
    for start in starts:
        start = np.clip(np.asarray(start, dtype=float), 0.0, 1.0)
        result = minimize(
            margin_objective,
            start,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * n60.CHANNEL_COUNT,
            constraints=({
                "type": "ineq",
                "fun": lambda x: float(abs(focal.dot(np.clip(x, 0.0, 1.0)))) - 0.15 * ref_target,
            },),
            options={"maxiter": 220, "ftol": 1e-9, "disp": False},
        )
        amp = np.clip(result.x, 0.0, 1.0)
        metrics = metrics_for_amplitudes(case, amp, reference_target=ref_target)
        margin_score = (
            metrics["max_sidelobe_db"]
            + max(0.0, -metrics["target_gain_delta_db"])
            + 0.25 * (metrics["p99_sidelobe_db"] + max(0.0, -metrics["target_gain_delta_db"]))
        )
        margin_candidates.append(make_candidate(result, amp, margin_score, 0.15, "dbc_margin"))

    for gain_floor in gain_floors:
        min_target = gain_floor * ref_target
        floor_candidates = []
        for start in starts:
            start = np.clip(np.asarray(start, dtype=float), 0.0, 1.0)
            if float(focal.dot(start)) < min_target:
                start = np.clip(start + (1.0 - start) * 0.5, 0.0, 1.0)

            result = minimize(
                sidelobe_objective,
                start,
                method="SLSQP",
                bounds=[(0.0, 1.0)] * n60.CHANNEL_COUNT,
                constraints=({
                    "type": "ineq",
                    "fun": lambda x, mt=min_target: float(focal.dot(np.clip(x, 0.0, 1.0))) - mt,
                },),
                options={"maxiter": 180, "ftol": 1e-9, "disp": False},
            )
            amp = np.clip(result.x, 0.0, 1.0)
            metrics = metrics_for_amplitudes(case, amp, reference_target=ref_target)
            score = metrics["max_sidelobe_db"] + 0.35 * metrics["p99_sidelobe_db"]
            candidate = make_candidate(result, amp, score, gain_floor, "sidelobe")
            floor_candidates.append(candidate)
            all_candidates.append(candidate)
        best_by_floor[gain_floor] = min(floor_candidates, key=lambda row: row["score"])

    dbc_margin = min(margin_candidates, key=lambda row: row["score"])
    balanced = best_by_floor[0.50]
    aggressive = min(all_candidates, key=lambda row: row["score"])
    return dbc_margin, balanced, aggressive, best_by_floor, margin_candidates + all_candidates


def amplitudes_for_mode(geometry, case, mode, optimized_by_key):
    if mode in (n60.MODE_OPTIMIZED_DBC_MARGIN, n60.MODE_OPTIMIZED_TABLE, n60.MODE_OPTIMIZED_AGGRESSIVE):
        return optimized_by_key[(case["distance_mm"], case["az_deg"], case["el_deg"])]
    return n60.mode_amplitudes(geometry, case["az_deg"], mode)


def write_focus_table(path, rows):
    fields = ["distance_mm", "az_deg", "el_deg", "gain_floor", "score", "success"] + ["amp_%02d" % i for i in range(n60.CHANNEL_COUNT)]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {
                "distance_mm": row["distance_mm"],
                "az_deg": "%.3f" % row["az_deg"],
                "el_deg": "%.3f" % row["el_deg"],
                "gain_floor": "%.3f" % row.get("gain_floor", 0.0),
                "score": "%.6f" % row.get("score", 0.0),
                "success": int(bool(row.get("success", False))),
            }
            for i, amp in enumerate(row["amplitudes"]):
                out["amp_%02d" % i] = "%.6f" % amp
            writer.writerow(out)


def write_metrics(path, rows):
    fields = [
        "distance_m",
        "az_deg",
        "el_deg",
        "mode",
        "max_sidelobe_db",
        "dbc",
        "dbc_improvement_db",
        "gain_loss_db",
        "dbc_gain_margin_db",
        "p99_sidelobe_db",
        "p99_dbc",
        "p99_dbc_improvement_db",
        "p99_dbc_gain_margin_db",
        "p95_sidelobe_db",
        "target_gain_delta_db",
        "mean_amp",
        "min_amp",
        "max_amp",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {k: row[k] for k in ("distance_m", "az_deg", "el_deg", "mode")}
            for k in fields:
                if k in row["metrics"]:
                    out[k] = "%.6f" % row["metrics"][k]
            writer.writerow(out)


def write_peak_direction_check(path, rows):
    fields = [
        "distance_m",
        "az_deg",
        "el_deg",
        "mode",
        "peak_offset_az_deg",
        "peak_offset_el_deg",
        "peak_offset_deg",
        "peak_db",
        "max_sidelobe_offset_az_deg",
        "max_sidelobe_offset_el_deg",
        "max_sidelobe_offset_deg",
        "max_sidelobe_db",
        "peak_direction_pass",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            check = row["direction_check"]
            out = {k: row[k] for k in ("distance_m", "az_deg", "el_deg", "mode")}
            for k in fields:
                if k in check:
                    value = check[k]
                    out[k] = int(value) if isinstance(value, bool) else "%.6f" % value
            writer.writerow(out)


def plot_geometry(path, geometry):
    fig, ax = plt.subplots(figsize=(10.0, 6.5))
    colors = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2"]
    for unit_id, angle in enumerate(n60.UNIT_ANGLES_DEG):
        mask = geometry["unit_ids"] == unit_id
        pts = geometry["positions"][mask]
        ax.scatter(pts[:, 0] * 1000.0, pts[:, 2] * 1000.0, s=36, color=colors[unit_id], label="unit %d %.1f deg" % (unit_id, angle))
        center = np.mean(pts, axis=0)
        normal = geometry["normals"][mask][0]
        ax.arrow(center[0] * 1000.0, center[2] * 1000.0, normal[0] * 80.0, normal[2] * 80.0, color=colors[unit_id], head_width=5)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("z (mm)")
    ax.set_title("N60 5x12 bowl geometry, R=%.3f m" % geometry["radius_m"])
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def plot_unit_gains(path):
    az_values = np.linspace(-30.0, 30.0, 121)
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    gains = np.asarray([n60.unit_cosine_gains(az) for az in az_values])
    for idx, angle in enumerate(n60.UNIT_ANGLES_DEG):
        ax.plot(az_values, gains[:, idx], label="unit %.1f deg" % angle)
    ax.set_xlabel("target azimuth (deg)")
    ax.set_ylabel("unit gain")
    ax.set_ylim(0, 1.05)
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=3, fontsize=8)
    ax.set_title("Reverse-side unit attenuation, floor=0.15 gamma=2")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def plot_patterns(path, rows):
    plot_distances = (0.5, 2.0, 5.0)
    plot_azimuths = (-30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0)
    plot_modes = (n60.MODE_UNIFORM, n60.MODE_OPTIMIZED_DBC_MARGIN, n60.MODE_OPTIMIZED_TABLE)
    mode_labels = {
        n60.MODE_UNIFORM: "uniform",
        n60.MODE_OPTIMIZED_DBC_MARGIN: "dBc margin",
        n60.MODE_OPTIMIZED_TABLE: "balanced",
    }

    fig, axes = plt.subplots(
        len(plot_azimuths),
        len(plot_distances) * len(plot_modes),
        figsize=(24.0, 18.0),
        sharex=True,
        sharey=True,
    )
    levels = np.linspace(DB_FLOOR, 0.0, 56)
    contour = None
    for row_idx, az_deg in enumerate(plot_azimuths):
        for dist_idx, distance_m in enumerate(plot_distances):
            for mode_idx, mode in enumerate(plot_modes):
                col_idx = dist_idx * len(plot_modes) + mode_idx
                row = next(
                    r for r in rows
                    if abs(r["distance_m"] - distance_m) < 1e-9
                    and abs(r["az_deg"] - az_deg) < 1e-9
                    and abs(r["el_deg"]) < 1e-9
                    and r["mode"] == mode
                )
                ax = axes[row_idx, col_idx]
                db = np.maximum(row["metrics"]["db_grid"], DB_FLOOR)
                contour = ax.contourf(row["case"]["ox"], row["case"]["oy"], db, levels=levels, cmap="viridis", extend="min")
                check = row["direction_check"]
                ax.plot([0.0], [0.0], "rx", ms=6, mew=1.5, label="target")
                ax.plot([check["peak_offset_az_deg"]], [check["peak_offset_el_deg"]], "wo", ms=4, mec="black", mew=0.7, label="peak")
                ax.plot([check["max_sidelobe_offset_az_deg"]], [check["max_sidelobe_offset_el_deg"]], "k^", ms=4, label="sidelobe")
                ax.set_aspect("equal", adjustable="box")
                ax.set_xlim(-PROBE_SPAN_DEG, PROBE_SPAN_DEG)
                ax.set_ylim(-PROBE_SPAN_DEG, PROBE_SPAN_DEG)
                if row_idx == 0:
                    ax.set_title("%.1fm %s" % (distance_m, mode_labels[mode]), fontsize=8)
                if col_idx == 0:
                    ax.set_ylabel("az %+.0f\nel offset" % az_deg, fontsize=8)
                else:
                    ax.set_ylabel("")
                ax.text(
                    0.02,
                    0.02,
                    "m %.1f / off %.1f" % (row["metrics"].get("dbc_gain_margin_db", 0.0), check["peak_offset_deg"]),
                    transform=ax.transAxes,
                    fontsize=6,
                    color="white",
                    ha="left",
                    va="bottom",
                    bbox={"facecolor": "black", "alpha": 0.35, "pad": 1.0, "edgecolor": "none"},
                )
                ax.grid(True, color="white", alpha=0.12)
                if row_idx == len(plot_azimuths) - 1:
                    ax.set_xlabel("az offset", fontsize=7)
    fig.subplots_adjust(left=0.05, right=0.90, top=0.94, bottom=0.05, wspace=0.12, hspace=0.18)
    cbar_ax = fig.add_axes([0.925, 0.20, 0.012, 0.60])
    cbar = fig.colorbar(contour, cax=cbar_ax)
    cbar.set_label("relative pressure (dB)")
    fig.suptitle("N60 5x12 horizontal directivity heatmaps")
    fig.savefig(path, dpi=170)
    plt.close(fig)


def plot_amplitudes(path, geometry, optimized_rows, title):
    fig, axes = plt.subplots(2, 2, figsize=(12.0, 7.5))
    for ax, case in zip(axes.ravel(), PLOT_CASES):
        row = next(r for r in optimized_rows if abs(r["distance_m"] - case[0]) < 1e-9 and abs(r["az_deg"] - case[1]) < 1e-9 and abs(r["el_deg"] - case[2]) < 1e-9)
        vals = np.asarray(row["amplitudes"]).reshape(n60.UNIT_COUNT, n60.ELEMENTS_PER_UNIT)
        im = ax.imshow(vals, vmin=0.0, vmax=1.0, cmap="magma", aspect="auto")
        ax.set_title("%.1fm az %.0f el %.0f amp" % case)
        ax.set_xlabel("element id")
        ax.set_ylabel("unit id")
        ax.set_yticks(range(n60.UNIT_COUNT))
        ax.set_xticks(range(n60.ELEMENTS_PER_UNIT))
    fig.colorbar(im, ax=axes, shrink=0.8)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def write_summary(path, rows):
    by_mode = {mode: [r for r in rows if r["mode"] == mode] for mode in MODES}
    uniform = by_mode[n60.MODE_UNIFORM]
    hamming = by_mode[n60.MODE_UNIT_COSINE_HAMMING]
    dbc_margin_opt = by_mode[n60.MODE_OPTIMIZED_DBC_MARGIN]
    balanced_opt = by_mode[n60.MODE_OPTIMIZED_TABLE]
    aggressive_opt = by_mode[n60.MODE_OPTIMIZED_AGGRESSIVE]

    def count_positive_margin(mode_rows, metric="dbc_gain_margin_db"):
        return sum(1 for row in mode_rows if row["metrics"].get(metric, -1e9) > 0.0)

    def average_metric(mode_rows, metric):
        return float(np.mean([row["metrics"].get(metric, 0.0) for row in mode_rows]))
    big_angle = [r for r in hamming if abs(r["az_deg"]) >= 15.0]
    big_angle_wins = 0
    for row in big_angle:
        base = next(r for r in uniform if r["distance_m"] == row["distance_m"] and r["az_deg"] == row["az_deg"] and r["el_deg"] == row["el_deg"])
        if row["metrics"]["p99_sidelobe_db"] <= base["metrics"]["p99_sidelobe_db"]:
            big_angle_wins += 1

    gain_warnings = [
        r for r in rows
        if r["mode"] != n60.MODE_UNIFORM and r["metrics"]["target_gain_delta_db"] < -6.0
    ]
    direction_failures = [
        r for r in rows
        if r["mode"] in (n60.MODE_UNIFORM, n60.MODE_OPTIMIZED_DBC_MARGIN, n60.MODE_OPTIMIZED_TABLE)
        and not r["direction_check"]["peak_direction_pass"]
    ]

    with open(path, "w") as f:
        f.write("N60 5x12 horizontal dBc-margin optimization study\n")
        f.write("==================================================\n")
        f.write("Geometry: 5 x N12 units, angles %s deg\n" % ", ".join("%.1f" % v for v in n60.UNIT_ANGLES_DEG))
        f.write("Unit attenuation: floor=%.2f gamma=%.1f\n" % (n60.DEFAULT_UNIT_GAIN_FLOOR, n60.DEFAULT_UNIT_GAIN_GAMMA))
        f.write("Full 60-channel optimization: SLSQP; optimized_dbc_margin maximizes dBc improvement minus gain loss, optimized_table keeps 0.50 gain floor, optimized_aggressive chooses best sidelobe score across floors %s.\n" % (
            ", ".join("%.2f" % v for v in GAIN_FLOORS)
        ))
        f.write("Directionality check: heatmap peak offset must be <= %.1f deg from target.\n" % PEAK_DIRECTION_LIMIT_DEG)
        f.write("Cases: %d distances x %d azimuths x %d elevations = %d cases\n\n" % (
            len(DISTANCES_M), len(AZIMUTHS_DEG), len(ELEVATIONS_DEG), len(DISTANCES_M) * len(AZIMUTHS_DEG) * len(ELEVATIONS_DEG)
        ))

        f.write("Averages by mode:\n")
        f.write("%-24s %10s %10s %10s %10s %10s %10s\n" % (
            "mode", "maxSL", "dBc+", "gainLoss", "margin", "p99SL", "meanAmp"
        ))
        for mode in MODES:
            values = by_mode[mode]
            f.write("%-24s %10.2f %10.2f %10.2f %10.2f %10.2f %10.2f\n" % (
                mode,
                average_metric(values, "max_sidelobe_db"),
                average_metric(values, "dbc_improvement_db"),
                average_metric(values, "gain_loss_db"),
                average_metric(values, "dbc_gain_margin_db"),
                average_metric(values, "p99_sidelobe_db"),
                average_metric(values, "mean_amp"),
            ))

        f.write("\nLarge-angle p99 result: unit_cosine_hamming beats/equal uniform in %d/%d large-angle cases.\n" % (big_angle_wins, len(big_angle)))
        balanced_wins = sum(
            1 for row in balanced_opt
            if row["metrics"]["p99_sidelobe_db"] <= next(
                r for r in uniform
                if r["distance_m"] == row["distance_m"] and r["az_deg"] == row["az_deg"] and r["el_deg"] == row["el_deg"]
            )["metrics"]["p99_sidelobe_db"]
        )
        aggressive_wins = sum(
            1 for row in aggressive_opt
            if row["metrics"]["p99_sidelobe_db"] <= next(
                r for r in uniform
                if r["distance_m"] == row["distance_m"] and r["az_deg"] == row["az_deg"] and r["el_deg"] == row["el_deg"]
            )["metrics"]["p99_sidelobe_db"]
        )
        f.write("Balanced 60-channel optimized table beats/equal uniform p99 in %d/%d cases.\n" % (balanced_wins, len(balanced_opt)))
        f.write("Aggressive 60-channel optimized table beats/equal uniform p99 in %d/%d cases.\n" % (aggressive_wins, len(aggressive_opt)))
        f.write("\nEngineering criterion: dBc improvement must exceed gain loss.\n")
        for mode in MODES:
            if mode == n60.MODE_UNIFORM:
                continue
            values = by_mode[mode]
            f.write("  %-22s maxSL dBc margin positive: %d/%d, avg margin %.2f dB; p99 margin positive: %d/%d, avg margin %.2f dB\n" % (
                mode,
                count_positive_margin(values, "dbc_gain_margin_db"),
                len(values),
                average_metric(values, "dbc_gain_margin_db"),
                count_positive_margin(values, "p99_dbc_gain_margin_db"),
                len(values),
                average_metric(values, "p99_dbc_gain_margin_db"),
            ))
        dbc_avg_margin = average_metric(dbc_margin_opt, "dbc_gain_margin_db")
        balanced_avg_margin = average_metric(balanced_opt, "dbc_gain_margin_db")
        if dbc_avg_margin > balanced_avg_margin:
            f.write("\noptimized_dbc_margin improves average margin over balanced_table by %.2f dB.\n" % (dbc_avg_margin - balanced_avg_margin))
        else:
            f.write("\noptimized_dbc_margin does not beat balanced_table on average margin; amplitude tapering is not broadly worth hardware testing unless heatmaps show a desired shape.\n")
        if count_positive_margin(dbc_margin_opt, "dbc_gain_margin_db") <= len(dbc_margin_opt) // 2:
            f.write("Most optimized_dbc_margin cases have margin <= 0, so the summary recommendation is to fall back to uniform or a lighter taper for those cases.\n")
        if gain_warnings:
            f.write("\nGain warnings below -6 dB, consider raising floor:\n")
            for row in gain_warnings[:20]:
                f.write("  %.1fm az=%+.0f el=%+.0f mode=%s gain=%.2f dB\n" % (
                    row["distance_m"], row["az_deg"], row["el_deg"], row["mode"], row["metrics"]["target_gain_delta_db"]
                ))
        else:
            f.write("\nNo target-gain warning below -6 dB.\n")

        if direction_failures:
            f.write("\nPeak-direction failures (> %.1f deg offset), inspect heatmaps before hardware testing:\n" % PEAK_DIRECTION_LIMIT_DEG)
            for row in direction_failures[:30]:
                check = row["direction_check"]
                f.write("  %.1fm az=%+.0f mode=%s peak_offset=%.2f deg margin=%.2f dB\n" % (
                    row["distance_m"],
                    row["az_deg"],
                    row["mode"],
                    check["peak_offset_deg"],
                    row["metrics"].get("dbc_gain_margin_db", 0.0),
                ))
        else:
            f.write("\nAll selected heatmap modes keep the peak within %.1f deg of target.\n" % PEAK_DIRECTION_LIMIT_DEG)

        f.write("\nSelected cases:\n")
        for case in PLOT_CASES:
            f.write("  case %.1fm az=%+.0f el=%+.0f\n" % case)
            for mode in MODES:
                row = next(r for r in rows if abs(r["distance_m"] - case[0]) < 1e-9 and abs(r["az_deg"] - case[1]) < 1e-9 and abs(r["el_deg"] - case[2]) < 1e-9 and r["mode"] == mode)
                m = row["metrics"]
                f.write("    %-22s maxSL=%7.2f dBc+=%6.2f loss=%6.2f margin=%6.2f p99=%7.2f meanAmp=%5.2f\n" % (
                    mode,
                    m["max_sidelobe_db"],
                    m.get("dbc_improvement_db", 0.0),
                    m.get("gain_loss_db", 0.0),
                    m.get("dbc_gain_margin_db", 0.0),
                    m["p99_sidelobe_db"],
                    m["mean_amp"],
                ))


def main():
    ensure_out_dir()
    geometry = n60.build_geometry()
    n60.write_geometry_csv(os.path.join(OUT_DIR, "n60_5x12_geometry.csv"), geometry)

    dbc_margin_rows = []
    opt_rows = []
    aggressive_rows = []
    dbc_margin_by_key = {}
    balanced_by_key = {}
    aggressive_by_key = {}
    metrics_rows = []

    print("Building optimized amplitude table...")
    for distance_m in DISTANCES_M:
        for az_deg in AZIMUTHS_DEG:
            for el_deg in ELEVATIONS_DEG:
                case_opt = build_case_matrix(geometry, distance_m, az_deg, el_deg, PROBE_N_OPT)
                starts = candidate_starts(geometry, case_opt)
                dbc_margin, balanced, aggressive, by_floor, candidates = optimize_case_amplitudes(case_opt, starts)
                key = (case_opt["distance_mm"], case_opt["az_deg"], case_opt["el_deg"])
                dbc_margin_by_key[key] = dbc_margin["amplitudes"]
                balanced_by_key[key] = balanced["amplitudes"]
                aggressive_by_key[key] = aggressive["amplitudes"]
                dbc_margin_rows.append({
                    "distance_mm": case_opt["distance_mm"],
                    "distance_m": case_opt["distance_m"],
                    "az_deg": case_opt["az_deg"],
                    "el_deg": case_opt["el_deg"],
                    "amplitudes": dbc_margin["amplitudes"],
                    "success": dbc_margin["success"],
                    "score": dbc_margin["score"],
                    "gain_floor": dbc_margin["gain_floor"],
                })
                opt_rows.append({
                    "distance_mm": case_opt["distance_mm"],
                    "distance_m": case_opt["distance_m"],
                    "az_deg": case_opt["az_deg"],
                    "el_deg": case_opt["el_deg"],
                    "amplitudes": balanced["amplitudes"],
                    "success": balanced["success"],
                    "score": balanced["score"],
                    "gain_floor": balanced["gain_floor"],
                })
                aggressive_rows.append({
                    "distance_mm": case_opt["distance_mm"],
                    "distance_m": case_opt["distance_m"],
                    "az_deg": case_opt["az_deg"],
                    "el_deg": case_opt["el_deg"],
                    "amplitudes": aggressive["amplitudes"],
                    "success": aggressive["success"],
                    "score": aggressive["score"],
                    "gain_floor": aggressive["gain_floor"],
                })
                print(
                    "  opt %.1fm az=%+.0f el=%+.0f dbc_score=%.2f bal_floor=%.2f bal_score=%.2f aggr_floor=%.2f aggr_score=%.2f"
                    % (
                        case_opt["distance_m"],
                        case_opt["az_deg"],
                        case_opt["el_deg"],
                        dbc_margin["score"],
                        balanced["gain_floor"],
                        balanced["score"],
                        aggressive["gain_floor"],
                        aggressive["score"],
                    )
                )

    write_focus_table(os.path.join(OUT_DIR, "n60_5x12_focus_table_dbc_margin.csv"), dbc_margin_rows)
    write_focus_table(os.path.join(OUT_DIR, "n60_5x12_focus_table.csv"), opt_rows)
    write_focus_table(os.path.join(OUT_DIR, "n60_5x12_focus_table_aggressive.csv"), aggressive_rows)

    print("Evaluating modes...")
    for distance_m in DISTANCES_M:
        for az_deg in AZIMUTHS_DEG:
            for el_deg in ELEVATIONS_DEG:
                case = build_case_matrix(geometry, distance_m, az_deg, el_deg, PROBE_N_EVAL)
                uniform_metrics = metrics_for_amplitudes(case, np.ones(n60.CHANNEL_COUNT))
                reference_target = uniform_metrics["target_abs"]
                uniform_dbc = -uniform_metrics["max_sidelobe_db"]
                uniform_p99_dbc = -uniform_metrics["p99_sidelobe_db"]
                for mode in MODES:
                    if mode == n60.MODE_OPTIMIZED_DBC_MARGIN:
                        lookup = dbc_margin_by_key
                    elif mode == n60.MODE_OPTIMIZED_AGGRESSIVE:
                        lookup = aggressive_by_key
                    else:
                        lookup = balanced_by_key
                    amp = amplitudes_for_mode(geometry, case, mode, lookup)
                    metrics = metrics_for_amplitudes(case, amp, reference_target=reference_target)
                    metrics["dbc"] = -metrics["max_sidelobe_db"]
                    metrics["p99_dbc"] = -metrics["p99_sidelobe_db"]
                    metrics["dbc_improvement_db"] = metrics["dbc"] - uniform_dbc
                    metrics["p99_dbc_improvement_db"] = metrics["p99_dbc"] - uniform_p99_dbc
                    metrics["gain_loss_db"] = max(0.0, -metrics["target_gain_delta_db"])
                    metrics["dbc_gain_margin_db"] = metrics["dbc_improvement_db"] - metrics["gain_loss_db"]
                    metrics["p99_dbc_gain_margin_db"] = metrics["p99_dbc_improvement_db"] - metrics["gain_loss_db"]
                    direction_check = direction_check_for_metrics(case, metrics)
                    metrics_rows.append({
                        "distance_m": case["distance_m"],
                        "az_deg": case["az_deg"],
                        "el_deg": case["el_deg"],
                        "mode": mode,
                        "metrics": metrics,
                        "direction_check": direction_check,
                        "case": case,
                    })

    write_metrics(os.path.join(OUT_DIR, "n60_5x12_metrics_horizontal.csv"), metrics_rows)
    write_peak_direction_check(os.path.join(OUT_DIR, "n60_5x12_peak_direction_check.csv"), metrics_rows)
    plot_geometry(os.path.join(OUT_DIR, "n60_5x12_geometry.png"), geometry)
    plot_unit_gains(os.path.join(OUT_DIR, "n60_5x12_unit_gains.png"))
    plot_patterns(os.path.join(OUT_DIR, "n60_5x12_patterns_horizontal.png"), metrics_rows)
    plot_amplitudes(os.path.join(OUT_DIR, "n60_5x12_optimized_amplitudes_dbc_margin.png"), geometry, dbc_margin_rows, "dBc-margin 60-channel optimized amplitudes")
    plot_amplitudes(os.path.join(OUT_DIR, "n60_5x12_optimized_amplitudes.png"), geometry, opt_rows, "Balanced 60-channel optimized amplitudes")
    plot_amplitudes(os.path.join(OUT_DIR, "n60_5x12_optimized_amplitudes_aggressive.png"), geometry, aggressive_rows, "Aggressive 60-channel optimized amplitudes")
    write_summary(os.path.join(OUT_DIR, "n60_5x12_summary_horizontal.txt"), metrics_rows)

    print("Done. Outputs written under %s" % OUT_DIR)


if __name__ == "__main__":
    main()
