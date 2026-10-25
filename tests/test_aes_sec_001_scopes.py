from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from aes_sec_001_scan import (DEFAULT_REVIEW_DISPOSITIONS_PATH, format_github,
    format_markdown, scan, scan_source_for_apis)
from aes_sec_001_rekey import rekey
from aems_scope_coverage import coverage
from aes_sec_001_aggregate import scan_checkout
from tests import test_aes_sec_001_scan as scan_tests


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / '.git').mkdir()
        self.scope = self.root / 'alpha'
        self.scope.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def adoption(self, prefix=''):
        for name in ('SECURE-C-CXX.md', 'AES-SEC-001-waivers.md'):
            self.write(prefix + 'docs/engineering/' + name, 'Explicit synthetic test adoption.\n')

    def ledger(self, finding):
        return {'schema_version':'1.0.0','repository':'example/native',
            'baseline':{'captured_at':'2026-07-27','source':'synthetic historical baseline',
                'findings':[{k:getattr(finding,k) for k in ('finding_id','source_fingerprint','path','line','symbol')}]},
            'dispositions':[scan_tests.AesSec001ScanTests.disposition(finding)]}

    def test_exclusions_are_literal_segment_prefixes_and_repeatable(self):
        for name in ('alpha/a.c','alpha-extra/a.c','beta/a.c','root.c'):
            self.write(name, 'void f(){strcpy(d,s);}')
        report=scan(self.root,'example/native',True,exclude_paths=['alpha/','beta'])
        self.assertEqual(report.native_files,['alpha-extra/a.c','root.c'])
        self.assertEqual([f.path for f in report.findings],report.native_files)
        self.assertEqual(report.excluded_paths,['alpha','beta'])

    def test_invalid_exclusion_and_annotation_paths_fail_closed(self):
        report=scan(self.root,'example/native',True)
        for prefix in ('.','../alpha','/alpha','a/../b','a\\b','a\n::error','a*'):
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValueError):
                    scan(self.root,'example/native',True,exclude_paths=[prefix])
        for prefix in ('../alpha','/alpha','a\n::error'):
            with self.assertRaises(ValueError):format_github(report,prefix)

    def test_scope_reads_own_profile_and_has_scope_relative_identities(self):
        self.adoption()
        self.write('alpha/source.c','void f(){strcpy(d,s);}')
        report=scan(self.scope,'example/native',True)
        self.assertFalse(report.secure_profile_present)
        self.assertFalse(report.waiver_log_present)
        self.assertEqual(report.scan_root,'alpha')
        self.assertEqual(report.native_files,['source.c'])
        self.adoption('alpha/')
        self.assertTrue(scan(self.scope,'example/native',True).secure_profile_present)
        self.assertIn('`source.c`',format_markdown(report))
        original=report.to_dict()
        self.assertIn('file=alpha/source.c,',format_github(report,'alpha/'))
        self.assertIn('file=source.c,',format_github(report))
        self.assertEqual(report.to_dict(),original)

    def test_legacy_ledger_and_matching_optional_scope_are_accepted(self):
        path=self.write('alpha/source.c','void f(){memset(d,0,n);}')
        finding=scan_source_for_apis(self.scope,path,True)[0]
        ledger=self.ledger(finding)
        target='alpha/'+DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix()
        self.write(target,json.dumps(ledger))
        self.assertTrue(scan(self.scope,'example/native',True).passes_review_ratchet)
        ledger['scope']='alpha/'
        self.write(target,json.dumps(ledger))
        self.assertTrue(scan(self.scope,'example/native',True).passes_review_ratchet)
        ledger['scope']='beta'
        self.write(target,json.dumps(ledger))
        with self.assertRaisesRegex(ValueError,'scope.*expected'):
            scan(self.scope,'example/native',True)

    def test_symlink_source_and_borrowed_profile_do_not_pass(self):
        outside=self.write('outside.c','void f(){strcpy(d,s);}')
        (self.scope/'alias.c').symlink_to(outside)
        self.adoption()
        (self.scope/'docs').symlink_to(self.root/'docs',target_is_directory=True)
        report=scan(self.scope,'example/native',True)
        self.assertFalse(report.secure_profile_present)
        self.assertEqual(report.native_files,[])
        self.write(DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix(),'{}')
        with self.assertRaisesRegex(ValueError,'scope-local'):
            scan(self.scope,'example/native',True)

    def test_default_python_call_retains_repository_paths_and_identities(self):
        path=self.write('source.c','void f(){memset(d,0,n);}')
        expected=scan_source_for_apis(self.root,path,True)[0]
        report=scan(self.root,'example/native',True)
        self.assertEqual(report.scan_root,'.')
        self.assertEqual(report.excluded_paths,[])
        self.assertEqual(report.findings[0].finding_id,expected.finding_id)
        self.assertEqual(report.findings[0].source_fingerprint,expected.source_fingerprint)
        self.assertEqual(report.findings[0].path,'source.c')

    def test_cli_exclusion_and_annotation_prefix(self):
        self.write('alpha/source.c','void f(){strcpy(d,s);}')
        command=[sys.executable,str(ROOT/'scripts/aes_sec_001_scan.py'),str(self.root),
                 '--exclude','alpha','--format','json']
        run=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)['findings'],[])
        bad=subprocess.run(command+['--exclude','../escape'],capture_output=True,text=True)
        self.assertEqual(bad.returncode,2)
        self.assertEqual(bad.stdout,'')
        run=subprocess.run([sys.executable,str(ROOT/'scripts/aes_sec_001_scan.py'),str(self.scope),
            '--annotation-prefix','alpha','--format','github'],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('file=alpha/source.c,',run.stdout)

    def moved_history(self):
        old=self.write('old.c','void f(){memset(d,0,n);}')
        finding=scan_source_for_apis(self.root,old,True)[0]
        ledger=self.ledger(finding)
        new=self.scope/'new.c'
        old.rename(new)
        return ledger,new

    def test_rekey_conserves_history_and_preserves_review_metadata(self):
        ledger,new=self.moved_history()
        self.write('keep.c','void f(){memcpy(d,s,n);}')
        keep=scan_source_for_apis(self.root,self.root/'keep.c',True)[0]
        other=self.ledger(keep)
        ledger['baseline']['findings']+=other['baseline']['findings']
        ledger['dispositions']+=other['dispositions']
        before=copy.deepcopy(ledger)
        moved,remainder,report=rekey(ledger,self.root,'alpha',{'old.c':'new.c'})
        self.assertEqual(ledger,before)
        self.assertEqual(report['baseline_before'],report['baseline_moved']+report['baseline_remaining'])
        self.assertEqual(report['dispositions_before'],report['dispositions_moved']+report['dispositions_remaining'])
        self.assertEqual(report['approvals_created'],0)
        self.assertEqual(remainder['dispositions'],other['dispositions'])
        old=before['dispositions'][0]
        current=moved['dispositions'][0]
        for key in ('classification','rationale','invariant','evidence','owner','reviewer','reviewed_at','reassess_after','resolution_commit'):
            self.assertEqual(current[key],old[key])
        expected=scan_source_for_apis(self.scope,new,True)[0]
        self.assertEqual(current['finding_id'],expected.finding_id)
        self.assertEqual(current['source_fingerprint'],expected.source_fingerprint)
        self.write('alpha/'+DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix(),json.dumps(moved))
        self.assertTrue(scan(self.scope,'example/native',True).passes_review_ratchet)

    def test_rekey_refuses_changed_source_and_missing_identity(self):
        ledger,new=self.moved_history()
        new.write_text('void f(){memset(d,0,n+1);}')
        with self.assertRaisesRegex(ValueError,'fingerprint changed'):
            rekey(ledger,self.root,'alpha',{'old.c':'new.c'})
        new.write_text('void f(){}')
        with self.assertRaisesRegex(ValueError,'no exact current source match'):
            rekey(ledger,self.root,'alpha',{'old.c':'new.c'})

    def test_rekey_refuses_ambiguous_destination_and_unmapped_history(self):
        ledger,new=self.moved_history()
        with self.assertRaisesRegex(ValueError,'ambiguous path map'):
            rekey(ledger,self.root,'alpha',{'old.c':'new.c','other.c':'new.c'})
        with self.assertRaisesRegex(ValueError,'multiple aliases'):
            rekey(ledger,self.root,'alpha',{'old.c':'new.c','./old.c':'different.c'})
        with self.assertRaisesRegex(ValueError,'no retained history'):
            rekey(ledger,self.root,'alpha',{'unknown.c':'new.c'})

    def test_rekey_cli_never_overwrites_input_or_outputs(self):
        ledger,new=self.moved_history()
        input_path=self.write(DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix(),json.dumps(ledger))
        mapping=self.write('paths.json',json.dumps({'old.c':'new.c'}))
        command=[sys.executable,str(ROOT/'scripts/aes_sec_001_rekey.py'),str(self.root),
            '--ledger',str(input_path),'--new-scope','alpha','--path-map',str(mapping),
            '--output-directory',str(self.root/'build/move')]
        before=input_path.read_bytes()
        first=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stderr)
        report=json.loads((self.root/'build/move/rekey-report.json').read_text())
        self.assertEqual(report['dispositions_moved'],1)
        second=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(second.returncode,2)
        self.assertIn('refusing to overwrite',second.stderr)
        self.assertEqual(input_path.read_bytes(),before)
        mapping.write_text('{\"old.c\":\"new.c\",\"old.c\":\"new.c\"}')
        duplicate=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(duplicate.returncode,2)
        self.assertIn('duplicate JSON key',duplicate.stderr)

    def test_coverage_assigns_every_tracked_path_once_with_root_remainder(self):
        report=coverage(self.root,{'scopes':[{'id':'alpha','path':'alpha/'}]},
                        ['alpha/source.c','root.c','alpha-extra/source.c'])
        self.assertEqual(report['ownership']['alpha'],['alpha/source.c'])
        self.assertEqual(report['ownership']['.'],['alpha-extra/source.c','root.c'])
        self.assertEqual(report['scan_plan'],[{'scan_root':'.','exclude_paths':['alpha']},
                                            {'scan_root':'alpha','exclude_paths':[]}])
        self.assertEqual(report['tracked_file_count'],3)

    def test_coverage_refuses_duplicate_nested_missing_and_symlink_scopes(self):
        for scopes in ([{'id':'a','path':'alpha'},{'id':'b','path':'alpha'}],
                       [{'id':'a','path':'alpha/sub'}],
                       [{'id':'a','path':'missing'}],
                       [{'id':'a','path':'alpha'},{'id':'a','path':'beta'}]):
            with self.subTest(scopes=scopes):
                with self.assertRaises(ValueError):coverage(self.root,{'scopes':scopes},[])
        (self.root/'link').symlink_to(self.scope,target_is_directory=True)
        with self.assertRaises(ValueError):coverage(self.root,{'scopes':[{'id':'link','path':'link'}]},[])

    def test_composite_action_executes_scope_and_newline_exclusions_safely(self):
        self.adoption('alpha/')
        self.write('alpha/source.c','void f(){strcpy(d,s);}')
        self.write('alpha/excluded/no.c','void f(){strcpy(d,s);}')
        action=(ROOT/'.github/actions/aes-sec-001/action.yml').read_text()
        script=textwrap.dedent(action.split('      run: |\n',1)[1])
        env={**os.environ,'GITHUB_ACTION_PATH':str(ROOT/'.github/actions/aes-sec-001'),
            'GITHUB_REPOSITORY':'example/native','AEMS_REPOSITORY':'',
            'AEMS_SCAN_ROOT':'alpha','AEMS_EXCLUDE_PATHS':'excluded\nnot-present',
            'AEMS_INCLUDE_DANGEROUS':'true','AEMS_STRICT':'false','AEMS_STRICT_REVIEW_RATCHET':'false',
            'AEMS_OUTPUT_DIRECTORY':str(self.root/'build/evidence')}
        run=subprocess.run(['bash','-c',script],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('file=alpha/source.c,',run.stdout)
        report=json.loads((self.root/'build/evidence/report.json').read_text())
        self.assertEqual(report['native_files'],['source.c'])
        self.assertEqual(report['scan_root'],'alpha')
        self.assertEqual(report['excluded_paths'],['excluded','not-present'])
        env['AEMS_EXCLUDE_PATHS']='$(touch owned)'
        run=subprocess.run(['bash','-c',script],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertFalse((self.root/'owned').exists())

    def workflow_script(self, name):
        text=(ROOT/'.github/workflows/aes-sec-001-distributed.yml').read_text()
        step=text.split('      - name: '+name+'\n',1)[1].split('\n      - name:',1)[0]
        return textwrap.dedent(step.split('        run: |\n',1)[1])

    def test_artifact_identity_is_safe_and_distinguishes_sanitization_collisions(self):
        script=self.workflow_script('Resolve scope and evidence identity')
        values=[]
        for label in ('a/b','a-b','! unsafe: name\nmore'):
            output=self.root/'outputs'
            output.unlink(missing_ok=True)
            env={**os.environ,'AEMS_SCAN_ROOT':'alpha','AEMS_EVIDENCE_NAME':label,'GITHUB_OUTPUT':str(output)}
            run=subprocess.run(['bash','-c',script],cwd=self.root,env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            pairs=dict(line.split('=',1) for line in output.read_text().splitlines())
            self.assertRegex(pairs['artifact'],r'^[A-Za-z0-9_.-]+$')
            self.assertTrue(pairs['output'].startswith('build/aems/aes-sec-001/'))
            values.append(pairs['artifact'])
        self.assertEqual(len(set(values)),3)

    def test_workflow_refuses_scan_root_outside_checkout(self):
        script=self.workflow_script('Resolve scope and evidence identity')
        env={**os.environ,'AEMS_SCAN_ROOT':'..','AEMS_EVIDENCE_NAME':'','GITHUB_OUTPUT':str(self.root/'outputs')}
        run=subprocess.run(['bash','-c',script],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertNotEqual(run.returncode,0)
        self.assertFalse((self.root/'outputs').exists())

    def test_clang_policy_prefers_scope_then_falls_back_to_root_and_rejects_symlinks(self):
        script=self.workflow_script('Validate repository Clang-Tidy policy')
        self.write('.clang-tidy','root policy')
        tools=self.root/'bin';tools.mkdir()
        fake=self.write('bin/clang-tidy','#!/bin/sh\nprintf "%s\\n" "$@" > "$TRACE_FILE"\n')
        fake.chmod(0o755)
        env={**os.environ,'PATH':str(tools)+os.pathsep+os.environ['PATH'],
             'TRACE_FILE':str(self.root/'trace'),'AEMS_SCAN_ROOT':'alpha'}
        def run():return subprocess.run(['bash','-eu','-c',script],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertEqual(run().returncode,0)
        self.assertIn('--config-file=.clang-tidy',(self.root/'trace').read_text())
        config=self.write('alpha/.clang-tidy','scope policy')
        self.assertEqual(run().returncode,0)
        self.assertIn('--config-file=alpha/.clang-tidy',(self.root/'trace').read_text())
        config.unlink();config.symlink_to(self.root/'.clang-tidy')
        self.assertNotEqual(run().returncode,0)

    def declare(self, scopes):
        self.write('aes-manifest.yaml',json.dumps({'scopes':scopes}))

    def alpha_declaration(self):
        return {'id':'alpha','path':'alpha/','standards':[{'id':'AES-SEC-001','applicability':'applicable'}]}

    def test_aggregate_keeps_legacy_gates_for_documentation_only_scopes(self):
        self.adoption()
        path=self.write('alpha/source.c','void f(){memset(d,0,n);}')
        finding=scan_source_for_apis(self.root,path,True)[0]
        self.write(DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix(),json.dumps(self.ledger(finding)))
        self.declare([self.alpha_declaration()])
        report=scan_checkout(self.root,'example/native',True)
        self.assertIn('documentation-only',report['scope_mode'])
        self.assertTrue(report['review_dispositions']['passes_ratchet'])
        self.assertEqual(report['findings'][0]['path'],'alpha/source.c')

    def adopted_scope(self):
        self.adoption();self.adoption('alpha/')
        ledger,new=self.moved_history()
        moved,remainder,_=rekey(ledger,self.root,'alpha',{'old.c':'new.c'})
        self.write(DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix(),json.dumps(remainder))
        self.write('alpha/'+DEFAULT_REVIEW_DISPOSITIONS_PATH.as_posix(),json.dumps(moved))
        self.declare([self.alpha_declaration()])

    def test_aggregate_combines_scope_and_remainder_without_resetting_ids(self):
        self.adopted_scope()
        expected=scan(self.scope,'example/native',True).findings[0].finding_id
        report=scan_checkout(self.root,'example/native',True)
        self.assertEqual(report['scope_mode'],'scope-bound-ledgers')
        self.assertEqual(len(report['scope_reports']),2)
        self.assertEqual(report['scope_reports'][0]['excluded_paths'],['alpha'])
        self.assertEqual(report['review_dispositions']['reviewed'],1)
        self.assertEqual(report['findings'][0]['path'],'alpha/new.c')
        self.assertEqual(report['findings'][0]['finding_id'],expected)
        self.assertEqual(report['native_file_count'],1)
        self.assertTrue(report['summary']['requires_secure_profile'])
        self.assertTrue(report['summary']['passes_minimum_adoption_gate'])
        self.assertTrue(report['review_dispositions']['passes_ratchet'])

    def test_aggregate_refuses_unresolved_applicability_and_native_not_applicable(self):
        self.adopted_scope();(self.root/'beta').mkdir()
        beta={'id':'beta','path':'beta','standards':[{'id':'AES-SEC-001','applicability':'unknown'}]}
        self.declare([self.alpha_declaration(),beta])
        with self.assertRaisesRegex(ValueError,'unresolved'):scan_checkout(self.root,'example/native',True)
        beta['standards'][0].update(applicability='not-applicable',reason='Python only')
        self.declare([self.alpha_declaration(),beta])
        self.assertTrue(scan_checkout(self.root,'example/native',True)['summary']['passes_minimum_adoption_gate'])
        self.write('beta/new.cu','void native(){}')
        with self.assertRaisesRegex(ValueError,'contradicts'):scan_checkout(self.root,'example/native',True)

    def test_aggregate_does_not_ignore_missing_applicable_sibling_evidence(self):
        self.adopted_scope();(self.root/'beta').mkdir()
        beta=self.alpha_declaration();beta.update(id='beta',path='beta')
        self.declare([self.alpha_declaration(),beta])
        report=scan_checkout(self.root,'example/native',True)
        self.assertFalse(report['summary']['passes_minimum_adoption_gate'])


if __name__=='__main__':unittest.main()
