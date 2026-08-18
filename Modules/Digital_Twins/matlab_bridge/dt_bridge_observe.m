function obs_json = dt_bridge_observe()
%DT_BRIDGE_OBSERVE Return the latest bridge observation as JSON.

global DT_BRIDGE;

if isempty(DT_BRIDGE) || ~isfield(DT_BRIDGE, 'last_observation')
    command = struct( ...
        'p_batt_cmd_w', 0.0, ...
        'enable', false, ...
        'mode', 'SAFE', ...
        'mode_code', 99.0, ...
        'reason', 'bridge not initialized');
    obs = dt_bridge_default_observation(0.0, command);
    obs.fault_flags.bridge_not_initialized = true;
    obs_json = jsonencode(obs);
    return;
end

obs_json = jsonencode(DT_BRIDGE.last_observation);
end
