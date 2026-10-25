import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("pr_signatures", Path(__file__).resolve().parents[1] / "scripts/pr_signatures.py")
ps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps)
HEAD = "a" * 40
OLD = "b" * 40


def commit(sha=HEAD, verified=True, reason="valid"):
    return {"sha": sha, "commit": {"verification": {"verified": verified, "reason": reason}}}


class Signatures(unittest.TestCase):
    def snapshot(self, count=1, sha=HEAD):
        return {"head": {"sha": sha}, "commits": count}

    def test_signed_subject_passes(self):
        p = self.snapshot()
        self.assertEqual(ps.assess(p, [commit()], p, HEAD)["outcome"], "pass")

    def test_signed_head_does_not_hide_unsigned_parent(self):
        p = self.snapshot(2)
        result = ps.assess(p, [commit(OLD, False, "unsigned"), commit()], p, HEAD)
        self.assertEqual(result["outcome"], "violation")
        self.assertIn("sign-off cannot sign", result["diagnostics"][0])

    def test_wrong_head_is_indeterminate(self):
        p = self.snapshot()
        self.assertEqual(ps.assess(p, [commit()], self.snapshot(sha=OLD), HEAD)["outcome"], "indeterminate")

    def test_missing_commit_page_is_not_pass(self):
        p = self.snapshot(2)
        self.assertEqual(ps.assess(p, [commit()], p, HEAD)["outcome"], "indeterminate")

    def test_missing_verification_is_not_pass(self):
        p = self.snapshot()
        self.assertEqual(ps.assess(p, [{"sha": HEAD}], p, HEAD)["outcome"], "indeterminate")

    def test_inconsistent_verified_flag_is_not_pass(self):
        p = self.snapshot()
        self.assertEqual(ps.assess(p, [commit(reason="unsigned")], p, HEAD)["outcome"], "indeterminate")

    def test_duplicate_or_malformed_ids_are_not_pass(self):
        p = self.snapshot(2)
        self.assertEqual(ps.assess(p, [commit(), commit()], p, HEAD)["outcome"], "indeterminate")
        p = self.snapshot()
        self.assertEqual(ps.assess(p, [commit("x" * 40)], p, HEAD)["outcome"], "indeterminate")

    def test_actual_enumeration_ends_at_requested_head(self):
        p = self.snapshot()
        self.assertEqual(ps.assess(p, [commit(OLD)], p, HEAD)["outcome"], "indeterminate")

    def test_pagination_reads_every_commit(self):
        ids = [format(i, "040x") for i in range(100)] + [HEAD]
        pages = [[commit(s) for s in ids[:100]], [commit()]]
        requests = []
        def request(path, token):
            requests.append(path)
            return pages.pop(0) if "/commits?" in path else self.snapshot(101)
        result = ps.collect("dlworrell/example", 1, HEAD, request=request)
        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(len(requests), 4)

    def test_endpoint_truncation_is_detected(self):
        def request(path, token):
            return [commit()] if "/commits?" in path else self.snapshot(500)
        self.assertEqual(ps.collect("dlworrell/example", 1, HEAD, request=request)["outcome"], "indeterminate")

    def test_unverified_head_fails(self):
        p = self.snapshot()
        self.assertEqual(ps.assess(p, [commit(verified=False, reason="bad_email")], p, HEAD)["outcome"], "violation")

    def test_invalid_repository_refused_before_request(self):
        with self.assertRaises(ps.PreflightError):
            ps.collect("other.example/../../", 1, HEAD)

    def test_malformed_nested_api_data_is_indeterminate(self):
        p = self.snapshot()
        self.assertEqual(ps.assess({"head": None}, [commit()], p, HEAD)["outcome"], "indeterminate")
        self.assertEqual(ps.assess(p, [{"sha": HEAD, "commit": None}], p, HEAD)["outcome"], "indeterminate")


if __name__ == "__main__":
    unittest.main()
