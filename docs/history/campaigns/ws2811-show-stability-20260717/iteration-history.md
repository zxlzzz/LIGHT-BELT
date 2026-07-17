# Iteration History

## 1. Historical timing and interface experiments

Early FastLED, SPI6, SPI4, repeated-frame, moving-point, and multi-node runs
showed intermittent wrong colors, brightness jumps, black-group violations,
and first-group divergence. Runs made before the real SN74 B-side supply was
confirmed at 5 V remain historical but electrically confounded.

The supplied WS2811 V2.1 timing table rejects the old SPI6 200 ns T0H as a
production candidate. The current source uses the V2.1-compatible guarded SPI4
encoding: 3.2 MHz, `1000/1100`, and 500 us low guards.

## 2. VCCB correction

The operator corrected each SN74LVC1T45 B-side supply to 5 V. Strip 41 became
visibly much more stable. This changed the controlled fixture and superseded
old conclusions that treated the earlier SN74 condition as valid. It did not
prove a complete repair.

## 3. Frozen breath and connector sensitivity

A pre-generated 600-frame pure-blue breath trace proved every Host frame had
ten equal groups, zero red/green, and only blue values 5 through 37. Live and
frozen replay initially produced many whole-strip wrong-color events. Reseating
all three strip wires, with software and payload frozen, reduced the same replay
to three events and then one zero-event run. This is strong evidence of a
physical connection/reference margin without locating one conductor.

## 4. Pull-down and data-wire coupling

One 10 kohm `DI -> GND` pull-down was added at each strip input. Separating the
two `B -> DI` wires prevented Node8 activity from changing strip 41; bringing
the wires close during transmission made strip 41 light again. This directly
demonstrated proximity-dependent coupling. The retained mitigation is short,
separated data wiring with an adjacent ground return for each branch.

## 5. Exact-content dedupe

Unrestricted exact-content dedupe was added at each node. Identical complete
payloads skip physical output, while KEY and SAFE still force writes. This
removed repeated-black T0 activity from an inactive node and stabilized the
inactive phase, but both strips could still jump when both outputs changed.

## 6. Inter-node offset

Node8 first received a 5 ms Immediate physical-write offset, then a 30 ms
offset. Runtime counters expose waits and cancellations. The 30 ms image is the
current Node8 field identity in this freeze. Later visual observation still
found possible strip-41 flashing during a Node2-only breath phase. Therefore
simultaneous Node8 traffic and exact transaction overlap are not necessary for
all failures, and the offset is not a complete repair.

## 7. Current effect surface

The 171-second exploratory sweep exercises all 17 registered effects on both
logical strips at 15 FPS Immediate. Deterministic blue/orange effects precede
random, full-color, and generated-media effects. It can look very good but does
not define a safe palette.

The 32-second authored virtual-path Show creates one 30-group logical path,
`strip_41[0..9] -> strip_42[0..19]`. One comet crosses the node boundary,
changes hue after each wrap, and then traverses the entire path in reverse.
Focused Host tests prove the logical seam and direction. The Node8 30 ms offset
means the physical seam is not a strict timing acceptance test.

## 8. Frozen conclusion

The present direction is worth continuing because it produces useful and often
excellent effects. The residual fault remains real. Evidence favors a marginal
physical signal/connection/regeneration boundary, but it does not yet isolate
the strip IC from the driver, reference, contact, or first receiver. Preserve
this checkpoint before changing firmware, wiring, color policy, or timing.
