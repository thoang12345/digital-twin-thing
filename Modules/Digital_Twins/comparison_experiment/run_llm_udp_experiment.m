function timing = run_llm_udp_experiment(output_dir)
%RUN_LLM_UDP_EXPERIMENT Run the paced model while a UDP supervisor is live.

this_dir = fileparts(mfilename('fullpath'));
dt_dir = fileparts(this_dir);
if nargin < 1 || strlength(string(output_dir)) == 0
    output_dir = fullfile(fileparts(fileparts(dt_dir)), 'results', 'latest_comparison');
end
if ~isfolder(output_dir)
    mkdir(output_dir);
end

addpath(this_dir, dt_dir);
model_name = 'DT_enviroment_state_machine_llm_udp';
model_path = fullfile(dt_dir, [model_name '.slx']);
if ~isfile(model_path)
    build_llm_udp_comparison_models();
end

load_system(model_path);
cleanup = onCleanup(@() close_if_loaded(model_name));
set_param(model_name, 'EnablePacing', 'on', 'PacingRate', '1', 'StopTime', '120.5');

sampler = start_cpu_sampler('llm_udp', output_dir);
wall_clock = tic;
matlab_cpu_before_s = cputime;
simulation_output = sim(model_name, 'ReturnWorkspaceOutputs', 'on');
matlab_cpu_s = cputime - matlab_cpu_before_s;
wall_time_s = toc(wall_clock);
stop_cpu_sampler(sampler);

data = normalize_experiment_output(simulation_output, true);
data = data(data.sim_time_s <= 120.0, :);
writetable(data, fullfile(output_dir, 'llm_udp_data.csv'));

timing = make_timing( ...
    'LLM/UDP guarded state machine', ...
    120.0, wall_time_s, matlab_cpu_s, model_path);
save(fullfile(output_dir, 'llm_udp_timing.mat'), 'timing');

fprintf('\nLLM/UDP experiment complete\n');
fprintf('  Wall time: %.3f s\n', timing.wall_time_s);
fprintf('  MATLAB CPU time: %.3f s\n', timing.matlab_cpu_s);
fprintf('  Real-time factor: %.3f x\n', timing.realtime_factor);

clear cleanup;
close_if_loaded(model_name);
end


function timing = make_timing(label, simulated_time_s, wall_time_s, cpu_s, model_path)
timing = struct();
timing.label = label;
timing.model_path = model_path;
timing.simulated_time_s = simulated_time_s;
timing.wall_time_s = wall_time_s;
timing.matlab_cpu_s = cpu_s;
timing.realtime_factor = simulated_time_s / wall_time_s;
timing.matlab_average_core_pct = 100.0 * cpu_s / wall_time_s;
timing.finished_utc = char(datetime('now', 'TimeZone', 'UTC'));
end


function close_if_loaded(model_name)
if bdIsLoaded(model_name)
    close_system(model_name, 0);
end
end
