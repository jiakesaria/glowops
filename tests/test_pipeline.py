"""Integration checks for evaluation boundaries, generation, Jev, and credential handling."""
import json
import os
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from config import ROOT, get_config
from contracts.schema import Failure, TestCase, Verdict
from generate import validate_candidates
from jev import JevError, ask
from run_tests import evaluate_case, format_failures, load_cases, run_evaluation, summarize, worker
from screening import QUESTIONS, combine
from telemetry import completion
from run_rounds import continue_run
from run_tests import input_hashes, write_json
from run_tests import CheckerExecutionError, main as evaluation_main
from generate import generate_candidates


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.verdict = Verdict.model_validate_json((ROOT / 'contracts/sample_verdict.json').read_text())
        self.case = TestCase(id='T1', hypothesis=self.verdict.hypothesis, split='learn',
                             expected_decision='revise', rationale='Draft fixture label for a wiring test.')

    def test_benchmark_has_required_distribution_and_valid_shared_format(self):
        rows = load_cases(ROOT / 'data/tests.json')
        self.assertEqual(Counter(x.expected_decision for x in rows), {'proceed': 7, 'revise': 7, 'reject': 6})
        self.assertEqual(Counter(x.split for x in rows), {'learn': 10, 'holdout': 10})
        for split in ('learn', 'holdout'):
            self.assertEqual({x.expected_decision for x in rows if x.split == split}, {'proceed', 'revise', 'reject'})

    def test_worker_passes_metadata_but_never_expected_answers(self):
        calls = []
        def check(hypothesis, **kwargs):
            calls.append((hypothesis, kwargs))
            return self.verdict
        with patch('checker.check', check):
            result = worker({'hypothesis': self.case.hypothesis, 'fake': False, 'with_jev': False,
                             'round': 2, 'split': 'learn', 'test_id': 'T1', 'run_id': 'run'})
        self.assertTrue(result['ok'])
        self.assertEqual(calls[0][1]['round'], 2)
        self.assertNotIn('expected_decision', calls[0][1])
        self.assertNotIn('rationale', calls[0][1])

    def test_learning_failures_match_sylvias_contract_and_exclude_holdout_and_errors(self):
        mismatch = evaluate_case(self.case, lambda _: self.verdict)
        holdout = {**mismatch, 'id': 'H', 'split': 'holdout'}
        error = {**mismatch, 'id': 'E', 'status': 'error', 'response': None, 'actual_decision': None}
        values = format_failures([mismatch, holdout, error], round_number=2, model='test-model')
        self.assertEqual(len(values), 1)
        failure = Failure.model_validate(values[0])
        self.assertEqual((failure.test_id, failure.round, failure.model), ('T1', 2, 'test-model'))
        score = summarize([mismatch, holdout, error])
        self.assertEqual(score['assigned'], 3)
        self.assertEqual(score['errors'], 1)

    def test_holdout_run_does_not_replace_learning_handoff(self):
        destination = self.root / 'failures.json'
        destination.write_text('["preserve learning output"]')
        case = self.case.model_copy(update={'split': 'holdout'})
        run_evaluation([case], self.root / 'holdout', fake=True,
                       failure_output=destination, call=lambda _: self.verdict)
        self.assertEqual(json.loads(destination.read_text()), ['preserve learning output'])

    def test_wrong_hypothesis_and_exception_are_errors_without_secret_text(self):
        wrong = self.verdict.model_copy(update={'hypothesis': 'wrong input'})
        self.assertEqual(evaluate_case(self.case, lambda _: wrong)['status'], 'error')
        def broken(_):
            raise RuntimeError('do-not-log-this-secret')
        result = evaluate_case(self.case, broken)
        self.assertEqual(result['status'], 'error')
        self.assertNotIn('do-not-log-this-secret', json.dumps(result))

    def test_worker_error_type_survives_without_provider_message(self):
        def broken(_):
            raise CheckerExecutionError('APITimeoutError')
        row = evaluate_case(self.case, broken)
        self.assertEqual(row['error'], 'APITimeoutError')
        self.assertEqual(row['status'], 'error')

    def test_error_retry_preserves_original_score_and_learning_handoff(self):
        second = self.case.model_copy(update={'id': 'T2'})
        cases = [self.case, second]
        prior = self.root / 'results/prior'
        write_json(self.root / 'data/tests.json', [c.model_dump() for c in cases])
        write_json(prior / 'tests_snapshot.json', [c.model_dump() for c in cases])
        (prior / 'results.jsonl').write_text(json.dumps({'id': 'T1', 'status': 'error'}) + '\n' +
                                            json.dumps({'id': 'T2', 'status': 'mismatch'}) + '\n')
        write_json(self.root / 'results/single_run_summary.json', {'original': True})
        write_json(self.root / 'data/failures.json', ['preserve'])
        score = summarize([evaluate_case(self.case, lambda _: self.verdict)])
        with patch('run_tests.ROOT', self.root), patch('run_tests.input_hashes', return_value={}), \
             patch('run_tests.run_evaluation', return_value=score) as evaluate:
            write_json(prior / 'manifest.json', {'mode': 'fake', 'with_jev': False, 'model': 'fake',
                'round': 0, 'input_sha256': {}})
            result = evaluation_main(['--fake', '--tests', str(self.root / 'data/tests.json'),
                                      '--retry-errors-from', str(prior)])
        self.assertEqual(result, 0)
        self.assertEqual([c.id for c in evaluate.call_args.args[0]], ['T1'])
        self.assertIsNone(evaluate.call_args.kwargs['failure_output'])
        self.assertEqual(json.loads((self.root / 'results/single_run_summary.json').read_text()), {'original': True})
        self.assertEqual(json.loads((self.root / 'data/failures.json').read_text()), ['preserve'])

    def test_generator_rejects_unknown_references_and_duplicates(self):
        paper = SimpleNamespace(id='known')
        candidate = {'hypothesis': 'A measurable association.', 'source_paper_ids': ['known'],
                     'source_basis': 'Supplied finding', 'extension_rationale': 'New period',
                     'required_data': ['Documented variables']}
        self.assertEqual(len(validate_candidates(json.dumps({'candidates': [candidate]}), [paper], 1)), 1)
        bad = {**candidate, 'source_paper_ids': ['fabricated']}
        for rows, count in (([bad], 1), ([candidate, candidate], 2), ([candidate], 2)):
            with self.assertRaises(ValueError):
                validate_candidates(json.dumps({'candidates': rows}), [paper], count)

    def test_jev_uses_typed_request_and_pinned_model(self):
        requests = []
        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(request.headers['authorization'], 'Bearer environment-key')
            return httpx.Response(200, json={'answers': {
                'decision': {'type': 'choice', 'choice': 'revise'},
                'research_value': {'type': 'choice', 'choice': 'needs_justification'}},
                'usage': {'input_tokens': 12, 'output_tokens': 3}})
        (self.root / '.env').write_text('TYPESAFE_API_KEY=file-key\n')
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'environment-key'}, clear=True):
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                result = ask({'hypothesis': 'Example'}, QUESTIONS, root=self.root, client=client)
        self.assertEqual(requests[0]['model'], 'jev-1.13.0')
        self.assertEqual(result['answers']['decision']['choice'], 'revise')
        text = (self.root / 'results/api_calls.jsonl').read_text()
        self.assertNotIn('environment-key', text)
        self.assertIn('input_tokens', text)

    def test_jev_service_errors_never_become_decisions_or_leak_response_bodies(self):
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'secret-header'}, clear=True):
            for status_code, body in ((401, {'error': 'secret-provider-body'}),
                                      (200, {'answers': {'decision': {'type': 'choice', 'choice': 'invalid'}}})):
                with httpx.Client(transport=httpx.MockTransport(
                    lambda _: httpx.Response(status_code, json=body))) as client:
                    with self.assertRaises(JevError) as caught:
                        ask({}, QUESTIONS, root=self.root, client=client)
                self.assertNotIn('secret', str(caught.exception))
        text = (self.root / 'results/api_calls.jsonl').read_text()
        self.assertNotIn('secret', text)

    def test_disagreement_or_weak_value_requires_revision(self):
        def assessment(decision, value):
            return {'answers': {'decision': {'choice': decision}, 'research_value': {'choice': value}}}
        self.assertEqual(combine(self.verdict, assessment('proceed', 'worth_investigating')).decision, 'proceed')
        self.assertEqual(combine(self.verdict, assessment('reject', 'worth_investigating')).decision, 'revise')
        self.assertEqual(combine(self.verdict, assessment('proceed', 'needs_justification')).decision, 'revise')

    def test_foundry_dotenv_explicit_loading_and_shell_priority(self):
        (self.root / '.env').write_text('MODEL=foundry\nFOUNDRY_API_KEY=file-key\nFOUNDRY_DEPLOYMENT=DeepSeek-V4-Flash-2\n')
        with patch.dict(os.environ, {'FOUNDRY_API_KEY': 'environment-key'}, clear=True):
            settings = get_config(root=self.root)
        self.assertEqual(settings.api_key, 'environment-key')
        self.assertEqual(settings.model_id, 'DeepSeek-V4-Flash-2')
        self.assertTrue(settings.base_url.endswith('/openai/v1/'))
        self.assertNotIn('environment-key', repr(settings))

    def test_completion_telemetry_records_errors_without_provider_details(self):
        settings = get_config(root=self.root)
        def fail(**kwargs):
            raise RuntimeError('private-provider-error')
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail)))
        with self.assertRaises(RuntimeError):
            completion(settings, client, model='test', messages=[])
        log = (self.root / 'results/api_calls.jsonl').read_text()
        self.assertNotIn('private-provider-error', log)
        self.assertEqual(json.loads(log)['status'], 'error')

    def test_real_rounds_cannot_skip_pending_human_review(self):
        settings = get_config(root=self.root)
        write_json(self.root / 'data/tests.json', [self.case.model_dump()])
        state = {'round': 1, 'phase': 'review', 'history': [], 'current': {},
                 'input_sha256': input_hashes(), 'options': {
                     'fake': False, 'rounds': 1, 'model': settings.model_id}}
        with patch('run_rounds.get_config', return_value=settings), \
             patch('run_rounds.status', return_value=3), \
             patch('run_rounds.run_evaluation') as evaluate:
            self.assertEqual(continue_run(self.root, state, review_complete=True), 3)
            evaluate.assert_not_called()
        self.assertEqual(state['phase'], 'review')

    def test_changed_inputs_block_round_resume(self):
        with self.assertRaises(ValueError):
            continue_run(self.root, {'options': {}, 'input_sha256': {'changed': 'content'}})

    def test_generation_uses_real_source_context_and_validates_model_output(self):
        from checker import load_inputs
        papers, datasets, _, _ = load_inputs(get_config())
        candidate = {'hypothesis': 'A testable comparison over a specified period.',
                     'source_paper_ids': [papers[0].id], 'source_basis': 'Supplied finding',
                     'extension_rationale': 'Measurement comparison', 'required_data': ['Documented variables']}
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
                message=SimpleNamespace(content=json.dumps({'candidates': [candidate]})))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        values = generate_candidates(1, settings=get_config(root=self.root), papers=papers[:1],
                                     datasets=datasets, client=client)
        context = json.loads(calls[0]['messages'][1]['content'])
        self.assertEqual(context['papers'][0]['id'], papers[0].id)
        items = context['output_schema']['properties']['candidates']
        self.assertEqual((items['minItems'], items['maxItems']), (1, 1))
        self.assertIn('EXACTLY 1', calls[0]['messages'][0]['content'])
        self.assertNotIn('expected_decision', json.dumps(context))
        self.assertEqual(values[0].source_paper_ids, [papers[0].id])

    def test_saved_candidate_can_be_rescreened_without_regeneration(self):
        from checker import load_inputs
        from generate import run
        papers, datasets, _, _ = load_inputs(get_config())
        candidate = {'hypothesis': self.verdict.hypothesis, 'source_paper_ids': [papers[0].id],
                     'source_basis': 'Supplied finding', 'extension_rationale': 'Comparison',
                     'required_data': ['Documented fields']}
        prior = [{'candidate_id': 'keep-this-id', 'generator_model': 'original-generator',
                  'mode': 'real', 'candidate': candidate}]
        path = self.root / 'saved.json'
        write_json(path, prior)
        with patch('generate.ROOT', self.root), \
             patch('generate.get_config', return_value=get_config(root=self.root)), \
             patch('generate.load_inputs', return_value=(papers, datasets, [], False)), \
             patch('generate.generate_candidates') as generator, \
             patch('generate.screen', return_value=(self.verdict, {'answers': {}})):
            result = run(screen_file=path)
        generator.assert_not_called()
        self.assertEqual(result[0]['candidate_id'], 'keep-this-id')
        self.assertEqual(result[0]['generator_model'], 'original-generator')
        self.assertEqual(result[0]['status'], 'screened')
        events = [json.loads(line) for line in (self.root / 'data/candidate_ledger.jsonl').read_text().splitlines()]
        self.assertEqual([x['status'] for x in events], ['screening_started', 'screened'])


if __name__ == '__main__':
    unittest.main()
