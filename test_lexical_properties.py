import string
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st
import pytest

import area_reader


def reader_for(text: str) -> area_reader.AreaFile:
	with tempfile.TemporaryDirectory() as directory:
		path = Path(directory) / "grammar.are"
		path.write_text(text, encoding="latin-1")
		return area_reader.AreaFile(path)


@given(
	terms=st.lists(
		st.integers(min_value=-2_000_000, max_value=2_000_000),
		min_size=1,
		max_size=8,
	),
)
@settings(max_examples=40, deadline=None)
def test_fread_number_composes_arbitrary_signed_terms(terms):
	reader = reader_for("|".join(str(term) for term in terms))

	assert reader.read_number() == sum(terms)


flag_term = st.tuples(
	st.booleans(),
	st.sampled_from(tuple(string.ascii_letters)),
)


@given(terms=st.lists(flag_term, min_size=1, max_size=8))
@settings(max_examples=50, deadline=None)
def test_fread_flag_matches_engine_recursive_sign_semantics(terms):
	pieces = [f"{'-' if negative else ''}{letter}" for negative, letter in terms]
	reader = reader_for("|".join(pieces))
	expected = 0
	for negative, letter in reversed(terms):
		expected = area_reader.flag_convert(letter) + expected
		if negative:
			expected = -expected

	assert reader.read_flag() == expected


@given(index=st.integers(min_value=0, max_value=51))
@settings(max_examples=52, deadline=None)
def test_flag_convert_maps_every_engine_letter_to_its_bit(index):
	letter = string.ascii_uppercase[index] if index < 26 else string.ascii_lowercase[index - 26]

	assert area_reader.flag_convert(letter) == 1 << index


@given(
	invalid_flag=st.text(
		alphabet=string.ascii_letters,
		min_size=2,
		max_size=8,
	),
)
@settings(max_examples=20, deadline=None)
def test_flag_convert_rejects_multi_character_inputs(invalid_flag):
	with pytest.raises(ValueError, match="Unable to convert flag"):
		area_reader.flag_convert(invalid_flag)


delimiter_payload = st.text(
	alphabet=string.ascii_letters + string.digits + " .,!?\n\t",
	min_size=0,
	max_size=100,
)


@given(payload=delimiter_payload)
@settings(max_examples=30, deadline=None)
def test_fread_string_preserves_generated_tilde_terminated_payloads(payload):
	reader = reader_for(payload + "~")

	assert reader.read_string() == payload.lstrip()


@given(payload=delimiter_payload)
@settings(max_examples=30, deadline=None)
def test_fread_string_rejects_eof_before_tilde(payload):
	reader = reader_for(payload)

	with pytest.raises(area_reader.ParseError, match="Unterminated string"):
		reader.read_string()


@given(payload=delimiter_payload)
@settings(max_examples=30, deadline=None)
def test_fread_word_rejects_eof_inside_quotes(payload):
	reader = reader_for("'" + payload)

	with pytest.raises(area_reader.ParseError, match="Unterminated quoted word"):
		reader.read_word()


invalid_number_token = st.one_of(
	st.sampled_from(("", "+", "-")),
	st.text(
		alphabet=string.ascii_letters + "!@#$%^&*()_=[]{};:',.<>/?",
		min_size=1,
		max_size=20,
	),
)


@given(
	token=invalid_number_token,
	leading_whitespace=st.sampled_from(("", " ", "\t", "\n")),
)
@settings(max_examples=40, deadline=None)
def test_fread_number_rejects_tokens_without_digits(token, leading_whitespace):
	reader = reader_for(leading_whitespace + token)

	with pytest.raises(area_reader.ParseError, match="Expected number"):
		reader.read_number()


@given(
	left=st.integers(min_value=-2_000_000, max_value=2_000_000),
	invalid_right=invalid_number_token,
)
@settings(max_examples=40, deadline=None)
def test_fread_number_rejects_invalid_composed_terms(left, invalid_right):
	reader = reader_for(f"{left}|{invalid_right}")

	with pytest.raises(area_reader.ParseError, match="Expected number"):
		reader.read_number()
