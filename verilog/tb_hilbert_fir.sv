`timescale 1ns / 1ps

module tb_hilbert_fir;
    logic clk;
    logic rst_n;
    logic sample_valid;
    logic signed [15:0] sample_in;
    logic signed [15:0] sample_delay;
    logic signed [15:0] hilbert_out;
    logic out_valid;

    integer pass_cnt;
    integer error_cnt;
    integer i;
    integer nonzero_count;

    hilbert_fir dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .sample_in(sample_in),
        .sample_delay(sample_delay),
        .hilbert_out(hilbert_out),
        .out_valid(out_valid)
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

    task automatic send_sample;
        input signed [15:0] value;
        begin
            @(negedge clk);
            sample_in = value;
            sample_valid = 1'b1;
            @(negedge clk);
            sample_valid = 1'b0;
            @(posedge clk);
        end
    endtask

    initial begin
        $dumpfile("tb_hilbert_fir.vcd");
        $dumpvars(0, tb_hilbert_fir);

        pass_cnt = 0;
        error_cnt = 0;
        nonzero_count = 0;
        sample_valid = 1'b0;
        sample_in = 16'sd0;
        rst_n = 1'b0;
        repeat (4) @(posedge clk);
        rst_n = 1'b1;

        for (i = 0; i < 96; i = i + 1) begin
            case (i[3:0])
                4'd0: send_sample(16'sd0);
                4'd1: send_sample(16'sd4277);
                4'd2: send_sample(16'sd8192);
                4'd3: send_sample(16'sd11363);
                4'd4: send_sample(16'sd14189);
                4'd5: send_sample(16'sd16069);
                4'd6: send_sample(16'sd16384);
                4'd7: send_sample(16'sd16069);
                4'd8: send_sample(16'sd14189);
                4'd9: send_sample(16'sd11363);
                4'd10: send_sample(16'sd8192);
                4'd11: send_sample(16'sd4277);
                4'd12: send_sample(16'sd0);
                4'd13: send_sample(-16'sd4277);
                4'd14: send_sample(-16'sd8192);
                default: send_sample(-16'sd11363);
            endcase
            if (out_valid && (hilbert_out > 16'sd100 || hilbert_out < -16'sd100))
                nonzero_count = nonzero_count + 1;
        end

        check(nonzero_count > 10, "Hilbert FIR produces nonzero quadrature output for sine input");
        check(out_valid == 1'b1, "Hilbert FIR asserts output valid on samples");

        $display("Simulation summary: passes=%0d errors=%0d", pass_cnt, error_cnt);
        if (error_cnt == 0)
            $display("RESULT: ALL TESTS PASSED");
        else
            $display("RESULT: %0d CHECK(S) FAILED", error_cnt);
        $finish;
    end

    initial begin
        #300000;
        $display("[FAIL] simulation timeout");
        $finish;
    end
endmodule
