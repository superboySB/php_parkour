#!/usr/bin/env python3
"""One completed low-step teacher: CPU checkpoint, scalar and ONNX binding.

Execute each phase inside the unified research Docker. This does not run Isaac,
train, evaluate policy quality, or assert PT/ONNX numerical parity.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

ITERATION = 19999
TAGS = ('Train/mean_reward', 'Loss/Value', 'Loss/Surrogate', 'Loss/Entropy')
ARTIFACTS = {
    'model_19999.pt': (10345023, 'ff6912286a5b2a4d8d048dca5471b53935baecca4d06c3407af7201ef09153e6'),
    'model_19999.onnx': (428920342, 'bb3d4fd4657233a7ede2a14005ee7336efa82954d115112cecc5d7cec1f5cd69'),
    'holosoma_config.yaml': (30944, 'd9ee3170421d7561cb9e52ebd06850e396fb7dbbe5385a1e73c2d0d610053bfd'),
    'events.out.tfevents.1791651217.pro5000-6.71862.0': (72561360, '85ed6bec3d6737dc8705c6191bd9e11da5908eb35e803345d2cc590f7b436203'),
    'model_00000.pt': (10345023, '0eeeecfc7c7bc71ef8ee6b1a6a5cd1ffe61362598c2af38e146b5926df05f8dc'),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def fingerprint(path):
    path = Path(path).absolute()
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'Regular nonsymlink input required: ' + str(path))
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}


def artifact(directory, name):
    row = fingerprint(directory / name)
    size, sha = ARTIFACTS[name]
    require((row['bytes'], row['sha256']) == (size, sha), 'Artifact differs from actual completed cloud teacher: ' + name)
    return row


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda token: (_ for _ in ()).throw(ValueError('Nonfinite report JSON: ' + token)))


def check_unchanged(records):
    for row in records:
        require(fingerprint(row['path']) == row, 'Input changed during CPU acceptance: ' + row['path'])


def resolved_yaml_contract(yaml_config, saved_config):
    """Only the native PPOActor._process_module_config symbolic replacement."""
    path = '$.algo.config.module_dict.actor.output_dim'
    require(yaml_config['algo']['config']['module_dict']['actor']['output_dim'] == ['robot_action_dim']
            and saved_config['algo']['config']['module_dict']['actor']['output_dim'] == [29]
            and type(saved_config['algo']['config']['module_dict']['actor']['output_dim'][0]) is int,
            'Expected exact documented actor output_dim symbolic resolution')
    resolved = copy.deepcopy(yaml_config)
    resolved['algo']['config']['module_dict']['actor']['output_dim'] = [29]
    require(resolved == saved_config, 'PT config differs after the sole documented output_dim resolution; no other difference allowed')
    require(yaml_config != saved_config, 'This cohort must preserve the observed raw YAML/PT output_dim difference')
    return {'path': path, 'raw_yaml_value': ['robot_action_dim'], 'saved_pt_value': [29],
            'source': 'thirdparty/holosoma/src/holosoma/holosoma/agents/modules/ppo_modules.py:40-43 PPOActor._process_module_config',
            'scope': 'Single documented runtime output_dim resolution; all other configuration fields exactly equal'}


def config_contract(config):
    training, algo = config['training'], config['algo']
    cfg = algo['config']
    actor = config['observation']['groups']['actor_obs']
    control = config['robot']['control']
    expected_terms = {'actions', 'base_ang_vel', 'base_lin_vel', 'dof_pos', 'dof_vel',
                      'height_scan', 'motion_command', 'motion_ref_ori_b', 'motion_ref_pos_b'}
    require(training['num_envs'] == 4096 and training['seed'] == 42
            and training['name'] == 'teacher-low-step'
            and training['registry_name'] == 'file:///data/assets/motions-low-step', 'Official training identity differs')
    kwargs = training['preprocess_hook_kwargs']
    if isinstance(kwargs, str):
        kwargs = json.loads(kwargs)
    require(training['preprocess_hook'] == 'wbt_training.config_values.terrain:apply_terrain_preprocess'
            and kwargs == {'num_variants': 64, 'add_onpath_obstacle': True, 'obstacle_seed': 42}, 'Official terrain preprocessing differs')
    require(algo['_target_'] == 'holosoma.agents.ppo.ppo.PPO'
            and all(cfg[key] == value for key, value in {'num_learning_iterations': 20000, 'save_interval': 500,
                'num_steps_per_env': 24, 'num_mini_batches': 4, 'num_learning_epochs': 5}.items())
            and cfg['empirical_normalization'] is False, 'Official PPO schedule differs')
    require(set(actor['terms']) == expected_terms and actor['history_length'] == 1
            and control['action_scale'] == 1.0
            and control['action_scales_by_effort_limit_over_p_gain'] is False, 'Heightscan actor or action scaling differs')
    return {'algorithm': algo['_target_'], 'num_envs': 4096, 'seed': 42, 'registry': training['registry_name'],
            'preprocessing': kwargs, 'learning_iterations': 20000, 'save_interval': 500,
            'steps_per_env': 24, 'mini_batches': 4, 'epochs': 5, 'empirical_normalization': False,
            'actor_terms': sorted(expected_terms), 'actor_history': 1, 'actor_observation_dim': 449,
            'critic_observation_dim': 575, 'actions_dim': 29, 'action_scale': 1.0,
            'action_scales_by_effort_limit_over_p_gain': False}


def tensor_inventory(value, torch, path='$'):
    """Check every Tensor, while allowing legal scalar infinity in config bounds."""
    if isinstance(value, torch.Tensor):
        require(torch.isfinite(value).all().item(), 'Nonfinite checkpoint Tensor: ' + path)
        return [{'path': path, 'shape': list(value.shape), 'dtype': str(value.dtype), 'numel': value.numel()}]
    if isinstance(value, dict):
        return [item for key, child in value.items() for item in tensor_inventory(child, torch, path + '.' + str(key))]
    if isinstance(value, (list, tuple)):
        return [item for index, child in enumerate(value) for item in tensor_inventory(child, torch, path + '[' + str(index) + ']')]
    return []


def network_shapes(state, prefix, input_dim, output_dim, std, torch):
    shapes = {f'{prefix}.module.{layer}.{kind}': ([rows, columns] if kind == 'weight' else [rows])
              for layer, rows, columns in ((0, 512, input_dim), (2, 256, 512), (4, 128, 256), (6, output_dim, 128))
              for kind in ('weight', 'bias')}
    if std:
        shapes['std'] = [29]
    require(set(state) == set(shapes) and all(isinstance(state[key], torch.Tensor) and list(state[key].shape) == shape
            for key, shape in shapes.items()), 'Native actor/critic tensor keys or MLP dimensions differ: ' + prefix)
    return shapes


def optimizer_steps(state, torch):
    require(state['state'] and state['param_groups'], 'Empty optimizer state')
    steps = {}
    for key, entry in state['state'].items():
        require({'step', 'exp_avg', 'exp_avg_sq'} <= set(entry), 'Incomplete AdamW optimizer state')
        step = entry['step']
        if isinstance(step, torch.Tensor):
            require(step.numel() == 1, 'Nonscalar Adam step')
            step = step.item()
        require(type(step) in (int, float) and math.isfinite(step) and step >= 0 and int(step) == step, 'Invalid Adam step')
        steps[str(key)] = int(step)
    return steps


def checkpoint(args):
    import torch
    import yaml
    require(not torch.cuda.is_initialized(), 'CPU checkpoint phase must not initialize CUDA')
    current = artifact(args.artifacts, 'model_19999.pt')
    yaml_record = artifact(args.artifacts, 'holosoma_config.yaml')
    baseline_record = artifact(args.baseline.parent, 'model_00000.pt')
    require(Path(args.baseline).name == 'model_00000.pt', 'Iteration-zero native baseline required')
    value = torch.load(current['path'], map_location='cpu', weights_only=False)
    baseline = torch.load(baseline_record['path'], map_location='cpu', weights_only=False)
    required = {'actor_model_state_dict', 'critic_model_state_dict', 'actor_optimizer_state_dict',
                'critic_optimizer_state_dict', 'actor_obs_normalizer_state_dict', 'critic_obs_normalizer_state_dict',
                'iter', 'infos', 'experiment_config', 'iteration'}
    require(required <= set(value) and required <= set(baseline), 'Missing native PT fields')
    require(value['iter'] == value['iteration'] == ITERATION and baseline['iter'] == baseline['iteration'] == 0, 'Native checkpoint iteration differs')
    require(value['actor_obs_normalizer_state_dict'] is None and value['critic_obs_normalizer_state_dict'] is None, 'Disabled normalization must save both normalizers as None')
    tensors = tensor_inventory(value, torch)
    require(tensors, 'No checkpoint Tensors')
    tensor_inventory(baseline, torch)
    config = value['experiment_config']
    yaml_config = yaml.safe_load(Path(yaml_record['path']).read_text())
    resolution = resolved_yaml_contract(yaml_config, config)
    contract = config_contract(config)
    baseline_contract = config_contract(baseline['experiment_config'])
    require(baseline_contract == contract and baseline['experiment_config'] == config,
            'Same-run iteration-zero and final checkpoint full configurations must match')
    shapes = {}
    updates = {}
    for role, prefix, dim, out, std in (('actor', 'actor_module', 449, 29, True), ('critic', 'critic_module', 575, 1, False)):
        state, old = value[role + '_model_state_dict'], baseline[role + '_model_state_dict']
        shapes[role] = network_shapes(state, prefix, dim, out, std, torch)
        require(set(state) == set(old), 'Baseline/final network keys differ: ' + role)
        differences = []
        for key, tensor in state.items():
            require(tensor.shape == old[key].shape, 'Baseline/final network shape differs: ' + key)
            delta = tensor.to(torch.float64) - old[key].to(torch.float64)
            differences.append({'tensor': key, 'changed_elements': int(torch.count_nonzero(delta).item()),
                                'max_absolute_delta': float(delta.abs().max().item()), 'l2_delta': float(torch.linalg.vector_norm(delta).item())})
        require(any(row['changed_elements'] for row in differences), 'No actual baseline-to-final weight update: ' + role)
        before = optimizer_steps(baseline[role + '_optimizer_state_dict'], torch)
        after = optimizer_steps(value[role + '_optimizer_state_dict'], torch)
        require(set(before) == set(after) and all(after[key] > before[key] for key in before), 'Adam steps did not advance for all saved parameters: ' + role)
        updates[role] = {'tensors': differences, 'adam_baseline_steps_by_parameter': before,
                         'adam_final_steps_by_parameter': after, 'adam_baseline_unique_steps': sorted(set(before.values())),
                         'adam_final_unique_steps': sorted(set(after.values())),
                         'step_scope': 'Observed saved AdamW step values; no hardcoded 400000-step assertion'}
    require(not torch.cuda.is_initialized(), 'CUDA initialized during checkpoint inspection')
    check_unchanged([current, yaml_record, baseline_record])
    return {'checkpoint': current, 'yaml': yaml_record, 'baseline_checkpoint': baseline_record,
            'iteration': ITERATION, 'required_checkpoint_keys': sorted(required), 'actual_checkpoint_keys': sorted(value),
            'tensor_inventory': tensors, 'tensor_count': len(tensors), 'all_checkpoint_tensors_finite': True,
            'normalizers': {'actor': None, 'critic': None}, 'network_shapes': shapes, 'contract': contract,
            'raw_full_config_equal': False, 'resolved_yaml_full_config_equal': True,
            'yaml_runtime_resolution': resolution, 'experiment_config_json': json.dumps(config, sort_keys=True, allow_nan=True),
            'baseline_config_binding': {'full_config_equal': True, 'contract': baseline_contract,
                                        'source': 'Same low-step native run, remote before/after SHA and actual baseline ARTIFACTS pin'},
            'configuration_serialization': 'Original full config JSON stored as a string; legal scalar Infinity bounds retained, all checkpoint Tensors checked finite',
            'baseline_to_final_updates': updates, 'torch_version': torch.__version__, 'cuda_initialized': False}


def scalars(args):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    event = artifact(args.artifacts, 'events.out.tfevents.1791651217.pro5000-6.71862.0')
    accumulator = EventAccumulator(event['path'], size_guidance={'scalars': 0})
    accumulator.Reload()
    values = {}
    for tag in TAGS:
        rows = accumulator.Scalars(tag)
        require(len(rows) == 20000 and [row.step for row in rows] == list(range(20000)), 'Full exact steps 0..19999 required: ' + tag)
        require(all(math.isfinite(row.value) and math.isfinite(row.wall_time) for row in rows), 'Nonfinite full TensorBoard tag: ' + tag)
        values[tag] = [{'step': int(row.step), 'wall_time': row.wall_time, 'value': row.value} for row in rows]
    check_unchanged([event])
    return {'event_file': event, 'scalars': values, 'required_tags': list(TAGS), 'samples_per_tag': 20000,
            'first_step': 0, 'last_step': ITERATION, 'stage': 'teacher-low-step', 'stage_complete': True,
            'training_status': 'completed_20000_iterations', 'official_schedule_complete': False}


def bind(args):
    import yaml
    records = [fingerprint(args.checkpoint_report), fingerprint(args.scalars_report), fingerprint(args.onnx_report)]
    ckpt, scalar, onnx = (read(row['path']) for row in records)
    require(all(row['status'] == 'passed' for row in (ckpt, scalar, onnx)), 'All three actual CPU reports must pass')
    model = artifact(args.artifacts, 'model_19999.onnx')
    yaml_record = artifact(args.artifacts, 'holosoma_config.yaml')
    pt = artifact(args.artifacts, 'model_19999.pt')
    event = artifact(args.artifacts, 'events.out.tfevents.1791651217.pro5000-6.71862.0')
    require(ckpt['checkpoint'] == pt and ckpt['yaml'] == yaml_record and ckpt['iteration'] == ITERATION
            and scalar['event_file'] == event and scalar['stage_complete'] is True, 'Checkpoint/scalar reports bind other originals')
    config = json.loads(ckpt['experiment_config_json'])
    resolution = resolved_yaml_contract(yaml.safe_load(Path(yaml_record['path']).read_text()), config)
    require(ckpt['raw_full_config_equal'] is False and ckpt['resolved_yaml_full_config_equal'] is True
            and ckpt['yaml_runtime_resolution'] == resolution, 'Checkpoint must retain the actual raw YAML/PT difference')
    require(config == json.loads(onnx['metadata']['experiment_config'])
            and json.loads(onnx['metadata']['iteration']) == ITERATION, 'Original YAML/PT/ONNX full config or iteration mismatch')
    require(onnx['sha256'] == model['sha256'] and onnx['bytes'] == model['bytes']
            and onnx['self_contained'] is True and onnx['expected_observation_dim'] == 449
            and len(onnx['cases']) == 12
            and len([row for row in onnx['cases'] if row['observations'] == 'zeros']) == 6
            and len([row for row in onnx['cases'] if row['observations'] == 'random_normal']) == 6, 'Existing 12-case teacher ONNX CPU acceptance differs')
    for field, name, shape in (('inputs', 'obs', [1, 449]), ('outputs', 'actions', [1, 29])):
        matches = [row for row in onnx[field] if row['name'] == name]
        require(len(matches) == 1 and matches[0]['shape'] == shape and matches[0]['type'] == 'tensor(float)', 'Official ONNX tensor interface differs: ' + name)
    require(scalar['samples_per_tag'] == 20000 and set(scalar['scalars']) == set(TAGS), 'Full scalar report scope differs')
    for tag in TAGS:
        require([row['step'] for row in scalar['scalars'][tag]] == list(range(20000))
                and all(math.isfinite(row['value']) for row in scalar['scalars'][tag]), 'Full scalar report was truncated or changed: ' + tag)
    check_unchanged([*records, model, yaml_record, pt, event])
    return {'reports': records, 'artifacts': [pt, model, yaml_record, event], 'iteration': ITERATION,
            'raw_full_config_equal': False, 'full_config_equal_pt_onnx': True,
            'full_config_equal_pt_resolved_yaml': True, 'yaml_runtime_resolution': resolution,
            'teacher_onnx_cpu_cases': 12, 'onnx_self_contained': True,
            'observations': [1, 449], 'actions': [1, 29], 'stage_complete': True,
            'official_schedule_complete': False, 'pt_onnx_numerical_parity_verified': False,
            'convergence_verified': False, 'skills_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('checkpoint', 'scalars', 'bind'))
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--checkpoint-report', type=Path)
    parser.add_argument('--scalars-report', type=Path)
    parser.add_argument('--onnx-report', type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'Use a fresh report path; prior evidence is immutable')
    require(args.phase != 'checkpoint' or args.baseline is not None, 'Checkpoint phase requires --baseline')
    require(args.phase != 'bind' or all((args.checkpoint_report, args.scalars_report, args.onnx_report)), 'Bind phase requires all three report paths')
    report = {'schema_version': 1, 'phase': args.phase, 'status': 'running', 'source': fingerprint(__file__),
              'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'quality_verified': False,
              'official_schedule_complete': False, 'convergence_verified': False,
              'pt_onnx_numerical_parity_verified': False,
              'scope': 'Completed second official low-step teacher CPU artifact acceptance; no policy rollout or claim that the whole official schedule completed'}
    try:
        report.update(globals()[args.phase](args), status='passed')
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        report['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(report, stream, indent=2, allow_nan=False); stream.write('\n')
        args.output.chmod(0o644)
    print(json.dumps({'phase': args.phase, 'status': report['status'], 'quality_verified': False}))


if __name__ == '__main__':
    main()
