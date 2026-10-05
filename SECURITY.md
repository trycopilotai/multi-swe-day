# Security

## Reporting a vulnerability

Report privately through GitHub:
<https://github.com/trycopilotai/multi-swe-day/security/advisories/new>

That opens a private security advisory visible only to the
maintainers. Do not put the details of a vulnerability in a
public issue.

If that link shows "Not Found", private reporting is not
turned on for this repository. Open a public issue titled
"Security report waiting" that says only that you have a
report, with no details, and a maintainer will arrange a
private channel.

## What is in scope

- **Prompt content that redirects an agent.** `SKILL.md`,
  `references/PROTOCOL.md` and the three prompt files are
  instructions that several agents follow through a whole
  run, including commits and a landing step. Text in any of
  them that makes an agent push to a shared repository,
  write outside its lanes, skip a human gate, or treat
  message content as instructions is a valid report.
- **The registry program.**
  `skills/multi-swe-day/scripts/msd_lane_registry.py` reads
  and rewrites one JSON file at the path `--registry` names,
  through a temporary file beside it, and creates that
  file's parent directory. With `--lock-path` it also reads
  `metadata.json` inside that directory. A pair of lanes it
  accepts for two different builders, neither `aborted`,
  where one path equals the other or is its ancestor, is a
  valid report. So is a call with a non-empty `--lock-path`
  that changes the registry while stating an owner other
  than the one in the metadata, or a session id other than a
  non-empty one the metadata records.
- **The listener.** `skills/multi-swe-day/scripts/msd_listen.py`
  runs `git fetch`, `git for-each-ref`, `git ls-tree` and
  `git show` in `--repo`, prints envelopes as JSON lines, and
  writes one seen-state file, through a `.tmp` file beside
  it. The file's directory is `--repo` joined with
  `--state-dir` after trailing slashes are removed, so a
  relative `--state-dir` without `..` lands inside `--repo`,
  one with `..` can leave it, one made only of slashes is
  treated as empty, and any other absolute one replaces
  `--repo`. The directory is created when it is
  missing. A message on the
  remote that makes it write anywhere else is a valid
  report.
- **The banner.** `skills/multi-swe-day/scripts/msd_next.py`
  reads the registry file and, with `--lock-path`, the lock
  metadata, and prints the banner: one line when nothing
  is active, otherwise two to four. It writes no file.
- **The review helper.**
  `skills/multi-swe-day/scripts/msd_review_open.py` runs
  `git diff` in `--repo`, writes `.diff` files, a checklist,
  two placeholder files and a `.vscode/settings.json` into
  `--review-dir` or a new temporary directory, and, unless
  `--no-open` is passed, runs the macOS `open` command and
  then, unless `--no-position` is passed, `osascript`. A
  changed-file name that makes it
  write outside the review directory is a valid report.
  The revisions given as `--range`, `--base` and `--head`
  are the caller's: they are passed to `git diff` as given.
- **The install blocks.** The two README blocks run
  `mkdir -p`, `mktemp -d`, `git clone`, `cp`, `mv` and
  `rm -rf`, all inside one skills directory under `$HOME`. A
  repository state that makes either block write or delete
  outside its install target is in scope.
- **The build scripts.** `assets/build.py` finds a Chrome or
  Chromium binary from a fixed candidate list, runs it
  headless with a temporary profile directory, and writes
  the preview PNG and its stamp. `scripts/generate_demo.py`
  writes two SVG files; `scripts/verify_demo.py` only reads.
  `scripts/record_session.py` copies `skills/` into a
  temporary directory, runs two of the programs there
  through `bash`, and rewrites the transcript and the
  manifest. The tests create temporary directories and git
  repositories under the system temporary directory and
  leave some of them behind.

## The programs coordinate; they do not enforce

These are known limits, not findings. The programs validate
little of what they read, so the lists below are the cases
known at release, not a full account of how malformed input
can fail.

### The registry

- **Lanes are bookkeeping.** The registry compares the path
  strings it is given. It does not look at a repository, so
  it cannot tell whether a builder edits only its lanes.
  Comparison is by path component and case-sensitive. It
  does not resolve symbolic links, expand globs, trim
  surrounding spaces, normalize Unicode, or treat a
  backslash as a separator.
- **What `register` lets through.** A builder whose status
  is `aborted` does not block a new registration.
  Registering a slug that already has a row replaces that
  row, whatever its status, and sets it back to `proposed`.
  `release` removes a row at any status. `aborted` can be
  set only from `reported`. Lanes are compared with other
  builders' lanes, not with each other, so one `register`
  call may carry lanes that overlap among themselves. The
  role and slug values are stored as given.
- **The lock check is opt-in and advisory.** It runs only
  when a non-empty `--lock-path` is passed. It compares
  `--lock-owner`, and `--session-id` when the metadata
  records a non-empty one, with plain strings in
  `metadata.json`. Any caller that can read that file can
  state them.
- **Writes are not serialized.** Every write goes through
  one temporary file with a fixed name. Two registry
  commands that run at once can lose one of the two writes
  or leave a file that is not valid JSON.
- **Malformed input ends in a traceback.** A registry file
  or lock metadata that is not valid JSON, or is JSON but
  not an object of the expected shape, and lock metadata
  with a `schema_version` that is neither 1 nor null are
  not handled.
- **Paths are the caller's.** A relative `--registry` or
  `--lock-path` is resolved against the current directory,
  not against a repository root.
- **Two options do nothing new.** `adopt` is another name
  for `init`. `register` accepts `--leader` and ignores it.
- **Two commands skip steps.** `init` on a registry that
  already exists prints it and does not check the lock.
  `run-advance` on a missing registry creates one, with
  `leader` set to the `--lock-owner` value or to the word
  `leader`.

