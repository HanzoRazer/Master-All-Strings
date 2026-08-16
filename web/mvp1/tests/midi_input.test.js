import test from "node:test";
import assert from "node:assert/strict";
import { MidiInputState, WebMidiInput } from "../midi_input.js";
test("permission states are explicit", async () => {
  assert.equal(
    new WebMidiInput({ navigatorObject: {} }).state,
    MidiInputState.UNSUPPORTED,
  );
  const denied = new WebMidiInput({
    navigatorObject: {
      requestMIDIAccess: async () => {
        let e = new Error();
        e.name = "NotAllowedError";
        throw e;
      },
    },
  });
  assert.equal(
    await denied.requestPermission(),
    MidiInputState.PERMISSION_DENIED,
  );
});
test("adapter forwards bytes and device timestamp without interpretation", async () => {
  const input = { id: "d", name: "Device" };
  const access = { inputs: new Map([["d", input]]) };
  const midi = new WebMidiInput({
    navigatorObject: { requestMIDIAccess: async () => access },
  });
  await midi.requestPermission();
  let captured;
  midi.connect(
    "d",
    (m) => (captured = m),
    () => {},
  );
  input.onmidimessage({ timeStamp: 1.25, data: new Uint8Array([144, 60, 90]) });
  assert.deepEqual(captured, {
    capture_time_ns: 1250000,
    raw_payload: [144, 60, 90],
    device_id: "d",
  });
});

test("explicit fake mode exposes deterministic browser smoke input", async () => {
  const midi = new WebMidiInput({ navigatorObject: {}, fakeMode: true });
  assert.equal(await midi.requestPermission(), MidiInputState.READY);
  let count = 0;
  midi.connect(
    "deterministic-fake-midi",
    () => count++,
    () => {},
  );
  midi.emitFakeScale();
  assert.equal(count, 6);
});
