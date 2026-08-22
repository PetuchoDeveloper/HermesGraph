from __future__ import annotations

import importlib.util
import os
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
