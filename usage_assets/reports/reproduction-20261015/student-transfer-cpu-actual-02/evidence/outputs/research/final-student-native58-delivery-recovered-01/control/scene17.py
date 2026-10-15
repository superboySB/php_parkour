"""Thin default17 adapter; source core and supervisor stay byte unchanged."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from common import load, sha, require
from run_frozen_matrix import attach_gate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-plan',type=Path,required=True)
    p.add_argument('--helper-sha256',required=True)
    p.add_argument('--matrix-sha256',required=True)
    p.add_argument('native_args',nargs=argparse.REMAINDER)
    a=p.parse_args();argv=a.native_args
    if argv and argv[0]=='--':argv=argv[1:]
    require(not any(x in argv for x in ('--all-configs','--resume','--case-id','--case-limit','--plan','--plan-output')),
            'Fresh unfiltered default17 phase required')
    own=Path(__file__).resolve();source=Path('/workspace/php_parkour/scripts/research/sim2sim_scene_matrix.py')
    require(sha(own)==a.helper_sha256 and sha(source)==a.matrix_sha256,'Frozen scene control/core SHA differs')
    matrix=load(source,'native58_frozen_scene_core');plan=json.loads(a.expected_plan.read_text())
    require(plan['schema_version']==3 and plan['all_configurations'] is False
            and plan['planned_scenarios']==plan['planned_configurations']==len(plan['selections'])==17,
            'Actual CPU plan must contain exactly default17 scenarios/configurations')
    attach_gate(matrix,plan,own,a.helper_sha256)
    sys.argv=[str(source),*argv]
    matrix.main()


if __name__=='__main__':main()
