"""Text formatting helpers for template-driven messages."""


def format_text(template: str, **kwargs) -> str:
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template
