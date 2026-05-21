# Agent Development Guide

本文档面向后续接手 UltraAudio 的开发 agent。目标是减少重复摸索，明确下一步开发边界和优先级。

## 项目边界

UltraAudio 分为三层：

- 阵列算法层：`analysis/` 和部分 `upper/*_beam_params.py`。
- 上位机层：`upper/`。
- FPGA RTL 层：`verilog/`。

当前阵列算法层基本结束。后续主要工作是：

1. 整合上位机，使它能清晰支持 N32 和 5x12 两套目标阵列。
2. 新增 5x12/N60 对应 RTL，不和 N32 混成同一份动态切换 RTL。
3. 系统分析解调结果中二次、三次谐波幅度过大的来源。

## 先读文件

每次接手前先读：

- `README.md`
- `UART_PROTOCOL.md`
- `docs/HARMONIC_ANALYSIS.md`
- `WORK_SUMMARY_N60_5X12.md`
- `upper/n32_beam_params.py`
- `analysis/n60_5x12_beam_params.py`
- `verilog/top_ultrasound_array.sv`
- `verilog/uart_protocol_parser.sv`
- `verilog/pwm32_generator.sv`
- `verilog/audio_debug_processor.sv`

如果任务涉及仿真，再读：

- `run_sim.ps1`
- `verilog/tb_uart_protocol_parser.sv`
- `verilog/tb_pwm32_generator.sv`
- `verilog/tb_audio_debug_processor.sv`
- `analysis/test_n60_5x12_beam_params.py`

## 当前事实

N32：

- 当前 RTL 主链路以 N32 为中心；上位机已支持 N32/N60 profile 切换。
- `0x01` UART 帧传输 32 路幅度和 32 路相位。
- `0x02` UART 帧传输调试配置，包括音源选择、增益、限幅、调制深度、DDS 参数、最大 duty 和 output mask。
- `0x04` UART 帧传输实时 modulation/debug v1 参数，默认 MAM1、`mod_index_q15=19661`。
- 当前 PWM 输出宽度为 32。

5x12/N60：

- 算法层已经有 60 路几何、幅度模式和相位计算。
- 通道顺序固定为 `channel = unit_id * 12 + element_id`。
- 子阵角度固定为 `[-45, -22.5, 0, 22.5, 45]°`。
- 当前水平优化只考虑 `el=0°`，水平 `±30°`。
- 推荐优先使用 `optimized_dbc_margin` 表，即 `analysis_outputs/n60_5x12_focus_table_dbc_margin.csv`。
- 上位机已支持 N60 计算和 `0x03` 幅相帧。
- 还没有 60 路 RTL 顶层输出。

## 下一步开发建议

### 1. 上位机整合

第一版上位机标签页和控制模型已经完成。后续如继续改 UI，应保持 `upper/protocol.py`、`upper/array_profiles.py` 和 `upper/Phased_Array_Control.py` 的分层，不要把新协议字段重新写回 GUI 事件处理里。

需要明确：

- 选择 N32 还是 5x12 的入口已在 `Array` 标签页。
- 两种阵列各自的距离、角度、幅度模式和通道数限制由 `upper/array_profiles.py` 管理。
- N32 继续使用现有 `upper/n32_beam_params.py`。
- 5x12 可以从 `analysis/n60_5x12_beam_params.py` 抽出可供上位机复用的计算/打包模块，或复制到 `upper/` 后保持接口一致。
- 音频来源和调试参数应保持独立于阵列幅相参数，继续沿用 `0x02` 调试帧的思想。

不要把 GUI 层写死为只有 N32，也不要让 5x12 直接依赖分析脚本中的绘图/评估逻辑。

建议形成的接口：

```text
calculate_beam_params(distance_mm, az_deg, el_deg, mode) -> amplitudes, phases, metadata
build_beam_packet(amplitudes, phases, profile) -> bytes
build_debug_packet(...) -> bytes
```

如果扩展 5x12 UART 协议，必须同步：

- `UART_PROTOCOL.md`
- 上位机 packet builder
- RTL parser
- 对应 testbench

### 2. 5x12/N60 RTL

建议为 5x12 单独建立 RTL 文件，不要直接扩大当前 N32 顶层后让两者混在一起。

建议新增或复制后改造：

- `verilog/top_ultrasound_array_n60.sv`
- `verilog/uart_protocol_parser_n60.sv`
- `verilog/pwm60_generator.sv`
- `verilog/tb_uart_protocol_parser_n60.sv`
- `verilog/tb_pwm60_generator.sv`

需要确认的硬件问题：

