#!/usr/bin/env python3
"""The packaging contract.

Facts this repository states in more than one place are
pinned here where a script can compare them: the name and
version, the claim and the transcript behind it, the demo
images, the install blocks, and the evidence hashes.

Runs offline with the standard library and `git`:

    python3 tests/test_integrations.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "multi-swe-day"
PACKAGE = ROOT / "skills" / NAME
REGISTRY = PACKAGE / "scripts" / "msd_lane_registry.py"
BANNER = PACKAGE / "scripts" / "msd_next.py"
SKILL = PACKAGE / "SKILL.md"
README = ROOT / "README.md"
TRANSCRIPT = ROOT / "evidence" / "transcripts" / "registry-session.txt"
MANIFEST = ROOT / "evidence" / "demo-manifest.json"
INVOCATIONS = ROOT / "evidence" / "transcripts"
RENDERER = ROOT / "scripts" / "render_invocation.py"
CLAIM = "The lane registry refuses overlapping lanes."
REFUSAL = "lane conflict: 'src' overlaps 'src/auth' held by 'builder-a'"
REPOSITORY = "https://github.com/trycopilotai/" + NAME


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest(product: str) -> dict:
    return json.loads(read(ROOT / product / "plugin.json"))


def frontmatter(text: str) -> dict:
    """The `key: value` pairs between the two `---` lines."""
    lines = text.splitlines()
    if lines[0] != "---":
        raise AssertionError("SKILL.md does not open with frontmatter")
    end = lines.index("---", 1)
    fields: dict = {}
    key = None
    for line in lines[1:end]:
        match = re.match(r"^([a-z_-]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            fields[key] = match.group(2).strip()
            continue
        if key is None or not line.startswith(" "):
            raise AssertionError("unexpected frontmatter line: " + line)
        fields[key] = (fields[key] + " " + line.strip()).strip()
    for name, value in fields.items():
        if value.startswith(">-"):
            fields[name] = value[2:].strip()
    return fields


def interface_yaml(text: str) -> dict:
    """The quoted scalars under `interface:` in agents/openai.yaml."""
    lines = text.splitlines()
    if lines[0] != "interface:":
        raise AssertionError("openai.yaml does not start with interface:")
    fields: dict = {}
    key = None
    for line in lines[1:]:
        match = re.match(r"^  ([a-z_]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            fields[key] = match.group(2).strip()
            continue
        fields[key] = (fields[key] + " " + line.strip()).strip()
    for name, value in fields.items():
        if not (value.startswith('"') and value.endswith('"')):
            raise AssertionError(name + " is not a double-quoted scalar")
        fields[name] = value[1:-1]
    return fields


def install_blocks() -> list:
    return re.findall(r"```sh\nset -eu\n(.*?)```", read(README), flags=re.S)


class LayoutTest(unittest.TestCase):
    def test_skill_is_a_symlink_into_the_canonical_package(self) -> None:
        link = ROOT / "skill"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(str(link)), "skills/" + NAME)
        self.assertFalse(PACKAGE.is_symlink())

    def test_package_holds_what_the_readme_says_it_installs(self) -> None:
        for relative in (
            "SKILL.md",
            "agents/openai.yaml",
            "references/PROTOCOL.md",
            "references/leader.prompt.md",
            "references/builder.prompt.md",
            "references/auditor.prompt.md",
            "scripts/msd_lane_registry.py",
            "scripts/msd_listen.py",
            "scripts/msd_next.py",
            "scripts/msd_review_open.py",
            "scripts/test_msd_lane_registry.py",
            "scripts/test_msd_next.py",
            "scripts/msd_listen_test.py",
        ):
            self.assertTrue((PACKAGE / relative).is_file(), relative)

    def test_the_four_programs_are_committed_executable(self) -> None:
        modes = {}
        for line in git("ls-files", "--stage", "--", "skills").splitlines():
            mode, _, rest = line.partition(" ")
            modes[rest.split("\t", 1)[1]] = mode
        for name in (
            "msd_lane_registry.py",
            "msd_listen.py",
            "msd_next.py",
            "msd_review_open.py",
        ):
            path = "skills/%s/scripts/%s" % (NAME, name)
            self.assertEqual(modes[path], "100755", path)

    def test_history_has_no_co_author_trailer(self) -> None:
        messages = git("log", "--all", "--format=%B")
        self.assertNotIn("co-authored-by", messages.lower())


class SkillTest(unittest.TestCase):
    def test_frontmatter_is_name_and_description_only(self) -> None:
        fields = frontmatter(read(SKILL))
        self.assertEqual(sorted(fields), ["description", "name"])
        self.assertEqual(fields["name"], NAME)
        self.assertRegex(NAME, r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertLessEqual(len(NAME), 64)
        self.assertTrue(fields["description"])
        self.assertLessEqual(len(fields["description"]), 1024)

    def test_skill_stays_under_five_hundred_lines(self) -> None:
        self.assertLess(len(read(SKILL).splitlines()), 500)

    def test_files_the_skill_points_at_exist(self) -> None:
        text = read(SKILL)
        for relative in (
            "scripts/msd_lane_registry.py",
            "scripts/msd_listen.py",
            "scripts/msd_next.py",
            "scripts/msd_review_open.py",
            "references/PROTOCOL.md",
        ):
            self.assertIn(relative, text)
            self.assertTrue((PACKAGE / relative).is_file(), relative)


class ManifestTest(unittest.TestCase):
    def test_both_manifests_agree(self) -> None:
        claude = manifest(".claude-plugin")
        codex = manifest(".codex-plugin")
        for field in (
            "name",
            "version",
            "description",
            "license",
            "homepage",
            "repository",
            "skills",
        ):
            self.assertEqual(claude[field], codex[field], field)
        self.assertEqual(claude["name"], NAME)
        self.assertEqual(claude["skills"], "./skills/")
        self.assertEqual(claude["repository"], REPOSITORY)
        self.assertEqual(claude["license"], "MIT")
        self.assertRegex(claude["version"], r"^\d+\.\d+\.\d+$")

    def test_a_release_tag_on_head_is_the_manifest_version(self) -> None:
        tags = git("tag", "--points-at", "HEAD").split()
        releases = [tag for tag in tags if tag.startswith("v")]
        if not releases:
            self.skipTest("HEAD carries no release tag")
        self.assertEqual(releases, ["v" + manifest(".claude-plugin")["version"]])

    def test_codex_interface_matches_the_agent_file(self) -> None:
        interface = manifest(".codex-plugin")["interface"]
        for field in (
            "displayName",
            "shortDescription",
            "longDescription",
            "developerName",
            "category",
            "websiteURL",
        ):
            self.assertTrue(interface.get(field), field)
        prompts = interface["defaultPrompt"]
        self.assertEqual(len(prompts), 1)
        self.assertIn("$" + NAME, prompts[0])
        agent = interface_yaml(read(PACKAGE / "agents" / "openai.yaml"))
        self.assertEqual(agent["default_prompt"], prompts[0])
        self.assertEqual(agent["display_name"], interface["displayName"])
        self.assertEqual(agent["short_description"], interface["shortDescription"])


class ReadmeTest(unittest.TestCase):
    def test_claim_is_on_its_own_line(self) -> None:
        self.assertIn(CLAIM, read(README).splitlines())

    def test_transcript_shows_the_refused_overlapping_register(self) -> None:
        lines = read(TRANSCRIPT).splitlines()
        registers = [
            i for i, line in enumerate(lines) if line.startswith("$ reg register")
        ]
        self.assertEqual(len(registers), 3)
        self.assertTrue(lines[registers[0]].endswith("--lane src/auth"))
        self.assertTrue(lines[registers[1]].endswith("--lane src"))
        second = lines[registers[1] : registers[2]]
        self.assertEqual(
            second,
            [second[0], REFUSAL, '$ echo "exit status: $?"', "exit status: 4"],
        )

    def test_each_install_block_pins_the_manifest_version(self) -> None:
        version = manifest(".claude-plugin")["version"]
        blocks = install_blocks()
        self.assertEqual(len(blocks), 2)
        roots = []
        for block in blocks:
            self.assertEqual(
                re.findall(r"^release=(\S+)$", block, flags=re.M),
                ["v" + version],
            )
            self.assertIn(REPOSITORY + " \\\n", block)
            self.assertIn('--branch "$release"', block)
            target = re.findall(r'^install_target="\$HOME/(\S+)"$', block, flags=re.M)
            self.assertEqual(len(target), 1)
            roots.append(target[0])
        self.assertEqual(
            sorted(roots),
            [".agents/skills/" + NAME, ".claude/skills/" + NAME],
        )

    def test_relative_links_resolve(self) -> None:
        targets = re.findall(r"\]\(([^)#]+)\)", read(README))
        self.assertTrue(targets)
        for target in targets:
            if target.startswith("http"):
                continue
            self.assertTrue((ROOT / target).exists(), target)

    def test_readme_says_what_was_not_measured(self) -> None:
        text = " ".join(read(README).split())
        self.assertIn("No agent ran a multi-swe-day network", text)
        self.assertIn("has not been measured", text)

    def test_demo_is_offered_with_a_reduced_motion_poster(self) -> None:
        text = read(README)
        picture = re.search(r"<picture>(.*?)</picture>", text, flags=re.S)
        self.assertIsNotNone(picture)
        body = picture.group(1)
        self.assertIn('media="(prefers-reduced-motion: reduce)"', body)
        self.assertIn('srcset="assets/poster.svg"', body)
        self.assertIn('src="assets/demo.svg"', body)


class EvidenceTest(unittest.TestCase):
    def test_manifest_hashes_match_the_files(self) -> None:
        record = json.loads(read(MANIFEST))
        self.assertEqual(record["skill"]["sha256"], sha256(SKILL))
        programs = {item["path"]: item["sha256"] for item in record["programs"]}
        self.assertEqual(
            programs,
            {
                str(REGISTRY.relative_to(ROOT)): sha256(REGISTRY),
                str(BANNER.relative_to(ROOT)): sha256(BANNER),
            },
        )
        self.assertEqual(record["output"]["sha256"], sha256(TRANSCRIPT))
        self.assertIs(record["output"]["edited"], False)
        self.assertEqual(record["output"]["transforms"], [])
        self.assertIs(record["agent"]["invoked_the_skill"], False)

    def test_manifest_commands_are_the_ones_in_the_transcript(self) -> None:
        record = json.loads(read(MANIFEST))
        commands = [
            line[2:]
            for line in read(TRANSCRIPT).splitlines()
            if line.startswith("$ ") and not line.startswith("$ echo")
        ]
        self.assertEqual(record["invocation"]["commands"], commands)

    def test_no_recorded_command_passes_a_lock_path(self) -> None:
        record = json.loads(read(MANIFEST))
        for command in record["invocation"]["commands"]:
            self.assertNotIn("--lock-path", command)
        self.assertIn("passes no `--lock-path`", " ".join(read(README).split()))

    def test_an_overlapping_register_is_refused_as_the_transcript_shows(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            command = [
                sys.executable,
                "-B",
                str(REGISTRY),
                "--registry",
                os.path.join(raw, "run", "registry.json"),
            ]
            register = command + [
                "register",
                "--role",
                "builder-NN",
                "--day",
                "D01",
                "--plan-path",
                "plans/d01.md",
            ]

            def run(arguments):
                return subprocess.run(arguments, capture_output=True, text=True)

            created = run(command + ["init", "--leader", "leader"])
            first = run(register + ["--slug", "builder-a", "--lane", "src/auth"])
            ancestor = run(register + ["--slug", "builder-b", "--lane", "src"])
            exact = run(register + ["--slug", "builder-b", "--lane", "src/auth"])
            descendant = run(
                register + ["--slug", "builder-b", "--lane", "src/auth/login.ts"]
            )
            disjoint = run(register + ["--slug", "builder-b", "--lane", "src/billing"])
        self.assertEqual(created.returncode, 0)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(ancestor.returncode, 4)
        self.assertEqual(ancestor.stderr.splitlines(), [REFUSAL])
        self.assertEqual(exact.returncode, 4)
        self.assertEqual(descendant.returncode, 4)
        self.assertEqual(disjoint.returncode, 0)

    def test_transcript_names_no_machine(self) -> None:
        text = read(TRANSCRIPT)
        for marker in ("/var/folders", "/tmp", "/Users/", "/home/", "hostname"):
            self.assertNotIn(marker, text)


class InvocationTest(unittest.TestCase):
    def published(self) -> list:
        record = json.loads(read(MANIFEST))
        return [item for item in record["invocations"] if item["published"]]

    def test_each_client_has_one_published_run(self) -> None:
        self.assertEqual(
            sorted(item["product"] for item in self.published()),
            ["Claude Code", "Codex"],
        )

    def test_transcript_set_is_the_published_runs(self) -> None:
        on_disk = sorted(
            str(path.relative_to(ROOT))
            for path in INVOCATIONS.glob("*-invocation.txt")
        )
        listed = sorted(item["transcript"]["path"] for item in self.published())
        self.assertEqual(on_disk, listed)

    def test_transcript_hashes_match_the_manifest(self) -> None:
        for item in self.published():
            path = ROOT / item["transcript"]["path"]
            self.assertEqual(item["transcript"]["sha256"], sha256(path), path)
            self.assertRegex(item["raw_output_sha256"], r"^[0-9a-f]{64}$")

    def test_every_run_invoked_the_skill_and_says_how_it_ended(self) -> None:
        record = json.loads(read(MANIFEST))
        for item in record["invocations"]:
            self.assertIs(item["invoked_the_skill"], True)
            self.assertTrue(item["outcome"])
            self.assertRegex(item["raw_output_sha256"], r"^[0-9a-f]{64}$")
            if not item["published"]:
                self.assertNotIn("transcript", item)

    def test_declared_transforms_are_known(self) -> None:
        known = {
            "replace-isolation-root",
            "replace-plugin-root",
            "replace-scratch-root",
            "replace-capture-root",
            "replace-home",
            "replace-hostname",
        }
        for item in self.published():
            self.assertTrue(set(item["transforms"]) <= known, item["transforms"])

    def test_transcripts_show_the_skill_being_loaded(self) -> None:
        for item in self.published():
            text = read(ROOT / item["transcript"]["path"])
            if item["product"] == "Claude Code":
                self.assertIn("] Skill\n    skill: multi-swe-day:multi-swe-day", text)
            else:
                self.assertIn(".agents/skills/multi-swe-day/SKILL.md", text)
            self.assertIn(item["invocation"], text)

    def test_transcripts_name_no_machine(self) -> None:
        for path in INVOCATIONS.glob("*-invocation.txt"):
            text = read(path)
            for marker in ("/var/folders", "/private/", "/Users/", "/home/", "/tmp/claude-"):
                self.assertNotIn(marker, text, path)

    def test_readme_links_both_transcripts(self) -> None:
        text = read(README)
        for item in self.published():
            self.assertIn("](" + item["transcript"]["path"] + ")", text)


class RendererTest(unittest.TestCase):
    def render(self, events, *options) -> str:
        with tempfile.TemporaryDirectory() as raw:
            stream = os.path.join(raw, "out.jsonl")
            prompt = os.path.join(raw, "prompt.txt")
            with open(stream, "w", encoding="utf-8") as handle:
                handle.write("\n".join(json.dumps(event) for event in events) + "\n")
            with open(prompt, "w", encoding="utf-8") as handle:
                handle.write("Use the /multi-swe-day skill.\n")
            done = subprocess.run(
                [sys.executable, "-B", str(RENDERER), "claude-code", stream, prompt]
                + list(options),
                capture_output=True,
                text=True,
                check=True,
            )
        return done.stdout

    def call(self, command: str) -> list:
        use = {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": command}}
        result = {"type": "tool_result", "tool_use_id": "t1", "is_error": False}
        return [
            {"type": "assistant", "message": {"content": [use]}},
            {"type": "user", "message": {"content": [result]}},
            {"type": "result", "subtype": "success", "result": "done"},
        ]

    def test_roots_are_replaced_whole_and_in_order(self) -> None:
        text = self.render(
            self.call("ls /x/iso/plugin /x/iso/work/f /x/iso2 /h/u/a"),
            "--isolation-root", "/x/iso",
            "--plugin-root", "/x/iso/plugin",
            "--home", "/h/u",
        )
        self.assertIn("command: ls /iso/plugin /iso/work/f /x/iso2 ~/a", text)
        self.assertIn("    status: ok", text)
        self.assertTrue(text.endswith("## Final message\n\ndone\n"))

    def test_a_root_inside_or_beside_another_path_is_left_alone(self) -> None:
        text = self.render(
            self.call(
                "ls /x/iso /x/iso/a /p/x/iso/a /x/iso-old /x/iso.bak /x/iso2"
                " a/x/iso /x/iso@old /p@/x/iso/a \"/x/iso\" (/x/iso) d=/x/iso\\n"
                " h.example h.example.org sub.h.example"
            ),
            "--isolation-root", "/x/iso",
            "--hostname", "h.example",
        )
        self.assertIn(
            "command: ls /iso /iso/a /p/x/iso/a /x/iso-old /x/iso.bak /x/iso2"
            " a/x/iso /x/iso@old /p@/x/iso/a \"/iso\" (/iso) d=/iso\\n"
            " host h.example.org sub.h.example",
            text,
        )

    def test_a_cut_never_leaves_part_of_a_replaced_path(self) -> None:
        long_root = "/r/" + "d" * 400
        text = self.render(self.call("cd " + long_root + "/w"), "--capture-root", long_root)
        self.assertIn("command: cd /work/w", text)
        self.assertNotIn("/r/d", text)
        cut = self.render(self.call("x" * 301))
        self.assertIn("x" * 300 + " ...[1 more characters]", cut)


class DemoTest(unittest.TestCase):
    def test_images_agree_with_the_transcript(self) -> None:
        verifier = load(ROOT / "scripts" / "verify_demo.py", "verify_demo")
        generator = verifier.load_generator()
        self.assertEqual(verifier.problems_in(generator, read(TRANSCRIPT)), [])


class SocialPreviewTest(unittest.TestCase):
    def test_preview_is_the_size_github_expects(self) -> None:
        header = (ROOT / "assets" / "social-preview.png").read_bytes()[:24]
        self.assertEqual(header[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", header[16:24]), (1280, 640))

    def test_stamp_binds_the_source_and_the_render(self) -> None:
        recorded = {}
        for line in read(ROOT / "assets" / "social-preview.sha256").splitlines():
            value, name = line.split()
            recorded[name] = value
        for name in ("social-preview.html", "social-preview.png"):
            self.assertEqual(recorded[name], sha256(ROOT / "assets" / name), name)

    def test_preview_source_carries_the_claim(self) -> None:
        text = " ".join(read(ROOT / "assets" / "social-preview.html").split())
        self.assertIn(CLAIM, text)


class SupportFilesTest(unittest.TestCase):
    def test_license_is_mit(self) -> None:
        self.assertTrue(read(ROOT / "LICENSE").startswith("MIT License\n"))

    def test_security_names_this_repository_for_reports(self) -> None:
        self.assertIn(
            REPOSITORY + "/security/advisories/new",
            read(ROOT / "SECURITY.md"),
        )

    def test_contributing_names_the_check_command(self) -> None:
        self.assertIn("make check", read(ROOT / "CONTRIBUTING.md"))


if __name__ == "__main__":
    unittest.main()
