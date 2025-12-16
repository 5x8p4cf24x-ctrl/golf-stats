def course_handicap(hcp_exact: float, slope: int) -> int:
    # MVP simple WHS
    return int(round(hcp_exact * (slope / 113.0)))

def strokes_received_per_hole(ch: int, holes):
    """
    holes: lista Hole con stroke_index
    devuelve dict {hole_number: golpes_recibidos}
    """
    base = ch // 18
    extra = ch % 18

    ordered = sorted(holes, key=lambda h: h.stroke_index)

    received = {h.number: base for h in holes}
    for i in range(extra):
        received[ordered[i].number] += 1

    return received

def stableford_points(net_strokes: int, par: int) -> int:
    diff = net_strokes - par
    if diff >= 2: return 0
    if diff == 1: return 1
    if diff == 0: return 2
    if diff == -1: return 3
    if diff == -2: return 4
    if diff == -3: return 5
    return 6
