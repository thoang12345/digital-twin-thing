function data = normalize_experiment_output(simulation_output, include_llm)
%NORMALIZE_EXPERIMENT_OUTPUT Convert Simulink structures to one flat table.

experiment_log = simulation_output.get('Experiment_Data');
controller_log = simulation_output.get('SM_Controller');

time_s = experiment_log.time(:);
values = experiment_log.signals.values;
controller_time_s = controller_log.time(:);
controller_values = controller_log.signals.values;

if size(values, 2) ~= 8
    error('Expected 8 Experiment_Data columns; found %d.', size(values, 2));
end
if size(controller_values, 2) ~= 8
    error('Expected 8 SM_Controller columns; found %d.', size(controller_values, 2));
end

data = table();
data.sim_time_s = time_s;
data.v_bus_v = values(:, 1);
data.soc_pct = values(:, 2);
data.i_batt_a = values(:, 3);
data.p_batt_w = values(:, 4);
data.p_load_w = values(:, 5);
data.p_source_w = values(:, 6);
data.source_at_limit = values(:, 7);
data.p_batt_ref_w = values(:, 8);
data.state_code = interp1(controller_time_s, controller_values(:, 2), ...
    time_s, 'previous', 'extrap');
data.charge_headroom_w = interp1(controller_time_s, controller_values(:, 3), ...
    time_s, 'previous', 'extrap');
data.p_load_nominal_w = interp1(controller_time_s, controller_values(:, 4), ...
    time_s, 'previous', 'extrap');
data.voltage_error_v = interp1(controller_time_s, controller_values(:, 5), ...
    time_s, 'previous', 'extrap');

data.llm_mode_code = nan(height(data), 1);
data.llm_requested_power_w = nan(height(data), 1);
data.llm_command_valid = nan(height(data), 1);
data.llm_command_seq = nan(height(data), 1);
data.llm_command_age_s = nan(height(data), 1);

if include_llm
    llm_log = simulation_output.get('LLM_UDP');
    llm_time_s = llm_log.time(:);
    llm_values = llm_log.signals.values;
    if size(llm_values, 2) ~= 6
        error('Expected 6 LLM_UDP columns; found %d.', size(llm_values, 2));
    end
    for column_index = 1:5
        field_names = { ...
            'llm_mode_code', ...
            'llm_requested_power_w', ...
            'llm_command_valid', ...
            'llm_command_seq', ...
            'llm_command_age_s'};
        data.(field_names{column_index}) = interp1( ...
            llm_time_s, llm_values(:, column_index), ...
            time_s, 'previous', 'extrap');
    end
end
end
