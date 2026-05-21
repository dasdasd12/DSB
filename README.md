# UltraAudio

UltraAudio 是一个超声换能器音箱小项目。系统使用超声相控阵把调制后的超声载波定向发射到目标区域，目标区域通过空气非线性或接收端解调获得可听音频。

项目当前分为三层：

- 阵列算法层：计算每个换能器通道的幅度、相位和通道顺序。
- 上位机层：调整聚焦位置、指向角、音频来源和调试参数，并通过 UART 发送给 FPGA。
- FPGA RTL 层：接收上位机参数，产生 40 kHz 超声 PWM/调制输出，驱动超声换能器。

## 当前阵列方案

项目保留两套阵列算法：

- N32：32 路阵列，当前已有上位机和 RTL 调试链路。
- N=5x12 / N60：5 个 12 路子阵组成的 60 路阵列，当前算法层基本搭建完成。

N32 和 5x12 是两种独立硬件/RTL 路线，不计划在同一份 RTL 中同时动态支持两种阵列。后续开发应按目标阵列分别维护顶层、PWM 输出宽度、UART 幅相帧长度、通道映射和约束文件。

## 目录结构

```text
analysis/          阵列算法、仿真、优化和评估脚本
analysis_outputs/  算法输出结果、优化表、图像和评估摘要
upper/             Python/PyQt 上位机和 UART 打包逻辑
verilog/           FPGA RTL 和 testbench
docs/              器件资料、历史说明和专题文档
icarus/            Icarus Verilog 仿真输出
```

关键文件：

- `upper/Phased_Array_Control.py`：N32/N60 上位机 GUI，包含阵列、调制和 debug 标签页。
- `upper/protocol.py`：UART `0x01/0x02/0x03/0x04` 打包逻辑。
- `upper/array_profiles.py`：N32/N60 profile 统一入口。
- `upper/modulation_reference.py`：SSB-AM/MAM1 Python 参考实现。
- `upper/n32_beam_params.py`：N32 幅相计算和 UART 打包。
- `upper/n60_beam_params.py`：5x12/N60 上位机幅相计算。
- `analysis/n60_5x12_beam_params.py`：5x12/N60 幅相计算。
- `analysis/evaluate_n60_5x12.py`：5x12/N60 水平指向评估和优化表生成。
- `verilog/top_ultrasound_array.sv`：当前 N32 RTL 顶层。
- `verilog/uart_protocol_parser.sv`：UART 协议解析。
- `verilog/pwm32_generator.sv`：32 路 PWM 生成。
- `verilog/audio_input_processor.sv`、`verilog/audio_iq_modulator.sv`、`verilog/hilbert_fir.sv`、`verilog/cordic_polar.sv`：实时 SSB/MAM1 调制链路。
- `verilog/audio_debug_processor.sv`：音频来源选择、增益、限幅、调制深度和偏置处理。
- `UART_PROTOCOL.md`：当前 UART 协议说明。

## 当前状态

阵列算法层基本完成：

- N32 参数生成和 N32 幅相 UART 打包已存在。
- 5x12/N60 算法已完成水平 `±30°` 指向优化评估。
- 当前 5x12 推荐优先使用 `analysis_outputs/n60_5x12_focus_table_dbc_margin.csv`。

上位机层已完成第一版整合：

- GUI 已改为标签页结构，支持 N32/N60 profile 切换。
- N60/5x12 使用 `0x03` 幅相帧，通道顺序为 `channel = unit_id * 12 + element_id`。
- 新增 `0x04` modulation/debug v1 帧，支持 Legacy SRAM、DSB-AM、SSB USB、SSB LSB、MAM1。
- 默认新增调制模式为 MAM1，`mod_index=0.6`。

FPGA RTL 层当前状态：

- 当前顶层仍是 N32 路线，输出为 32 路 `transducer_io`。
- N32 顶层已接入 `0x04` 实时调制链路，包括 audio input、Hilbert FIR、I/Q modulator、polar conversion 和 PWM global phase/duty。
- 仍需要为 N60/5x12 单独建立 RTL 顶层、60 路参数解析、60 路 PWM 输出和对应 testbench。
- 不建议把 N32 和 N60 强行塞进同一个动态可切换顶层，除非硬件目标确实需要共板兼容。

## 已知重点问题

测试时发现解调结果存在幅度较大的二次、三次谐波。该问题尚未完成归因，需要作为下一阶段重点分析任务。

当前可能来源包括：

- 调制链路非线性：PWM duty 映射、平方根/ROM 映射、限幅、偏置或调制深度设置导致失真。
- 超声传播和空气自解调非线性：解调音频本身可能包含较强高次项。
- 换能器和驱动非线性：功放、UCC 驱动、换能器带宽或机械响应引入谐波。
- 采集/解调链路问题：麦克风、ADC、滤波、包络检波或 FFT 流程引入额外谐波。
- 阵列空间效应：旁瓣、近场焦点偏移、多路径反射导致测得的解调波形畸变。

后续排查应先用 FPGA 的 DDS/test 音源和可控调制参数复现实验，再逐步打开 I2S、阵列聚焦、实际换能器和真实音频输入。

## 常用命令

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

运行 N60 单元测试：

```powershell
python -m unittest analysis.test_n60_5x12_beam_params
```

重新生成 N60 水平评估输出：

```powershell
python analysis\evaluate_n60_5x12.py
```

运行默认 RTL 仿真：

```powershell
.\run_sim.ps1
```

指定 testbench：

```powershell
.\run_sim.ps1 -tb verilog\tb_pwm32_generator.sv -out icarus\tb_pwm32_generator.vvp -vcd tb_pwm32_generator.vcd
```

## 开发注意事项

- 新文档和 Python 文件统一使用 UTF-8。
- 修改 UART 协议时必须同步 `UART_PROTOCOL.md`、上位机打包逻辑、RTL parser 和 testbench。
- 修改通道顺序时必须同步算法输出、上位机显示、RTL 输出位序和硬件接线说明。
- 当前工作区包含未提交改动，继续开发前应先确认这些改动是否为当前基线。
