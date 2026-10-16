"""Classify WBGT using HABOOB's five operational flags."""


def wbgt_flag(wbgt_c):
    """Return a color flag; compare at one-decimal operational precision."""
    if wbgt_c is None:
        return None
    value = round(float(wbgt_c), 1)
    if value <= 26.6:
        return "white"
    if value <= 29.3:
        return "green"
    if value <= 31.0:
        return "yellow"
    if value <= 32.1:
        return "red"
    return "black"
