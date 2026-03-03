import os
import subprocess
import time
from tempfile import TemporaryDirectory
from typing import Final

from celery import signals
from celery.utils.log import get_task_logger

# API docs - https://openrelik.github.io/openrelik-worker-common/openrelik_worker_common/index.html
from openrelik_worker_common.file_utils import create_output_file
from openrelik_common.logging import Logger
from openrelik_worker_common.task_utils import create_task_result, get_input_files

from .app import celery

# Task name used to register and route the task to the correct queue.
TASK_NAME = "openrelik-worker-thor-lite.tasks.thor-lite"

# Task metadata for registration in the core system.
TASK_METADATA = {
    "display_name": "Thor Lite",
    "description": "Scanner for attacker tools and activity",
    # Configuration that will be rendered as a web for in the UI, and any data entered
    # by the user will be available to the task function when executing (task_config).
    "task_config": [
        {
            "name": "Thor Lite",
            "label": "ThorLite",
            "description": "Scanner for attacker tools and activity",
            "type": "text",  # Types supported: text, textarea, checkbox
            "required": False,
        },
    ],
}

log_root = Logger()
logger = log_root.get_logger(__name__, get_task_logger(__name__))


@signals.task_prerun.connect
def on_task_prerun(sender, task_id, task, args, kwargs, **_):
    log_root.bind(
        task_id=task_id,
        task_name=task.name,
        worker_name=TASK_METADATA.get("display_name"),
    )


@celery.task(bind=True, name=TASK_NAME, metadata=TASK_METADATA)
def command(
    self,
    pipe_result: str | None = None,
    input_files: list | None = None,
    output_path: str | None = None,
    workflow_id: str | None = None,
    task_config: dict | None = None,
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
    # Setup logger
    log_root.bind(workflow_id=workflow_id)
    logger.info(f"Starting {TASK_NAME} for workflow {workflow_id}")

    # License check
    if not os.getenv("THOR_LICENSE"):
        logger.error(
            "Thor Lite license key not found. Please set the THOR_LICENSE"
            " environment variable in your docker-compose.yml."
        )
        raise RuntimeError(
            "Thor Lite license key not found. Please set the THOR_LICENSE"
            " environment variable in your docker-compose.yml."
        )

    input_files = get_input_files(pipe_result, input_files or []) or []
    output_files = []

    # Create output files
    html_output = create_output_file(
        output_path,
        display_name="Thor_Lite_HTML_report",
        extension="html",
        data_type="openrelik:worker:thor-lite:html_report",
    )

    json_log = create_output_file(
        output_path,
        display_name="Thor_Lite_JSON_log",
        extension="json",
        data_type="openrelik:worker:thor-lite:json_log",
    )

    txt_log = create_output_file(
        output_path,
        display_name="Thor_Lite_TXT_log",
        extension="txt",
        data_type="openrelik:worker:thor-lite:txt_log",
    )

    # Thor Lite command
    thor_command = [
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
        thor_command.append("--silent")

    # Prepare input files and run Thor Lite
    logger.debug(f"Creating temporary directory for {TASK_NAME} processing.")
    with TemporaryDirectory(dir=output_path) as temp_dir:
        # Hard link input files for processing
        logger.debug(f"Hard linking input files for {TASK_NAME} processing.")
        for input_file in input_files:
            filename = os.path.basename(input_file.get("path"))
            os.link(input_file.get("path"), f"{temp_dir}/{filename}")

        # Add the created temporary directory to the command for processing.
        thor_command.append("--path")
        thor_command.append(temp_dir)

        # Run Thor Lite
        progress_update_interval_in_s: Final[int] = 2
        logger.debug(f"Running Thor in {TASK_NAME}")
        with subprocess.Popen(thor_command) as proc:
            logger.debug(f"Waiting for Thor to finish in {TASK_NAME}")
            while proc.poll() is None:
                self.send_event("task-progress", data=None)
                time.sleep(progress_update_interval_in_s)

    # Populate the list of resulting output files.
    logger.debug(f"Collecting output files for {TASK_NAME}")
    for output_file in [html_output, json_log, txt_log]:
        if os.stat(output_file.path).st_size > 0:
            output_files.append(output_file.to_dict())

    logger.info(f"Finished {TASK_NAME} for workflow {workflow_id}")

    return create_task_result(
        output_files=output_files,
        workflow_id=workflow_id,
        command=" ".join(thor_command),
        meta={},
    )
