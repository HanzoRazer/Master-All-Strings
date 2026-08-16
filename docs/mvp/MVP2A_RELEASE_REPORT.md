# MVP-2A Release Report

## Outcome

MVP-2A implements the synchronized **hear + see + slow + loop** practice experience on
branch `feat/mvp-2a-practice-audio`. The branch descends from merged MVP-1F commit
`9ab975632225ee8cb0c26eba501869ea73615c2c`.

## Automated gates

- Python: `1487 passed, 1 skipped`
- Coverage: `95.48%` (repository floor: `95%`)
- JavaScript transport/audio tests: `26 passed`
- Ruff: pass
- strict mypy: pass
- Playback and practice JSON Schema tests: pass
- Checked-in demo fixture drift tests: pass
- All ten demos pin playback digests and declare `audio_demo: true`

## Interactive browser walkthrough

Environment: Windows, Codex in-app Chromium browser (exact browser build not exposed).

Observed:

- Reference Synth reached `ready` after an explicit Sound on gesture.
- Visual active-note state advanced from the same transport used by audio scheduling.
- Seek and `0.50×`, `0.75×`, `1.00×`, `1.50×` controls operated.
- A `0.00s–0.60s` loop completed more than three repetitions with one shared wrap.
- Pause changed tracked voices from `2` to `0`.
- Lesson switch retained `0` tracked voices from the prior lesson.
- Unplayable F#1 remained in the gutter while its canonical playback event stayed present.
- Teacher Override rendered the override position while its canonical E4 playback remained
  spatially independent.
- Natural completion showed `Complete` and left `0` tracked voices.
- Captured scheduler mapping error: `0.000000 ms` for the sampled event.

The mapping error measures deterministic transport-to-AudioContext timestamp mapping. It
does not claim speaker latency, display scan-out latency, or human-perceived drift.
Scheduling variance was not measured by this environment and is not fabricated.

Screenshots:

- [Ready practice state](evidence/mvp2a-practice-ready.png)
- [Loop running](evidence/mvp2a-loop-running.png)
- [Unplayable event](evidence/mvp2a-unplayable-audible.png)
- [Teacher override](evidence/mvp2a-teacher-override.png)

## Offline and audio-capture status

The app loaded entirely from localhost and source inspection confirms no remote runtime
asset, soundbank, CDN, or third-party synth dependency. The agent did not disable the
user's network adapter, so the exact disconnected-machine replay remains part of the
human procedure.

`UNVERIFIED_AUDIO_OUTPUT`: WebAudio reached `running`, oscillators were scheduled, active
voices were observed, and panic was verified. The environment could neither listen to
host speakers nor record a walkthrough with audio, so audible speaker output is not
reported as an automated PASS. Follow the acoustic procedure in
[MVP2A_RELEASE_GATE.md](MVP2A_RELEASE_GATE.md) before external review.

## Deferred

Count-in policy is preserved; audible count-in is deferred. No empty rollout commit was
created for it.
