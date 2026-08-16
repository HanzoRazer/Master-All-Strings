# DO-009 release gate

Run the complete Python suite with coverage, Ruff over `src tests scripts`, strict mypy over
`src`, and Node tests under `web/mvp1/tests`. Rebuild the checked-in return artifact with
`scripts/build_do009_evidence.py` and confirm a clean semantic digest.

Browser smoke uses `?fakeMidi=1`: Enable MIDI, Arm, Start Attempt, Inject Fake Scale, and Stop
Attempt. Confirm six raw messages become three Python-paired observed notes and the neutral overlay
contains no assessment language. Exercise seek, 1.50x rate, and at least three loop repetitions.

Physical verification requires a Web MIDI device: repeat the workflow, deliberately omit, add, and
alter pitches, then disconnect during capture and confirm interrupted evidence survives. Until this
is performed, status is `UNVERIFIED_PHYSICAL_MIDI_INPUT`.
