"""M4a: confidence arithmetic verified by hand (DESIGN §5 rows 1, 9)."""
from transformer.confidence import element_confidence, overall, scalar_confidence
from transformer.models import Evidence


def atom(value, source_id, source_type, method="direct_field", rid=None):
    return Evidence(field_path="f", value=value, raw_value=value,
                    source_id=source_id, source_type=source_type,
                    method=method, record_id=rid or f"{source_id}#r")


def test_scalar_confidence_hand_computed():
    # ats (0.90) and csv (0.85) agree on X; notes regex (0.50*0.90=0.45) says Y.
    atoms = [
        atom("X", "ats.json", "ats_json"),
        atom("X", "r.csv", "recruiter_csv"),
        atom("Y", "n.txt", "notes_txt", method="regex:labeled_name_v1"),
    ]
    winners = atoms[:2]
    # agreement = 1 - 0.10*0.15 = 0.985 ; support = 1.75/2.20
    want = round(0.985 * (1.75 / 2.20), 6)
    assert scalar_confidence(atoms, winners) == want == 0.783523


def test_single_source_never_inflated():
    atoms = [atom("X", "r.csv", "recruiter_csv")]
    assert scalar_confidence(atoms, atoms) == 0.85


def test_duplicate_rows_count_once_per_source():
    atoms = [
        atom("X", "r.csv", "recruiter_csv", rid="r.csv#row=1"),
        atom("X", "r.csv", "recruiter_csv", rid="r.csv#row=5"),  # dup row
    ]
    assert scalar_confidence(atoms, atoms) == 0.85  # not noisy-OR'd with itself


def test_element_confidence_no_support_penalty():
    # Absence in another source is not contradiction: pure noisy-OR.
    atoms = [
        atom("a@b.com", "ats.json", "ats_json"),
        atom("a@b.com", "n.txt", "notes_txt", method="regex:email_v1"),
    ]
    assert element_confidence(atoms) == round(1 - 0.10 * 0.55, 6) == 0.945


def test_overall_weights_and_empty_fields():
    # Only full_name (w=3) at 1.0 in a 17-weight table.
    assert overall({"full_name": 1.0}) == round(3 / 17, 6)
    assert overall({}) == 0.0
