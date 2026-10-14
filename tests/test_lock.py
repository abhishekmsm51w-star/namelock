import pytest

from namelock.cases import NAMES, notes
from namelock.drafter import ScriptedDrafter
from namelock.lock import forbidden_spellings, verify


# ---- the core promise: a changed name never becomes printable -------------------

@pytest.mark.parametrize("note,good,bad", notes())
def test_faithful_banner_is_printable(note, good, bad):
    d = ScriptedDrafter().draft(note)
    assert good in d.names
    v = verify(note, d.names, d.banner)
    assert v.printable, v.issues


@pytest.mark.parametrize("note,good,bad", notes())
def test_autocorrected_banner_is_blocked(note, good, bad):
    d = ScriptedDrafter(autocorrect="banner").draft(note)
    assert bad in d.banner
    v = verify(note, d.names, d.banner)
    assert not v.printable
    assert any(i.severity == "block" for i in v.issues)


@pytest.mark.parametrize("note,good,bad", notes())
def test_autocorrected_names_are_blocked(note, good, bad):
    d = ScriptedDrafter(autocorrect="names").draft(note)
    v = verify(note, d.names, d.banner)
    assert not v.printable
    assert any(i.kind == "not_in_note" for i in v.issues)


@pytest.mark.parametrize("note,good,bad", notes())
def test_any_repair_offered_passes_the_same_gate(note, good, bad):
    d = ScriptedDrafter(autocorrect="banner").draft(note)
    v = verify(note, d.names, d.banner)
    if v.fixed_banner is not None:
        assert good in v.fixed_banner
        assert verify(note, d.names, v.fixed_banner).printable


def test_twenty_names_all_covered():
    assert len(NAMES) == 20


# ---- specific behaviours --------------------------------------------------------

def test_two_as_not_adya():
    note = "blue flex 6 by 3, birthday, name Aadhya, with two a's, not Adya"
    assert forbidden_spellings(note) == {"adya"}
    assert verify(note, ["Aadhya"], "Happy Birthday Aadhya").printable
    v = verify(note, ["Aadhya"], "Happy Birthday Adya")
    assert not v.printable
    assert v.fixed_banner == "Happy Birthday Aadhya"
    assert len([i for i in v.issues if i.found == "Adya"]) == 1  # reported once


def test_model_returning_the_rejected_spelling_is_blocked():
    note = "name Aadhya, not Adya"
    v = verify(note, ["Adya"], "Happy Birthday Adya")
    assert [i.kind for i in v.issues] == ["forbidden_spelling"]


def test_not_followed_by_lowercase_word_forbids_nothing():
    assert forbidden_spellings("banner not too big, name Rohan") == set()


def test_all_caps_banner_is_fine():
    assert verify("name Aadhya", ["Aadhya"], "HAPPY BIRTHDAY AADHYA").printable


def test_caps_repair_stays_caps():
    v = verify("name Aadhya", ["Aadhya"], "HAPPY BIRTHDAY ADYA")
    assert v.fixed_banner == "HAPPY BIRTHDAY AADHYA"


def test_accent_loss_is_a_change():
    v = verify("name Jos\u00e9", ["Jos\u00e9"], "Feliz Cumple Jose")
    assert not v.printable


def test_decomposed_accent_is_same_name():
    # "e" + combining acute (typed on some phones) must equal the single character
    assert verify("name Jose\u0301", ["Jos\u00e9"], "Feliz Cumple Jos\u00e9").printable


def test_possessive_is_not_a_respelling():
    assert verify("name Aadhya", ["Aadhya"], "Aadhya's Birthday").printable


def test_longer_word_containing_the_name_is_not_a_match():
    assert not verify("name Ann", ["Ann"], "Happy Birthday Anna").printable


def test_invented_name_is_blocked_and_closest_word_suggested():
    v = verify("name Aadhya", ["Aarya"], "Happy Birthday Aarya")
    assert v.issues[0].kind == "not_in_note"
    assert v.issues[0].suggestion == "Aadhya"


def test_name_missing_from_banner():
    v = verify("name Aadhya", ["Aadhya"], "Happy Birthday")
    assert [i.kind for i in v.issues] == ["missing_from_banner"]


def test_two_word_name():
    note = "name Sri Lakshmi"
    assert verify(note, ["Sri Lakshmi"], "Happy Birthday Sri Lakshmi").printable
    assert not verify(note, ["Sri Lakshmi"], "Happy Birthday Sri Laxmi").printable


def test_no_name_needs_a_person():
    v = verify("blue flex 6x3", [], "Happy Birthday")
    assert not v.printable and v.issues[0].kind == "no_name"


# ---- the spelling book ------------------------------------------------------------

def test_close_to_approved_spelling_needs_confirmation():
    v = verify("name Adhya", ["Adhya"], "Happy Birthday Adhya", approved=["Aadhya"])
    assert not v.printable
    assert [(i.kind, i.severity) for i in v.issues] == [("confirm_book", "confirm")]


def test_exact_approved_spelling_passes():
    assert verify("name Aadhya", ["Aadhya"], "Happy Birthday Aadhya", approved=["Aadhya"]).printable


def test_confirming_clears_the_prompt():
    approved = ["Aadhya", "Adhya"]  # the person confirmed the second spelling
    assert verify("name Adhya", ["Adhya"], "Happy Birthday Adhya", approved=approved).printable


def test_unrelated_approved_names_do_not_interfere():
    assert verify("name Rohan", ["Rohan"], "Happy Birthday Rohan", approved=["Aadhya"]).printable
