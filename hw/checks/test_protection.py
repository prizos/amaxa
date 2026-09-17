"""
Input protection, on any board that has it.

One check lives here, and it is the one that caught a defect no hand-written
table could: a reverse-polarity FET fitted backwards. Its expected value is
derived from the netlist, so it holds on a board it was not written for.
"""

import pytest


# KiCad names a discrete MOSFET's symbol after its pin order, so the letters in
# the symbol name say which pad is which. That is the only place the pin order
# is recorded in a form a check can read, and it is the thing that differs
# between the two P-FETs this project has used: a SOT-23 part numbered G, S, D
# and a SOT-223 one numbered G, D, S.
_PMOS = "Transistor_FET:Q_PMOS_"


def _terminals(symbol: str) -> dict[str, str]:
    """Terminal letter -> pad number, from the symbol's name."""
    order = symbol[len(_PMOS):]
    return {letter: str(index) for index, letter in enumerate(order, start=1)}


@pytest.fixture(scope="module")
def net_of_pad(design):
    return {
        (address, pad): net
        for net, nodes in design["nets"].items()
        for address, pad in nodes
    }


def test_reverse_polarity_fets_face_the_supply(design, net_of_pad):
    """
    A reverse-polarity FET's drain is on the supply side, not the load side.

    A P-channel MOSFET's body diode has its anode on the drain. Put the drain
    on the supply and that diode is reverse-biased when the input goes
    negative, so the FET blocks. Put the source there instead - which reads
    more naturally, and is how a high-side load switch is drawn - and the part
    still switches perfectly on the bench while the body diode conducts under
    reverse polarity. On led12 that was a two-diode path from ground to the
    reversed input, simulated at 69 A and limited only by the fuse.

    led12 shipped for months with a hand-written table naming the backwards
    orientation as the expected one, with a comment asserting it was right. A
    table of what you believe cannot catch a belief that is wrong. So this asks
    the netlist instead: whatever net a fuse feeds is the supply side by
    definition, and that is the net the drain must be on.

    Which pad is the drain comes from the symbol's own name, so this holds for
    a part with any pin order.
    """
    fets = {
        address: part["symbol"]
        for address, part in design["parts"].items()
        if part["symbol"].startswith(_PMOS)
    }
    fuse_nets = {
        net_of_pad[(address, pad)]
        for address, part in design["parts"].items()
        if part["symbol"] == "Device:Fuse"
        for pad in ("1", "2")
        if (address, pad) in net_of_pad
    }

    wrong = []
    for address, symbol in sorted(fets.items()):
        pads = _terminals(symbol)
        drain = net_of_pad.get((address, pads["D"]))
        source = net_of_pad.get((address, pads["S"]))
        if drain not in fuse_nets and source not in fuse_nets:
            continue  # not in series with a fuse: not the protection FET
        if drain not in fuse_nets:
            wrong.append(
                f"  {address}: the drain is on {drain!r} and the source on "
                f"{source!r}, but the fuse feeds {source!r}. The body diode's "
                "anode is the drain, so this conducts when the input is "
                "reversed and the board is not protected at all."
            )
        elif source in fuse_nets:
            wrong.append(
                f"  {address}: drain and source are both on a net the fuse "
                "touches, so the FET is shorted out."
            )
    assert not wrong, "Reverse-polarity protection wired the wrong way:\n" + "\n".join(wrong)
