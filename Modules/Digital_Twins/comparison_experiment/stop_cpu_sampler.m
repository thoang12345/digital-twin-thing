function stop_cpu_sampler(sampler)
%STOP_CPU_SAMPLER Ask the independent CPU sampler to finish cleanly.

file_id = fopen(sampler.stop_path, 'w');
if file_id ~= -1
    fprintf(file_id, 'stop\n');
    fclose(file_id);
end

try
    sampler.process.WaitForExit(10000);
catch
end

if isfile(sampler.stop_path)
    delete(sampler.stop_path);
end
end
