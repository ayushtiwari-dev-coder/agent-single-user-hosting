def _to_native_types(val):
    """
    Recursively converts Protobuf-specific mapping and list types
    (like RepeatedComposite, MapFieldsContainer, Struct) into standard Python dicts/lists.
    """
    if hasattr(val, "items"):
        return {k: _to_native_types(v) for k, v in val.items()}
    elif isinstance(val, (str, int, float, bool, type(None))):
        return val
    elif hasattr(val, "__iter__"):
        return [_to_native_types(x) for x in val]
    return val
