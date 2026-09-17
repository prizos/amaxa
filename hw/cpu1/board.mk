# Everything placed so far is routed, so DRC is held to the strict gate: any
# connection left undrawn fails, as on a finished board. Adding a block that
# cannot be routed in the same change means setting this back to `incomplete`,
# deliberately and visibly.
ROUTING := complete
SIM     := none
