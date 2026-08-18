function finish_llm_supervisor(process, output_dir)
%FINISH_LLM_SUPERVISOR Wait for the runner and save its console transcript.

finished = process.WaitForExit(30000);
if ~finished
    warning('The UDP supervisor did not exit within 30 seconds of model completion.');
    return;
end

stdout_text = char(process.StandardOutput.ReadToEnd());
stderr_text = char(process.StandardError.ReadToEnd());
transcript_path = fullfile(output_dir, 'llm_runner_console.txt');
file_id = fopen(transcript_path, 'w');
if file_id ~= -1
    fprintf(file_id, '%s', stdout_text);
    if strlength(string(stderr_text)) > 0
        fprintf(file_id, '\n--- STDERR ---\n%s', stderr_text);
    end
    fclose(file_id);
end

if process.ExitCode ~= 0
    error('The UDP supervisor exited with status %d. See %s.', ...
        process.ExitCode, transcript_path);
end
end
