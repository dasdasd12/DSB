`timescale 1ns / 1ps

module hilbert_fir (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               sample_valid,
    input  logic signed [15:0] sample_in,
    output logic signed [15:0] sample_delay,
    output logic signed [15:0] hilbert_out,
    output logic               out_valid
);

    logic signed [15:0] delay [0:62];
    logic signed [47:0] acc;
    integer i;

    function automatic signed [15:0] coeff(input [5:0] idx);
        begin
            case (idx)
            6'd0: coeff = -16'sd336;
            6'd1: coeff = 16'sd0;
            6'd2: coeff = -16'sd360;
            6'd3: coeff = 16'sd0;
            6'd4: coeff = -16'sd386;
            6'd5: coeff = 16'sd0;
            6'd6: coeff = -16'sd417;
            6'd7: coeff = 16'sd0;
            6'd8: coeff = -16'sd453;
            6'd9: coeff = 16'sd0;
            6'd10: coeff = -16'sd497;
            6'd11: coeff = 16'sd0;
            6'd12: coeff = -16'sd549;
            6'd13: coeff = 16'sd0;
            6'd14: coeff = -16'sd614;
            6'd15: coeff = 16'sd0;
            6'd16: coeff = -16'sd695;
            6'd17: coeff = 16'sd0;
            6'd18: coeff = -16'sd802;
            6'd19: coeff = 16'sd0;
            6'd20: coeff = -16'sd948;
            6'd21: coeff = 16'sd0;
            6'd22: coeff = -16'sd1159;
            6'd23: coeff = 16'sd0;
            6'd24: coeff = -16'sd1490;
            6'd25: coeff = 16'sd0;
            6'd26: coeff = -16'sd2086;
            6'd27: coeff = 16'sd0;
            6'd28: coeff = -16'sd3477;
            6'd29: coeff = 16'sd0;
            6'd30: coeff = -16'sd10430;
            6'd31: coeff = 16'sd0;
            6'd32: coeff = 16'sd10430;
            6'd33: coeff = 16'sd0;
            6'd34: coeff = 16'sd3477;
            6'd35: coeff = 16'sd0;
            6'd36: coeff = 16'sd2086;
            6'd37: coeff = 16'sd0;
            6'd38: coeff = 16'sd1490;
            6'd39: coeff = 16'sd0;
            6'd40: coeff = 16'sd1159;
            6'd41: coeff = 16'sd0;
            6'd42: coeff = 16'sd948;
            6'd43: coeff = 16'sd0;
            6'd44: coeff = 16'sd802;
            6'd45: coeff = 16'sd0;
            6'd46: coeff = 16'sd695;
            6'd47: coeff = 16'sd0;
            6'd48: coeff = 16'sd614;
            6'd49: coeff = 16'sd0;
            6'd50: coeff = 16'sd549;
            6'd51: coeff = 16'sd0;
            6'd52: coeff = 16'sd497;
            6'd53: coeff = 16'sd0;
            6'd54: coeff = 16'sd453;
            6'd55: coeff = 16'sd0;
            6'd56: coeff = 16'sd417;
            6'd57: coeff = 16'sd0;
            6'd58: coeff = 16'sd386;
            6'd59: coeff = 16'sd0;
            6'd60: coeff = 16'sd360;
            6'd61: coeff = 16'sd0;
            6'd62: coeff = 16'sd336;
            default: coeff = 16'sd0;
            endcase
        end
    endfunction

    function automatic signed [15:0] clamp16(input signed [47:0] value);
        begin
            if (value > 48'sd32767)
                clamp16 = 16'sd32767;
            else if (value < -48'sd32768)
                clamp16 = -16'sd32768;
            else
                clamp16 = value[15:0];
        end
    endfunction

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < 63; i = i + 1)
                delay[i] <= 16'sd0;
            sample_delay <= 16'sd0;
            hilbert_out <= 16'sd0;
            out_valid <= 1'b0;
        end else begin
            out_valid <= 1'b0;
            if (sample_valid) begin
                for (i = 62; i > 0; i = i - 1)
                    delay[i] <= delay[i-1];
                delay[0] <= sample_in;

                acc = 48'sd0;
                for (i = 0; i < 63; i = i + 1)
                    acc = acc + ($signed(delay[i]) * $signed(coeff(i[5:0])));

                sample_delay <= delay[31];
                hilbert_out <= clamp16(acc >>> 14);
                out_valid <= 1'b1;
            end
        end
    end
endmodule
