import io
import json
import logging
import tarfile
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import anthropic

from github_client import GitHubClient
from jira import JiraClient
from telegram import TelegramClient

logger = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=60)
APPROVAL_TIMEOUT = timedelta(minutes=30)

# Go source files Claude is allowed to analyze and modify
FIXABLE_FILES = [
    "operations/arithmetic.go",
    "handlers/arithmetic.go",
]

ANALYSIS_PROMPT = """\
You are an autonomous software engineer. A Jira incident has been filed for a Go arithmetic REST API.

INCIDENT:
Title: {title}
Description: {description}

SOURCE FILES:
{files}

Your task:
1. Determine if this is a fixable code bug (logic error, missing validation, division by zero, etc.)
2. If fixable, provide the complete corrected file content for each file that needs changes

Respond ONLY with valid JSON in this exact format:
{{
  "fixable": true or false,
  "analysis": "brief explanation of the root cause",
  "fix_description": "one-line description of the fix (empty string if not fixable)",
  "files": [
    {{
      "path": "operations/arithmetic.go",
      "content": "...complete new file content..."
    }}
  ]
}}

Only include files that actually need changes. If not fixable, return an empty array for files.\
"""


@dataclass
class PendingFix:
    issue_key: str
    issue_summary: str
    fix_description: str
    files: list[dict] = field(default_factory=list)  # [{"path", "content", "sha"}]
    proposed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RemediationAgent:
    def __init__(
        self,
        jira: JiraClient,
        telegram: TelegramClient,
        github: GitHubClient,
        anthropic_client: anthropic.Anthropic,
        target_deployment: str,
        target_namespace: str,
        target_image: str,
        github_token: str,
        github_repo: str,
    ):
        self.jira = jira
        self.telegram = telegram
        self.github = github
        self.claude = anthropic_client
        self.target_deployment = target_deployment
        self.target_namespace = target_namespace
        self.target_image = target_image
        self._github_token = github_token
        self._github_repo = github_repo
        self._pending: dict[str, PendingFix] = {}
        self._telegram_offset: int = 0

    def run_cycle(self) -> None:
        self._check_approvals()
        self._process_new_incidents()

    # ------------------------------------------------------------------ #
    #  Incident discovery                                                  #
    # ------------------------------------------------------------------ #

    def _process_new_incidents(self) -> None:
        try:
            issues = self.jira.find_open_issues_for_remediation()
        except Exception as exc:
            logger.error(f"Failed to query Jira: {exc}")
            return

        for issue in issues:
            key = issue["key"]
            if key in self._pending:
                continue
            summary = issue["fields"]["summary"]
            description = _extract_description(issue)
            logger.info("Analyzing incident for remediation", extra={"key": key})
            self.jira.add_label(key, "in-remediation")
            self._analyze_and_propose(key, summary, description)

    def _analyze_and_propose(self, key: str, summary: str, description: str) -> None:
        files_content: dict[str, str] = {}
        files_sha: dict[str, str] = {}
        for path in FIXABLE_FILES:
            try:
                content, sha = self.github.get_file(path)
                files_content[path] = content
                files_sha[path] = sha
            except Exception as exc:
                logger.warning(f"Could not fetch {path}: {exc}")

        files_text = "\n\n".join(
            f"--- {path} ---\n{content}" for path, content in files_content.items()
        )

        prompt = ANALYSIS_PROMPT.format(
            title=summary, description=description, files=files_text
        )

        try:
            resp = self.claude.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text
            result = _parse_json(raw)
        except Exception as exc:
            logger.error(f"Claude analysis failed: {exc}")
            self.jira.add_label(key, "remediation-failed")
            return

        if not result.get("fixable"):
            logger.info("Issue not auto-fixable", extra={"key": key})
            self.telegram.send(
                f"🔍 *Incident {key}*: _{summary}_\n\n"
                f"{result.get('analysis', '')}\n\n"
                f"_Cannot be auto-remediated._"
            )
            self.jira.add_label(key, "remediation-not-applicable")
            return

        files_with_sha = [
            {"path": f["path"], "content": f["content"], "sha": files_sha.get(f["path"], "")}
            for f in result.get("files", [])
        ]

        pending = PendingFix(
            issue_key=key,
            issue_summary=summary,
            fix_description=result["fix_description"],
            files=files_with_sha,
        )
        self._pending[key] = pending

        # Advance offset so we don't re-read old messages when waiting for approval
        try:
            updates = self.telegram.get_updates(offset=self._telegram_offset)
            if updates:
                self._telegram_offset = updates[-1]["update_id"] + 1
        except Exception:
            pass

        changed = ", ".join(f"`{f['path']}`" for f in files_with_sha)
        self.telegram.send(
            f"🛠 *Proposed fix for {key}*\n\n"
            f"*Issue:* {summary}\n"
            f"*Analysis:* {result.get('analysis', '')}\n"
            f"*Fix:* {result['fix_description']}\n"
            f"*Files:* {changed}\n\n"
            f"Reply *APPROVE* to deploy or *REJECT* to skip."
        )
        logger.info("Fix proposed, waiting for approval", extra={"key": key})

    # ------------------------------------------------------------------ #
    #  Approval polling                                                    #
    # ------------------------------------------------------------------ #

    def _check_approvals(self) -> None:
        if not self._pending:
            return

        try:
            updates = self.telegram.get_updates(offset=self._telegram_offset)
        except Exception as exc:
            logger.warning(f"Telegram poll failed: {exc}")
            return

        for update in updates:
            self._telegram_offset = update["update_id"] + 1
            text = update.get("message", {}).get("text", "").strip().upper()
            if text == "APPROVE":
                self._apply_oldest_pending()
                return
            elif text == "REJECT":
                self._reject_oldest_pending()
                return

        # Check for timeouts
        now = datetime.now(timezone.utc)
        for key, pending in list(self._pending.items()):
            if now - pending.proposed_at > APPROVAL_TIMEOUT:
                logger.info("Approval timeout", extra={"key": key})
                self.telegram.send(f"⏱ Fix for *{key}* timed out waiting for approval.")
                self.jira.add_label(key, "approval-timeout")
                del self._pending[key]

    def _apply_oldest_pending(self) -> None:
        key, pending = next(iter(self._pending.items()))
        logger.info("Applying approved fix", extra={"key": key})
        try:
            for f in pending.files:
                commit_sha = self.github.update_file(
                    path=f["path"],
                    content=f["content"],
                    sha=f["sha"],
                    message=f"fix({key}): {pending.fix_description}",
                )
                logger.info("File committed", extra={"path": f["path"], "commit": commit_sha})

            self._rebuild_and_deploy()
            self.jira.add_label(key, "remediated")
            self.jira.transition_to_done(key)
            self.telegram.send(
                f"✅ *Fix deployed for {key}*\n\n"
                f"_{pending.fix_description}_\n\n"
                f"Code pushed to repository, image rebuilt and deployment restarted."
            )
        except Exception as exc:
            logger.error(f"Failed to apply fix for {key}: {exc}")
            self.telegram.send(f"❌ Failed to deploy fix for *{key}*: {exc}")
            self.jira.add_label(key, "remediation-failed")
        finally:
            del self._pending[key]

    def _reject_oldest_pending(self) -> None:
        key, pending = next(iter(self._pending.items()))
        logger.info("Fix rejected by operator", extra={"key": key})
        self.jira.add_label(key, "remediation-rejected")
        self.telegram.send(f"🚫 Fix for *{key}* rejected.")
        del self._pending[key]

    # ------------------------------------------------------------------ #
    #  Build & deploy                                                      #
    # ------------------------------------------------------------------ #

    def _rebuild_and_deploy(self) -> None:
        import docker  # type: ignore[import]
        image = self.target_image

        # Download repo archive from GitHub API as a tar stream
        logger.info("Downloading repo archive", extra={"repo": self._github_repo})
        resp = self.github.client.get(
            f"https://api.github.com/repos/{self._github_repo}/tarball",
            headers=self.github.headers,
            follow_redirects=True,
        )
        resp.raise_for_status()

        # Repack into a flat tar (docker build context expects files at root)
        context_buf = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as src_tar:
            with tarfile.open(fileobj=context_buf, mode="w") as dst_tar:
                for member in src_tar.getmembers():
                    # Strip the top-level directory added by GitHub
                    parts = member.name.split("/", 1)
                    if len(parts) < 2:
                        continue
                    member.name = parts[1]
                    if member.name == "":
                        continue
                    f = src_tar.extractfile(member)
                    dst_tar.addfile(member, f)
        context_buf.seek(0)

        logger.info("Building Docker image via SDK", extra={"image": image})
        docker_client = docker.from_env()
        built_image, logs = docker_client.images.build(
            fileobj=context_buf,
            custom_context=True,
            tag=image,
            rm=True,
            nocache=True,
        )
        for chunk in logs:
            if isinstance(chunk, dict) and "stream" in chunk:
                line = chunk["stream"].strip()
                if line:
                    logger.info(f"[docker] {line}")
        logger.info("Image ready", extra={"id": built_image.short_id})

        logger.info("Image built, triggering rollout", extra={"image": image})
        self._rollout_restart()
        self._wait_for_rollout()

    def _wait_for_rollout(self, timeout: int = 120, interval: int = 5) -> None:
        """Poll until the deployment rollout completes or timeout is reached."""
        import time
        from kubernetes import client, config  # type: ignore[import]
        config.load_incluster_config()
        apps_v1 = client.AppsV1Api()
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(interval)
            d = apps_v1.read_namespaced_deployment(
                name=self.target_deployment,
                namespace=self.target_namespace,
            )
            spec_replicas = d.spec.replicas or 1
            updated = d.status.updated_replicas or 0
            available = d.status.available_replicas or 0
            ready = d.status.ready_replicas or 0
            observed_gen = d.status.observed_generation or 0
            desired_gen = d.metadata.generation or 0
            logger.info(
                "Rollout status",
                extra={
                    "updated": updated,
                    "available": available,
                    "desired": spec_replicas,
                    "generation": f"{observed_gen}/{desired_gen}",
                },
            )
            if (
                observed_gen >= desired_gen
                and updated == spec_replicas
                and available == spec_replicas
                and ready == spec_replicas
            ):
                logger.info("Rollout complete")
                return
        raise RuntimeError(
            f"Rollout did not complete within {timeout}s — "
            f"new pod may be crashing. Check: kubectl get pod -n {self.target_namespace}"
        )

    def _rollout_restart(self) -> None:
        from kubernetes import client, config  # type: ignore[import]
        config.load_incluster_config()
        core_v1 = client.CoreV1Api()
        pods = core_v1.list_namespaced_pod(
            namespace=self.target_namespace,
            label_selector=f"app={self.target_deployment}",
        )
        for pod in pods.items:
            core_v1.delete_namespaced_pod(
                name=pod.metadata.name,
                namespace=self.target_namespace,
            )
            logger.info("Pod deleted for restart", extra={"pod": pod.metadata.name})
        logger.info(
            "Deployment rollout triggered",
            extra={"deployment": self.target_deployment, "namespace": self.target_namespace},
        )


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def _parse_json(text: str) -> dict:
    """Extract and parse JSON from Claude's response, handling markdown code blocks."""
    text = text.strip()
    # Strip markdown code fences if present
    for marker in ("```json", "```"):
        if text.startswith(marker):
            text = text[len(marker):]
            if "```" in text:
                text = text[:text.index("```")]
            break
    # Fallback: find outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def _extract_description(issue: dict) -> str:
    """Extract plain text from Jira ADF description."""
    desc = issue["fields"].get("description")
    if not desc:
        return ""
    texts: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text":
                texts.append(node.get("text", ""))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(desc)
    return " ".join(texts)
