function paths = build_llm_udp_comparison_models()
%BUILD_LLM_UDP_COMPARISON_MODELS Create two new, matched experiment SLXs.
%
% Existing SLX files are only read.  The function creates:
%   DT_enviroment_state_machine_baseline_instrumented.slx
%   DT_enviroment_state_machine_llm_udp.slx

this_dir = fileparts(mfilename('fullpath'));
dt_dir = fileparts(this_dir);
addpath(this_dir, dt_dir);

source_path = fullfile(dt_dir, 'DT_enviroment_state_machine.slx');
baseline_path = fullfile( ...
    dt_dir, 'DT_enviroment_state_machine_baseline_instrumented.slx');
llm_path = fullfile(dt_dir, 'DT_enviroment_state_machine_llm_udp.slx');

if ~isfile(source_path)
    error('Standalone state-machine model not found: %s', source_path);
end

copy_model(source_path, baseline_path);
[~, baseline_name] = fileparts(baseline_path);
load_system(baseline_path);
baseline_cleanup = onCleanup(@() close_if_loaded(baseline_name));
add_experiment_log(baseline_name);
set_common_configuration(baseline_name, 120.0);
add_model_note(baseline_name, sprintf([ ...
    'Instrumented deterministic comparison model\n' ...
    'This is a copy; DT_enviroment_state_machine.slx is unchanged.\n' ...
    'The plant, state machine, scenario, and 1 ms controller are preserved.']));
save_system(baseline_name, baseline_path);
clear baseline_cleanup;
close_if_loaded(baseline_name);

copy_model(baseline_path, llm_path);
[~, llm_name] = fileparts(llm_path);
load_system(llm_path);
llm_cleanup = onCleanup(@() close_if_loaded(llm_name));

replace_constants_with_udp_intent(llm_name);
add_udp_observation_sender(llm_name);
set_common_configuration(llm_name, 120.5);
add_model_note(llm_name, sprintf([ ...
    'LLM/UDP supervisory comparison model\n' ...
    'UDP mode request -> guarded local state machine -> battery power interface\n' ...
    'Stale, disabled, or SAFE commands force state 3 (SAFE LOCAL).\n' ...
    'Physical bus support overrides a conflicting LLM request.']));
save_system(llm_name, llm_path);

clear llm_cleanup;
close_if_loaded(llm_name);

paths = struct( ...
    'source', source_path, ...
    'baseline', baseline_path, ...
    'llm_udp', llm_path);

fprintf('Created comparison models without changing existing SLX files:\n');
fprintf('  Baseline: %s\n', baseline_path);
fprintf('  LLM/UDP:  %s\n', llm_path);
end


function copy_model(source_path, output_path)
[copied, message] = copyfile(source_path, output_path, 'f');
if ~copied
    error('Could not create %s: %s', output_path, message);
end
end


function set_common_configuration(model_name, stop_time_s)
set_param(model_name, ...
    'StopTime', sprintf('%.3f', stop_time_s), ...
    'EnablePacing', 'on', ...
    'PacingRate', '1');
end


function add_experiment_log(model_name)
% One common log is added to both copied models. Columns:
% [Vbus, SOC, Ibatt, Pbatt, Pload, Psource, source_at_limit, Pbat_ref]
names = { ...
    'EXP Vbus', ...
    'EXP SOC', ...
    'EXP Ibatt', ...
    'EXP Pbatt', ...
    'EXP Pload', ...
    'EXP Psource', ...
    'EXP Source Limit', ...
    'EXP Pbat Ref'};
tags = { ...
    'V_bus', ...
    'soc_pct', ...
    'i_batt', ...
    'P_batt', ...
    'P_load', ...
    'P_source', ...
    'Source_at_limit', ...
    'Pbat_cmd_w'};

for index = 1:numel(names)
    y = 720 + (index - 1) * 42;
    add_block('simulink/Signal Routing/From', ...
        [model_name '/' names{index}], ...
        'GotoTag', tags{index}, ...
        'Position', [1760 y 1870 y + 24]);
end

add_block('simulink/Signal Routing/Mux', ...
    [model_name '/EXP Data Mux'], ...
    'Inputs', '8', ...
    'Position', [1930 720 1960 1035]);
