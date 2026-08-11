# DO-008 three-repository integration report

## Authority stack

| Repository | Role | Tested commit |
| --- | --- | --- |
| `string_master_v.4.0` | Zone/Tritone semantic authority | `5d7af1d0efcd026c8cdf861c8a0f8467d77ee03e` |
| `sg-agentd` | Semantic propagation and bundle assembly | `ae7a58fff0f0cc136ee22434282899ceb811a5d3` |
| `Master-All-Strings` | Bundle consumption, MSME correlation, and teaching UI | Commit 12 tree; exact post-commit SHA is recorded in the rollout handoff |

The machine-readable evidence is in `DO008_INTEGRATION_EVIDENCE.json`. The checked-in
bundle is a minimal, hash-verified fixture produced through the real String Master and
`sg-agentd` integration, not a MAS reimplementation of Zone/Tritone theory.

## End-to-end result

The proof generated 48 authoritative semantic events, packaged them as a manifest-bound
artifact, loaded them into MAS, correlated all 48 to canonical musical events, and projected
the events through MSME. Adding Zone metadata did not change any event's selected string,
fret, or onset. Both Zone IDs and the `TRITONE_ANCHOR` and `HALF_STEP_CROSSING` teaching
roles reached the browser. The six one-string projections contain explicit playable or
unplayable outcomes; no renderer-side theory or fingering inference was added.

Count-in policy is preserved; audible count-in is deferred.

## Automated verification

- MAS focused DO-008 integration tests: passed.
- MAS Python regression, strict typing, Ruff, and coverage gates: passed at the final commit
  boundary (results recorded in the rollout handoff).
- Browser transport, scheduler, audio, Zone renderer, and one-string tests: 30 passed.
- String Master regression baseline: 762 passed, 27 skipped, with the same single known
  manifest self-listing failure present before DO-008.
- `sg-agentd` regression baseline: 242 passed, 2 skipped, with the same single known stdlib
  `inspect` test failure present before DO-008.

## Interactive browser verification

Passed:

- Zone Colors toggled on and off without changing normal fingering.
- The rendered overlay exposed 15 Zone 1 notes, 21 Zone 2 notes, one tritone anchor, and
  four half-step crossings in the visible DOM.
- One-string view used precomputed positions and displayed explicit impossible states.
- Reference Synth activation reached `Reference Synth ready`.
- Play, Pause, Seek, and 1.50x rate controls shared one transport position.
- A shortened verification loop stopped after exactly three repetitions.
- Switching during playback to the unplayable-note lesson left its impossible event visible.
- Teacher-override lesson loaded with its declared override origin.

Audio status: `UNVERIFIED_AUDIO_OUTPUT`. The browser environment confirmed audio context
activation and scheduler operation but cannot attest to physical speaker output or record an
audio-bearing walkthrough. Human verification: open the DO-008 projection, enable Sound,
press Play, confirm audible notes, change rate without changing pitch, pause and seek, run a
three-repetition loop, and switch lessons while listening for stuck voices.

Screenshots are stored in `docs/mvp/do008_artifacts/`.
