# Ultrasonic Air Demodulation and Harmonic Analysis

本文档记录 UltraAudio 当前二次、三次谐波问题的理论背景、项目内可疑代码点、推荐实验顺序和调制算法优化方向。

## 结论摘要

超声参数阵的空气自解调不是线性包络检波。按 Berktay 远场近似，解调后的可听声与超声包络平方的二阶时间导数相关：

```text
p_audio(t) ∝ d²/dt² [E²(t)]
```

如果直接做普通 AM：

```text
E(t) = 1 + m s(t)
E²(t) = 1 + 2m s(t) + m² s²(t)
```

其中 `2m s(t)` 是目标音频项，`m² s²(t)` 是失真项。单音 `s(t)=sin(Ωt)` 时，`s²(t)` 会产生 `2Ω` 分量，所以二次谐波是普通 AM 的自然结果。

三次谐波不是这个二阶近似直接产生的主项。当前项目若看到明显三次谐波，应优先怀疑：

- 音频链路削波或分段限幅。
- PWM duty 映射、ROM 预失真曲线或 `max_duty` 截断。
- 换能器、功放、UCC 驱动或空气传播进入更强非线性区。
- 采集/解调链路自身非线性或超声载波串入麦克风/ADC。

阵列算法本身通常不是第一嫌疑。应先用单通道、固定 DDS 音源、固定测量距离把数字调制链路和物理链路分开。

当前补充实测现象：

- 单通道、1 kHz 测试仍有明显二次、三次谐波。
- 减小 `audio_depth_q8` 后音量大幅下降，谐波相对幅度只略有改善，仍不可接受。
- `center_align` 开关对结果影响不明显。

这些现象基本排除了阵列干涉和 PWM 边沿对齐作为主因，也说明单纯降低调制深度不是可用方案。下一步应重点识别实际换能器/驱动/空气/接收链路的幅相传递函数，或改用更适合窄带换能器的 SSB/MAM 类调制。

## 理论模型

### Westervelt 方程

Westervelt 的有限幅声波模型中，非线性源项来自声压平方：

```text
source ∝ ∂²(p²)/∂t²
```

这意味着高强度超声在空气中传播时，会通过介质非线性产生差频、谐波和互调。参数阵音箱利用的正是这个非线性项。

### Berktay 远场近似

设超声载波为：

```text
p1(t) = P0 E(t) cos(ωc t)
```

则：

```text
p1²(t) = P0² E²(t) [1 + cos(2ωc t)] / 2
```

在远场、近轴和高频超声衰减之后，可听声近似由 `E²(t)` 生成。因此发射包络不能简单等于目标音频；否则平方项会制造谐波。

### KZK 模型

KZK 方程把有限孔径声束的衍射、吸收和非线性放在同一个模型里，比 Berktay 更适合解释实际阵列的近场、焦点、旁瓣和传播损耗。工程上可以先用 Berktay 判断调制失真，再用实测或 KZK 类模型处理阵列/传播细节。

## 当前项目的重点可疑点

### 1. `audio_debug_processor.sv`

文件：`verilog/audio_debug_processor.sv`

重点信号：

- `gain_q8`：只对 I2S 源生效，DDS/test 源绕过 gain。I2S 路径若增益过大，很容易推入限幅或最终 `clamp16`。
- `dc_offset`：在限幅和调制深度之前加入。非零偏置会破坏正负半周对称，和限幅叠加后特别容易产生二次谐波。
- `limiter_mode` / `flags[4]`：当前逻辑中 `limiter_mode == 1 || flags[4]` 触发硬限幅；但 GUI 文案是 `Soft limiter flag`。这会让用户以为打开的是软限幅，实际可能打开硬削波。
- `audio_depth_q8`：在限幅后继续乘法，最后才 `clamp16`。即使 limiter 阈值安全，`audio_depth_q8 > 256` 也可能在输出级削顶。
- `soft_abs`：所谓 soft limiter 是超过阈值后斜率变为 1/4 的分段函数，不是平滑 knee；拐点仍会产生谐波。

### 2. `pwm32_generator.sv`

文件：`verilog/pwm32_generator.sv`

重点信号：

