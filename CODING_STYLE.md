# Coding Style Guide

A complete specification of one engineer's coding style across Python, JavaScript,
HTML/Jinja templates, CSS, and JSON config, plus how they lay out projects. It was
reverse-engineered from about 20,000 lines of their own tools, libraries, CLIs, Qt
GUIs, a Flask web app, and its front-end code.

**Goal:** code written to this guide should be indistinguishable from the author's.
Rules marked **[STRONG]** are near-universal in the reference code. Where the author is
inconsistent, the most common behavior is the rule and the exception is noted. **When
this guide and the surrounding code disagree, match the surrounding code**, and mirror
the closest existing module of the same shape.

> **Python compatibility:** the author's Python must run under **both Python 2 and
> Python 3** (via the `future` library). Many rules below exist for that reason. Do not
> "modernize" them away. They're intentional. If a project is Python-3-only, see the appendix
> for which rules relax.

---

## Contents

**Python**
1. File header & module structure
2. Package layout
3. Imports
4. Naming
5. Class design
6. Function design
7. Strings & formatting
8. Docstrings & comments
9. Error handling
10. Logging
11. Filesystem, paths & environment
12. Idioms used / avoided
13. Configuration, email, external services
14. Command-line entry scripts
15. Qt / GUI code
16. Formatting details

**Other languages and projects**

17. JavaScript
18. HTML / Jinja templates
19. CSS
20. JSON / config files
21. Web app (Flask) project structure
22. Decision heuristics

23. Quick reference templates

Appendix: Python-3-only projects

---

## 1. File Header & Module Structure (Python)

Every `.py` module follows this exact top-to-bottom skeleton:

1. **Shebang** `#!/usr/bin/env python` **[STRONG]**. Always plain `python`, never
   `python2`/`python3`.
2. **Copyright/license header**: the project's comment block, with the current year.
   Use whatever header the project requires. If none is specified, use a short
   `# Copyright (c) <YEAR> <Owner>. All rights reserved.` line.
3. **Module docstring**: triple-double-quoted. It describes *what the module does* in
   imperative mood (see §8). It immediately follows the header **with no blank line**.
4. **Imports**: grouped, and ordered by line length (see §3).
5. Two blank lines, then **`logger.setup('<package>.<dotted.name>')`** at module level,
   for any module that logs.
6. Two blank lines, then **module-level constants** (if any) or the first class or
   function.

```python
#!/usr/bin/env python
# Copyright (c) 2026 <Owner>. All rights reserved.
"""
One or more imperative sentences describing what this module does.
"""
```

- Always include the header. It appears on about 100% of files.
- Exception: a few GUI/widget files omit the shebang but keep the header.

---

## 2. Package Layout (the standard tool skeleton)

Each tool lives in its own package directory under `<package>/tools/<tool_name>/`. The
**canonical layout**:

```
<tool_name>/
    __init__.py       # exposes the public entry point
    main.py           # thin entry point: parse/normalize args -> instantiate class -> call
    <tool_name>.py    # the core class (e.g. scene_transfer.py -> class SceneTransfer)
    utils.py          # helper functions + the tool's custom Exception
    constants.py      # module-level constants, patterns, dict config
```

Rules:
- **One core class per tool**, named in `CamelCase` after the tool
  (`scene_transfer.py` → `SceneTransfer`). **[STRONG]**
- **`main.py` is always thin.** It builds arguments, constructs the core object, and
  calls one or two public methods. It contains almost no logic.
- **`constants.py`** holds all magic values, regex patterns, directory-structure dicts,
  and format templates. Don't inline magic strings or numbers in logic; lift them to
  `constants.py`. **[STRONG]**
- **`utils.py`** (or `_utils.py`) holds stateless helper functions and the tool's custom
  exception class.
- `__init__.py` exposes the public surface:
  ```python
  from __future__ import absolute_import
  from .main import main
  ```
  or, for a library-style package:
  ```python
  from __future__ import absolute_import
  from .reference_manager import ReferenceManager
  from .file_map import FileMap
  ```

### Private-module convention (newer code)
Newer packages prefix internal modules with an underscore: `_api.py`, `_utils.py`,
`_constants.py`. A module meant to be imported by other packages stays unprefixed
(`api.py`, `constants.py`). The underscore form is the more recent preference.

The newer `__init__.py` re-exports from `_api` with labeled sections and no docstring:
```python
from <package>.tools.<tool> import _api

# Classes
<Tool> = _api.<Tool>

# Functions
run = _api.run
```

### GUI subpackage
GUI code goes in a `gui/` subpackage with files like `main.py`, `widgets.py`,
`groups.py`, and `qss.py`. Qt styling lives in `qss.py` as a `QSS` string constant.

### Entry scripts
CLI entry scripts live in a separate `bin/` directory as **extensionless `camelCase`
files** (`sceneTransfer`, `projectSetup`). They're thin dispatchers that import the tool
package (see §14).

---

## 3. Imports

- **Group imports** into blocks separated by a single blank line, in this order:
  1. `__future__` imports (when present)
  2. Standard library
  3. Third-party / host-application modules (`Qt`, `flask`, `future`, host-application APIs)
  4. The project's own framework packages
  5. Intra-package imports (`from <package>.tools.<tool> import utils`)
- **Order imports within a group by line length, shortest first.** **[STRONG]** This is
  a distinctive, consistent habit:
  ```python
  from core import mail
  from core import logger
  from core import settings
  from db import api as assetdb
  from tools.reference_manager import ReferenceManager
  ```
- Put **two blank lines** after the final import block, before `logger.setup(...)`,
  constants, or the first definition.
