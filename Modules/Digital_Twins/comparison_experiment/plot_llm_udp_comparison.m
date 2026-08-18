function [timing_table, performance_table] = plot_llm_udp_comparison(output_dir)
%PLOT_LLM_UDP_COMPARISON Create paper-ready plots and summary tables.

this_dir = fileparts(mfilename('fullpath'));
dt_dir = fileparts(this_dir);
if nargin < 1 || strlength(string(output_dir)) == 0
    output_dir = fullfile(fileparts(fileparts(dt_dir)), 'results', 'latest_comparison');
end

baseline = readtable(fullfile(output_dir, 'baseline_data.csv'));
llm = readtable(fullfile(output_dir, 'llm_udp_data.csv'));
baseline = baseline(baseline.sim_time_s <= 120.0, :);
llm = llm(llm.sim_time_s <= 120.0, :);

figure_dir = fullfile(output_dir, 'figures');
if ~isfolder(figure_dir)
    mkdir(figure_dir);
end

plot_overview(baseline, llm, figure_dir);
plot_power_balance(baseline, llm, figure_dir);
plot_llm_supervision(llm, figure_dir);
plot_policy_guard_audit(output_dir, figure_dir);

timing_table = build_timing_table(output_dir);
writetable(timing_table, fullfile(output_dir, 'comparison_timing.csv'));
plot_timing(timing_table, figure_dir);

performance_table = [ ...
    performance_row('Deterministic state machine', baseline); ...
    performance_row('LLM/UDP guarded state machine', llm)];
writetable(performance_table, ...
    fullfile(output_dir, 'comparison_performance_metrics.csv'));

fprintf('\nTiming comparison\n');
disp(timing_table);
fprintf('\nControl-performance comparison\n');
disp(performance_table);
fprintf('Figures written to: %s\n', figure_dir);
end


function plot_overview(baseline, llm, figure_dir)
fig = figure('Color', 'w', 'Position', [100 100 1250 850]);
tiledlayout(4, 1, 'TileSpacing', 'compact', 'Padding', 'compact');

nexttile;
plot(baseline.sim_time_s, baseline.v_bus_v, 'LineWidth', 1.2); hold on;
plot(llm.sim_time_s, llm.v_bus_v, '--', 'LineWidth', 1.2);
yline(400, ':k', '400 V');
yline(397, ':', 'support entry');
ylabel('Bus voltage (V)'); grid on;
legend('Deterministic', 'LLM/UDP', 'Location', 'best');
title('Matched digital-twin control comparison');

nexttile;
plot(baseline.sim_time_s, baseline.p_batt_ref_w, 'LineWidth', 1.2); hold on;
plot(llm.sim_time_s, llm.p_batt_ref_w, '--', 'LineWidth', 1.2);
yline(0, ':k');
ylabel('Battery ref. (W)'); grid on;

nexttile;
plot(baseline.sim_time_s, baseline.soc_pct, 'LineWidth', 1.2); hold on;
plot(llm.sim_time_s, llm.soc_pct, '--', 'LineWidth', 1.2);
ylabel('SOC (%)'); grid on;

nexttile;
stairs(baseline.sim_time_s, baseline.state_code, 'LineWidth', 1.2); hold on;
stairs(llm.sim_time_s, llm.state_code, '--', 'LineWidth', 1.2);
yticks(0:3);
yticklabels({'HOLD', 'CHARGE', 'BUS SUPPORT', 'SAFE LOCAL'});
ylabel('Enforced state'); xlabel('Simulation time (s)'); grid on;

exportgraphics(fig, fullfile(figure_dir, 'comparison_overview.png'), ...
    'Resolution', 180);
exportgraphics(fig, fullfile(figure_dir, 'comparison_overview.pdf'), ...
    'ContentType', 'vector');
close(fig);
end


