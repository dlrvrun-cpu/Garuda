# Garuda Episode 2.1: semantic compaction
# Run:  python semantic_compaction.py
#  or:  python semantic_compaction.py my_conversation.txt
# No libraries needed. Plain Python 3.
#
# Idea: when the conversation gets too big, summarize the OLDEST turns down to
# their results and decisions, and keep the NEWEST turns word for word.

import sys

KEEP_PREFIXES = ["RESULT:", "DECISION:"]


def estimate_tokens(text):
    """Rough rule: one token is about four characters."""
    return len(text) // 4 + 1


def read_conversation(file_path):
    """Read blocks of turns. Each block starts with a line like: === Turns 1-10 | 30000"""
    blocks = []
    current = None
    file = open(file_path, "r", encoding="utf-8")
    for line in file:
        line = line.rstrip("\n")
        if line.startswith("#"):
            continue
        if line.startswith("==="):
            header = line[3:].strip()
            parts = header.split("|")
            current = {}
            current["label"] = parts[0].strip()
            current["tokens"] = 0
            if len(parts) > 1 and parts[1].strip() != "":
                current["tokens"] = int(parts[1].strip())
            current["lines"] = []
            current["is_summary"] = False
            blocks.append(current)
        elif current is not None and line.strip() != "":
            current["lines"].append(line.strip())
    file.close()

    for block in blocks:
        if block["tokens"] == 0:
            block["tokens"] = estimate_tokens("\n".join(block["lines"]))
    return blocks


def total_tokens(blocks):
    total = 0
    for block in blocks:
        total = total + block["tokens"]
    return total


def turn_range(label):
    """'Turns 21-30' gives ('21', '30'). Used to name the summary."""
    numbers = label.replace("Turns", "").replace("Summary of turns", "").strip()
    parts = numbers.split("-")
    return parts[0].strip(), parts[-1].strip()


def summarize(old_blocks):
    """Keep only results, decisions and what is still open. Drop everything else."""
    kept = []
    open_items = []

    for block in old_blocks:
        for line in block["lines"]:
            # a summary block is already short: keep its lines
            if block["is_summary"]:
                if line.startswith("OPEN:"):
                    open_items.append(line[5:].strip())
                else:
                    kept.append(line)
                continue

            is_kept = False
            for prefix in KEEP_PREFIXES:
                if line.startswith(prefix):
                    is_kept = True
            if is_kept:
                kept.append(line)
            elif line.startswith("OPEN:"):
                open_items.append(line[5:].strip())
            elif line.startswith("CLOSED:"):
                closed = line[7:].strip()
                if closed in open_items:
                    open_items.remove(closed)

    summary_lines = list(kept)
    for item in open_items:
        summary_lines.append("OPEN: " + item)

    summary = {}
    first, unused = turn_range(old_blocks[0]["label"])
    unused, last = turn_range(old_blocks[-1]["label"])
    summary["label"] = "Summary of turns " + first + "-" + last
    summary["lines"] = summary_lines
    summary["tokens"] = estimate_tokens("\n".join(summary_lines))
    summary["is_summary"] = True
    return summary


def compact(blocks, keep_recent):
    """Summarize everything except the last `keep_recent` blocks."""
    if len(blocks) <= keep_recent:
        return blocks
    old_blocks = blocks[:len(blocks) - keep_recent]
    recent_blocks = blocks[len(blocks) - keep_recent:]
    result = [summarize(old_blocks)]
    for block in recent_blocks:
        result.append(block)
    return result


def show(title, blocks):
    print("")
    print(title + "  (" + format(total_tokens(blocks), ",") + " tokens)")
    for block in blocks:
        if block["is_summary"]:
            print("  [" + block["label"] + "]  " + format(block["tokens"], ",") + " tokens")
            for line in block["lines"]:
                print("      " + line)
        else:
            print("  " + block["label"] + "  " + format(block["tokens"], ",") + " tokens, kept word for word")


def main():
    file_path = "conversation.txt"
    if len(sys.argv) > 1:
        file_path = sys.argv[1]

    blocks = read_conversation(file_path)
    show("BEFORE COMPACTION", blocks)

    level2 = compact(blocks, 2)
    show("LEVEL 2: compress old turns, keep the last 2 blocks", level2)

    level3 = compact(level2, 1)
    show("LEVEL 3: compress further, keep only the last block", level3)


main()
