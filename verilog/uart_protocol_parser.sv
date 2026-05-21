`timescale 1ns / 1ps

module uart_protocol_parser (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [7:0]  rx_data,
    input  logic        rx_done,

    output logic [7:0]  o_amplitude [0:31],
    output logic [11:0] o_phase     [0:31],
    output logic        o_update_pulse,

    output logic [7:0]  o_debug_version,
    output logic [7:0]  o_array_profile,
    output logic [7:0]  o_debug_flags,
    output logic [15:0] o_gain_q8,
    output logic [7:0]  o_limiter_mode,
    output logic signed [15:0] o_limiter_threshold,
    output logic [15:0] o_audio_depth_q8,
    output logic signed [15:0] o_dc_offset,
    output logic [31:0] o_test_ftw,
    output logic [15:0] o_test_amp,
    output logic [11:0] o_max_duty,
    output logic [63:0] o_output_mask,
    output logic        o_debug_update_pulse,

    output logic [7:0]  o_mod_version,
    output logic [7:0]  o_mod_array_profile,
    output logic [15:0] o_mod_flags,
    output logic [7:0]  o_mod_source_select,
    output logic [7:0]  o_modulation_mode,
    output logic [7:0]  o_mod_sideband,
    output logic [7:0]  o_debug_probe_select,
    output logic [15:0] o_input_gain_q8,
    output logic [7:0]  o_mod_limiter_mode,
    output logic signed [15:0] o_mod_limiter_threshold,
    output logic signed [15:0] o_mod_dc_offset,
    output logic [15:0] o_mod_index_q15,
    output logic [15:0] o_envelope_scale_q8,
    output logic [31:0] o_mod_test_ftw,
    output logic [15:0] o_mod_test_amp,
    output logic [11:0] o_mod_max_duty,
    output logic [63:0] o_mod_output_mask,
    output logic        o_mod_update_pulse
);

    localparam int DEBUG_PAYLOAD_BYTES = 28;
    localparam int MOD_PAYLOAD_BYTES = 36;

    typedef enum logic [3:0] {
        S_IDLE,
        S_HEAD2,
        S_CMD,
        S_AMP,
        S_PHASE_L,
        S_PHASE_H,
        S_DEBUG,
        S_MOD_DEBUG,
        S_CHECKSUM,
        S_TAIL1,
        S_TAIL2
    } state_t;

    state_t state;
    logic [7:0] current_cmd;
    logic [5:0] byte_cnt;
    logic [7:0] calc_sum;
    logic [7:0] temp_phase_l;
    logic [7:0] debug_payload [0:DEBUG_PAYLOAD_BYTES-1];
    logic [7:0] mod_payload [0:MOD_PAYLOAD_BYTES-1];
    integer reset_i;
    integer reset_j;
    integer reset_k;
    integer commit_i;

    logic [7:0]  shadow_amplitude [0:31];
    logic [11:0] shadow_phase     [0:31];

    task automatic set_debug_defaults;
        begin
            o_debug_version      <= 8'd1;
            o_array_profile      <= 8'd0;
            o_debug_flags        <= 8'h09; // output enable + ROM mapping, DDS source, edge aligned.
            o_gain_q8            <= 16'd256;
            o_limiter_mode       <= 8'd0;
            o_limiter_threshold  <= 16'sd32767;
            o_audio_depth_q8     <= 16'd256;
            o_dc_offset          <= 16'sd0;
            o_test_ftw           <= 32'd42950;
            o_test_amp           <= 16'd8192;
            o_max_duty           <= 12'd1250;
            o_output_mask        <= 64'h00000000FFFFFFFF;
        end
    endtask

    task automatic set_mod_defaults;
        begin
            o_mod_version           <= 8'd1;
            o_mod_array_profile     <= 8'd0;
            o_mod_flags             <= 16'h0005; // output enable + safe clamp.
            o_mod_source_select     <= 8'd0;
            o_modulation_mode       <= 8'd4;     // MAM1 default.
            o_mod_sideband          <= 8'd0;
            o_debug_probe_select    <= 8'd0;
            o_input_gain_q8         <= 16'd256;
            o_mod_limiter_mode      <= 8'd0;
            o_mod_limiter_threshold <= 16'sd32767;
            o_mod_dc_offset         <= 16'sd0;
            o_mod_index_q15         <= 16'd19661;
            o_envelope_scale_q8     <= 16'd256;
            o_mod_test_ftw          <= 32'd42950;
            o_mod_test_amp          <= 16'd8192;
            o_mod_max_duty          <= 12'd1250;
            o_mod_output_mask       <= 64'h00000000FFFFFFFF;
        end
    endtask

    task automatic commit_debug_payload;
        begin
            o_debug_version     <= debug_payload[0];
            o_array_profile     <= debug_payload[1];
            o_debug_flags       <= debug_payload[2];
            o_gain_q8           <= {debug_payload[4], debug_payload[3]};
            o_limiter_mode      <= debug_payload[5];
            o_limiter_threshold <= $signed({debug_payload[7], debug_payload[6]});
            o_audio_depth_q8    <= {debug_payload[9], debug_payload[8]};
            o_dc_offset         <= $signed({debug_payload[11], debug_payload[10]});
            o_test_ftw          <= {debug_payload[15], debug_payload[14], debug_payload[13], debug_payload[12]};
            o_test_amp          <= {debug_payload[17], debug_payload[16]};
            o_max_duty          <= {debug_payload[19][3:0], debug_payload[18]};
            o_output_mask       <= {
                debug_payload[27], debug_payload[26], debug_payload[25], debug_payload[24],
                debug_payload[23], debug_payload[22], debug_payload[21], debug_payload[20]
            };

            o_mod_version           <= debug_payload[0];
            o_mod_array_profile     <= debug_payload[1];
            o_mod_flags             <= {
                11'd0,
                1'b0,
                ~debug_payload[2][3],
                1'b1,
                debug_payload[2][2],
                debug_payload[2][0]
            };
            o_mod_source_select     <= {7'd0, debug_payload[2][1]};
            o_modulation_mode       <= 8'd0;
            o_mod_sideband          <= 8'd0;
            o_debug_probe_select    <= 8'd0;
            o_input_gain_q8         <= {debug_payload[4], debug_payload[3]};
            o_mod_limiter_mode      <= debug_payload[5];
            o_mod_limiter_threshold <= $signed({debug_payload[7], debug_payload[6]});
            o_mod_dc_offset         <= $signed({debug_payload[11], debug_payload[10]});
            o_mod_index_q15         <= 16'd22938;
            o_envelope_scale_q8     <= {debug_payload[9], debug_payload[8]};
            o_mod_test_ftw          <= {debug_payload[15], debug_payload[14], debug_payload[13], debug_payload[12]};
            o_mod_test_amp          <= {debug_payload[17], debug_payload[16]};
            o_mod_max_duty          <= {debug_payload[19][3:0], debug_payload[18]};
            o_mod_output_mask       <= {
                debug_payload[27], debug_payload[26], debug_payload[25], debug_payload[24],
                debug_payload[23], debug_payload[22], debug_payload[21], debug_payload[20]
            };
        end
    endtask

    task automatic commit_mod_payload;
        begin
            o_mod_version           <= mod_payload[0];
            o_mod_array_profile     <= mod_payload[1];
            o_mod_flags             <= {mod_payload[3], mod_payload[2]};
            o_mod_source_select     <= mod_payload[4];
            o_modulation_mode       <= mod_payload[5];
            o_mod_sideband          <= mod_payload[6];
            o_debug_probe_select    <= mod_payload[7];
            o_input_gain_q8         <= {mod_payload[9], mod_payload[8]};
            o_mod_limiter_mode      <= mod_payload[10];
            o_mod_limiter_threshold <= $signed({mod_payload[12], mod_payload[11]});
            o_mod_dc_offset         <= $signed({mod_payload[14], mod_payload[13]});
            o_mod_index_q15         <= {mod_payload[16], mod_payload[15]};
            o_envelope_scale_q8     <= {mod_payload[18], mod_payload[17]};
            o_mod_test_ftw          <= {mod_payload[22], mod_payload[21], mod_payload[20], mod_payload[19]};
            o_mod_test_amp          <= {mod_payload[24], mod_payload[23]};
            o_mod_max_duty          <= {mod_payload[26][3:0], mod_payload[25]};
            o_mod_output_mask       <= {
                mod_payload[34], mod_payload[33], mod_payload[32], mod_payload[31],
                mod_payload[30], mod_payload[29], mod_payload[28], mod_payload[27]
            };
        end
    endtask

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_IDLE;
            current_cmd <= 8'd0;
            byte_cnt <= '0;
            calc_sum <= 8'd0;
            temp_phase_l <= 8'd0;
            o_update_pulse <= 1'b0;
            o_debug_update_pulse <= 1'b0;
            o_mod_update_pulse <= 1'b0;
            set_debug_defaults();
            set_mod_defaults();

            for (reset_i = 0; reset_i < 32; reset_i = reset_i + 1) begin
                o_amplitude[reset_i] <= 8'd255;
                o_phase[reset_i]     <= 12'd0;
                shadow_amplitude[reset_i] <= 8'd255;
                shadow_phase[reset_i] <= 12'd0;
            end
            for (reset_j = 0; reset_j < DEBUG_PAYLOAD_BYTES; reset_j = reset_j + 1) begin
                debug_payload[reset_j] <= 8'd0;
            end
            for (reset_k = 0; reset_k < MOD_PAYLOAD_BYTES; reset_k = reset_k + 1) begin
                mod_payload[reset_k] <= 8'd0;
            end
        end else begin
            o_update_pulse <= 1'b0;
            o_debug_update_pulse <= 1'b0;
            o_mod_update_pulse <= 1'b0;

            if (rx_done) begin
                case (state)
                    S_IDLE: begin
                        if (rx_data == 8'hAA)
                            state <= S_HEAD2;
                    end

                    S_HEAD2: begin
                        if (rx_data == 8'hBB)
                            state <= S_CMD;
                        else
                            state <= S_IDLE;
                    end

                    S_CMD: begin
                        current_cmd <= rx_data;
                        calc_sum <= rx_data;
                        byte_cnt <= '0;
                        if (rx_data == 8'h01)
                            state <= S_AMP;
                        else if (rx_data == 8'h02)
                            state <= S_DEBUG;
                        else if (rx_data == 8'h04)
                            state <= S_MOD_DEBUG;
                        else
                            state <= S_IDLE;
                    end

                    S_AMP: begin
                        calc_sum <= calc_sum + rx_data;
                        shadow_amplitude[byte_cnt] <= rx_data;
                        if (byte_cnt == 6'd31) begin
                            byte_cnt <= '0;
                            state <= S_PHASE_L;
                        end else begin
                            byte_cnt <= byte_cnt + 1'b1;
                        end
                    end

                    S_PHASE_L: begin
                        calc_sum <= calc_sum + rx_data;
                        temp_phase_l <= rx_data;
                        state <= S_PHASE_H;
                    end

                    S_PHASE_H: begin
                        calc_sum <= calc_sum + rx_data;
                        shadow_phase[byte_cnt] <= {rx_data[3:0], temp_phase_l};
                        if (byte_cnt == 6'd31) begin
                            state <= S_CHECKSUM;
                        end else begin
                            byte_cnt <= byte_cnt + 1'b1;
                            state <= S_PHASE_L;
                        end
                    end

                    S_DEBUG: begin
                        calc_sum <= calc_sum + rx_data;
                        debug_payload[byte_cnt] <= rx_data;
                        if (byte_cnt == DEBUG_PAYLOAD_BYTES - 1)
                            state <= S_CHECKSUM;
                        else
                            byte_cnt <= byte_cnt + 1'b1;
                    end

                    S_MOD_DEBUG: begin
                        calc_sum <= calc_sum + rx_data;
                        mod_payload[byte_cnt] <= rx_data;
                        if (byte_cnt == MOD_PAYLOAD_BYTES - 1)
                            state <= S_CHECKSUM;
                        else
                            byte_cnt <= byte_cnt + 1'b1;
                    end

                    S_CHECKSUM: begin
                        if (rx_data == calc_sum)
                            state <= S_TAIL1;
                        else
                            state <= S_IDLE;
                    end

                    S_TAIL1: begin
                        if (rx_data == 8'h0D)
                            state <= S_TAIL2;
                        else
                            state <= S_IDLE;
                    end

                    S_TAIL2: begin
                        if (rx_data == 8'h0A) begin
                            if (current_cmd == 8'h01) begin
                                for (commit_i = 0; commit_i < 32; commit_i = commit_i + 1) begin
                                    o_amplitude[commit_i] <= shadow_amplitude[commit_i];
                                    o_phase[commit_i] <= shadow_phase[commit_i];
                                end
                                o_update_pulse <= 1'b1;
                            end else if (current_cmd == 8'h02) begin
                                commit_debug_payload();
                                o_debug_update_pulse <= 1'b1;
                                o_mod_update_pulse <= 1'b1;
                            end else if (current_cmd == 8'h04) begin
                                commit_mod_payload();
                                o_mod_update_pulse <= 1'b1;
                            end
                        end
                        state <= S_IDLE;
                    end

                    default: state <= S_IDLE;
                endcase
            end
        end
    end
endmodule
