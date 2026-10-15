#!/usr/bin/env python3
"""Read-only local host PID/thread observer for one fixed isolated Docker cohort.

Does not create/exec/stop containers or send signals. Writes only its fresh audit
directory. Run before the separately authorized native job and stop afterwards.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(f"Docker read-only command {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def local_endpoint():
    override = os.environ.get("DOCKER_HOST")
    context = docker("context", "show").strip()
    settings = json.loads(docker("context", "inspect", context))[0]
    endpoint = override or settings["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("unix://"):
        raise RuntimeError("Host /proc mapping requires a local Unix Docker endpoint")
    return {"context": context, "endpoint": endpoint}


def inspect_identity(container_id, expected_image):
    info = json.loads(docker("inspect", "--type", "container", container_id))[0]
    if info["Id"] != container_id or info["Image"] != expected_image:
        raise RuntimeError("Fixed container or image identity changed")
    host = info["HostConfig"]
    if host["NetworkMode"] != "none":
        raise RuntimeError("Native pilot requires network none")
    if host["IpcMode"] not in ("", "private") or host.get("PidMode", ""):
        raise RuntimeError("Native pilot requires private IPC and PID namespaces")
    return {"container_id": info["Id"], "image_id": info["Image"],
            "running": info["State"]["Running"], "host_init_pid": info["State"]["Pid"],
            "started_at": info["State"]["StartedAt"], "network_mode": host["NetworkMode"],
            "ipc_mode": host["IpcMode"], "pid_mode": host.get("PidMode", ""),
            "mounts": [{k: m[k] for k in ("Source", "Destination", "RW", "Type")} for m in info["Mounts"]]}


def parse_status(text):
    values = {}
    for line in text.splitlines():
        key, _, value = line.partition(":")
        if key in ("Name", "State", "Tgid", "Pid", "PPid", "Threads"):
            values[key] = value.strip()
        elif key in ("NSpid", "NStgid"):
            values[key] = [int(n) for n in value.split()]
    return values


def parse_stat(text):
    end = text.rfind(")")
    if end < 0:
        raise ValueError("Malformed proc stat")
    fields = text[end + 2:].split()
    return {"state": fields[0], "host_ppid": int(fields[1]), "host_pgid": int(fields[2]),
            "host_sid": int(fields[3]), "start_time_clock_ticks": int(fields[19])}


def parse_top(text):
    lines = [line.split(None, 5) for line in text.splitlines() if line.strip()]
    if not lines or lines[0][0] != "PID":
        raise ValueError("Unexpected docker top header")
    result = []
    for row in lines[1:]:
        if len(row) != 6:
            raise ValueError("Malformed docker top process row")
        result.append({"host_pid": int(row[0]), "host_ppid": int(row[1]),
                       "host_pgid": int(row[2]), "host_sid": int(row[3]), "state": row[4], "comm": row[5]})
    return result


def worker_role(argv):
    for i, token in enumerate(argv[:-1]):
        if token == "--worker" and argv[i + 1] in ("simulator", "inference"):
            return argv[i + 1]
    return None


def capture_pid(proc_root: Path, pid: int, container_id: str):
    root = proc_root / str(pid)
    stat = parse_stat((root / "stat").read_text())
    cgroup = (root / "cgroup").read_text()
    if not any(container_id in line.rsplit(":", 1)[-1].split("/")
               or f"docker-{container_id}.scope" in line.rsplit(":", 1)[-1].split("/")
               for line in cgroup.splitlines()):
        raise ValueError("Docker top PID no longer belongs to the exact container cgroup")
    status = parse_status((root / "status").read_text())
    if int(status["Pid"]) != pid or int(status["Tgid"]) != pid:
        raise ValueError("Expected host process leader identity")
    cmd = (root / "cmdline").read_bytes()
    argv = [a.decode(errors="replace") for a in cmd.split(b"\0") if a]
    role = worker_role(argv)
    namespaces = status.get("NSpid", [])
    if len(namespaces) < 2 or namespaces[0] != pid or namespaces[-1] <= 0:
        raise ValueError("Missing or inconsistent host/container PID namespace mapping")
    result = {"host_pid": pid, "container_pid": namespaces[-1] if len(namespaces) >= 2 else None,
              "nspid": namespaces, "role": role, "status": status, **stat,
              "cmdline_sha256": hashlib.sha256(cmd).hexdigest(),
              "program_basename": Path(argv[0]).name if argv else None, "command_writer_threads": [],
              "cgroup_sha256": hashlib.sha256(cgroup.encode()).hexdigest()}
    # Do not log arbitrary argv/credentials. Bind only the known worker's local output path.
    if role and "--output" in argv:
        index = argv.index("--output")
        if index + 1 < len(argv) and argv[index + 1].startswith("/outputs/"):
            result["worker_output"] = argv[index + 1]
    for task in sorted((root / "task").iterdir(), key=lambda p: int(p.name)):
        try:
            thread_stat = parse_stat((task / "stat").read_text())
            if (task / "comm").read_text().strip() != "command_writer":
                continue
            thread = parse_status((task / "status").read_text())
            if int(thread["Tgid"]) != pid or int(thread["Pid"]) != int(task.name):
                raise ValueError("Command-writer thread identity differs from owning process")
            thread_ns = thread.get("NSpid", [])
            thread_tgids = thread.get("NStgid", [])
            if (len(thread_ns) < 2 or thread_ns[0] != int(task.name)
                    or len(thread_tgids) < 2 or thread_tgids[0] != pid
                    or thread_tgids[-1] != result["container_pid"]):
                raise ValueError("Missing or inconsistent command-writer namespace mapping")
            if parse_stat((task / "stat").read_text())["start_time_clock_ticks"] != thread_stat["start_time_clock_ticks"]:
                raise ValueError("Command-writer TID was reused during observation")
            result["command_writer_threads"].append({"host_tid": int(task.name), "host_tgid": pid,
                "container_tid": thread_ns[-1] if len(thread_ns) >= 2 else None,
                "container_tgid": result["container_pid"], "nspid": thread_ns,
                "owner_start_time_clock_ticks": result["start_time_clock_ticks"],
                "nstgid": thread.get("NStgid", []), "status": thread,
                "start_time_clock_ticks": thread_stat["start_time_clock_ticks"]})
        except (FileNotFoundError, ProcessLookupError):
            # Normal sampling race: thread already exited, no identity is invented.
            continue
    # Reject a PID reused while reading its tasks rather than joining two lives.
    final_stat = parse_stat((root / "stat").read_text())
    if final_stat["start_time_clock_ticks"] != stat["start_time_clock_ticks"]:
        raise ValueError("Host PID was reused during observation")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--expected-image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--max-seconds", type=float, default=22500)
    args = parser.parse_args()
    if sys.platform != "linux" or not re.fullmatch(r"[0-9a-f]{64}", args.container_id):
        raise SystemExit("Require Linux and an exact full64hex container ID")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.expected_image):
        raise SystemExit("Require exact image config SHA256")
    if not 0.05 <= args.interval <= 5 or not 1 <= args.max_seconds <= 86400:
        raise SystemExit("Invalid bounded observation interval/duration")
    endpoint = local_endpoint()
    identity = inspect_identity(args.container_id, args.expected_image)
    if not identity["running"] or args.stop_file.exists():
        raise SystemExit("Container must be running and fresh stop-file absent")
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {"schema_version": 1, "scope": "Read-only fixed local Docker container and host proc; no exec/start/stop/signal",
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "start_utc": utc(), "endpoint": endpoint, "identity": identity,
               "interval_seconds": args.interval, "max_seconds": args.max_seconds}
    (args.output / "launch.json").write_text(json.dumps(receipt, indent=2) + "\n")
    started = time.monotonic()
    roles, writer_roles, mappings, errors = set(), set(), {}, []
    snapshots = 0
    reason = None
    try:
        with (args.output / "snapshots.jsonl").open("x") as log:
            while True:
                if args.stop_file.exists():
                    reason = "stop_file"
                    break
                if time.monotonic() - started >= args.max_seconds:
                    reason = "time_bound"
                    break
                current = inspect_identity(args.container_id, args.expected_image)
                if current["started_at"] != identity["started_at"]:
                    raise RuntimeError("Container was restarted during observation")
                if not current["running"]:
                    reason = "container_exited"
                    break
                event = {"utc": utc(), "monotonic": time.monotonic(), "processes": [], "raced_exit_pids": []}
                for row in parse_top(docker("top", args.container_id, "-eo", "pid,ppid,pgid,sid,stat,comm")):
                    try:
                        value = capture_pid(Path("/proc"), row["host_pid"], args.container_id)
                    except (FileNotFoundError, ProcessLookupError):
                        event["raced_exit_pids"].append(row["host_pid"])
                        continue
                    event["processes"].append(value)
                    role = value["role"]
                    if role:
                        roles.add(role)
                    for thread in value["command_writer_threads"]:
                        if role and thread["container_tid"] is not None and thread["container_tgid"] is not None:
                            writer_roles.add(role)
                        key = (thread["host_tid"], thread["start_time_clock_ticks"])
                        mapping = {"role": role, "worker_output": value.get("worker_output"), **thread}
                        if key not in mappings:
                            mappings[key] = mapping | {"first_observed_utc": event["utc"]}
                        mappings[key]["last_observed_utc"] = event["utc"]
                log.write(json.dumps(event, sort_keys=True) + "\n")
                log.flush()
                snapshots += 1
                time.sleep(args.interval)
    except BaseException as error:
        errors.append({"type": type(error).__name__, "message": str(error)})
        reason = "observation_failed"
    result = receipt | {"end_utc": utc(), "stop_reason": reason, "snapshots": snapshots,
                        "worker_roles_observed": sorted(roles), "command_writer_roles_mapped": sorted(writer_roles),
                        "command_writer_mappings": sorted(mappings.values(), key=lambda m: (m["host_tid"], m["start_time_clock_ticks"])),
                        "errors": errors, "native_exit_or_quality_verified": False}
    result["mapping_scope_complete"] = not errors and reason != "time_bound" and writer_roles == {"simulator", "inference"}
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"stop_reason": reason, "snapshots": snapshots, "command_writer_roles_mapped": sorted(writer_roles),
                      "mapping_scope_complete": result["mapping_scope_complete"]}))
    return 0 if result["mapping_scope_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
