# 超声阵列调试与 5x12 水平指向优化总结

日期：2026-05-21

## 1. 工作范围

本轮工作分为两部分：

1. N32 调试参数化：减少排查谐波和“炸麦”问题时的 Vivado 综合/烧写次数。
2. 5x12 / N60 阵列算法试验：只做算法和仿真输出，不接上位机、不改 RTL、不改 UART。

当前重点已经从 N32 板转到 5x12 阵列。N60 部分以水平 `±30°` 指向优化为主，不再考虑垂直 `±15°` 偏转。

## 2. N32 参数化改动

已新增 UART 调试参数控制路径，保留旧 `0x01` 幅相包兼容性。

新增 `0x02` 调试配置帧，覆盖：

- 输出总使能
- 音源选择：DDS/test 或 I2S
- PWM 中心对齐开关
- ROM 映射开关
- 软限幅开关
- 音频增益 `gain_q8`
- 调制深度 `audio_depth_q8`
- DDS 测试频率 `test_ftw`
- DDS 测试幅度 `test_amp`
- 最大 duty `max_duty`
- 输出 mask，N32 使用低 32 位，5x12 预留低 60 位

相关文件：

- `UART_PROTOCOL.md`
- `upper/Phased_Array_Control.py`
- `upper/n32_beam_params.py`
- `verilog/uart_protocol_parser.sv`
- `verilog/audio_debug_processor.sv`
- `verilog/dds_generator.sv`
- `verilog/pwm32_generator.sv`
- `verilog/top_ultrasound_array.sv`
- `verilog/tb_uart_protocol_parser.sv`
- `verilog/tb_pwm32_generator.sv`
- `verilog/tb_audio_debug_processor.sv`
- `verilog/tb_uart_rx_protocol.sv`
- `run_sim.ps1`

N32 验证结果：

- UART 协议解析测试通过
- PWM32 输出 mask、最大 duty、边沿/中心对齐测试通过
- 音频调试链路增益、限幅、DDS 参数测试通过
- 上位机 Python 语法检查通过

## 3. N60 / 5x12 算法实现

新增 60 路算法库：

- `analysis/n60_5x12_beam_params.py`
- `analysis/evaluate_n60_5x12.py`
- `analysis/test_n60_5x12_beam_params.py`

阵列模型：

- 5 个 N12 子阵
- 子阵角度固定为 `[-45, -22.5, 0, 22.5, 45]°`
- 通道顺序固定为 `channel = unit_id * 12 + element_id`
- 相位使用精确近场聚焦距离公式
- 幅度支持多种策略

支持的幅度模式：

- `uniform`
- `unit_cosine`
- `unit_cosine_hamming`
- `optimized_dbc_margin`
- `optimized_table`
- `optimized_aggressive`

其中 `optimized_dbc_margin` 是本轮新增的主要候选策略。

## 4. 水平优化工况

本轮只扫描水平偏转：

- 距离：`0.5, 1, 2, 3, 5 m`
- 水平角：`-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30°`
- 垂直角：`0°`
- 总工况：`5 * 13 = 65`

优化变量：

- 60 路幅度全部参与离线优化
- 每路幅度范围 `0..1`
- 输出给硬件时映射到 `0..255`
- 相位范围 `0..2499`

核心评价标准：

```text
dBc = -max_sidelobe_db
dBc_improvement = dBc_optimized - dBc_uniform
gain_loss = -target_gain_delta_db
margin = dBc_improvement - gain_loss
```

只有 `margin > 0` 时，才认为幅度衰减相对 uniform 是工程上划算的。

## 5. 主要结果

水平 65 个工况完整评估已完成。

平均结果：

