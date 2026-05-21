`timescale 1ns / 1ps

module tb_uart_protocol_parser;

    logic clk;
    logic rst_n;
    logic [7:0] rx_data;
    logic rx_done;
    logic [7:0] amplitude [0:31];
    logic [11:0] phase [0:31];
    logic update_pulse;
    logic [7:0] debug_version;
    logic [7:0] array_profile;
    logic [7:0] debug_flags;
    logic [15:0] gain_q8;
    logic [7:0] limiter_mode;
    logic signed [15:0] limiter_threshold;
    logic [15:0] audio_depth_q8;
    logic signed [15:0] dc_offset;
    logic [31:0] test_ftw;
    logic [15:0] test_amp;
    logic [11:0] max_duty;
    logic [63:0] output_mask;
    logic debug_update_pulse;
    logic [7:0] mod_version;
    logic [7:0] mod_array_profile;
    logic [15:0] mod_flags;
    logic [7:0] mod_source_select;
    logic [7:0] modulation_mode;
    logic [7:0] mod_sideband;
    logic [7:0] debug_probe_select;
    logic [15:0] input_gain_q8;
    logic [7:0] mod_limiter_mode;
    logic signed [15:0] mod_limiter_threshold;
    logic signed [15:0] mod_dc_offset;
    logic [15:0] mod_index_q15;
    logic [15:0] envelope_scale_q8;
    logic [31:0] mod_test_ftw;
    logic [15:0] mod_test_amp;
    logic [11:0] mod_max_duty;
    logic [63:0] mod_output_mask;
    logic mod_update_pulse;

    integer pass_cnt;
    integer error_cnt;
    integer update_count;
    integer debug_update_count;
    integer mod_update_count;
    integer ch;

    uart_protocol_parser dut (
        .clk                  (clk),
        .rst_n                (rst_n),
        .rx_data              (rx_data),
        .rx_done              (rx_done),
        .o_amplitude          (amplitude),
        .o_phase              (phase),
        .o_update_pulse       (update_pulse),
        .o_debug_version      (debug_version),
        .o_array_profile      (array_profile),
        .o_debug_flags        (debug_flags),
        .o_gain_q8            (gain_q8),
        .o_limiter_mode       (limiter_mode),
        .o_limiter_threshold  (limiter_threshold),
        .o_audio_depth_q8     (audio_depth_q8),
        .o_dc_offset          (dc_offset),
        .o_test_ftw           (test_ftw),
        .o_test_amp           (test_amp),
        .o_max_duty           (max_duty),
        .o_output_mask        (output_mask),
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
        .o_mod_output_mask    (mod_output_mask),
        .o_mod_update_pulse   (mod_update_pulse)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            update_count <= 0;
            debug_update_count <= 0;
            mod_update_count <= 0;
        end else begin
            if (update_pulse)
                update_count <= update_count + 1;
            if (debug_update_pulse)
                debug_update_count <= debug_update_count + 1;
            if (mod_update_pulse)
                mod_update_count <= mod_update_count + 1;
        end
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

    task automatic send_byte;
        input [7:0] value;
        begin
            @(negedge clk);
            rx_data = value;
            rx_done = 1'b1;
            @(negedge clk);
            rx_done = 1'b0;
            repeat (2) @(negedge clk);
        end
    endtask

    task automatic send_n32_frame;
        input bad_checksum;
        input bad_tail;
        integer i;
        reg [7:0] sum;
        reg [11:0] ph;
        reg [7:0] amp;
        begin
            sum = 8'h01;
            send_byte(8'hAA);
            send_byte(8'hBB);
            send_byte(8'h01);
            for (i = 0; i < 32; i = i + 1) begin
                amp = i + 8'd1;
                sum = sum + amp;
                send_byte(amp);
            end
            for (i = 0; i < 32; i = i + 1) begin
                ph = (i * 77) & 12'hFFF;
                sum = sum + ph[7:0];
                send_byte(ph[7:0]);
                sum = sum + {4'd0, ph[11:8]};
                send_byte({4'd0, ph[11:8]});
            end
            send_byte(bad_checksum ? (sum ^ 8'h55) : sum);
            send_byte(bad_tail ? 8'h00 : 8'h0D);
            send_byte(8'h0A);
        end
    endtask

    task automatic send_debug_frame;
        input bad_checksum;
        input bad_tail;
        integer i;
        reg [7:0] sum;
        reg [7:0] payload [0:27];
        begin
            payload[0] = 8'd1;
            payload[1] = 8'd1;
            payload[2] = 8'h1F;
            payload[3] = 8'h00; payload[4] = 8'h02;
            payload[5] = 8'd2;
            payload[6] = 8'h00; payload[7] = 8'h40;
            payload[8] = 8'h80; payload[9] = 8'h00;
            payload[10] = 8'hCE; payload[11] = 8'hFF;
            payload[12] = 8'hCD; payload[13] = 8'hCC; payload[14] = 8'h00; payload[15] = 8'h00;
            payload[16] = 8'h00; payload[17] = 8'h20;
            payload[18] = 8'hE8; payload[19] = 8'h03;
            payload[20] = 8'h0F; payload[21] = 8'h00; payload[22] = 8'h00; payload[23] = 8'h00;
            payload[24] = 8'h00; payload[25] = 8'h00; payload[26] = 8'h00; payload[27] = 8'h80;

            sum = 8'h02;
            send_byte(8'hAA);
            send_byte(8'hBB);
            send_byte(8'h02);
            for (i = 0; i < 28; i = i + 1) begin
                sum = sum + payload[i];
                send_byte(payload[i]);
            end
            send_byte(bad_checksum ? (sum ^ 8'h55) : sum);
            send_byte(bad_tail ? 8'h00 : 8'h0D);
            send_byte(8'h0A);
        end
    endtask

    task automatic send_partial_frame;
        integer i;
        begin
            send_byte(8'hAA);
            send_byte(8'hBB);
            send_byte(8'h01);
            for (i = 0; i < 5; i = i + 1)
                send_byte(i[7:0]);
        end
    endtask

    task automatic send_mod_debug_frame;
        input bad_checksum;
        input bad_tail;
        integer i;
        reg [7:0] sum;
        reg [7:0] payload [0:35];
        begin
            payload[0] = 8'd1;
            payload[1] = 8'd1;
            payload[2] = 8'h17; payload[3] = 8'h00;
            payload[4] = 8'd1;
            payload[5] = 8'd4;
            payload[6] = 8'd0;
            payload[7] = 8'd3;
            payload[8] = 8'h00; payload[9] = 8'h02;
            payload[10] = 8'd2;
            payload[11] = 8'h34; payload[12] = 8'h12;
            payload[13] = 8'hC9; payload[14] = 8'hFF;
            payload[15] = 8'hCD; payload[16] = 8'h4C;
            payload[17] = 8'h80; payload[18] = 8'h01;
            payload[19] = 8'h04; payload[20] = 8'h03; payload[21] = 8'h02; payload[22] = 8'h01;
            payload[23] = 8'h00; payload[24] = 8'h20;
            payload[25] = 8'hE8; payload[26] = 8'h03;
            payload[27] = 8'hEF; payload[28] = 8'hCD; payload[29] = 8'hAB; payload[30] = 8'h89;
            payload[31] = 8'h67; payload[32] = 8'h45; payload[33] = 8'h23; payload[34] = 8'h01;
            payload[35] = 8'd0;

            sum = 8'h04;
            send_byte(8'hAA);
            send_byte(8'hBB);
            send_byte(8'h04);
            for (i = 0; i < 36; i = i + 1) begin
                sum = sum + payload[i];
                send_byte(payload[i]);
            end
            send_byte(bad_checksum ? (sum ^ 8'h55) : sum);
            send_byte(bad_tail ? 8'h00 : 8'h0D);
            send_byte(8'h0A);
        end
    endtask

    initial begin
        $dumpfile("tb_uart_protocol_parser.vcd");
        $dumpvars(0, tb_uart_protocol_parser);

        pass_cnt = 0;
        error_cnt = 0;
        rx_data = 8'd0;
        rx_done = 1'b0;
        rst_n = 1'b0;
        repeat (5) @(posedge clk);
        rst_n = 1'b1;
        repeat (3) @(posedge clk);

        check(dut.o_amplitude[0] == 8'd255, "reset default amplitude is full scale");
        check(dut.o_phase[0] == 12'd0, "reset default phase is zero");
        check(debug_flags == 8'h09, "reset debug flags enable output and ROM mapping");
        check(gain_q8 == 16'd256, "reset debug gain is unity Q8");
        check(modulation_mode == 8'd4, "reset modulation mode is MAM1");
        check(mod_index_q15 == 16'd19661, "reset modulation index is 0.6 Q15");

        send_n32_frame(1'b0, 1'b0);
        repeat (5) @(posedge clk);
        check(update_count == 1, "valid N32 frame produces one update pulse");
        for (ch = 0; ch < 32; ch = ch + 1) begin
            check(dut.o_amplitude[ch] == ch + 1, "amplitude matches payload");
            check(dut.o_phase[ch] == ((ch * 77) & 12'hFFF), "phase matches payload");
        end

        send_n32_frame(1'b1, 1'b0);
        repeat (5) @(posedge clk);
        check(update_count == 1, "bad checksum does not update");

        send_n32_frame(1'b0, 1'b1);
        repeat (5) @(posedge clk);
        check(update_count == 1, "bad tail does not update");

        send_debug_frame(1'b0, 1'b0);
        repeat (5) @(posedge clk);
        check(debug_update_count == 1, "valid debug frame produces one update pulse");
        check(debug_version == 8'd1, "debug version matches payload");
        check(array_profile == 8'd1, "array profile reserves 5x12 value");
        check(debug_flags == 8'h1F, "debug flags match payload");
        check(gain_q8 == 16'd512, "debug gain matches payload");
        check(limiter_mode == 8'd2, "limiter mode matches payload");
        check(limiter_threshold == 16'sd16384, "limiter threshold matches payload");
        check(audio_depth_q8 == 16'd128, "audio depth matches payload");
        check(dc_offset == -16'sd50, "dc offset matches payload");
        check(test_ftw == 32'h0000CCCD, "test FTW matches payload");
        check(test_amp == 16'd8192, "test amplitude matches payload");
        check(max_duty == 12'd1000, "max duty matches payload");
        check(output_mask == 64'h800000000000000F, "output mask matches payload");
        check(modulation_mode == 8'd0, "legacy debug maps to legacy modulation");

        send_debug_frame(1'b1, 1'b0);
        repeat (5) @(posedge clk);
        check(debug_update_count == 1, "bad debug checksum does not update");

        send_debug_frame(1'b0, 1'b1);
        repeat (5) @(posedge clk);
        check(debug_update_count == 1, "bad debug tail does not update");

        send_mod_debug_frame(1'b0, 1'b0);
        repeat (5) @(posedge clk);
        check(mod_update_count == 2, "valid mod/debug frame produces one update pulse after legacy debug");
        check(mod_version == 8'd1, "mod version matches payload");
        check(mod_array_profile == 8'd1, "mod array profile matches payload");
        check(mod_flags == 16'h0017, "mod flags match payload");
        check(mod_source_select == 8'd1, "mod source matches payload");
        check(modulation_mode == 8'd4, "MAM1 modulation mode matches payload");
        check(debug_probe_select == 8'd3, "debug probe matches payload");
        check(input_gain_q8 == 16'd512, "input gain matches payload");
        check(mod_limiter_mode == 8'd2, "mod limiter mode matches payload");
        check(mod_limiter_threshold == 16'sh1234, "mod limiter threshold matches payload");
        check(mod_dc_offset == -16'sd55, "mod dc offset matches payload");
        check(mod_index_q15 == 16'h4CCD, "mod index matches payload");
        check(envelope_scale_q8 == 16'd384, "envelope scale matches payload");
        check(mod_test_ftw == 32'h01020304, "mod test FTW matches payload");
        check(mod_test_amp == 16'd8192, "mod test amp matches payload");
        check(mod_max_duty == 12'd1000, "mod max duty matches payload");
        check(mod_output_mask == 64'h0123456789ABCDEF, "mod output mask matches payload");

        send_mod_debug_frame(1'b1, 1'b0);
        repeat (5) @(posedge clk);
        check(mod_update_count == 2, "bad mod checksum does not update");

        send_mod_debug_frame(1'b0, 1'b1);
        repeat (5) @(posedge clk);
        check(mod_update_count == 2, "bad mod tail does not update");

        rst_n = 1'b0;
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        repeat (3) @(posedge clk);
        send_partial_frame();
        repeat (20) @(posedge clk);
        check(update_count == 0, "short packet does not update");

        $display("Simulation summary: passes=%0d errors=%0d", pass_cnt, error_cnt);
        if (error_cnt == 0)
            $display("RESULT: ALL TESTS PASSED");
        else
            $display("RESULT: %0d CHECK(S) FAILED", error_cnt);
        $finish;
    end

    initial begin
        #2000000;
        $display("[FAIL] simulation timeout");
        $finish;
    end
endmodule
