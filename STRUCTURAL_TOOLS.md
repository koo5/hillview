# Query structure, don't match text

Portable working agreement. Copy or `@`-include into any repo's `CLAUDE.md`.

> "grep is the asbestos of our time" — convenient, everywhere, quietly harmful.

**The rule:** if the thing you are inspecting has structure — a process tree, an
XML document, a struct, an AST, a package database — query it through something
that understands that structure. Reach for a regex over text only when nothing
else exists.

Not because regexes are inelegant. Because they are **confidently wrong**, and
the wrongness looks like an answer.

## Why (each of these actually happened, in one session)

| what was matched | what went wrong |
|---|---|
| `pkill -f "darktable-cli.*phase_11"` | the pattern appeared in the **killing shell's own command line**, so it killed its own launcher |
| `pgrep -f darktable-cli` | matched the `sudo`/`systemd-run`/`runuser` **wrappers** (RSS 0), not the real process — twice reported the wrong state to the user, twice corrected |
| `pgrep -c -f pano_pipeline.py` | matched **my own shell**; reported a dead pipeline as alive |
| regex over an XMP sidecar | two attempts silently returned nothing before a third worked. It is **XML** |
| guessing a `struct.unpack` format | inferred `<ffii` by reading a header. DWARF knew the real layout |
| `ast` walk for a function call | missed every call site because they used an **aliased import**; nearly reported a safety gate as missing when it was present and correct |

Every one produced a *plausible* answer. That is the danger: a failed structural
query errors, a failed text match returns nothing and looks like a fact.

## Pick the tool by data type

