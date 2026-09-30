from app.verify.spans import locate, normalize_with_map

TEXT = (
    "12.4 Termination for Convenience\n\n"
    "Customer may terminate this Agreement or any Order Form for convenience upon fifteen (15) days’ written notice to Provider. "
    "On termination for convenience, Customer shall pay all Fees accrued through the effective date of termination."
)


def test_exact_match_returns_original_offsets() -> None:
    quote = "upon fifteen (15) days’ written notice to Provider"
    found = locate(quote, TEXT)
    assert found is not None
    assert found.method == "exact"
    assert TEXT[found.start : found.end] == quote


def test_typographic_quotes_and_whitespace_are_normalised() -> None:
    quote = "fifteen  (15) days' written   notice"
    found = locate(quote, TEXT)
    assert found is not None
    assert found.method == "normalized"
    assert TEXT[found.start : found.end] == "fifteen (15) days’ written notice"


def test_case_differences_still_locate() -> None:
    found = locate("customer MAY terminate this agreement", TEXT)
    assert found is not None
    assert found.method == "casefold"
    assert TEXT[found.start : found.end] == "Customer may terminate this Agreement"


def test_paraphrase_is_not_found() -> None:
    assert locate("the customer can end the contract with 15 days notice", TEXT) is None


def test_empty_quote_is_not_found() -> None:
    assert locate("   ", TEXT) is None


def test_index_map_points_at_original_characters() -> None:
    normalized, index_map = normalize_with_map("A  B—C")
    assert normalized == "A B-C"
    assert [("A  B—C")[i] for i in index_map] == ["A", " ", "B", "—", "C"]


DEFINITION = "“GDPR” means European Union Regulation 2016/679 as implemented by local law in the relevant European Union member state."
BODY = "Customer may terminate this Agreement or any Order Form for convenience upon fifteen (15) days’ written notice to Provider."


def test_quotation_marks_and_punctuation_do_not_block_a_match() -> None:
    found = locate("GDPR means European Union Regulation 2016/679 as implemented by local law", DEFINITION)
    assert found is not None and found.method == "typed"
    assert DEFINITION[found.start : found.end] == "GDPR” means European Union Regulation 2016/679 as implemented by local law"


def test_an_inserted_space_is_forgiven_but_a_changed_digit_or_word_is_not() -> None:
    assert locate("upon fifteen (1 5) days written notice", BODY) is None, "a number split in two is two numbers (verifier v5)"
    spaced = locate("upon fifteen (15) days written notice", BODY)
    assert spaced is not None and spaced.method == "typed"
    assert BODY[spaced.start : spaced.end] == "upon fifteen (15) days’ written notice"
    assert locate("upon fifteen (16) days’ written notice", BODY) is None
    assert locate("upon sixteen (15) days’ written notice", BODY) is None
    assert locate("upon fifteen (15) days’ prior written notice", BODY) is None


def test_a_section_label_copied_in_front_of_the_quote_is_stripped_only_when_the_label_is_known() -> None:
    quote = "12.4 Termination for Convenience. Customer may terminate this Agreement or any Order Form"
    assert locate(quote, BODY) is None
    found = locate(quote, BODY, label="12.4 Termination for Convenience")
    assert found is not None and found.method == "unprefixed:exact"
    assert BODY[found.start : found.end] == "Customer may terminate this Agreement or any Order Form"
    assert locate("12.4 Termination for Convenience", BODY, label="12.4 Termination for Convenience") is None, "a label alone is not a quote"


def test_casefold_keeps_offsets_when_a_character_folds_to_two() -> None:
    text = "Notices go to Straße 1, Berlin."
    found = locate("STRASSE 1, BERLIN", text)
    assert found is not None and found.method == "casefold"
    assert text[found.start : found.end] == "Straße 1, Berlin"


def test_a_heading_copied_without_its_number_is_stripped_too() -> None:
    text = "There are no third-party beneficiaries of this Agreement."
    quote = "No Third-Party Beneficiary There are no third-party beneficiaries of this Agreement."
    found = locate(quote, text, label="12.11 No Third-Party Beneficiary")
    assert found is not None and found.method == "unprefixed:exact"
    assert text[found.start : found.end] == text
    # Verifier v4: the number alone is not a label to strip; a quote that starts with digits keeps them.
    assert locate("12.11 There are no third-party beneficiaries of this Agreement.", text, label="12.11 No Third-Party Beneficiary") is None
    assert locate(quote, text, label="12.11 Assignment") is None, "a different heading is not a label to strip"


