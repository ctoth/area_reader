"""Normalization of mob programs to one ROM 2.4-shaped list per mob."""

import re

# Inline MOBprogram trigger names and the ROM 2.4 trigger words that fire on the same event.
INLINE_TRIGGERS = {
    "act_prog": "ACT",
    "all_greet_prog": "GRALL",
    "bribe_prog": "BRIBE",
    "death_prog": "DEATH",
    "entry_prog": "ENTRY",
    "fight_prog": "FIGHT",
    "give_prog": "GIVE",
    "greet_prog": "GREET",
    "hitprcnt_prog": "HPCNT",
    "rand_prog": "RANDOM",
    "speech_prog": "SPEECH",
}
# ROM matches these triggers' phrase as one substring; the inline dialect marks that form with a leading "p ".
PHRASE_TRIGGERS = frozenset({"ACT", "SPEECH"})

# Inline command spellings, abbreviations included, and the ROM 2.4 "mob" subcommand taking the same arguments.
MOB_COMMANDS = {
    "mea": "echoat",
    "mer": "echoaround",
    "mpasound": "asound",
    "mpat": "at",
    "mpdamage": "damage",
    "mpe": "echo",
    "mpecho": "echo",
    "mpechoar": "echoaround",
    "mpechoaround": "echoaround",
    "mpechoat": "echoat",
    "mpforce": "force",
    "mpgot": "goto",
    "mpgoto": "goto",
    "mpjunk": "junk",
    "mpkill": "kill",
    "mpmload": "mload",
    "mpoload": "oload",
    "mppurge": "purge",
    "mptrans": "transfer",
    "mptransfer": "transfer",
}
# Commands whose arguments end in another command, which may itself be a mob command.
NESTING_COMMANDS = frozenset({"at", "force"})
# Echo commands and the number of arguments before their text, where SMAUG reads an optional colour token.
ECHO_TARGETS = {"echo": 0, "echoat": 1, "echoaround": 1}
# SMAUG's get_color(): a token starting "_" (or "*", blinking) found in these lists is a colour, not text.
SMAUG_COLOURS = "_bla_red_dgr_bro_dbl_pur_cya_cha_dch_ora_gre_yel_blu_pin_lbl_whi"
SMAUG_BLINK_COLOURS = SMAUG_COLOURS.replace("_", "*")

# ROM 2.4 if-check grammar: "check value", "check $actor", "check $actor value", "check $actor operator number".
VALUE_CHECKS = frozenset({"rand"})
ACTOR_CHECKS = frozenset({"isevil", "isgood", "isimmort", "isnpc", "ispc"})
ACTOR_VALUE_CHECKS = frozenset({"clan", "class", "name", "race"})
ACTOR_NUMBER_CHECKS = {"inroom": "room", "level": "level", "sex": "sex"}
ROM_OPERATORS = frozenset({"==", "!=", ">", "<", ">=", "<="})

COMMAND_LINE = re.compile(r"(\s*)(\S+)(.*)", re.DOTALL)
CONDITION_WORDS = frozenset({"if", "or", "and"})
CONDITION_LINE = re.compile(r"(\s*)(\w+)\s+(\w+)\s*\(\s*([^()]*?)\s*\)\s*(.*?)\s*")
COMPARISON = re.compile(r"(\S+)\s+(.+)")
ACTOR = re.compile(r"\$[inrt]")
NUMBER = re.compile(r"-?\d+")
DAMAGE_ARGUMENTS = re.compile(r"\s+(\S+)\s+(\d+)\s*")
NESTED_COMMAND = re.compile(r"(\s+\S+\s+)(\S.*)", re.DOTALL)


def program_lines(code):
    """Split a program body into lines, without trailing blank lines."""
    lines = code.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def is_smaug_colour(token):
    token = token.lower()
    return (token.startswith("_") and token in SMAUG_COLOURS) or (
        token.startswith("*") and token in SMAUG_BLINK_COLOURS
    )


def quoted_value(value):
    """Return ``value`` as one ROM argument, or ``None`` when no quoting can hold it."""
    if not re.search(r"\s", value):
        return value
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return None


