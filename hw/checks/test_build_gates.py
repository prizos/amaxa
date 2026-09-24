"""
Gates on what the build itself produced.

These read the board and the bill of materials rather than the design source,
so they check what was actually generated. A part can be described perfectly
and still reach the board wrong.
"""

import pytest


def test_one_value_per_part_number(footprints):
    """
    A supplier part number means exactly one part, with one value.

    Explicit parts make it easy to reuse a part number for a different value:
    the footprint fits, the build passes, and the board arrives with four wrong
    resistors on it. Checked against the board rather than the BOM, because the
    BOM merges rows that share a part number and so hides the clash.
    """
    by_code: dict[str, dict[str, list[str]]] = {}
    for fp in footprints:
        code = fp["properties"].get("LCSC")
        if not code:
            continue  # deliberately not purchased; covered by its own check
        identity = (
            f"{fp['properties'].get('Partnumber', '?')} "
            f"= {fp['properties'].get('Value', '?')}"
        )
        by_code.setdefault(code, {}).setdefault(identity, []).append(fp["designator"])

    clashes = {code: v for code, v in by_code.items() if len(v) > 1}
    assert not clashes, "Supplier part numbers used for more than one part:\n" + "\n".join(
        f"  {code}:\n"
        + "\n".join(f"      {ident}  ({', '.join(sorted(refs))})" for ident, refs in v.items())
        for code, v in clashes.items()
    )


def test_every_bom_line_is_orderable(bom):
    """
    Every line on the BOM can actually be bought.

    A part with no supplier code is one nobody can order. Parts that are
    deliberately not bought — test pads, mounting holes — carry
    `has_part_removed` and never reach the BOM at all.
    """
    missing = [
        row
        for row in bom
        if not row["LCSC Part #"].strip() or not row["Partnumber"].strip()
    ]
    assert not missing, "BOM lines without a supplier or part number:\n" + "\n".join(
        f"  {row['Designator']}: mfr={row['Manufacturer']!r} "
        f"mpn={row['Partnumber']!r} lcsc={row['LCSC Part #']!r}"
        for row in missing
    )


def test_every_placed_part_has_a_designator(footprints):
    """A footprint with no reference cannot be assembled or reviewed."""
    unnamed = [
        fp for fp in footprints if not fp["designator"] or "?" in fp["designator"]
    ]
    assert not unnamed, "Footprints without a designator:\n" + "\n".join(
        f"  {fp['lib_id']} at ({fp['x']}, {fp['y']})" for fp in unnamed
    )


def test_designators_are_unique(footprints):
    """Two parts sharing a designator makes the BOM ambiguous."""
    seen: dict[str, int] = {}
    for fp in footprints:
        seen[fp["designator"]] = seen.get(fp["designator"], 0) + 1
    duplicates = {d: n for d, n in seen.items() if n > 1}
    assert not duplicates, f"Designators used more than once: {duplicates}"


def test_no_unconnected_pads(footprints, design):
    """
    Every pad on every placed part belongs to a net, or is declared unused.

    A pad with no net is a part whose connection was never drawn. It is not a
    DRC violation — DRC sees an unconnected pad as intentional — so it has to
    be caught here. The only exception is a pin the design source marked `NC`,
    which `design.json` records as `no_connect`: unused on purpose, and said so.
    """
    declared = {tuple(node) for node in design.get("no_connect", [])}
    floating = [
        (fp["designator"], pad)
        for fp in footprints
        for pad, net in fp["pads"].items()
        if not net and (fp["properties"].get("address"), pad) not in declared
    ]
    assert not floating, "Pads with no net:\n" + "\n".join(
        f"  {ref} pad {pad}" for ref, pad in floating
    )


def test_every_net_has_a_track_width_rule(design, board_dir):
    """
    No net falls through to the fab's minimum track width by accident.

    `rules.kicad_dru` names nets explicitly, so a net added later is not in any
    rule and silently gets the fab floor — 0.1 mm — instead of a width someone
    chose. That is how the four LED anode nets ended up unconstrained: they were
    renamed during the port and the rules file was not part of the rename.

    DRC cannot catch this. A rule that matches nothing passes.

    Names may use KiCad's `*` wildcard, which matches the way KiCad does — on
    the whole name. A pattern that is only `*` would cover every net and decide
    nothing, so it is refused.
    """
    import fnmatch
    import re

    rules = (board_dir / "rules.kicad_dru").read_text()
    patterns = set(re.findall(r"A\.NetName == '([^']+)'", rules))
    assert "*" not in patterns, (
        f"{board_dir.name}/rules.kicad_dru has a rule matching every net, which "
        "chooses no width for any of them"
    )
    unruled = sorted(
        net
        for net in design["nets"]
        if not any(fnmatch.fnmatchcase(net, pattern) for pattern in patterns)
    )
    assert not unruled, (
        "Nets with no track-width rule, so they get the fab minimum:\n"
        + "\n".join(f"  {net}" for net in unruled)
        + f"\nAdd them to {board_dir.name}/rules.kicad_dru, in the rule whose "
        "reasoning applies to them."
    )