- `rom_addr = audio_in + 32768`：所有音频削波、偏置和量化都会直接变成 ROM 地址非线性。
- `sqrt_mapping_rom`：真实 Vivado ROM 数据不在仓库中，当前 `tb_pwm32_generator.sv` 里的 ROM 是常数桩，无法验证真实预失真曲线。
- `use_rom_mapping=0`：当前不是线性 AM，而是固定 duty debug carrier。关闭 ROM 应用于“无音频载波对照实验”，不是一个可听音频调制模式。
- `max_duty`：ROM 输出再被 `effective_max_duty` 截断。如果高端经常撞到 `max_duty`，等价于包络削顶。
- `center_align`：默认 edge-aligned。中心对齐通常更利于降低边沿分布不对称和驱动链路非线性。

### 3. `generate_coe.py`

文件：`verilog/generate_coe.py`

这个脚本的思路是 `sqrt + arcsin` 预失真：

```text
target_envelope = sqrt(1 + MODULATION_INDEX * audio_norm)
pwm_val = asin(target_envelope / max_envelope) / (pi/2) * PWM_MAX
```

这有两个隐含条件：

- ROM 固定假设 `MODULATION_INDEX = 0.7`。
- PWM 到实际超声声压的关系近似为脚本里的 `sin()` 模型。

实际 RTL 又允许调 `audio_depth_q8`、`test_amp` 和 `max_duty`，所以运行时调制指数可能和 ROM 生成时假设不一致。若 Vivado 中的 ROM 数据不是当前脚本生成的版本，问题会更复杂。

### 4. 上位机参数范围

文件：`upper/Phased_Array_Control.py`

当前 GUI 允许：

- `gain_q8` 到 8192，即 32x。
- `audio_depth_q8` 到 8192，即 32x。
- `test_amp` 到 32767。
- limiter 和 `Soft limiter flag` 可同时配置。

这些范围适合调试，但也很容易把链路推入削波区。做谐波实验时必须记录完整 debug 参数。

## 排查实验矩阵

### 阶段 A：数字源和 RTL 输出基线

目标：确认 DDS、音频处理和 PWM 映射本身是否已产生明显谐波。

固定条件：

```text
source = DDS/test
test_freq = 1000 Hz
test_amp = 8192
gain_q8 = 256
audio_depth_q8 = 256
dc_offset = 0
limiter_mode = 0
soft limiter flag = 0
output_mask = 0x0000000000000001
beam amplitude ch0 = 255
beam phase ch0 = 0
```

实验：

1. 直接 FFT `test_sine`，确认 DDS 自身 H2/H3 底噪。
2. FFT `audio_out`，确认 `audio_debug_processor` 没有削波。
3. 用真实 ROM 导出每个 40 kHz 周期的 `duty_base_d2`，对 duty 包络做 FFT。
4. 统计 `duty_base_d2 == effective_max_duty` 的比例，判断是否撞 `max_duty`。
5. 设置 `use_rom_mapping=0` 做固定 duty 载波对照；此时理论上不应有可听音频，若测到 1 kHz 或其谐波，说明测量或外部链路有串扰/伪影。

### 阶段 B：参数扫描

每次只改一个参数：

```text
test_amp:        1024, 4096, 8192, 16384
audio_depth_q8:  64, 128, 192, 256, 384, 512
max_duty:        256, 512, 800, 1000, 1250
center_align:    0, 1
dc_offset:       0, +500, -500, +2000, -2000
limiter_mode:    0, 1, 2
flags[4]:        0, 1
```

重点观察：

- H2 是否随 `dc_offset` 和 `max_duty` 截断上升。
- H3 是否随 limiter、`audio_depth_q8` 或输出级削顶上升。
- `center_align=1` 是否降低实测 H2/H3 或载波相关伪影。
- `use_rom_mapping=0` 时是否仍有可听分量。

### 阶段 C：单换能器物理实验

只打开一个通道，避免阵列和反射复杂化。

建议记录：

```text
测试距离
换能器型号和驱动电压
debug 参数完整截图或 UART 包
麦克风型号
采样率
FFT 窗函数和采样时长
1f、2f、3f 幅度
THD
```

如果单通道已经有强 H2/H3，优先排查调制、驱动、换能器和采集链路。不要先改阵列算法。

