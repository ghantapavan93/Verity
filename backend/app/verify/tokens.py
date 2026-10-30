"""Typed tokens: the representation under which a quote and its source are compared once exact text has failed.

The letters-and-digits tier compared two texts by their letters and digits alone, which made "$1,500" and
"$15.00" the same six characters and "15%" the same as "1.5%". Under typed tokens a number is a number:
"1,500" and "1500" are one value (Decimal, never float), "15.00" and "1,500" are two, "15%" and "1.5%" are
two, and a run of letters is a word, compared whole. Punctuation, quotation marks, dashes and whitespace carry
no meaning and are dropped, so "days’ written" still meets "days written" and "non- exclusive" still meets
"non-exclusive", while a changed digit or a moved decimal point can never be forgiven, and neither can a space
moved inside the letters: "the rapist" is not "therapist" (verifier v6).

Until v7 a token could end inside a run of letters and digits, so "30days" gave the number 3 and "1,500USD" gave
1,50, and every comma was dropped, so "1,5%" was 15%: five quotes with a changed number were found, and one recorded
span verified "3,0 days" against "30 days". From v7 every letter and digit belongs to exactly one significant token,
and a comma separates thousands only in thousands grouping.

Until v8 a sign was punctuation: "-5%" met "5%" and "($500)" met "$500", so a negative amount verified as a positive
one. From v8 what is written against a number belongs to it (`signed`): a minus sign, and parentheses around it, which
are how accounting writes a negative and cannot be told from a restated "(30)". The same reading of a number as it
is written (`written_numbers`) tells the verifier's edges where a number ends: no located span begins or ends inside one.

Until v9 an amount written with a magnitude letter against its digits ("$5M", "USD 10K", "2.5bn") was no number at
all: its digits and letter were one word, and its minus sign, parentheses and currency were punctuation, so "Adjustment
Amount $5M" verified against "Adjustment Amount -$5M" (the legal evaluation's blocker B1, 2026-10-14), and "$5M" was
found word for word inside "-$5M". A currency written as letters before a dollar sign ("US$500") was no currency, so
its minus sign was dropped as well. From v9 both are numbers as they are written (`_WRITTEN`): such an amount carries
its sign, its parentheses, its currency and its magnitude letter, and no span begins or ends inside it; nor, in a number
written with a sign or parentheses, at the space after its currency ("-USD 10K" never yields "10K"). `tokenize` is
unchanged: the amount's tokens are joined only where the verifier compares them (`signed`).

Until v10 a currency outside v9's lists ("Ksh", "RM", "Rp") was a word, so its minus sign or parentheses were
punctuation and "Ksh 5M" verified against "-Ksh 5M", "RM5M" against "(RM5M)" (found on 2026-10-14, after the legal
evaluation's pilot). From v10 a short label (one to four letters, an optional full stop and space) directly after a
minus sign, or directly inside an opening parenthesis, is part of the number written after it, whatever the label: a
sign is never dropped for want of knowing a currency's name. Inside such a number a word that holds digits ("RM5M") is
part of its value, so "(RM5M)" and "(RM 5M)" are one value, and neither is "RM5M". As with v8's parentheses around any
number, a quote that leaves out the parentheses of "(No 1)" is withheld; one that keeps them is found.

Until v11 a number opened only with a minus sign or a parenthesis, so a late fee of ".5%" was found as "5%", "±5%" and
"+/-5%" as "5%" and "-5%", ">$1,000,000" as "$1,000,000" and "≥99.9%" as "99.9%" (the break audit, 2026-10-30). From
v11 a comparator or a plus or plus-minus sign directly before a number, and a decimal point with no digit before it,
are part of the number (`_written_v11`), as a minus sign is: written apart from the number by a space, each stays
punctuation, as a minus sign does. Digits joined by "/" or ":" are one number and one value ("2/3", "3:1",
"12/31/2026"), so "2/3" is not "2-3". And the typed tier no longer forgives a sentence's end (`sentence_ends`): it
compared "terminate. Without cause" as "terminate without cause".

Every token keeps the offsets of its surface in the original text, so a match is reported as exact
character offsets and the interface highlights what was found.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum


class Kind(StrEnum):
    WORD = "word"
    NUMBER = "number"
    CURRENCY = "currency"
    PERCENT = "percent"
    SECTION = "section"  # "8.1.2", "12.4(a)": an identifier made of numbers, never a quantity
    PUNCT = "punct"
    BREAK = "break"  # v11: the mark that ends a sentence, which the typed tier compares (`compared`); `tokenize` makes none


@dataclass(frozen=True)
class Token:
    kind: Kind
    canonical: str
    start: int
    end: int

    @property
    def significant(self) -> bool:
        return self.kind is not Kind.PUNCT


_CURRENCY_SIGNS = "$€£¥"
_CURRENCY = rf"[{_CURRENCY_SIGNS}]|USD|EUR|GBP|CHF|CAD|AUD"
# The ways a number is written, in the order they are tried; each is one token, and `_WRITTEN` below is made of them.
_SECTION = r"\d+(?:\.\d+){2,}(?:\([a-z0-9]+\))*|\d+(?:\.\d+)?(?:\([a-z0-9]+\))+"  # 8.1.2, 12.4(a), 3(b)
_MONEY = rf"(?:{_CURRENCY})\s?\d+(?:,\d+)*(?:\.\d+)?"  # $1,500  USD 10.00
_PERCENT = r"\d+(?:,\d+)*(?:\.\d+)?\s?(?:%|percent\b|per\s+cent\b)"  # 15%  1.5 percent
_PLAIN = r"\d+(?:,\d+)*(?:\.\d+)?"  # 30  1,500  15.00; a comma only between digits
_TOKEN = re.compile(
    rf"""
    (?<![^\W_])                                         # no token starts inside a run of letters and digits
    (?:(?:(?P<section>{_SECTION})
    |(?P<currency>{_MONEY})
    |(?P<percent>{_PERCENT})
    |(?P<number>{_PLAIN})
    |(?P<word>[^\W_]+))                                 # letters, any script; "A1", "30days" are one word
    (?![^\W_])                                          # and no token ends inside a run (v7)
    |(?P<punct>[^\w\s]|_))
    """,
    re.IGNORECASE | re.VERBOSE,
)

# What is written against a number and belongs to it (verifier v8). A minus sign is any dash a typesetter writes for
# one, directly before the number, with no letter or digit directly before the dash: in "COVID-19" and "4-6" the dash
# is a hyphen or a range. A digit mark joins two digits into one number: a decimal point or a thousands separator, in
# each form it is typeset ("1,500", "30.5", "1 500" with a no-break, narrow or thin space, "1'500", the Arabic marks).
_MINUS_SIGNS = frozenset("-\u2010\u2011\u2012\u2013\u2014\u2212\ufe63\uff0d")
_DIGIT_MARKS = frozenset(".,'\u2019\u00a0\u202f\u2009\u066b\u066c")
_NUMBERS = frozenset({Kind.NUMBER, Kind.CURRENCY, Kind.PERCENT, Kind.SECTION})
# The only characters at which an edge can meet what is written against a number: its sign, its currency or percent
# sign, its parentheses. An edge on any other punctuation, or on a space, is an edge (spans.bounded), except inside a
# number written with a sign or parentheses (v9, `SIGN_OPENERS`).
_ATTACHED_V8 = _MINUS_SIGNS | frozenset(f"()%{_CURRENCY_SIGNS}")  # verifier v8's, kept for the packs of v8 runs
# What a negative number opens with: a minus sign or the parenthesis of an accounting negative (verifier v9).
SIGN_OPENERS = _MINUS_SIGNS | frozenset("(")

# Verifier v9. A currency is any currency sign Unicode has (category Sc: "$", "₹", "₩", "₽", …), any ISO 4217 code
# written in capitals, a few abbreviations contracts write ("Rs.", "RMB", "kr"), the six codes v8 knew in any case, or
# capitals against a dollar sign ("US$", "HK$", "A$"). An amount may carry a magnitude letter against its digits, as
# finance writes thousands, millions, billions and trillions.
_CURRENCY_SYMBOLS = (
    "$¢£¤¥֏؋߾߿৲৳৻૱௹฿៛₠₡₢₣"
    "₤₥₦₧₨₩₪₫€₭₮₯₰₱₲₳₴₵₶₷"
    "₸₹₺₻₼₽₾₿⃀꠸﷼﹩＄￠￡￥￦\U00011fdd"
    "\U00011fde\U00011fdf\U00011fe0\U0001e2ff\U0001ecb0"
)  # Unicode 15.1 category Sc, written out so that every Python, and every pack, reads the same set
_ISO_4217 = (  # noqa: SIM905 - the ISO 4217 list as it is printed, not 180 quoted literals
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE "
    "CHF CHW CLF CLP CNY COP COU CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ "
    "GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD "
    "MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG "
    "QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD "
    "TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAF XAG XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XUA "
    "YER ZAR ZMW ZWG ZWL"
).split()
_CODES_V9 = rf"(?-i:{'|'.join(_ISO_4217)}|RMB|Rs\.?|kr\.?|Kr\.?)|USD|EUR|GBP|CHF|CAD|AUD"
_CURRENCY_V9 = rf"(?-i:[A-Z]{{1,3}})\$|[{re.escape(_CURRENCY_SYMBOLS)}]|{_CODES_V9}"
# The only characters at which an edge can meet what is written against a number: its sign, its currency or percent
# sign, its parentheses. An edge on any other punctuation, or on a space, is an edge (spans.bounded), except inside a
# number written with a sign or parentheses (v9, `SIGN_OPENERS`). From v9 every currency sign is one of them.
_ATTACHED = _ATTACHED_V8 | frozenset(_CURRENCY_SYMBOLS)
_MAGNITUDE = r"(?:mln|bln|mm|mn|bn|tn|k|m|b|t)"
_MONEY_V9 = rf"(?:{_CURRENCY_V9})\s?\d+(?:,\d+)*(?:\.\d+)?"  # US$500  HK$ 1,200  ₹ 500  INR 1,500  USD 10.00
_AMOUNT = rf"(?:(?:{_CURRENCY_V9})\s?)?\d+(?:,\d+)*(?:\.\d+)?{_MAGNITUDE}"  # $5M  USD 10K  INR 5M  2.5bn  US$3m
# The token an amount's digits make with a magnitude letter or a currency code glued to them once `tokenize` has read
# them: one word ("5m", "usd10k", "INR5M", "INR500"), since a token never ends inside a run of letters and digits. Its
# value is read from its parts (`_amount_value`); without a code it must end in its magnitude letter.
_AMOUNT_WORD = re.compile(
    rf"(?P<code>(?-i:{'|'.join(_ISO_4217)}|RMB)|USD|EUR|GBP|CHF|CAD|AUD)?(?P<digits>\d+)(?P<magnitude>mln|bln|mm|mn|bn|tn|k|m|b|t)?"
    r"(?(code)|(?<=[^\W\d_]))",
    re.IGNORECASE,
)


# Verifier v10: the label a minus sign or an opening parenthesis may carry before a number ("Ksh", "RM", "Rp", "No"),
# one to four letters of any script, whole: never the start of a longer word.
_LABEL = r"[^\W\d_]{1,4}(?![^\W\d_])"
# The value of a word inside a number once a label has joined it ("RM5M", "Ksh5"): its letters, digits and magnitude.
_LABELLED_WORD = re.compile(r"([^\W\d_]*)(\d+)(mln|bln|mm|mn|bn|tn|k|m|b|t)?", re.IGNORECASE)

# Verifier v11: what else a number may open with, directly before its digits or its label (a comparator, a plus or
# plus-minus sign), the marks that join its digits into one value, and what every edge inside a number splits it after.
# A sign of relation may stand against a letter ("Margin>5%"); the others, like a minus sign, may not ("A+" is a grade,
# "3+4" a sum, "COVID-19" a name).
_RELATIONS = frozenset("<>≤≥≦≧≠⩽⩾≶≷")
_COMPARATORS = _RELATIONS | frozenset("+±∓~≈")
_JOINED = frozenset("/:")
_DIGIT_MARKS_V11 = _DIGIT_MARKS | _JOINED
SIGN_OPENERS_V11 = SIGN_OPENERS | _COMPARATORS | frozenset(".")
# Where a sentence ends: a full stop, an ellipsis, a question or an exclamation mark, past closing quotation marks and
# brackets, that a space and a letter not in lower case follow ("Inc. shall" goes on, "terminate. Without" does not), or,
# with no space, a capitalised word after a lower-case letter ("terminate.Without"); and every semicolon.
_SENTENCE_END = re.compile(r"""[.!?…](?=["'”’)\]»]*(?:\s+["'“‘(\[«]*(?P<next>[^\W\d_])|(?P<tight>[^\W\d_])[^\W\d_]))|;""")
# A clause's letter or numeral standing in parentheses, "(a)", "(A)", "(iv)", "(IV)": its case names a different clause.
_CLAUSE_LETTER = re.compile(r"\((?:[^\W\d_]|[ivxlcdm]+|[IVXLCDM]+)\)")
# A combining mark or a zero-width (non-)joiner belongs to the word it is written in, as Unicode's word boundaries read it.
_JOINERS = frozenset("\u200c\u200d")


def marked(ch: str) -> bool:
    """Whether ``ch`` is a combining mark or a joiner: part of the letters it is written between or after (v11)."""
    return ch in _JOINERS or unicodedata.category(ch)[0] == "M"


def _one_of(characters: frozenset[str]) -> str:
    return "[" + "".join(re.escape(c) for c in sorted(characters)) + "]"


def _written(one: str) -> re.Pattern[str]:
    """A number as it is written, made of ``one``: an opening parenthesis that a closing one answers, a minus sign, one
    or more tokens joined by a digit mark ("1 500 000" with narrow spaces, "1.500.000,25"), and a percent sign the tokens
    leave out ("1.500.000%" is an identifier and a sign to them). Each token is matched whole, as `_TOKEN` matches it,
    and the groups possessively: a number that is never closed costs one pass, not a search over the ways to split it."""
    # The pattern's text is v8's to the character (a v8 pack carries it), so its lines keep v8's indentation.
    pattern = rf"""
    (?:(?P<open>\()|(?<![^\W_]))
    (?:(?<![^\W_]){_one_of(_MINUS_SIGNS)})?
    {one}(?:{_one_of(_DIGIT_MARKS)}{one})*+%?+
    (?(open)\))
    """
    return re.compile(pattern, re.IGNORECASE | re.VERBOSE)


def _written_v10(one: str) -> re.Pattern[str]:
    """v10's number as written: v9's, and after its minus sign, or inside its opening parenthesis, a short label
    (`_LABEL`, with an optional full stop and space) before the number: "-Ksh 5M", "(RM5M)", "(Rp 5M)"."""
    pattern = rf"""
    (?:(?P<open>\()|(?<![^\W_]))
    (?:(?<![^\W_])(?P<sign>{_one_of(_MINUS_SIGNS)}))?
    (?:(?(sign){_LABEL}\.?\s?|(?(open){_LABEL}\.?\s?|(?!))))?
    {one}(?:{_one_of(_DIGIT_MARKS)}{one})*+%?+
    (?(open)\))
    """
    return re.compile(pattern, re.IGNORECASE | re.VERBOSE)


def _written_v11(one: str) -> re.Pattern[str]:
    """v11's number as written: v10's, opened also by a comparator or a plus sign, alone or before a minus sign, or by
    "+/-" ("≥99.9%", ">$1,000,000", "±5%", "+/-5%"), a sign of relation even against a letter ("Margin>5%"), and by a
    decimal point before its digits (".5%", "-.5%", "$.50"); and its digits joined by "/" or ":" as well ("2/3", "3:1")."""
    minus = _one_of(_MINUS_SIGNS)
    loose = _one_of(_COMPARATORS - _RELATIONS)
    relation = _one_of(_RELATIONS)
    pattern = rf"""
    (?:(?P<open>\()|(?<![^\W_])|(?={relation}))
    (?:(?P<sign>(?<![^\W_])(?:\+/{minus}|{loose}{minus}?|{minus})|(?:[<>]=|{relation}){minus}?))?
    (?:(?(sign){_LABEL}\.?\s?|(?(open){_LABEL}\.?\s?|(?!))))?
    (?:\.(?=\d))?
    {one}(?:{_one_of(_DIGIT_MARKS_V11)}{one})*+%?+
    (?(open)\))
    """
    return re.compile(pattern, re.IGNORECASE | re.VERBOSE)


# A number as it is written: the one definition that both the typed tier (`signed`) and the verifier's edges
# (`written_numbers`, spans.bounded) read. `_WRITTEN_V8` is verifier v8's, kept for the evidence packs of runs verified
# under v8 (application/evidence_pack); `_WRITTEN_V9` is v9's, which also reads an amount with a magnitude letter and a
# currency written as letters against a dollar sign, kept for the packs of runs verified under v9; `_WRITTEN_V10` is
# v10's, which also reads a label after a minus sign or inside a parenthesis as part of the number, kept for the packs of
# runs verified under v10; `_WRITTEN` is v11's, which also reads a comparator, a plus sign and a leading decimal point as
# part of the number, and "/" and ":" between its digits.
_WRITTEN_V8 = _written(rf"(?>(?:{_SECTION}|{_MONEY}|{_PERCENT}|{_PLAIN})(?![^\W_]))")
# v9's begins by looking ahead for a digit within the widest currency's width, so that the many words where no number
# begins are passed over at once rather than tried against every currency (it changes no match: every way v9 writes a
# number puts a digit within twelve characters of where the number begins).
_V9_ONE = rf"(?=\D{{0,12}}\d)(?>(?:{_AMOUNT}|{_SECTION}|{_MONEY_V9}|{_PERCENT}|{_PLAIN})(?![^\W_]))"
# v11's: an amount may carry a decimal point before its digits after its currency, "$.50", "€.50", "$.5M".
_DIGITS_V11 = r"(?:\d+(?:,\d+)*(?:\.\d+)?|\.\d+)"
_V11_ONE = (
    rf"(?=\D{{0,12}}\d)(?>(?:(?:(?:{_CURRENCY_V9})\s?)?{_DIGITS_V11}{_MAGNITUDE}|{_SECTION}"
    rf"|(?:{_CURRENCY_V9})\s?{_DIGITS_V11}|{_PERCENT}|{_PLAIN})(?![^\W_]))"
)
_WRITTEN_V9 = _written(_V9_ONE)
_WRITTEN_V10 = _written_v10(_V9_ONE)
_WRITTEN = _written_v11(_V11_ONE)
VERSION = 11  # the verifier version these definitions are (spans.VERIFIER_VERSION)


def written_numbers(text: str, version: int = VERSION, invisible: frozenset[str] = frozenset()) -> list[tuple[int, int]]:
    """Where each number of ``text`` lies as it is written, its sign, parentheses, groups, currency, magnitude letter
    and percent sign included, under the verifier ``version`` (8 to 11): in order, never overlapping. Characters in
    ``invisible`` (those normalisation deletes, spans._INVISIBLE) are read as absent, as a reader sees the text, and the
    offsets returned are the original text's: "-‎$5M" is one number, its sign included (v9)."""
    pattern = _WRITTEN if version >= 11 else _WRITTEN_V10 if version >= 10 else _WRITTEN_V9 if version >= 9 else _WRITTEN_V8
    if not invisible or invisible.isdisjoint(text):
        return [match.span() for match in pattern.finditer(text)]
    kept = [i for i, ch in enumerate(text) if ch not in invisible]
    visible = "".join(text[i] for i in kept)
    return [(kept[match.start()], kept[match.end() - 1] + 1) for match in pattern.finditer(visible)]


def joins_digits(before: str, after: str) -> bool:
    """Whether the joint between ``before`` and ``after``, the characters a reader sees on each side of an edge, is a
    digit mark between two digits: "1,500|,000", "Section 5|.2", "1| 500" with a narrow space (verifier v8), "2|/3" (v11)."""
    b, a = before[-1:], after[:1]
    return (b.isdigit() and a in _DIGIT_MARKS_V11 and after[1:2].isdigit()) or (b in _DIGIT_MARKS_V11 and before[-2:-1].isdigit() and a.isdigit())


def attaches(b: str, a: str) -> bool:
    """Whether a character at a joint is one written against a number (a sign, a currency or percent sign, a
    parenthesis). Only there can a joint that is not between two digits lie inside a number; at a space or any other
    punctuation it is an edge."""
    return b in _ATTACHED or a in _ATTACHED


_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")


def canonical_number(text: str) -> str:
    """ "1,500" → "1500": thousands separators and spaces carry nothing. The digits themselves are kept as written,
    so "15.00" is not "15" and "1.50" is not "1.5": a verifier forgives spelling, never precision. A comma is a
    thousands separator only in thousands grouping: "1,5" and "15,00" keep it, so they are never 15 or 1500 (v7)."""
    compact = text.replace(" ", "")
    if "," in compact and not _GROUPED.fullmatch(compact):
        return compact
    cleaned = compact.replace(",", "")
    try:
        Decimal(cleaned)
    except InvalidOperation:
        return text
    return cleaned


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    for match in _TOKEN.finditer(text):
        kind = Kind(match.lastgroup or "punct")
        surface = match.group(0)
        if kind is Kind.WORD:
            canonical = surface.casefold()
        elif kind is Kind.NUMBER:
            canonical = canonical_number(surface)
        elif kind is Kind.CURRENCY:
            symbol = re.match(rf"(?:{_CURRENCY})", surface, re.IGNORECASE)
            assert symbol is not None
            canonical = symbol.group(0).upper() + canonical_number(surface[symbol.end() :])
        elif kind is Kind.PERCENT:
            digits = re.match(r"[\d,]*(?:\.\d+)?", surface)
            assert digits is not None
            canonical = canonical_number(digits.group(0)) + "%"
        elif kind is Kind.SECTION:
            canonical = surface.lower()
        else:
            canonical = surface
        tokens.append(Token(kind, canonical, match.start(), match.end()))
    return tokens


def significant(tokens: list[Token]) -> list[Token]:
    return [t for t in tokens if t.significant]


def is_amount(text: str, token: Token) -> bool:
    """Whether ``token`` is an amount word of ``text`` (verifier v9): its digits with a magnitude letter or a currency code
    glued to them, "5m", "usd10k", "INR500"."""
    if token.kind is not Kind.WORD or text[token.start : token.end].isalpha():
        return False  # most words are letters alone: no need to try them against every currency code
    return _AMOUNT_WORD.fullmatch(text, token.start, token.end) is not None


def _amount_value(text: str, token: Token) -> str:
    """An amount word's value as its parts say it, "USD10k" for "usd10k": its currency code, its digits and its
    magnitude letter, the letter compared without case ("5M" is "5m", never "5MM")."""
    match = _AMOUNT_WORD.fullmatch(text, token.start, token.end)
    assert match is not None
    return (match["code"] or "").upper() + match["digits"] + (match["magnitude"] or "").casefold()


def _number_word_value(text: str, token: Token) -> str:
    """The value of a word that is part of a number: an amount word's (`_amount_value`), or, from v10, a labelled word's
    letters in capitals, its digits and its magnitude letter without case ("RM5M" is "RM5m", as "RM 5M" joins to)."""
    if _AMOUNT_WORD.fullmatch(text, token.start, token.end) is not None:
        return _amount_value(text, token)
    match = _LABELLED_WORD.fullmatch(text, token.start, token.end)
    if match is None:
        return token.canonical
    return match[1].upper() + match[2] + (match[3] or "").casefold()


def signed(text: str, tokens: list[Token], version: int = VERSION, invisible: frozenset[str] = frozenset()) -> list[Token]:
    """The tokens of ``text`` with what is written against each number joined to it (verifier v8): its minus sign, so
    "-5%" is not "5%"; the parentheses around it, so "($500)" is not "$500"; a percent sign the tokens left out. What
    a number is written as is `_WRITTEN`: its first token takes what stands before it, its last token what stands after
    it, and a joined token starts and ends where the written number does. The punctuation it took in stays a token, and
    carries nothing. `tokenize` itself is unchanged, so the values read from a passage elsewhere (runs.values,
    trust.facts) do not move.

    From v9 an amount word ("5m", "10k") is a number too, so "-$5M" is not "$5M" and "(USD 10K)" not "USD 10K"; what is
    written before a number is compared without spaces or case ("USD 10K" is "usd10k"), and a currency written as
    letters before it ("USD", "US" of "US$") belongs to it rather than standing as a word of its own. ``version`` 8
    reads as v8 did, for the evidence packs of runs verified under v8. ``invisible`` (v9): characters a reader does not
    see, which neither part a sign from its number nor count as written ("-‎$5M" is "-$5M"). From v10 a word holding
    digits inside a number ("RM5M" of "(RM5M)") is part of its value, and a label before it is joined like a currency.
    From v11 a number whose digits "/" or ":" join is one token, its value read whole: "2/3" is not "2 3"; and a section
    identifier keeps its letters' case, so "2(A)" is not "2(a)"."""
    v9, v10, v11 = version >= 9, version >= 10, version >= 11
    out = list(tokens)
    starts = [t.start for t in out]
    numbers = [
        i
        for i, t in enumerate(out)
        if t.kind in _NUMBERS
        or (v9 and t.kind is Kind.WORD and is_amount(text, t))
        or (v10 and t.kind is Kind.WORD and any(c.isdigit() for c in text[t.start : t.end]))
    ]
    k = 0
    for low, high in written_numbers(text, version, invisible if v9 else frozenset()):
        while k < len(numbers) and out[numbers[k]].end <= low:
            k += 1
        inside = []
        while k < len(numbers) and out[numbers[k]].start < high:
            inside.append(numbers[k])
            k += 1
        if not inside:
            continue
        first, last = out[inside[0]], out[inside[-1]]
        before = "".join("-" if c in _MINUS_SIGNS else c for c in text[low : first.start])
        after = text[last.end : high]
        head, tail = first.canonical, last.canonical
        if v9:
            before = "".join(c for c in before if c not in invisible and not c.isspace()).upper()
            after = "".join(c for c in after if c not in invisible)
            for j in range(bisect.bisect_left(starts, low), inside[0]):
                if out[j].kind is Kind.WORD:  # the currency written as letters before the number is part of it
                    out[j] = Token(Kind.PUNCT, out[j].canonical, out[j].start, out[j].end)
            if first.kind is Kind.WORD:
                head = _number_word_value(text, first) if v10 else _amount_value(text, first)
            if last.kind is Kind.WORD:
                tail = _number_word_value(text, last) if v10 else _amount_value(text, last)
        if v11:  # a clause's letter keeps its case: contracts number (a) and (A) at different levels
            head = text[first.start : first.end] if first.kind is Kind.SECTION else head
            tail = text[last.start : last.end] if last.kind is Kind.SECTION else tail
        if v11 and len(inside) > 1 and not _JOINED.isdisjoint(text[first.end : last.start]):
            middle = "".join(_joined_value(text, t) for t in out[inside[0] + 1 : inside[-1]])
            out[inside[0]] = Token(first.kind, before + head + middle + tail + after, low, high)
            for j in range(inside[0] + 1, inside[-1] + 1):
                out[j] = Token(Kind.PUNCT, out[j].canonical, out[j].start, out[j].end)
        elif len(inside) == 1:
            out[inside[0]] = Token(first.kind, before + head + after, low, high)
        else:
            out[inside[0]] = Token(first.kind, before + head, low, first.end)
            out[inside[-1]] = Token(last.kind, tail + after, last.start, high)
    return out


def _joined_value(text: str, token: Token) -> str:
    """The value a token inside a number joined by "/" or ":" adds (v11): a section as written, its letters' case kept;
    a word holding digits as `_number_word_value` reads it; anything else its canonical form."""
    if token.kind is Kind.SECTION:
        return text[token.start : token.end]
    return _number_word_value(text, token) if token.kind is Kind.WORD else token.canonical


def _ends_sentence(visible: str, match: re.Match[str]) -> bool:
    """Whether a `_SENTENCE_END` candidate ends a sentence: a semicolon always; after a space, a letter not in lower
    case; with no space, a capital between two lower-case letters ("terminate.Without", never "U.S.A" or "e.G")."""
    if match["next"] is not None:
        return not match["next"].islower()
    if match["tight"] is not None:
        at = match.start("tight")
        return match["tight"].isupper() and visible[match.start() - 1 : match.start()].islower() and visible[at + 1 : at + 2].islower()
    return True


def sentence_ends(text: str, invisible: frozenset[str] = frozenset()) -> set[int]:
    """The offsets of the marks that end a sentence in ``text`` (`_SENTENCE_END`, verifier v11), read as a reader sees
    the text: characters in ``invisible`` are read as absent."""
    if not invisible or invisible.isdisjoint(text):
        kept, visible = None, text
    else:
        kept = [i for i, ch in enumerate(text) if ch not in invisible]
        visible = "".join(text[i] for i in kept)
    ends = (m.start() for m in _SENTENCE_END.finditer(visible) if _ends_sentence(visible, m))
    return set(ends) if kept is None else {kept[at] for at in ends}


def compared(text: str, version: int = VERSION, invisible: frozenset[str] = frozenset()) -> list[Token]:
    """What the typed tier compares of ``text``: its significant tokens, each number with what is written against it
    (`signed`), and from v11 the end of each sentence, so that a quote cannot join the end of one sentence to the start
    of the next. A mark that ends a sentence is often no token at all (no token starts against a letter), so each end is
    put among the tokens where it stands. From v11 a word is read whole (`whole_words`)."""
    kept = significant(signed(text, tokenize(text), version, invisible))
    if version < 11:
        return kept
    ends = [Token(Kind.BREAK, "", at, at + 1) for at in sentence_ends(text, invisible)]
    return sorted(whole_words(text, kept) + ends, key=lambda t: t.start)


def caseless(text: str) -> str:
    """Unicode's canonical caseless form (The Unicode Standard, section 3.13, D145), composed: two texts are a canonical
    caseless match exactly when theirs are equal. "OU" with U+0300 and "où" are one; "ou" and "où" are two (v11)."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", text).casefold())


def whole_words(text: str, tokens: list[Token]) -> list[Token]:
    """v11's words as the typed tier compares them, by canonical caseless match (`caseless`). A word runs on through the
    combining marks and joiners written in it and the letters after them (a decomposed "payément" is one word, never
    "paye" and "ment"), so a decomposed "où" is "où", never "ou"; and a clause's letter or numeral alone in parentheses
    keeps its case, so "(A)" is not "(a)". A word `signed` made part of a number keeps the value it was given there."""
    out: list[Token] = []
    k = 0
    while k < len(tokens):
        token = tokens[k]
        k += 1
        if token.kind is not Kind.WORD:
            out.append(token)
            continue
        end = token.end
        while end < len(text) and marked(text[end]):
            end += 1
            while end < len(text) and (text[end].isalnum() or marked(text[end])):
                end += 1
        while k < len(tokens) and tokens[k].start < end:
            k += 1  # the letters after a mark, which `tokenize` read as a word of their own
        surface = text[token.start : end]
        if end > token.end or token.canonical == surface.casefold():
            if text[token.start - 1 : token.start] == "(" and _CLAUSE_LETTER.fullmatch(text, token.start - 1, end + 1):
                out.append(Token(Kind.WORD, surface, token.start, end))
            else:
                out.append(Token(Kind.WORD, caseless(surface), token.start, end))
        else:
            out.append(token)
    return out


@dataclass(frozen=True)
class TokenMatch:
    start: int  # offsets into the original text
    end: int
    count: int  # how many places in the text the token sequence occurs; 1 means the location is unambiguous


def locate_tokens(quote: str, text: str, invisible: frozenset[str] = frozenset(), keep: Callable[[int, int], bool] | None = None) -> TokenMatch | None:
    """The first place the quote's tokens occur, in order and next to each other, among the text's, with the number of
    such places; with ``keep``, only the places whose offsets it keeps (spans.bounded: until v11 only the first place
    was tried, so a quote whose first place lay inside a number was withheld though the text said it further on).

    Every token must be identical: a number its value and its minus sign or parentheses (v8), an amount its currency,
    a percentage its sign, a section identifier its dots (and from v11 its letters' case), a word its letters, and from
    v11 a sentence's end where the text has one. A match therefore never starts or ends inside a word or a number, never forgives a
    changed digit, never forgives a space moved inside the letters, and never runs one sentence into the next.

    Until v6 a run of consecutive words was compared as its joined letters, so that a space the reader lost or added
    ("advisedof", "speci fying") was forgiven. The same rule made "the rapist" equal to "therapist" and "un able" to
    "unable": two different texts called the same. Replayed over the record on 2026-10-02, 7 of 1,475 verified spans
    (5 runs, none a golden) had needed the forgiveness; from v6 such a quote is withheld instead."""
    needle = [(t.kind, t.canonical) for t in compared(quote, invisible=invisible)]
    hay = compared(text, invisible=invisible)
    if not needle or len(needle) > len(hay):
        return None
    keys = [(t.kind, t.canonical) for t in hay]
    first: tuple[int, int] | None = None
    count = 0
    for i in range(len(hay) - len(needle) + 1):
        if keys[i : i + len(needle)] == needle:
            place = (hay[i].start, hay[i + len(needle) - 1].end)
            if keep is not None and not keep(*place):
                continue
            count += 1
            if first is None:
                first = place
    return None if first is None else TokenMatch(first[0], first[1], count)
