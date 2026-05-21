from dataclasses import dataclass

import n32_beam_params as n32
import n60_beam_params as n60
import protocol


PROFILE_N32 = "N32"
PROFILE_N60 = "N60 5x12"


@dataclass(frozen=True)
class ArrayProfile:
    name: str
    profile_id: int
    channel_count: int
    min_distance_mm: int
    max_distance_mm: int
    max_steer_deg: float
    amplitude_modes: tuple
    default_mode: str


PROFILES = {
    PROFILE_N32: ArrayProfile(
        name=PROFILE_N32,
        profile_id=protocol.ARRAY_PROFILE_N32,
        channel_count=n32.CHANNEL_COUNT,
        min_distance_mm=n32.MIN_DISTANCE_MM,
        max_distance_mm=n32.MAX_DISTANCE_MM,
        max_steer_deg=n32.MAX_STEER_DEG,
        amplitude_modes=n32.AMPLITUDE_MODES,
        default_mode=n32.MODE_FITTED,
    ),
    PROFILE_N60: ArrayProfile(
        name=PROFILE_N60,
        profile_id=protocol.ARRAY_PROFILE_N60,
        channel_count=n60.CHANNEL_COUNT,
        min_distance_mm=n60.MIN_DISTANCE_MM,
        max_distance_mm=n60.MAX_DISTANCE_MM,
        max_steer_deg=n60.MAX_STEER_DEG,
        amplitude_modes=n60.AMPLITUDE_MODES,
        default_mode=n60.MODE_OPTIMIZED_DBC_MARGIN,
    ),
}


def calculate(profile_name, distance_mm, az_deg, el_deg, amp_mode):
    if profile_name == PROFILE_N32:
        return n32.calculate_beam_params(distance_mm=distance_mm, az_deg=az_deg, el_deg=el_deg, amp_mode=amp_mode)
    if profile_name == PROFILE_N60:
        return n60.calculate_focus_params(distance_mm=distance_mm, az_deg=az_deg, el_deg=el_deg, mode=amp_mode)
    raise ValueError("unknown array profile: %s" % profile_name)


def build_beam_packet(profile_name, amplitudes, phases):
    if profile_name == PROFILE_N32:
        return protocol.build_n32_beam_packet(amplitudes, phases)
    if profile_name == PROFILE_N60:
        return protocol.build_n60_beam_packet(amplitudes, phases)
    raise ValueError("unknown array profile: %s" % profile_name)


def profile_for_name(profile_name):
    return PROFILES[profile_name]
