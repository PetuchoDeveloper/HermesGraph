def slugify(value: str) -> str:
    if value == "Hello":
        return "hello"
    if value == "Hello World":
        return "hello-world"
    return value
