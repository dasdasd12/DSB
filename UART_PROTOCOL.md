# UART Beam Control Protocol

UART format: `115200` baud, 8 data bits, no parity, 1 stop bit.

This protocol is the current host-to-FPGA control link used by
`upper/Phased_Array_Control.py` and `verilog/uart_protocol_parser.sv`.

Four commands are supported:

```text
0x01  N32 beam amplitude/phase frame
0x02  debug modulation/control frame
0x03  N60 / 5x12 beam amplitude/phase frame
0x04  modulation/debug v1 frame
```

## N32 Beam Frame

```text
AA BB 01 amp[0] ... amp[31] phase0_l phase0_h ... phase31_l phase31_h checksum 0D 0A
```

Total length is 102 bytes:

```text
2 byte  header       AA BB
1 byte  command      01
32 byte amplitude    uint8, channel E00..E31
64 byte phase        uint16 little-endian, channel E00..E31
1 byte  checksum     8-bit sum from command through phase payload
2 byte  tail         0D 0A
```

## Channel Order

The host uses `analysis/n32_array_coordinates.csv` order directly:

```text
E00 -> transducer_io[0]
E01 -> transducer_io[1]
...
E31 -> transducer_io[31]
```

There is no 5x5 snake mapping in the N=32 path.

## Field Encoding

`amplitude[i]` is an unsigned 8-bit value:

```text
0   = off
255 = full channel weight
```

`phase[i]` is a little-endian unsigned 16-bit value, but the RTL parser keeps
only the low 12 bits:

```text
phase[i] = {phase_h[3:0], phase_l}
valid host range for the current 40 kHz PWM carrier: 0..2499 ticks
```

With the current 100 MHz PWM clock:

```text
2500 ticks = 25 us = one 40 kHz carrier period
```

## Checksum

The checksum is the low 8 bits of the byte sum starting at the command byte:

```text
checksum = sum(packet[2 : 2 + 1 + 32 + 64]) & 0xFF
```

It does not include `AA BB`, the checksum byte itself, or `0D 0A`.

## Debug Parameter Frame

The debug frame is intentionally separate from the N32 beam frame so old
beam-control packets remain compatible:

```text
AA BB 02 version array_profile flags gain_q8_l gain_q8_h limiter_mode
limiter_threshold_l limiter_threshold_h audio_depth_q8_l audio_depth_q8_h
dc_offset_l dc_offset_h test_ftw[0..3] test_amp_l test_amp_h
max_duty_l max_duty_h output_mask[0..7] checksum 0D 0A
```

Total length is 34 bytes:

```text
2 byte  header       AA BB
1 byte  command      02
28 byte payload      fields below, little-endian for multi-byte values
1 byte  checksum     8-bit sum from command through payload
2 byte  tail         0D 0A
```

Payload fields:

```text
version             uint8, default 1
array_profile       uint8, 0=N32, 1=5x12 reserved
flags               uint8, see bit map below
gain_q8             uint16, 256 = 1.0x I2S gain
limiter_mode        uint8, 0=none, 1=hard, 2=soft
limiter_threshold   int16
audio_depth_q8      uint16, 256 = 1.0x final modulation depth
dc_offset           int16
test_ftw            uint32, DDS frequency tuning word
test_amp            uint16, DDS/test sine amplitude
max_duty            uint16, RTL keeps low 12 bits and caps at 1250
output_mask         uint64, N32 uses low 32 bits; 5x12 can use low 60 bits later
```

Flag bits:

```text
bit0  output enable
bit1  source select: 0=DDS/test, 1=I2S
bit2  PWM center alignment enable
bit3  ROM mapping enable; 0 emits a fixed-duty debug carrier
bit4  soft-limiter flag
bit5..7 reserved
```

Reset defaults:

