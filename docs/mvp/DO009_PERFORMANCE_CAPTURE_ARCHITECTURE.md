# DO-009 performance return architecture

`CapturedMidiEventV1` and `RawPerformanceCaptureV1` remain the immutable observation authority.
Web MIDI forwards bytes, device identity, and browser timestamps to localhost. Python pairs note
lifecycles FIFO, maps explicit transport anchors through Musical Core, aligns structurally, and
exports evidence. No browser code performs pairing, tick conversion, alignment, or assessment.

Clock domains remain named and distinct. No assumed device, browser, USB, or acoustic latency is
subtracted. Observed source string and MSME-selected string remain independent facts.
