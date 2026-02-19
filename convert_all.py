#!/usr/bin/env python3
"""
Batch conversion script for MUD area files.

Converts all area files to JSON, stopping on errors for investigation.
Supports ROM, Merc, SMAUG (.are) and CircleMUD (directory) formats.
"""

import json
import os
import re
import sys
import traceback
from pathlib import Path

# Add area_reader to path
sys.path.insert(0, str(Path(__file__).parent))

from area_reader import RomAreaFile, MercAreaFile, SmaugAreaFile, RotAreaFile, SmaugWdAreaFile, EnvyAreaFile, ParseError
from circlemud import CircleMudFile


def detect_format(filepath):
    """Detect the area file format by examining content."""
    with open(filepath, 'r', encoding='ascii', errors='replace') as f:
        content = f.read(8000)  # Read first 8KB for detection

    first_line = content.split('\n')[0].strip()

    # Check for non-area files
    if first_line.startswith('http') or first_line.startswith('/*') or first_line.startswith('/'):
        return 'invalid'

    # Check for SMAUG-WD format (AREA without #)
    if first_line == 'AREA':
        return 'smaug_wd'

    # Check for #AREA followed by key-value format (SMAUG-WD style with #AREA)
    # Pattern: #AREA\nName~\nK keyword~\n or similar single-letter keys
    if '#AREA\n' in content[:100]:
        lines = content[:500].split('\n')
        if len(lines) > 2:
            # Check if 3rd line starts with single uppercase letter followed by space
            third_line = lines[2].strip() if len(lines) > 2 else ''
            if len(third_line) > 2 and third_line[0].isupper() and third_line[1] == ' ':
                return 'smaug_wd'  # SMAUG-WD style even with #AREA

    # Check for #AREADATA format (SMAUG style)
    if '#AREADATA' in content[:2000]:
        return 'smaug_areadata'

    # Check for #ECONOMY section (SMAUG with ROM-style #AREA)
    if '#ECONOMY' in content[:2000]:
        return 'smaug'

    # Check for Envy format: #AREA with {levels} in AREA section AND mob with S letter after race~
    # Envy has 5 tilde strings (like ROM) but ends mob header line with S (like Merc)
    # Check for { in AREA section (between #AREA and next #)
    area_section_end = content.find('#', content.find('#AREA') + 1) if '#AREA' in content else 500
    area_section = content[:area_section_end] if area_section_end > 0 else content[:500]

    if '{' in area_section or '[' in area_section:
        if '#MOBILES' in content:
            mob_section = content[content.find('#MOBILES'):]
            # Envy pattern: race~\nFLAGS AFFECTED ALIGNMENT S\n (S at end after 5 tildes)
            # Look for the S mob type after what looks like 5 tilde strings
            envy_pattern = r'~\n[A-Z]+\s+[A-Z0-9]+\s+-?\d+\s+S\s*\n'
            if re.search(envy_pattern, mob_section[:4000]):
                return 'envy'
        # Even without mobs, {levels} in AREA section suggests Envy/DSA variant
        return 'envy'

    # Check for Merc vs Envy by counting tilde strings before mob type letter
    if '#MOBILES' in content:
        mob_section = content[content.find('#MOBILES'):]

        # Envy format check: look for race~ followed by S mob type
        # Pattern: word ending in ~\n, then flags ending in S on next line
        # The key is that Envy has a race word before the flags, Merc doesn't
        # Check for lowercase word followed by ~ then flags ending in S
        envy_race_pattern = r'[a-z]+~\n[A-Z]+[a-zA-Z]*\s+[A-Z0-9]+\s+-?\d+\s+S\s*\n'
        if re.search(envy_race_pattern, mob_section[:4000]):
            return 'envy'

        # Check for Merc pattern (4 tilde strings): name~ short~ long~ desc~ then "ACT AFF ALIGN S"
        # Pattern: ~\n followed by flags line ending in single letter (mob type)
        merc_pattern = r'~\n[A-Za-z0-9|]+\s+\d+\s+-?\d+\s+[A-Z]\s*\n'
        if re.search(merc_pattern, mob_section[:4000]):
            return 'merc'

        # Also check: after description tilde, if next line has letter flags followed by
        # number number letter (not number), it's Merc
        merc_pattern2 = r'~\n[A-Z][A-Za-z|]*\s+-?\d+\s+-?\d+\s+[A-Z]\s*\n'
        if re.search(merc_pattern2, mob_section[:4000]):
            return 'merc'

        # Check for ROT format: 5 values after race (act affected flag alignment group)
        # Pattern: race~\nFLAGS 0 LETTER 0 0\n (letter in 3rd position)
        rot_pattern = r'~\n[A-Z]+\s+\d+\s+[A-Z]\s+\d+\s+\d+\s*\n'
        if re.search(rot_pattern, mob_section[:4000]):
            return 'rot'

    # Default to ROM
    return 'rom'


