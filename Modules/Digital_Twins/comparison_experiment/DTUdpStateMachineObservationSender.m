classdef DTUdpStateMachineObservationSender < matlab.System
    %DTUDPSTATEMACHINEOBSERVATIONSENDER Publish the guarded DT state at 10 Hz.

    properties(Nontunable)
        RemoteHost (1, 1) string = "127.0.0.1"
        RemotePort (1, 1) double = 55001
        SampleTimeS (1, 1) double = 0.1
        SourcePowerLimitW (1, 1) double = 500.0
        MaxSafeChargeW (1, 1) double = 300.0
    end

    properties(Access = private)
        Socket
        PacketSeq (1, 1) double = 0.0
    end

    methods(Access = protected)
        function setupImpl(obj)
            obj.Socket = udpport('datagram', 'IPV4');
            obj.PacketSeq = 0.0;
        end

        function sent_seq = stepImpl(obj, sim_time_s, soc_pct, v_bus_v, ...
                v_batt_v, i_batt_a, p_batt_w, p_load_w, p_source_w, ...
                source_at_limit, source_available, state_code, ...
                command_seq, command_age_s)
            obj.PacketSeq = obj.PacketSeq + 1.0;

            observation = struct();
            observation.sim_time_s = double(sim_time_s);
            observation.soc_pct = double(soc_pct);
            observation.v_bus_v = double(v_bus_v);
            observation.v_batt_v = double(v_batt_v);
            observation.i_batt_a = double(i_batt_a);
            observation.p_batt_w = double(p_batt_w);
            observation.p_load_w = double(p_load_w);
            observation.p_source_w = double(p_source_w);
            observation.source_power_limit_w = double(obj.SourcePowerLimitW);
            observation.source_at_limit = logical(source_at_limit);
            observation.source_available = logical(source_available);
            observation.fault_flags = struct();
            % Keep the datagram comfortably below the 512-byte default used
            % by some Windows/udpport paths.  Python derives load consumption
            % and safe charge headroom from these core fields.
            observation.extra = struct('state_code', double(state_code));

            packet = struct();
            packet.protocol = 'dt_udp';
            packet.version = 1.0;
            packet.kind = 'observation';
            packet.seq = obj.PacketSeq;
            packet.observation = observation;

            try
                write(obj.Socket, uint8(jsonencode(packet)), 'uint8', ...
                    char(obj.RemoteHost), obj.RemotePort);
            catch
                % UDP telemetry is best effort.  Loss of incoming commands is
                % handled independently by the receiver's stale-command timer.
            end
            sent_seq = obj.PacketSeq;
        end

        function releaseImpl(obj)
            obj.Socket = [];
        end

        function resetImpl(obj)
            obj.PacketSeq = 0.0;
        end

        function sample_time = getSampleTimeImpl(obj)
            sample_time = createSampleTime( ...
                obj, ...
                'Type', 'Discrete', ...
                'SampleTime', obj.SampleTimeS, ...
                'OffsetTime', 0.0);
        end

        function num = getNumInputsImpl(~)
            num = 13;
        end

        function num = getNumOutputsImpl(~)
            num = 1;
        end

        function name = getOutputNamesImpl(~)
            name = 'sent_seq';
        end

        function dt = getOutputDataTypeImpl(~)
            dt = 'double';
        end

        function sz = getOutputSizeImpl(~)
            sz = [1 1];
        end

        function c = isOutputComplexImpl(~)
            c = false;
        end

        function f = isOutputFixedSizeImpl(~)
            f = true;
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
end
