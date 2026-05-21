`timescale 1ns / 1ps

module tb_audio_debug_processor;
    logic clk;
    logic rst_n;
    logic signed [15:0] i2s_audio;
    logic signed [15:0] test_audio;
    logic [7:0] flags;
    logic [15:0] gain_q8;
    logic [7:0] limiter_mode;
    logic signed [15:0] limiter_threshold;
    logic [15:0] audio_depth_q8;
    logic signed [15:0] dc_offset;
    logic signed [15:0] audio_out;

    integer pass_cnt;
    integer error_cnt;

    audio_debug_processor dut (
        .clk(clk),
        .rst_n(rst_n),
        .i2s_audio(i2s_audio),
        .test_audio(test_audio),
        .flags(flags),
        .gain_q8(gain_q8),
        .limiter_mode(limiter_mode),
        .limiter_threshold(limiter_threshold),
        .audio_depth_q8(audio_depth_q8),
        .dc_offset(dc_offset),
        .audio_out(audio_out)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    task automatic check;
        input condition;
        input [1023:0] message;
        begin
            if (condition) begin
                pass_cnt = pass_cnt + 1;
                $display("[PASS] %0s", message);
            end else begin
                error_cnt = error_cnt + 1;
                $display("[FAIL] %0s", message);
            end
        end
    endtask

    initial begin
        $dumpfile("tb_audio_debug_processor.vcd");
        $dumpvars(0, tb_audio_debug_processor);

        pass_cnt = 0;
        error_cnt = 0;
        i2s_audio = 16'sd1000;
        test_audio = 16'sd2000;
        flags = 8'h00;
        gain_q8 = 16'd256;
        limiter_mode = 8'd0;
        limiter_threshold = 16'sd32767;
        audio_depth_q8 = 16'd256;
        dc_offset = 16'sd0;
        rst_n = 1'b0;
        repeat (3) @(posedge clk);
        rst_n = 1'b1;

        repeat (2) @(posedge clk);
        check(audio_out == 16'sd2000, "DDS/test source passes through by default");

        flags = 8'h02;
        gain_q8 = 16'd512;
        repeat (2) @(posedge clk);
        check(audio_out == 16'sd2000, "I2S source gain_q8=512 doubles audio");

        gain_q8 = 16'd2048;
        limiter_mode = 8'd1;
        limiter_threshold = 16'sd4096;
        repeat (2) @(posedge clk);
        check(audio_out == 16'sd4096, "hard limiter clamps gained audio");

        gain_q8 = 16'd512;
        limiter_mode = 8'd0;
        audio_depth_q8 = 16'd128;
        repeat (2) @(posedge clk);
        check(audio_out == 16'sd1000, "audio_depth_q8=128 halves processed audio");

        dc_offset = -16'sd100;
        repeat (2) @(posedge clk);
        check(audio_out == 16'sd950, "dc offset applies before depth scaling");

        $display("Simulation summary: passes=%0d errors=%0d", pass_cnt, error_cnt);
        if (error_cnt == 0)
            $display("RESULT: ALL TESTS PASSED");
        else
            $display("RESULT: %0d CHECK(S) FAILED", error_cnt);
        $finish;
    end

    initial begin
        #200000;
        $display("[FAIL] simulation timeout");
        $finish;
    end
endmodule