function plot_power_balance(baseline, llm, figure_dir)
fig = figure('Color', 'w', 'Position', [120 120 1250 760]);
tiledlayout(2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');

nexttile;
plot(baseline.sim_time_s, abs(baseline.p_load_w), 'k', 'LineWidth', 1.1); hold on;
plot(baseline.sim_time_s, baseline.p_source_w, 'LineWidth', 1.1);
plot(baseline.sim_time_s, baseline.p_batt_w, 'LineWidth', 1.1);
ylabel('Power (W)'); title('Deterministic state machine'); grid on;
legend('|P_{load}|', 'P_{source}', 'P_{battery}', 'Location', 'best');

nexttile;
plot(llm.sim_time_s, abs(llm.p_load_w), 'k', 'LineWidth', 1.1); hold on;
plot(llm.sim_time_s, llm.p_source_w, 'LineWidth', 1.1);
plot(llm.sim_time_s, llm.p_batt_w, 'LineWidth', 1.1);
ylabel('Power (W)'); xlabel('Simulation time (s)');
title('LLM/UDP guarded state machine'); grid on;
legend('|P_{load}|', 'P_{source}', 'P_{battery}', 'Location', 'best');

exportgraphics(fig, fullfile(figure_dir, 'power_balance.png'), ...
    'Resolution', 180);
exportgraphics(fig, fullfile(figure_dir, 'power_balance.pdf'), ...
    'ContentType', 'vector');
close(fig);
end


function plot_llm_supervision(llm, figure_dir)
fig = figure('Color', 'w', 'Position', [140 140 1250 850]);
tiledlayout(4, 1, 'TileSpacing', 'compact', 'Padding', 'compact');

nexttile;
requested_state_display = nan(height(llm), 1);
requested_state_display(abs(llm.llm_mode_code) < 0.25) = 0;
requested_state_display(abs(llm.llm_mode_code + 1) < 0.25) = 1;
requested_state_display(abs(llm.llm_mode_code - 1) < 0.25) = 2;
requested_state_display(llm.llm_mode_code >= 90) = 3;
stairs(llm.sim_time_s, requested_state_display, 'LineWidth', 1.2); hold on;
stairs(llm.sim_time_s, llm.state_code, '--', 'LineWidth', 1.2);
yticks(0:3);
yticklabels({'HOLD', 'CHARGE', 'DISCHARGE/SUPPORT', 'SAFE LOCAL'});
ylabel('Requested/enforced mode'); grid on;
legend('Guarded UDP mode', 'Locally enforced state', 'Location', 'best');
title('Supervisory request versus deterministic enforcement');

nexttile;
stairs(llm.sim_time_s, llm.llm_requested_power_w, 'LineWidth', 1.2); hold on;
plot(llm.sim_time_s, llm.p_batt_ref_w, '--', 'LineWidth', 1.2);
yline(0, ':k'); ylabel('Power (W)'); grid on;
legend('Guarded UDP command', 'Locally enforced reference', 'Location', 'best');

nexttile;
yyaxis left;
stairs(llm.sim_time_s, llm.llm_command_seq, 'LineWidth', 1.2);
ylabel('UDP command sequence');
yyaxis right;
stairs(llm.sim_time_s, llm.llm_command_valid, '--', 'LineWidth', 1.2);
ylim([-0.05 1.05]);
yticks([0 1]);
ylabel('Command valid'); grid on;

nexttile;
plot(llm.sim_time_s, llm.llm_command_age_s, 'LineWidth', 1.2);
yline(15, ':r', 'stale threshold');
ylabel('Command age (s)'); xlabel('Simulation time (s)'); grid on;

exportgraphics(fig, fullfile(figure_dir, 'llm_supervision.png'), ...
    'Resolution', 180);
exportgraphics(fig, fullfile(figure_dir, 'llm_supervision.pdf'), ...
    'ContentType', 'vector');
close(fig);
end


function plot_policy_guard_audit(output_dir, figure_dir)
runner_path = fullfile(output_dir, 'llm_runner.csv');
if ~isfile(runner_path)
    return;
end
runner = readtable(runner_path, ...
    'Delimiter', ',', ...
    'TextType', 'string', ...
    'VariableNamingRule', 'preserve');
if isempty(runner)
    return;
end

policy_state = mode_to_display(runner.policy_mode);
guarded_state = mode_to_display(runner.command_mode);

fig = figure('Color', 'w', 'Position', [180 180 1150 650]);
tiledlayout(2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');

nexttile;
stairs(runner.sim_time_s, policy_state, '-o', 'LineWidth', 1.2); hold on;
stairs(runner.sim_time_s, guarded_state, '--s', 'LineWidth', 1.2);
yticks(0:3);
yticklabels({'HOLD', 'CHARGE', 'DISCHARGE', 'SAFE'});
ylabel('Supervisory mode'); grid on;
title('Raw LLM proposal versus deterministic Python guard');
legend('Raw LLM policy', 'Command sent over UDP', 'Location', 'best');

nexttile;
stairs(runner.sim_time_s, runner.policy_p_batt_cmd_w, '-o', 'LineWidth', 1.2); hold on;
stairs(runner.sim_time_s, runner.p_batt_cmd_w, '--s', 'LineWidth', 1.2);
yline(0, ':k');
ylabel('Power request (W)'); xlabel('Simulation time (s)'); grid on;
legend('Raw LLM policy', 'Command sent over UDP', 'Location', 'best');

exportgraphics(fig, fullfile(figure_dir, 'llm_policy_guard_audit.png'), ...
    'Resolution', 180);
exportgraphics(fig, fullfile(figure_dir, 'llm_policy_guard_audit.pdf'), ...
    'ContentType', 'vector');
close(fig);
end


function value = mode_to_display(mode)
mode = upper(strtrim(string(mode)));
value = nan(size(mode));
value(mode == "HOLD") = 0;
value(mode == "CHARGE") = 1;
value(mode == "DISCHARGE") = 2;
value(mode == "SAFE") = 3;
end


function timing_table = build_timing_table(output_dir)
baseline_file = load(fullfile(output_dir, 'baseline_timing.mat'), 'timing');
llm_file = load(fullfile(output_dir, 'llm_udp_timing.mat'), 'timing');
baseline_cpu = cpu_summary(fullfile(output_dir, 'baseline_cpu.csv'));
llm_cpu = cpu_summary(fullfile(output_dir, 'llm_udp_cpu.csv'));
llm_stats = llm_trace_summary(fullfile(output_dir, 'llm_trace.jsonl'));

timing_table = table( ...
    string({baseline_file.timing.label; llm_file.timing.label}), ...
    [baseline_file.timing.simulated_time_s; llm_file.timing.simulated_time_s], ...
    [baseline_file.timing.wall_time_s; llm_file.timing.wall_time_s], ...
    [baseline_file.timing.matlab_cpu_s; llm_file.timing.matlab_cpu_s], ...
    [baseline_file.timing.realtime_factor; llm_file.timing.realtime_factor], ...
    [baseline_file.timing.matlab_average_core_pct; llm_file.timing.matlab_average_core_pct], ...
    [baseline_cpu.average_system_cpu_pct; llm_cpu.average_system_cpu_pct], ...
    [baseline_cpu.python_cpu_delta_s; llm_cpu.python_cpu_delta_s], ...
    [baseline_cpu.lm_studio_cpu_delta_s; llm_cpu.lm_studio_cpu_delta_s], ...
    [0; llm_stats.calls], ...
    [nan; llm_stats.mean_latency_s], ...
    [nan; llm_stats.p95_latency_s], ...
    [0; llm_stats.fallbacks], ...
    'VariableNames', { ...
        'controller', ...
        'simulated_time_s', ...
        'wall_time_s', ...
        'matlab_cpu_s', ...
        'realtime_factor', ...
        'matlab_average_core_pct', ...
        'average_system_cpu_pct', ...
        'python_cpu_delta_s', ...
        'lm_studio_cpu_delta_s', ...
        'llm_calls', ...
        'mean_llm_latency_s', ...
        'p95_llm_latency_s', ...
        'llm_fallbacks'});
end


function summary = cpu_summary(path)
summary = struct( ...
    'average_system_cpu_pct', nan, ...
    'python_cpu_delta_s', nan, ...
    'lm_studio_cpu_delta_s', nan);
if ~isfile(path)
    return;
end
data = readtable(path);
if isempty(data)
    return;
end
summary.average_system_cpu_pct = mean(data.total_cpu_pct, 'omitnan');
% The short-lived Python runner may exit before the sampler's final row, so
% use the observed cumulative range instead of final-minus-initial.
summary.python_cpu_delta_s = max(data.python_cpu_s) - min(data.python_cpu_s);
summary.lm_studio_cpu_delta_s = ...
    max(data.lm_studio_cpu_s) - min(data.lm_studio_cpu_s);
end


function summary = llm_trace_summary(path)
summary = struct('calls', 0, 'fallbacks', 0, ...
    'mean_latency_s', nan, 'p95_latency_s', nan);
if ~isfile(path)
    return;
end

lines = readlines(path);
request_time = NaT;
latencies_s = [];
for index = 1:numel(lines)
    if strlength(strtrim(lines(index))) == 0
        continue;
    end
    try
        record = jsondecode(lines(index));
    catch
        continue;
    end
    event = string(record.event);
    if event == "request"
        summary.calls = summary.calls + 1;
        request_time = parse_python_utc(record.timestamp_utc);
    elseif event == "response"
        timestamp = parse_python_utc(record.timestamp_utc);
        if ~isnat(request_time)
            latencies_s(end + 1, 1) = seconds(timestamp - request_time); %#ok<AGROW>
            request_time = NaT;
        end
    elseif event == "fallback"
        summary.fallbacks = summary.fallbacks + 1;
        % A normal policy fallback is logged after the API response event,
        % so the request/response latency has already been counted.
    end
end
if ~isempty(latencies_s)
    summary.mean_latency_s = mean(latencies_s);
    summary.p95_latency_s = prctile(latencies_s, 95);
end


function value = parse_python_utc(text)
% Python emits ISO-8601 microseconds followed by +00:00.  Removing the zone
% suffix avoids MATLAB release-specific automatic parsing differences.
text = regexprep(string(text), '(Z|[+-]\d\d:\d\d)$', '');
try
    value = datetime(text, ...
        'InputFormat', "yyyy-MM-dd'T'HH:mm:ss.SSSSSS", ...
        'TimeZone', 'UTC');
catch
    value = NaT;
end
end
end


function row = performance_row(label, data)
time_s = data.sim_time_s;
v_error = data.v_bus_v - 400.0;
state_changes = nnz(diff(data.state_code) ~= 0);
safe_time_s = state_duration(time_s, data.state_code, 3.0);
support_time_s = state_duration(time_s, data.state_code, 2.0);
battery_energy_to_bus_wh = trapz(time_s, data.p_batt_w) / 3600.0;

row = table( ...
    string(label), ...
    min(data.v_bus_v), ...
    max(data.v_bus_v), ...
    sqrt(mean(v_error .^ 2)), ...
    max(abs(v_error)), ...
    data.soc_pct(end) - data.soc_pct(1), ...
    min(data.p_batt_ref_w), ...
    max(data.p_batt_ref_w), ...
    battery_energy_to_bus_wh, ...
    state_changes, ...
    support_time_s, ...
    safe_time_s, ...
    'VariableNames', { ...
        'controller', ...
        'min_v_bus_v', ...
        'max_v_bus_v', ...
        'v_bus_rmse_v', ...
        'max_abs_v_error_v', ...
        'soc_change_pct', ...
        'min_p_batt_ref_w', ...
        'max_p_batt_ref_w', ...
        'battery_energy_to_bus_wh', ...
        'state_transition_count', ...
        'bus_support_time_s', ...
        'safe_local_time_s'});
end


function duration_s = state_duration(time_s, state_code, requested_state)
if numel(time_s) < 2
    duration_s = 0.0;
    return;
end
dt = diff(time_s);
duration_s = sum(dt(state_code(1:end-1) == requested_state));
end


function plot_timing(timing_table, figure_dir)
fig = figure('Color', 'w', 'Position', [160 160 1100 480]);
tiledlayout(1, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
short_labels = categorical( ...
    ["Deterministic"; "LLM/UDP"], ...
    ["Deterministic" "LLM/UDP"]);

nexttile;
bar(short_labels, ...
    [timing_table.wall_time_s timing_table.matlab_cpu_s]);
ylabel('Seconds'); title('Execution timing'); grid on;
legend('Wall time', 'MATLAB CPU time', 'Location', 'best');

nexttile;
bar(short_labels, ...
    [timing_table.average_system_cpu_pct timing_table.matlab_average_core_pct]);
ylabel('Percent'); title('Average CPU utilization'); grid on;
legend('Whole system', 'MATLAB equivalent core', 'Location', 'best');

exportgraphics(fig, fullfile(figure_dir, 'timing_comparison.png'), ...
    'Resolution', 180);
exportgraphics(fig, fullfile(figure_dir, 'timing_comparison.pdf'), ...
    'ContentType', 'vector');
close(fig);
end
