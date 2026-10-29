# Order: re-read docs/runtimes/optiq.md against installed mlx-optiq 0.5.13
Files you may touch: docs/runtimes/optiq.md only, EXCEPT the MTP-gate passages (another worker edits
those now -- do not touch any paragraph about optiq_mtp_refusal or mtp_depth_missing).
The doc was written against 0.5.6 and carries a banner saying only some lines were rechecked. Locate
the installed package (the `optiq` on PATH; `optiq --version` is safe to run -- do NOT run `optiq serve`).
Walk every file:line citation and every capability claim; correct what moved or changed, cite 0.5.13
paths, and mark claims you could not verify. Then replace the banner with an accurate one-paragraph
statement of what was re-verified and when (2026-09-25).
Acceptance: a list in your report of every changed claim (old -> new, with citation). No git, no pytest.
Report DONE or BLOCKED.