for index = 1:numel(names)
    if index == 7
        add_block('simulink/Signal Attributes/Data Type Conversion', ...
            [model_name '/EXP Source Limit Double'], ...
            'OutDataTypeStr', 'double', ...
            'Position', [1880 970 1915 995]);
        add_line(model_name, [names{index} '/1'], ...
            'EXP Source Limit Double/1', 'autorouting', 'on');
        add_line(model_name, 'EXP Source Limit Double/1', ...
            sprintf('EXP Data Mux/%d', index), 'autorouting', 'on');
    else
        add_line(model_name, [names{index} '/1'], ...
            sprintf('EXP Data Mux/%d', index), 'autorouting', 'on');
    end
end

add_block('simulink/Sinks/To Workspace', ...
    [model_name '/EXP Data Log'], ...
    'VariableName', 'Experiment_Data', ...
    'SaveFormat', 'StructureWithTime', ...
    'MaxDataPoints', 'inf', ...
    'Position', [2030 850 2170 890]);
add_line(model_name, 'EXP Data Mux/1', 'EXP Data Log/1', 'autorouting', 'on');
end


function replace_constants_with_udp_intent(model_name)
controller_name = 'Battery Grid State Machine';
controller_path = [model_name '/' controller_name];

% Remove the three existing supervisory-input lines explicitly before their
% source blocks are deleted.  This also handles SLX versions that preserve a
% dangling line segment after deleting a Rate Transition block.
controller_lines = get_param(controller_path, 'LineHandles');
for input_index = 5:7
    if controller_lines.Inport(input_index) ~= -1
        delete_line(controller_lines.Inport(input_index));
    end
end

blocks_to_remove = { ...
    'SM Charge Enable', ...
    'SM SOC Target Pct', ...
    'SM Charge Power Cap W', ...
    'SM RT Charge Enable', ...
    'SM RT SOC Target', ...
    'SM RT Power Cap'};
for index = 1:numel(blocks_to_remove)
    block_path = [model_name '/' blocks_to_remove{index}];
    if getSimulinkBlockHandle(block_path) ~= -1
        delete_block(block_path);
    end
end

rt = sfroot;
chart = rt.find('-isa', 'Stateflow.EMChart', 'Path', controller_path);
if isempty(chart)
    error('Could not find controller chart in %s.', model_name);
end
chart.Script = llm_guarded_state_machine_script();

receiver_name = 'LLM UDP Supervisory Receiver';
receiver_path = [model_name '/' receiver_name];
add_block('simulink/User-Defined Functions/MATLAB System', receiver_path, ...
    'System', 'DTUdpStateMachineCommandReceiver', ...
    'Position', [-570 515 -335 665]);
set_param(receiver_path, ...
    'LocalPort', '55000', ...
    'SampleTimeS', '0.1', ...
    'MaxCommandAgeS', '15');

add_discrete_boundary(model_name, 'LLM RT Mode', [-300 520 -250 550]);
add_discrete_boundary(model_name, 'LLM RT Valid', [-300 565 -250 595]);
add_discrete_boundary(model_name, 'LLM RT Power', [-300 610 -250 640]);

add_line(model_name, [receiver_name '/1'], 'LLM RT Mode/1', 'autorouting', 'on');
add_line(model_name, 'LLM RT Mode/1', [controller_name '/5'], 'autorouting', 'on');
add_line(model_name, [receiver_name '/3'], 'LLM RT Valid/1', 'autorouting', 'on');
add_line(model_name, 'LLM RT Valid/1', [controller_name '/6'], 'autorouting', 'on');
add_line(model_name, [receiver_name '/2'], 'LLM RT Power/1', 'autorouting', 'on');
add_line(model_name, 'LLM RT Power/1', [controller_name '/7'], 'autorouting', 'on');

% Log the raw request separately from the state-machine output. Columns:
% [mode, requested_power, valid, seq, age, enforced_state]
add_block('simulink/Signal Routing/Mux', [model_name '/LLM UDP Log Mux'], ...
    'Inputs', '6', ...
    'Position', [315 560 345 760]);
