"""Blood compatibility. Derived from antigens, not a hand-typed table."""
GROUPS = ["O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"]
SHELF_LIFE_DAYS = {"RBC": 42, "PLT": 5}   # red cells ~42d, platelets ~5d

def antigens(group):
    s = set(group[:-1].replace("O", ""))   # 'AB' -> {A,B}, 'O' -> {}
    if group.endswith("+"):
        s.add("D")
    return s

def can_donate(donor, recipient):
    """RBC rule: donor carries no antigen the recipient lacks."""
    return antigens(donor) <= antigens(recipient)

def reach(group):
    """How many groups this donor can serve. High = precious (O- serves all 8)."""
    return sum(can_donate(group, r) for r in GROUPS)

def donors_for(recipient, component="RBC"):
    """Compatible donor groups, best first: exact match, then least-versatile first
    so universal donors (O-) are kept for those who truly need them."""
    if component == "PLT":   # platelets: ABO-identical preferred
        ok = [g for g in GROUPS if g[:-1] == recipient[:-1]]
    else:
        ok = [g for g in GROUPS if can_donate(g, recipient)]
    return sorted(ok, key=lambda g: (g != recipient, reach(g), g))

def recipients_for(donor):
    return [g for g in GROUPS if can_donate(donor, g)]
