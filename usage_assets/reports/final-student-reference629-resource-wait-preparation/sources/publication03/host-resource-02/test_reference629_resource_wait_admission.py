"""Offline hostresource refusal tests; synthetic transformed CPU fixtures, no nvidia/Docker/native."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType
import unittest
sys.dont_write_bytecode=True
ROOT=Path('/home/dzp/projects/php_parkour');REPRO=ROOT/'outputs/research/reproduction-20261015'
PUB=ROOT/'outputs/research/final-student-reference629-crossboot-publication-preparation-02'
PREP=ROOT/'outputs/research/final-student-reference629-crossboot-preparation-02'
def load(p):
    m=ModuleType(p.stem);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
GATE=load(PUB/'admission.py');READER=load(PUB/'reference629_resource_wait_admission.py')

class ResourceAdmission(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=REPRO/'local-checks');self.root=Path(self.temp.name)
        candidates=list((REPRO/'local-checks/reference629-resource-wait-controls-03/fixtures').glob('test_busy_then_idle*/result'))
        assert len(candidates)==1;self.original=candidates[0];self.directory=self.root/'runs/pure/host/resource-admission'
        shutil.copytree(self.original,self.directory)
        self.e=GATE.Evidence();self.receipt=json.loads((self.directory/'receipt.json').read_bytes())
        def translate(v):
            if isinstance(v,dict):return {k:translate(x) for k,x in v.items()}
            if isinstance(v,list):return [translate(x) for x in v]
            if isinstance(v,str):return v.replace(str(self.original),str(self.directory))
            return v
        self.receipt=translate(self.receipt);self.receipt['synthetic_fixture']='Offline transformation of ordinary Python CPU receipts; nvidia argv are synthetic, no actual GPU evidence.'
        source=self.e.fingerprint(PREP/'reference629_gpu_resource_wait.py');self.receipt['source']=self.receipt['source_after']=source
        self.receipt['budget_seconds']=1800;self.receipt['poll_seconds']=5
        self.owner=self.receipt['owner'];self.parent={'boot_id':self.receipt['boot_id']}
        self.contract={'base':str(self.root),'global_host_lock':self.receipt['mutex_initial']['path']}
        for row in self.receipt['rounds']:
            row['identity_query']['argv']=['nvidia-smi','--query-gpu=uuid','--format=csv,noheader,nounits']
            row['compute_query']['argv']=['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits']
        self.flush()
    def tearDown(self):self.temp.cleanup()
    def flush(self):
        for row in self.receipt['rounds']:
            d=self.directory/f"round-{row['index']:05d}"
            for key,label in [('identity_query','gpu-identity'),('compute_query','gpu-compute')]:
                (d/(label+'.execution.json')).write_text(json.dumps(row[key],indent=2)+'\n')
        (self.directory/'receipt.json').write_text(json.dumps(self.receipt,indent=2)+'\n')
        self.item={'kind':'pure','native_receipt':{'host_resource_admission':self.receipt,'host_resource_admission_receipt':GATE.Evidence().fingerprint(self.directory/'receipt.json')}}
    def verify(self):return READER.verify(GATE.Evidence(),PREP,self.contract,self.item,self.parent,self.owner)
    def test_synthetic_busy_to_idle_complete_raw_chain(self):
        r=self.verify();self.assertEqual(r['status'],'verified_actual_host_only_resource_admission');self.assertEqual((r['rounds'],r['query_count']),(2,4))
    def test_late_query_actual0_failed_status_rejected(self):
        q=self.receipt['rounds'][0]['identity_query'];q['status']='failed';q['actual_wait_returncode']=0;q['errors']=[{'message':'Synthetic late completion; real0 still failure'}];self.flush()
        with self.assertRaisesRegex(ValueError,'Actual query0'):self.verify()
    def test_nonzero_bool_or_null_query_wait_rejected(self):
        for code in (1,True,None):
            self.receipt['rounds'][0]['identity_query']['actual_wait_returncode']=code;self.flush()
            with self.subTest(code=code),self.assertRaisesRegex(ValueError,'Actual query0'):self.verify()
    def test_mutex_owner_or_inode_drift_rejected(self):
        self.receipt['rounds'][0]['mutex_after']['inode']+=1;self.flush()
        with self.assertRaisesRegex(ValueError,'same|Same'):self.verify()
    def test_raw_compute_sha_mutation_rejected(self):
        p=Path(self.receipt['rounds'][-1]['compute_query']['stdout']['path']);p.write_text(READER.GPU+', 456\n')
        with self.assertRaisesRegex(ValueError,'bound bytes'):self.verify()
    def test_busy_cannot_be_relabelled_idle(self):
        self.receipt['rounds'][0]['status']='idle';self.flush()
        with self.assertRaisesRegex(ValueError,'Raw GPU predicate'):self.verify()
    def test_missing_raw_and_extra_unsealed_files_rejected(self):
        p=self.directory/'unexpected';p.write_text('synthetic extra')
        with self.assertRaisesRegex(ValueError,'file-set'):self.verify()
        p.unlink();Path(self.receipt['rounds'][0]['identity_query']['stderr']['path']).unlink()
        with self.assertRaises((ValueError,FileNotFoundError)):self.verify()
    def test_source_parent_default_budget_or_pending_signal_drift_rejected(self):
        for key,value in [('budget_seconds',1801),('poll_seconds',4),('query_timeout_seconds',16),('pending_signals',[15])]:
            previous=copy.deepcopy(self.receipt[key]);self.receipt[key]=value;self.flush()
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
            self.receipt[key]=previous
if __name__=='__main__':unittest.main(verbosity=2)
