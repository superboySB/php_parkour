"""Import and exact CLI config parsing only; no policy/Robot/DDS/sim construction."""
from __future__ import annotations
import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from common import fingerprint, write
from container_runner import native_argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=('simulator', 'inference'), required=True)
    args = parser.parse_args()
    os.chdir('/workspace/php_parkour/thirdparty/holosoma')
    source = Path('/workspace/php_parkour')
    sim, infer = native_argv(Path('/outputs'), os.environ['PHP_GUI_TOKEN'])
    entries = []
    if args.role == 'simulator':
        from holosoma.config_types.run_sim import RunSimConfig
        from holosoma.utils.config_registry import parse_config
        from holosoma.utils.sim_utils import DirectSimulation
        from holosoma.simulator.mujoco.mujoco import MuJoCo
        prefix = ['robot:g1-29dof', 'sensor.d435i_front_depth:g1-d435i-front-depth',
                  'plugin.depth:depth-shm-d435i', 'terrain:terrain-load-step', '--robot.asset.xml-file',
                  'g1/g1_29dof_halfspherehand.xml', '--simulator.config.bridge.enabled=True', '--simulator.config.sim.fps=500']
        config = parse_config(RunSimConfig, args=prefix + sim[2:])
        if (config.device != 'cpu' or config.training.headless or config.simulator.config.sim.control_decimation_steps != 10
                or str(config.terrain.terrain_term.mesh_type) != 'plane'):
            raise ValueError('Exact GUI simulator CLI did not resolve CPU physics/visible500:50Hz')
        for ep in importlib.metadata.entry_points(group='holosoma.bridge'):
            if ep.name == 'unitree':
                target = ep.load()
                entries.append({'group': ep.group, 'name': ep.name, 'value': ep.value, 'loaded': repr(target)})
        if len(entries) != 1:
            raise ValueError('Unitree bridge metadata entrypoint unavailable')
        from observe_native import install_simulator
        install_simulator()  # install diagnostic wrappers only; no objects/calls
        resolved = {'device': config.device, 'headless': config.training.headless, 'fps': config.simulator.config.sim.fps,
                    'control_decimation_steps': config.simulator.config.sim.control_decimation_steps,
                    'terrain_func': config.terrain.terrain_term.func, 'bridge_interface': config.simulator.config.bridge.interface,
                    'mesh_type': str(config.terrain.terrain_term.mesh_type),
                    'bridge_enabled': config.simulator.config.bridge.enabled}
    else:
        import tkinter
        import Xlib.ext.xtest
        import Xlib.ext.record
        from holosoma_inference.config.config_values.inference import get_annotated_inference_config
        from holosoma_inference.utils.config_registry import parse_config
        from holosoma_inference.policies.depth_distillation import DepthDistillationPolicy
        from holosoma_inference.sdk.unitree.unitree_interface import UnitreeInterface
        from common import load
        bootstrap = load(source / 'scripts/research/run_native_policy.gui-original.py', 'gui_preflight_keyboard_bootstrap')
        keyboard = bootstrap.install_keyboard_compat()  # no listener or Robot construction
        config = parse_config(get_annotated_inference_config, args=['inference:g1-wbt-distillation-d435i',
            '--task.interface', 'lo', '--task.model-path', "['/data/assets/student/depth_backbone.onnx','/data/assets/student/student.onnx']", *infer[2:]])
        if config.task.velocity_input != 'keyboard' or config.task.state_input != 'keyboard' or config.task.rl_rate != 50:
            raise ValueError('Exact native inference CLI did not resolve real keyboard at50Hz')
        if importlib.metadata.version('far-unitree-sdk') != '0.1.8':
            raise ValueError('Canonical SDK018 identity differs')
        from observe_native import install_inference
        install_inference()  # install diagnostic wrappers only; no objects/calls
        resolved = {'velocity_input': config.task.velocity_input, 'state_input': config.task.state_input,
                    'rl_rate': config.task.rl_rate, 'record_dir': config.task.record_dir, 'record_label': config.task.record_label,
                    'keyboard_compat': keyboard}
    modules = []
    for name, module in sorted(sys.modules.copy().items()):
        value = getattr(module, '__file__', None)
        if value and Path(value).is_file() and Path(value).resolve().is_relative_to(source):
            modules.append({'module': name, 'path': str(Path(value).resolve()), **fingerprint(value)})
    report = {'role': args.role, 'status': 'passed', 'scope': 'imports and CLI parse only; no native runtime or GUI acceptance',
              'native_objects_constructed': False, 'resolved': resolved, 'entrypoints': entries, 'modules': modules}
    write(Path('/outputs') / (args.role + '-cpu-preflight.json'), report)
    print(json.dumps({'role': args.role, 'status': report['status'], 'source_modules': len(modules), 'native_objects_constructed': False}))


if __name__ == '__main__':
    main()
