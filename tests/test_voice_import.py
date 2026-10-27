import runpy
import unittest
from pathlib import Path
from speech_text import digits, prepare, prepare_for_local, pronunciation_guide
from voice_catalog import catalog, resolve_call_voice

ROOT = Path(__file__).resolve().parents[1]


class NumberSpeech(unittest.TestCase):
    def test_leading_zeros_survive(self):
        self.assertEqual(prepare('My account number is 0042.'), 'My account number is zero zero four two.')

    def test_last_four_that_looks_like_a_year(self):
        self.assertEqual(prepare('The last four are 2026.'), 'The last four are two zero two six.')

    def test_year_stays_a_year(self):
        self.assertEqual(prepare('My appointment is in 2026.'), 'My appointment is in 2026.')

    def test_money_and_duration_keep_their_value(self):
        text = 'The bill was $1,250.00 for 120 minutes.'
        self.assertEqual(prepare(text), text)

    def test_local_currency_has_explicit_units(self):
        self.assertEqual(prepare_for_local('The charge was $35.'), 'The charge was 35 dollars.')
        self.assertEqual(prepare_for_local('The credit is $1.05.'), 'The credit is 1 dollar and 5 cents.')

    def test_phone_groups(self):
        self.assertEqual(digits('415 730 3332'), 'four one five, seven three zero, three three three two')

    def test_single_digit_groups_flow_together(self):
        self.assertEqual(digits('0-0-4-2'), 'zero zero four two')

    def test_account_pronunciation_guide_preserves_zero(self):
        self.assertEqual(pronunciation_guide(['account number: 0042', 'charge: $35']),
            [{'word': '0042', 'pronunciation': 'zero zero four two'}])


class CallingPayloads(unittest.TestCase):
    def test_questions_use_selected_clone(self):
        module = runpy.run_path(str(ROOT / 'phone-ask'))
        body = module['build_request']('+15555550123', 'Example store', ['What are your hours?'])
        self.assertEqual(body['voice'], catalog()['voices']['george-natural']['blandId'])
        self.assertIn('one digit at a time', body['task'])

    def test_errand_uses_natural_and_digit_guide(self):
        module = runpy.run_path(str(ROOT / 'phone-do'))
        body = module['build_request']({'who': 'Example', 'number': '+15555550123', 'goal': 'Ask a question',
            'facts': ['account number: 0042'], 'limits': [], 'voice': 'george-natural'})
        self.assertEqual(body['voice'], catalog()['voices']['george-natural']['blandId'])
        self.assertEqual(body['pronunciation_guide'][0]['pronunciation'], 'zero zero four two')

    def test_local_only_voice_requires_a_bland_id(self):
        with self.assertRaisesRegex(ValueError, 'needs its Bland voice ID'):
            resolve_call_voice('majestic-george')

    def test_named_provider_voice_override_still_works(self):
        self.assertEqual(resolve_call_voice('ryan'), 'ryan')


if __name__ == '__main__':
    unittest.main()
