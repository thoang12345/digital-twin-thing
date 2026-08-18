from __future__ import annotations

import argparse
import socket
import time

from Modules.Digital_Twins.types import DTCommand
from Modules.Digital_Twins.udp_protocol import make_command_packet, packet_to_datagram


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send repeated DT UDP command packets for receiver testing."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=55000)
    parser.add_argument(
        "--mode",
        choices=["CHARGE", "HOLD", "DISCHARGE", "SAFE"],
        default="DISCHARGE",
    )
    parser.add_argument("--power", type=float, default=100.0)
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--reason", default="manual UDP receiver test")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    command = _build_command(args.mode, args.power, args.reason)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for seq in range(1, args.count + 1):
            packet = make_command_packet(command=command, seq=seq)
            sock.sendto(packet_to_datagram(packet), (args.host, args.port))
            print(
                f"sent seq={seq} mode={command.mode} "
                f"p_batt_cmd_w={command.p_batt_cmd_w:.3f} "
                f"to {args.host}:{args.port}"
            )
            if seq < args.count:
                time.sleep(max(0.0, args.interval))
    finally:
        sock.close()


def _build_command(mode: str, power: float, reason: str) -> DTCommand:
    if mode == "CHARGE":
        return DTCommand.charge(power, reason=reason)
    if mode == "DISCHARGE":
        return DTCommand.discharge(power, reason=reason)
    if mode == "SAFE":
        return DTCommand.safe(reason=reason)
    return DTCommand.hold(reason=reason)


if __name__ == "__main__":
    main()
