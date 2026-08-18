function ensure_lm_studio_headless()
%ENSURE_LM_STUDIO_HEADLESS Start the API server and load the experiment LLM.

lms_path = fullfile(getenv('USERPROFILE'), '.lmstudio', 'bin', 'lms.exe');
if ~isfile(lms_path)
    error('LM Studio CLI was not found: %s', lms_path);
end

[server_status, ~] = system(sprintf('"%s" server status', lms_path));
if server_status ~= 0
    [status, output] = system(sprintf( ...
        '"%s" server start --port 1234 --bind 127.0.0.1', lms_path));
    if status ~= 0
        error('Could not start the LM Studio server:\n%s', output);
    end
end

model_key = 'llama-3-groq-8b-tool-use';
[~, loaded_models] = system(sprintf('"%s" ps', lms_path));
if ~contains(loaded_models, 'llama-3-groq-8b-tool-use')
    command = sprintf([ ...
        '"%s" load "%s" --identifier llama-3-groq-8b-tool-use ' ...
        '--context-length 4096 --gpu max --yes'], lms_path, model_key);
    [status, output] = system(command);
    if status ~= 0
        error('Could not load the LM Studio model:\n%s', output);
    end
end

fprintf('LM Studio is serving llama-3-groq-8b-tool-use on port 1234.\n');
end
