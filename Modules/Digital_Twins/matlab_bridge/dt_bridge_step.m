function obs_json = dt_bridge_step(seconds)
%DT_BRIDGE_STEP Advance the Simulink model by one supervisor window.

global DT_BRIDGE;

if isempty(DT_BRIDGE)
    error('dt_bridge_step:NotInitialized', ...
        'Call dt_bridge_init before stepping the simulation.');
end

seconds = double(seconds);
if seconds < 0
    error('dt_bridge_step:NegativeStep', ...
        'Step duration must be non-negative.');
end

external_start_time_s = DT_BRIDGE.current_time_s;
external_stop_time_s = external_start_time_s + seconds;

% When resuming from a saved ModelOperatingPoint, Simulink expects the model
% StartTime to match the operating point's saved start-time context. For this
% bridge we treat each call as a local segment while tracking absolute mission
% time separately in DT_BRIDGE.current_time_s. The StopTime remains absolute
% so it is always greater than the snapshot time stored in the operating point.
% This avoids the repeated warning:
% "The start time ... is different from the start time saved in the initial
% ModelOperatingPoint."
if ~isempty(DT_BRIDGE.final_state)
    segment_start_time_s = 0.0;
    segment_stop_time_s = external_stop_time_s;
else
    segment_start_time_s = external_start_time_s;
    segment_stop_time_s = external_stop_time_s;
end

try
    sim_in = Simulink.SimulationInput(DT_BRIDGE.model_name);
    sim_in = sim_in.setModelParameter( ...
        'StartTime', num2str(segment_start_time_s, '%.15g'), ...
        'StopTime', num2str(segment_stop_time_s, '%.15g'), ...
        'SignalLogging', 'on', ...
        'SignalLoggingName', 'logsout', ...
        'SaveOutput', 'on', ...
        'SaveTime', 'on', ...
        'SaveFinalState', 'on', ...
        'FinalStateName', 'xFinal', ...
        'SaveCompleteFinalSimState', 'on');

    sim_in = sim_in.setVariable( ...
        DT_BRIDGE.p_batt_cmd_variable, DT_BRIDGE.last_command.p_batt_cmd_w);
    sim_in = sim_in.setVariable( ...
        DT_BRIDGE.enable_variable, double(DT_BRIDGE.last_command.enable));
    if isfield(DT_BRIDGE.last_command, 'mode_code')
        mode_value = DT_BRIDGE.last_command.mode_code;
    else
        mode_value = 0.0;
    end
    sim_in = sim_in.setVariable( ...
        DT_BRIDGE.mode_variable, mode_value);

    if ~isempty(DT_BRIDGE.final_state)
        try
            sim_in = sim_in.setInitialState(DT_BRIDGE.final_state);
        catch
            sim_in = sim_in.setVariable( ...
                'dt_bridge_initial_state', DT_BRIDGE.final_state);
            sim_in = sim_in.setModelParameter( ...
                'LoadInitialState', 'on', ...
                'InitialState', 'dt_bridge_initial_state');
        end
    end

    sim_out = sim(sim_in);
    DT_BRIDGE.current_time_s = external_stop_time_s;

    if seconds > 0
        try
            DT_BRIDGE.final_state = sim_out.xFinal;
        catch
            DT_BRIDGE.final_state = [];
        end
    end

    obs = dt_bridge_extract_observation( ...
        sim_out, external_stop_time_s, DT_BRIDGE.last_command, ...
        DT_BRIDGE.last_observation);
    DT_BRIDGE.last_observation = obs;
    obs_json = jsonencode(obs);
catch ME
    obs = DT_BRIDGE.last_observation;
    obs.sim_time_s = external_stop_time_s;
    obs.fault_flags.bridge_sim_failed = true;
    obs.extra.bridge_error_identifier = ME.identifier;
    obs.extra.bridge_error = ME.message;
    try
        obs.extra.bridge_error_report = getReport(ME, 'extended', 'hyperlinks', 'off');
    catch
        obs.extra.bridge_error_report = ME.message;
    end
    DT_BRIDGE.last_observation = obs;
    obs_json = jsonencode(obs);
end
end
