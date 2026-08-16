# MVP-2A Known Limitations

- The Reference Synth is a proof timbre, not a finished guitar or piano sound.
- Count-in policy is preserved, but audible count-in is deferred.
- There are no samples, backing tracks, effects, recording, or overdubbing.
- There is no microphone, live guitar, Web MIDI, assessment, or pitch detection.
- Chord-aware fingering remains unsupported; simultaneous canonical pitches still sound.
- Browser audio requires a user gesture and depends on the host audio device and mixer.
- The automated environment verified a running AudioContext, scheduled voices, and panic,
  but could not capture or independently hear host speaker output. That release item is
  recorded as `UNVERIFIED_AUDIO_OUTPUT` with a human procedure in the release report.
- Audible walkthrough recording was unavailable in the browser-control environment.
