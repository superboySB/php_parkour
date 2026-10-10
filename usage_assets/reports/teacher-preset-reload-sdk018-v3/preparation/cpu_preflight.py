#!/usr/bin/env python3
"""Docker CPU only: parse real saved preset configs and exact planned eval argv."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/workspace/php_parkour')
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    import torch
    from holosoma.utils.eval_utils import CheckpointConfig
    from wbt_training.utils.checkpoint import load_saved_experiment_config, parse_saved_config_overrides
    from scripts.research.validate_teacher_presets import inspect_config
    rows = []
    for row in plan['cases']:
        for item in row['inputs']:
            assert sha(item['native_path']) == item['sha256'], item['native_path']
        loaded = torch.load(row['checkpoint'], map_location='cpu', weights_only=False)
        state = loaded['actor_model_state_dict']
        assert loaded['iter'] == 1
        assert all(torch.isfinite(value).all().item() for value in state.values())
        contract = inspect_config(row['preset'], loaded['experiment_config'], state['actor_module.module.0.weight'].shape[1])
        saved, _ = load_saved_experiment_config(CheckpointConfig(checkpoint=row['checkpoint']))
        config = parse_saved_config_overrides(saved.get_eval_config(), row['native_overrides'])
        assert config.training.num_envs == 16 and config.training.max_eval_steps == 100
        assert config.training.export_onnx is False and config.training.headless is True
        assert config.training.registry_name == 'file:///data/assets/motions-locomotion'
        assert config.training.seed == 42 and str(config.logger.base_dir) == row['native_output']
        assert config.robot.asset.asset_root == '/outputs/teacher-preset-runtime-assets-v3/robots'
        assert config.robot.asset.urdf_file == 'g1/main_mesh_arm_collision_halfspherehand.urdf'
        runtime_root = Path(config.robot.asset.asset_root)
        assert runtime_root.is_dir() and (runtime_root/config.robot.asset.urdf_file).is_file()
        assert not str(runtime_root).startswith('/workspace/php_parkour/')
        for asset in plan['robot_assets']:
            assert sha(asset['source']['native_path']) == asset['source']['sha256']
            assert sha(asset['copy']['native_path']) == asset['copy']['sha256'] == asset['source']['sha256']
        assert config.logger.video.enabled and config.logger.video.interval == 1
        assert config.logger.video.upload_to_wandb is False
        assert json.loads(config.training.preprocess_hook_kwargs) == {'add_onpath_obstacle': True, 'num_variants': 1, 'obstacle_seed': 42}
        assert inspect_config(row['preset'], loaded['experiment_config'], contract['observation_dim']) == contract
        from dataclasses import asdict
        assert inspect_config(row['preset'], asdict(config), contract['observation_dim']) == contract
        rows.append({'preset': row['preset'], 'checkpoint_sha256': sha(row['checkpoint']), 'checkpoint_iteration': loaded['iter'],
            'actual_saved_contract': contract, 'native_parser_passed': True, 'num_envs': 16, 'max_eval_steps': 100,
            'export_onnx': False, 'logger_base_dir': str(config.logger.base_dir), 'native_overrides': row['native_overrides'],
            'runtime_robot_asset_root':config.robot.asset.asset_root, 'runtime_urdf':config.robot.asset.urdf_file})
    assert not torch.cuda.is_initialized()
    report = {'schema_version': 1, 'status': 'passed', 'plan_sha256': sha(args.plan), 'rows': rows,
        'cuda_initialized': False, 'isaac_started': False, 'physics_verified': False, 'quality_verified': False,
        'scope': 'Actual five local smoke PT loads and native saved-config Tyro parse only; no simulator setup or new ONNX export'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'presets': len(rows), 'cuda_initialized': False}))


if __name__ == '__main__':
    main()
