function obs = dt_bridge_extract_observation(sim_out, sim_time_s, command, previous_obs)
%DT_BRIDGE_EXTRACT_OBSERVATION Convert Simulink logs into the runner contract.
%
% Preferred logging shape:
%   logsout element named dt_state containing a bus with fields:
%   soc_pct, v_bus_v, v_batt_v, i_batt_a, p_batt_w, p_load_w, p_source_w,
%   source_at_limit, source_available, source_power_limit_w
%
% Fallback:
%   individually logged signals with those names, or common aliases such as
%   SOC, V_bus, I_batt, etc.

if nargin >= 4 && isstruct(previous_obs)
    obs = previous_obs;
else
    obs = dt_bridge_default_observation(sim_time_s, command);
end

obs.sim_time_s = double(sim_time_s);
obs.fault_flags = struct();
obs.extra.command_mode = command.mode;
if isfield(command, 'mode_code')
    obs.extra.command_mode_code = command.mode_code;
end
obs.extra.command_p_batt_cmd_w = command.p_batt_cmd_w;
obs.extra.command_enable = command.enable;
obs.extra.command_reason = command.reason;

[value, found] = read_any_signal(sim_out, {'soc_pct', 'SOC', 'SoC', 'soc'});
if found
    obs.soc_pct = double(value);
else
    obs.fault_flags.bridge_missing_soc_pct = true;
end

[value, found] = read_any_signal(sim_out, {'v_bus_v', 'V_bus', 'v_bus', 'Vbus'});
if found
    obs.v_bus_v = double(value);
else
    obs.fault_flags.bridge_missing_v_bus_v = true;
end

[value, found] = read_any_signal(sim_out, {'v_batt_v', 'V_batt', 'v_batt', 'Vbatt'});
if found
    obs.v_batt_v = double(value);
end

[value, found] = read_any_signal(sim_out, {'i_batt_a', 'I_batt', 'i_batt', 'Ibatt'});
if found
    obs.i_batt_a = double(value);
end

[value, found] = read_any_signal(sim_out, {'p_batt_w', 'P_batt', 'p_batt', 'Pbatt'});
if found
    obs.p_batt_w = double(value);
end

[value, found] = read_any_signal(sim_out, {'p_load_w', 'P_load', 'p_load', 'Pload'});
if found
    obs.p_load_w = double(value);
end

[value, found] = read_any_signal(sim_out, {'p_source_w', 'P_source', 'p_source', 'Psource'});
if found
    obs.p_source_w = double(value);
end

[value, found] = read_any_signal(sim_out, {'source_at_limit', 'source_limit', 'sourceAtLimit'});
if found
    obs.source_at_limit = logical_value(value);
end

[value, found] = read_any_signal(sim_out, {'source_available', 'sourceAvailable'});
if found
    obs.source_available = logical_value(value);
end

[value, found] = read_any_signal(sim_out, {'source_power_limit_w', 'P_source_limit', 'sourcePowerLimit', 'Psource_limit'});
if found
    obs.source_power_limit_w = double(value);
end

[value, found] = read_any_signal(sim_out, {'max_safe_charge_w', 'safe_charge_limit_w', 'P_charge_safe'});
if found
    obs.max_safe_charge_w = double(value);
end

[value, found] = read_any_signal(sim_out, {'D_cmd', 'd_cmd', 'duty_cmd', 'duty'});
if found
    obs.extra.D_cmd = double(value);
end

[value, found] = read_any_signal(sim_out, {'V_ref_cmd', 'v_ref_cmd', 'Vref_cmd', 'V_ref'});
if found
    obs.extra.V_ref_cmd = double(value);
end

[value, found] = read_any_signal(sim_out, {'D_limited', 'd_limited', 'duty_limited'});
if found
    obs.extra.D_limited = double(value);
end
end

function [value, found] = read_any_signal(sim_out, aliases)
value = [];
found = false;

for idx = 1:numel(aliases)
    [value, found] = read_named_signal(sim_out, aliases{idx});
    if found
        return;
    end
end

for idx = 1:numel(aliases)
    [value, found] = read_dt_state_field(sim_out, aliases{idx});
    if found
        return;
    end
end
end

function [value, found] = read_named_signal(sim_out, signal_name)
value = [];
found = false;

