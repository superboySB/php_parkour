from pathlib import Path
import datetime as dt
import json

base=Path('/outputs/live-audit-0653')
matrix=json.loads((base/'captured-matrix.json').read_text())
cases=[]
for item in matrix['selections']:
    if item.get('status')!='completed': continue
    result=item['result']; sim=result['simulation']
    cases.append({'case_id':item['case_id'],'scenario':item['scenario'],
                  'command':result['config']['commands'],'reference_clip_seconds':item['reference_clip_seconds'],
                  'original_videos':result['videos'],'output':item['attempts'][-1]['output'],
                  'policy_seconds':sim['policy_simulation_seconds'],'active_samples':sim['active_samples'],
                  'minimum_pelvis_height_m':sim['minimum_pelvis_height_m'],'minimum_base_up_z':sim['minimum_base_up_z'],
                  'low_pelvis_detected':sim['low_pelvis_detected'],'fall_detected':sim['fall_detected'],
                  'fall_criterion':sim['fall_criterion'],'fall_detection_is_heuristic':sim['fall_detection_is_heuristic'],
                  'survival_passed':result['survival_passed'],'quality_verified':False,'obstacle_course_completion_verified':False})
report={'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'captured_completed_cases':len(cases),
        'heuristic_survival':sum(x['survival_passed'] for x in cases),
        'low_pelvis_events':sum(x['low_pelvis_detected'] for x in cases),
        'fall_events':sum(x['fall_detected'] for x in cases),
        'union_threshold_events':sum(not x['survival_passed'] for x in cases),
        'cases':cases,'scope':'Original retained closed-loop movies/threshold metrics for the captured completed subset, constant-forward commands, not reference-motion replay or obstacle-course success',
        'quality_verified':False}
path=base/'quality-stage.json';path.write_text(json.dumps(report,indent=2)+'\n');path.chmod(0o644)
print(json.dumps({key:value for key,value in report.items() if key!='cases'},indent=2))
