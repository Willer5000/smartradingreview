"""Run unchanged strict Structure behavioral tests on 17.5.11.

The original 17.5.3 whole-repository hash test targets 17.5.2, so it is excluded.
17.5.11 base/delivery hashes are recorded separately in the release manifest.
"""
import unittest
import qa_commit17_5_3_structure_signal_path as original

suite=unittest.TestSuite(original.StructureRuntimeQA(name) for name in
    unittest.defaultTestLoader.getTestCaseNames(original.StructureRuntimeQA)
    if not name.startswith('test_01_'))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