当前已观察到单通道 1 kHz 仍存在不可接受的谐波，因此后续单通道实验不应继续以“降低 `audio_depth_q8`”为主线，而应转向：

- 测量 40 kHz 附近的实际上下边带幅相。
- 分离换能器前电信号失真和空气解调后的声信号失真。
- 验证接收麦克风/ADC/解调流程是否自身产生 H2/H3。
- 对实际 `duty -> acoustic carrier/sideband` 曲线做拟合，再重建预失真 LUT。

### 阶段 D：阵列实验

按通道数逐步增加：

```text
1 -> 4 -> 8 -> 16 -> N32/N60
```

比较：

- 单点聚焦 vs 全通道同相。
- full amplitude vs 加权 amplitude。
- 近距离 vs 远距离。
- 目标点 vs 旁瓣方向。

若谐波只在多通道阵列时明显上升，才进一步考虑焦点声压过高、反射、多路径或阵列旁瓣问题。

## 调制算法优化方向

### 短期：解释当前 `sqrt + arcsin` 实测路线

当前工程已经采用 `sqrt + arcsin` 路线，并且实测仍出现明显二次、三次谐波。因此下一步不是简单“打开平方根预失真”，而是解释为什么理论预失真没有在当前硬件上闭环成立。

- 默认关闭 limiter 和 `flags[4]`。
- `dc_offset=0`。
- 限制 `audio_depth_q8 <= 256`，优先从 64、128、192 扫起。
- `test_amp` 不要直接满量程，优先 `4096` 或 `8192`。
- 优先启用 center-aligned PWM。
- 确认 Vivado ROM 数据与 `generate_coe.py` 一致；当前仓库缺 ROM 数据属于上传缺失，不代表硬件未实现该路线。

如果当前 ROM 是 `sqrt + arcsin`，需要明确运行时调制指数。不要同时让 `MODULATION_INDEX`、`test_amp`、`audio_depth_q8` 和 `max_duty` 各自独立改变而没有统一定义。

当前路线仍失真的主要可能原因：

- Berktay 模型中可听声近似为 `d²(E²)/dt²`，只做 `E=sqrt(1+m*x)` 会让 `E²≈1+m*x`，但输出仍近似 `x''`，需要音频预均衡或测量端统一补偿频响。
- `arcsin` 假设 PWM duty 到 40 kHz 基波声压满足理想 `sin(pi*D)`，但实际链路还包括 UCC 驱动、换能器阻抗、机械谐振、声学负载和麦克风响应。
- 40 kHz 换能器通常是窄带器件，平方根预处理产生的上下边带未必被等幅等相地发射。边带幅相不对称会破坏 `E²≈目标` 的前提。
- `MODULATION_INDEX=0.7`、`test_amp`、`audio_depth_q8`、`max_duty` 和每通道 `amplitude` 必须共同定义实际声学调制度；任一处削顶或压缩都会重新产生 H2/H3。
- 空气非线性模型只覆盖传播中的二阶效应，不覆盖驱动器/换能器/接收解调链路的三阶或分段非线性。

因此下一步关键实验是识别“电输入 duty -> 换能器声压基波幅相 -> 解调音频”的实际传递函数，而不是只验证 ROM 数学公式。

### 只有可听范围测试条件时

如果没有 40 kHz 附近声学测量条件，仍然可以推进，但方法要改成黑箱音频测量：

```text
数字输入/调制参数 -> FPGA/驱动/换能器/空气/麦克风 -> 可听录音
```

此时不要试图直接验证 40 kHz 包络，而是用可听录音估计整条链路的等效非线性。推荐做法：

1. 固定单通道、固定距离、固定麦克风位置。
2. 使用 DDS/test 或从上位机送入纯净单音。
3. 录制可听输出，计算 `1f/2f/3f` 幅度和相位。
4. 对 `500 Hz, 800 Hz, 1 kHz, 1.5 kHz, 2 kHz, 3 kHz` 分别测量。
5. 对几个可用音量档分别测量，避免只在接近听不见的低 q8 区工作。

在只有可听测量时，实用优化路线有两条：

