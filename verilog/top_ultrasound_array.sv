`timescale 1ns / 1ps

module top_ultrasound_array (
    input  logic clk_50m,
    input  logic async_rst_n,
    input  logic uart_rx,
    input  logic key_in,
    output logic [31:0] transducer_io,
    output logic led,
    output logic i2c_scl,
    inout  wire  i2c_sda,
    output logic config_led,
    output logic clk_mclk,
    output logic wm8978_bclk,
    output logic wm8978_lrck,
    input  logic wm8978_adcdat
);

    logic clk_100m;
    logic locked;
    mmcm_main u_mmcm (
        .clk_in1  (clk_50m),
        .clk_out1 (clk_100m),
        .clk_out2 (clk_mclk),
        .locked   (locked)
    );

    logic rst_n;
    assign rst_n = async_rst_n & locked;

    logic i2c_init_done, i2c_error;
    wm8978_i2c_init u_conf (
        .clk       (clk_100m),
        .rst_n     (rst_n),
        .i2c_scl   (i2c_scl),
        .i2c_sda   (i2c_sda),
        .init_done (i2c_init_done),
        .ack_error (i2c_error)
    );
    assign config_led = !(i2c_init_done && !i2c_error);

    logic key_flag;
    key_filter u_key (
        .clk       (clk_100m),
        .rst       (~rst_n),
        .key_in    (key_in),
        .key_flag  (key_flag),
        .key_state ()
    );

    // The push button remains a quick local source toggle for bench work.
    logic audio_mode_override;
    always_ff @(posedge clk_100m or negedge rst_n) begin
        if (!rst_n)
            audio_mode_override <= 1'b0;
        else if (key_flag)
            audio_mode_override <= ~audio_mode_override;
    end

    logic signed [15:0] i2s_left_12m, i2s_right_12m;
    logic i2s_valid_12m;
    i2s_rx_master u_i2s (
        .rst_n      (rst_n),
        .mclk       (clk_mclk),
        .bclk       (wm8978_bclk),
        .lrck       (wm8978_lrck),
        .adcdat     (wm8978_adcdat),
        .left_data  (i2s_left_12m),
        .right_data (i2s_right_12m),
        .data_valid (i2s_valid_12m)
    );

    logic [2:0] valid_sync_100m;
    logic signed [15:0] i2s_left_100m, i2s_right_100m;
    always_ff @(posedge clk_100m or negedge rst_n) begin
        if (!rst_n) begin
            valid_sync_100m <= 3'b0;
            i2s_left_100m <= 16'sd0;
            i2s_right_100m <= 16'sd0;
        end else begin
            valid_sync_100m <= {valid_sync_100m[1:0], i2s_valid_12m};
            if (valid_sync_100m[2:1] == 2'b01) begin
                i2s_left_100m <= i2s_left_12m;
                i2s_right_100m <= i2s_right_12m;
            end
        end
    end

    logic [7:0]  beam_amplitude [0:31];
    logic [11:0] beam_phase     [0:31];
    logic [7:0]  debug_version;
    logic [7:0]  array_profile;
    logic [7:0]  debug_flags_raw;
    logic [7:0]  debug_flags;
    logic [15:0] gain_q8;
    logic [7:0]  limiter_mode;
    logic signed [15:0] limiter_threshold;
    logic [15:0] audio_depth_q8;
    logic signed [15:0] dc_offset;
    logic [31:0] test_ftw;
    logic [15:0] test_amp;
    logic [11:0] max_duty;
    logic [63:0] output_mask64;
    logic [7:0]  mod_version;
    logic [7:0]  mod_array_profile;
    logic [15:0] mod_flags;
    logic [7:0]  mod_source_select;
    logic [7:0]  modulation_mode;
    logic [7:0]  mod_sideband;
    logic [7:0]  debug_probe_select;
    logic [15:0] input_gain_q8;
    logic [7:0]  mod_limiter_mode;
    logic signed [15:0] mod_limiter_threshold;
    logic signed [15:0] mod_dc_offset;
    logic [15:0] mod_index_q15;
    logic [15:0] envelope_scale_q8;
    logic [31:0] mod_test_ftw;
    logic [15:0] mod_test_amp;
    logic [11:0] mod_max_duty;
    logic [63:0] mod_output_mask64;
    logic mod_update_pulse;

    (* mark_debug = "true", keep = "true" *) logic [7:0] uart_byte;
    (* mark_debug = "true", keep = "true" *) logic uart_done;
    (* mark_debug = "true", keep = "true" *) logic beam_update_pulse;
    (* mark_debug = "true", keep = "true" *) logic debug_update_pulse;
    (* mark_debug = "true", keep = "true" *) logic [15:0] uart_done_stretch_cnt;
    (* mark_debug = "true", keep = "true" *) logic [15:0] beam_update_stretch_cnt;
    (* mark_debug = "true", keep = "true" *) logic [15:0] debug_update_stretch_cnt;
    (* mark_debug = "true", keep = "true" *) logic uart_done_debug;
    (* mark_debug = "true", keep = "true" *) logic beam_update_debug;
    (* mark_debug = "true", keep = "true" *) logic debug_update_debug;

    uart_rx #(
        .CLK_FRE(100),
        .BAUD_RATE(115200)
    ) u_uart_rx (
        .clk         (clk_100m),
        .rst_n       (rst_n),
        .i_uart_rx   (uart_rx),
        .o_uart_data (uart_byte),
        .o_rx_done   (uart_done)
    );

    uart_protocol_parser u_parser (
        .clk                  (clk_100m),
        .rst_n                (rst_n),
        .rx_data              (uart_byte),
        .rx_done              (uart_done),
        .o_amplitude          (beam_amplitude),
        .o_phase              (beam_phase),
        .o_update_pulse       (beam_update_pulse),
        .o_debug_version      (debug_version),
        .o_array_profile      (array_profile),
        .o_debug_flags        (debug_flags_raw),
        .o_gain_q8            (gain_q8),
        .o_limiter_mode       (limiter_mode),
        .o_limiter_threshold  (limiter_threshold),
        .o_audio_depth_q8     (audio_depth_q8),
        .o_dc_offset          (dc_offset),
        .o_test_ftw           (test_ftw),
        .o_test_amp           (test_amp),
        .o_max_duty           (max_duty),
        .o_output_mask        (output_mask64),
        .o_debug_update_pulse (debug_update_pulse),
        .o_mod_version        (mod_version),
        .o_mod_array_profile  (mod_array_profile),
        .o_mod_flags          (mod_flags),
        .o_mod_source_select  (mod_source_select),
        .o_modulation_mode    (modulation_mode),
        .o_mod_sideband       (mod_sideband),
        .o_debug_probe_select (debug_probe_select),
        .o_input_gain_q8      (input_gain_q8),
        .o_mod_limiter_mode   (mod_limiter_mode),
        .o_mod_limiter_threshold(mod_limiter_threshold),
        .o_mod_dc_offset      (mod_dc_offset),
        .o_mod_index_q15      (mod_index_q15),
        .o_envelope_scale_q8  (envelope_scale_q8),
        .o_mod_test_ftw       (mod_test_ftw),
        .o_mod_test_amp       (mod_test_amp),
        .o_mod_max_duty       (mod_max_duty),
        .o_mod_output_mask    (mod_output_mask64),
        .o_mod_update_pulse   (mod_update_pulse)
    );

    assign debug_flags = debug_flags_raw ^ {6'd0, audio_mode_override, 1'b0};

    logic signed [15:0] test_sine;
    dds_generator u_dds (
        .clk       (clk_100m),
        .rst_n     (rst_n),
        .ftw       (mod_test_ftw),
        .amplitude (mod_test_amp),
        .sin_1k    (test_sine)
    );

    logic signed [15:0] processed_audio;
    audio_input_processor u_audio_input (
        .clk               (clk_100m),
        .rst_n             (rst_n),
        .i2s_audio         (i2s_left_100m),
        .test_audio        (test_sine),
        .source_select     (mod_source_select ^ {7'd0, audio_mode_override}),
        .input_gain_q8     (input_gain_q8),
        .limiter_mode      (mod_limiter_mode),
        .limiter_threshold (mod_limiter_threshold),
        .dc_offset         (mod_dc_offset),
        .safe_clamp_enable (mod_flags[2]),
        .audio_out         (processed_audio)
    );

    logic [11:0] sample_div_cnt;
    logic sample_tick;
    always_ff @(posedge clk_100m or negedge rst_n) begin
        if (!rst_n) begin
            sample_div_cnt <= 12'd0;
            sample_tick <= 1'b0;
        end else if (sample_div_cnt == 12'd2082) begin
            sample_div_cnt <= 12'd0;
            sample_tick <= 1'b1;
        end else begin
            sample_div_cnt <= sample_div_cnt + 1'b1;
            sample_tick <= 1'b0;
        end
    end

    logic signed [15:0] audio_delay_48k;
    logic signed [15:0] hilbert_audio_48k;
    logic hilbert_valid;
    hilbert_fir u_hilbert (
        .clk          (clk_100m),
        .rst_n        (rst_n),
        .sample_valid (sample_tick),
        .sample_in    (processed_audio),
        .sample_delay (audio_delay_48k),
        .hilbert_out  (hilbert_audio_48k),
        .out_valid    (hilbert_valid)
    );

    logic signed [31:0] audio_i_q15;
    logic signed [31:0] audio_q_q15;
    logic [31:0] audio_norm_q15;
    logic iq_valid;
    audio_iq_modulator u_iq (
        .clk             (clk_100m),
        .rst_n           (rst_n),
        .sample_valid    (hilbert_valid),
        .audio_sample    (audio_delay_48k),
        .hilbert_sample  (hilbert_audio_48k),
        .modulation_mode (modulation_mode),
        .sideband        (mod_sideband),
        .mod_index_q15   (mod_index_q15),
        .i_q15           (audio_i_q15),
        .q_q15           (audio_q_q15),
        .norm_q15        (audio_norm_q15),
        .out_valid       (iq_valid)
    );

    logic [11:0] audio_envelope_q12;
    logic [11:0] audio_phase_ticks;
    logic polar_valid;
    cordic_polar u_polar (
        .clk          (clk_100m),
        .rst_n        (rst_n),
        .sample_valid (iq_valid),
        .i_q15        (audio_i_q15),
        .q_q15        (audio_q_q15),
        .norm_q15     (audio_norm_q15),
        .envelope_q12 (audio_envelope_q12),
        .phase_ticks  (audio_phase_ticks),
        .out_valid    (polar_valid)
    );

    logic [35:0] duty_scale_mult;
    logic [23:0] duty_env_mult;
    logic [11:0] global_duty_base;
    always_comb begin
        duty_env_mult = audio_envelope_q12 * mod_max_duty;
        duty_scale_mult = (duty_env_mult >> 12) * envelope_scale_q8;
        if ((duty_scale_mult >> 8) > 36'd1250)
            global_duty_base = 12'd1250;
        else
            global_duty_base = (duty_scale_mult >> 8);
    end

    logic use_external_duty;
    logic use_legacy_rom_mapping;
    assign use_external_duty = (modulation_mode != 8'd0) && !mod_flags[3];
    assign use_legacy_rom_mapping = (modulation_mode == 8'd0) && !mod_flags[3];

    always_ff @(posedge clk_100m or negedge rst_n) begin
        if (!rst_n) begin
            uart_done_stretch_cnt <= 16'd0;
            beam_update_stretch_cnt <= 16'd0;
            debug_update_stretch_cnt <= 16'd0;
        end else begin
            if (uart_done)
                uart_done_stretch_cnt <= 16'hFFFF;
            else if (uart_done_stretch_cnt != 16'd0)
                uart_done_stretch_cnt <= uart_done_stretch_cnt - 1'b1;

            if (beam_update_pulse)
                beam_update_stretch_cnt <= 16'hFFFF;
            else if (beam_update_stretch_cnt != 16'd0)
                beam_update_stretch_cnt <= beam_update_stretch_cnt - 1'b1;

            if (debug_update_pulse)
                debug_update_stretch_cnt <= 16'hFFFF;
            else if (debug_update_stretch_cnt != 16'd0)
                debug_update_stretch_cnt <= debug_update_stretch_cnt - 1'b1;
        end
    end

    assign uart_done_debug = (uart_done_stretch_cnt != 16'd0);
    assign beam_update_debug = (beam_update_stretch_cnt != 16'd0);
    assign debug_update_debug = (debug_update_stretch_cnt != 16'd0);
    assign led = debug_update_debug;

    pwm32_generator u_pwm32 (
        .clk             (clk_100m),
        .rst_n           (rst_n),
        .audio_in        (processed_audio),
        .amplitude       (beam_amplitude),
        .phase_del       (beam_phase),
        .output_enable   (mod_flags[0]),
        .center_align    (mod_flags[1]),
        .use_rom_mapping (use_legacy_rom_mapping),
        .max_duty        (mod_max_duty),
        .use_external_duty(use_external_duty),
        .global_duty_base(global_duty_base),
        .global_phase_offset(use_external_duty ? audio_phase_ticks : 12'd0),
        .output_mask     (mod_output_mask64[31:0]),
        .pwm_out         (transducer_io)
    );

    wire _unused_top = ^{
        debug_version, array_profile, debug_flags, gain_q8, limiter_mode, limiter_threshold,
        audio_depth_q8, dc_offset, test_ftw, test_amp, max_duty, output_mask64,
        mod_version, mod_array_profile, debug_probe_select, polar_valid, mod_update_pulse,
        i2s_right_100m, uart_done_debug, beam_update_debug
    };
endmodule
