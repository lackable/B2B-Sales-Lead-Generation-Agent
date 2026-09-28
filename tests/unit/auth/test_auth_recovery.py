"""Recovery codes: shape, entropy, normalization and verification input."""

from leadgen.auth import recovery


def test_generated_code_has_five_groups_of_four():
    code = recovery.generate_recovery_code()

    groups = code.split("-")
    assert len(groups) == recovery.GROUP_COUNT
    assert all(len(group) == recovery.GROUP_SIZE for group in groups)
    assert all(character in recovery.ALPHABET for group in groups for character in group)


def test_alphabet_omits_ambiguous_characters_and_folds_them_back():
    for ambiguous in "ILOU":
        assert ambiguous not in recovery.ALPHABET

    assert recovery.normalize_recovery_code("oil") == "011"


def test_generated_codes_are_unique():
    codes = {recovery.generate_recovery_code() for _ in range(200)}

    assert len(codes) == 200


def test_normalization_accepts_human_input():
    code = recovery.generate_recovery_code()
    messy = f"  {code.replace('-', ' ').lower()}  "

    assert recovery.normalize_recovery_code(messy) == recovery.normalize_recovery_code(code)
    assert recovery.is_well_formed(messy) is True
    assert recovery.is_well_formed("nope") is False
    assert recovery.is_well_formed("") is False


def test_normalization_strips_separators_and_uppercases():
    assert recovery.normalize_recovery_code("k7q2-9xmp 4hda_zr8n.tw3c") == "K7Q29XMP4HDAZR8NTW3C"


def test_code_length_is_a_hundred_bits():
    import math

    assert len(recovery.ALPHABET) == 32
    assert recovery.CODE_LENGTH * math.log2(len(recovery.ALPHABET)) == 100
