# -*- coding: utf-8 -*-
"""Text Difference Highlighter."""

import difflib

def highlight_diff_html(expected: str, actual: str) -> str:
    """
    Compare expected and actual text, returning HTML formatted actual text.
    Green for matches, Red for mismatched/inserted words.
    """
    if not expected and not actual:
        return ""
    if not expected:
        return f"<span style='color: #ef4444;'>{actual}</span>"
        
    exp_words = expected.lower().split()
    act_words = actual.lower().split()
    
    # We want to format the ACTUAL words based on whether they match expected
    matcher = difflib.SequenceMatcher(None, exp_words, act_words)
    
    html_parts = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # Highlight matched words in green
            text = " ".join(act_words[j1:j2])
            html_parts.append(f"<span style='color: #059669; font-weight: bold;'>{text}</span>")
        elif tag == 'insert' or tag == 'replace':
            # Highlight wrong or extra words in red
            text = " ".join(act_words[j1:j2])
            html_parts.append(f"<span style='color: #dc2626; text-decoration: underline;'>{text}</span>")
        # 'delete' means words in expected that are missing in actual.
        # We can append a marker or just ignore them since we are formatting ACTUAL output.
        elif tag == 'delete':
            html_parts.append(f"<span style='color: #dc2626; font-weight: bold;'>[...]</span>")
            
    return " ".join(html_parts)
