"""S6-F11: P5-4 read a network outage as a packaging failure and could not tell it from a
TLS-verification failure.

The block used to create the SSL context, call `urlopen`, and only then assert
`verify_mode`/`check_hostname`; any raised `URLError` skipped those assertions and the shell
printed one line for every cause.

The three tests here run the block's own source:
  * the certificate checks (including a readable CA file) come before any network call, so an
    outage cannot skip them;
  * a dead endpoint exits 3 -- "network unreachable" -- with the certificate facts printed;
  * an unreadable CA file exits 2 -- "certificate" -- without a network call.
The last test reads the shell's `case` to check the two verdicts are distinguished, and that the
old single line is gone.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / "scripts" / "check_bundle.sh").read_text()

URL = "https://huggingface.co/api/models/mlx-community/Qwen3-0.6B-4bit"


def _p54_python():
    start = TEXT.index("==> P5-4")
    match = re.search(r"<<'PY'\n(.*?)\nPY\n", TEXT[start:], re.S)
    assert match is not None, "the P5-4 heredoc moved"
    return match.group(1)


def _run_dead_endpoint(code, env=None):
    """The block's source with its one URL pointed at a closed local port."""
    return subprocess.run(
        [sys.executable, "-I", "-B", "-"],
        input=code.replace(URL, "https://127.0.0.1:1/").replace("timeout=60", "timeout=5"),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_the_certificate_properties_are_checked_before_the_network():
    code = _p54_python()
    call = code.index("urllib.request.urlopen(")
    for check in (
        "ssl.get_default_verify_paths()",
        "context.verify_mode != ssl.CERT_REQUIRED",
        "context.check_hostname",
    ):
        assert code.index(check) < call, (
            f"{check!r} is checked after the network call, so an outage skips it and a missing "
            "trust store reads as a failed download"
        )
    assert "os.path.getsize(paths.cafile)" in code, "the CA file is not checked for content"
    assert code.count("context = ssl.create_default_context()") == 1


def test_a_dead_endpoint_prints_the_certificate_facts_and_exits_as_a_network_failure():
    completed = _run_dead_endpoint(_p54_python())
    assert completed.returncode == 3, (completed.returncode, completed.stdout, completed.stderr)
    assert '"verify_mode": "CERT_REQUIRED"' in completed.stdout
    assert '"check_hostname": true' in completed.stdout
    assert "URLError" in completed.stderr


def test_an_unreadable_ca_file_is_a_certificate_failure_before_any_call():
    import os

    env = {**os.environ, "SSL_CERT_FILE": "/nonexistent/cert.pem"}
    completed = _run_dead_endpoint(_p54_python(), env=env)
    assert completed.returncode == 2, (completed.returncode, completed.stdout, completed.stderr)
    assert "certificate:" in completed.stderr
    assert "URLError" not in completed.stderr, "the network was tried before the CA check"


def test_the_shell_tells_a_certificate_failure_from_an_unreachable_network():
    start = TEXT.index("==> P5-4")
    assert "==> P5-6:" in TEXT[start:], "the P5-4 block no longer ends at the writable-copy P5-6"
    block = TEXT[start:TEXT.index("==> P5-6:")]
    assert 'fail P5-4 "the HTTPS GET failed (see above)"' not in block, (
        "one line still covers a dead network and a bad certificate"
    )
    assert "(certificate)" in block
    assert "(network unreachable; rerun)" in block
    assert "2) fail P5-4 \"(certificate)" in block, "exit 2 is not mapped to the certificate verdict"
    assert "3) fail P5-4 \"(network unreachable; rerun)" in block, (
        "exit 3 is not mapped to the network verdict"
    )
