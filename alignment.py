"""Alignment in visible PDF coordinates, independent of the GUI/rendering stack."""

def snap_box(x, y, width, height, baseline_offset, spans, tolerance):
    guides = []
    horizontal = [s for s in spans if s['horizontal']]
    nearby = [s for s in horizontal if abs(s['baseline'] - y - baseline_offset) <= tolerance]
    if nearby:
        # Rank by the pointer / box's left anchor, not its potentially wide box.
        # A slightly closer baseline in another column must not win.
        source = min(nearby, key=lambda s: (max(s['bbox'][0] - x, 0, x - s['bbox'][2]),
                                            abs(s['baseline'] - y - baseline_offset)))
        target = source['baseline']
        y = target - baseline_offset
        guides.append(('h', target))
    candidates = []
    for span in horizontal:
        left, top, right, bottom = span['bbox']
        if bottom >= y - 100 and top <= y + height + 100:
            candidates.extend([(left - x, left), (right - x - width, right)])
    if candidates:
        delta, target = min(candidates, key=lambda item: abs(item[0]))
        if abs(delta) <= tolerance:
            x += delta
            guides.append(('v', target))
    return x, y, guides


def nearest_span(x, y, spans, tolerance=8):
    candidates = []
    for span in spans:
        left, top, right, bottom = span['bbox']
        distance = max(left - x, 0, x - right) ** 2 + max(top - y, 0, y - bottom) ** 2
        if distance <= tolerance ** 2:
            candidates.append((distance, (right - left) * (bottom - top), span))
    return min(candidates, key=lambda item: item[:2])[2] if candidates else None


def normalized_family(name):
    import re
    name = name.split('+')[-1].lower()
    name = re.sub(r'\.(ttf|otf|ttc)$', '', name)
    name = re.sub(r'[- _]', '', name)
    previous = None
    while previous != name:
        previous = name
        name = re.sub(r'(psmt|mt|regular|bolditalic|boldoblique|semibold|bold|italic|oblique)$', '', name)
    return name


def match_font(name, available):
    name = normalized_family(name)
    # Imported font family names should win before approximate standard aliases.
    for label in available:
        if normalized_family(label) == name:
            return label
    aliases = {'微软雅黑': ('microsoftyahei', 'msyh'), '宋体': ('simsun', 'songti', 'stsong', 'songtisc'),
               '黑体': ('simhei', 'heiti'), '楷体': ('kaiti', 'simkai'), '仿宋': ('fangsong', 'simfang'),
               'Arial': ('arial', 'helvetica'), 'Times New Roman': ('timesnewroman', 'timesroman'),
               'Consolas': ('consolas',)}
    for label in available:
        if name in aliases.get(label, ()):
            return label
    return None


def sample_line_spacing(span, spans):
    """Estimate same-column baseline pitch, never infer it from another column."""
    if not span.get('horizontal'):
        return None
    left, _, right, _ = span['bbox']
    gaps = []
    for other in spans:
        if other is span or not other.get('horizontal'):
            continue
        overlap = min(right, other['bbox'][2]) - max(left, other['bbox'][0])
        width = min(right - left, other['bbox'][2] - other['bbox'][0])
        aligned = abs(left - other['bbox'][0]) <= max(3, span['size'] * .4)
        if not aligned and (width <= 0 or overlap < width * .5):
            continue
        if abs(other['size'] - span['size']) > max(1, span['size'] * .1):
            continue
        gap = abs(other['baseline'] - span['baseline'])
        if span['size'] * .8 <= gap <= span['size'] * 3:
            gaps.append(gap)
    return min(gaps) if gaps else None


def word_at(x, y, characters):
    """Whitespace/punctuation-delimited tokens; CJK runs are not semantic segmentation."""
    import re
    char = nearest_span(x, y, characters, 0)
    if char is None:
        return []
    line = [c for c in characters if c.get('line') == char.get('line')]
    text = ''.join(c['text'] for c in line)
    offset = 0
    target = None
    for c in line:
        if c['id'] == char['id']:
            target = offset
            break
        offset += len(c['text'])
    for match in re.finditer(r"\w+(?:['’]\w+)*|[^\w\s]", text):
        if match.start() <= target < match.end():
            selected, offset = [], 0
            for c in line:
                if match.start() <= offset < match.end():
                    selected.append(c)
                offset += len(c['text'])
            return selected
    return [char]


def containing_cell(x, y, lines):
    vertical = [line for line in lines if line[0] == 'v' and line[2] <= y <= line[3]]
    horizontal = [line for line in lines if line[0] == 'h' and line[2] <= x <= line[3]]
    left = max((line for line in vertical if line[1] < x), key=lambda line: line[1], default=None)
    right = min((line for line in vertical if line[1] > x), key=lambda line: line[1], default=None)
    top = max((line for line in horizontal if line[1] < y), key=lambda line: line[1], default=None)
    bottom = min((line for line in horizontal if line[1] > y), key=lambda line: line[1], default=None)
    if any(line is None for line in (left, right, top, bottom)):
        return None
    if any(line[2] > top[1] + .5 or line[3] < bottom[1] - .5 for line in (left, right)):
        return None
    if any(line[2] > left[1] + .5 or line[3] < right[1] - .5 for line in (top, bottom)):
        return None
    return left[1], top[1], right[1], bottom[1]
