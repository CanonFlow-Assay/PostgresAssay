from pathlib import Path
import copy
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
PACKAGE=next(p.name for p in (ROOT/'src').iterdir() if p.is_dir())
engine=importlib.import_module(PACKAGE+'.engine')
CAT=json.loads((ROOT/'src'/PACKAGE/'catalogue.json').read_text())


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.snapshot=self.base/'snapshot.json'; self.policy=self.base/'policy.json'
        self.sample=json.loads((ROOT/'examples/snapshot.json').read_text())
        self.snapshot.write_text(json.dumps(self.sample))
        self.script=self.base/'acceptance.py'
        self.script.write_text('value = sum([2, 3])\nassert value == 5\n')
        self.config={'schemaVersion':1,'profile':CAT['profiles'][0],'requiredCommands':[[sys.executable,'acceptance.py']],'inputs':['acceptance.py']}
        self.save_policy()

    def save_policy(self): self.policy.write_text(json.dumps(self.config))
    def audit(self,command='verify'):
        return engine.audit(self.snapshot,self.policy,CAT,{'name':CAT['assay'],'version':'test'},command)[0]
    def write_snapshot(self): self.snapshot.write_text(json.dumps(self.sample))
    def cli(self,*args):
        return subprocess.run([sys.executable,'-m',PACKAGE,*map(str,args)],env={**os.environ,'PYTHONPATH':str(ROOT/'src')},cwd=self.base,capture_output=True,text=True,timeout=40)

    def test_real_sample_and_executed_test_pass(self):
        result=self.audit(); self.assertEqual(result['verdict'],'Pass'); self.assertEqual(result['commands'][0]['status'],'Pass')
    def test_scan_is_not_executed_verification(self):
        result=self.audit('scan'); self.assertEqual(result['verdict'],'Inconclusive'); self.assertEqual(result['commands'][0]['status'],'NotRun')
    def test_missing_required_behavior_is_inconclusive(self):
        self.config['requiredCommands']=[]; self.save_policy(); self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_undeclared_command_inputs_are_inconclusive(self):
        self.config['inputs']=[]; self.save_policy(); self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_every_blocking_rule_detects_a_real_value_violation(self):
        for profile in CAT['profiles']:
            for rule in CAT['rules']:
                if profile not in rule['profiles']:continue
                document=copy.deepcopy(self.sample)
                target=document
                parts=rule['path'].strip('/').split('/')
                for p in parts[:-1]:target=target[p]
                test=rule
                if rule['kind']=='each':
                    target=target[parts[-1]][0]; parts=rule['field'].strip('/').split('/');test=rule['test']
                kind=test['kind']
                bad={'boolean':not test.get('expected',False),'integer':0,'bytes':'0 B','nonempty':'','enum':'unsupported-value'}[kind]
                target[parts[-1]]=bad
                checks=engine.evaluate(document,CAT,profile)
                self.assertTrue(any(c['ruleId']==rule['id'] and c['outcome']=='failed' for c in checks),(profile,rule['id']))
    def test_missing_setting_is_not_assumed_default(self):
        self.sample['settings']={}; self.write_snapshot(); self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_unsupported_engine_keeps_observations_and_incompleteness(self):
        self.sample['version']='0.0.0'; self.write_snapshot(); result=self.audit(); self.assertEqual(result['verdict'],'Inconclusive');self.assertTrue(result['checks'])
    def test_bad_type_is_not_interpreted_as_valid_value(self):
        rule=next(r for r in CAT['rules'] if r['kind']=='boolean' or r['kind']=='integer') if CAT['product']!='postgresql' else CAT['rules'][0]
        parts=rule['path'].strip('/').split('/'); self.sample[parts[0]][parts[1]]=[];self.write_snapshot()
        self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_boolean_is_not_an_integer(self):
        with self.assertRaises(ValueError):engine.scalar(True,{'kind':'integer','min':1})
    def test_duplicate_json_key_is_rejected(self):
        self.snapshot.write_text('{"schemaVersion":1,"schemaVersion":1}')
        self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_nan_is_rejected(self):
        self.snapshot.write_text('{"bad":NaN}');self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_invalid_utf8_is_incomplete(self):
        self.snapshot.write_bytes(b'\xff');self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_oversize_input_is_incomplete(self):
        self.snapshot.write_bytes(b' '*(engine.LIMIT+1));self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_missing_snapshot_is_incomplete(self):
        self.snapshot.unlink();self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_unknown_policy_field_is_rejected_before_execution(self):
        self.config['requiredCommand']='echo unsafe';self.save_policy()
        with self.assertRaises(ValueError):self.audit()
    def test_shell_string_is_rejected(self):
        self.config['requiredCommands']=['echo unsafe'];self.save_policy()
        with self.assertRaises(ValueError):self.audit()
    def test_input_escape_is_rejected(self):
        self.config['inputs']=['../other'];self.save_policy()
        with self.assertRaises(ValueError):self.audit()
    def test_failed_command_is_known_failure(self):
        self.script.write_text('raise SystemExit(7)');self.assertEqual(self.audit()['verdict'],'Fail')
    def test_missing_executable_is_unavailable(self):
        self.config['requiredCommands']=[['./no-such-executable']];self.save_policy();self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_changed_command_input_invalidates_evidence(self):
        self.script.write_text('from pathlib import Path\nPath("acceptance.py").write_text("changed")')
        self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_changed_snapshot_invalidates_evidence(self):
        self.script.write_text('from pathlib import Path\nPath("snapshot.json").write_text("{}")')
        self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_timeout_is_not_a_success(self):
        result=engine.run_command([sys.executable,'-c','import time;time.sleep(3)'],self.base,timeout=.1)
        self.assertEqual(result['status'],'Unavailable');self.assertEqual(result['reason'],'timeout')
    def test_closed_output_does_not_escape_timeout(self):
        result=engine.run_command([sys.executable,'-c','import os,time;os.close(1);os.close(2);time.sleep(3)'],self.base,timeout=.1)
        self.assertEqual(result['status'],'Unavailable')
    def test_output_is_bounded(self):
        result=engine.run_command([sys.executable,'-c','print("x"*10000)'],self.base,output_limit=100)
        self.assertEqual(result['status'],'Unavailable');self.assertLessEqual(result['collectedBytes'],101)
    def test_input_symlink_is_not_followed(self):
        link=self.base/'linked.json';link.symlink_to(self.snapshot)
        with self.assertRaises(ValueError):engine.read_bytes(link)
    def test_receipt_cannot_overwrite_input(self):
        before=self.snapshot.read_bytes()
        with self.assertRaises(ValueError):engine.publish({},self.snapshot,[self.snapshot])
        self.assertEqual(self.snapshot.read_bytes(),before)
    def test_hardlink_output_is_rejected(self):
        output=self.base/'hardlink';os.link(self.snapshot,output)
        with self.assertRaises(ValueError):engine.publish({},output,[self.snapshot])
    def test_symlink_parent_output_is_rejected(self):
        folder=self.base/'link';folder.symlink_to(self.base,target_is_directory=True)
        with self.assertRaises(ValueError):engine.publish({},folder/'out.json',[self.snapshot])
    def test_cli_verdict_and_atomic_publication(self):
        output=self.base/'receipt.json';run=self.cli('verify',self.snapshot,'--policy',self.policy,'--out',output)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout),json.loads(output.read_text()))
    def test_cli_output_failure_is_tool_failure(self):
        run=self.cli('verify',self.snapshot,'--policy',self.policy,'--out',self.snapshot)
        self.assertEqual(run.returncode,3);self.assertEqual(json.loads(run.stdout)['verdict'],'ToolFailure')
    def test_assess_retains_raw_receipt(self):
        run=self.cli('assess',self.snapshot,'--policy',self.policy);result=json.loads(run.stdout)
        self.assertEqual(run.returncode,0);self.assertEqual(result['receipt']['verdict'],'Pass');self.assertTrue(result['receipt']['checks'])
    def test_catalog_explain_and_doctor_have_distinct_authority(self):
        self.assertEqual(self.cli('catalog').returncode,0)
        self.assertEqual(self.cli('explain',CAT['rules'][0]['id']).returncode,0)
        self.assertEqual(self.cli('explain','unknown').returncode,3)
        self.assertEqual(json.loads(self.cli('doctor').stdout)['authority'],'readiness-only')
    def test_empty_array_cannot_hide_unobserved_scope(self):
        rule=next((r for r in CAT['rules'] if r['kind']=='each'),None)
        if rule is None:self.skipTest("profile has no array-valued rules")
        self.sample[rule['path'].strip('/')]=[];self.write_snapshot();self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_one_failure_and_one_unavailable_array_member_are_both_retained(self):
        rule=next((r for r in CAT['rules'] if r['kind']=='each'),None)
        if rule is None:self.skipTest("profile has no array-valued rules")
        test=rule['test'];bad=not test.get('expected',False) if test['kind']=='boolean' else 0 if test['kind']=='integer' else 'trust'
        self.sample[rule['path'].strip('/')]=[{rule['field'].strip('/'):bad},{}];self.write_snapshot();result=self.audit()
        self.assertEqual(result['verdict'],'Fail');self.assertTrue(result['missingEvidence'])
    def test_bytes_require_real_positive_units(self):
        for val in ['256 MiB','1GB','0.5 GiB']:self.assertTrue(engine.scalar(val,{'kind':'bytes'}))
        self.assertFalse(engine.scalar('0 B',{'kind':'bytes'}))
        for val in ['unlimited','80%',True]:
            with self.assertRaises(ValueError):engine.scalar(val,{'kind':'bytes'})
    def test_deterministic_scan_receipt(self):
        self.assertEqual(engine.canonical(self.audit('scan')),engine.canonical(self.audit('scan')))
    def test_independent_deterministic_archive_consumer(self):
        subprocess.run([sys.executable,str(ROOT/'eng/package.py')],check=True,capture_output=True)
        archive=ROOT/'artifacts'/(PACKAGE+'.pyz');first=hashlib.sha256(archive.read_bytes()).hexdigest()
        subprocess.run([sys.executable,str(ROOT/'eng/package.py')],check=True,capture_output=True)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),first)
        consumer=self.base/'consumer.pyz';shutil.copy(archive,consumer)
        env={**os.environ};env.pop('PYTHONPATH',None)
        run=subprocess.run([sys.executable,str(consumer),'verify',str(self.snapshot),'--policy',str(self.policy)],cwd=self.base,env=env,text=True,capture_output=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(run.stdout)['verdict'],'Pass')

    def test_cli_invalid_usage_is_structured_tool_failure(self):
        result=self.cli('verify')
        self.assertEqual(result.returncode,3)
        self.assertEqual(json.loads(result.stdout)['verdict'],'ToolFailure')
    def test_policy_change_after_command_invalidates_evidence(self):
        self.script.write_text('from pathlib import Path\nPath("policy.json").write_text("{}")')
        self.assertEqual(self.audit()['verdict'],'Inconclusive')
    def test_producer_drift_cannot_retain_pass(self):
        copyroot=self.base/'producer'
        shutil.copytree(ROOT/'src',copyroot)
        target=copyroot/PACKAGE/'engine.py'
        self.script.write_text('from pathlib import Path\np=Path('+repr(str(target))+')\np.write_text(p.read_text()+"\\n# changed\\n")')
        run=subprocess.run([sys.executable,'-m',PACKAGE,'verify',str(self.snapshot),'--policy',str(self.policy)],env={**os.environ,'PYTHONPATH':str(copyroot)},cwd=self.base,text=True,capture_output=True)
        self.assertEqual(run.returncode,2,run.stdout+run.stderr)
        self.assertIn('producer changed during required commands',json.loads(run.stdout)['missingEvidence'])


    def test_admitted_rule_sources_are_primary_and_present(self):
        register=json.loads((ROOT/'docs/sources.json').read_text())
        source_by_id={r['id']:r for r in register['sources']}
        self.assertEqual(len(source_by_id),len(register['sources']))
        for rule in CAT['rules']:
            self.assertEqual(source_by_id[rule['source']]['kind'],'primary',rule['id'])
    def test_skill_references_survive_standalone_installation(self):
        import re
        skill=next((ROOT/'skills').iterdir())
        for file in skill.rglob('*.md'):
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',file.read_text()):
                if '://' in target:continue
                resolved=(file.parent/target.split('#')[0]).resolve()
                self.assertTrue(resolved.is_relative_to(skill.resolve()))
                self.assertTrue(resolved.exists(),target)


if __name__=='__main__':unittest.main()
