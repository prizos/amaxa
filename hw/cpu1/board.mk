# The MCU core and the power block are routed; the safety chain is placed and
# not yet routed, so DRC runs in the mode that still refuses anything drawn
# wrongly but does not demand what has not been drawn at all.
#
# Routing that block on its own turned into a fight with the escapes of a
# package whose other three sides are full. M8 is where the plan sets aside the
# full route, with the whole board in view, and this goes back to `complete`
# there. Until then `make drc` reports how many connections are outstanding.
ROUTING := incomplete
SIM     := decks
