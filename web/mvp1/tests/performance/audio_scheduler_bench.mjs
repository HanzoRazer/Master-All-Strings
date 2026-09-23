/**
 * M1 — what `AudioScheduler.tick()` costs, and how it scales.
 *
 * The claim under test: the tick loops over every event in the plan, so at a
 * 25 ms interval it performs up to forty full-plan scans per second, and the
 * `scheduled` set stops duplicate scheduling without stopping the iteration.
 *
 * Five positions, because the cost is not one number. A tick early in a plan
 * skips almost everything on a `release_seconds <= position` test; a tick near
 * the end skips almost everything on the other branch; a tick where most
 * events are already scheduled is the steady state during playback, and is the
 * one the review is really about.
 *
 * Pure JavaScript. No DOM, no audio context -- the synth is a counter. What
 * this measures is the scan itself, which is exactly the thing in question.
 *
 * Emits JSON on stdout. Changes nothing.
 */

import { AudioScheduler } from "../../audio_scheduler.js";
import { Transport } from "../../transport.js";
import { WORKLOAD_SIZES, benchmark, buildBenchmarkPlan, summarize } from "./benchmark-fixtures.js";

const TICK_INTERVAL_MS = 25;

function scheduler(plan) {
  let nowMs = 0;
  const transport = new Transport({ now: () => nowMs });
  transport.setDuration(plan.total_seconds);
  const synth = {
    context: { currentTime: 0 },
    readiness: "ready",
    scheduled: 0,
    scheduleNote() {
      this.scheduled += 1;
    },
    panic() {},
  };
  const instance = new AudioScheduler({
    transport,
    synth,
    lookaheadSeconds: 0.2,
    onDiagnostic: () => {},
  });
  instance.loadPlan(plan);
  return { instance, transport, synth, advance: (ms) => (nowMs += ms) };
}

/** Put the transport at a fraction of the plan and let the scheduler catch up. */
function positioned(plan, fraction, { prescheduled = false } = {}) {
  const harness = scheduler(plan);
  const seconds = plan.total_seconds * fraction;
  harness.transport.seek(seconds);
  harness.transport.play();
  if (prescheduled) {
    // The steady state: most of the window has already been scheduled, so
    // every event the loop touches fails the `scheduled.has()` test.
    harness.instance.tick();
  }
  return harness;
}

const SCENARIOS = [
  { name: "start", fraction: 0 },
  { name: "middle", fraction: 0.5 },
  { name: "near_end", fraction: 0.95 },
  { name: "mostly_scheduled", fraction: 0.5, prescheduled: true },
  { name: "after_seek", fraction: 0.25, reseek: true },
];

function measure(eventCount) {
  const plan = buildBenchmarkPlan({ eventCount });
  const results = {};
  for (const scenario of SCENARIOS) {
    const harness = positioned(plan, scenario.fraction, {
      prescheduled: scenario.prescheduled,
    });
    const samples = benchmark(
      () => {
        if (scenario.reseek) {
          // A seek clears what was scheduled, so the next tick is the
          // expensive one: nothing can be skipped as already done.
          harness.instance.reset?.();
          harness.transport.seek(plan.total_seconds * scenario.fraction);
        }
        harness.advance(TICK_INTERVAL_MS);
        harness.instance.tick();
      },
      { iterations: eventCount >= 10000 ? 30 : 50, warmup: 10 },
    );
    const summary = summarize(samples);
    results[scenario.name] = {
      ...summary,
      // What a tick costs, multiplied by how often the scheduler runs one.
      estimated_ms_per_second: summary.median_ms * (1000 / TICK_INTERVAL_MS),
      plan_events: eventCount,
    };
  }
  return results;
}

const measurements = {};
for (const size of WORKLOAD_SIZES) {
  measurements[String(size)] = measure(size);
}

process.stdout.write(
  JSON.stringify(
    {
      benchmark: "audio_scheduler_tick",
      risk: "M1",
      tick_interval_ms: TICK_INTERVAL_MS,
      measures: "pure JavaScript scan cost; no DOM, no audio context",
      scenarios: SCENARIOS.map((scenario) => scenario.name),
      measurements,
    },
    null,
    2,
  ),
);
