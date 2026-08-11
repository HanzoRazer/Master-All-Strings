# MVP-2A Audio Architecture

MVP-2A adds an offline browser Reference Synth without changing musical authority.

```text
LessonAssignmentV1
  -> canonical MusicalEvent values + Core tempo map
     -> FretboardScrollProjectionV1 -> renderer
     -> LessonPlaybackPlanV1        -> AudioScheduler -> ReferenceSynth
                                  \-> shared Transport <-/
```

The projection and playback plan are siblings. Audio never consumes string, fret,
candidate, or teacher-override data. Both outputs carry the same `assignment_id` and
`content_id`; `MvpPracticeBundleV1` rejects identity, pitch, or onset disagreement.

## Timing and transport

Musical Core performs every tick-to-seconds conversion. The browser receives event and
loop positions in seconds and contains no tempo conversion. `Transport` is the sole
position, rate, loop, and repetition authority. It is anchored to wall time rather than
accumulating animation-frame deltas. AudioContext time is used only to map that shared
position onto accurate scheduling timestamps.

Pause, restart, seek, rate change, loop wrap, lesson change, tab hiding, completion, and
explicit stop all reach the scheduler panic path. `VoiceRegistry` tracks scheduled and
active oscillators so stale voices can be terminated.

## Reference Synth

The browser adapter uses native Web Audio oscillators, a velocity-sensitive envelope,
master gain, optional cents offset, and a 16-voice registry. Rate changes reschedule note
events and never alter oscillator pitch. The timbre is intentionally labeled
**Reference Synth**; sound-quality optimization is outside this tranche.

No soundfont, CDN, Ardour, Pi service, live input, or network dependency is present.
