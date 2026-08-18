function [timing_table, performance_table] = run_full_comparison()
%RUN_FULL_COMPARISON Build, run, record, summarize, and plot both models.

this_dir = fileparts(mfilename('fullpath'));
dt_dir = fileparts(this_dir);
project_root = fileparts(fileparts(dt_dir));
output_dir = fullfile(project_root, 'results', 'latest_comparison');
if ~isfolder(output_dir)
    mkdir(output_dir);
end
addpath(this_dir, dt_dir);

build_llm_udp_comparison_models();
ensure_lm_studio_headless();

run_baseline_experiment(output_dir);

supervisor = start_llm_supervisor(output_dir);
run_llm_udp_experiment(output_dir);
finish_llm_supervisor(supervisor, output_dir);

[timing_table, performance_table] = plot_llm_udp_comparison(output_dir);
fprintf('\nFull comparison complete. Results: %s\n', output_dir);
end
