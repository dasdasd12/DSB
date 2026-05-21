import os
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import array_profiles
import modulation_reference
import protocol


class ProtocolProfilesTest(unittest.TestCase):
    def test_n60_packet_format_and_checksum(self):
        amps = list(range(60))
        phases = [(i * 41) % 2500 for i in range(60)]
        packet = protocol.build_n60_beam_packet(amps, phases)
        self.assertEqual(len(packet), 186)
        self.assertEqual(packet[0:3], b"\xAA\xBB\x03")
        self.assertEqual(packet[-2:], b"\x0D\x0A")
        self.assertEqual(packet[-3], sum(packet[2:-3]) & 0xFF)

    def test_mod_debug_v1_packet_fields(self):
        packet = protocol.build_mod_debug_v1_packet(
            array_profile=protocol.ARRAY_PROFILE_N60,
            flags=0x0017,
            source_select=protocol.SOURCE_I2S,
            modulation_mode=protocol.MOD_MAM1,
            sideband=1,
            debug_probe_select=2,
            input_gain_q8=512,
            limiter_mode=2,
            limiter_threshold=1234,
            dc_offset=-55,
            mod_index_q15=19661,
            envelope_scale_q8=384,
            test_ftw=0x01020304,
            test_amp=8192,
            max_duty=1000,
            output_mask=0x000FFFFFFFFFFFFF,
        )
        self.assertEqual(len(packet), 42)
        self.assertEqual(packet[0:3], b"\xAA\xBB\x04")
        self.assertEqual(packet[-3], sum(packet[2:-3]) & 0xFF)
        payload = packet[3:-3]
        self.assertEqual(len(payload), 36)
        self.assertEqual(payload[0], 1)
        self.assertEqual(payload[1], protocol.ARRAY_PROFILE_N60)
        self.assertEqual(struct.unpack("<H", payload[2:4])[0], 0x0017)
        self.assertEqual(payload[4], protocol.SOURCE_I2S)
        self.assertEqual(payload[5], protocol.MOD_MAM1)
        self.assertEqual(payload[6], 1)
        self.assertEqual(payload[7], 2)
        self.assertEqual(struct.unpack("<H", payload[8:10])[0], 512)
        self.assertEqual(payload[10], 2)
        self.assertEqual(struct.unpack("<h", payload[11:13])[0], 1234)
        self.assertEqual(struct.unpack("<h", payload[13:15])[0], -55)
        self.assertEqual(struct.unpack("<H", payload[15:17])[0], 19661)
        self.assertEqual(struct.unpack("<H", payload[17:19])[0], 384)
        self.assertEqual(struct.unpack("<I", payload[19:23])[0], 0x01020304)
        self.assertEqual(struct.unpack("<H", payload[23:25])[0], 8192)
        self.assertEqual(struct.unpack("<H", payload[25:27])[0], 1000)
        self.assertEqual(struct.unpack("<Q", payload[27:35])[0], 0x000FFFFFFFFFFFFF)

    def test_n60_profile_defaults_and_ranges(self):
        profile = array_profiles.profile_for_name(array_profiles.PROFILE_N60)
        self.assertEqual(profile.channel_count, 60)
        self.assertEqual(profile.profile_id, protocol.ARRAY_PROFILE_N60)
        self.assertEqual(profile.default_mode, "optimized_dbc_margin")
        result = array_profiles.calculate(profile.name, 2000, 30, 0, profile.default_mode)
        self.assertEqual(len(result.amplitudes), 60)
        self.assertEqual(len(result.phases), 60)
        self.assertTrue(all(0 <= amp <= 255 for amp in result.amplitudes))
        self.assertTrue(all(0 <= phase < 2500 for phase in result.phases))

    def test_modulation_reference_ranges(self):
        samples = [0.0, 0.25, 0.5, -0.25, -0.5, 0.0] * 32
        for mode in (
            modulation_reference.MODE_DSB_AM,
            modulation_reference.MODE_SSB_USB,
            modulation_reference.MODE_SSB_LSB,
            modulation_reference.MODE_MAM1,
            modulation_reference.MODE_LEGACY_SRAM,
        ):
            env, phase = modulation_reference.polar_reference(samples, mode=mode, mod_index=0.6)
            self.assertEqual(len(env), len(samples))
            self.assertEqual(len(phase), len(samples))
            self.assertTrue(all(0 <= value <= 4095 for value in env))
            self.assertTrue(all(0 <= value < 2500 for value in phase))


if __name__ == "__main__":
    unittest.main()