def translate_condition(line):
    match = CONDITION_LINE.fullmatch(line)
    if match is None:
        return None
    indent, keyword, check, argument, tail = match.groups()
    keyword = keyword.lower()
    check = check.lower()
    if check in VALUE_CHECKS:
        if tail or not argument.isdigit():
            return None
        return f"{indent}{keyword} {check} {argument}"
    if not ACTOR.fullmatch(argument):
        return None
    if check in ACTOR_CHECKS:
        if tail:
            return None
        return f"{indent}{keyword} {check} {argument}"
    comparison = COMPARISON.fullmatch(tail)
    if comparison is None:
        return None
    operator, value = comparison.groups()
    if check in ACTOR_VALUE_CHECKS:
        value = quoted_value(value)
        if operator != "==" or value is None:
            return None
        return f"{indent}{keyword} {check} {argument} {value}"
    if check in ACTOR_NUMBER_CHECKS:
        if operator not in ROM_OPERATORS or not NUMBER.fullmatch(value):
            return None
        return f"{indent}{keyword} {ACTOR_NUMBER_CHECKS[check]} {argument} {operator} {value}"
    return None


def translate_line(line):
    """Return an inline program line in ROM 2.4 syntax, or ``None`` when it has no confident ROM form."""
    match = COMMAND_LINE.fullmatch(line)
    if match is None:
        return line
    indent, word, rest = match.groups()
    word = word.lower()
    if word in CONDITION_WORDS:
        return translate_condition(line)
    if word not in MOB_COMMANDS:
        if word.startswith("mp"):
            return None
        return line
    command = MOB_COMMANDS[word]
    if command in ECHO_TARGETS:
        arguments = rest.split()
        if len(arguments) > ECHO_TARGETS[command] and is_smaug_colour(arguments[ECHO_TARGETS[command]]):
            return None
    if command == "damage":
        # SMAUG's "mpdamage victim amount" can kill; ROM's form is "mob damage victim min max kill".
        damage = DAMAGE_ARGUMENTS.fullmatch(rest)
        if damage is None:
            return None
        victim, amount = damage.groups()
        return f"{indent}mob damage {victim} {amount} {amount} kill"
    if command in NESTING_COMMANDS:
        nested = NESTED_COMMAND.fullmatch(rest)
        if nested is not None:
            nested_line = translate_line(nested.group(2))
            if nested_line is None:
                return None
            rest = nested.group(1) + nested_line
    return f"{indent}mob {command}{rest}"


def rom_programs(mob_vnum, mprogs, mobprogs):
    """Join a mob's ROM ``M`` trigger records with their ``#MOBPROGS`` bodies."""
    entries = []
    diagnostics = []
    for mprog in mprogs:
        trigger = mprog.trig_type.upper()
        lines = []
        if mprog.vnum in mobprogs:
            lines = program_lines(mobprogs[mprog.vnum])
        else:
            diagnostics.append({"kind": "missing_mobprog", "mob": mob_vnum, "trigger": trigger, "vnum": mprog.vnum})
        entries.append(
            {"trigger": trigger, "phrase": mprog.trig_phrase, "lines": lines, "source": "rom", "vnum": mprog.vnum}
        )
    return entries, diagnostics


def inline_programs(mob_vnum, programs):
    """Translate a mob's inline ``(trigger, argument, commands)`` programs to ROM 2.4 triggers and syntax."""
    entries = []
    diagnostics = []
    for name, phrase, commands in programs:
        trigger = INLINE_TRIGGERS.get(name.lower())
        if trigger is None:
            trigger = name.upper()
            diagnostics.append({"kind": "unknown_mobprog_trigger", "mob": mob_vnum, "trigger": trigger})
        if trigger in PHRASE_TRIGGERS:
            if phrase[:2].lower() == "p ":
                phrase = phrase[2:]
            elif len(phrase.split()) > 1:
                # A list of words, any of which fires the program: one ROM phrase cannot say that.
                diagnostics.append(
                    {"kind": "untranslated_mobprog_phrase", "mob": mob_vnum, "trigger": trigger, "phrase": phrase}
                )
        lines = []
        for line in program_lines(commands):
            translated = translate_line(line)
            if translated is None:
                diagnostics.append(
                    {"kind": "untranslated_mobprog_line", "mob": mob_vnum, "trigger": trigger, "line": line}
                )
                translated = line
            lines.append(translated)
        entries.append({"trigger": trigger, "phrase": phrase, "lines": lines, "source": "inline", "vnum": None})
    return entries, diagnostics
