# MVP-2A Practice Loop

`PracticeSessionPolicyV1` preserves lesson intent using canonical tick positions:

- `enabled`
- `start_tick`
- `end_tick`
- optional `target_repetitions`
- `count_in_bars` (`0`, `1`, or `2`)

Persisted bounds must satisfy `0 <= start < end <= lesson_end`. Invalid bounds fail;
they are never silently clamped. Python converts valid bounds through Musical Core and
exports derived runtime seconds. The browser does not convert ticks or tempo.

The shared transport wraps both visual and audio consumers at the same boundary,
increments the repetition counter once per crossing, and reanchors each cycle instead of
accumulating frame deltas. Optional target repetitions stop at the loop end.

Count-in policy is preserved; audible count-in is deferred. Count-in does not alter
canonical event timestamps and will be implemented as transport pre-roll with a separate
click generator in a follow-on change.
