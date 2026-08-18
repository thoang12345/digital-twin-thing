function obs = dt_bridge_default_observation(sim_time_s, command)
%DT_BRIDGE_DEFAULT_OBSERVATION Build the observation struct returned to Python.

if nargin < 1
    sim_time_s = 0.0;
end
if nargin < 2 || isempty(command)
    command = struct( ...
        'p_batt_cmd_w', 0.0, ...
        'enable', false, ...
        'mode', 'SAFE', ...
        'mode_code', 99.0, ...
        'reason', '');
end

obs = struct();
obs.sim_time_s = double(sim_time_s);
obs.soc_pct = NaN;
obs.v_bus_v = NaN;
obs.v_batt_v = NaN;
obs.i_batt_a = NaN;
obs.p_batt_w = NaN;
obs.p_load_w = NaN;
obs.p_source_w = NaN;
obs.source_at_limit = false;
obs.source_available = true;
obs.fault_flags = struct();
obs.extra = struct();
obs.extra.command_mode = command.mode;
if isfield(command, 'mode_code')
    obs.extra.command_mode_code = command.mode_code;
end
obs.extra.command_p_batt_cmd_w = command.p_batt_cmd_w;
obs.extra.command_enable = command.enable;
obs.extra.command_reason = command.reason;
end
