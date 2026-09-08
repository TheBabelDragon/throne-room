# E-ink observer

Duck Gate owns truth. This package renders the last committed GateEvent.

It does not:

- validate proposals
- clamp or budget
- bind UDP :4210
- write FieldTick

ACK is a physical witness (`display_ack`), not an approval.
