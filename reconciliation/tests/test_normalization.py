from django.test import SimpleTestCase

from reconciliation.services import (
    name_found,
    normalize_description,
    normalize_name,
    normalize_reference,
)


class NormalizationTests(SimpleTestCase):
    def test_reference_keeps_only_letters_and_digits(self):
        for raw in ['cc-1003', 'CC-1003', 'cc 1003', 'cc.1003']:
            self.assertEqual(normalize_reference(raw), 'CC1003')

    def test_entity_suffix_is_dropped_but_trust_is_not(self):
        self.assertEqual(normalize_name('Haller Capital LLC'), 'HALLER CAPITAL')
        self.assertEqual(normalize_name('Cedar Grove Fund LP'), 'CEDAR GROVE FUND')
        self.assertEqual(normalize_name('Blackrock Inc'), 'BLACKROCK')
        self.assertEqual(normalize_name('Patel Family Trust'), 'PATEL FAMILY TRUST')

    def test_name_must_match_whole_words(self):
        self.assertTrue(name_found('Patel Family Trust', 'WIRE IN PATEL FAMILY TRUST'))
        self.assertFalse(name_found('Haller Capital', 'WIRE IN HALLER CAPITALIZATION'))

    def test_name_matches_across_repeated_spaces(self):
        self.assertTrue(name_found('Haller Capital', 'WIRE IN HALLER  CAPITAL  LLC'))

    def test_description_collapses_punctuation_to_single_spaces(self):
        self.assertEqual(
            normalize_description('  wire, incoming: acme fund  '),
            'WIRE INCOMING ACME FUND',
        )