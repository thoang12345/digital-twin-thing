classdef DTUdpStateMachineCommandReceiver < matlab.System
    %DTUDPSTATEMACHINECOMMANDRECEIVER Receive bounded supervisory intent.
    %
    % The receiver speaks the project's dt_udp v1 command protocol.  It does
    % not emit a converter command.  Instead it exposes the requested mode and
    % power magnitude to the local finite-state controller.  Missing, stale,
    % disabled, or SAFE commands are reported as invalid so Simulink retains
    % final authority.

    properties(Nontunable)
        LocalPort (1, 1) double = 55000
        SampleTimeS (1, 1) double = 0.1
        MaxCommandAgeS (1, 1) double = 15.0
    end

    properties(Access = private)
        Socket
        LastModeCode (1, 1) double = 99.0
        LastRequestedPowerW (1, 1) double = 0.0
        LastEnable (1, 1) logical = false
        LastCommandSeq (1, 1) double = 0.0
        LastCommandTic
    end

    methods(Access = protected)
        function setupImpl(obj)
            obj.Socket = udpport( ...
                'datagram', 'IPV4', ...
                'LocalPort', obj.LocalPort, ...
                'Timeout', 0.001);
            obj.resetState();
        end

        function [mode_code, requested_power_w, command_valid, command_seq, command_age_s] = stepImpl(obj)
            obj.readAvailablePackets();

            command_age_s = toc(obj.LastCommandTic);
            stale = obj.MaxCommandAgeS > 0 && command_age_s > obj.MaxCommandAgeS;
            command_valid = double( ...
                obj.LastEnable && ~stale && obj.LastModeCode ~= 99.0);

            if command_valid
                mode_code = obj.LastModeCode;
                requested_power_w = obj.LastRequestedPowerW;
            else
                mode_code = 99.0;
                requested_power_w = 0.0;
            end
            command_seq = obj.LastCommandSeq;
        end

        function releaseImpl(obj)
            obj.Socket = [];
        end

        function resetImpl(obj)
            obj.resetState();
        end

        function sample_time = getSampleTimeImpl(obj)
            sample_time = createSampleTime( ...
                obj, ...
                'Type', 'Discrete', ...
                'SampleTime', obj.SampleTimeS, ...
                'OffsetTime', 0.0);
        end

        function num = getNumInputsImpl(~)
            num = 0;
        end

        function num = getNumOutputsImpl(~)
            num = 5;
        end

        function [name1, name2, name3, name4, name5] = getOutputNamesImpl(~)
            name1 = 'requested_mode_code';
            name2 = 'requested_power_w';
            name3 = 'command_valid';
            name4 = 'command_seq';
            name5 = 'command_age_s';
        end

        function [dt1, dt2, dt3, dt4, dt5] = getOutputDataTypeImpl(~)
            dt1 = 'double';
            dt2 = 'double';
            dt3 = 'double';
            dt4 = 'double';
            dt5 = 'double';
        end

        function [sz1, sz2, sz3, sz4, sz5] = getOutputSizeImpl(~)
            sz1 = [1 1];
            sz2 = [1 1];
            sz3 = [1 1];
            sz4 = [1 1];
            sz5 = [1 1];
        end

        function [c1, c2, c3, c4, c5] = isOutputComplexImpl(~)
            c1 = false; c2 = false; c3 = false; c4 = false; c5 = false;
        end

        function [f1, f2, f3, f4, f5] = isOutputFixedSizeImpl(~)
            f1 = true; f2 = true; f3 = true; f4 = true; f5 = true;
        end
    end

    methods(Static, Access = protected)
        function sim_mode = getSimulateUsingImpl()
            sim_mode = 'Interpreted execution';
        end

        function flag = showSimulateUsingImpl()
            flag = false;
        end
    end

    methods(Access = private)
        function resetState(obj)
            obj.LastModeCode = 99.0;
            obj.LastRequestedPowerW = 0.0;
            obj.LastEnable = false;
            obj.LastCommandSeq = 0.0;
            obj.LastCommandTic = tic;
        end

        function readAvailablePackets(obj)
            if isempty(obj.Socket)
                return;
            end

            while obj.Socket.NumDatagramsAvailable > 0
                datagram = read(obj.Socket, 1, 'uint8');
                try
                    packet = jsondecode(obj.datagramToText(datagram));
                    if ~isfield(packet, 'protocol') || ~strcmp(char(packet.protocol), 'dt_udp')
                        continue;
                    end
                    if ~isfield(packet, 'version') || double(packet.version) ~= 1
                        continue;
                    end
                    if ~isfield(packet, 'kind') || ~strcmp(char(packet.kind), 'command')
                        continue;
                    end
                    if ~isfield(packet, 'command')
                        continue;
                    end

                    command = packet.command;
                    obj.LastModeCode = obj.readModeCode(command);
                    obj.LastRequestedPowerW = obj.readNumber(command, 'p_batt_cmd_w', 0.0);
                    obj.LastEnable = logical(obj.readNumber(command, 'enable', 1.0));
                    obj.LastCommandSeq = obj.readNumber(packet, 'seq', obj.LastCommandSeq);
                    obj.LastCommandTic = tic;
                catch
                    % Invalid datagrams are ignored; command-age protection
                    % deterministically moves the model to SAFE_LOCAL.
                end
            end
        end
    end

    methods(Static, Access = private)
        function text = datagramToText(datagram)
            if istable(datagram)
                raw = datagram.Data;
                if iscell(raw)
                    raw = raw{end};
                else
                    raw = raw(end, :);
                end
            elseif isstruct(datagram) && isfield(datagram, 'Data')
                raw = datagram.Data;
            elseif isobject(datagram) && isprop(datagram, 'Data')
                raw = datagram.Data;
            else
                raw = datagram;
            end
            if iscell(raw)
                raw = raw{end};
            end
            if isstring(raw)
                raw = char(raw);
            end
            text = char(raw(:).');
        end

        function value = readNumber(payload, field_name, default_value)
            value = default_value;
            if ~isfield(payload, field_name)
                return;
            end
            raw = payload.(field_name);
            if islogical(raw) || isnumeric(raw)
                value = double(raw);
            elseif ischar(raw) || isstring(raw)
                parsed = str2double(raw);
                if isfinite(parsed)
                    value = parsed;
                end
            end
        end

        function code = readModeCode(command)
            if isfield(command, 'mode_code')
                code = DTUdpStateMachineCommandReceiver.readNumber( ...
                    command, 'mode_code', 0.0);
                return;
            end
            if ~isfield(command, 'mode')
                code = 0.0;
                return;
            end
            switch upper(strtrim(string(command.mode)))
                case "CHARGE"
                    code = -1.0;
                case "DISCHARGE"
                    code = 1.0;
                case "SAFE"
                    code = 99.0;
                otherwise
                    code = 0.0;
            end
        end
    end
end
