`timescale 1ns / 1ps

module audio_iq_modulator (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               sample_valid,
    input  logic signed [15:0] audio_sample,
    input  logic signed [15:0] hilbert_sample,
    input  logic [7:0]         modulation_mode,
    input  logic [7:0]         sideband,
    input  logic [15:0]        mod_index_q15,
    output logic signed [31:0] i_q15,
    output logic signed [31:0] q_q15,
    output logic [31:0]        norm_q15,
    output logic               out_valid
);

    localparam signed [31:0] UNITY_Q15 = 32'sd32768;

    logic signed [31:0] mx_q15;
    logic signed [31:0] mh_q15;
    logic signed [63:0] mx_sq_q30;
    logic signed [31:0] mam_q_q15;
    logic [31:0] norm_dsb;
    logic [31:0] norm_ssb;
    logic [31:0] norm_mam;

    always_comb begin
        mx_q15 = ($signed(audio_sample) * $signed({1'b0, mod_index_q15})) >>> 15;
        mh_q15 = ($signed(hilbert_sample) * $signed({1'b0, mod_index_q15})) >>> 15;
        mx_sq_q30 = mx_q15 * mx_q15;
        mam_q_q15 = UNITY_Q15 - ((mx_sq_q30 >>> 15) >>> 1);
        norm_dsb = UNITY_Q15 + {16'd0, mod_index_q15};
        norm_ssb = UNITY_Q15 + {16'd0, mod_index_q15} + ({16'd0, mod_index_q15} >> 2);
        norm_mam = UNITY_Q15 + {16'd0, mod_index_q15} + (UNITY_Q15 >> 1);
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            i_q15 <= UNITY_Q15;
            q_q15 <= 32'sd0;
            norm_q15 <= UNITY_Q15;
            out_valid <= 1'b0;
        end else begin
            out_valid <= 1'b0;
            if (sample_valid) begin
                case (modulation_mode)
                    8'd1: begin // DSB-AM
                        i_q15 <= UNITY_Q15 + mx_q15;
                        q_q15 <= 32'sd0;
                        norm_q15 <= norm_dsb;
                    end
                    8'd2, 8'd3: begin // SSB USB/LSB
                        i_q15 <= UNITY_Q15 + mx_q15;
                        q_q15 <= (sideband == 8'd1 || modulation_mode == 8'd3) ? -mh_q15 : mh_q15;
                        norm_q15 <= norm_ssb;
                    end
                    8'd4: begin // MAM1
                        i_q15 <= UNITY_Q15 + mx_q15;
                        q_q15 <= mam_q_q15;
                        norm_q15 <= norm_mam;
                    end
                    default: begin // legacy/debug fallback
                        i_q15 <= UNITY_Q15 + mx_q15;
                        q_q15 <= 32'sd0;
                        norm_q15 <= norm_dsb;
                    end
                endcase
                out_valid <= 1'b1;
            end
        end
    end
endmodule