### Human gates and the banner

- **Human gates are text.** `run-advance` records whatever
  phase, owner, gate and note the caller passes, replacing
  the previous run object, a pending gate included. It does
  not require that an earlier gate was cleared.
  `run-clear-gate` clears only a gate that `run-advance`
  recorded; it refuses when the banner merely derived a
  human phase. The program cannot tell an operator from an
  agent; the skill text is what tells an agent to stop at a
  gate.
- **`--owner` is stored, not used.** The banner takes OWNER
  from its own phase model and from a recorded blocking
  gate. `run-advance --phase build --owner human` renders
  `OWNER: agent`.
- **One derived phase can pass a review.** With no recorded
  `run.phase`, a mix of `reported` and `landed` rows derives
  `reconcile`, an agent phase, and so does a status the
  model does not know. Landed rows left in the registry
  beside newly reported ones therefore render
  `OWNER: agent`. The protocol has the leader record
  `human-review` with its gate when all lanes are reported;
  the derivation alone does not hold that gate.
- **Other banner behaviour.** A note recorded with
  `run-advance --note` is free text, printed as one line.
  It replaces the banner's action text in an agent-owned
  phase with no blocking gate; in a human-owned phase, or
  while a gate blocks, it is printed on a `note:` line of
  its own under the operator's action. A note that is only
  whitespace leaves the action text empty in an agent-owned
  phase. A run whose rows are all `aborted` derives `plan`. After `run-clear-gate` on a recorded human phase the
  banner still says the gate is unmet until the leader runs
  `run-advance`. All lanes `landed` derives `done`, with
  nothing said about the push gate. A `run.phase` the model
  does not know is ignored and the phase is derived. A
  registry file or lock metadata that is not valid JSON, or
  not an object of the expected shape, ends `render` with a
  Python traceback.

### The listener

- **It trusts the remote.** It prints `response` and `error`
  envelopes found on any `gitchat/*-outbox` branch of the
  remote whose `to` field is the given slug. The `from`
  field is not checked. Anyone who can push to that remote
  can put text in front of the leader.
- **One bad file can stop it.** Each of these ends every
  run with a traceback until the file is gone: a message
  file that is not valid UTF-8; one whose JSON is valid but
  is not an object; an object whose `id` is a non-empty
  list or object, or whose `kind` is a list or an object;
  and envelopes whose `created_at` or
  `id` values are of mixed types, which fail in sorting. A
  non-string `id` can also fail while the seen-state is
  being saved, after printing, so the same envelopes print
  again on every run. A file that is UTF-8 text but not JSON
  is skipped.
- **Some envelopes are never printed.** One with no `id`,
  or an `id` that is empty, zero, false or null, is
  dropped. When two files on different branches carry the
  same `id`, only the first one read is considered, before
  the `kind` and `to` checks. A file whose name git prints
  quoted (non-ASCII bytes, for example) is skipped.
- **Printing and recording are two steps.** Each envelope
  is flushed to the output, and the ids of the batch are
  recorded as seen after the batch is printed. A run killed
  between the two prints that batch again next time.
- **The slug check is loose.** A slug that ends with one
  newline is accepted.
- **Seen-state.** A seen-state file that is missing or is
  not JSON is treated as empty, so every matching envelope
  is printed again. Its shape is not checked: an object
  without `seen` is empty, a string or an object under
  `seen` is read as its characters or its keys, and other
  shapes (a top-level list, or `seen` that is null, a
  number, or a list holding lists or objects) end the run
  with a traceback. `--all` and `--no-mark` repeat
  envelopes by design; `--all` without `--no-mark` still
  records the ids it prints. An empty `--mark-seen` value is
  ignored and the stream loop starts.
- **A failed `git fetch` is not reported.** The listener
  then reads the refs it already has.
- **`--repo` is the top level.** With a `--repo` that is a
  subdirectory of the work tree, message paths do not
  resolve and no envelope is read.

### The review helper

- **It is for macOS and one machine.** Opening uses `open`
  and `osascript`. Window positioning moves the first two
  VS Code windows it finds, without checking which they
  are, and does nothing more when it finds none. The
  temporary review directory is not removed.
- **Not every change gets a faithful diff.** File names are
  read from `git diff --name-only` as git prints them. A
  name git quotes (non-ASCII bytes, quotes, control
  characters) gets an empty `.diff` and a normal checklist
  line. A rename is listed under its new path only, so the
  old path's removal is in no `.diff`. Leading and trailing
  whitespace of each diff is stripped. `a...b` is diffed as
  `a..b`. Each name is passed back to git as a pathspec, so
  a name with glob characters or pathspec magic can pull in
  other files' changes or miss its own. A `--repo` that is
  a subdirectory of the work tree gets empty or wrong
  diffs; pass the top level. When every changed file is
  skipped, the checklist says no file changed.
- **The checklist names local paths.** `CHECKLIST.md`
  carries the absolute paths of the repository and of the
  review directory on the operator's machine.
- **`--skip-glob` is a plain wildcard match.** `*` also
  matches `/`, so `gen/*` skips everything below `gen/`.
- **File names can collide.** Two changed files whose paths
  differ only by `/` and `-` share one `.diff` file name,
  and the later one wins. A reused `--review-dir` keeps
  earlier `.diff` files, and they are opened with the new
  ones.
- **Revisions are not checked.** A `--range` or `--base`
  value that starts with `-` is read by git as an option.
  A malformed range, an unknown revision or any
  other git failure, a flattened name too long for the file
  system, and a diff that is not UTF-8 each end in a
  traceback.

## What is out of scope

gitchat, the swe-day lock, the review method and the
editor extension the text names are separate projects. So
are Claude Code, Codex and any other host. Report those to
their own maintainers.
