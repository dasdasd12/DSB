import struct


HEADER = b"\xAA\xBB"
TAIL = b"\x0D\x0A"

CMD_N32_BEAM = 0x01
CMD_LEGACY_DEBUG = 0x02
CMD_N60_BEAM = 0x03
CMD_MOD_DEBUG_V1 = 0x04

ARRAY_PROFILE_N32 = 0
ARRAY_PROFILE_N60 = 1

MOD_LEGACY_SRAM = 0
MOD_DSB_AM = 1
MOD_SSB_USB = 2
MOD_SSB_LSB = 3
MOD_MAM1 = 4

SOURCE_DDS = 0
SOURCE_I2S = 1


def clamp(value, low, high):
    return max(low, min(high, value))


def checksum(command, payload):
    return (int(command) + sum(payload)) & 0xFF


def build_frame(command, payload):
    body = bytes([command & 0xFF]) + bytes(payload)
    return HEADER + body + bytes([sum(body) & 0xFF]) + TAIL


def format_packet_hex(packet):
    return " ".join("{:02X}".format(b) for b in packet)


def ftw_from_hz(freq_hz, clock_hz=100_000_000.0):
    return int(round(float(freq_hz) * (2**32) / float(clock_hz))) & 0xFFFFFFFF


def build_beam_packet(command, channel_count, amplitudes, phases):
    if len(amplitudes) != channel_count or len(phases) != channel_count:
        raise ValueError("beam packet requires %d amplitudes and phases" % channel_count)

    payload = bytearray()
    for amp in amplitudes:
        payload.append(int(clamp(amp, 0, 255)) & 0xFF)

    for phase in phases:
        ph = int(phase)
        if ph < 0 or ph > 0x0FFF:
            raise ValueError("phase must fit in the parser's 12-bit field")
        payload.extend(struct.pack("<H", ph))

    return build_frame(command, payload)


def build_n32_beam_packet(amplitudes, phases):
    packet = build_beam_packet(CMD_N32_BEAM, 32, amplitudes, phases)
    if len(packet) != 102:
        raise AssertionError("N32 UART packet length must be 102 bytes")
    return packet


def build_n60_beam_packet(amplitudes, phases):
    packet = build_beam_packet(CMD_N60_BEAM, 60, amplitudes, phases)
    if len(packet) != 186:
        raise AssertionError("N60 UART packet length must be 186 bytes")
    return packet


def build_legacy_debug_packet(
    version=1,
    array_profile=ARRAY_PROFILE_N32,
    flags=0x09,
    gain_q8=256,
    limiter_mode=0,
    limiter_threshold=32767,
    audio_depth_q8=256,
    dc_offset=0,
    test_ftw=42950,
    test_amp=8192,
    max_duty=1250,
    output_mask=0x00000000FFFFFFFF,
):
    payload = bytearray()
    payload.append(int(clamp(version, 0, 255)) & 0xFF)
    payload.append(int(clamp(array_profile, 0, 255)) & 0xFF)
    payload.append(int(clamp(flags, 0, 255)) & 0xFF)
    payload.extend(struct.pack("<H", int(clamp(gain_q8, 0, 65535))))
    payload.append(int(clamp(limiter_mode, 0, 255)) & 0xFF)
    payload.extend(struct.pack("<h", int(clamp(limiter_threshold, -32768, 32767))))
    payload.extend(struct.pack("<H", int(clamp(audio_depth_q8, 0, 65535))))
    payload.extend(struct.pack("<h", int(clamp(dc_offset, -32768, 32767))))
    payload.extend(struct.pack("<I", int(clamp(test_ftw, 0, 0xFFFFFFFF))))
    payload.extend(struct.pack("<H", int(clamp(test_amp, 0, 65535))))
    payload.extend(struct.pack("<H", int(clamp(max_duty, 0, 4095))))
    payload.extend(struct.pack("<Q", int(clamp(output_mask, 0, 0xFFFFFFFFFFFFFFFF))))
    if len(payload) != 28:
        raise AssertionError("legacy debug payload length mismatch")
    packet = build_frame(CMD_LEGACY_DEBUG, payload)
    if len(packet) != 34:
        raise AssertionError("legacy debug UART packet length must be 34 bytes")
    return packet


def build_mod_debug_v1_packet(
    array_profile=ARRAY_PROFILE_N32,
    flags=0x0005,
    source_select=SOURCE_DDS,
    modulation_mode=MOD_MAM1,
    sideband=0,
    debug_probe_select=0,
    input_gain_q8=256,
    limiter_mode=0,
    limiter_threshold=32767,
    dc_offset=0,
    mod_index_q15=19661,
    envelope_scale_q8=256,
    test_ftw=42950,
    test_amp=8192,
    max_duty=1250,
    output_mask=0x00000000FFFFFFFF,
    reserved=0,
):
    payload = bytearray()
    payload.append(1)
    payload.append(int(clamp(array_profile, 0, 255)) & 0xFF)
    payload.extend(struct.pack("<H", int(clamp(flags, 0, 0xFFFF))))
    payload.append(int(clamp(source_select, 0, 255)) & 0xFF)
    payload.append(int(clamp(modulation_mode, 0, 255)) & 0xFF)
    payload.append(int(clamp(sideband, 0, 255)) & 0xFF)
    payload.append(int(clamp(debug_probe_select, 0, 255)) & 0xFF)
    payload.extend(struct.pack("<H", int(clamp(input_gain_q8, 0, 65535))))
    payload.append(int(clamp(limiter_mode, 0, 255)) & 0xFF)
    payload.extend(struct.pack("<h", int(clamp(limiter_threshold, -32768, 32767))))
    payload.extend(struct.pack("<h", int(clamp(dc_offset, -32768, 32767))))
    payload.extend(struct.pack("<H", int(clamp(mod_index_q15, 0, 65535))))
    payload.extend(struct.pack("<H", int(clamp(envelope_scale_q8, 0, 65535))))
    payload.extend(struct.pack("<I", int(clamp(test_ftw, 0, 0xFFFFFFFF))))
    payload.extend(struct.pack("<H", int(clamp(test_amp, 0, 65535))))
    payload.extend(struct.pack("<H", int(clamp(max_duty, 0, 4095))))
    payload.extend(struct.pack("<Q", int(clamp(output_mask, 0, 0xFFFFFFFFFFFFFFFF))))
    payload.append(int(clamp(reserved, 0, 255)) & 0xFF)
    if len(payload) != 36:
        raise AssertionError("mod/debug v1 payload length mismatch")
    packet = build_frame(CMD_MOD_DEBUG_V1, payload)
    if len(packet) != 42:
        raise AssertionError("mod/debug v1 UART packet length must be 42 bytes")
    return packet
