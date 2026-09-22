# flight-calendar-ics agent eval

This directory currently wires the evaluated skill source only.

## Candidate source

The candidate is the complete skill directory at Git ref:

`update/flight-calendar-ics`

It is materialized through the common harness skill-source mechanism. The
`SDD-skill` checkout is not switched, merged, reset, or cleaned in order to
load the candidate.

At the time this wiring was added, GitHub reported the candidate branch head as:

`70c2574ca5f8b6735892fcafe05ae4a93d382b7c`

That SHA is reference evidence for this change, not a hard-coded source pin.
Each actual eval run must record the ref's resolved commit and content digest.

## Current scope

This step does not claim that the flight-calendar-ics agent eval is ready to
run. Scenarios, recorded fixtures, deterministic Outcome/Trajectory/Privacy
rules, and the flight-calendar consumer remain separate follow-up work.

The purpose of this step is to make the external candidate available without
merging `update/flight-calendar-ics` into `SDD-skill`.
