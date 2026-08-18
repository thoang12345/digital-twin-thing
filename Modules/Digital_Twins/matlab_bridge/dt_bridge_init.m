function obs_json = dt_bridge_init(model_name, model_path, p_batt_cmd_variable, enable_variable, mode_variable)
%DT_BRIDGE_INIT Initialize the MATLAB/Simulink side of the DT runner bridge.
%
% The Python runner calls this through MATLAB Engine. State is stored in the
% global DT_BRIDGE struct so each subsequent bridge call can continue the
% simulation from the previous final state.

global DT_BRIDGE;

if nargin < 1 || isempty(model_name)
    model_name = 'DT_enviroment';
end
if nargin < 2
    model_path = '';
end
if nargin < 3 || isempty(p_batt_cmd_variable)
    p_batt_cmd_variable = 'P_batt_cmd';
end
if nargin < 4 || isempty(enable_variable)
    enable_variable = 'enable_cmd';
end
if nargin < 5 || isempty(mode_variable)
    mode_variable = 'mode_cmd';
end

DT_BRIDGE = struct();
DT_BRIDGE.model_name = char(model_name);
DT_BRIDGE.model_path = char(model_path);
DT_BRIDGE.p_batt_cmd_variable = char(p_batt_cmd_variable);
DT_BRIDGE.enable_variable = char(enable_variable);
DT_BRIDGE.mode_variable = char(mode_variable);
DT_BRIDGE.current_time_s = 0.0;
DT_BRIDGE.final_state = [];
DT_BRIDGE.last_command = struct( ...
    'p_batt_cmd_w', 0.0, ...
    'enable', true, ...
    'mode', 'HOLD', ...
    'mode_code', 0.0, ...
    'reason', 'bridge init');
DT_BRIDGE.last_observation = dt_bridge_default_observation( ...
    0.0, DT_BRIDGE.last_command);

try
    if ~isempty(DT_BRIDGE.model_path) && exist(DT_BRIDGE.model_path, 'file')
        addpath(fileparts(DT_BRIDGE.model_path));
        load_system(DT_BRIDGE.model_path);
        [~, resolved_model_name, ~] = fileparts(DT_BRIDGE.model_path);
        DT_BRIDGE.model_name = resolved_model_name;
    else
        load_system(DT_BRIDGE.model_name);
    end

    dt_bridge_apply_command(0.0, true, 'HOLD', 'reset');
    obs_json = dt_bridge_step(0.0);
catch ME
    obs = DT_BRIDGE.last_observation;
    obs.fault_flags.bridge_init_failed = true;
    obs.extra.bridge_error = ME.message;
    DT_BRIDGE.last_observation = obs;
    obs_json = jsonencode(obs);
end
end
