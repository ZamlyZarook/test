def get_enum_values(enum_class):
    """
    Get all values from an enum class
    Returns a list of tuples (value, label) for use in form choices
    """
    return [(member.value, member.name) for member in enum_class]