| data | use | not |
|---|---|---|
| a running job / process tree | the **cgroup**: `cgroup.procs` (kernel's own membership list, includes children), `cgroup.kill` (atomic subtree kill, ≥5.14), `systemd-run --unit=NAME` for a stable handle, `systemctl kill/status`, `systemd-cgls`, `systemd-cgtop` | `pgrep`/`pkill -f`, `ps \| grep` |
| C / C++ | **clangd** + `compile_commands.json` (`cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`), or `ctags`/`cscope`, or `ast-grep` | grep for definitions/references |
| Python | **pyright** via LSP (`uv tool install pyright` — bundles its own Node), or the stdlib `ast` module | grep for call sites |
| XML / XMP / SVG / HTML | `python3 -c` + `xml.etree`, `xmlstarlet`, `xmllint` | regex |
| XMP specifically | `exiv2 -P Xkv pr` addresses properties by path (`Xmp.darktable.history[N]/…`). Note it **reads** struct members but cannot **write** them | regex |
| JSON / YAML | `jq`, `yq`, `python3 -m json.tool` | regex |
| struct layout, binary blobs | **`pahole`** (from `dwarves`) reads DWARF from the actual binary | inferring a format from a header |
| image / EXIF metadata | `exiftool`, `vipsheader`, `tiffinfo`, `identify` | byte offsets by hand |
| packages / file ownership | `dpkg -S`, `dpkg -l`, `apt-cache policy` | guessing from paths or mtimes |
| your own program's state | make it **emit JSON** (a few lines) and parse that | printing to a log and scraping it back |

## Install

```fish
sudo apt install -y xmlstarlet libxml2-utils dwarves universal-ctags cscope jq
uv tool install pyright          # brings its own Node; do NOT use npm -g
sudo apt install -y clangd-19    # see the trap below
```

## Kotlin

Two tools, and both cost a session to get right.

**ast-grep** — tree-sitter patterns, Kotlin built in. Structural, so comments and
string literals cannot pollute a match; that alone settled a question a regex had
been over-reporting by 58 hits.

```bash
ast-grep -l kotlin -p 'Log.$M($$$ARGS)' --json=compact path/     # calls
ast-grep scan -r rule.yml path/                                  # kind: based rules
```

- **`$METAVAR` does not work in Kotlin expression positions.** `$` is Kotlin's
  string-template character, so `const val TAG = $V` parses to an ERROR node and
  matches **nothing, silently**. Check every new pattern with
  `--debug-query=ast`. Where a metavariable will not go, use a YAML rule with
  `kind:` plus `regex:` anchored to the node text.
- **`sg` is NOT ast-grep on a Debian box.** It is shadow-utils' run-as-group
  (`dpkg -S $(command -v sg)` → `login`). ast-grep installs `sg` as an alias, so
  after installing, `sg` is ambiguous. Always invoke `ast-grep`.

**kotlin-lsp** (JetBrains) — the tool that RESOLVES NAMES, so it answers what a
pattern cannot: an aliased import, a re-export, a call through a typealias. In
Claude Code it arrives as the `kotlin-lsp` marketplace plugin, which is metadata
only — it invokes a `kotlin-lsp` executable on PATH, the same way
`rust-analyzer-lsp` needs `rust-analyzer`. Upstream ships that name via Homebrew
only; on Linux use the standalone tarball and supply the name
(`~/.local/bin/kotlin-lsp`, already written, version-agnostic).

```bash
# 1. pick a build: releases at github.com/Kotlin/kotlin-lsp
# 2. tarball + published SHA-256 from download-cdn.jetbrains.com
curl -sS -o kls.tar.gz https://download-cdn.jetbrains.com/language-server/kotlin-server/<V>/kotlin-server-<V>.tar.gz
curl -sS  https://download-cdn.jetbrains.com/language-server/kotlin-server/<V>/kotlin-server-<V>.tar.gz.sha256
tar -xzf kls.tar.gz -C ~/.local/share/kotlin-lsp/<V>/     # ~1.3 GB extracted
kotlin-lsp --version                                      # LS-<V>
```

- **THESE BUILDS EXPIRE.** An older build is not the safe choice here, which
  inverts the usual instinct: `v262.9593.0` (61 days old) dies with
  `This build of intellij-server has expired` and the LSP tool reports only
  `crashed with exit code 7`. Run the binary by hand to see the real reason.
- **The expiry fights the 14-day dependency cooloff** (`scripts/deps.py`): the
  newest build is often the ONLY unexpired one, and therefore too young. On
  2026-09-26 the only usable build was 12 days old, eligible 2026-09-27 — so the
  answer was to wait a day, not to bend either rule. Check both before
  downloading 400 MB.

## Traps worth knowing

* **A tool that fails is better than one that lies.** Prefer the query that
  errors on a bad key (`exiv2` → `Invalid key`) over the one that silently
  matches nothing.
* **Verify the tool before trusting its answer.** A `clangd` snap on one machine
  was version **6.0.0 from 2018** and spun 21s of CPU on `--version`. Check
  `--version` and the origin (`dpkg -S`, `snap list`) before believing output.
* **Version-pinned toolchains fight each other.** `clangd-18` refused to install
  against an `apt.llvm.org` `libllvm18` snapshot; `clangd-19` from the distro
  installed cleanly because it brings its own runtime. Match the *source*, not
  just the number.
* **Structured does not mean faithful.** Round-tripping XML through `lxml`
  reflowed a 17 KB sidecar into 402 diff lines. If the file belongs to someone
  else, prefer *not writing it at all* over rewriting it "equivalently" — let
  the owning application write its own format.
* **An AST query is only as good as its name resolution.** Aliased imports,
  re-exports and dynamic dispatch defeat naive matching. Prefer a real LSP
  (`findReferences`) over hand-rolled AST walks when one is available.
* **Text matching is legitimate for genuinely unstructured data** — free-form
  log lines, human prose, a one-off rename audit. Use it deliberately, and say
  so, rather than by reflex.

## The uncomfortable part

In the session that produced this list, the right tool was almost always
**already installed**. `xml.etree` shipped with Python. `cgroup.procs` was
sitting in `/sys/fs/cgroup`. Nothing needed to be fetched. The failure was
reaching for the familiar hammer, not a missing one.

So the discipline matters more than the package list: **before matching text,
ask what actually holds this data, and whether it will answer the question
directly.**
