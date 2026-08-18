function summary = run_state_machine_dt_smoke()
%RUN_STATE_MACHINE_DT_SMOKE Build, simulate, and summarize the standalone DT.

this_dir = fileparts(mfilename('fullpath'));
addpath(this_dir);

model_path = build_state_machine_dt();
[~, model_name] = fileparts(model_path);
load_system(model_path);
cleanup = onCleanup(@() close_if_loaded(model_name));

set_param(model_name, 'EnablePacing', 'off', 'StopTime', '120');
simulation_output = sim(model_name, 'ReturnWorkspaceOutputs', 'on');

controller_log = simulation_output.get('SM_Controller');
if isempty(controller_log) || ~isfield(controller_log, 'signals')
    error('The controller log SM_Controller was not produced.');
end

time_s = controller_log.time(:);
values = controller_log.signals.values;
if size(values, 2) ~= 8
    error('Expected 8 SM_Controller columns, received %d.', size(values, 2));
end

state_code = values(:, 2);
state_change_index = [true; diff(state_code) ~= 0];
transition_times_s = time_s(state_change_index);
transition_states = state_code(state_change_index);

% Fail loudly if the standalone controller regresses.  The supplied load
% profile should charge until the 50 s load increase, then remain in bus
% support through the 100 s increase without mode chatter.
assert(all(isfinite(values), 'all'), ...
    'The controller log contains non-finite values.');
assert(all(ismember(unique(state_code), [0 1 2 3])), ...
    'The controller produced an unknown state code.');
assert(min(values(:, 6)) > 390.0 && max(values(:, 6)) < 410.0, ...
    'The DC bus left the 390--410 V standalone smoke-test band.');
assert(min(values(:, 1)) >= -300.0 && max(values(:, 1)) <= 480.0, ...
    'The battery reference exceeded the interface power limits.');
assert(isequal(transition_states(:).', [1 2]), ...
    'Expected the clean state sequence CHARGE -> BUS_SUPPORT.');
assert(abs(transition_times_s(1)) <= 1e-9 && ...
       abs(transition_times_s(2) - 50.0) <= 0.01, ...
    'Expected the BUS_SUPPORT transition at the 50 s load step.');

summary = struct();
summary.model_path = model_path;
summary.samples = numel(time_s);
summary.start_time_s = time_s(1);
summary.end_time_s = time_s(end);
summary.min_vbus_v = min(values(:, 6));
summary.max_vbus_v = max(values(:, 6));
summary.initial_soc_pct = values(1, 7);
summary.final_soc_pct = values(end, 7);
summary.min_p_batt_ref_w = min(values(:, 1));
summary.max_p_batt_ref_w = max(values(:, 1));
summary.transition_times_s = transition_times_s;
summary.transition_states = transition_states;

fprintf('\nStandalone state-machine DT smoke result\n');
fprintf('  Model: %s\n', model_path);
fprintf('  Vbus min/max: %.3f / %.3f V\n', ...
    summary.min_vbus_v, summary.max_vbus_v);
fprintf('  SOC initial/final: %.4f / %.4f %%\n', ...
    summary.initial_soc_pct, summary.final_soc_pct);
fprintf('  P_batt_ref min/max: %.3f / %.3f W\n', ...
    summary.min_p_batt_ref_w, summary.max_p_batt_ref_w);
fprintf('  State transitions [time_s -> state_code]:\n');
for index = 1:numel(transition_times_s)
    fprintf('    %.3f -> %.0f\n', transition_times_s(index), transition_states(index));
end

log_dir = fullfile(fileparts(this_dir), '..', 'logs');
if ~isfolder(log_dir)
    mkdir(log_dir);
end

column_names = { ...
    'p_batt_ref_w', ...
    'state_code', ...
    'charge_headroom_w', ...
    'p_load_nominal_w', ...
    'voltage_error_v', ...
    'v_bus_v', ...
    'soc_pct', ...
    'source_at_limit'};
log_table = array2table(values, 'VariableNames', column_names);
log_table.sim_time_s = time_s;
log_table = movevars(log_table, 'sim_time_s', 'Before', 1);
writetable(log_table, fullfile(log_dir, 'state_machine_dt_smoke.csv'));

save(fullfile(log_dir, 'state_machine_dt_smoke_summary.mat'), 'summary');

clear cleanup;
close_if_loaded(model_name);
end


function close_if_loaded(model_name)
if bdIsLoaded(model_name)
    close_system(model_name, 0);
end
end
