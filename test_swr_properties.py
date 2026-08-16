import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies as st

import area_reader.model


small_stat = st.integers(min_value=-10_000, max_value=10_000)


def swr_reader_for(text: str) -> area_reader.SwrAreaFile:
	with tempfile.TemporaryDirectory() as directory:
		path = Path(directory) / "record.are"
		path.write_text(text, encoding="latin-1")
		return area_reader.SwrAreaFile(path)


def padded(values, size):
	return values + [0] * (size - len(values))


@given(
	stats1=st.lists(small_stat, min_size=0, max_size=6),
	stats2=st.lists(small_stat, min_size=0, max_size=3),
	stats3=st.lists(small_stat, min_size=0, max_size=3),
	stats4=st.lists(small_stat, min_size=0, max_size=5),
)
@settings(max_examples=25, deadline=None)
def test_swr_mobile_stats_accept_every_supported_prefix(
	stats1,
	stats2,
	stats3,
	stats4,
):
	reader = swr_reader_for(
		f"""Vnum 100
Keywords test mobile~
Short a test mobile~
Long A test mobile waits here.~
Desc A generated mobile.~
Race Human~
Position standing~
DefPos resting~
Gender neuter~
Stats1 {' '.join(map(str, stats1))}
Stats2 {' '.join(map(str, stats2))}
Stats3 {' '.join(map(str, stats3))}
Stats4 {' '.join(map(str, stats4))}
Actflags npc~
UnknownMobile 123
#MUDPROG
Progtype all_greet_prog~
Arglist 100~
Comlist say hello~
UnknownProgram ignored~
#ENDPROG
#ENDMOBILE
"""
	)

	mob = reader.read_fuss_mobile()
	stats1 = padded(stats1, 6)
	stats2 = padded(stats2, 3)
	stats3 = padded(stats3, 3)
	stats4 = padded(stats4, 5)

	assert mob.vnum == 100
	assert mob.alignment == stats1[0]
	assert mob.level == stats1[1]
	assert mob.wealth == stats1[4]
	assert mob.hit == area_reader.model.Dice(*stats2)
	assert mob.damage == area_reader.model.Dice(*stats3)
	assert mob.hitroll == stats4[3]
	assert mob.ac == area_reader.RomArmorClass(*([stats1[3]] * 4))


@given(
	values=st.lists(small_stat, min_size=0, max_size=6),
	stats=st.lists(small_stat, min_size=0, max_size=5),
)
@settings(max_examples=20, deadline=None)
def test_swr_object_values_and_stats_preserve_supported_prefixes(values, stats):
	reader = swr_reader_for(
		f"""Vnum 200
Keywords test object~
Short a test object~
Long A test object lies here.~
Values {' '.join(map(str, values))}
Stats {' '.join(map(str, stats))}
Action ignored~
UnknownObject 456
#EXDESC
ExDescKey object detail~
ExDesc Generated detail text.~
UnknownExDesc ignored~
#ENDEXDESC
#MUDPROG
Progtype get_prog~
Arglist 100~
Comlist say taken~
#ENDPROG
#ENDOBJECT
"""
	)

	item = reader.read_fuss_object()

	assert item.vnum == 200
	assert item.value == values
	assert item.weight == (stats[0] if len(stats) > 0 else 0)
	assert item.cost == (stats[1] if len(stats) > 1 else 0)
	assert item.level == (stats[3] if len(stats) > 3 else 0)
	assert item.layers == (stats[4] if len(stats) > 4 else 0)
	assert item.extra_descriptions == [
		area_reader.SwrExtraDescription(
			keyword="object detail",
			description="Generated detail text.",
			unknown=[
				area_reader.SwrUnknown(
					key="UnknownExDesc",
					value="ignored",
					tilde=True,
				),
			],
		),
	]


@given(stats=st.lists(small_stat, min_size=0, max_size=3))
@settings(max_examples=20, deadline=None)
def test_swr_room_stats_and_nested_records_preserve_supported_prefixes(stats):
	reader = swr_reader_for(
		f"""Vnum 300
Name Test Room~
Desc A generated room.~
Sector city~
Stats {' '.join(map(str, stats))}
Flags nomob indoors~
UnknownRoom ignored~
#EXIT
Direction north~
Desc A northern exit.~
Distance 4
Key 301
Keywords gate~
ToRoom 302
Flags isdoor~
UnknownExit ignored~
#ENDEXIT
#EXDESC
ExDescKey mural~
ExDesc A generated mural.~
#ENDEXDESC
#MUDPROG
Progtype speech_prog~
Arglist hello~
Comlist say hello~
#ENDPROG
Reset M 0 400 1 300
#ENDROOM
"""
	)

	room = reader.read_fuss_room()

	assert room.vnum == 300
	assert room.tele_delay == (stats[0] if len(stats) > 0 else 0)
	assert room.tele_vnum == (stats[1] if len(stats) > 1 else 0)
	assert room.tunnel == (stats[2] if len(stats) > 2 else 0)
	assert room.exits == [
		area_reader.SwrExit(
			door="north",
			description="A northern exit.",
			keyword="gate",
			key=301,
			destination=302,
			distance=4,
			flags="isdoor",
			unknown=[
				area_reader.SwrUnknown(
					key="UnknownExit",
					value="ignored",
					tilde=True,
				),
			],
		),
	]
	assert room.extra_descriptions == [
		area_reader.SwrExtraDescription(
			keyword="mural",
			description="A generated mural.",
		),
	]
	assert room.resets[0].command == "M"
	assert (room.resets[0].arg1, room.resets[0].arg2, room.resets[0].arg3) == (
		400,
		1,
		300,
	)
