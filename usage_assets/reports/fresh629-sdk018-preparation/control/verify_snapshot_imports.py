#!/usr/bin/env python3
"""CPU import/config-only preflight of the exact frozen native pilot snapshot.

No simulator, policy, bridge or robot instance is constructed. Unitree C factory
calls are rejected before invocation by the Python profile hook. The container
must have no NVIDIA devices/runtime and no network, independently inspected by host.
"""
from __future__ import annotations
import argparse
import dataclasses
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path('/workspace/php_parkour')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def simulator_cli(mesh, output):
    return ['robot:g1-29dof', 'sensor.d435i_front_depth:g1-d435i-front-depth', 'plugin.depth:depth-shm-d435i',
            'terrain:terrain-load-step', '--robot.asset.xml-file', 'g1/g1_29dof_halfspherehand.xml',
            '--simulator.config.bridge.enabled', 'True', '--simulator.config.bridge.interface', 'lo',
            '--simulator.config.sim.fps', '500', '--simulator.config.sim.control-decimation', '10',
            '--simulator.config.virtual-gantry.length', '0.5', '--training.headless', 'True',
            '--training.seed', '42', '--device', 'cpu', '--simulator.config.debug-viz', 'False',
            '--logger.video.enabled', 'True', '--logger.video.width', '640', '--logger.video.height', '360',
            '--logger.video.save-dir', str(output / 'video'), '--logger.video.upload-to-wandb', 'False',
            '--logger.video.show-command-overlay', 'False', '--terrain.terrain-term.obj-file-path', mesh]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=['simulator', 'inference'], required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Fresh CPU evidence file required')
    report = {'schema_version': 1, 'scope': 'Actual CPU imports, selected metadata entrypoint load and native config parsing only',
              'status': 'running', 'role': args.role, 'argv': sys.argv, 'started_unix': time.time(),
              'probe_sha256': sha(__file__), 'robot_or_dds_construction_attempts': [], 'native_instances_created': False,
              'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
              'nvidia_visible_devices': os.environ.get('NVIDIA_VISIBLE_DEVICES'), 'selected_entrypoints': []}
    try:
        if os.environ.get('CUDA_VISIBLE_DEVICES') != '' or os.environ.get('NVIDIA_VISIBLE_DEVICES') != 'void':
            raise ValueError('No-device CPU import guard missing')
        plan = json.loads(args.plan.read_text())
        report['native_plan_sha256'] = plan['plan_sha256']
        import unitree_interface as sdk
        factories = [sdk.create_robot, *(getattr(sdk.UnitreeInterface, name) for name in
                     ('create_custom', 'create_g1', 'create_go2', 'create_h1', 'create_h1_2'))]
        def forbid_factory(frame, event, value):
            if event == 'c_call' and any(value is factory for factory in factories):
                report['robot_or_dds_construction_attempts'].append(getattr(value, '__name__', repr(value)))
                raise RuntimeError('CPU preflight forbids native Unitree robot/DDS construction')
        sys.setprofile(forbid_factory)
        extension = list(Path(sdk.__file__).parent.glob('unitree_interface.cpython-*.so'))
        if len(extension) != 1:
            raise ValueError('Expected one native SDK extension')
        report['sdk'] = {'version': importlib.metadata.version('far-unitree-sdk'),
                         'extension': str(extension[0]), 'sha256': sha(extension[0])}
        if report['sdk']['version'] != '0.1.8':
            raise ValueError('CPU preflight image SDK is not0.1.8')
        report['configurations'] = []
        if args.role == 'simulator':
            from holosoma.config_types.run_sim import RunSimConfig
            from holosoma.utils.config_registry import parse_config
            from holosoma.utils.sim_utils import DirectSimulation, setup_simulation_environment
            from holosoma.simulator.mujoco.mujoco import MuJoCo
            from holosoma.simulator.base_simulator.hooks import Phase
            entrypoints = [entry for entry in importlib.metadata.entry_points(group='holosoma.bridge') if entry.name == 'unitree']
            if len(entrypoints) != 1:
                raise ValueError('Selected installed Unitree entrypoint is missing/duplicate')
            entry = entrypoints[0]
            bridge_class = entry.load()  # Returns a class only; never instantiated.
            report['selected_entrypoints'].append({'group': entry.group, 'name': entry.name, 'value': entry.value,
                                                   'class_module': bridge_class.__module__, 'class_name': bridge_class.__name__})
            selected = {}
            for case in plan['selections']:
                selected.setdefault(case['scenario'], case)
            report['configuration_selection_scope'] = 'First planned case per scenario family; full629 inputs checked by native --plan'
            for case in selected.values():
                cli = simulator_cli(case['mesh'], Path(case['output']))
                cfg = parse_config(RunSimConfig, args=cli)
                if cfg.robot.bridge.sdk_type != 'unitree' or cfg.simulator.config.bridge.interface != 'lo':
                    raise ValueError('Selected native bridge config differs')
                # Resolve configured dynamic implementations, without creating them.
                for config in [cfg.simulator, *cfg.plugin.values()]:
                    target = getattr(config, '_target_', None)
                    if target:
                        module, _, name = target.rpartition('.')
                        getattr(importlib.import_module(module), name)
                    getter = getattr(config, 'get_cls', None)
                    if getter:
                        getter()  # Class resolution only; no constructor.
                report['configurations'].append({'case_id': case['case_id'], 'cli': cli,
                    'parsed_config': dataclasses.asdict(cfg), 'bridge_class_resolved_only': True})
        else:
            from holosoma_inference.config.config_values.inference import g1_wbt_distillation_d435i
            from holosoma_inference.inputs.api.commands import StateCommand
            from holosoma_inference.policies.depth_distillation import DepthDistillationPolicy
            from holosoma_inference.sdk.unitree.unitree_interface import UnitreeInterface
            from holosoma_inference.sensors.depth_shm import DepthShmSensor
            from holosoma_inference.sensors.depth_heartbeat import STATE_FAILED
            preset = g1_wbt_distillation_d435i
            cfg = dataclasses.replace(preset, task=dataclasses.replace(preset.task,
                model_path=['/data/assets/student/depth_backbone.onnx', '/data/assets/student/student.onnx'],
                interface='lo', velocity_input='injected', state_input='injected',
                record_dir='/outputs/preflight-not-created', record_label='rollout'))
            report['configurations'].append({'parsed_config': dataclasses.asdict(cfg), 'policy_class_resolved_only': True,
                                             'policy_class': DepthDistillationPolicy.__module__ + '.' + DepthDistillationPolicy.__name__})
        dependencies = {item['path']: item['sha256'] for item in plan['dependencies']}
        loaded = {}
        for module in tuple(sys.modules.values()):
            filename = getattr(module, '__file__', None)
            if filename and Path(filename).is_relative_to(ROOT) and Path(filename).is_file():
                path = str(Path(filename).resolve())
                actual = sha(path)
                if dependencies.get(path) != actual:
                    raise ValueError('Actual import escapes frozen dependency closure: ' + path)
                loaded[path] = actual
        report['actual_frozen_repo_modules'] = [{'path': path, 'sha256': digest} for path, digest in sorted(loaded.items())]
        if 'torch' in sys.modules:
            report['torch_cuda_initialized'] = sys.modules['torch'].cuda.is_initialized()
            if report['torch_cuda_initialized']:
                raise ValueError('Import-only CPU preflight unexpectedly initialized CUDA')
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
        raise
    finally:
        sys.setprofile(None)
        report['finished_unix'] = time.time()
        args.output.write_text(json.dumps(report, indent=2, default=str, allow_nan=False) + '\n')
    print(json.dumps({'role': args.role, 'status': report['status'],
                      'repo_modules': len(report['actual_frozen_repo_modules']),
                      'native_instances_created': False}))


if __name__ == '__main__':
    main()
