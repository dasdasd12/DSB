`timescale 1ns / 1ps

module audio_input_processor (
    input  logic               clk,
    input  logic               rst_n,
    input  logic signed [15:0] i2s_audio,
    input  logic signed [15:0] test_audio,
    input  logic [7:0]         source_select,
    input  logic [15:0]        input_gain_q8,
    input  logic [7:0]         limiter_mode,
    input  logic signed [15:0] limiter_threshold,
    input  logic signed [15:0] dc_offset,
    input  logic               safe_clamp_enable,
    output logic signed [15:0] audio_out
);

    function automatic signed [15:0] clamp16(input signed [31:0] value);
        begin
            if (value > 32'sd32767)
                clamp16 = 16'sd32767;
            else if (value < -32'sd32768)
                clamp16 = -16'sd32768;
            else
                clamp16 = value[15:0];
        end
    endfunction

    function automatic signed [31:0] abs32(input signed [31:0] value);
        begin
            abs32 = value[31] ? -value : value;
        end
    endfunction

    logic signed [15:0] selected_audio;
    logic signed [31:0] gained_audio;
    logic signed [31:0] offset_audio;
    logic signed [31:0] limited_audio;
    logic signed [31:0] limit_abs;
    logic signed [31:0] threshold_abs;
    logic signed [31:0] soft_abs;

    always_comb begin
        selected_audio = (source_select == 8'd1) ? i2s_audio : test_audio;
        gained_audio = (selected_audio * $signed({1'b0, input_gain_q8})) >>> 8;
        offset_audio = gained_audio + dc_offset;
        limited_audio = offset_audio;

        threshold_abs = abs32(limiter_threshold);
        if (threshold_abs < 32'sd1)
            threshold_abs = 32'sd1;
        if (threshold_abs > 32'sd32767)
            threshold_abs = 32'sd32767;

        limit_abs = abs32(offset_audio);
        if (limiter_mode == 8'd1) begin
            if (limit_abs > threshold_abs)
                limited_audio = offset_audio[31] ? -threshold_abs : threshold_abs;
        end else if (limiter_mode == 8'd2) begin
            if (limit_abs > threshold_abs) begin
                soft_abs = threshold_abs + ((limit_abs - threshold_abs) >>> 2);
                if (soft_abs > 32'sd32767)
                    soft_abs = 32'sd32767;
                limited_audio = offset_audio[31] ? -soft_abs : soft_abs;
            end
        end

        if (safe_clamp_enable) begin
            if (limited_audio > 32'sd30000)
                limited_audio = 32'sd30000;
            else if (limited_audio < -32'sd30000)
                limited_audio = -32'sd30000;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            audio_out <= 16'sd0;
        else
            audio_out <= clamp16(limited_audio);
    end
endmodule
