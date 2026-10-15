#!/usr/bin/env python3
"""Ordinary CPU/in-memory synthetic schema controls, not actual888 evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('synthetic_cloud888_browser_adapter', Path(__file__).with_name('verify_cloud888_http.py'))
adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)


def fixture():
    digest = 'a' * 64; name = 'media/' + digest + '.mp4'
    files = [{'path': name, 'bytes': 100, 'sha256': digest}]
    validations = {digest: {'sha256': digest, 'bytes': 100, 'ffprobe_returncode': 0, 'ffmpeg_returncode': 0, 'decoded_frames': 1,
                           'metadata': {'streams': [{'width': 640, 'height': 360, 'nb_read_frames': '1', 'r_frame_rate': '50/1'}], 'format': {'duration': '.02'}}}}
    inventory = [{'path': 'synthetic/original.mp4', 'stored': name, 'storage': 'original', 'bytes': 100, 'sha256': digest, 'mode': 0o664}]
    cases, groups = [], []
    for policy in adapter.POLICIES:
        ordinal = 0
        for skill, count in zip(adapter.SKILLS, adapter.COUNTS):
            for _ in range(count):
                ordinal += 1
                cases.append({'policy': policy, 'case_id': 'synthetic-' + str(ordinal), 'source_clip_id': 'source-' + str(ordinal),
                              'skill': skill, 'source_boundary_completed': False, 'status': 'execution_passed', 'returncode': 0,
                              'videos': [{'url': name, 'sha256': digest, 'duration_seconds': .02, 'quality_bound': True, 'association': 'synthetic fixture only'}]})
            groups.append({'policy': policy, 'skill': skill, 'attempts': count, 'execution_passed': count, 'source_boundary_completed': 0})
    summary = {'attempts': 888, 'original_batch_status': 'completed', 'input_identity': adapter.INPUT_IDENTITY, 'quality_verified': False,
               'obstacle_course_completion_verified': False, 'groups': groups, 'unique_videos_full_decoded': 1}
    return summary, cases, inventory, files, validations


class SyntheticSchemaControls(unittest.TestCase):
    def test_one_frame_clip_is_retained_and_not_called_visible_motion(self):
        result = adapter.prefilter(*fixture())
        self.assertEqual((result['cases'], result['one_frame_unique_videos'], len(result['videos'])), (888, 1, 1))
        self.assertIn('not visible robot motion', result['videos'][0]['browser_play_scope'])

    def test_all_unique_orphan_mp4s_are_retained(self):
        summary, cases, inventory, files, validation = fixture(); digest = 'b' * 64; name = 'media/' + digest + '.mp4'
        files.append({'path': name, 'bytes': 200, 'sha256': digest})
        inventory.append({'path': 'synthetic/orphan.mp4', 'stored': name, 'storage': 'original', 'bytes': 200, 'sha256': digest, 'mode': 0o664})
        validation[digest] = copy.deepcopy(next(iter(validation.values()))); validation[digest].update(sha256=digest, bytes=200)
        summary['unique_videos_full_decoded'] = 2
        result = adapter.prefilter(summary, cases, inventory, files, validation)
        self.assertEqual(len(result['videos']), 2); self.assertEqual(result['videos'][1]['case_references'], [])

    def test_case_sha_mismatch_rejected(self):
        args = fixture(); args[1][0]['videos'][0]['sha256'] = 'b' * 64
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_full_decode_failure_rejected(self):
        args = fixture(); next(iter(args[4].values()))['ffmpeg_returncode'] = 1
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_nonfinite_duration_rejected(self):
        args = fixture(); next(iter(args[4].values()))['metadata']['format']['duration'] = 'nan'
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_missing_original_media_rejected(self):
        args = fixture(); args[2].clear()
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_duplicate_policy_attempt_rejected(self):
        args = fixture(); args[1][1]['case_id'] = args[1][0]['case_id']
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_changed_summary_group_rejected(self):
        args = fixture(); args[0]['groups'][0]['source_boundary_completed'] = 1
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_traversing_seal_member_rejected(self):
        args = fixture(); args[3].append({'path': '../outside', 'bytes': 0, 'sha256': 'b' * 64})
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_mismatched_cpu_frame_count_rejected(self):
        args = fixture(); next(iter(args[4].values()))['decoded_frames'] = 2
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_noncanonical_media_path_rejected(self):
        args = fixture(); old = args[3][0]['path']; new = 'media/noncanonical.mp4'
        args[3][0]['path'] = new; args[2][0]['stored'] = new
        for case in args[1]: case['videos'][0]['url'] = new
        self.assertNotEqual(old, new)
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_unsafe_original_mode_rejected(self):
        args = fixture(); args[2][0]['mode'] = 0o4664
        with self.assertRaises(ValueError): adapter.prefilter(*args)

    def test_wrong_cohort_identity_rejected(self):
        args = fixture(); args[0]['input_identity'] = '0' * 64
        with self.assertRaises(ValueError): adapter.prefilter(*args)


class RestoredRawBindingControls(unittest.TestCase):
    """Two synthetic cases only; the real entry requires all888 before this."""
    def setUp(self):
        self.context = tempfile.TemporaryDirectory(); self.root = Path(self.context.name)

    def tearDown(self):
        self.context.cleanup()

    def fixture(self, identical_video_bytes=False):
        from pathlib import PurePosixPath
        raw = self.root / 'synthetic-restored'; raw.mkdir()
        def write(path, value):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))
        selection = {'input_identity': adapter.INPUT_IDENTITY}
        write(raw / 'selection.json', selection)
        write(raw / 'monitor-status.json', {'status': 'completed', 'container_exit_code': 0,
              'container': 'php-parkour-posttrain-gpu-' + adapter.INPUT_IDENTITY[:12]})
        attempts, originals, inventory, validations, published = [], {}, [], {}, []
        for index in (1, 2):
            name = 'synthetic-' + str(index); directory = raw / 'teacher/cases' / name
            directory.mkdir(parents=True)
            data = b'synthetic only, not real MP4' + (b'' if identical_video_bytes else str(index).encode())
            video = directory / 'video.mp4'; video.write_bytes(data); digest = hashlib.sha256(data).hexdigest()
            path = '/outputs/posttrain-coverage/teacher/cases/' + name + '/video.mp4'
            trajectory = directory / 'trajectory.jsonl'; trajectory.write_text('{}\n')
            case = {'policy': 'teacher', 'case_id': name, 'checkpoint_sha256': str(index) * 64,
                    'source': {'skill': 'locomotion', 'frames': 3, 'source_clip_id': 'synthetic-source-' + str(index)}}
            quality = {'stop_reason': 'native_boundary', 'control_steps': 1, 'metrics': {'synthetic_fixture_only': True},
                       'trajectory': {'path': '/outputs/posttrain-coverage/teacher/cases/' + name + '/trajectory.jsonl'},
                       'policy_sim_seconds': .02,
                       'videos': [{'path': path, 'sha256': digest, 'bytes': len(data), 'association': 'synthetic fixture'}]}
            write(directory / 'case.json', case); write(directory / 'quality.json', quality)
            attempt = {'policy': 'teacher', 'case_id': name, 'source_clip_id': case['source']['source_clip_id'],
                       'status': 'execution_passed', 'returncode': 0, 'error': None, 'stop_reason': 'original'}
            attempts.append(attempt); originals[('teacher', name)] = case
            inventory.append({'path': video.relative_to(raw).as_posix(), 'storage': 'original', 'stored': 'media/' + digest + '.mp4',
                              'sha256': digest, 'bytes': len(data), 'mode': stat.S_IMODE(video.stat().st_mode)})
            validations[digest] = {'metadata': {'format': {'duration': '.02'}}}
            published.append({'policy': 'teacher', 'case_id': name, 'source_clip_id': case['source']['source_clip_id'],
                'status': 'execution_passed', 'returncode': 0, 'error': None, 'stop_reason': 'native_boundary',
                'skill': 'locomotion', 'source_frames': 3, 'checkpoint_sha256': case['checkpoint_sha256'],
                'source_boundary_completed': True, 'reference_boundary_observed': True, 'policy_steps': 1, 'expected_policy_steps': 1,
                'scope': 'Synthetic completion stub, not actual source completion', 'tracking_metrics': quality['metrics'],
                'videos': [{'url': 'media/' + digest + '.mp4', 'sha256': digest, 'duration_seconds': .02,
                            'association': 'synthetic fixture', 'quality_bound': True}], 'policy_video_span_covers_policy_steps': True})
        write(raw / 'summary.json', {'status': 'completed', 'cases': attempts})
        helper = SimpleNamespace(read=lambda p: json.loads(Path(p).read_bytes()),
            sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest(),
            verify_input_chain=lambda *_: originals,
            local=lambda root, path: root / PurePosixPath(path).relative_to('/outputs/posttrain-coverage'),
            completion=lambda *_: {'source_boundary_completed': True, 'policy_steps': 1, 'expected_policy_steps': 1,
                                  'scope': 'Synthetic completion stub, not actual source completion'})
        return helper, raw, published, inventory, validations

    def bind(self, args):
        with patch.object(adapter, 'SELECTION_SHA', args[0].sha(args[1] / 'selection.json')):
            return adapter.bind_raw_rows(*args)

    def test_synthetic_raw_identity_and_legal_identical_byte_aliases(self):
        args = self.fixture(identical_video_bytes=True); result = self.bind(args)
        self.assertEqual(result['published_rows_exactly_recomputed'], 2)
        self.assertNotEqual(result['cases'][0]['quality_video_original_paths'], result['cases'][1]['quality_video_original_paths'])

    def test_cross_case_existing_url_and_sha_swap_rejected(self):
        args = self.fixture(); args[2][0]['videos'] = copy.deepcopy(args[2][1]['videos'])
        with self.assertRaisesRegex(ValueError, 'Published case/model'): self.bind(args)

    def test_changed_published_checkpoint_rejected(self):
        args = self.fixture(); args[2][0]['checkpoint_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'Published case/model'): self.bind(args)

    def test_changed_published_source_or_quality_rejected(self):
        args = self.fixture(); args[2][0]['tracking_metrics'] = {'changed': True}
        with self.assertRaisesRegex(ValueError, 'Published case/model'): self.bind(args)

    def test_full_raw_tree_bytes_and_modes_match(self):
        path = self.root / 'original.bin'; path.write_bytes(b'synthetic raw inventory control')
        row = {'path': path.name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'mode': stat.S_IMODE(path.stat().st_mode)}
        self.assertTrue(adapter.verify_raw_tree(self.root, [row])['complete_bytes_sha_modes_and_file_set_match'])
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Full restored coverage'): adapter.verify_raw_tree(self.root, [row])

    def test_full_raw_tree_extra_file_rejected(self):
        (self.root / 'unexpected.bin').write_bytes(b'synthetic extra file')
        with self.assertRaisesRegex(ValueError, 'Full restored coverage'): adapter.verify_raw_tree(self.root, [])

    def test_raw_tree_path_order_is_canonical_for_directory_prefixes(self):
        (self.root / 'case').mkdir(); (self.root / 'case/x').write_bytes(b'nested'); (self.root / 'case.json').write_bytes(b'sibling')
        rows = [{'path': p.relative_to(self.root).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                 'mode': stat.S_IMODE(p.stat().st_mode)} for p in (self.root / 'case/x', self.root / 'case.json')]
        self.assertEqual(adapter.verify_raw_tree(self.root, rows)['original_files'], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
