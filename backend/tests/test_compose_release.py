"""The cloud stack runs the release its .env names, and nothing else (deploy/cloud/compose.yml).

`${VERITY_TAG:-local}` once let a missing or mistyped tag start whatever stale `:local` build the host still had
(war room F-16, 2026-10-13). Every image this repository builds now requires the tag; images pulled by digest are
unaffected. `docker compose config` with no tag exits 1 naming the variable (evidence/r13-compose-notag.txt).
"""

from __future__ import annotations

import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[2] / "deploy" / "cloud" / "compose.yml"
ENV_EXAMPLE = COMPOSE.with_name("env.example")
README = COMPOSE.with_name("README.md")


def _images() -> list[str]:
    """Every image reference, whole: a required variable's message holds spaces."""
    return [line.split("image:", 1)[1].strip() for line in COMPOSE.read_text(encoding="utf-8").splitlines() if line.strip().startswith("image:")]


def test_every_image_built_here_requires_the_release_tag() -> None:
    images = _images()
    ours = [image for image in images if image.startswith("verity-")]
    assert len(ours) == 2, images
    for image in ours:
        assert re.fullmatch(r"verity-(api|web):\$\{VERITY_TAG:\?[^}]+\}", image), image


def test_control_images_from_elsewhere_are_pinned_by_digest() -> None:
    images = _images()
    for image in images:
        if not image.startswith("verity-"):
            assert "@sha256:" in image, image


def test_the_runbook_builds_saves_and_runs_the_tagged_release() -> None:
    """The runbook failed against the required tag: its archive saved `:local`, env.example had no tag line, and the tag
    was appended to .env before .env was copied over it from env.example (war room W5, r13-runbook.txt)."""
    assert re.search(r"^VERITY_TAG=$", ENV_EXAMPLE.read_text(encoding="utf-8"), re.M), "env.example names the tag, empty until set"
    readme = README.read_text(encoding="utf-8")
    build = readme.split("## Build, and gate the image", 1)[1].split("```", 2)[1]
    assert ":local" not in build and "docker save verity-api:$VERITY_TAG verity-web:$VERITY_TAG" in build, build
    assert readme.index("cp env.example .env") < readme.index("echo VERITY_TAG=<sha> >> .env"), "the tag is set after .env is copied"


DOCKERFILES = [COMPOSE.with_name("Dockerfile.api"), COMPOSE.with_name("Dockerfile.web")]
ORACLE = COMPOSE.with_name("HETZNER.md")


def test_the_store_is_named_by_the_host_and_required() -> None:
    """A staging store must not become a production one by being left in place: the volume's name is the host's to give,
    and compose refuses to start without one (release integration, 2026-10-13)."""
    compose = COMPOSE.read_text(encoding="utf-8")
    assert re.search(r"verity-data:\n(?:\s*#.*\n)*\s+name: \$\{VERITY_STORE:\?[^}]+\}", compose), "the store volume's name is required"
    assert re.search(r"^VERITY_STORE=$", ENV_EXAMPLE.read_text(encoding="utf-8"), re.M)


def test_the_hosts_configuration_and_credentials_live_outside_the_release() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    for mounted in ("/.env", "/tunnel.json:", "/contract-state.json:"):
        assert "${VERITY_SHARED:-.}" + mounted in compose, mounted
    assert "./tunnel.json" not in compose and "env_file: .env" not in compose


def test_every_image_built_here_names_its_commit_and_is_never_pulled() -> None:
    for dockerfile in DOCKERFILES:
        assert "LABEL org.opencontainers.image.revision=$VERITY_BUILD_SHA" in dockerfile.read_text(encoding="utf-8"), dockerfile.name
    compose = COMPOSE.read_text(encoding="utf-8")
    assert compose.count("pull_policy: never") == 2 and compose.count("VERITY_BUILD_SHA: ${VERITY_BUILD_SHA:-}") == 2


def test_the_runbook_unpacks_each_release_once_into_a_directory_of_its_own() -> None:
    """Each archive was unpacked over /opt/verity: tar removes nothing, so a file a commit deleted stayed in the next
    build's context (release integration, 2026-10-13)."""
    runbook = ORACLE.read_text(encoding="utf-8")
    assert not re.search(r"tar -x\w*f [^\n]* -C /opt/verity(\s|$)", runbook), "never unpacked over the shared root"
    assert 'test ! -e $R || { echo "$R exists' in runbook and "R=/opt/verity/releases/$SHA" in runbook
    assert "up -d --no-build" in runbook and "docker compose up -d\n" not in runbook
    assert "tar -tzf verity-$SHA.tar.gz | grep -E" in runbook, "the archive is checked for secrets before it leaves"
    assert "org.opencontainers.image.revision" in runbook, "each image's label is checked against the commit"


def test_every_compose_command_on_the_released_host_reads_the_shared_configuration() -> None:
    """Without `--env-file`, compose on the release layout stops at the missing VERITY_STORE and VERITY_TAG, and from the
    old tree it opens the staging store whatever the host's role (counter-review S2 and S4, 2026-10-13)."""
    runbook = ORACLE.read_text(encoding="utf-8")
    commands = [line for line in runbook.splitlines() if "docker compose " in line]
    assert len(commands) >= 5, commands
    for line in commands:
        assert "docker compose --env-file /opt/verity/shared/.env " in line, line
    assert "Never run compose from the old tree" in runbook
    schema_check = next(line for line in commands if " run --rm " in line)
    assert schema_check.startswith("VERITY_TAG=$TAG "), "the first release's .env has no tag yet"
    assert "mode=ro" in runbook, "a check of the store must never create one"
    assert "--env-file /opt/verity/shared/.env" in README.read_text(encoding="utf-8")


def _service(name: str) -> str:
    """The service's block of compose.yml, as text: from its name to the next service or top-level key."""
    text = COMPOSE.read_text(encoding="utf-8")
    start = text.index(f"\n  {name}:\n")
    end = re.search(r"\n  [a-z]+:\n|\n[a-z]+:", text[start + 1 :])
    return text[start : start + 1 + end.start()] if end else text[start:]


def test_the_model_is_reachable_from_the_api_only_and_writes_no_core() -> None:
    """The model holds questions and contracts' sections in memory (review of the Hetzner kit, 2026-10-16): it publishes
    no port, joins only the model network, which only the API also joins, writes no core file and keeps no capability."""
    model = _service("ollama")
    assert "ports:" not in model
    assert re.search(r"networks:\n\s+- model\n", model) and "- default" not in model
    assert re.search(r"ulimits:\n\s+core: 0", model) and re.search(r"cap_drop:\n\s+- ALL", model)
    assert re.search(r"networks:\n\s+- default\n\s+- model\n", _service("api"))
    for other in ("web", "caddy", "tunnel"):
        assert not re.search(r"\bmodel\b", re.sub(r"#.*", "", _service(other))), other


def test_the_deployment_says_the_model_is_on_this_server() -> None:
    """Its address is a container name, not loopback: unsaid, the interface would tell visitors their text goes to a
    hosted model that sleeps."""
    env = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert re.search(r"^WORKBENCH_OLLAMA_URL=http://ollama:11434$", env, re.M)
    assert re.search(r"^WORKBENCH_MODEL_ON_SERVER=1$", env, re.M)
    assert not re.search(r"^WORKBENCH_MODEL_HOST=\S", env, re.M)
