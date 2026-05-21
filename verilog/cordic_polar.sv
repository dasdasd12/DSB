`timescale 1ns / 1ps

module cordic_polar (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               sample_valid,
    input  logic signed [31:0] i_q15,
    input  logic signed [31:0] q_q15,
    input  logic [31:0]        norm_q15,
    output logic [11:0]        envelope_q12,
    output logic [11:0]        phase_ticks,
    output logic               out_valid
);

    localparam [11:0] PWM_PERIOD = 12'd2500;
    localparam [11:0] QUADRANT_TICKS = 12'd625;
    localparam [11:0] OCTANT_TICKS = 12'd313;

    function automatic [31:0] abs32(input signed [31:0] value);
        begin
            abs32 = value[31] ? -value : value;
        end
    endfunction

    logic [31:0] abs_i;
    logic [31:0] abs_q;
    logic [31:0] max_v;
    logic [31:0] min_v;
    logic [31:0] env_approx;
    logic [63:0] env_scaled;
    logic [31:0] ratio_q15;
    logic [31:0] angle_oct;
    logic [31:0] angle_quad;
    logic signed [31:0] phase_signed;

    always_comb begin
        abs_i = abs32(i_q15);
        abs_q = abs32(q_q15);
        max_v = (abs_i >= abs_q) ? abs_i : abs_q;
        min_v = (abs_i >= abs_q) ? abs_q : abs_i;
        env_approx = max_v + (min_v >> 2) + (min_v >> 3);
        env_scaled = (norm_q15 == 32'd0) ? 64'd0 : (({32'd0, env_approx} * 64'd4095) / {32'd0, norm_q15});
        ratio_q15 = (max_v == 32'd0) ? 32'd0 : ((min_v << 15) / max_v);
        angle_oct = (ratio_q15 * OCTANT_TICKS) >> 15;
        angle_quad = (abs_q > abs_i) ? (QUADRANT_TICKS - angle_oct) : angle_oct;

        if (!i_q15[31] && !q_q15[31])
            phase_signed = angle_quad;
        else if (i_q15[31] && !q_q15[31])
            phase_signed = QUADRANT_TICKS + (QUADRANT_TICKS - angle_quad);
        else if (i_q15[31] && q_q15[31])
            phase_signed = 32'd1250 + angle_quad;
        else
            phase_signed = 32'd2500 - angle_quad;
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            envelope_q12 <= 12'd0;
            phase_ticks <= 12'd0;
            out_valid <= 1'b0;
        end else begin
            out_valid <= 1'b0;
            if (sample_valid) begin
                envelope_q12 <= (env_scaled > 64'd4095) ? 12'd4095 : env_scaled[11:0];
                if (phase_signed >= PWM_PERIOD)
                    phase_ticks <= phase_signed - PWM_PERIOD;
                else if (phase_signed < 0)
                    phase_ticks <= phase_signed + PWM_PERIOD;
                else
                    phase_ticks <= phase_signed[11:0];
                out_valid <= 1'b1;
            end
        end
    end
endmodule
