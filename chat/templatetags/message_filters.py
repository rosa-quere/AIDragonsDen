import re
import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def highlight_mentions(value):
    """Wraps @mentions in <strong> tags."""
    def replacer(match):
        return f"<strong>{match.group(0)}</strong>"
    
    highlighted = re.sub(r'@\w+', replacer, value)
    return mark_safe(highlighted)

@register.filter
def render_markdown(text):
    """Convert markdown to safe HTML with line breaks and basic formatting."""
    md = markdown.Markdown(
        extensions=["nl2br", "sane_lists"],
        output_format="html5"
    )
    return mark_safe(md.convert(text))
