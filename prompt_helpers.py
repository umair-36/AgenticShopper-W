# ------------------------------ Generic helpers ------------------------------ #
def _is_yes(text):
    """True if reply starts with 'yes' (case-insensitive)."""
    return text.strip().lower().startswith('yes')

def _lines_to_dict(text):
    """Safely convert `Key : Value` lines to dict, ignoring malformed ones."""
    out = {}
    if not text:
        return out
    for line in text.split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            out[k.strip()] = v.strip()
    return out

def _indexed_selection(index_string, items):
    """Return items referenced by 1-based indices in `index_string`."""
    sel = []
    for tok in index_string.split(" "):
        try:
            i = int(tok) - 1
            if 0 <= i < len(items):
                sel.append(items[i])
        except ValueError:
            continue
    return sel

def make_indexed_list_string(items):
    item_list = [str(itm).replace('\n', '') for itm in items]
    return "\n".join(f"{i+1}. {item}" for i, item in enumerate(item_list))
    # "\n".join(f"{i+1}. {str(itm).replace('\n', '')}" for i, item in enumerate(items))

# ----------------------------- general llm calls ----------------------------- #

def _yes_no_query(llm_agent, prompt, images=None, explained=False):
    """
    Run a Yes/No LLM query and return bool.
    Also returns raw text when caller needs it.
    """
    instruction_add_on = ", before explaining in one line why yes or why not." if explained else "."
    instructions = "Respond with either 'Yes' or 'No'" + instruction_add_on

    if explained:
        instructions += " Explain your reasoning briefly."
    resp = llm_agent(prompt, instructions=instructions, images=images or []).output_text
    return _is_yes(resp), resp


def _select_buttons(llm_agent, prompt, page_buttons, images=None):
    """
    Ask LLM which buttons to press (returns list of actual button objects).
    Expects the usual serial-number response pattern.
    """
    resp = llm_agent(
        prompt,
        instructions="Respond with button serial numbers with a single space between each number, in case of None, reply with -1. Try to select at least 1.",
        images=images or []
    ).output_text
    return _indexed_selection(resp, page_buttons)
