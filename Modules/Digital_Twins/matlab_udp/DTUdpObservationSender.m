classdef DTUdpObservationSender < matlab.System
    %DTUDPOBSERVATIONSENDER Send live DT state packets from Simulink.
    %
    % Add this class to a MATLAB System block and wire scalar state signals
    % into the block. The block sends one JSON UDP observation packet every
    % SampleDecimation calls and outputs the latest packet sequence number.

    properties
        RemoteHost (1, 1) string = "127.0.0.1"
        RemotePort (1, 1) double = 55001
        SourceName (1, 1) string = "simulink"
        SampleDecimation (1, 1) double = 1.0
        SourcePowerLimitW (1, 1) double = NaN
        MaxSafeChargeW (1, 1) double = NaN
    end

    properties(Access = private)
        Socket
        PacketSeq (1, 1) double = 0.0
        SkipCounter (1, 1) double = 0.0
    end

    methods(Access = protected)
        function setupImpl(obj)
            obj.Socket = udpport("datagram", "IPV4");
            obj.PacketSeq = 0.0;
            obj.SkipCounter = 0.0;
        end

        function sent_seq = stepImpl( ...
                obj, ...
                sim_time_s, ...
                soc_pct, ...
                v_bus_v, ...
                v_batt_v, ...
                i_batt_a, ...
                p_batt_w, ...
                p_load_w, ...
                p_source_w, ...
                source_at_limit, ...
                source_available)

            obj.SkipCounter = obj.SkipCounter + 1.0;
            if obj.SkipCounter < max(1.0, obj.SampleDecimation)
                sent_seq = obj.PacketSeq;
                return;
            end
            obj.SkipCounter = 0.0;
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
            observation.source_at_limit = logical(source_at_limit);
            observation.source_available = logical(source_available);
            if isfinite(obj.SourcePowerLimitW)
                observation.source_power_limit_w = double(obj.SourcePowerLimitW);
            end
            if isfinite(obj.MaxSafeChargeW)
                observation.max_safe_charge_w = double(obj.MaxSafeChargeW);
            end
            observation.fault_flags = struct();
            observation.extra = struct();
            observation.extra.source = char(obj.SourceName);

            packet = struct();
            packet.protocol = "dt_udp";
            packet.version = 1.0;
            packet.kind = "observation";
            packet.seq = obj.PacketSeq;
            packet.sent_at_epoch_s = posixtime(datetime("now", "TimeZone", "UTC"));
            packet.observation = observation;

            try
                write( ...
                    obj.Socket, ...
                    uint8(jsonencode(packet)), ...
                    'uint8', ...
                    char(obj.RemoteHost), ...
                    obj.RemotePort);
            catch
            end

            sent_seq = obj.PacketSeq;
        end

        function releaseImpl(obj)
            obj.Socket = [];
        end

        function resetImpl(obj)
            obj.PacketSeq = 0.0;
            obj.SkipCounter = 0.0;
        end

        function num = getNumInputsImpl(~)
            num = 10;
        end

        function num = getNumOutputsImpl(~)
            num = 1;
        end

        function [name1, name2, name3, name4, name5, name6, name7, name8, name9, name10] = getInputNamesImpl(~)
            name1 = 'sim_time_s';
            name2 = 'soc_pct';
            name3 = 'v_bus_v';
            name4 = 'v_batt_v';
            name5 = 'i_batt_a';
            name6 = 'p_batt_w';
            name7 = 'p_load_w';
            name8 = 'p_source_w';
            name9 = 'source_at_limit';
            name10 = 'source_available';
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
        function simMode = getSimulateUsingImpl()
            simMode = 'Interpreted execution';
        end

        function flag = showSimulateUsingImpl()
            flag = false;
        end
    end
end
