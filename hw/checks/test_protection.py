"""
Input protection, on any board that has it.

One check lives here, and it is the one that caught a defect no hand-written
table could: a reverse-polarity FET fitted backwards. Its expected value is
derived from the netlist, so it holds on a board it was not written for.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


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



# A gate clamp is a Zener across a MOSFET's gate and source. Which way round it
# goes depends on the channel, and the channel is in the symbol library: the
# generic symbols spell it into their names, a part-numbered one like 2N7002
# spells its pins G, S and D and puts "N-Channel MOSFET" in its Description.
_NMOS = "Transistor_FET:Q_NMOS_"


def _fet(symbol: str) -> tuple[dict[str, str], str] | None:
    """(terminal letter -> pad, channel letter) for a MOSFET, else None."""
    from symbols import symbol_description, symbol_pin_names

    if symbol.startswith(_PMOS):
        return _terminals(symbol), "P"
    if symbol.startswith(_NMOS):
        return _terminals(symbol), "N"
    names = symbol_pin_names(symbol)
    # Not `<`. A proper-subset test passes a symbol with *extra* pins and
    # fails one with exactly these three, which is the opposite of the
    # question - "are these the three terminals" - and only the Description
    # filter below was saving it.
    if set(names.values()) != {"G", "S", "D"}:
        return None
    described = symbol_description(symbol).upper()
    if "N-CHANNEL" in described or "N-MOSFET" in described:
        channel = "N"
    elif "P-CHANNEL" in described or "P-MOSFET" in described:
        channel = "P"
    else:
        return None
    return {name: pad for pad, name in names.items()}, channel


def test_every_gate_clamp_faces_the_way_its_fet_needs(design, net_of_pad):
    """
    A Zener across a gate and a source has its cathode on the positive end.

    The clamp exists to keep V_GS inside the FET's rating while the gate is
    dragged about by the input. Fitted the other way round it is a forward
    diode from gate to source: it conducts at 0.7 V, the FET can no longer be
    held in the state it is meant to be in, and the part that was there to
    protect the gate is what shorts it.

    Which end is positive depends on the channel. An N-channel FET is turned on
    by a gate above its source, so the cathode goes to the **gate**; a P-channel
    one by a gate below its source, so the cathode goes to the **source**. Both
    come out of the symbol library - the channel from the symbol's name or its
    Description, the cathode from the Zener's own pin names - so no pad number
    is written down anywhere here.

    This is the second half of the check above, and for the same reason. led12
    carried a hand-written table of expected pins for months with the row for
    its reverse-polarity FET backwards in it, under a comment asserting it was
    right. These are the rows that table no longer needs.
    """
    from symbols import symbol_pin_names

    zeners = {
        address for address, part in design["parts"].items()
        if part["symbol"] == "Device:D_Zener"
    }
    fets = {
        address: found
        for address, part in design["parts"].items()
        for found in [_fet(part["symbol"])] if found
    }
    if not zeners or not fets:
        pytest.skip("no MOSFET and Zener pair on this board")

    names = {name: pad for pad, name in symbol_pin_names("Device:D_Zener").items()}
    checked, wrong = 0, []
    for zener in sorted(zeners):
        cathode = net_of_pad.get((zener, names["K"]))
        anode = net_of_pad.get((zener, names["A"]))
        for fet, (pads, channel) in sorted(fets.items()):
            gate = net_of_pad.get((fet, pads["G"]))
            source = net_of_pad.get((fet, pads["S"]))
            if {cathode, anode} != {gate, source}:
                continue
            checked += 1
            positive = gate if channel == "N" else source
            if cathode != positive:
                wrong.append(
                    f"  {zener} across {fet}, a {channel}-channel part: its "
                    f"cathode is on {cathode!r} and the positive end of that "
                    f"gate-source pair is {positive!r}, so it is a forward "
                    f"diode and not a clamp"
                )
    assert checked, "no Zener found across a gate and a source, and this is about them"
    assert not wrong, "Gate clamps fitted backwards:\n" + "\n".join(wrong)