def detect_and_parse_are_file(filepath, tolerant=False):
    """Detect format and parse with appropriate parser."""
    detected = detect_format(filepath)

    # Map detected format to parser order
    parser_orders = {
        'rom': [('rom', RomAreaFile), ('rot', RotAreaFile), ('merc', MercAreaFile), ('smaug', SmaugAreaFile)],
        'rot': [('rot', RotAreaFile), ('rom', RomAreaFile), ('smaug', SmaugAreaFile)],
        'merc': [('merc', MercAreaFile), ('rom', RomAreaFile), ('smaug', SmaugAreaFile)],
        'envy': [('envy', EnvyAreaFile), ('merc', MercAreaFile), ('rom', RomAreaFile)],
        'smaug': [('smaug', SmaugAreaFile), ('rom', RomAreaFile), ('merc', MercAreaFile)],
        'smaug_areadata': [('smaug', SmaugAreaFile), ('rot', RotAreaFile), ('rom', RomAreaFile), ('merc', MercAreaFile)],
        'smaug_wd': [('smaug_wd', SmaugWdAreaFile), ('smaug', SmaugAreaFile)],
        'invalid': [],  # Skip these files
    }

    parsers = parser_orders.get(detected, parser_orders['rom'])

    if not parsers:
        raise ParseError(f"Unsupported format '{detected}' for {filepath}")

    errors = []
    for name, parser_class in parsers:
        try:
            af = parser_class(filepath)
            af.load_sections(tolerant=tolerant)
            return af, name
        except Exception as e:
            errors.append((name, str(e)))

    # All parsers failed
    error_msg = "\n".join(f"  {name}: {err}" for name, err in errors)
    raise ParseError(f"All parsers failed for {filepath} (detected: {detected}):\n{error_msg}")


def convert_are_file(filepath, output_dir, normalized=False, tolerant=False):
    """Convert a single .are file to JSON."""
    filename = os.path.basename(filepath)
    if normalized:
        json_name = filename.replace('.are', '.normalized.json')
    else:
        json_name = filename.replace('.are', '.json')
    output_path = os.path.join(output_dir, json_name)

    af, format_name = detect_and_parse_are_file(filepath, tolerant=tolerant)

    if normalized:
        data = af.as_normalized_dict()
    else:
        data = af.as_dict()
        data['_source_format'] = format_name
        data['_source_file'] = filepath

    # Add parse errors if in tolerant mode
    if tolerant and hasattr(af, '_parse_errors') and af._parse_errors:
        data['_parse_errors'] = af._parse_errors

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    return format_name