for output_index = 1:5
    add_line(model_name, sprintf('%s/%d', receiver_name, output_index), ...
        sprintf('LLM UDP Log Mux/%d', output_index), 'autorouting', 'on');
end
add_line(model_name, [controller_name '/2'], 'LLM UDP Log Mux/6', ...
    'autorouting', 'on');
add_block('simulink/Sinks/To Workspace', [model_name '/LLM UDP Log'], ...
    'VariableName', 'LLM_UDP', ...
    'SaveFormat', 'StructureWithTime', ...
    'MaxDataPoints', 'inf', ...
    'Position', [405 635 520 675]);
add_line(model_name, 'LLM UDP Log Mux/1', 'LLM UDP Log/1', 'autorouting', 'on');
end


function add_udp_observation_sender(model_name)
sender_name = 'LLM UDP Observation Sender';
receiver_name = 'LLM UDP Supervisory Receiver';
controller_name = 'Battery Grid State Machine';

add_block('simulink/Sources/Clock', [model_name '/LLM Sim Clock'], ...
    'Position', [2250 650 2280 680]);

from_names = { ...
    'LLM OBS SOC', ...
    'LLM OBS Vbus', ...
    'LLM OBS Vbatt', ...
    'LLM OBS Ibatt', ...
    'LLM OBS Pbatt', ...
    'LLM OBS Pload', ...
    'LLM OBS Psource', ...
    'LLM OBS Source Limit'};
tags = { ...
    'soc_pct', ...
    'V_bus', ...
    'V_batt', ...
    'i_batt', ...
    'P_batt', ...
    'P_load', ...
    'P_source', ...
    'Source_at_limit'};
for index = 1:numel(from_names)
    y = 700 + (index - 1) * 40;
    add_block('simulink/Signal Routing/From', ...
        [model_name '/' from_names{index}], ...
        'GotoTag', tags{index}, ...
        'Position', [2220 y 2335 y + 24]);
end

add_block('simulink/Sources/Constant', [model_name '/LLM Source Available'], ...
    'Value', '1', ...
    'Position', [2265 1030 2315 1060]);

sender_path = [model_name '/' sender_name];
add_block('simulink/User-Defined Functions/MATLAB System', sender_path, ...
    'System', 'DTUdpStateMachineObservationSender', ...
    'Position', [2440 655 2740 1075]);
set_param(sender_path, ...
    'RemoteHost', '127.0.0.1', ...
    'RemotePort', '55001', ...
    'SampleTimeS', '0.1', ...
    'SourcePowerLimitW', '500', ...
    'MaxSafeChargeW', '300');

sources = { ...
    'LLM Sim Clock/1', ...
    'LLM OBS SOC/1', ...
    'LLM OBS Vbus/1', ...
    'LLM OBS Vbatt/1', ...
    'LLM OBS Ibatt/1', ...
    'LLM OBS Pbatt/1', ...
    'LLM OBS Pload/1', ...
    'LLM OBS Psource/1', ...
    'LLM OBS Source Limit/1', ...
    'LLM Source Available/1', ...
    [controller_name '/2'], ...
    [receiver_name '/4'], ...
    [receiver_name '/5']};
for input_index = 1:numel(sources)
    add_line(model_name, sources{input_index}, ...
        sprintf('%s/%d', sender_name, input_index), 'autorouting', 'on');
end

% Keep the sender in the executable graph.  An unconnected System-object
% output can be optimized away even though the block has the side effect of
% transmitting UDP telemetry.
add_block('simulink/Sinks/To Workspace', ...
    [model_name '/LLM Observation Sequence Log'], ...
    'VariableName', 'LLM_Observation_Seq', ...
    'SaveFormat', 'StructureWithTime', ...
    'MaxDataPoints', 'inf', ...
    'Position', [2800 820 2965 860]);
add_line(model_name, [sender_name '/1'], ...
    'LLM Observation Sequence Log/1', 'autorouting', 'on');
end


function add_discrete_boundary(model_name, block_name, position)
add_block('simulink/Signal Attributes/Rate Transition', ...
    [model_name '/' block_name], ...
    'OutPortSampleTime', '1e-3', ...
    'Position', position);
