#!/usr/bin/env python3
"""Ordinary CPU/in-memory synthetic schema controls, not actual888 evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
