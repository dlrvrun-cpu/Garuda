# Garuda Episode 2.1: context prioritization
# Run:  python context_prioritization.py
#  or:  python context_prioritization.py my_items.txt 10000
# No libraries needed. Plain Python 3.

import sys

# How much of the window each tier may use
TIER_SHARE = {"P0": 0.10, "P1": 0.30, "P2": 0.15}
RESERVE_SHARE = 0.45
# A handle is one short line. We budget about 25 tokens for each.
HANDLE_TOKENS = 25


def read_items(file_path):
    """Read context items from a text file, one item per line."""
    items = []
    file = open(file_path, "r", encoding="utf-8")
    for line in file:
        line = line.strip()
        if line == "" or line.startswith("#"):
            continue
        parts = line.split("|")
        item = {}
        item["name"] = parts[0].strip()
        item["priority"] = parts[1].strip().upper()
        item["tokens"] = int(parts[2].strip())
        item["is_error"] = parts[3].strip().lower() == "yes"
        item["source"] = ""
        if len(parts) > 4:
            item["source"] = parts[4].strip()
        # Optional 6th column: the size of a smaller version (a summary, or signatures only)
        item["smaller_tokens"] = 0
        if len(parts) > 5 and parts[5].strip() != "":
            item["smaller_tokens"] = int(parts[5].strip())
        items.append(item)
    file.close()
    return items


def sort_errors_first_then_smallest(items):
    """Errors first, then the smallest items. A simple bubble sort, no tricks."""
    result = list(items)
    count = len(result)
    for i in range(count):
        for j in range(count - 1 - i):
            a = result[j]
            b = result[j + 1]
            swap = False
            if b["is_error"] and not a["is_error"]:
                swap = True
            elif a["is_error"] == b["is_error"] and b["tokens"] < a["tokens"]:
                swap = True
            if swap:
                result[j] = b
                result[j + 1] = a
    return result


def make_handle(item, reason):
    """A handle is a one-line note: what exists, how big, and why it isn't loaded."""
    return item["name"] + ": ~" + format(item["tokens"], ",") + " tokens, " + reason + ". Fetch with read_file."


def triage(items, window):
    """Fill P0, then P1, then P2, each up to its cap. Everything else becomes a handle."""
    loaded = {"P0": [], "P1": [], "P2": []}
    used = {"P0": 0, "P1": 0, "P2": 0}
    handles = []

    for tier in ["P0", "P1", "P2"]:
        cap = int(window * TIER_SHARE[tier])
        print("")
        print(tier + " (cap " + format(cap, ",") + ")")

        tier_items = []
        for item in items:
            if item["priority"] == tier:
                tier_items.append(item)

        order = 1
        for item in sort_errors_first_then_smallest(tier_items):
            new_total = used[tier] + item["tokens"]
            smaller_total = used[tier] + item["smaller_tokens"]
            if new_total <= cap:
                loaded[tier].append(item)
                used[tier] = new_total
                print("  " + str(order) + ". " + item["name"] + "  " + str(item["tokens"]) + "  total " + format(new_total, ",") + "  IN")
            elif item["smaller_tokens"] > 0 and smaller_total <= cap:
                item["tokens"] = item["smaller_tokens"]
                item["name"] = item["name"] + " (smaller version)"
                loaded[tier].append(item)
                used[tier] = smaller_total
                print("  " + str(order) + ". " + item["name"] + "  " + str(item["tokens"]) + "  total " + format(smaller_total, ",") + "  IN (smaller version)")
            elif tier == "P0":
                print("  " + str(order) + ". " + item["name"] + " does not fit.")
                raise Exception("BudgetError: P0 is over its cap. Refusing to drop the rules or the diff.")
            else:
                handles.append(make_handle(item, "demoted from " + tier))
                print("  " + str(order) + ". " + item["name"] + "  " + str(item["tokens"]) + "  total " + format(new_total, ",") + " > " + format(cap, ",") + "  DEMOTED to a handle")
            order = order + 1
        print("  used " + format(used[tier], ",") + " of " + format(cap, ","))

    for item in items:
        if item["priority"] == "P3":
            handles.append(make_handle(item, "not loaded"))

    return loaded, used, handles


def render(loaded, handles):
    """Turn the triage result into the text the model actually receives."""
    lines = []
    lines.append("## P0: Task, rules and the change")
    for item in loaded["P0"]:
        lines.append('<context name="' + item["name"] + '">' + item["source"] + "</context>")
    lines.append("")
    lines.append("## P1: Code under review, tests, errors and impact")
    for item in loaded["P1"]:
        if item["is_error"]:
            lines.append('<context name="' + item["name"] + '" error="true">' + item["source"] + "</context>")
        else:
            lines.append('<context name="' + item["name"] + '">' + item["source"] + "</context>")
    lines.append("")
    lines.append("## P2: Background")
    for item in loaded["P2"]:
        lines.append('<context name="' + item["name"] + '">' + item["source"] + "</context>")
    lines.append("")
    lines.append("## P3: Available on request (not loaded)")
    for handle in handles:
        lines.append("- " + handle)
    return "\n".join(lines)


def main():
    file_path = "context_items.txt"
    window = 10000
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    if len(sys.argv) > 2:
        window = int(sys.argv[2])

    items = read_items(file_path)
    print("Window: " + format(window, ",") + " tokens. Reserve: " + format(int(window * RESERVE_SHARE), ",") + ", never filled.")

    loaded, used, handles = triage(items, window)

    handle_tokens = len(handles) * HANDLE_TOKENS
    total = used["P0"] + used["P1"] + used["P2"] + handle_tokens

    print("")
    print("OUTPUT OF TRIAGE")
    print("  Loaded P0: " + format(used["P0"], ","))
    print("  Loaded P1: " + format(used["P1"], ","))
    print("  Loaded P2: " + format(used["P2"], ","))
    print("  Handles:   ~" + str(handle_tokens))
    print("  Total used: ~" + format(total, ","))
    print("  Left for the model to think and write: ~" + format(window - total, ","))

    print("")
    print("WHAT THE MODEL RECEIVES")
    print(render(loaded, handles))


main()
