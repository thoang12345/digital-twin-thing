function dt_bridge_apply_command(p_batt_cmd_w, enable_cmd, mode_cmd, reason)
%DT_BRIDGE_APPLY_COMMAND Store the command for the next simulation window.
%
% The command is both stored in DT_BRIDGE and assigned into the MATLAB base
% workspace. This supports either SimulationInput variables or simple Constant
% blocks whose values are set to P_batt_cmd / enable_cmd / mode_cmd.

global DT_BRIDGE;

if isempty(DT_BRIDGE)
    error('dt_bridge_apply_command:NotInitialized', ...
        'Call dt_bridge_init before applying commands.');
end
if nargin < 1 || isempty(p_batt_cmd_w)
    p_batt_cmd_w = 0.0;
end
if nargin < 2 || isempty(enable_cmd)
    enable_cmd = true;
end
if nargin < 3 || isempty(mode_cmd)
    mode_cmd = 'HOLD';
end
if nargin < 4
    reason = '';
end

command = struct();
command.p_batt_cmd_w = double(p_batt_cmd_w);
command.enable = logical(enable_cmd);
command.mode = char(mode_cmd);
command.mode_code = mode_to_code(command.mode);
command.reason = char(reason);
DT_BRIDGE.last_command = command;

assignin('base', DT_BRIDGE.p_batt_cmd_variable, command.p_batt_cmd_w);
assignin('base', DT_BRIDGE.enable_variable, double(command.enable));
assignin('base', DT_BRIDGE.mode_variable, command.mode_code);
end

function code = mode_to_code(mode)
mode = upper(strtrim(char(mode)));
switch mode
    case 'CHARGE'
        code = -1.0;
    case 'HOLD'
        code = 0.0;
    case 'DISCHARGE'
        code = 1.0;
    case 'SAFE'
        code = 99.0;
    otherwise
        code = 0.0;
end
end
