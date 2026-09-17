"""
Gates on what the build itself produced.

These read the board and the bill of materials rather than the design source,
so they check what was actually generated. A part can be described perfectly
and still reach the board wrong.
"""


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