def test_a_quote_is_never_found_inside_a_longer_number_or_word() -> None:
    """Found by the independent review of 2026-09-29: substring matches without a boundary."""
    assert locate("5 days", "Customer may cure within fifteen (15) days of notice.") is None
    assert locate("$1,500", "The fee is $11,500 per year.") is None
    assert locate("30 days", "Payment is due within 130 days.") is None
    assert locate("able to terminate", "The Provider is unable to terminate for convenience.") is None
    assert locate("Section 1", "Section 12 applies to renewals.") is None
    assert locate("pay", "Payment is due on receipt.") is None
    found = locate("15) days", "Customer may cure within fifteen (15) days of notice.")
    assert found is not None and found.method == "exact"


def test_a_quote_ending_on_punctuation_stays_exact_when_a_letter_follows_it() -> None:
    # From the record (run d9aaaa4683054be8, §9.4): the quote ends with "(" and the text continues "(a) nor (b)".
    text = "Provider may: (a) obtain the right for Customer to continue using the Product; or (c) if neither (a) nor (b) are available, terminate."
    found = locate("or (c) if neither (", text)
    assert found is not None and found.method == "exact"
    assert text[found.start : found.end] == "or (c) if neither ("


def test_a_bounded_occurrence_later_in_the_text_is_preferred_over_an_unbounded_first_one() -> None:
    text = "The 130 days mentioned above are not the 30 days of the cure period."
    found = locate("30 days", text)
    assert found is not None
    assert text[found.start : found.end] == "30 days" and found.start == text.index("the 30 days") + 4


def test_a_verbatim_quote_with_a_boundary_is_still_found_even_when_it_drops_context() -> None:
    # "less than 30 days" is a verbatim quote of "not less than 30 days"; the highlight shows the "not".
    found = locate("less than 30 days", "Notice of not less than 30 days is required.")
    assert found is not None and found.method == "exact"


def test_a_number_alone_is_never_stripped_so_a_changed_number_cannot_hide_behind_a_label() -> None:
    """Found by tracing (docs/SYSTEM_TRUTH.md, 2026-09-29): under verifier v2 and v3 the number of §1.5 was cut
    from "15 days' written notice" and the remainder verified against "forty-five (45) days' written notice"."""
    text = "Either party may terminate on forty-five (45) days' written notice to the other."
    assert locate("15 days' written notice", text, label="1.5 Termination") is None
    assert locate("15 days' written notice", text, label="15 Termination") is None
    assert locate("1.5 days' written notice", text, label="1.5 Termination") is None
    assert locate("1.5", text, label="1.5 Termination") is None
    # The label written as the model saw it, number and heading, is still forgiven.
    found = locate("1.5 Termination Either party may terminate on forty-five (45) days' written notice", text, label="1.5 Termination")
    assert found is not None and found.method == "unprefixed:exact"
    found = locate("1.5. Termination. Either party may terminate", text, label="1.5 Termination")
    assert found is not None and found.method == "unprefixed:exact"
    # A number written differently from the label is not the label: "15 Termination" is not §1.5.
    assert locate("15 Termination Either party may terminate", text, label="1.5 Termination") is None


def test_a_decimal_point_is_a_digit_to_the_alnum_tier() -> None:
    """Found by tracing (docs/SYSTEM_TRUTH.md, 2026-09-29): the letters-and-digits tier read "$1,500" and "$15.00"
    as the same six characters, and "15%" as "1.5%"."""
    assert locate("fee of $15.00 per user", "The fee of “$1,500” per user is payable annually.") is None
    assert locate("interest at 15% per annum", "Interest accrues at “1.5%” per annum.") is None
    assert locate("a cap of 2.0 times the fees", "A cap of “20” times the fees applies.") is None
    found = locate("fee of $1500 per user", "The fee of “$1,500” per user is payable annually.")
    assert found is not None and found.method == "typed", "a thousands separator is not something a reader notices"
    found = locate("interest accrues at 1.5% per annum", "Interest accrues at “1.5%” per annum.")
    assert found is not None and found.method == "typed"
