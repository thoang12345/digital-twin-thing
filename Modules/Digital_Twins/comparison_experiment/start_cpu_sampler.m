function sampler = start_cpu_sampler(label, output_dir)
%START_CPU_SAMPLER Launch an independent Windows CPU sampler.

if ~isfolder(output_dir)
    mkdir(output_dir);
end

this_dir = fileparts(mfilename('fullpath'));
sampler = struct();
sampler.csv_path = fullfile(output_dir, sprintf('%s_cpu.csv', label));
sampler.stop_path = fullfile(output_dir, sprintf('.%s_cpu.stop', label));

if isfile(sampler.stop_path)
    delete(sampler.stop_path);
end

script_path = fullfile(this_dir, 'sample_cpu_usage.ps1');
arguments = sprintf([ ...
    '-NoProfile -ExecutionPolicy Bypass -File "%s" ' ...
    '-OutputPath "%s" -StopPath "%s" -IntervalSeconds 1'], ...
    script_path, sampler.csv_path, sampler.stop_path);

start_info = System.Diagnostics.ProcessStartInfo();
start_info.FileName = 'powershell.exe';
start_info.Arguments = arguments;
start_info.UseShellExecute = false;
start_info.CreateNoWindow = true;
sampler.process = System.Diagnostics.Process.Start(start_info);
pause(0.25);
end