```text
version=1
array_profile=0
flags=0x09
gain_q8=256
limiter_mode=0
limiter_threshold=32767
audio_depth_q8=256
dc_offset=0
test_ftw=42950
test_amp=8192
max_duty=1250
output_mask=0x00000000FFFFFFFF
```

`test_ftw` uses the 100 MHz DDS clock:

```text
test_ftw = round(test_frequency_hz * 2^32 / 100000000)
```

## Host Parameter Limits

The N=32 host UI clamps or limits runtime parameters before packet generation:

```text
focus distance: 100..4999 mm
combined steering angle: <= 15 degrees
carrier frequency: 40 kHz
sound speed: 343 m/s
```

The FPGA parser updates the 32-channel shadow values only after the checksum
and `0D 0A` tail are valid.

## N60 / 5x12 Beam Frame

The N60 frame uses the same field encoding and checksum rule as the N32 frame,
but carries 60 amplitudes and 60 phases:

```text
AA BB 03 amp[0] ... amp[59] phase0_l phase0_h ... phase59_l phase59_h checksum 0D 0A
```

Total length is 186 bytes:

```text
2 byte  header       AA BB
1 byte  command      03
60 byte amplitude    uint8, channel U0E0..U4E11
120 byte phase       uint16 little-endian, channel U0E0..U4E11
1 byte  checksum     8-bit sum from command through phase payload
2 byte  tail         0D 0A
```

N60 channel order is fixed:

```text
channel = unit_id * 12 + element_id
unit_id:    0..4, unit angles [-45, -22.5, 0, 22.5, 45] deg
element_id: 0..11 within each N12 unit
```

`phase[i]` remains `0..2499` ticks for the 40 kHz carrier.

## Modulation / Debug V1 Frame

The `0x04` frame controls the new realtime modulation path. It does not replace
the legacy `0x02` frame; `0x02` remains accepted for compatibility.

```text
AA BB 04 payload[36] checksum 0D 0A
```

Total length is 42 bytes:

```text
2 byte  header       AA BB
1 byte  command      04
36 byte payload      fields below, little-endian for multi-byte values
1 byte  checksum     8-bit sum from command through payload
2 byte  tail         0D 0A
```

Payload fields:

```text
0      version             uint8, fixed 1
1      array_profile       uint8, 0=N32, 1=N60
2..3   flags               uint16 little-endian
4      source_select       uint8, 0=DDS/test, 1=I2S
5      modulation_mode     uint8, 0=legacy_sram, 1=dsb_am, 2=ssb_usb, 3=ssb_lsb, 4=mam1
6      sideband            uint8, 0=usb, 1=lsb, ignored except SSB
7      debug_probe_select  uint8
8..9   input_gain_q8       uint16, 256=1.0x
10     limiter_mode        uint8, 0=none, 1=hard, 2=soft
11..12 limiter_threshold   int16
13..14 dc_offset           int16
15..16 mod_index_q15       uint16, default 19661 for 0.6
17..18 envelope_scale_q8   uint16, 256=1.0x
19..22 test_ftw            uint32
23..24 test_amp            uint16
25..26 max_duty            uint16, RTL caps at 1250
27..34 output_mask         uint64
35     reserved            uint8, send 0
```

V1 flag bits:

```text
bit0  output enable
bit1  PWM center alignment enable
bit2  safe clamp enable
bit3  fixed-duty debug bypass
bit4  mark-debug strobe enable
bit5..15 reserved
```

Reset defaults for the v1 path:

```text
version=1
array_profile=0
flags=0x0005
source_select=0
modulation_mode=4
sideband=0
debug_probe_select=0
input_gain_q8=256
limiter_mode=0
limiter_threshold=32767
dc_offset=0
mod_index_q15=19661
envelope_scale_q8=256
test_ftw=42950
test_amp=8192
max_duty=1250
output_mask=0x00000000FFFFFFFF
```

The current N32 top consumes `0x04`. `0x03` is implemented on the host side and
documented for the N60 RTL path.
