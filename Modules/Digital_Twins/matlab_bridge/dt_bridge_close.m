function dt_bridge_close()
%DT_BRIDGE_CLOSE Release the Simulink bridge state.

global DT_BRIDGE;

if ~isempty(DT_BRIDGE) && isfield(DT_BRIDGE, 'model_name')
    try
        close_system(DT_BRIDGE.model_name, 0);
    catch
    end
end

DT_BRIDGE = [];
end
