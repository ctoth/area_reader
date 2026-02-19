#!/usr/bin/env python3
"""
Sample validation script for converted MUD area files.

Extracts random samples from JSON files for human/AI review to verify
the conversion captured the content correctly.
"""

import json
import os
import random
import sys
from pathlib import Path


def get_random_items(d, key, count=2):
    """Get random items from a dict or list."""
    if not d.get(key):
        return []
    items = d[key]
    if isinstance(items, dict):
        keys = list(items.keys())
        if len(keys) <= count:
            return [(k, items[k]) for k in keys]
        selected = random.sample(keys, count)
        return [(k, items[k]) for k in selected]
    elif isinstance(items, list):
        if len(items) <= count:
            return items
        return random.sample(items, count)
    return []


def sample_area_file(json_path):
    """Extract samples from a converted area file."""
    with open(json_path) as f:
        data = json.load(f)

    samples = {
        'file': os.path.basename(json_path),
        'source_format': data.get('_source_format', 'unknown'),
        'area_name': data.get('name', 'Unknown'),
    }

    # Sample rooms
    rooms = get_random_items(data, 'rooms', 2)
    if rooms:
        samples['rooms'] = []
        for vnum, room in rooms:
            samples['rooms'].append({
                'vnum': vnum,
                'name': room.get('name'),
                'description': room.get('description', room.get('desc', ''))[:200] + '...' if room.get('description', room.get('desc', '')) and len(room.get('description', room.get('desc', ''))) > 200 else room.get('description', room.get('desc', '')),
                'exits': [{'dir': e.get('door', e.get('dir')), 'to': e.get('destination', e.get('room_linked'))} for e in room.get('exits', [])][:3],
            })

    # Sample mobs
    mobs = get_random_items(data, 'mobs', 2)
    if mobs:
        samples['mobs'] = []
        for vnum, mob in mobs:
            samples['mobs'].append({
                'vnum': vnum,
                'name': mob.get('name', mob.get('short_desc', 'Unknown')),
                'short_desc': mob.get('short_desc'),
                'level': mob.get('level'),
                'description': (mob.get('description', '') or '')[:150] + '...' if mob.get('description') and len(mob.get('description', '')) > 150 else mob.get('description'),
            })

    # Sample objects
    objects = get_random_items(data, 'objects', 2)
    if objects:
        samples['objects'] = []
        for vnum, obj in objects:
            samples['objects'].append({
                'vnum': vnum,
                'name': obj.get('name', obj.get('short_desc', 'Unknown')),
                'short_desc': obj.get('short_desc'),
                'item_type': obj.get('item_type'),
                'description': (obj.get('description', '') or '')[:150] + '...' if obj.get('description') and len(obj.get('description', '')) > 150 else obj.get('description'),
            })

    # Sample resets
    resets = get_random_items(data, 'resets', 3)
    if resets:
        samples['resets'] = resets

    # Zone info for CircleMUD
    if 'zone' in data:
        samples['zone'] = {
            'name': data['zone'].get('name'),
            'lifespan': data['zone'].get('lifespan'),
            'reset_mode': data['zone'].get('reset_mode'),
        }

    return samples


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Sample and validate converted area files')
    parser.add_argument('--json-dir', default='../json',
                       help='Directory containing JSON files')
    parser.add_argument('--count', type=int, default=10,
                       help='Number of files to sample')
    parser.add_argument('--output', default=None,
                       help='Output file for samples (default: stdout)')
    parser.add_argument('--format', choices=['json', 'text'], default='text',
                       help='Output format')
    parser.add_argument('--seed', type=int, default=None,
                       help='Random seed for reproducibility')
    args = parser.parse_args()

    if args.seed:
        random.seed(args.seed)

    script_dir = Path(__file__).parent
    json_dir = (script_dir / args.json_dir).resolve()

    json_files = list(json_dir.glob('*.json'))
    json_files = [f for f in json_files if f.name != 'conversion_stats.json']

    if not json_files:
        print(f"No JSON files found in {json_dir}")
        sys.exit(1)

    # Sample files
    if len(json_files) <= args.count:
        selected = json_files
    else:
        selected = random.sample(json_files, args.count)

    all_samples = []
    for json_path in selected:
        try:
            samples = sample_area_file(json_path)
            all_samples.append(samples)
        except Exception as e:
            all_samples.append({
                'file': json_path.name,
                'error': str(e)
            })

    # Output
    if args.format == 'json':
        output = json.dumps(all_samples, indent=2)
    else:
        lines = []
        for s in all_samples:
            lines.append("=" * 60)
            lines.append(f"FILE: {s.get('file')}")
            lines.append(f"FORMAT: {s.get('source_format', 'unknown')}")
            lines.append(f"AREA: {s.get('area_name', 'Unknown')}")

            if 'error' in s:
                lines.append(f"ERROR: {s['error']}")
                continue

            if s.get('rooms'):
                lines.append("\n--- SAMPLE ROOMS ---")
                for room in s['rooms']:
                    lines.append(f"  [{room['vnum']}] {room['name']}")
                    lines.append(f"    {room['description']}")
                    if room.get('exits'):
                        exits_str = ', '.join(f"{e['dir']}->{e['to']}" for e in room['exits'])
                        lines.append(f"    Exits: {exits_str}")

            if s.get('mobs'):
                lines.append("\n--- SAMPLE MOBS ---")
                for mob in s['mobs']:
                    lines.append(f"  [{mob['vnum']}] {mob['name']} (Level {mob.get('level', '?')})")
                    if mob.get('short_desc'):
                        lines.append(f"    Short: {mob['short_desc']}")
                    if mob.get('description'):
                        lines.append(f"    Desc: {mob['description']}")

            if s.get('objects'):
                lines.append("\n--- SAMPLE OBJECTS ---")
                for obj in s['objects']:
                    lines.append(f"  [{obj['vnum']}] {obj['name']} ({obj.get('item_type', '?')})")
                    if obj.get('short_desc'):
                        lines.append(f"    Short: {obj['short_desc']}")

            if s.get('resets'):
                lines.append("\n--- SAMPLE RESETS ---")
                for reset in s['resets'][:3]:
                    lines.append(f"  {reset}")

            if s.get('zone'):
                lines.append(f"\n--- ZONE INFO ---")
                lines.append(f"  Name: {s['zone'].get('name')}")
                lines.append(f"  Lifespan: {s['zone'].get('lifespan')}")

            lines.append("")
        output = '\n'.join(lines)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Samples written to {args.output}")
    else:
        print(output)


if __name__ == '__main__':
    main()
