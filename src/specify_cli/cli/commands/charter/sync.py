"""``spec-kitty charter sync`` command (WP06 per-subcommand split)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import typer

from specify_cli.task_utils import TaskCliError

from specify_cli.cli.commands.charter._app import charter_app, console
from specify_cli.cli.commands.charter._common import _emit_error, _resolve_charter_path

# Test-patch shim — see ``synthesize.py``.
import specify_cli.cli.commands.charter as _charter_pkg

if TYPE_CHECKING:
    from charter.activation.sync import SyncResult

__all__ = ["sync"]

#: #4679: ``charter sync`` is a compatibility shim. The prose->triad extraction
#: it used to perform is retired (IC-04 / #2773), so there is never anything to
#: sync -- say so plainly instead of reporting a failure-shaped ``synced=False``.
_NOOP_MESSAGE = (
    "'spec-kitty charter sync' is kept for compatibility only and no longer "
    "syncs anything -- governance and directives are hand-authored in "
    "charter.yaml. Nothing to do."
)


def _sync_json_payload(result: SyncResult) -> dict[str, object]:
    """Return stable JSON output for ``charter sync``.

    #4679: a no-op is an inert outcome, not a failure, so it is reported as
    ``success: true`` / ``result: "noop"`` with an explicit ``message`` -- not
    the failure-shaped ``success: false`` this used to emit. ``stale_before``
    and ``files_written`` keep their meaning for callers that still read them.
    """
    return {
        "result": "success" if result.synced else "noop",
        "success": result.error is None,
        "message": "Charter synced" if result.synced else _NOOP_MESSAGE,
        "stale_before": result.stale_before,
        "files_written": result.files_written,
        "extraction_mode": result.extraction_mode,
        "error": result.error,
        "warnings": result.warnings,
    }


def _emit_sync_human_result(result: SyncResult) -> None:
    """Render the non-JSON ``charter sync`` result.

    Since the IC-04 triad retirement, ``charter.activation.sync.sync()`` is a
    pure staleness reporter — ``synced`` is always ``False`` and nothing is
    written — so this command is a permanent no-op kept for compatibility.

    #4679: it used to render that as a failure (#3045's honest-reporter
    remedy: a red "Charter was not synced", exit 1, pointing at ``charter
    generate`` / ``synthesize``), which reads as something the operator must
    fix. A no-op is inert, not broken: say so explicitly and exit 0. The JSON
    surface (``_sync_json_payload``) reports the same inert success, so the
    two surfaces still agree (#3045). ``result.synced`` being ``True`` would
    only occur under a future repair-mode ``sync()``.
    """
    if result.error:
        console.print(f"[red]Error:[/red] {result.error}")
        raise typer.Exit(code=1)

    if result.synced:
        console.print("[green]Charter synced[/green]")
        return

    console.print(f"[yellow]No-op:[/yellow] {_NOOP_MESSAGE}")


@charter_app.command()
def sync(
    force: bool = typer.Option(False, "--force", "-f", help="Accepted for compatibility; has no effect"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """No-op kept for compatibility; there is nothing to sync.

    The prose-to-YAML extraction this command used to perform is retired:
    governance and directives are hand-authored directly in charter.yaml.
    Running it is harmless and changes nothing.
    """
    from charter.activation.sync import sync as sync_charter

    try:
        repo_root = _charter_pkg.find_repo_root()
        charter_path = _resolve_charter_path(repo_root)
        output_dir = charter_path.parent

        result = sync_charter(charter_path, output_dir, force=force)

        if json_output:
            if result.error:
                _emit_error(console, json_output=True, message=str(result.error))
                raise typer.Exit(code=1)
            print(json.dumps(_sync_json_payload(result), indent=2))
            return

        _emit_sync_human_result(result)

    except typer.Exit:
        raise
    except TaskCliError as e:
        _emit_error(console, json_output=json_output, message=str(e))
        raise typer.Exit(code=1) from e
    except Exception as e:
        _emit_error(console, json_output=json_output, message=str(e), unexpected=True)
        raise typer.Exit(code=1) from e