| 模式 | maxSL 平均 | dBc 收益 | 声压损失 | margin | p99SL 平均 | 平均幅度 |
|---|---:|---:|---:|---:|---:|---:|
| uniform | -9.95 dB | 0.00 dB | 0.00 dB | 0.00 dB | -11.11 dB | 1.00 |
| unit_cosine | -8.95 dB | -1.00 dB | 3.20 dB | -4.21 dB | -10.33 dB | 0.74 |
| unit_cosine_hamming | -6.76 dB | -3.19 dB | 13.37 dB | -16.56 dB | -7.57 dB | 0.23 |
| optimized_dbc_margin | -12.32 dB | 2.37 dB | 1.56 dB | 0.81 dB | -13.46 dB | 0.77 |
| optimized_table | -13.09 dB | 3.14 dB | 5.98 dB | -2.84 dB | -14.36 dB | 0.51 |
| optimized_aggressive | -12.78 dB | 2.82 dB | 11.04 dB | -8.22 dB | -14.19 dB | 0.35 |

结论：

- `optimized_dbc_margin` 是当前最适合硬件测试的候选表。
- `optimized_dbc_margin` 在 `55/65` 个工况满足 maxSL margin `> 0`。
- `optimized_dbc_margin` 在 `62/65` 个工况满足 p99 margin `> 0`。
- `optimized_table` 的绝对旁瓣更低，但声压损失过大，按 `dBc收益 > 声压损失` 标准不划算。
- `unit_cosine` 和 `unit_cosine_hamming` 不推荐作为硬件主方案，尤其 Hamming 导致主声压损失过大。

## 6. 指向性热力图检查

热力图是本轮必检项。输出中对比了：

- `uniform`
- `optimized_dbc_margin`
- `optimized_table`

重点角度：

- `0, ±10, ±20, ±30°`

重点距离：

- `0.5, 2, 5 m`

图中标记：

- 红叉：目标点
- 白点：实际峰值点
- 黑三角：最大旁瓣位置

峰值方向验收：

- 阈值：实际峰值偏移目标点不超过 `3°`
- 结果：选定热力图模式没有超过 `3°` 的失败项

结论：

- 主瓣没有明显跑偏。
- 从热力图看，`optimized_dbc_margin` 主瓣形态连续，适合作为第一版硬件测试表。
- `balanced/optimized_table` 旁瓣更干净，但声压损失不符合当前工程判据。

## 7. 输出文件

关键输出：

- `analysis_outputs/n60_5x12_focus_table_dbc_margin.csv`
- `analysis_outputs/n60_5x12_focus_table.csv`
- `analysis_outputs/n60_5x12_focus_table_aggressive.csv`
- `analysis_outputs/n60_5x12_metrics_horizontal.csv`
- `analysis_outputs/n60_5x12_summary_horizontal.txt`
- `analysis_outputs/n60_5x12_peak_direction_check.csv`
- `analysis_outputs/n60_5x12_patterns_horizontal.png`
- `analysis_outputs/n60_5x12_optimized_amplitudes_dbc_margin.png`
- `analysis_outputs/n60_5x12_geometry.csv`
- `analysis_outputs/n60_5x12_geometry.png`
- `analysis_outputs/n60_5x12_unit_gains.png`

已清理过期输出：

- `analysis_outputs/n60_5x12_metrics.csv`
- `analysis_outputs/n60_5x12_patterns.png`
- `analysis_outputs/n60_5x12_summary.txt`

这些文件来自旧版包含垂直偏转的评估，已被水平优化结果替代。

## 8. 验证

已执行：

```powershell
python -m py_compile analysis\n60_5x12_beam_params.py analysis\evaluate_n60_5x12.py analysis\test_n60_5x12_beam_params.py
python -m unittest analysis.test_n60_5x12_beam_params
python analysis\evaluate_n60_5x12.py
```

结果：

- 单元测试：`8` 个测试通过
- 完整水平优化：`65` 个工况完成
- 输出表、summary、峰值方向检查和热力图均已生成

## 9. 当前建议

下一步硬件测试优先使用：

```text
analysis_outputs/n60_5x12_focus_table_dbc_margin.csv
```

原因：

- 平均 margin 为正
- 多数工况满足 `dBc收益 > 声压损失`
- 热力图峰值方向检查通过
- 声压损失明显低于 balanced/aggressive

不建议优先使用：

- `unit_cosine_hamming`：声压损失过大，且旁瓣表现反而变差
- `optimized_aggressive`：声压损失过大
- `optimized_table`：可作为对照表，但不是当前工程判据下的首选

