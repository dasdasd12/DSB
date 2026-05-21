`timescale 1ns / 1ps

module pwm32_generator (
    input  logic               clk,
    input  logic               rst_n,
    input  logic signed [15:0] audio_in,
    input  logic [7:0]         amplitude [0:31],
    input  logic [11:0]        phase_del [0:31],
    input  logic               output_enable,
    input  logic               center_align,
    input  logic               use_rom_mapping,
    input  logic [11:0]        max_duty,
    input  logic               use_external_duty,
    input  logic [11:0]        global_duty_base,
    input  logic [11:0]        global_phase_offset,
    input  logic [31:0]        output_mask,
    output logic [31:0]        pwm_out
);

    localparam [11:0] PWM_PERIOD = 12'd2500;
    localparam [11:0] DUTY_LIMIT = 12'd1250;

    logic [11:0] carrier_cnt;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            carrier_cnt <= 12'd0;
        else if (carrier_cnt == PWM_PERIOD - 1'b1)
            carrier_cnt <= 12'd0;
        else
            carrier_cnt <= carrier_cnt + 1'b1;
    end

    logic [15:0] rom_addr;
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            rom_addr <= 16'd0;
        else
            rom_addr <= audio_in + 16'd32768;
    end

    logic [11:0] rom_duty_d2;
    sqrt_mapping_rom u_math_rom (
        .clka  (clk),
        .addra (rom_addr),
        .ena   (1'b1),
        .douta (rom_duty_d2)
    );

    logic [11:0] effective_max_duty;
    logic [11:0] duty_base_d2;
    always_comb begin
        effective_max_duty = (max_duty > DUTY_LIMIT) ? DUTY_LIMIT : max_duty;
        if (use_external_duty)
            duty_base_d2 = (global_duty_base > effective_max_duty) ? effective_max_duty : global_duty_base;
        else if (use_rom_mapping)
            duty_base_d2 = (rom_duty_d2 > effective_max_duty) ? effective_max_duty : rom_duty_d2;
        else
            duty_base_d2 = effective_max_duty;
    end

    function automatic [11:0] wrap_tick(input signed [13:0] value);
        logic signed [13:0] adjusted;
        begin
            adjusted = value;
            if (adjusted < 0)
                adjusted = adjusted + {2'b0, PWM_PERIOD};
            else if (adjusted >= {2'b0, PWM_PERIOD})
                adjusted = adjusted - {2'b0, PWM_PERIOD};
            wrap_tick = adjusted[11:0];
        end
    endfunction

    genvar i;
    generate
        for (i = 0; i < 32; i++) begin : gen_ch
            logic [19:0] duty_ch_mult;
            assign duty_ch_mult = duty_base_d2 * {12'h0, amplitude[i]};

            logic [11:0] duty_ch_d3;
            logic [11:0] phase_d3;
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    duty_ch_d3 <= 12'd0;
                    phase_d3   <= 12'd0;
                end else begin
                    duty_ch_d3 <= duty_ch_mult[19:8];
                    phase_d3   <= ((phase_del[i] + global_phase_offset) >= PWM_PERIOD) ?
                                  (phase_del[i] + global_phase_offset - PWM_PERIOD) :
                                  (phase_del[i] + global_phase_offset);
                end
            end

            logic [11:0] duty_ch_d4;
            logic [11:0] start_d4;
            logic [12:0] end_raw_d4;
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    duty_ch_d4  <= 12'd0;
                    start_d4    <= 12'd0;
                    end_raw_d4  <= 13'd0;
                end else begin
                    duty_ch_d4 <= duty_ch_d3;
                    if (center_align)
                        start_d4 <= wrap_tick($signed({2'b0, phase_d3}) - $signed({2'b0, (duty_ch_d3 >> 1)}));
                    else
                        start_d4 <= phase_d3;
                    end_raw_d4 <= {1'b0, (center_align ? wrap_tick($signed({2'b0, phase_d3}) - $signed({2'b0, (duty_ch_d3 >> 1)})) : phase_d3)} + duty_ch_d3;
                end
            end

            logic [11:0] duty_locked;
            logic [11:0] start_locked;
            logic [11:0] end_locked;
            logic        wrap_locked;
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    duty_locked  <= 12'd0;
                    start_locked <= 12'd0;
                    end_locked   <= 12'd0;
                    wrap_locked  <= 1'b0;
                end else if (carrier_cnt == PWM_PERIOD - 1'b1) begin
                    duty_locked  <= duty_ch_d4;
                    start_locked <= start_d4;
                    end_locked   <= (end_raw_d4 >= {1'b0, PWM_PERIOD}) ? (end_raw_d4 - {1'b0, PWM_PERIOD}) : end_raw_d4[11:0];
                    wrap_locked  <= (end_raw_d4 >= {1'b0, PWM_PERIOD});
                end
            end

            logic pwm_active;
            assign pwm_active = (duty_locked == 12'd0) ? 1'b0 :
                                (!wrap_locked) ? (carrier_cnt >= start_locked && carrier_cnt < end_locked) :
                                                 (carrier_cnt >= start_locked || carrier_cnt < end_locked);
            assign pwm_out[i] = output_enable && output_mask[i] && pwm_active;
        end
    endgenerate
endmodule