- Use `import x` or `from x import y`, **one name per `from` line**. Write
  `from flask import request` and `from flask import session` on separate lines, not
  `from flask import request, session`. **Never use wildcard imports.**
- **Alias conventions:**
  - Short API aliases: `from db import api as assetdb`, `from media import utilities as mu`
  - Qt: `from Qt import QtCore as qc`, `QtWidgets as qw`, `QtGui as qg` (the `Qt.py`
    shim)
  - In public `api.py` files, alias implementation imports with a leading underscore to
    keep them out of the public namespace: `from ... import register_media as _register`
- Compat imports appear when needed: `from builtins import object`,
  `from __future__ import absolute_import`, `from future.utils import listitems`,
  `from past.builtins import basestring`.

---

## 4. Naming

| Kind | Convention | Example |
|------|-----------|---------|
| Modules / packages | `snake_case`, often matching the tool | `project_setup`, `reference_manager` |
| Classes | `CamelCase` | `SceneTransfer`, `ReferenceManager`, `FileMap` |
| Functions / methods | `snake_case`, **verb-first** | `create_package`, `map_references_from`, `get_export_dir` |
| Private methods/attrs | leading underscore | `_check_args`, `_setup`, `self._project` |
| Constants | `UPPER_SNAKE_CASE` | `MASK`, `WORK_DIR`, `DIR_STRUCT`, `VERSION_PADDING` |
| Regex pattern constants | `UPPER_SNAKE` + `_PATTERN` | `ASSET_PATTERN`, `SPLIT_SEQ_PATTERN` |
| Custom exceptions | `<Tool>Error` | `ProjectSetupError`, `SceneTransferError` |
| Bools / bool params | plain adjective or `is_`/`has_` | `dry`, `new`, `overwrite`, `add_watermark`, `allow_missing` |
| Collections | plural nouns | `file_maps`, `references`, `versions`, `missing_references` |
| Loop / temp vars | short real words; `i` for an index | `for i, file_map in enumerate(...)`, `msg`, `err`, `f_in`/`f_out` |
| CLI scripts | `camelCase`, no extension | `projectSetup`, `sceneTransfer`, `convertAsset` |

Rules:
- **Method names are verb-first and descriptive.** Common prefixes: `get_`, `create_`,
  `map_`, `replace_`, `send_`, `do_`, `run`, `check_`, `setup_`, `populate_`,
  `report_`. **[STRONG]**
- The **public orchestrator method** on a class is `run()`, `do_<thing>()`
  (`do_setup`, `do_transfer`), or `create_package()`.
- **Don't abbreviate**, except for a small set of established short names: `msg`, `err`,
  `ext`, `src`, `dest`, `dir`, `f_in`/`f_out`, `mf` (media file), `cc`. Write
  `reference_manager`, not `rm`.
- File objects from `with open(...)` are named `f_in` / `f_out`.
- Error and message strings are built into a local named `msg`.

---

## 5. Class Design

Tools are **strongly object-oriented**. Each tool is a class constructed with all its
inputs and then driven by a small number of public methods.

### Constructor pattern **[STRONG]**
```python
class SceneTransfer(object):
    def __init__(self, original_file, project, vendor=None, dry=False):
        """
        Initialize the scene transfer

        :param original_file: (str)  the original scene file
        :param project:       (str)  the name of the project
        :param vendor:        (str)  the name of the vendor the package will be sent to
        :param dry:           (bool) whether to skip side effects
        """
        self._original_file = original_file
        self._project = project
        self._vendor = vendor
        self._dry = dry
        self._transfer_id = None
        self._export_dir = utils.get_export_dir(original_file, project)
        self._tar = None

        # Check that the provided arguments are valid
        self._check_args()

        logger.info('New Scene File: {}'.format(self._edit_file))
```

Rules:
- **Inherit explicitly from `object`**: `class Foo(object):`. **[STRONG]** Add
  `from builtins import object` when the file otherwise imports builtins.
- **Store every constructor argument as a `self._private` attribute.**
- **Initialize all derived and mutable state in `__init__`** (to `None`, `[]`, or `{}`),
  so the full attribute surface is visible at construction. **[STRONG]**
- **Call `self._check_args()` (or `self._setup()`) at the end of `__init__`** to
  validate inputs and/or build initial state.
- In newer code, group constructor attributes with short section comments:
  ```python
  # Source
  self.source_dir = path.initialize(source)
  # Context
  self._project = project
  self._environment = environment
  # Processing options
  self._add_watermark = add_watermark
  ```

### Properties **[STRONG]**
- Expose instance state through **read-only `@property` getters**, with no setters. In
  older code nearly every private attribute has a matching property:
  ```python
  @property
  def project(self):
      return self._project
  ```
- Use properties for **computed/derived values** too:
  ```python
  @property
  def shots(self):
      return list(self.shot_renders.keys())
  ```
- **Never use `@staticmethod` or `@classmethod`.** Put stateless helpers in `utils.py`
  as module-level functions instead.

### Public vs private methods
- **Private helpers** (`_verb_noun`) do the internal steps. **Public methods** form the
  orchestration API and are mostly thin.
- The public `run()` / `do_*()` method reads like a checklist of private calls, each
  preceded by a one-line `#` comment:
  ```python
  def run(self):
      """
      Run a registration
      """
      logger.info('Starting registration ...')

      # Collect and sort media files from the source directory
      self._analyze_source_dir()

      # Prep, upload, and register the media
      self._prep_media()
      ...
  ```

### Attribute visibility
- **Older code:** near-total `self._private` plus matching properties.
- **Newer code:** mixes public attributes (`self.source_dir`, `self.settings`) for things
  freely read or written, while keeping context like `self._project` private.
- When in doubt, **default to `self._private` plus a property.**

