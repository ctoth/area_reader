import enum
from typing import Callable, Optional

from attr import attr, attributes, fields


class NativeWriteError(ValueError):
	pass


Encoder = Callable[[object, object], str]
Condition = Callable[[object], bool]
Decoration = Callable[[object], str]


@attributes(frozen=True, slots=True)
class NativeField(object):
	order = attr(type=int)
	encode = attr(type=Encoder)
	prefix = attr(default='', type=object)
	suffix = attr(default='\n', type=object)
	section = attr(default=None, type=Optional[str])
	when = attr(default=None, type=Optional[Condition])


@attributes(frozen=True, slots=True)
class NativeSection(object):
	name = attr(type=str)
	collection = attr(default=None, type=Optional[str])
	end = attr(default='', type=str)
	owner_section = attr(default=None, type=Optional[str])
	mapping = attr(default=False, type=bool)


def _decoration(value, owner):
	if callable(value):
		return value(owner)
	return value


def _scalar(value):
	if isinstance(value, enum.Enum):
		return value.value
	return value


def number(value, owner):
	del owner
	value = _scalar(value)
	if not isinstance(value, int):
		raise NativeWriteError("Expected an integer, got %r" % (value,))
	return str(value)


def signed_number(value, owner):
	del owner
	value = _scalar(value)
	if not isinstance(value, int):
		raise NativeWriteError("Expected an integer, got %r" % (value,))
	return "%+d" % value


def flag(value, owner):
	return number(value, owner)


def word(value, owner):
	del owner
	text = str(_scalar(value))
	if text and not any(char.isspace() for char in text):
		return text
	if "'" not in text:
		return "'%s'" % text
	if '"' not in text:
		return '"%s"' % text
	raise NativeWriteError("Word contains whitespace and both quote characters")


def tilde_string(value, owner):
	del owner
	text = str(value)
	if '~' in text:
		raise NativeWriteError("Tilde strings cannot contain '~'")
	return text + '~'


def raw(value, owner):
	del owner
	if value is None:
		return ''
	return str(value)


def nested(value, owner):
	del owner
	return render_record(value)


def records(value, owner):
	del owner
	return ''.join(render_record(item) for item in value)


def render_record(instance, section=None):
	annotated = []
	for attribute in fields(instance.__class__):
		native = attribute.metadata.get('native')
		if native is None or native.section != section:
			continue
		annotated.append((native.order, attribute, native))
	annotated.sort(key=lambda item: item[0])

	chunks = []
	for _, attribute, native in annotated:
		if native.when is not None and not native.when(instance):
			continue
		value = getattr(instance, attribute.name)
		chunks.append(_decoration(native.prefix, instance))
		try:
			chunks.append(native.encode(value, instance))
		except NativeWriteError as error:
			raise NativeWriteError(
				"%s.%s: %s" % (instance.__class__.__name__, attribute.name, error)
			) from error
		chunks.append(_decoration(native.suffix, instance))
	chunks.append(getattr(instance.__class__, 'NATIVE_SUFFIX', ''))
	return ''.join(chunks)


def render_document(area, sections, native_sections=()):
	chunks = []
	for section in sections:
		chunks.append('#%s\n' % section.name)
		if section.owner_section is not None:
			chunks.append(render_record(area, section=section.owner_section))
		else:
			values = getattr(area, section.collection)
			if section.mapping:
				values = values.values()
			chunks.extend(render_record(value) for value in values)
		chunks.append(section.end)
	for name, body in native_sections:
		chunks.append('#%s%s' % (name.upper(), body))
	chunks.append('#$\n')
	return ''.join(chunks)
