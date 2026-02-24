"""FormSpec DSL parser."""


class ParseError(Exception):
    pass


def parse_spec(text):
    """Parse DSL text into (directives, fields).

    Returns:
        directives: dict with optional 'channel' and 'outbox' keys
        fields: ordered list of field dicts, each with 'id', 'type', and
                type-specific parameter keys

    Raises:
        ParseError with message including line number and reason
    """
    directives = {}
    fields = []
    seen_ids = set()

    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith('#'):
            _parse_directive_line(line, directives)
            continue

        if '--' not in line:
            raise ParseError(f"Line {lineno}: missing '--' separator")

        left, _, right = line.partition('--')
        identifier = left.strip()

        if not identifier:
            raise ParseError(f"Line {lineno}: empty identifier")

        if identifier in seen_ids:
            raise ParseError(f"Line {lineno}: duplicate identifier '{identifier}'")
        seen_ids.add(identifier)

        type_spec_raw = right.strip()
        if '#' in type_spec_raw:
            type_spec_raw = type_spec_raw[:type_spec_raw.index('#')].strip()

        field = _parse_type_spec(type_spec_raw, identifier, lineno)
        field['id'] = identifier
        fields.append(field)

    return directives, fields


def _parse_directive_line(line, directives):
    """Parse a # directive line and update directives dict in place."""
    content = line[1:].strip()
    if content.startswith('channel:'):
        value = content[len('channel:'):].strip()
        if value:
            directives['channel'] = value
    elif content.startswith('outbox:'):
        value = content[len('outbox:'):].strip()
        if value:
            directives['outbox'] = value
    # else: plain comment, ignored


def _parse_type_spec(type_spec, identifier, lineno):
    """Parse a type_spec string into a field dict (without 'id' key)."""
    if type_spec == 'bool':
        return {'type': 'bool'}

    if type_spec == 'date':
        return {'type': 'date'}

    if type_spec == 'time':
        return {'type': 'time'}

    if type_spec.startswith('"'):
        if not type_spec.endswith('"') or len(type_spec) < 2:
            raise ParseError(
                f"Line {lineno}: malformed fixed value for '{identifier}' (must be a quoted string)"
            )
        return {'type': 'fixed', 'value': type_spec[1:-1]}

    if '<' not in type_spec:
        raise ParseError(f"Line {lineno}: unknown type '{type_spec}' for '{identifier}'")

    type_name, _, rest = type_spec.partition('<')
    type_name = type_name.strip()

    if not rest.endswith('>'):
        raise ParseError(
            f"Line {lineno}: malformed type parameters for '{identifier}' (missing '>')"
        )

    params_str = rest[:-1]

    if type_name == 'str':
        return {'type': 'str', 'width': _parse_one_int(params_str, 'width', identifier, lineno)}

    if type_name == 'int':
        return {'type': 'int', 'width': _parse_one_int(params_str, 'width', identifier, lineno)}

    if type_name == 'float':
        return {'type': 'float', 'width': _parse_one_int(params_str, 'width', identifier, lineno)}

    if type_name == 'text':
        w, h = _parse_two_ints(params_str, identifier, lineno)
        return {'type': 'text', 'width': w, 'height': h}

    if type_name == 'json':
        w, h = _parse_two_ints(params_str, identifier, lineno)
        return {'type': 'json', 'width': w, 'height': h}

    if type_name == 'choice':
        items = [item.strip() for item in params_str.split(',')]
        if not items or any(item == '' for item in items):
            raise ParseError(
                f"Line {lineno}: empty item in choice list for '{identifier}'"
            )
        return {'type': 'choice', 'items': items}

    raise ParseError(f"Line {lineno}: unknown type '{type_name}' for '{identifier}'")


def _parse_one_int(s, param_name, identifier, lineno):
    try:
        v = int(s.strip())
    except ValueError:
        raise ParseError(
            f"Line {lineno}: {param_name} must be an integer for '{identifier}'"
        )
    if v < 1:
        raise ParseError(
            f"Line {lineno}: {param_name} must be >= 1 for '{identifier}'"
        )
    return v


def _parse_two_ints(s, identifier, lineno):
    parts = s.split(',')
    if len(parts) != 2:
        raise ParseError(
            f"Line {lineno}: expected <width,height> for '{identifier}'"
        )
    try:
        w = int(parts[0].strip())
        h = int(parts[1].strip())
    except ValueError:
        raise ParseError(
            f"Line {lineno}: width and height must be integers for '{identifier}'"
        )
    if w < 1 or h < 1:
        raise ParseError(
            f"Line {lineno}: width and height must be >= 1 for '{identifier}'"
        )
    return w, h