def test_every_rule_in_the_dru_file_is_one_kicad_will_apply(board_dir):
    """
    Each rule in `rules.kicad_dru` is a well-formed s-expression carrying both a
    condition and a constraint.

    KiCad does not complain about a rule it cannot parse: it reports no error,
    DRC runs, and the rule simply does not exist. A stray parenthesis closing
    `(rule "analog supply")` before its condition cost that net its width rule
    for two milestones, and the check above did not notice because it reads the
    file as text and the condition was still there - just no longer inside
    anything.

    So this reads the file the way KiCad's parser does, and requires that what
    comes out is the rules the file appears to contain.

    **A board-wide floor is the one rule that may have no condition**, and it
    has to be, because that is what makes it board-wide. Every other rule here
    narrows a constraint to the nets it names - a width rule matching every
    net would say nothing, which is what this is for - but a `clearance` with
    no condition is the board's own minimum, above the fabricator's, and cpu1
    had no such rule at all until an adversarial pass counted the places
    sitting between the two figures. There were thirteen, in no check and in
    no rule, because DRC only ever saw PCBWay's floor.

    So the exemption is by constraint and not by name: a rule may drop its
    condition if what it constrains is `clearance`, and nothing else.
    """
    import re

    text = (board_dir / "rules.kicad_dru").read_text()
    stripped = re.sub(r"#[^\n]*", "", text)

    forms, stack = [], []
    for token in re.findall(r"\(|\)|\"[^\"]*\"|[^\s()]+", stripped):
        if token == "(":
            stack.append([])
        elif token == ")":
            assert stack, f"{board_dir.name}/rules.kicad_dru: a ')' with nothing open"
            done = stack.pop()
            (stack[-1] if stack else forms).append(done)
        elif stack:
            stack[-1].append(token)
    assert not stack, (
        f"{board_dir.name}/rules.kicad_dru ends with {len(stack)} form(s) still "
        "open, so KiCad reads the rest of the file as part of one of them"
    )

    written = len(re.findall(r"^\(rule\b", stripped, re.MULTILINE))
    parsed = [form for form in forms if form and form[0] == "rule"]
    assert len(parsed) == written, (
        f"{board_dir.name}/rules.kicad_dru is written as {written} rules but "
        f"parses as {len(parsed)}: one of them closes early, and the parts left "
        "outside it are not applied to anything"
    )
    def constrains(form, what):
        return any(part[0] == "constraint" and len(part) > 1 and part[1] == what
                   for part in form[2:] if isinstance(part, list))

    incomplete = [
        form[1]
        for form in parsed
        if not any(part[0] == "constraint" for part in form[2:] if isinstance(part, list))
        or (not any(part[0] == "condition" for part in form[2:] if isinstance(part, list))
            and not constrains(form, "clearance"))
    ]
    assert not incomplete, (
        "Rules with no condition or no constraint, which apply to everything or "
        "require nothing:\n" + "\n".join(f"  {name}" for name in incomplete)
    )


def test_pending_nets_are_still_pending(design, board_config, board_dir):
    """
    A board still being drawn may leave nets half-connected, and only that.

    Each pending net is exempt from ERC because its other end belongs to a block
    not drawn yet. The exemption is only honest while that is true, so each must
    still have exactly one connection: once the block lands, the waiver has to
    go. And a board that declares itself complete may have none at all, nor
    declare its routing incomplete.
    """
    pending = design.get("pending", {})
    nets = design["nets"]
    board_mk = board_dir / "board.mk"
    routing_incomplete = board_mk.is_file() and "ROUTING := incomplete" in board_mk.read_text()

    if board_config.COMPLETE:
        assert not pending, (
            f"{board_dir.name} declares itself complete but has pending nets: {sorted(pending)}"
        )
        assert not routing_incomplete, (
            f"{board_dir.name} declares itself complete but board.mk still says ROUTING := incomplete"
        )
        return

    outdated = [
        f"  {name}: {len(nets.get(name, []))} connections — {why}"
        for name, why in sorted(pending.items())
        if len(nets.get(name, [])) != 1
    ]
    assert not outdated, (
        "Pending nets that are no longer single-ended. Remove them from the board's "
        "pending list; the block they waited for has landed:\n" + "\n".join(outdated)
    )


def test_a_board_declaring_itself_unfinished_says_what_is_unfinished(
    design, board_config, board_dir
):
    """
    `COMPLETE = False` has to point at something.

    The flag is a claim about the board, and the check above enforces it in
    one direction: a board that says it is complete may have no pending nets
    and no incomplete routing. Nothing enforced the other, so the flag could
    go on saying "still being built" after both of its reasons had gone - and
    on cpu1 it did, under a comment naming pending nets it no longer had and
    a `ROUTING := incomplete` that said complete.

    A stale "not finished yet" is worse than a stale "finished": it is the
    sentence that makes every other unfinished-looking thing forgivable.
    """
    blocking = getattr(board_config, "BLOCKING", {})
    if board_config.COMPLETE:
        assert not blocking, (
            f"{board_dir.name} declares itself complete and still lists "
            f"{sorted(blocking)} as blocking"
        )
        return
    board_mk = board_dir / "board.mk"
    routing = board_mk.is_file() and "ROUTING := incomplete" in board_mk.read_text()
    assert design.get("pending") or routing or blocking, (
        f"{board_dir.name} declares COMPLETE = False and has no pending nets, "
        f"no incomplete routing and nothing in BLOCKING. Either something is "
        f"unfinished and is not saying so, or the flag is out of date"
    )
    for what, why in sorted(blocking.items()):
        assert why.strip(), f"{board_dir.name}: {what!r} blocks the board and gives no reason"


