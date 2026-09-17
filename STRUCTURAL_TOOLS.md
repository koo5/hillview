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
