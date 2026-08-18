function output_path = build_state_machine_dt()
%BUILD_STATE_MACHINE_DT Build a standalone state-machine-controlled DT.
%
% The original DT_enviroment.slx is copied and left unchanged.  The copy
% replaces the active external battery-power command with a deterministic
% local controller that has four operating states:
%
%   0 HOLD
%   1 CHARGE
%   2 BUS_SUPPORT
%   3 SAFE_LOCAL
%
% The existing source controller, electrical plant, battery, sensors, load
% profile, and averaged battery power interface are preserved.  UDP command
% and telemetry blocks are omitted from this standalone validation model;
% they remain unchanged in the original SLX for later integration.

this_dir = fileparts(mfilename('fullpath'));
source_path = fullfile(this_dir, 'DT_enviroment.slx');
output_path = fullfile(this_dir, 'DT_enviroment_state_machine.slx');

if ~isfile(source_path)
    error('Source model not found: %s', source_path);
end

[copied, copy_message] = copyfile(source_path, output_path, 'f');
if ~copied
    error('Could not copy source model: %s', copy_message);
end

[~, model_name] = fileparts(output_path);
load_system(output_path);
cleanup = onCleanup(@() close_if_loaded(model_name));

% This variant is intentionally standalone.  Remove the command receiver,
% observation sender, and their dedicated rate-transition/diagnostic blocks
% from the copied model.  The original SLX retains the complete UDP path.
remove_udp_integration(model_name);

controller_name = 'Battery Grid State Machine';
controller_path = [model_name '/' controller_name];

% Local signal taps.  These reuse the original model's global Goto tags and
% avoid disturbing any existing measurement or logging connections.
add_from(model_name, 'SM Vbus', 'V_bus', [-560 335 -455 365]);
add_from(model_name, 'SM SOC', 'soc_pct', [-560 380 -455 410]);
add_from(model_name, 'SM Load Current', 'I_load', [-560 425 -455 455]);
add_from(model_name, 'SM Source At Limit', 'Source_at_limit', ...
    [-560 470 -455 500]);

% These three constants form the future supervisory-intent interface.  They
% are deliberately independent of UDP/LLM control in this standalone model.
add_block('simulink/Sources/Constant', [model_name '/SM Charge Enable'], ...
    'Value', '1', ...
    'Position', [-560 525 -510 555]);
add_block('simulink/Sources/Constant', [model_name '/SM SOC Target Pct'], ...
    'Value', '40', ...
    'Position', [-560 570 -510 600]);
add_block('simulink/Sources/Constant', [model_name '/SM Charge Power Cap W'], ...
    'Value', '100', ...
    'Position', [-560 615 -510 645]);

% Explicitly cross from continuous plant signals into a 1 ms discrete
% controller task.  Stateful MATLAB Function blocks cannot safely inherit a
% continuous sample time.
add_rate_transition(model_name, 'SM RT Vbus', [-425 335 -385 365]);
add_rate_transition(model_name, 'SM RT SOC', [-425 380 -385 410]);
add_rate_transition(model_name, 'SM RT Load Current', [-425 425 -385 455]);
add_rate_transition(model_name, 'SM RT Source At Limit', [-425 470 -385 500]);
add_rate_transition(model_name, 'SM RT Charge Enable', [-425 525 -385 555]);
add_rate_transition(model_name, 'SM RT SOC Target', [-425 570 -385 600]);
add_rate_transition(model_name, 'SM RT Power Cap', [-425 615 -385 645]);

add_block('simulink/User-Defined Functions/MATLAB Function', controller_path, ...
    'Position', [-300 350 -30 625]);

rt = sfroot;
chart = rt.find('-isa', 'Stateflow.EMChart', 'Path', controller_path);
if isempty(chart)
    error('Could not locate generated MATLAB Function chart: %s', controller_path);
end

chart.Script = state_machine_script();

% Wire local measurements and the temporary supervisory constants through
% the discrete-rate boundary.
wire_through_rate_transition(model_name, 'SM Vbus', 'SM RT Vbus', ...
    controller_name, 1);
wire_through_rate_transition(model_name, 'SM SOC', 'SM RT SOC', ...
    controller_name, 2);
wire_through_rate_transition(model_name, 'SM Load Current', ...
    'SM RT Load Current', controller_name, 3);
wire_through_rate_transition(model_name, 'SM Source At Limit', ...
    'SM RT Source At Limit', controller_name, 4);
wire_through_rate_transition(model_name, 'SM Charge Enable', ...
    'SM RT Charge Enable', controller_name, 5);
wire_through_rate_transition(model_name, 'SM SOC Target Pct', ...
    'SM RT SOC Target', controller_name, 6);
wire_through_rate_transition(model_name, 'SM Charge Power Cap W', ...
    'SM RT Power Cap', controller_name, 7);

% Replace only the active Pbat_cmd_w source.  The existing Goto block feeds
% the original averaged battery power interface inside Subsystem4.
old_command_line = get_param([model_name '/Goto1'], 'LineHandles');
if old_command_line.Inport ~= -1
    delete_line(old_command_line.Inport);
