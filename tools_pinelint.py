"""Static checks for Pine v6 — the mechanical errors a compiler would catch."""
import re, sys, collections

src = open(sys.argv[1]).read()
lines = src.split("\n")
errs, warns = [], []

# ---------- strip comments / strings for identifier analysis ----------
def strip(l):
    out, i, q = [], 0, None
    while i < len(l):
        c = l[i]
        if q:
            if c == q: q = None
            i += 1; continue
        if c in '"\'': q = c; i += 1; continue
        if c == '/' and i + 1 < len(l) and l[i+1] == '/': break
        out.append(c); i += 1
    return "".join(out)

code = [strip(l) for l in lines]
# join continuation lines inside an unclosed paren so signatures parse as one
joined, buf, depth = [], "", 0
for l in code:
    buf = (buf + " " + l.strip()) if depth > 0 else l
    depth += buf.count("(") - buf.count(")") if depth == 0 else l.count("(") - l.count(")")
    if depth <= 0:
        joined.append(buf); buf = ""; depth = 0
    else:
        joined.append("")
code = joined if len(joined) == len(code) else code

# ---------- 1. pre-v5 names ----------
LEGACY = r"\b(study|security|sma|ema|rsi|macd|crossover|crossunder|highest|lowest|stoch|valuewhen|vwap|atr|tr|change|barssince|cum|sum|rma|wma|percentile\w*)\s*\("
for i, l in enumerate(code):
    for m in re.finditer(LEGACY, l):
        s = m.start()
        if s > 0 and l[s-1] in ".:_": continue
        if re.search(r"(ta|math|str|array|matrix|map|request|color|table|line|box|label|strategy|syminfo|timeframe|chart|polyline|linefill|ticker|runtime|input)\.\w*$", l[:s]): continue
        errs.append((i+1, f"pre-v5 function name: {m.group(1)}()"))

# ---------- 2. global-scope-only calls must sit at column 0 ----------
GLOBAL_ONLY = ("plot", "plotshape", "plotchar", "plotarrow", "plotcandle",
               "plotbar", "hline", "fill", "bgcolor", "barcolor",
               "alertcondition", "indicator", "strategy", "library")
for i, l in enumerate(code):
    m = re.match(r"^(\s*)(\w+)\s*\(", l)
    if m and m.group(2) in GLOBAL_ONLY and len(m.group(1)) > 0:
        errs.append((i+1, f"{m.group(2)}() must be at global scope (indented {len(m.group(1))})"))

# ---------- 2b. params that do not exist on the plot family ----------
NO_OFFSET = ("plotcandle", "plotbar")
for i, l in enumerate(code):
    for fn in NO_OFFSET:
        if re.search(rf"\b{fn}\s*\(", l) or (i > 0 and re.search(rf"\b{fn}\s*\(", code[i-1])):
            if re.search(r"\boffset\s*=", l):
                errs.append((i+1, f"{fn}() has no 'offset' parameter (only plot/plotshape/plotchar/plotarrow do)"))

# ---------- 2c. Pine format strings have no '+' sign specifier ----------
for i, l in enumerate(lines):          # raw source: strip() removes string bodies
    if re.search(r'str\.tostring\s*\([^)]*,\s*"\+', l):
        errs.append((i+1, "str.tostring format string cannot start with '+' -- prepend the sign yourself"))

# ---------- 3. function defs must be at column 0 ----------
for i, l in enumerate(code):
    if re.match(r"^\s+\w+\s*\([^)]*\)\s*=>\s*$", l):
        errs.append((i+1, "function definition is indented — must be top level"))

# ---------- 4. indentation must be a multiple of 4, no tabs ----------
for i, l in enumerate(lines):
    if "\t" in l: errs.append((i+1, "tab character"))
    if code[i].strip():
        ind = len(code[i]) - len(code[i].lstrip())
        if ind % 4: warns.append((i+1, f"indent {ind} not a multiple of 4 (continuation?)"))

# ---------- 5. identifier declaration check ----------
BUILTIN = set("""
open high low close volume time time_close bar_index last_bar_index na true false
barstate syminfo timeframe strategy chart session dayofweek year month weekofyear
hour minute second dividends splits earnings adjustment backadjustment settlement
ta math str array matrix map request color table line box label polyline linefill
ticker runtime input alert plot plotshape plotchar plotarrow plotcandle plotbar
hline fill bgcolor barcolor alertcondition indicator library nz na fixnan
timestamp int float bool string var varip if else for while switch to by break
continue and or not export method type enum import as import size shape location
scale display format extend xloc yloc position text order barmerge currency
adjustment dividends label_style line_style font day week month year
max_bars_back timenow weekofyear dayofmonth
""".split())
PREFIXED = re.compile(r"\.\w+")

declared = {}          # name -> first line declared
def note(name, ln):
    if name and name not in declared:
        declared[name] = ln

for i, l in enumerate(code):
    ln = i + 1
    # function definition + params
    m = re.match(r"^(\w+)\s*\(([^)]*)\)\s*=>", l)
    if m:
        note(m.group(1), ln)
        for prm in m.group(2).split(","):
            parts = prm.strip().split()
            if parts: note(parts[-1], ln)
        continue
    # tuple destructuring
    m = re.match(r"^\s*\[([^\]]+)\]\s*=", l)
    if m:
        for nm in m.group(1).split(","): note(nm.strip(), ln)
        continue
    # for loops
    m = re.match(r"^\s*for\s+\[?([\w\s,]+)\]?\s*(=|in)\s", l)
    if m:
        for nm in m.group(1).split(","): note(nm.strip(), ln)
    # plain declaration / assignment
    m = re.match(r"^\s*(?:var(?:ip)?\s+)?(?:(?:int|float|bool|string|color|line|label|box|table|polyline|linefill|chart\.point|array<[^>]+>|matrix<[^>]+>|map<[^>]+>)\s+)?(\w+)\s*(?::=|=)(?!=)", l)
    if m: note(m.group(1), ln)

used = collections.defaultdict(list)
for i, l in enumerate(code):
    bare = PREFIXED.sub("", l)
    bare = re.sub(r"\b\w+\s*=(?!=)", "", bare)          # drop named-arg keys
    for m in re.finditer(r"\b[A-Za-z_]\w*\b", bare):
        used[m.group(0)].append(i + 1)

for name, locs in sorted(used.items()):
    if name in BUILTIN or name in declared: continue
    if re.match(r"^(SC_|SZ_|MAXN|IDX_|SIZE_|RENORM_|LEVEL_)", name): continue
    errs.append((locs[0], f"undeclared identifier: {name}"))

for name, ln in declared.items():
    first = min(used.get(name, [10**9]))
    if first < ln:
        errs.append((first, f"'{name}' used at line {first} but declared at {ln}"))

# ---------- 6. table bounds ----------
m = re.search(r"table\.new\([^,]+,\s*(\d+)\s*,\s*(\d+)", src)
if m:
    cols, rows = int(m.group(1)), int(m.group(2))
    for i, l in enumerate(code):
        for mm in re.finditer(r"table\.cell\(\s*\w+\s*,\s*(\d+)\s*,", l):
            if int(mm.group(1)) >= cols:
                errs.append((i+1, f"table column {mm.group(1)} >= declared {cols}"))
    print(f"table declared {cols} cols x {rows} rows")

print(f"\n{len(errs)} errors, {len(warns)} warnings")
for ln, msg in sorted(errs)[:40]: print(f"  ERROR line {ln}: {msg}")
for ln, msg in sorted(warns)[:15]: print(f"  warn  line {ln}: {msg}")
