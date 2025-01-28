# Copyright 2025 Nextron Systems GmbH

import os
import subprocess
import time
from tempfile import TemporaryDirectory
from typing import Final

from celery.utils.log import get_task_logger

from openrelik_worker_common.file_utils import create_output_file
from openrelik_worker_common.task_utils import (
    create_task_result,
    get_input_files,
)

from .app import celery

# Task name used to register and route the task to the correct queue.
TASK_NAME = "openrelik-worker-thor-lite.tasks.thor-lite"

# Task metadata for registration in the core system.
TASK_METADATA = {
    "display_name": "Thor Lite",
    "description": "Scanner for attacker tools and activity",
    "task_config": [],
}

logger = get_task_logger(__name__)


@celery.task(bind=True, name=TASK_NAME, metadata=TASK_METADATA)
def thor(  # pylint: disable=too-many-arguments
    self,
    pipe_result: str | None = None,
    input_files: list | None = None,
    output_path: str | None = None,
    workflow_id: str | None = None,
    task_config: dict | None = None,  # pylint: disable=unused-argument
) -> str:
    """Run Thor Lite on input files.

    Args:
        pipe_result: Base64-encoded result from the previous Celery task, if any.
        input_files: List of input file dictionaries (unused if pipe_result exists).
        output_path: Path to the output directory.
        workflow_id: ID of the workflow.
        task_config: User configuration for the task.

    Returns:
        Base64-encoded dictionary containing task results.
    """
    # pylint: disable=too-many-locals
    logger.debug("Running Thor Lite task")
    input_files = get_input_files(pipe_result, input_files or []) or []
    output_files = []

    # Create output files
    html_output = create_output_file(
        output_path,
        display_name="Thor_Lite_HTML_report.html",
        data_type="openrelik:worker:thor-lite:html_report",
    )

    json_log = create_output_file(
        output_path,
        display_name="Thor_Lite_JSON_log.json",
        data_type="openrelik:worker:thor-lite:json_log",
    )

    txt_log = create_output_file(
        output_path,
        display_name="Thor_Lite_TXT_log.txt",
        data_type="openrelik:worker:thor-lite:txt_log",
    )

    # Thor Lite command
    command = [
        "/thor-lite/thor-lite-linux-64",
        "--module",
        "FileScan",
        "--intense",
        "--norescontrol",
        "--cross-platform",
        "--html-file",
        html_output.path,
        "--log-file",
        txt_log.path,
        "--json-file",
        json_log.path,
        "--rebase-dir",
        output_path,
    ]

    # Debugging information
    if not os.getenv("THOR_LITE_WORKER_DEBUG"):
        command.append("--silent")

    # Prepare input files and run Thor Lite
    logger.debug("Creating temporary directory for Thor Lite processing.")
    with TemporaryDirectory(dir=output_path) as temp_dir:
        # Hard link input files for processing
        logger.debug("Hard linking input files for Thor Lite processing.")
        for input_file in input_files:
            filename = os.path.basename(input_file.get("path"))
            os.link(input_file.get("path"), f"{temp_dir}/{filename}")

        # Add the created temporary directory to the command for processing.
        command.append("--path")
        command.append(temp_dir)

        # Run Thor Lite
        progress_update_interval_in_s: Final[int] = 2
        logger.debug("Running Thor")
        with subprocess.Popen(command) as proc:
            logger.debug("Waiting for Thor to finish")
            while proc.poll() is None:
                self.send_event("task-progress", data=None)
                time.sleep(progress_update_interval_in_s)

    # Populate the list of resulting output files.
    logger.debug("Collecting output files")
    for output_file in [html_output, json_log, txt_log]:
        if os.stat(output_file.path).st_size > 0:
            output_files.append(output_file.to_dict())

    return create_task_result(
        output_files=output_files,
        workflow_id=workflow_id,
        command=" ".join(command),
        meta={},
    )