---

## 6. Function Design

- **Keep functions and methods short and single-purpose**, most 5–30 lines. Long parsing
  methods are allowed if heavily sub-commented into labeled steps.
- **Signatures use keyword arguments with defaults** liberally:
  ```python
  def register(source, project, environment, element='default', location=None,
               overwrite=False, add_watermark=False, upload=False):
  ```
- Use `os.getenv('<CONTEXT_VAR>')` / `os.getenv('USER')` as **default argument values**
  for environment-provided context.
- **Use guard clauses and early returns.** Return early on the negative or no-op case
  rather than nesting. **[STRONG]**
  ```python
  def send_summary(self):
      if self._dry:
          return
      ...
  ```
- Use **`for/else` and `while/else`** deliberately for search loops.
- Use **`continue` to skip** inside loops rather than wrapping the body in an `if`.
- Helpers return values. Stateless `utils.py` helpers avoid side effects. Mutating
  `self._...` collections is fine in the stateful core class.
- Thin wrappers pass through with `*args, **kwargs`:
  ```python
  def register(source, *args, **kwargs):
      reg = _register.RegisterMedia(source, *args, **kwargs)
      return reg.run()
  ```
- **Line length:** wrap at about **110–115 columns**. When wrapping a call or signature,
  **align continuation arguments to the opening paren**:
  ```python
  register = RegisterFiles(source, project, environment, element=element,
                           location=location, overwrite=overwrite,
                           add_watermark=add_watermark, upload=upload)
  ```
- Build command lines as a **list with `None` placeholders, then filter and join**:
  ```python
  cmd = [
      transfer_cmd,
      '-u {}'.format(user_dir) if user_dir else None,
      '--overwrite' if overwrite else None,
      '"{}"'.format(source)
  ]
  cmd = ' '.join(list(filter(None, cmd)))
  ```

---

## 7. Strings & Formatting

- **Use `str.format()` for all string interpolation.** **[STRONG]** It outnumbers
  f-strings about 16:1. **Do not use f-strings** (Py2 compat). Use `%`-formatting only
  rarely.
  ```python
  logger.info('Export directory: {}'.format(self._export_dir))
  msg = 'Cannot find asset {0} in project {1}'.format(self._asset, self._project)
  ```
- Use **`{}`** for simple substitutions and **`{0}`/`{1}`** when a value is reused or
  order needs to be explicit. Older code leans `{0}`, newer code leans `{}`.
- **Prefer single quotes** (about 2:1). Use double quotes when the string contains an
  apostrophe, or occasionally for user-facing text. **[STRONG]**
- **Build multi-line email and report bodies as a list of lines, then join:**
  ```python
  body = [
      'Project: {0}'.format(self._project),
      'Original File: {0}'.format(self._original_file)
  ]
  mail.send(subject, '\n'.join(body), ...)
  ```
  For HTML email, join with `'<br/>'` and pass `message_type='html'`.
- Split long string literals with **implicit concatenation** inside parens, each piece on
  its own aligned line:
  ```python
  help_page = ('https://docs.example.com'
               '/display/TOOLS/Transfer+Scene')
  ```

---

## 8. Docstrings & Comments