end


function add_model_note(model_name, note)
annotation = Simulink.Annotation(model_name, note);
annotation.Position = [1760 1100 2380 1205];
end


function script = llm_guarded_state_machine_script()
lines = {
    'function [P_batt_ref_w, state_code, charge_headroom_w, p_load_nominal_w, voltage_error_v, vbus_log_v, soc_log_pct, source_at_limit_log] = fcn(Vbus_v, soc_pct, i_load_a, source_at_limit, requested_mode_code, command_valid, requested_power_w)'
    '%#codegen'
    '% LLM chooses supervisory intent; deterministic local logic owns safety.'
    '% Mode codes: CHARGE=-1, HOLD=0, DISCHARGE=1, SAFE=99.'
    '% Positive battery power discharges into the bus; negative charges.'
    ''
    'HOLD = uint8(0);'
    'CHARGE = uint8(1);'
    'BUS_SUPPORT = uint8(2);'
    'SAFE_LOCAL = uint8(3);'
    ''
    'Ts = 1e-3;'
    'Vnom = 400.0;'
    'Vsupport_enter = 397.0;'
    'Vsupport_exit = 399.0;'
    'Vcharge_abort = 395.0;'
    'SOCtarget = 40.0;'
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
    '    state = SAFE_LOCAL;'
    '    integral_v_s = 0.0;'
    'end'
    ''
    'p_load_nominal_w = Vnom * abs(i_load_a);'
    'charge_headroom_w = max(0.0, Psource_allowed - p_load_nominal_w);'
    'voltage_error_v = max(0.0, Vsupport_exit - Vbus_v);'
    ''
    'signals_valid = isfinite(Vbus_v) && isfinite(soc_pct) && isfinite(i_load_a);'
    'hard_fault = ~signals_valid || soc_pct <= 10.0 || soc_pct >= 95.0 || Vbus_v <= 250.0 || Vbus_v >= 500.0;'
    'external_safe = command_valid < 0.5 || requested_mode_code >= 90.0;'
    'request_charge = abs(requested_mode_code + 1.0) < 0.25;'
    'request_discharge = abs(requested_mode_code - 1.0) < 0.25;'
    'physical_support = Vbus_v <= Vsupport_enter || source_at_limit >= 0.5 || p_load_nominal_w >= Psource_allowed;'
    'charge_support = Vbus_v <= Vcharge_abort || source_at_limit >= 0.5 || p_load_nominal_w >= Psource_allowed || request_discharge;'
    'support_requested = physical_support || request_discharge;'
    'support_cleared = Vbus_v >= Vsupport_exit && source_at_limit < 0.5 && p_load_nominal_w <= (Psource_allowed - 10.0) && ~request_discharge;'
    'charge_requested = request_charge && soc_pct < (SOCtarget - 0.1);'
    'charge_entry_possible = charge_requested && charge_headroom_w > 1.0 && Vbus_v >= Vsupport_exit;'
    'charge_continue_possible = charge_requested && charge_headroom_w > 1.0 && Vbus_v > Vcharge_abort && source_at_limit < 0.5;'
    ''
    'if hard_fault || external_safe'
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
    '            if charge_support'
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
    'switch state'
    '    case CHARGE'
    '        integral_v_s = 0.0;'
    '        requested_charge_w = min(max(abs(requested_power_w), 0.0), Pchg_max);'
    '        P_batt_ref_w = -min(requested_charge_w, charge_headroom_w);'
    '    case BUS_SUPPORT'
    '        p_deficit_w = max(0.0, p_load_nominal_w - Psource_allowed);'
    '        discretionary_limit_w = max(0.0, p_load_nominal_w - Psource_reserve);'
    '        requested_discharge_w = 0.0;'
    '        if request_discharge'
    '            requested_discharge_w = min(abs(requested_power_w), discretionary_limit_w);'
    '        end'
    '        p_local_w = p_deficit_w + Kp_v * voltage_error_v + Ki_v * integral_v_s;'
    '        p_unsat_w = max(p_local_w, requested_discharge_w);'
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
