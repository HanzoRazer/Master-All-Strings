# DO-009 browser MIDI runbook

1. Start the local MVP server and open a lesson in a Web MIDI-capable browser.
2. Select **Enable MIDI**, grant permission, select an input, then **Arm**.
3. Select **Start Attempt**; transport restarts and capture/playback begin together.
4. Play notes, then select **Stop Attempt** and inspect the neutral observed overlay.
5. Repeat after seek and rate changes, then run a three-repetition loop.
6. Disconnect the device during an attempt and confirm `interrupted` evidence survives.

When no device is present, record `UNVERIFIED_PHYSICAL_MIDI_INPUT`; never substitute simulation
for the physical hardware result.
