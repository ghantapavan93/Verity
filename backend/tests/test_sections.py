from app.ingest.sections import Block, build_sections, split_heading, split_lead_in


def test_split_heading_reads_numbers() -> None:
    assert split_heading("12.4 Termination for Convenience") == ("12.4", "Termination for Convenience")
    assert split_heading("Section 9. Limitation of Liability") == ("9", "Limitation of Liability")
    assert split_heading("Definitions") == ("", "Definitions")


def test_lead_in_split_keeps_short_headings_whole() -> None:
    assert split_lead_in("Termination for Convenience") == ("Termination for Convenience", "")


def test_lead_in_split_separates_clause_body() -> None:
    text = (
        "Access and Use.  During the Subscription Period and subject to this Agreement, Customer may access the Cloud Service "
        "in accordance with the Documentation for its internal business purposes."
    )
    heading, body = split_lead_in(text)
    assert heading == "Access and Use"
    assert body.startswith("During the Subscription Period")


def test_sentences_and_definitions_are_body_and_titles_lose_their_stop() -> None:
    assert split_lead_in("Restrictions on Customer.") == ("Restrictions on Customer", "")
    label, body = split_lead_in("Customer will no longer have any right to use the Product.")
    assert label.endswith("…") and body == "Customer will no longer have any right to use the Product."
    definition = "“Agreement” means the Order Form between Provider and Customer together with these terms."
    assert split_lead_in(definition) == ("Agreement", definition)
    assert split_lead_in('"Fees" means the applicable amounts described in an Order Form.') == (
        "Fees",
        '"Fees" means the applicable amounts described in an Order Form.',
    )


def test_a_numbered_sentence_inherits_its_parent_label_and_stays_quotable() -> None:
    blocks = [
        Block("heading", "5 Term & Termination", 1),
        Block("heading", "5.5 Effect of Termination", 2),
        Block("heading", "5.5.1 Customer will no longer have any right to use the Product.", 3),
        Block("heading", "5.5.2 Upon Customer's request, Provider will delete Customer Content within 60 days.", 3),
    ]
    sections = build_sections(blocks)
    assert [(s.number, s.heading) for s in sections[1:]] == [
        ("5.5", "Effect of Termination"),
        ("5.5.1", "Effect of Termination"),
        ("5.5.2", "Effect of Termination"),
    ]
    assert sections[2].text == "Customer will no longer have any right to use the Product."
    assert sections[3].text.startswith("Upon Customer's request")


def test_computed_numbers_follow_the_outline() -> None:
    blocks = [
        Block("text", "Cloud Service Agreement"),
        Block("heading", "Service", 1),
        Block("heading", "Access and Use.  During the Subscription Period, Customer may access the Cloud Service.", 2),
        Block("heading", "Support.  Provider will provide support.", 2),
        Block("heading", "Restrictions", 1),
        Block("heading", "Restrictions on Customer.  Customer will not resell the Cloud Service.", 2),
        Block("heading", "Provider will submit a final invoice for all outstanding Fees accrued before termination and Customer will pay it.", 3),
    ]
    sections = build_sections(blocks, title="Cloud Service Agreement")
    numbers = [(s.number, s.heading) for s in sections]
    assert numbers[0] == ("", "Cloud Service Agreement")
    assert numbers[1] == ("1", "Service")
    assert numbers[2] == ("1.1", "Access and Use")
    assert numbers[3] == ("1.2", "Support")
    assert numbers[4] == ("2", "Restrictions")
    assert numbers[5] == ("2.1", "Restrictions on Customer")
    assert numbers[6][0] == "2.1.1"
    assert sections[2].text == "During the Subscription Period, Customer may access the Cloud Service."
    assert sections[2].number_computed is True


def test_explicit_numbers_win_and_reset_counters() -> None:
    blocks = [
        Block("heading", "12 Termination", 1),
        Block("heading", "12.4 Termination for Convenience", 2),
        Block("text", "Body."),
        Block("heading", "Effect of Termination", 2),
    ]
    sections = build_sections(blocks)
    assert [s.number for s in sections] == ["12", "12.4", "12.5"]
    assert sections[1].text == "Body."


def test_oversized_sections_split_at_paragraphs() -> None:
    blocks = [Block("heading", "1 Long", 1)] + [Block("text", "x" * 2500) for _ in range(4)]
    sections = build_sections(blocks)
    assert [s.heading for s in sections] == ["Long (part 1)", "Long (part 2)"]
    assert all(len(s.text) <= 6000 for s in sections)


def test_a_long_lead_in_is_the_first_sentence_not_a_title() -> None:
    text = (
        "The following sections will survive expiration or termination of the Agreement: Section 1.4 (Feedback and Usage Data), "
        "Section 8 (Limitation of Liability), Section 10 (Confidentiality)."
    )
    label, body = split_lead_in(text)
    assert label.endswith("…") and body == text, "every word stays quotable"
    assert split_lead_in("Access and Use.  During the Subscription Period, Customer may access the Cloud Service.") == (
        "Access and Use",
        "During the Subscription Period, Customer may access the Cloud Service.",
    )
