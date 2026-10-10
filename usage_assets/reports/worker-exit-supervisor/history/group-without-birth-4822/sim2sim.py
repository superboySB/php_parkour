#!/usr/bin/env python3
"""Bounded, recorded PHP MuJoCo rollout through native DDS and depth SHM.

The orchestrator launches simulation and inference in their respective Docker
Python environments. Automated input replaces keyboard events only. Simulation,
the D435i camera, depth shared memory, SDK transport and ONNX policy remain the
official Holosoma implementations. Reports distinguish execution from skill
success; this harness does not assert obstacle-course completion.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import os
import random
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOLOSOMA = ROOT / "thirdparty/holosoma"


def save(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def process_identity(pid: int) -> dict:
    """Raw Linux namespace identity; NSpid may omit the host namespace."""
    value = {"pid": pid, "pid_namespace": "current container", "observed_unix": time.time()}
    proc = Path("/proc") / str(pid)
    try:
        status = {}
        for line in (proc / "status").read_text().splitlines():
            key, _, data = line.partition(":")
            if key in ("Name", "Pid", "PPid", "Tgid", "NSpid", "Threads"):
                status[key] = data.strip()
        value["proc_status"] = status
        stat = (proc / "stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        value.update(state=fields[0], process_group_id=int(fields[2]), session_id=int(fields[3]),
                     start_time_clock_ticks=int(fields[19]))
        value["cmdline"] = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
    except OSError as error:
        value["proc_unavailable"] = str(error)
    return value


def process_return_status(process) -> dict:
    """A wrapper's positive exit code does not reveal its child's signal."""
    code = process.poll()
    number = -code if code is not None and code < 0 else None
    try:
        name = signal.Signals(number).name if number is not None else None
    except ValueError:
        name = "UNKNOWN"
    return {"returncode": code, "signal_number": number, "signal_name": name,
            "exit_code": code if code is not None and code >= 0 else None,
            "status": "running" if code is None else "exited",
            "scope": "direct Popen process; wrappers may mask a native child signal"}


def process_group_members(pgid: int, sid: int) -> list[dict]:
    """Observe non-zombie members of this exact private group/session."""
    members = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            stat = (proc / "stat").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        fields = stat[stat.rfind(")") + 2:].split()
        if int(fields[2]) == pgid and int(fields[3]) == sid and fields[0] != "Z":
            members.append({"pid": int(proc.name), "state": fields[0], "parent_pid": int(fields[1]),
                            "process_group_id": int(fields[2]), "session_id": int(fields[3]),
                            "start_time_clock_ticks": int(fields[19])})
    return sorted(members, key=lambda value: value["pid"])


def worker_group_status(group: dict) -> dict:
    try:
        return group | {"live_members": process_group_members(group["process_group_id"], group["session_id"])}
    except (OSError, ValueError, IndexError) as error:
        return group | {"live_members": None, "observation_error": str(error)}


def wait_worker_shutdown(process, group: dict, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return False
    while process_group_members(group["process_group_id"], group["session_id"]):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def signal_worker_group(group: dict, number: int) -> bool:
    pgid, sid = group["process_group_id"], group["session_id"]
    if pgid <= 1 or pgid != sid or pgid == os.getpgrp():
        raise RuntimeError("Refusing to signal an unisolated or parent process group")
    if not process_group_members(pgid, sid):
        return False
    try:
        os.killpg(pgid, number)
    except ProcessLookupError:
        return False
    return True


def simulator(config: dict, output: Path) -> None:
    import numpy as np
    from holosoma.config_types.run_sim import RunSimConfig
    from holosoma.simulator.base_simulator.hooks import Phase
    from holosoma.utils.config_registry import parse_config
    from holosoma.utils.sim_utils import DirectSimulation, setup_simulation_environment

    os.chdir(HOLOSOMA)
    random.seed(config["seed"])
    np.random.seed(config["seed"])
    terrain = "terrain-locomotion-plane" if config["terrain"] == "plane" else "terrain-load-step"
    cli = ["robot:g1-29dof", "sensor.d435i_front_depth:g1-d435i-front-depth", "plugin.depth:depth-shm-d435i",
           f"terrain:{terrain}", "--robot.asset.xml-file", "g1/g1_29dof_halfspherehand.xml",
           "--simulator.config.bridge.enabled", "True", "--simulator.config.bridge.interface", "lo",
           "--simulator.config.sim.fps", "500", "--simulator.config.sim.control-decimation", "10",
           "--simulator.config.virtual-gantry.length", "0.5", "--training.headless", "True", "--training.seed", str(config["seed"]), "--device", "cpu",
           "--simulator.config.debug-viz", "False",
           "--logger.video.enabled", "True", "--logger.video.width", "640", "--logger.video.height", "360",
           "--logger.video.save-dir", str(output / "video"), "--logger.video.upload-to-wandb", "False",
           "--logger.video.show-command-overlay", "False"]
    if config.get("mesh"):
        cli += ["--terrain.terrain-term.obj-file-path", config["mesh"]]
    cfg = parse_config(RunSimConfig, args=cli)
    env, device, app = setup_simulation_environment(cfg, device="cpu")
    rows = []
    started = time.monotonic()
    policy_ready_step = None
    released_at = None
    released_step = None
    with DirectSimulation(cfg, env, device, app) as direct:
        sim = direct.simulator
        save(output / "sim-ready.json", {"ready": True, "pid": os.getpid(), "cli": cli})
        step = 0
        dt = 1.0 / cfg.simulator.config.sim.fps
        decimation = cfg.simulator.config.sim.control_decimation_steps
        deadline = started
        while not (output / "stop").exists():
            now = time.monotonic()
            if now - started > config["wall_timeout"]:
                raise TimeoutError("Inference failed to complete within the bounded rollout time")
            if policy_ready_step is None and (output / "policy-ready.json").exists():
                policy_ready_step = step
            if policy_ready_step is not None and released_at is None:
                # Send stiff startup targets while slowly removing support.
                progress = min(((step - policy_ready_step) * dt) / config["settle_seconds"], 1.0)
                root_position = sim.robot_root_states[0, :3].detach().cpu().numpy()
                zero_force_length = float(np.linalg.norm(sim.virtual_gantry.point - root_position))
                sim.virtual_gantry.length = 0.5 + (zero_force_length - 0.5) * progress
                if progress >= 1.0:
                    sim.virtual_gantry.set_enable(False)
                    released_at = now
                    released_step = step
                    save(output / "released.json", {"gantry_enabled": False, "wall_elapsed": now - started, "simulation_seconds": step * dt})
            if step % decimation == 0:
                sim.hooks.emit(Phase.FRAME_BEGIN)
            sim.hooks.emit(Phase.PRE_STEP)
            sim.simulate_at_each_physics_step()
            sim.hooks.emit(Phase.POST_STEP)
            if step % decimation == 0:
                sim.hooks.emit(Phase.FRAME_END)
                state = sim.robot_root_states[0, :].detach().cpu().numpy().copy()
                if not np.isfinite(state).all():
                    raise ValueError("MuJoCo robot state contains non-finite values")
                x, y, z = state[:3]
                qx, qy, qz, qw = state[3:7]
                elapsed = (step - released_step) * dt if released_step is not None else -1.0
                yaw = float(np.arctan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz)))
                save(output / "sim-clock.json", {"step": step, "simulation_seconds": step * dt, "policy_seconds": elapsed,
                                                "root_position_xyz": [float(x), float(y), float(z)], "base_yaw_rad": yaw,
                                                "base_up_z": float(1 - 2 * (qx * qx + qy * qy))})
                rows.append([elapsed, float(x), float(y), float(z), float(1 - 2 * (qx * qx + qy * qy)), int(sim.virtual_gantry.enabled), yaw])
                if policy_ready_step is not None:
                    # Software rendering can be slower than real time. Preserve
                    # the training control period (10 physics steps = 20 ms)
                    # rather than running many policies against an unchanged
                    # state. SDK communication remains the native DDS path.
                    ack_deadline = time.monotonic() + 30
                    while not (output / "stop").exists():
                        acknowledgement = output / "control-ack.json"
                        if acknowledgement.exists() and json.loads(acknowledgement.read_text())["step"] >= step:
                            break
                        if time.monotonic() > ack_deadline:
                            raise TimeoutError("Policy did not acknowledge a control frame")
                        time.sleep(0.001)
            step += 1
            deadline += dt
            delay = deadline - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            elif delay < -0.25:
                deadline = time.monotonic()
    with (output / "trajectory.csv").open("w") as file:
        writer = csv.writer(file)
        writer.writerow(["policy_seconds", "x_m", "y_m", "pelvis_z_m", "base_up_z", "gantry_enabled", "base_yaw_rad"])
        writer.writerows(rows)
    active = np.asarray([r for r in rows if r[0] >= 0])
    if not len(active):
        raise RuntimeError("No unsupported policy rollout samples were recorded")
    save(output / "simulation.json", {"status": "completed", "physics_steps": step, "active_samples": len(active),
         "policy_simulation_seconds": float(active[-1, 0]), "simulation_seconds": step * dt,
         "wall_seconds": time.monotonic() - started, "physics_fps_measured": step / (time.monotonic() - started),
         "displacement_xy_m": (active[-1, 1:3] - active[0, 1:3]).tolist(),
         "path_length_xy_m": float(np.linalg.norm(np.diff(active[:, 1:3], axis=0), axis=1).sum()),
         "heading_change_deg": float(np.degrees(np.unwrap(active[:, 6])[-1] - active[0, 6])),
         "minimum_pelvis_height_m": float(active[:, 3].min()), "minimum_base_up_z": float(active[:, 4].min()),
         "final_position_xyz_m": active[-1, 1:4].tolist(), "final_base_up_z": float(active[-1, 4]),
         "low_pelvis_detected": bool(np.any(active[:, 3] < 0.4)),
         "tilt_threshold_sample_seconds": float(np.count_nonzero(active[:, 4] < 0.35) * dt * decimation),
         "fall_detected": bool(np.any((active[:, 3] < 0.4) | (active[:, 4] < 0.35))),
         "fall_criterion": "pelvis height < 0.4 m OR base upright cosine < 0.35 after gantry release",
         "fall_detection_is_heuristic": True,
         "gantry_disabled_during_policy": bool(np.all(active[:, 5] == 0))})


def inference(config: dict, output: Path) -> None:
    import numpy as np
    import onnxruntime as ort
    from holosoma_inference.config.config_values.inference import g1_wbt_distillation_d435i
    from holosoma_inference.inputs.api.commands import StateCommand
    from holosoma_inference.policies.depth_distillation import DepthDistillationPolicy
    random.seed(config["seed"])
    np.random.seed(config["seed"])

    class AutomaticInput:
        def start(self):
            pass
        def stop(self):
            pass
        def poll_velocity(self):
            return None
        def poll_commands(self):
            return []

    preset = g1_wbt_distillation_d435i
    cfg = dataclasses.replace(preset, task=dataclasses.replace(preset.task,
          model_path=[str(Path(config["models"]) / "depth_backbone.onnx"), str(Path(config["models"]) / "student.onnx")],
          interface="lo", velocity_input="injected", state_input="injected",
          record_dir=str(output / "policy-recording"), record_label="rollout"))
    policy = DepthDistillationPolicy.__new__(DepthDistillationPolicy)
    provider = AutomaticInput()
    policy._injected_velocity_input = provider
    policy._injected_command_provider = provider
    options = ort.SessionOptions()
    options.intra_op_num_threads = config["ort_threads"]
    # Configure the native policy's real ONNX sessions without copying its
    # model-loading, observation or action logic into this harness.
    original_session = ort.InferenceSession
    def configured_session(*values, **kwargs):
        kwargs.setdefault("sess_options", options)
        return original_session(*values, **kwargs)
    ort.InferenceSession = configured_session
    try:
        DepthDistillationPolicy.__init__(policy, cfg)
    finally:
        ort.InferenceSession = original_session
    policy._handle_init_state()
    save(output / "policy-ready.json", {"ready": True, "pid": os.getpid(), "rate_hz": policy.rl_rate})
    policy_started = None
    commands = []
    ticks = 0
    command_position = -1
    samples = []
    last_control_step = -1
    try:
        while not (output / "stop").exists():
            clock_file = output / "sim-clock.json"
            if not clock_file.exists():
                time.sleep(0.001)
                continue
            clock = json.loads(clock_file.read_text())
            if clock["step"] == last_control_step:
                time.sleep(0.001)
                continue
            last_control_step = clock["step"]
            if policy_started is None and (output / "released.json").exists():
                policy._handle_start_policy()
                if config.get("record_policy"):
                    policy._dispatch_command(StateCommand.TOGGLE_RECORDING)
                policy_started = time.monotonic()
            if policy_started is not None:
                elapsed = max(0.0, clock["policy_seconds"])
                index = min(int(elapsed / config["seconds_per_command"]), len(config["commands"]) - 1)
                if index != command_position:
                    code = config["commands"][index]
                    policy.speed_mode = 1 if 6 <= code <= 10 else 0
                    policy.set_velocity_command(code)
                    commands.append({"seconds": elapsed, "code": code, "name": policy._command_name(code)})
                    command_position = index
                if elapsed >= config["duration"]:
                    break
                if config.get("course_guide"):
                    # A human operator normally steers with direction keys.
                    # This explicit test mode supplies equivalent existing
                    # one-hot commands from root pose; it is not an extra
                    # capability learned by the released locomotion policy.
                    # Unitree LowState contains no world position; the native
                    # interface fills it with zeros. Use simulator ground truth
                    # for this explicitly external input controller only.
                    state = clock["root_position_xyz"]
                    yaw, upright = clock["base_yaw_rad"], clock["base_up_z"]
                    target = float(np.arctan2(-state[1], 2.0))
                    error = float(np.arctan2(np.sin(target - yaw), np.cos(target - yaw)))
                    code = 0 if state[0] > 62 else (7 if error > 0.10 else 9 if error < -0.10 else 6)
                    if upright < 0.85:
                        code = 6
                    if code != policy.active_velocity_command_idx:
                        policy.speed_mode = 1 if 6 <= code <= 10 else 0
                        policy.set_velocity_command(code)
                        commands.append({"seconds": elapsed, "code": code, "name": policy._command_name(code), "source": "explicit course heading guide", "heading_error_rad": error})
            policy.latency_tracker.start_cycle()
            policy.policy_action()
            policy.latency_tracker.end_cycle()
            save(output / "control-ack.json", {"step": last_control_step})
            if policy_started is not None:
                if not np.isfinite(policy.cmd_q).all():
                    raise ValueError("Non-finite commanded joint targets")
                samples.append({"wall_seconds": time.monotonic() - policy_started, "simulation_seconds": elapsed, "command": policy.active_velocity_command_idx,
                                "target_min": float(policy.cmd_q.min()), "target_max": float(policy.cmd_q.max()),
                                "action_l2": float(np.linalg.norm(policy.last_policy_action))})
                ticks += 1
        policy._handle_stop_policy()
        lifecycle = {"damping_mode_active": bool(policy._damping_mode_active), "policy_action_disabled": not policy.use_policy_action}
        if config.get("record_policy"):
            # Exercise the actual manual-command/send path once after STOP.
            manual = policy._get_manual_command(policy.interface.get_low_state())
            if not np.all(manual["kp"] == 0) or not np.all(manual["kd"] > 0):
                raise ValueError("Native STOP did not produce zero stiffness and positive damping")
            policy.policy_action()
            lifecycle.update(damping_command_sent=True, damping_kp_max=float(np.max(manual["kp"])), damping_kd_min=float(np.min(manual["kd"])))
            recordings = sorted((output / "policy-recording").glob("*.npz"))
            if not recordings:
                raise RuntimeError("Native recording toggle/autosave did not write a clip")
            clips = []
            for path in recordings:
                with np.load(path, allow_pickle=False) as clip:
                    qpos, vel_cmd, fps = clip["qpos"], clip["vel_cmd"], int(clip["fps"])
                    if qpos.shape != (ticks, 36) or vel_cmd.shape != (ticks, 15) or fps != 50:
                        raise ValueError(f"Unexpected native recording schema: {path}")
                    if not np.isfinite(qpos).all() or not np.isfinite(vel_cmd).all():
                        raise ValueError("Native recording contains non-finite values")
                    if not np.allclose(np.linalg.norm(qpos[:, :4], axis=1), 1, atol=1e-3):
                        raise ValueError("Native recorded quaternion is not normalized")
                    clips.append({"file": str(path.relative_to(output)), "frames": ticks, "fps": fps, "qpos_shape": list(qpos.shape), "vel_cmd_shape": list(vel_cmd.shape),
                                  "qpos_layout": "native SDK wxyz quaternion, xyz root placeholders, 29 joints; inference recording format",
                                  "root_positions_are_zero_placeholders": True})
            lifecycle["recording_toggle_and_stop_autosave"] = clips
        save(output / "inference.json", {"status": "completed", "ticks": ticks, "commands": commands, "samples": samples,
             "control_period_simulation_seconds": 0.02, "onnxruntime_intra_op_threads": config["ort_threads"],
             "lifecycle": lifecycle,
             "transport": "official Unitree SDK DDS on lo; official depth shared memory", "input": "automated injected commands"})
    finally:
        (output / "stop").touch()
        if hasattr(policy.interface, "close"):
            policy.interface.close()
        if hasattr(policy._depth_sensor, "stop"):
            policy._depth_sensor.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--terrain", choices=("plane", "step", "custom"), default="plane")
    parser.add_argument("--mesh", type=Path)
    parser.add_argument("--commands", default="1", help="Comma-separated deployed command indices 0..11; all tests the twelve deployed directions")
    parser.add_argument("--seconds-per-command", type=float, default=8)
    parser.add_argument("--isolate-commands", action="store_true", help="Launch a fresh simulator/policy per command so a fall cannot contaminate later commands")
    parser.add_argument("--record-policy", action="store_true", help="Test native recording toggle, autosave on STOP, and damping command delivery")
    parser.add_argument("--python-faulthandler", action="store_true", help="New cohort only: enable Python fatal-signal tracebacks in both worker logs")
    parser.add_argument("--course-guide", action="store_true", help="For bundled step course only: external test input controller steers existing high-speed commands toward +X/y=0 and stands after x>62 m; not learned navigation")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gl", choices=("osmesa", "egl"), default="osmesa", help="CPU OSMesa by default; EGL uses NVIDIA graphics")
    parser.add_argument("--ort-threads", type=int, default=1, help="CPU ONNX threads; avoids contention with software rendering")
    parser.add_argument("--settle-seconds", type=float, default=3)
    parser.add_argument("--startup-timeout", type=float, default=180)
    parser.add_argument("--wall-timeout", type=float, help="Maximum wall seconds, independent of requested simulated duration")
    parser.add_argument("--sim-python", default=os.environ.get("HSSIM_PYTHON", "/opt/php/bin/train-python"))
    parser.add_argument("--inference-python", default=os.environ.get("PHP_INFERENCE_PYTHON", "/opt/php/bin/inference-python"))
    parser.add_argument("--worker", choices=("simulator", "inference"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.worker:
        save(output / f"{args.worker}-process-start.json", {"role": args.worker, "argv": sys.argv,
             "process": process_identity(os.getpid()), "python_faulthandler": os.environ.get("PYTHONFAULTHANDLER")})
        config = json.loads((output / "run.json").read_text())
        try:
            (simulator if args.worker == "simulator" else inference)(config, output)
        except BaseException as error:
            save(output / f"{args.worker}-error.json", {"error": str(error), "traceback": traceback.format_exc()})
            (output / "stop").touch()
            raise
        return
    if not (Path("/.dockerenv").exists() or os.environ.get("PHP_DOCKER") == "1"):
        parser.error("Run this harness inside the research Docker")
    if args.models is None:
        parser.error("--models is required")
    for name in ("depth_backbone.onnx", "student.onnx"):
        if not (args.models / name).is_file():
            parser.error(f"Missing {args.models / name}")
    commands = list(range(12)) if args.commands == "all" else [int(x) for x in args.commands.split(",")]
    if not commands or any(x < 0 or x > 11 for x in commands):
        parser.error("Deployed commands must be indices 0..11; ONNX validation covers reserved indices 12..14")
    if min(args.seconds_per_command, args.settle_seconds, args.startup_timeout) <= 0:
        parser.error("Durations must be positive")
    if args.ort_threads < 1:
        parser.error("--ort-threads must be positive")
    if args.terrain == "custom" and (args.mesh is None or not args.mesh.is_file()):
        parser.error("--terrain custom requires an existing --mesh OBJ")
    if args.course_guide and (args.terrain != "step" or commands != [6]):
        parser.error("--course-guide requires --terrain step --commands 6")
    if output.exists() and any(output.iterdir()):
        parser.error("Use an empty output directory so readiness markers and evidence cannot be reused")
    output.mkdir(parents=True, exist_ok=True)
    if args.isolate_commands and len(commands) > 1:
        results = []
        for code in commands:
            command = [sys.executable, str(Path(__file__).resolve()), "--models", str(args.models.resolve()), "--output", str(output / f"command-{code:02d}"),
                       "--terrain", args.terrain, "--commands", str(code), "--seconds-per-command", str(args.seconds_per_command),
                       "--settle-seconds", str(args.settle_seconds), "--startup-timeout", str(args.startup_timeout), "--seed", str(args.seed),
                       "--gl", args.gl, "--ort-threads", str(args.ort_threads),
                       "--sim-python", args.sim_python, "--inference-python", args.inference_python]
            if args.mesh:
                command += ["--mesh", str(args.mesh.resolve())]
            if args.wall_timeout:
                command += ["--wall-timeout", str(args.wall_timeout)]
            if args.record_policy:
                command += ["--record-policy"]
            if args.python_faulthandler:
                command += ["--python-faulthandler"]
            result = subprocess.run(command, check=False)
            report = output / f"command-{code:02d}" / "result.json"
            results.append({"command": code, "returncode": result.returncode, "report": str(report),
                            "result": json.loads(report.read_text()) if report.exists() else None})
        save(output / "matrix.json", {"seed": args.seed, "isolated_commands": True, "terrain": args.terrain, "commands": results,
                                      "status": "completed" if all(r["returncode"] == 0 for r in results) else "failed",
                                      "survived_commands": sum(bool(r["result"] and r["result"].get("survival_passed")) for r in results),
                                      "tested_commands": len(results),
                                      "quality_verified": False})
        if any(r["returncode"] != 0 for r in results):
            raise SystemExit(1)
        return
    config = {"models": str(args.models.resolve()), "terrain": args.terrain, "mesh": str(args.mesh.resolve()) if args.mesh else None,
              "model_sha256": {name: hashlib.sha256((args.models / name).read_bytes()).hexdigest() for name in ("depth_backbone.onnx", "student.onnx")},
              "mesh_sha256": hashlib.sha256(args.mesh.read_bytes()).hexdigest() if args.mesh else None,
              "commands": commands, "duration": len(commands) * args.seconds_per_command, "seconds_per_command": args.seconds_per_command,
              "record_policy": args.record_policy,
              "python_faulthandler": args.python_faulthandler,
              "course_guide": args.course_guide,
              "settle_seconds": args.settle_seconds, "startup_timeout": args.startup_timeout, "seed": args.seed, "gl": args.gl, "ort_threads": args.ort_threads,
              "egl_device_id": os.environ.get("MUJOCO_EGL_DEVICE_ID", "0") if args.gl == "egl" else None,
              "wall_timeout": args.wall_timeout or (args.startup_timeout + len(commands) * args.seconds_per_command * 20 + args.settle_seconds + 30),
              "scope": "native closed-loop rollout, not an assertion of skill success"}
    save(output / "run.json", config)
    env = os.environ | {"MUJOCO_GL": args.gl, "PYOPENGL_PLATFORM": args.gl, "LOGURU_LEVEL": "INFO",
                        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "MUJOCO_EGL_DEVICE_ID": os.environ.get("MUJOCO_EGL_DEVICE_ID", "0")}
    if args.python_faulthandler:
        env["PYTHONFAULTHANDLER"] = "1"
    script = str(Path(__file__).resolve())
    processes = []
    worker_roles = []
    worker_launches = []
    worker_identities = []
    worker_groups = []
    worker_events = []
    files = []
    started = time.monotonic()
    parent_identity = process_identity(os.getpid())

    def record_workers(event: str, **detail) -> dict:
        workers = [{"role": role, "launch": launch, "identity_at_spawn": identity,
                    "process_group": worker_group_status(group),
                    **process_return_status(process)}
                   for role, launch, identity, group, process in zip(worker_roles, worker_launches, worker_identities, worker_groups, processes)]
        entry = {"event": event, "observed_unix": time.time(),
                 "elapsed_seconds": time.monotonic() - started, "workers": workers, **detail}
        worker_events.append(entry)
        save(output / "worker-processes.json", {"schema_version": 1, "parent": parent_identity,
             "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             "python_faulthandler": env.get("PYTHONFAULTHANDLER"), "events": worker_events})
        return entry

    record_workers("orchestrator_started")
    try:
        for role, executable in (("simulator", args.sim_python), ("inference", args.inference_python)):
            if role == "inference":
                while not (output / "sim-ready.json").exists():
                    if processes[0].poll() is not None:
                        raise RuntimeError("Simulator exited before initialization; inspect simulator.log")
                    if time.monotonic() - started > args.startup_timeout:
                        raise TimeoutError("Simulator initialization timeout")
                    time.sleep(0.2)
            log = (output / f"{role}.log").open("w")
            files.append(log)
            launch = [executable, script, "--worker", role, "--output", str(output)]
            process = subprocess.Popen(launch, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            processes.append(process)
            worker_roles.append(role)
            worker_launches.append(launch)
            worker_groups.append({"process_group_id": process.pid, "session_id": process.pid,
                                  "source": "Popen start_new_session=True; private session/group leader PID"})
            worker_identities.append({"pid": process.pid})
            worker_identities[-1].update(process_identity(process.pid))
            record_workers("worker_spawned", role=role)
            identity = worker_identities[-1]
            if (("process_group_id" in identity and identity["process_group_id"] != process.pid)
                    or ("session_id" in identity and identity["session_id"] != process.pid)):
                raise RuntimeError("Worker did not remain in its expected private session/group")
        timeout = config["wall_timeout"]
        while any(process.poll() is None for process in processes):
            if any(process.poll() not in (None, 0) for process in processes):
                raise RuntimeError("A worker failed; inspect worker logs and error JSON")
            if time.monotonic() - started > timeout:
                raise TimeoutError("Closed-loop rollout exceeded its time bound")
            time.sleep(0.2)
        terminal = record_workers("workers_loop_complete")
        if any(worker["returncode"] != 0 for worker in terminal["workers"]):
            raise RuntimeError("Workers ended with nonzero status; inspect worker-processes.json and worker logs")
        if any(worker["process_group"]["live_members"] != [] for worker in terminal["workers"]):
            raise RuntimeError("Worker process groups remain live or unobservable after direct workers exited")
        summary = {"status": "completed", "elapsed_seconds": time.monotonic() - started, "config": config,
                   "worker_status_report": "worker-processes.json", "worker_status_at_completion": terminal,
                   "simulation": json.loads((output / "simulation.json").read_text()),
                   "inference": {k: v for k, v in json.loads((output / "inference.json").read_text()).items() if k != "samples"},
                   "videos": [str(p.relative_to(output)) for p in sorted((output / "video").glob("**/*.mp4"))],
                   "quality_verified": False, "obstacle_course_completion_verified": False}
        if not summary["videos"]:
            raise RuntimeError("Rollout completed but no MP4 was saved")
        summary["video_checks"] = []
        for relative in summary["videos"]:
            video = output / relative
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=codec_name,width,height,nb_frames,avg_frame_rate:format=duration", "-of", "json", str(video)],
                                   text=True, capture_output=True, check=True)
            details = json.loads(probe.stdout)
            duration = float(details["format"]["duration"])
            if duration <= 0:
                raise ValueError(f"Recorded video has no duration: {video}")
            thumbnail = video.with_suffix(".png")
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(duration / 2),
                            "-i", str(video), "-frames:v", "1", str(thumbnail)], check=True)
            summary["video_checks"].append({"video": relative, "probe": details, "thumbnail": str(thumbnail.relative_to(output))})
        summary["survival_passed"] = not summary["simulation"]["fall_detected"]
        save(output / "result.json", summary)
        print(json.dumps(summary, indent=2))
    except BaseException as error:
        detected = record_workers("error_detected", error_type=type(error).__name__, error=str(error))
        save(output / "error.json", {"status": "failed", "error": str(error), "elapsed_seconds": time.monotonic() - started,
             "worker_status_at_error": detected, "worker_status_report": "worker-processes.json"})
        raise
    finally:
        cleanup_errors = []
        unreaped_roles = []

        def cleanup_call(function, *arguments, **keywords):
            try:
                return function(*arguments, **keywords)
            except BaseException as error:
                cleanup_errors.append(error)

        cleanup_call((output / "stop").touch)
        cleanup_call(record_workers, "finally_enter")
        try:
            for role, process, group in zip(worker_roles, processes, worker_groups):
                try:
                    if not wait_worker_shutdown(process, group, 10):
                        signalled = signal_worker_group(group, signal.SIGTERM)
                        cleanup_call(record_workers, "terminate_requested", role=role, group_signalled=signalled)
                        if not wait_worker_shutdown(process, group, 5):
                            signalled = signal_worker_group(group, signal.SIGKILL)
                            cleanup_call(record_workers, "kill_requested", role=role, group_signalled=signalled)
                            if not wait_worker_shutdown(process, group, 5):
                                unreaped_roles.append(role)
                except BaseException as error:
                    cleanup_errors.append(error)
                    unreaped_roles.append(role)
        finally:
            if unreaped_roles:
                cleanup_errors.append(RuntimeError("Worker process groups remain unreaped: " + ", ".join(unreaped_roles)))
            cleanup_call(record_workers, "finally_wait_complete", unreaped_roles=unreaped_roles,
                         cleanup_errors=[{"type": type(error).__name__, "error": str(error)} for error in cleanup_errors])
            for log in files:
                cleanup_call(log.close)
        if cleanup_errors:
            raise cleanup_errors[0]


if __name__ == "__main__":
    main()
