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
    assert found is not None and found.method == "alnum"
    assert DEFINITION[found.start : found.end] == "GDPR” means European Union Regulation 2016/679 as implemented by local law"


def test_an_inserted_space_is_forgiven_but_a_changed_digit_or_word_is_not() -> None:
    spaced = locate("upon fifteen (1 5) days written notice", BODY)
    assert spaced is not None and spaced.method == "alnum"
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
    assert locate("12.11 There are no third-party beneficiaries of this Agreement.", text, label="12.11 No Third-Party Beneficiary") is not None
    assert locate(quote, text, label="12.11 Assignment") is None, "a different heading is not a label to strip"
