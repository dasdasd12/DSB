`timescale 1ns / 1ps

module tb_audio_iq_modulator;
    logic clk;
    logic rst_n;
    logic sample_valid;
    logic signed [15:0] audio_sample;
    logic signed [15:0] hilbert_sample;
    logic [7:0] modulation_mode;
    logic [7:0] sideband;
    logic [15:0] mod_index_q15;
    logic signed [31:0] i_q15;
    logic signed [31:0] q_q15;
    logic [31:0] norm_q15;
    logic out_valid;

    integer pass_cnt;
    integer error_cnt;
    integer valid_count;

    audio_iq_modulator dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .audio_sample(audio_sample),
        .hilbert_sample(hilbert_sample),
        .modulation_mode(modulation_mode),
        .sideband(sideband),
        .mod_index_q15(mod_index_q15),
        .i_q15(i_q15),
        .q_q15(q_q15),
        .norm_q15(norm_q15),
        .out_valid(out_valid)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            valid_count <= 0;
        else if (out_valid)
            valid_count <= valid_count + 1;
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

    task automatic tick_sample;
        begin
            @(negedge clk);
            sample_valid = 1'b1;
            @(negedge clk);
            sample_valid = 1'b0;
            repeat (2) @(posedge clk);
        end
    endtask

    initial begin
        $dumpfile("tb_audio_iq_modulator.vcd");
        $dumpvars(0, tb_audio_iq_modulator);

        pass_cnt = 0;
        error_cnt = 0;
        valid_count = 0;
        sample_valid = 1'b0;
        audio_sample = 16'sd16384;
        hilbert_sample = 16'sd8192;
        mod_index_q15 = 16'd16384;
        modulation_mode = 8'd1;
        sideband = 8'd0;
        rst_n = 1'b0;
        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        tick_sample();
        check(valid_count == 1, "DSB produces valid output");
        check(i_q15 > 32'sd32768, "DSB I increases for positive audio");
        check(q_q15 == 32'sd0, "DSB Q is zero");

        modulation_mode = 8'd2;
        sideband = 8'd0;
        tick_sample();
        check(q_q15 > 32'sd0, "SSB USB Q is positive");

        modulation_mode = 8'd3;
        sideband = 8'd1;
        tick_sample();
        check(q_q15 < 32'sd0, "SSB LSB Q is negative");

        modulation_mode = 8'd4;
        tick_sample();
        check(i_q15 > 32'sd32768, "MAM1 I follows audio");
        check(q_q15 < 32'sd32768, "MAM1 Q compresses with positive audio");
        check(norm_q15 > 32'd32768, "MAM1 norm is above unity");

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
