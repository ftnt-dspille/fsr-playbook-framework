"""Effect-verification probes -- does the affordance actually WRITE?

Every probe here names a terminal effect and reads box ground truth before AND
after driving the widget's exact payload through the deployed connector. A
rendered card, a green badge and `ok: True` are all satisfiable while nothing
is written -- that is the failure class this package exists to detect, and it
has already shipped twice (a step rename that could never apply, and the fix
for it that was a silent no-op past passing unit tests).

Plan: `fsr_all_widgets/docs/plans/effect-verification-probes.md`.
"""