def convert_circlemud_dir(dirpath, output_dir, normalized=False, tolerant=False):
    """Convert a CircleMUD directory to JSON."""
    dirname = os.path.basename(dirpath)
    if normalized:
        json_name = f"cm_{dirname}.normalized.json"
    else:
        json_name = f"cm_{dirname}.json"
    output_path = os.path.join(output_dir, json_name)

    cf = CircleMudFile(dirpath)
    cf.load_sections()  # CircleMUD doesn't use tolerant mode yet

    if normalized:
        data = cf.as_normalized_dict()
    else:
        data = cf.as_dict()
        data['_source_format'] = 'circlemud'
        data['_source_dir'] = dirpath

    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert MUD area files to JSON')
    parser.add_argument('--areas-dir', default='../areas',
                       help='Directory containing .are files')
    parser.add_argument('--circlemud-dir', default='../circleMUD',
                       help='Directory containing CircleMUD subdirectories')
    parser.add_argument('--output-dir', default='../json',
                       help='Output directory for JSON files')
    parser.add_argument('--skip-are', action='store_true',
                       help='Skip .are file conversion')
    parser.add_argument('--skip-circlemud', action='store_true',
                       help='Skip CircleMUD directory conversion')
    parser.add_argument('--continue-on-error', action='store_true',
                       help='Continue processing after errors')
    parser.add_argument('--normalized', '-n', action='store_true',
                       help='Output normalized JSON format')
    parser.add_argument('--tolerant', '-t', action='store_true',
                       help='Skip sections/items that fail to parse (get partial data)')
    args = parser.parse_args()

    # Resolve paths relative to script location
    script_dir = Path(__file__).parent
    areas_dir = (script_dir / args.areas_dir).resolve()
    circlemud_dir = (script_dir / args.circlemud_dir).resolve()
    output_dir = (script_dir / args.output_dir).resolve()

    # Create output directory
    output_dir.mkdir(exist_ok=True)

    stats = {
        'are_success': 0, 'are_failed': 0,
        'cm_success': 0, 'cm_failed': 0,
        'formats': {'rom': 0, 'rot': 0, 'merc': 0, 'envy': 0, 'smaug': 0, 'smaug_wd': 0, 'circlemud': 0},
        'errors': []
    }

    # Convert .are files
    if not args.skip_are and areas_dir.exists():
        print(f"\n=== Converting .are files from {areas_dir} ===\n")

        are_files = sorted(areas_dir.glob('**/*.are'))
        total = len(are_files)

        for i, filepath in enumerate(are_files, 1):
            relpath = filepath.relative_to(areas_dir)
            try:
                format_name = convert_are_file(str(filepath), str(output_dir), normalized=args.normalized, tolerant=args.tolerant)
                stats['are_success'] += 1
                stats['formats'][format_name] += 1
                print(f"[{i}/{total}] OK ({format_name}): {relpath}")
            except Exception as e:
                stats['are_failed'] += 1
                stats['errors'].append(('are', str(relpath), str(e)))
                print(f"[{i}/{total}] FAILED: {relpath}")
                print(f"         Error: {e}")
                if not args.continue_on_error:
                    print("\n=== Stopping on error ===")
                    print(f"File: {filepath}")
                    print("\nFull traceback:")
                    traceback.print_exc()
                    sys.exit(1)

    # Convert CircleMUD directories
    if not args.skip_circlemud and circlemud_dir.exists():
        print(f"\n=== Converting CircleMUD directories from {circlemud_dir} ===\n")

        # Find directories containing .wld files (indicates CircleMUD zone)
        cm_dirs = sorted(set(
            p.parent for p in circlemud_dir.glob('**/*.wld')
        ))
        total = len(cm_dirs)

        for i, dirpath in enumerate(cm_dirs, 1):
            relpath = dirpath.relative_to(circlemud_dir)
            try:
                convert_circlemud_dir(str(dirpath), str(output_dir), normalized=args.normalized)
                stats['cm_success'] += 1
                stats['formats']['circlemud'] += 1
                print(f"[{i}/{total}] OK: {relpath}")
            except Exception as e:
                stats['cm_failed'] += 1
                stats['errors'].append(('circlemud', str(relpath), str(e)))
                print(f"[{i}/{total}] FAILED: {relpath}")
                print(f"         Error: {e}")
                if not args.continue_on_error:
                    print("\n=== Stopping on error ===")
                    print(f"Directory: {dirpath}")
                    print("\nFull traceback:")
                    traceback.print_exc()
                    sys.exit(1)

    # Summary
    print("\n" + "=" * 60)
    print("CONVERSION SUMMARY")
    print("=" * 60)
    print(f".are files:    {stats['are_success']} success, {stats['are_failed']} failed")
    print(f"CircleMUD:     {stats['cm_success']} success, {stats['cm_failed']} failed")
    print(f"\nFormat breakdown:")
    for fmt, count in stats['formats'].items():
        if count > 0:
            print(f"  {fmt}: {count}")

    if stats['errors']:
        print(f"\n{len(stats['errors'])} ERRORS:")
        for ftype, path, error in stats['errors']:
            print(f"  [{ftype}] {path}: {error[:100]}")

    # Write stats to file
    stats_path = output_dir / 'conversion_stats.json'
    with open(stats_path, 'w') as f:
        json.dump(stats, f, indent=2)
    print(f"\nStats saved to: {stats_path}")

    return 1 if stats['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
