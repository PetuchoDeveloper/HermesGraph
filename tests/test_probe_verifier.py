from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "probe_verifier.py"
SPEC = importlib.util.spec_from_file_location("probe_verifier", MODULE_PATH)
assert SPEC and SPEC.loader
probe_verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_verifier)


class CloudflareProbeTests(unittest.TestCase):
    def test_cloudflare_disables_reasoning_for_single_token_verdict(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "CLOUDFLARE_ACCOUNT_ID": "account-id",
                    "CLOUDFLARE_API_TOKEN": "api-token",
                },
                clear=True,
            ),
            patch.object(probe_verifier, "post_json", return_value={}) as post_json,
        ):
            probe_verifier.cloudflare()

        payload = post_json.call_args.args[2]
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})


class ProbeValidationTests(unittest.TestCase):
    @staticmethod
    def response(content: object = "PASS", logprobs=None):
        if logprobs is None:
            logprobs = {"content": [{"token": content, "logprob": -0.1}]}
        return {
            "choices": [
                {
                    "message": {"content": content},
                    "logprobs": logprobs,
                }
            ]
        }

    def test_accepts_exact_verdict_with_output_logprob_position(self):
        self.assertTrue(probe_verifier.validate_response(self.response()))

    def test_accepts_fail_as_an_exact_verdict(self):
        self.assertTrue(probe_verifier.validate_response(self.response("FAIL")))

    def test_rejects_invalid_verdict(self):
        self.assertFalse(probe_verifier.validate_response(self.response("PASS ")))

    def test_rejects_non_string_verdict(self):
        self.assertFalse(probe_verifier.validate_response(self.response(["PASS"])))

    def test_rejects_missing_choices(self):
        self.assertFalse(probe_verifier.validate_response({}))

    def test_rejects_nonempty_logprobs_without_content_positions(self):
        response = self.response(logprobs={"top_logprobs": []})
        self.assertFalse(probe_verifier.validate_response(response))

    def test_rejects_empty_logprobs_content(self):
        response = self.response(logprobs={"content": []})
        self.assertFalse(probe_verifier.validate_response(response))

    def test_rejects_absent_logprobs(self):
        response = self.response()
        del response["choices"][0]["logprobs"]
        self.assertFalse(probe_verifier.validate_response(response))

    def test_main_returns_zero_for_usable_response(self):
        with (
            patch.object(probe_verifier, "cloudflare", return_value=self.response()),
            patch.object(sys, "argv", ["probe_verifier.py", "--provider", "cloudflare"]),
        ):
            self.assertEqual(probe_verifier.main(), 0)

    def test_main_returns_one_for_unusable_response(self):
        with (
            patch.object(probe_verifier, "cloudflare", return_value=self.response("MAYBE")),
            patch.object(sys, "argv", ["probe_verifier.py", "--provider", "cloudflare"]),
        ):
            self.assertEqual(probe_verifier.main(), 1)


if __name__ == "__main__":
    unittest.main()