end
add_line(model_name, [controller_name '/1'], 'Goto1/1', 'autorouting', 'on');

% Log all controller outputs in one structure-with-time variable.  Columns:
% [P_ref, state, charge_headroom, nominal_load, voltage_error,
%  Vbus, SOC, source_at_limit]
add_block('simulink/Signal Routing/Mux', [model_name '/SM Controller Log Mux'], ...
    'Inputs', '8', ...
    'Position', [45 370 75 590]);
for output_index = 1:8
    add_line(model_name, ...
        sprintf('%s/%d', controller_name, output_index), ...
        sprintf('SM Controller Log Mux/%d', output_index), ...
        'autorouting', 'on');
end

add_block('simulink/Sinks/To Workspace', [model_name '/SM Controller Log'], ...
    'VariableName', 'SM_Controller', ...
    'SaveFormat', 'StructureWithTime', ...
    'MaxDataPoints', 'inf', ...
    'Position', [135 445 265 485]);
add_line(model_name, 'SM Controller Log Mux/1', 'SM Controller Log/1', ...
    'autorouting', 'on');

add_block('simulink/Sinks/Display', [model_name '/SM Active State'], ...
    'Position', [135 515 215 545]);
add_line(model_name, [controller_name '/2'], 'SM Active State/1', ...
    'autorouting', 'on');

annotation_text = sprintf([ ...
    'Standalone battery grid controller\n' ...
    'State 0: HOLD | 1: CHARGE | 2: BUS SUPPORT | 3: SAFE LOCAL\n' ...
    'The state machine selects an operating mode; continuous logic inside\n' ...
    'CHARGE and BUS SUPPORT calculates the battery power reference.\n' ...
    'SM Charge Enable, SOC Target, and Power Cap are the future LLM intent ports.\n' ...
    'UDP/LLM blocks are omitted from this standalone validation model.']);
annotation = Simulink.Annotation(model_name, annotation_text);
annotation.Position = [-560 690 -20 810];

% A 120 s run demonstrates both the initial charging state and the 50 s and
% 100 s load transitions.  Pacing is disabled so standalone tests complete
% quickly; it can be re-enabled interactively for real-time viewing.
set_param(model_name, ...
    'StopTime', '120', ...
    'EnablePacing', 'off');

save_system(model_name, output_path);
fprintf('Created standalone state-machine model:\n  %s\n', output_path);

clear cleanup;
close_if_loaded(model_name);
end


function add_from(model_name, block_name, goto_tag, position)
add_block('simulink/Signal Routing/From', [model_name '/' block_name], ...
    'GotoTag', goto_tag, ...
    'Position', position);
end


function remove_udp_integration(model_name)
block_names = { ...
    'MATLAB System', ...
    'MATLAB System1', ...
    'Display', ...
    'Scope2', ...
    'Goto2', ...
    'Goto3', ...
    'Goto4', ...
    'Goto5', ...
    'Rate Transition', ...
    'Rate Transition1', ...
    'Rate Transition2', ...
    'Rate Transition3', ...
    'Rate Transition4', ...
    'Rate Transition5', ...
    'Rate Transition6', ...
    'Rate Transition7', ...
    'Rate Transition8', ...
    'Rate Transition9', ...
    'Rate Transition10', ...
    'Rate Transition11', ...
    'Rate Transition12', ...
    'Rate Transition13', ...
    'Rate Transition14'};

for index = 1:numel(block_names)
    block_path = [model_name '/' block_names{index}];
    if getSimulinkBlockHandle(block_path) ~= -1
        delete_block(block_path);
    end
end
end


function add_rate_transition(model_name, block_name, position)
add_block('simulink/Signal Attributes/Rate Transition', ...
    [model_name '/' block_name], ...
    'OutPortSampleTime', '1e-3', ...
    'Position', position);
end


function wire_through_rate_transition( ...
        model_name, source_name, rate_transition_name, controller_name, input_index)
add_line(model_name, [source_name '/1'], [rate_transition_name '/1'], ...
    'autorouting', 'on');
add_line(model_name, [rate_transition_name '/1'], ...
    sprintf('%s/%d', controller_name, input_index), ...
    'autorouting', 'on');
end


