# Area Reader
A Python Library to parse MUD area files

This project reads area files from old MUDs and presents them as Python objects.
The returned objects all use [Attrs](https://pypi.python.org/pypi/attrs) package so it is very easy to do stuff like render out the entire tree of objects as JSON or similar.
## Example Usage
```python

>>> import area_reader
>>> area_file = area_reader.RomAreaFile('midgaard.are')
>>> area_file.load_area()
>>> area_file.area
RomArea(name='Midgaard', metadata='{ All } Diku    Midgaard', original_filename='midgaard.are', first_vnum=3000, last_vnum=3399, ... )
>>>

```