- 单音/窄带校准：在输入中主动加入反相 `2f`、`3f` 小分量，让录音中的 H2/H3 抵消。这适合验证“可听端闭环补偿是否有效”，但不适合作为最终音乐播放算法。
- 宽带预失真：把系统近似成 `y = h1*x + h2*x² + h3*x³ + ...`，用录音估计二阶、三阶系数，然后在输入音频端加入反向多项式预失真。该方法可以只依赖可听录音，但需要多频点、多音和不同音量下拟合，且结果依赖麦克风位置。

建议先做单音谐波抵消实验。如果在 1 kHz 下加入反相 2 kHz/3 kHz 后，录音中 H2/H3 能明显下降，就说明“可听端黑箱预失真”可行。之后再升级为多项式或 Volterra/Hammerstein 预失真。

如果反相谐波注入也无法降低录音 H2/H3，则要优先怀疑：

- 麦克风/录音链路自身失真。
- 房间反射或测量位置导致的多路径。
- 解调声场在空间上变化太快，单点补偿不能稳定成立。
- 驱动或换能器已进入强非线性，且相位/幅度随时间或温度漂移。

### 中期：实现 SSB 或 MAM1

文献实验显示，SSB-AM 通常能降低谐波失真，MAM1 在常见窄带超声换能器上是很实用的折中方案。

推荐 FPGA 架构：

```text
audio sample
  -> optional EQ / limiter
  -> modulation preprocessor
  -> audio_envelope(t), audio_phase_ticks(t)
  -> pwmN_generator
       duty[ch]  = audio_envelope * beam_amplitude[ch]
       phase[ch] = beam_phase[ch] + audio_phase_ticks
```

这样阵列相位和音频预处理是解耦的。N32 和 N60 都可以共享音频预处理模块，只替换通道数和 beam 参数。

实现优先级：

1. `SRAM/sqrt LUT`：最容易落地，但受换能器带宽限制。
2. `SSB-AM`：需要 Hilbert FIR 或正交音频；适合中期实现。
3. `MAM1`：对窄带换能器更现实，可先在 Python 离线仿真，再移植为 LUT/FIR。
4. `Volterra/FM`：复杂度高，不建议作为当前主线。

## 推荐新增工具

建议后续新增：

- `analysis/harmonic_probe.py`：读取波形 CSV/WAV，输出 1f/2f/3f、THD 和频谱图。
- `verilog/tb_pwm_harmonic_probe.sv`：导出 `test_sine`、`audio_out`、`duty_base` 和单路 PWM 周期统计。
- `docs/harmonic_logs/`：保存每次实测参数、频谱图和结论。

## 参考资料

- Peter J. Westervelt, “Parametric Acoustic Array,” JASA 1963. DOI: https://doi.org/10.1121/1.1918525
- H. O. Berktay, “Possible Exploitation of Non-Linear Acoustics in Underwater Transmitting Applications,” Journal of Sound and Vibration, 1965. DOI: https://doi.org/10.1016/0022-460X(65)90122-7
- Ricardo San Martín, Pablo Tello, Ana Valencia, Asier Marzo, “Experimental Evaluation of Distortion in Amplitude Modulation Techniques for Parametric Loudspeakers,” Applied Sciences 2020. https://www.mdpi.com/2076-3417/10/6/2070
- Ee-Leng Tan, Peifeng Ji, Woon-Seng Gan, “On preprocessing techniques for bandlimited parametric loudspeakers,” Applied Acoustics 2010. https://doi.org/10.1016/j.apacoust.2009.11.006
- Takahi Kamakura, Masahide Yoneyama, Kazuo Ikegaya, “Studies for the realization of parametric loud-speaker,” JASJ 1985. https://www.jstage.jst.go.jp/article/jasj/41/6/41_KJ00001453735/_article/-char/en
- Vikrant A. Marathe, “Analog Single Sideband-Pulse Width Modulation Processor for Parametric Acoustic Arrays,” Cal Poly thesis, 2019. https://digitalcommons.calpoly.edu/theses/2056/
- Douglas Liu, “Single-Sideband Pulse Width Modulation for Parametric Acoustic Arrays,” Cal Poly thesis, 2024. https://digitalcommons.calpoly.edu/theses/3047/