def test_every_deck_carries_the_parts_that_load_the_nets_it_models(design, board_dir):
    """
    A deck's values come from the build. Its topology is typed. This is the
    part of that gap a machine can close.

    `tools/simulate.py` resolves every `@path:end@` out of `design.json`, so a
    deck cannot hold a stale number. Nothing resolves its **netlist**: the
    nodes and the parts between them are written by hand, and a deck can go
    on agreeing with its band while the board it claims to model grows a
    capacitor the deck has never heard of. `DESIGN-REVIEW` has listed that as
    open since the decks were written, with one instance closed by hand - the
    trip bus's twelve Schottky junctions, counted against the six packages
    that make them.

    This is that instance generalised. Wherever a deck names a net - by
    reaching for its measured copper as `@copper.<NET>.capacitance:end@`,
    which is the only way a deck can - every part the netlist puts on that
    net has to appear in the deck, one of two ways:

      - **by name**, as an `@<address>.<parameter>:end@` placeholder, which
        is how a passive gets its value; or
      - **by model**, as a `.subckt` or `.model` from `sim/models/` whose
        name is inside the part's own value or manufacturer part number -
        `lvc1g74` in `74LVC1G74`, `bat54a` in `BAT54A`. That match is made
        from `design.json` and the library, so a part swapped for a different
        one stops matching.

    Two kinds of part are exempt, and the exemption is a symbol library
    rather than a list of addresses: a **connector** and the **MCU** are
    what a deck represents as its excitation - a `PWL` source or a current
    ramp - and requiring them to appear as components would be requiring the
    deck to model the thing it is stimulating.

    **What it found.** `trip_clear.cir.in` modelled `TRIPPED` as its copper
    and a pull-up, and left off the two buffer enables and the gate-kill
    transistor's gate - the three loads on the latch's single output, which
    are the whole subject of the trip budget's `max(buffer_off, turn_on)`
    term and which `trip_chain.cir.in` models correctly. It changed the
    answer by a tenth of a nanosecond in a band three orders wider, which is
    why no band caught it and why a deck is not verified by its bands.
    """
    import json
    import re

    sim = board_dir / "sim"
    decks = sorted(sim.glob("*.cir.in"))
    if not decks:
        pytest.skip(f"{board_dir.name} has no simulation decks")

    models = set()
    for library in sorted((sim / "models").glob("*.lib")):
        models |= {found.group(1).lower() for found in
                   re.finditer(r"(?im)^\s*\.(?:subckt|model)\s+(\S+)",
                               library.read_text())}

    on_net: dict[str, set[str]] = {}
    for net, nodes in design["nets"].items():
        for address, _ in nodes:
            on_net.setdefault(net, set()).add(address)

    def squashed(text) -> str:
        return re.sub(r"[^a-z0-9]", "", (text or "").lower())

    # A deck represents these rather than modelling them.
    EXCITED = ("Connector", "MCU_", "TestPoint")

    missing = []
    for deck in decks:
        text = deck.read_text()
        lower = text.lower()
        # The net-name charset, not "anything up to the next dot": these
        # files document their own placeholder syntax in a comment, and
        # `@copper.<NET>.capacitance:end@` written as an example is not a net.
        nets = set(re.findall(r"@copper\.([A-Za-z0-9_+~{}\-]+)\.capacitance", text))
        named = set(re.findall(r"@([a-z][a-z0-9_.]*)\.[a-z_0-9]+:", text))
        for net in sorted(nets):
            assert net in on_net, (
                f"{deck.name} reads the copper capacitance of {net}, which is "
                f"not a net on this board"
            )
            for address in sorted(on_net[net]):
                if address in named:
                    continue
                part = design["parts"][address]
                if part["symbol"].startswith(EXCITED):
                    continue
                matched = [name for name in models
                           if name in squashed(part["value"])
                           or name in squashed(part["mpn"])]
                if any(re.search(rf"(?m)^\s*\S+\s+.*\b{re.escape(name)}\b", lower)
                       for name in matched):
                    continue
                missing.append(
                    f"  {deck.name} models {net} and not {address} "
                    f"({part['value']}), which the netlist puts on it")

    assert not missing, (
        "Decks whose topology is not the board's:\n" + "\n".join(missing)
        + "\nEvery number in a deck comes from the build; its netlist does "
        "not, so a part added to a modelled net has to be added here too."
    )