- 60 路输出如何接到 FPGA 管脚。
- 是否仍使用 100 MHz PWM 时钟和 40 kHz 载波，即 2500 tick 周期。
- `phase` 是否仍为 `0..2499` tick。
- `amplitude` 是否仍为 `0..255`。
- 5x12 是否需要保留 `0x02` output mask 的低 60 位。
- 是否需要新的 `0x03` 60 路幅相帧，还是把 `0x01` 根据 profile 扩展。

协议选择建议：

- 保留 `0x01` 作为 N32 幅相帧，避免破坏已通过的链路。
- 为 N60 新增独立命令，例如 `0x03`，包含 60 路 amplitude 和 60 路 phase。
- 继续保留 `0x02` 作为通用调试参数帧，`array_profile=1` 表示 5x12。

N60 幅相帧建议结构：

```text
AA BB 03 amp[0..59] phase0_l phase0_h ... phase59_l phase59_h checksum 0D 0A
```

总长度：

```text
2 header + 1 cmd + 60 amp + 120 phase + 1 checksum + 2 tail = 186 bytes
```

checksum 规则建议和现有协议一致：从 command 到 payload 求 8 位和，不包含 header、checksum 和 tail。

### 3. 谐波问题分析

当前现象：测试时发现解调结果存在幅度较大的二次、三次谐波。不要在没有实验隔离的情况下直接归因到阵列算法。

建议按从数字链路到物理链路的顺序排查。

第一阶段：纯数字仿真

- 使用 `DDS/test` 音源，关闭 I2S。
- 固定单频音频，例如 1 kHz。
- 分别测试 `use_rom_mapping=0/1`、`center_align=0/1`、不同 `audio_depth_q8`、不同 `max_duty`。
- 在 testbench 中导出单路或多路 PWM 的周期统计，重建等效包络后做 FFT。
- 判断二次、三次谐波是否已在 RTL 数字调制链路中出现。

第二阶段：FPGA 输出但不接换能器

- 用示波器测 PWM 输出 duty、频率、相位和边沿。
- 对单路输出低通/包络后观察音频频谱。
- 检查不同 `max_duty` 和调制深度下谐波是否随占空比非线性增加。

第三阶段：单换能器

- 只打开一个通道，固定距离测试。
- 扫描 `test_amp`、`audio_depth_q8`、`max_duty`。
- 如果单通道已有强二次/三次谐波，优先排查驱动、换能器、解调链路和调制方式。

第四阶段：阵列

- 从少量通道逐步增加到 N32 或 N60。
- 比较 full amplitude、加权 amplitude 和不同聚焦点。
- 判断谐波是否与空间焦点、旁瓣、反射或多路径有关。

第五阶段：真实音频输入

- 打开 I2S。
- 先输入单频正弦，再输入双音，再输入真实音频。
- 检查上位机/音频源是否已经含有谐波或削波。

优先可疑点：

- `audio_debug_processor.sv` 中限幅、偏置和调制深度组合造成削波。
- `pwm32_generator.sv` 中 `sqrt_mapping_rom` 和 duty 限制引入非线性。
- PWM duty 上限过大或过小导致调制曲线非线性。
- 换能器/驱动在当前声压下进入非线性区。
- 解调/采集流程本身没有足够隔离载波、二次包络项或环境反射。

详细理论、代码可疑点和实验矩阵见 `docs/HARMONIC_ANALYSIS.md`。建议新增的分析产物：

- `docs/HARMONIC_ANALYSIS.md`：记录每次谐波实验条件、频谱图和结论。
- `analysis/harmonic_probe.py`：对采样波形做 FFT、THD、二次/三次谐波比值统计。
- `verilog/tb_pwm_harmonic_probe.sv`：生成可重复 PWM 波形输出，用于数字链路 FFT。

## 验证要求

修改 Python 算法或上位机打包逻辑后至少运行：

```powershell
python -m py_compile upper\Phased_Array_Control.py upper\n32_beam_params.py analysis\n60_5x12_beam_params.py
python -m unittest analysis.test_n60_5x12_beam_params
```

修改 RTL parser 后至少运行：

```powershell
.\run_sim.ps1 -tb verilog\tb_uart_protocol_parser.sv -out icarus\tb_uart_protocol_parser.vvp -vcd tb_uart_protocol_parser.vcd
```

修改 PWM 后至少运行：

```powershell
.\run_sim.ps1 -tb verilog\tb_pwm32_generator.sv -out icarus\tb_pwm32_generator.vvp -vcd tb_pwm32_generator.vcd
```

新增 N60 RTL 后必须补齐 N60 parser 和 PWM testbench，不要只改顶层。

## 工作区注意事项

当前工作区可能包含未提交改动和新生成输出。不要随意格式化全仓库，不要回滚无关文件。

文档和代码中涉及中文时使用 UTF-8。PowerShell 查看中文文件时建议显式指定：

```powershell
Get-Content -Encoding UTF8 path\to\file.md
```
