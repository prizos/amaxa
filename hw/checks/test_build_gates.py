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


def test_no_unconnected_pads(footprints):
    """
    Every pad on every placed part belongs to a net.

    A pad with no net is a part whose connection was never drawn. It is not a
    DRC violation — DRC sees an unconnected pad as intentional — so it has to
    be caught here.
    """
    floating = [
        (fp["designator"], pad)
        for fp in footprints
        for pad, net in fp["pads"].items()
        if not net
    ]
    assert not floating, "Pads with no net:\n" + "\n".join(
        f"  {ref} pad {pad}" for ref, pad in floating
    )