function script = state_machine_script()
lines = {
    'function [P_batt_ref_w, state_code, charge_headroom_w, p_load_nominal_w, voltage_error_v, vbus_log_v, soc_log_pct, source_at_limit_log] = fcn(Vbus_v, soc_pct, i_load_a, source_at_limit, charge_enable, soc_target_pct, charge_power_cap_w)'
    '%#codegen'
    '% Deterministic hybrid battery/grid controller.'
    '% Positive P_batt_ref_w discharges into the DC bus.'
    '% Negative P_batt_ref_w charges the battery.'
    ''
    '% State codes.'
    'HOLD = uint8(0);'
    'CHARGE = uint8(1);'
    'BUS_SUPPORT = uint8(2);'
    'SAFE_LOCAL = uint8(3);'
    ''
    '% Plant and controller constants kept explicit for auditability.'
    'Ts = 1e-3;'
    'Vnom = 400.0;'
    'Vsupport_enter = 397.0;'
    'Vsupport_exit = 399.0;'
    'Vcharge_abort = 395.0;'
    'Psource_limit = 500.0;'
    'Psource_reserve = 25.0;'
    'Psource_allowed = Psource_limit - Psource_reserve;'
    'Pdis_max = 480.0;'
    'Pchg_max = 300.0;'
    'Kp_v = 5.0;'
    'Ki_v = 2.0;'
    'integral_max_v_s = 15.0;'
    ''
    'persistent state integral_v_s'
    'if isempty(state)'
    '    state = HOLD;'
    '    integral_v_s = 0.0;'
    'end'
    ''
    '% Use nominal-voltage load power so a voltage sag does not make the'
    '% load appear artificially smaller than the power needed at 400 V.'
    'p_load_nominal_w = Vnom * abs(i_load_a);'
    'charge_headroom_w = max(0.0, Psource_allowed - p_load_nominal_w);'
    'voltage_error_v = max(0.0, Vsupport_exit - Vbus_v);'
    ''
    'signals_valid = isfinite(Vbus_v) && isfinite(soc_pct) && isfinite(i_load_a);'
    'hard_fault = ~signals_valid || soc_pct <= 10.0 || soc_pct >= 95.0 || Vbus_v <= 250.0 || Vbus_v >= 500.0;'
    'support_requested = Vbus_v <= Vsupport_enter || source_at_limit >= 0.5 || p_load_nominal_w >= Psource_allowed;'
    'charge_support_requested = Vbus_v <= Vcharge_abort || source_at_limit >= 0.5 || p_load_nominal_w >= Psource_allowed;'
    'support_cleared = Vbus_v >= Vsupport_exit && source_at_limit < 0.5 && p_load_nominal_w <= (Psource_allowed - 10.0);'
    'charge_requested = charge_enable >= 0.5 && soc_pct < (soc_target_pct - 0.1);'
    'charge_entry_possible = charge_requested && charge_headroom_w > 1.0 && Vbus_v >= Vsupport_exit;'
    'charge_continue_possible = charge_requested && charge_headroom_w > 1.0 && Vbus_v > Vcharge_abort && source_at_limit < 0.5;'
    ''
    '% Deterministic transition arbitration.  Protection and bus support'
    '% always have more authority than the supervisory charge request.'
    'if hard_fault'
    '    state = SAFE_LOCAL;'
    'else'
    '    switch state'
    '        case SAFE_LOCAL'
    '            state = HOLD;'
    '        case HOLD'
    '            if support_requested'
    '                state = BUS_SUPPORT;'
    '            elseif charge_entry_possible'
    '                state = CHARGE;'
    '            end'
    '        case CHARGE'
    '            if charge_support_requested'
    '                state = BUS_SUPPORT;'
    '            elseif ~charge_continue_possible'
    '                state = HOLD;'
    '            end'
    '        case BUS_SUPPORT'
    '            if support_cleared'
    '                if charge_entry_possible'
    '                    state = CHARGE;'
    '                else'
    '                    state = HOLD;'
    '                end'
    '            end'
    '        otherwise'
    '            state = SAFE_LOCAL;'
    '    end'
    'end'
    ''
    '% Continuous command calculation inside the selected state.'
    'switch state'
    '    case CHARGE'
    '        integral_v_s = 0.0;'
    '        requested_charge_w = min(max(abs(charge_power_cap_w), 0.0), Pchg_max);'
    '        P_batt_ref_w = -min(requested_charge_w, charge_headroom_w);'
    '    case BUS_SUPPORT'
    '        p_deficit_w = max(0.0, p_load_nominal_w - Psource_allowed);'
    '        p_unsat_w = p_deficit_w + Kp_v * voltage_error_v + Ki_v * integral_v_s;'
    '        P_batt_ref_w = min(max(p_unsat_w, 0.0), Pdis_max);'
    '        if voltage_error_v > 0.0 && p_unsat_w < Pdis_max'
    '            integral_v_s = min(integral_v_s + voltage_error_v * Ts, integral_max_v_s);'
    '        elseif voltage_error_v <= 0.0'
    '            integral_v_s = max(0.0, integral_v_s - Ts);'
    '        end'
    '    otherwise'
    '        integral_v_s = 0.0;'
    '        P_batt_ref_w = 0.0;'
    'end'
    ''
    'state_code = double(state);'
    'vbus_log_v = Vbus_v;'
    'soc_log_pct = soc_pct;'
    'source_at_limit_log = double(source_at_limit >= 0.5);'
    'end'
    };
script = strjoin(lines, newline);
end


function close_if_loaded(model_name)
if bdIsLoaded(model_name)
    close_system(model_name, 0);
end
end
