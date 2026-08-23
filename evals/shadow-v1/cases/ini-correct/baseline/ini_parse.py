def parse_ini(text: str) -> dict:
    """Parse a flat INI document into a nested dict.

    Sections ([name]) become top-level keys. Keys inside a section become
    entries of that section's dict. Dotted keys (a.b) nest one level deeper.
    Values keep their raw string form. Text before any section lands under
    the "" (empty string) key.
    """
    raise NotImplementedError
