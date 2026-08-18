from __future__ import annotations

import argparse
import json
import socket
from pathlib import Path

from Modules.Digital_Twins.udp_protocol import (
    UdpProtocolError,
    observation_from_packet,
    packet_from_datagram,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Listen for live DT UDP observation packets."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=55002)
    parser.add_argument("--jsonl", default=None, help="Optional raw packet JSONL log.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.jsonl) if args.jsonl else None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.host, args.port))
    print(f"Listening for DT UDP observations on {args.host}:{args.port}")

    while True:
        datagram, sender = sock.recvfrom(65535)
        try:
            packet = packet_from_datagram(datagram)
            if packet.get("kind") != "observation":
                continue
            observation = observation_from_packet(packet)
        except UdpProtocolError as exc:
            print(f"ignored packet from {sender}: {exc}")
            continue

        if output_path is not None:
            with output_path.open("a", encoding="utf-8") as output_file:
                output_file.write(json.dumps(packet, sort_keys=True) + "\n")

        print(
            f"seq={packet.get('seq')} "
            f"t={observation.sim_time_s:.3f}s "
            f"SOC={observation.soc_pct:.2f}% "
            f"Vbus={observation.v_bus_v:.2f}V "
            f"Pbatt={observation.p_batt_w:.2f}W "
            f"faults={_active_faults(observation.fault_flags)}"
        )


def _active_faults(fault_flags: dict[str, bool]) -> str:
    active = [name for name, enabled in fault_flags.items() if enabled]
    return ",".join(active) if active else "-"


if __name__ == "__main__":
    main()
