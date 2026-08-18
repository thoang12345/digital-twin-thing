classdef DTUdpCommandReceiver < matlab.System
    %DTUDPCOMMANDRECEIVER Receive DT command packets inside a live simulation.
    %
    % Add this class to a MATLAB System block. The block listens for JSON
    % command packets produced by UdpLiveSimulinkBackend and outputs scalar
    % command signals for the Simulink controller:
    %
    %   p_batt_cmd_w, enable_cmd, mode_code, command_seq, command_age_s

    properties
        LocalPort (1, 1) double = 55000
        DefaultPCommandW (1, 1) double = 0.0
        DefaultEnable (1, 1) logical = true
        DefaultModeCode (1, 1) double = 0.0
        MaxCommandAgeS (1, 1) double = 10.0
    end

    properties(Access = private)
        Socket
        LastPCommandW (1, 1) double = 0.0
        LastEnable (1, 1) logical = true
        LastModeCode (1, 1) double = 0.0
        LastCommandSeq (1, 1) double = 0.0
        LastCommandTic
    end

    methods(Access = protected)
        function setupImpl(obj)
            obj.Socket = udpport( ...
                'datagram', 'IPV4', ...
                'LocalPort', obj.LocalPort, ...
                'Timeout', 0.001);
            obj.LastPCommandW = obj.DefaultPCommandW;
            obj.LastEnable = obj.DefaultEnable;
            obj.LastModeCode = obj.DefaultModeCode;
            obj.LastCommandSeq = 0.0;
            obj.LastCommandTic = tic;
        end

        function [p_batt_cmd_w, enable_cmd, mode_code, command_seq, command_age_s] = stepImpl(obj)
            obj.readAvailablePackets();

            command_age_s = toc(obj.LastCommandTic);
            if obj.MaxCommandAgeS > 0 && command_age_s > obj.MaxCommandAgeS
                p_batt_cmd_w = 0.0;
                enable_cmd = false;
                mode_code = 99.0;
            else
                p_batt_cmd_w = obj.LastPCommandW;
                enable_cmd = obj.LastEnable;
                mode_code = obj.LastModeCode;
            end
            command_seq = obj.LastCommandSeq;
        end

        function releaseImpl(obj)
            obj.Socket = [];
        end

        function resetImpl(obj)
            obj.LastPCommandW = obj.DefaultPCommandW;
            obj.LastEnable = obj.DefaultEnable;
            obj.LastModeCode = obj.DefaultModeCode;
            obj.LastCommandSeq = 0.0;
            obj.LastCommandTic = tic;
        end

        function num = getNumInputsImpl(~)
            num = 0;
        end

        function num = getNumOutputsImpl(~)
            num = 5;
        end

        function [name1, name2, name3, name4, name5] = getOutputNamesImpl(~)
            name1 = 'p_batt_cmd_w';
            name2 = 'enable_cmd';
            name3 = 'mode_code';
            name4 = 'command_seq';
            name5 = 'command_age_s';
        end

        function [dt1, dt2, dt3, dt4, dt5] = getOutputDataTypeImpl(~)
            dt1 = 'double';
            dt2 = 'boolean';
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
            c1 = false;
            c2 = false;
            c3 = false;
            c4 = false;
            c5 = false;
        end

        function [f1, f2, f3, f4, f5] = isOutputFixedSizeImpl(~)
            f1 = true;
            f2 = true;
            f3 = true;
            f4 = true;
            f5 = true;
        end
    end

    methods(Static, Access = protected)
        function simMode = getSimulateUsingImpl()
            simMode = 'Interpreted execution';
        end

        function flag = showSimulateUsingImpl()
            flag = false;
        end
    end

    methods(Access = private)
        function readAvailablePackets(obj)
            if isempty(obj.Socket)
                return;
            end

            while obj.Socket.NumDatagramsAvailable > 0
                datagram = read(obj.Socket, 1, 'uint8');
                try
                    text = obj.datagramToText(datagram);
                    packet = jsondecode(text);
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
                    obj.LastPCommandW = obj.readNumber(command, 'p_batt_cmd_w', 0.0);
                    obj.LastEnable = logical(obj.readNumber(command, 'enable', 1.0));
                    obj.LastModeCode = obj.readModeCode(command);
                    obj.LastCommandSeq = obj.readNumber(packet, 'seq', obj.LastCommandSeq);
                    obj.LastCommandTic = tic;
                catch
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
            elseif isstruct(datagram) && isfield(datagram, "Data")
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
            if isfield(payload, field_name)
                raw = payload.(field_name);
                if islogical(raw)
                    value = double(raw);
                elseif isnumeric(raw)
                    value = double(raw);
                elseif ischar(raw) || isstring(raw)
                    value = str2double(raw);
                    if isnan(value)
                        value = default_value;
                    end
                end
            end
        end

        function code = readModeCode(command)
            if isfield(command, 'mode_code')
                code = DTUdpCommandReceiver.readNumber(command, 'mode_code', 0.0);
                return;
            end
            if ~isfield(command, 'mode')
                code = 0.0;
                return;
            end
            mode = upper(strtrim(string(command.mode)));
            switch mode
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
