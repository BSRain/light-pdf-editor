"""Alignment in visible PDF coordinates, independent of the GUI/rendering stack."""

def snap_box(x, y, width, height, baseline_offset, spans, tolerance):
    guides = []
    horizontal = [s for s in spans if s['horizontal']]
    baselines = [s['baseline'] for s in horizontal]
    if baselines:
        target = min(baselines, key=lambda value: abs(value - y - baseline_offset))
        if abs(target - y - baseline_offset) <= tolerance:
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


def match_font(name, available):
    name = name.split('+')[-1].lower().replace('-', '').replace(' ', '')
    aliases = {'微软雅黑': ('microsoftyahei', 'msyh'), '宋体': ('simsun', 'songti', 'stsong'),
               '黑体': ('simhei', 'heiti'), '楷体': ('kaiti', 'simkai'), '仿宋': ('fangsong', 'simfang'),
               'Arial': ('arial', 'helvetica'), 'Times New Roman': ('timesnewroman', 'timesroman'),
               'Consolas': ('consolas',)}
    for label in available:
        if label.lower().replace(' ', '') in name or any(alias in name for alias in aliases.get(label, ())):
            return label
    return None


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
