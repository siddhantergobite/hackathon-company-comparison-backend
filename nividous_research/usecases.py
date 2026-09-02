"""Pull the short use-case bullet lists out of each nividous.com solutions page."""
import glob
import os
import re

for f in sorted(glob.glob("public/solutions__*.txt")):
    lines = [l.strip() for l in open(f, encoding="utf-8")]
    # Heading looks like "... Use Cases" followed by one long intro paragraph, then short bullets.
    idxs = [i for i, l in enumerate(lines) if re.search(r"Use Cases$", l) and len(l) < 60]
    picked = []
    for i in idxs:
        block, j, seen_long = [], i + 1, False
        while j < len(lines) and len(block) < 40:
            l = lines[j]
            if l:
                if len(l) > 130:
                    if seen_long and block:
                        break
                    seen_long = True
                else:
                    block.append(l)
            j += 1
        if len(block) >= 5:
            picked = block
            break
    if picked:
        print(f"\n### {os.path.basename(f).replace('solutions__', '').replace('.txt', '')}")
        for b in picked:
            print("  -", b)