logsout = get_logsout(sim_out);
if ~isempty(logsout)
    try
        [element, element_found] = find_dataset_element(logsout, signal_name);
        if element_found
            [value, found] = latest_value(element.Values);
            if found
                return;
            end
        end
    catch
    end
end

try
    raw = sim_out.get(signal_name);
    [value, found] = latest_value(raw);
    if found
        return;
    end
catch
end

try
    raw = evalin('base', signal_name);
    [value, found] = latest_value(raw);
catch
end
end

function [value, found] = read_dt_state_field(sim_out, field_name)
value = [];
found = false;

logsout = get_logsout(sim_out);
if ~isempty(logsout)
    try
        [element, element_found] = find_dataset_element(logsout, 'dt_state');
        if element_found
            [value, found] = read_struct_field(element.Values, field_name);
            if found
                return;
            end
        end
    catch
    end
end

try
    raw = sim_out.get('dt_state');
    [value, found] = read_struct_field(raw, field_name);
catch
end
end

function logsout = get_logsout(sim_out)
logsout = [];
try
    logsout = sim_out.logsout;
    if ~isempty(logsout)
        return;
    end
catch
end

try
    logsout = sim_out.get('logsout');
catch
    logsout = [];
end
end

function [value, found] = read_struct_field(raw, field_name)
value = [];
found = false;

if isa(raw, 'Simulink.SimulationData.Signal')
    [value, found] = read_struct_field(raw.Values, field_name);
    return;
end

if isa(raw, 'Simulink.SimulationData.Dataset')
    try
        [element, element_found] = find_dataset_element(raw, field_name);
        if element_found
            [value, found] = latest_value(element.Values);
            if found
                return;
            end
        end
    catch
    end
end

if isa(raw, 'timeseries')
    [value, found] = read_struct_field(raw.Data, field_name);
    return;
end

if isstruct(raw)
    if isfield(raw, field_name)
        [value, found] = latest_value(raw.(field_name));
        if found
            return;
        end
    end

    names = fieldnames(raw);
    for idx = 1:numel(names)
        if strcmpi(names{idx}, field_name)
            [value, found] = latest_value(raw.(names{idx}));
            if found
                return;
            end
        end
    end

    if isfield(raw, 'signals') && isfield(raw.signals, 'values')
        [value, found] = read_struct_field(raw.signals.values, field_name);
        if found
            return;
        end
    end
end
end

function [value, found] = latest_value(raw)
value = [];
found = false;

if isa(raw, 'Simulink.SimulationData.Signal')
    [value, found] = latest_value(raw.Values);
    return;
end

if isa(raw, 'timeseries')
    [value, found] = latest_value(raw.Data);
    return;
end

if isa(raw, 'timetable')
    data = raw{:, :};
    [value, found] = latest_value(data);
    return;
end

if isstruct(raw)
    if isfield(raw, 'signals') && isfield(raw.signals, 'values')
        [value, found] = latest_value(raw.signals.values);
        return;
    end
    if isfield(raw, 'Data')
        [value, found] = latest_value(raw.Data);
        return;
    end
end

if isnumeric(raw) || islogical(raw)
    if isempty(raw)
        return;
    end
    flattened = raw(:);
    value = flattened(end);
    found = true;
    return;
end

if ischar(raw) || isstring(raw)
    value = raw;
    found = true;
end
end

function [element, found] = find_dataset_element(dataset, element_name)
element = [];
found = false;

try
    n_elements = dataset.numElements;
catch
    try
        n_elements = dataset.numElements();
    catch
        n_elements = 0;
    end
end

for idx = 1:n_elements
    try
        candidate = dataset.getElement(idx);
        if isprop(candidate, 'Name')
            candidate_name = candidate.Name;
        elseif isfield(candidate, 'Name')
            candidate_name = candidate.Name;
        else
            candidate_name = '';
        end

        if strcmp(candidate_name, element_name) || strcmpi(candidate_name, element_name)
            element = candidate;
            found = true;
            return;
        end
    catch
    end
end
end

function value = logical_value(raw)
if islogical(raw)
    value = raw;
elseif isnumeric(raw)
    value = raw ~= 0;
elseif isstring(raw) || ischar(raw)
    value = any(strcmpi(char(raw), {'true', '1', 'yes', 'on'}));
else
    value = logical(raw);
end
end