### Docstrings: RST/Sphinx `:param:` style **[STRONG]**
- Use `"""` with the opening and closing quotes **on their own lines**.
- **Module docstrings:** one or more short imperative sentences ("Put a given scene file
  and all the files it references into a tar file."). Tools that create directory
  layouts may include an ASCII directory diagram.
- **Function and method docstrings:** an imperative summary line, a blank line, then
  aligned `:param:` / `:return:` blocks. **Never use Google (`Args:`) or NumPy styles.**
  ```python
  def get_export_dir(original_file, project):
      """
      Get the export directory

      :param original_file: (str) path to the original scene file
      :param project:       (str) the name of the project
      :return:              (str) the export directory
      """
  ```
  - **Align the parameter names and the `(type)` columns** with spaces. Types go in
    parentheses: `(str)`, `(bool)`, `(int)`, `(dict)`, `(list)`, `(obj)`, and nested forms
    like `(lst<str>)` and `(lst<obj>)`.
  - Web routes may use `:response: (jsn) ...` in place of `:return:`.
- **Summary lines have no trailing period** ("Get the export directory").
- **Short or obvious functions** may have a summary-only docstring:
  ```python
  def register(source, *args, **kwargs):
      """
      Run a media registration
      """
  ```
- **Every non-trivial function has a docstring**, including one-line private helpers.
  Pure field-return property getters are left undocumented. Computed properties get a
  one-line docstring.

### Inline comments
- Use **short, capitalized, imperative `#` comments to label steps.** This is pervasive:
  most logical blocks get a lead-in comment. **[STRONG]**
  ```python
  # Copy files to the export dir
  self._reference_manager.copy_files_to_dest()

  # Repoint the references in the scene files to the export directory
  self._reference_manager.replace_references_in(...)
  ```
- Comments explain **what the next block does and why**, not how a single line works.
- **Don't add `TODO`/`FIXME`.** They're essentially absent.
- A commented-out alternative line is occasionally left in place (e.g. an alternate
  `app.run(...)` call). It's tolerated, but don't add one deliberately.

---

## 9. Error Handling

- **Define one custom exception per tool** in its `utils.py`, with a bare `pass` body:
  ```python
  class ProjectSetupError(Exception):
      pass
  ```
  Name it `<Tool>Error`. **[STRONG]** Subclass `Exception`, never `BaseException`. When a
  package has a shared exception hierarchy (`MediaError` → `MediaFileError` →
  `NotOnDisk`), add new errors there instead.
- **Raise the custom exception with a descriptive `msg`** built just above the raise,
  and usually **log or report before raising**:
  ```python
  msg = 'Cannot find asset {0} in project {1}'.format(self._asset, self._project)
  self._report_issue(msg)
  raise utils.ProjectSetupError(msg)
  ```
- **Validate inputs up front** in `_check_args()`, raising the custom exception on
  invalid input.
- **Wrap entry points with an error-reporting decorator**
  (`@decorators.error(subject='...')`). It emails or reports the traceback of any
  unhandled exception, then re-raises. Put it on public `main()` / api-level functions.
  **[STRONG for entry points]**
  ```python
  @decorators.error('Scene Transfer Error Report')
  def main(original_file, project=os.getenv('PROJECT'), vendor=None, dry=False):
      ...
  ```
- **Settings lookups use `try/except KeyError` with a fallback default**, typically a
  team mailing list:
  ```python
  try:
      cc_users = settings.TOOLS['scene_transfer']['cc']
  except KeyError:
      cc_users = ['TEAM-LIST']
  ```
- **Use broad `except Exception as err:` only at best-effort boundaries** (e.g. a
  per-item loop where one failure shouldn't abort the batch). Log a warning and continue:
  ```python
  except Exception as err:
      logger.warning('Media registration failed: {}'.format(err))
  ```
- **No `assert` statements** for runtime validation. Validate explicitly and raise.
- In `main()` argument handling, prefer **`logger.warn(...)` plus `return`** for
  user-facing precondition failures (missing context) over raising.

---

## 10. Logging

- **Use the project logger, never `print()`**, for diagnostics. `print` is about 10
  uses versus about 560 `logger.*` calls. **[STRONG]**
- Call `logger.setup('<package>.<dotted.module.name>')` **once at module level**, right
  after imports. The name mirrors the module's dotted path.
- **Log progress narratively** at `logger.info(...)` around each meaningful step
  ("Creating the transfer package", "Copying files to {}", "Mapping reference: {}"). The
  author logs generously.
- Use `logger.warning(...)` for recoverable problems, `logger.error(...)` before an error
  report, and `logger.debug(...)` for verbose dumps.

---

## 11. Filesystem, Paths & Environment

- **Use `os.path`** (`join`, `basename`, `splitext`, `exists`, `os.makedirs`), or a
  project's own path-object API where one exists (`path.initialize(x)`,
  `path.Directory(x)`, `.join(name)`, `.create()`, `.exists`, `.path`, `.basename`,
  `.stem`, `.extension`).
- **Do not use `pathlib`.** It never appears.
- Get context from the environment: `os.getenv('USER')`, `os.environ['USER']`, and
  project context variables.
- Build directory paths from `constants.py` templates: `WORK_DIR = '/projects/{0}/work/{1}'`,
  then `WORK_DIR.format(project, user)`.
- Set permissions with an explicit `MASK` constant built from `stat` flags:
  ```python
  MASK = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO
  os.makedirs(self._export_dir)
  os.chmod(self._export_dir, MASK)
  ```
- **Version** directories and files by scanning for the next free `_v###` suffix
  (`find_next_version`). Control padding with a `VERSION_PADDING = '03'` constant and
  `format(n, padding)`.

---

## 12. Python Idioms Used / Avoided

**Used:**
- **List and dict comprehensions** for simple transforms and filters:
  `[file_map for file_map in self._file_maps if file_map.sub_dir in sub_dirs]`
- **`dict.setdefault(key, [])`** to group items into buckets
- **`enumerate()`** when the index is needed
- **`list(set(x))`** to dedupe
- **`(value or '').lower()`** to null-safe-normalize optional strings
- **`sorted(..., key=lambda item: ...)`** for ordering, and the ternary `x if cond else y`
  for small conditionals
- **`with open(a) as f_in, open(b) as f_out:`**: multiple context managers on one line
  for read-to-write transforms
- **`functools.wraps`** in decorators, **`re.compile`** patterns stored as constants, and
  **`datetime.now().strftime(...)`** for timestamps
- **`any(...)` with a generator** for membership tests
  (`any(real_path.startswith(limit) for limit in LIMITS)`)
- ANSI color escape codes in a `COLORS` constant dict for terminal output and argparse
  help text

**Avoided (do not introduce):**
- ❌ f-strings (use `.format()`)
- ❌ `pathlib` (use `os.path`)
- ❌ `@staticmethod` / `@classmethod` (use module functions or instance methods)
- ❌ Type annotations / `typing`
- ❌ `dataclasses`, `namedtuple`, `attrs` (use plain classes with `__init__` plus
  properties)
- ❌ `enum.Enum` (use `UPPER_SNAKE` constants or config dicts)
- ❌ Wildcard imports
- ❌ Global mutable state / module-level singletons (state lives in the tool class)
- ❌ Metaclasses, monkey-patching, clever decorators. Metaprogramming stops at one
  class-based error decorator and plain `functools.wraps`.
- ❌ `assert` for validation
- ❌ `print()` for logging
- ❌ Bare `super()`. Always `super(ClassName, self)`.
- ❌ Python-3-only syntax: walrus, keyword-only/positional-only args, `nonlocal`,
  `async`, `yield from`

---

## 13. Configuration, Email & External Services

- **Per-tool settings** live in a central config (`settings.TOOLS['<tool_name>']`) loaded
  from JSON-style config files (§20). Read them defensively with `try/except KeyError`.
  Common keys are `to`, `cc`, and service-specific options.
- **A dev-mode config layer** overrides recipients with `"${USER}"`, so development runs
  only email the developer. Every new tool gets a block in both the global and the dev
  config.
- **Email:** `mail.send(subject, body, to_users=, cc_users=, from_user=, message_type=)`.
  Recipients default to a team list.
- **Background job dispatch:** CLI scripts usually **submit work to a job queue**
  rather than doing it inline. They build a `python -c "from pkg import X; X(...).run()"`
  command, wrap it in a job object, submit it, and log the job id.
- **Fluent processing APIs:** media/processing wrappers use a step-by-step builder.
  Construct with a source, chain `.resize()`, `.add_watermark()`, `.convert_format()`,
  then `.render(dest_path=..., overwrite=True)`.
- **Respect a `dry` flag** on anything that touches the filesystem, a database, a job
  queue, or email. Short-circuit the side effect and log what would have happened.

---

## 14. Command-Line Entry Scripts (`bin/`)

- `bin/` scripts are **extensionless `camelCase` files** with the shebang, header, and
  module docstring. They define a `main()` guarded by `if __name__ == '__main__': main()`.
- Use `argparse.ArgumentParser(description=__doc__)` with `-x/--xword` short+long flags,
  `default=os.getenv(...)` for context args, `required=True` where needed, and
  `action='store_true'` for boolean flags.
- Wrap `main()` with the error-report decorator.
- **Catch `SystemExit` from `parse_args()`**, so a bare no-arg invocation exits quietly
  instead of sending an error report:
  ```python
  try:
      args = parser.parse_args()
  except SystemExit:
      if len(sys.argv) > 1:
          raise
      return
  ```
- Validate required context (`if not args.project: logger.error(...); return`) before
  dispatching.
- Split the script into **`dispatch(args)`**, which builds the command and submits the
  job, and **`main()`**, which parses and validates. Build the inner command's keyword
  arguments as a list of `'key={}'.format(...)` strings joined with `', '`.
- Mark required args in help text with a colored `(Required)` prefix, using ANSI codes
  from a constant.

---

## 15. Qt / GUI Code

- Import Qt through the `Qt.py` shim: `from Qt import QtCore as qc`, `QtWidgets as qw`,
  `QtGui as qg`. Never import PySide or PyQt directly.
- **Subclass Qt widgets** to make reusable components (`class ParmComboBox(qw.QComboBox)`,
  `class WarningDialog(qw.QDialog)`).
- Use old-style **`super(ClassName, self).__init__(...)`**. **[STRONG]**
- **Name signal/slot callbacks `_on_<event>`** (`_on_value_changed`,
  `_on_timer_interval`) for private handlers, or `on_<event>` when public.
- Expose widget state via `@property` (`current_label`, `current_node`).
- Keep stylesheet strings in a `qss.py` module and apply them with
  `self.setStyleSheet(qss.QSS)`.
- **Host-application plugins** subclass the host's mode or plugin base class. They
  register events and menus in an init method, and define a module-level factory
  function at the **bottom** of the file that returns the instance.

---

## 16. Formatting Details (Python)

- **Indentation:** 4 spaces, no tabs.
- **Two blank lines** between top-level definitions and after the import block. **One
  blank line** between methods and between logical blocks inside a function.
- **Spaces around operators** and after commas. `key=value` keyword arguments have **no
  spaces around `=`**.
- **Multi-line dicts and lists** have one entry per line and **no trailing comma** after
  the last element. That's more common, but match the surrounding file.
- Multi-line config dict literals use one key per line and may include an explanatory
  `#` comment inside the literal.
- Regex patterns are `NAME_PATTERN = re.compile(r'...')` raw strings in `constants.py`.
- Prefer **explicit, readable code over clever one-liners.** The author optimizes for
  explicitness, debuggability, and discoverability (hence heavy logging, step comments,
  and property getters) over brevity.

---

## 17. JavaScript

The author writes **plain, framework-free browser JavaScript** (no jQuery, React, or build
step). It's organized as a shared utility library plus per-page namespaced modules.

### File header
A block-comment copyright header with no leading asterisks:
```javascript
/*
Copyright (c) 2026 <Owner>. All rights reserved.
*/
```

### Structure
- **Shared utilities** (`static/utils/general.js`, `static/utils/routing.js`) are
  top-level `function` declarations, one per helper.
- **Per-page/component modules** use a **namespaced revealing-module IIFE** that returns
  `self`:
  ```javascript
  window.app = window.app || {};
  app.tools = app.tools || {};
  app.tools.transfer_scene = (function() {
      let self = {};

      self.required = ['project', 'command', 'fb-selected-path'];

      /**
       * Toggle the submit button based on whether all requirements have been met
       */
      self.toggleSubmitButton = function() {
          $('submit').disabled = !isFilled(...self.required);
      };

      /**
       * Set up the tool
       */
      self.setup = function(dept) {
          // Add event listeners for changing context
          for (const id of self.required) {
              $(id).addEventListener('change', self.onChangeContext);
          }

          self.onChangeContext();
      };

      return self;
  })();
  ```
  - The namespace path mirrors the project layout:
    `app.tools.<tool_name>` or `app.widgets.<widget_name>`, with snake_case segments.
  - Public members are `self.<name> = function() {...};`, each with a semicolon after the
    closing brace.
  - Module-private state is a `let` inside the IIFE.
  - Each page exposes a **`self.setup(...)`** entry point, called from an inline
    `<script>` in the template.
- Define a tiny **`$(id)` helper** that accepts either an id string or an element
  (`isElement(id) ? id : document.getElementById(id)`). Have every helper take `id` and
  resolve it with `const elem = $(id);` on the first line.

### Naming
- **Function and method names: `camelCase`, verb-first**: `toggleVisibility`,
  `addOptions`, `clearSelect`, `setSelector`, `runScriptsIn`, `createWidget`.
- **Local variables and parameters: `snake_case`** **[STRONG]**: `const input_element`,
  `let camel_str`, `default_option`, `toggle_required`. Never camelCase locals.
- Callback handlers are `on<Event>`: `self.onChangeContext`.
- Globals are `$UPPER_SNAKE`: `let $ROUTES = undefined;`.
- DOM ids and CSS classes are kebab-case (`fb-file-input`, `main-form`), and ids carry a
  short component prefix (`fb-` for file browser).

### Declarations & syntax
- **`const` by default, `let` when reassigned, never `var`.** **[STRONG]**
- **Use `function` expressions and declarations.** Arrow functions only for tiny inline
  promise callbacks (`.then(res => {...})`).
- **Single quotes** (about 30:1). Double quotes only in the `typeof x === "undefined"`
  idiom or JSON-like literals.
- **Concatenation with `+`** over template literals. A template literal appears only for
  a multi-value `alert(...)` message.
- **Always use braces**, even for one-line bodies. The one tolerated exception is a
  one-line guard: `if (callback !== undefined) callback(res);`.
- **`else` goes on its own line after the closing brace**, never `} else {`: **[STRONG]**
  ```javascript
  if (visible) {
      elem.style.removeProperty('display');
  }
  else {
      elem.style.display = 'none';
  }
  ```
- Use strict equality (`===`, `!==`) everywhere, and compare to `undefined` explicitly.
- Default parameter values use `=undefined` / `=true` / `={}` **without spaces** around
  `=` (`function toggleVisibility(id, visible=undefined)`), like Python kwargs.
- Loops: classic `for (let i=0; i<list.length; i++)` with no spaces inside the header,
  or `for (const x of list)`.
- **Guard clauses with early `return`**, and `continue` to skip, exactly as in Python.
- End statements with semicolons. A missing one on a final `return x` is common and
  tolerated.
- 4-space indentation.

### Docs & comments
- **JSDoc on every function** with an imperative summary and aligned `@param` / `@returns`
  columns. **The type goes after the name**, `@param name {type} description`, which is
  the reverse of standard JSDoc: **[STRONG]**
  ```javascript
  /**
   * Toggle the visibility of an input element and its label
   * @param id              {string|*} an element or id
   * @param visible         {boolean}  the state of visibility to set (true=visible, false=invisible)
   * @param toggle_required {boolean}  whether to toggle the required attribute of the element
   */
  ```
  Summary lines have no trailing period. A second summary line can describe the behavior
  ("Run any script elements inside").
- **Inline `//` comments label steps**, capitalized and imperative, the same as Python:
  `// Toggle the visibility`, `// Create the request and add the callback function`.
- Use banner comments only for globals: `// Globals`.

### Async & networking
- Use small wrapper helpers (`ajaxURL`, `ajaxPost`, `ajaxEndpoint`) that take a
  **`callback`** argument. Don't use `async/await` in page code.
- `fetch(...).then(...).then(...).catch(err => console.error(err))` lives inside the
  wrapper. Throw on `!res.ok`.
- When a dependency (like a routes table) may not be loaded yet, **retry with
  `setTimeout(fn.bind(this, ...args), 250)`**.
- Support optional-argument shifting explicitly
  (`if (typeof data === 'function') { callback = data; ... }`).

---

## 18. HTML / Jinja Templates

- Server-rendered templates (Jinja2). Each page **extends a base layout**
  (`{% extends 'tools/index.html' %}`) and fills named blocks (`base_css_sources`,
  `content`).
- **Header:** the copyright notice goes in a **Jinja comment** `{# ... #}`, right after
  `<!doctype html>` (or at the top of a partial).
- **Label each section with an HTML comment** naming the block or widget:
  `<!-- File Browser Widget -->`, `<!-- Submit Button -->`, `<!-- Embedded JavaScript -->`.
- Use **`{# ... #}` Jinja comments** for notes that shouldn't reach the browser.
- **Compose pages from reusable widgets** via a helper with a nested config dict, written
  one key per line:
  ```jinja
  {{ include_widget('selector', config={
      'label': 'Command:',
      'attributes': {
          'id': 'command',
          'required': true
      },
      'options': ['copy', 'move']
  }) }}
  ```
- **Forms:** `<form id="main-form" ... method=post enctype="multipart/form-data">`. Pair
  `<label for="...">` with each input. Separate fields with `<br>` (often a double
  `<br>`) rather than layout CSS.
- **End each page with an inline `<script>`** that calls the page module's
  `setup(...)`, passing template values: `app.tools.transfer_scene.setup("{{ dept }}");`.
- Attribute quoting is mixed; match the file. Double quotes are the norm in pages, while
  widget partials often use single quotes.
- Indent nested markup and Jinja blocks by 4 spaces. Indent `{% if %}` bodies inside
  attribute lists to line up under the attribute.

---

## 19. CSS

- **Header:** a block comment with leading ` * ` on each line.
- **Section banners** separate component parts, with two blank lines before each banner:
  ```css
  /* -------- File Browser -------- */
  ```
- **BEM-style class names** with a short component prefix: block `.fb`, element
  `.fb__left-pane`, `.fb__quick-link__header`. Words inside a segment use kebab-case.
  **[STRONG]**
- **Colors in `hsl()`**, usually greyscale (`hsl(0, 0%, 20%)`). Never hex.
- **Spacing and radii in `rem`** (`padding: 0.5rem`, `border-radius: 0.5rem`). Use `px`
  for fixed widget dimensions and borders (`width: 660px`, `border: 2px solid ...`).
- Use **flexbox** for layout (`display: flex; flex-direction: column; flex-basis: 12.5%;`).
- Write one declaration per line, 4-space indentation, and a blank line between rules.
- Use ids (`#fb-file-input`) only to target a specific widget element, and classes for
  everything styled.
- Short per-page stylesheets are named `style.css`. Component stylesheets are named after
  the component (`file_browser.css`).

---

## 20. JSON / Config Files

- **4-space indentation**, one key per line, and **one list item per line**, even for
  single-item lists:
  ```json
  {
      "devmode": "active",
      "tools": {
          "scene_transfer": {
              "to": [
                  "${USER}"
              ],
              "cc": [
                  "${USER}"
              ]
          }
      }
  }
  ```
- Group per-tool settings under a top-level `"tools"` object, keyed by the tool's
  snake_case package name.
- Use **`${VAR}` environment interpolation** for user-specific values.
- **Layered configs:** a base file that includes `global`, `dev`, and per-context
  overrides. Every new tool gets a block in the global and dev layers.

---

## 21. Web App (Flask) Project Structure

```
<app_name>/
    app.py                   # create_app() factory + index route + main() for local runs
    <app_name>.wsgi          # WSGI entry point
    core/                    # app-wide helpers
        app.py               #   app utilities (links, recently-visited, ...)
        blueprint.py         #   sub_render_template / sub_url_for / sub_redirect
        setup.py             #   registers blueprints, template globals, config
        settings.py
        template.py
        widget.py
        mail.py
    templates/               # base layouts (index.html, tools/index.html, tools/done.html)
    static/
        utils/
            general.js       # shared DOM helpers ($, toggleVisibility, addOptions, ...)
            routing.js       # ajax helpers + urlFor()
    blueprints/
        api/<service>/       # JSON endpoints, one blueprint per backend service
            __init__.py
        tools/<tool_name>/   # one blueprint per user-facing tool page
            __init__.py      #   the Blueprint + its routes
            [_api.py, _utils.py, _constants.py]   # when the tool grows
            static/
                <tool_name>.js
                style.css
            templates/<tool_name>/
                index.html
        widgets/<widget_name>/   # reusable UI components (file_browser, selector, ...)
            __init__.py      #   the Blueprint + any data routes the widget needs
            static/<widget_name>.js, <widget_name>.css
            templates/<widget_name>/widget.html
```

Rules:
- **One blueprint per tool, API service, or widget**, each a self-contained package with
  its own `static/` and `templates/<name>/` (namespaced so template names don't
  collide). Include a `blank` tool blueprint as the copy-me template.
- **Use an app factory:** `create_app(wsgi_prefix=None)` builds the `Flask` app, adds
  app-level routes with `add_url_rule`, and delegates blueprint registration to
  `core.setup.setup(...)`.
- A `main()` runs it locally (`app.run(debug=True, use_reloader=False,
  host='0.0.0.0', threaded=True)`) under `if __name__ == '__main__':`.
- **Blueprint module shape:**
  ```python
  # Initialize the blueprint
  bp = Blueprint(__name__, __name__, template_folder='templates', static_folder='static')


  # Index page
  @bp.route('/', methods=['GET', 'POST'])
  def index():
      """
      The index page
      """
      if request.method == 'GET':
          return bu.sub_render_template(bp, 'index.html',
                                        title='Transfer Scene',
                                        description='Transfer a scene to a shot directory',
                                        help_page='https://docs.example.com/...')

      if request.method == 'POST':
          project = request.form.get('project')
          ...
          return render_template('tools/done.html',
                                 title='Transfer Scene',
                                 message='Scene transfer submitted',
                                 back_button_txt='Back to Tool')
  ```
  - Branch on `request.method` with **two separate `if` blocks**, not `if/else`.
  - Read form fields with `request.form.get('<kebab-id>')`, matching the HTML ids.
  - Long-running work is **submitted as a background job**, never run in the request.
    The POST renders a shared `done.html` confirmation page.
  - Pass `title`, `description`, and `help_page` to every tool page.
- Widgets with data needs expose their own small routes on their blueprint (e.g.
  `/get_quick_links`), documented with `:response: (jsn) ...`.
- Validate user-supplied filesystem paths against an allow-list constant
  (`ALLOWED_ROOTS = [...]`) with `os.path.realpath` plus `startswith`.
- Front-end naming mirrors the back end: blueprint `tools/transfer_scene`, JS module
  `app.tools.transfer_scene`, files `transfer_scene.js` and
  `templates/transfer_scene/index.html`.

---

## 22. Decision Heuristics (how the author thinks)

1. **Is it a tool?** Make a package with the standard skeleton (§2): one core
   `CamelCase` class, a thin `main.py` or `_api.py`, `constants.py`, and `utils.py`. For
   a web tool, add a blueprint with the same name (§21).
2. **The constructor takes all inputs**, stores them as `self._private`, initializes all
   derived state, then calls `self._check_args()`.
3. **Expose state via read-only properties.** Expose behavior via a few verb-named public
   methods, with `run()` / `do_*()` as the orchestrator.
4. **Break work into small private `_step()` methods**, each logged and preceded by a
   one-line comment in the orchestrator.
5. **Lift every constant, path template, and regex into `constants.py`.**
6. **Validate early and raise a custom `<Tool>Error`.** Wrap the entry point with the
   error-report decorator.
7. **Log every meaningful step.** Never `print`.
8. **Send an email summary** at the end of user-facing operations. Build it as a list of
   lines joined together, with recipients from config and a team-list fallback.
9. **Respect a `dry` flag** wherever an operation touches the filesystem or an external
   service.
10. **Dispatch heavy work to a background job** from CLIs and web routes. Don't run it
    inline.
11. **Prefer duplicating a proven template over premature abstraction.** The author will
    copy an entire tool (one transfer tool to another, near-identical) and substitute
    specifics, rather than build a shared base class. When two tools are the same shape,
    mirror the existing one closely and keep the twins parallel when changing either.
12. **Same habits in every language:** guard clauses, step-labeling comments, aligned
    doc columns, verb-first names, explicit over clever.

---

## 23. Quick Reference Templates

### Python tool class
```python
#!/usr/bin/env python
# Copyright (c) 2026 <Owner>. All rights reserved.
"""
Do the thing this module exists to do, described imperatively.
"""
import os
from builtins import object

from core import mail
from core import logger
from core import settings

from tools.my_tool import utils
from tools.my_tool import constants


logger.setup('tools.my_tool')


class MyTool(object):
    def __init__(self, source, project, dry=False):
        """
        Initialize the tool

        :param source:  (str)  the source path
        :param project: (str)  the name of the project
        :param dry:     (bool) whether to skip side effects
        """
        self._source = source
        self._project = project
        self._dry = dry
        self._results = []

        # Check that the provided arguments are valid
        self._check_args()

    @property
    def source(self):
        return self._source

    def _check_args(self):
        """
        Check the provided arguments to ensure they are valid
        """
        if not self._project:
            raise utils.MyToolError('Must specify a project')

    def _do_step(self):
        """
        Do a single step of the work
        """
        logger.info('Doing the step for {}'.format(self._source))
        if self._dry:
            return
        ...

    def _send_summary(self):
        """
        Email a summary of the run
        """
        if self._dry:
            return
        try:
            cc_users = settings.TOOLS['my_tool']['cc']
        except KeyError:
            cc_users = ['TEAM-LIST']
        body = [
            'Project: {}'.format(self._project),
            'Source: {}'.format(self._source)
        ]
        mail.send('My Tool Summary', '<br/>'.join(body), to_users=os.environ['USER'],
                  cc_users=cc_users, message_type='html')

    def run(self):
        """
        Run the tool
        """
        logger.info('Starting MyTool for {}'.format(self._source))

        # Do the first step
        self._do_step()

        # Report the outcome
        self._send_summary()
```

### CLI dispatcher (`bin/myTool`)
```python
#!/usr/bin/env python
# Copyright (c) 2026 <Owner>. All rights reserved.
"""
Dispatch My Tool to the job queue.
"""
import os
import sys
import argparse

from core import logger
from core import decorators
from jobs.queue import SubmitJob


logger.setup('bin.myTool')


def dispatch(args):
    # Build the script arguments
    script_args = [
        'source=\'{}\''.format(args.source),
        'project=\'{}\''.format(args.project),
        'dry={}'.format(args.dry)
    ]
    script_args = ', '.join(script_args)

    # Build the script
    script = ('python -c "from tools.my_tool import MyTool; '
              'MyTool({0}).run()"'.format(script_args))
    logger.info('Job command: {}'.format(script))
    if args.dry:
        return

    # Create and submit the job
    job = SubmitJob(title='My Tool ({})'.format(args.project), commands=[script])
    job.submit()
    logger.info('Job ID: {0}'.format(job.id))


@decorators.error('My Tool Error Report')
def main():
    # Parse the arguments
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='\033[0;94m(Required)\033[0;0m the source path')
    parser.add_argument('-p', '--project', default=os.getenv('PROJECT'), help='the name of the project')
    parser.add_argument('-d', '--dry', action='store_true', help='log the job without submitting it')

    try:
        args = parser.parse_args()
    except SystemExit:
        if len(sys.argv) > 1:
            raise
        return

    # Check the arguments
    if not args.project:
        logger.error('Must specify a project')
        return

    dispatch(args)


if __name__ == '__main__':
    main()
```

### JavaScript page module (`static/my_tool.js`)
```javascript
/*
Copyright (c) 2026 <Owner>. All rights reserved.
*/
window.app = window.app || {};
app.tools = app.tools || {};
app.tools.my_tool = (function() {
    let self = {};

    self.required = ['project', 'source'];

    /**
     * Toggle the submit button based on whether all requirements have been met
     */
    self.toggleSubmitButton = function() {
        $('submit').disabled = !isFilled(...self.required);
    };

    /**
     * Callback function for changing context
     */
    self.onChangeContext = function() {
        const source_input = $('source');
        if (!source_input.value) {
            toggleVisibility('source-options', false);
        }
        else {
            toggleVisibility('source-options', true);
        }

        // Toggle the submit button
        self.toggleSubmitButton();
    };

    /**
     * Set up the tool
     * @param dept {string} the department the tool was opened from
     */
    self.setup = function(dept) {
        // Add event listeners for changing context
        for (const id of self.required) {
            $(id).addEventListener('change', self.onChangeContext);
        }

        self.onChangeContext();
    };

    return self;
})();
```

### CSS component (`static/my_widget.css`)
```css
/*
 * Copyright (c) 2026 <Owner>. All rights reserved.
*/
/* -------- My Widget -------- */

.mw {
    display: flex;
    border: 2px solid hsl(0, 0%, 10%);
    border-radius: 0.5rem;
    background-color: hsl(0, 0%, 20%);
}

.mw__button {
    cursor: pointer;
}

.mw__button:hover {
    color: white;
    background-color: hsl(0, 0%, 35%);
}
```

---

## Appendix: Python-3-only projects
Keep everything else. These rules relax:
- `class Foo(object)` → `class Foo:` is acceptable, but keep `(object)` if the file
  already uses it.
- Drop `from builtins import object` / `__future__` / `past` imports.
- `super(Foo, self)` stays (the author's habit). Still no f-strings, type hints,
  `pathlib`, or dataclasses. Those are style choices, not just compat.
