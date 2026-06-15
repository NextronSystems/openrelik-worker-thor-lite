import os
import subprocess
import time
from tempfile import TemporaryDirectory
from typing import Final

from celery import signals
from celery.utils.log import get_task_logger

# API docs - https://openrelik.github.io/openrelik-worker-common/openrelik_worker_common/index.html
from openrelik_common.logging import Logger
from openrelik_worker_common.file_utils import create_output_file, is_disk_image
from openrelik_worker_common.mount_utils import BlockDevice
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
            "name": "mount_disk_images",
            "label": "Mount disk images",
            "description": (
                "If checked, the worker will try to mount disk images and scan "
                "the files inside the disk image."
            ),
            "type": "checkbox",
            "required": True,
            "default_value": False,
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


def send_progress(task, status: str, progress: str | None = None, **fields) -> None:
    """Send task progress text for the OpenRelik UI."""
    data = {"status": status, "message": status}
    if progress:
        data["progress"] = progress
        data["message"] = f"{status}: {progress}"
    data.update({key: value for key, value in fields.items() if value is not None})
    task.send_event("task-progress", data=data)


def validate_scan_target(path: str, display_name: str = "input") -> None:
    """Reject scan targets that would silently scan the worker container."""
    if not path:
        raise RuntimeError("Input file path is empty.")
    if os.path.abspath(path) == os.path.sep:
        raise RuntimeError(
            "Refusing to scan filesystem root as Thor Lite input. "
            "Select a file or folder input instead."
        )
    if not os.path.exists(path):
        raise RuntimeError(f"Input path does not exist: {path}")
    if not (os.path.isfile(path) or os.path.isdir(path)):
        raise RuntimeError(
            f"Unsupported Thor Lite scan target: {display_name}. "
            "Thor Lite can scan regular files and directories. "
            "Disk images must be mounted before scanning their filesystems."
        )


def add_scan_path(thor_command: list[str], scan_path: str) -> None:
    """Add one THOR scan path to the command."""
    thor_command.extend(["--path", scan_path])


def output_file_has_data(output_file) -> bool:
    """Return whether THOR created a non-empty output file."""
    return os.path.exists(output_file.path) and os.path.getsize(output_file.path) > 0


def read_file_tail(path: str, max_bytes: int = 4096) -> str:
    """Read the end of a potentially large log file."""
    if not os.path.exists(path):
        return ""

    with open(path, "rb") as file_handle:
        file_handle.seek(0, os.SEEK_END)
        file_size = file_handle.tell()
        file_handle.seek(max(file_size - max_bytes, 0))
        return file_handle.read().decode("utf-8", errors="replace").strip()


def thor_failure_message(returncode: int, log_files: list) -> str:
    """Build a useful THOR failure message from generated logs."""
    log_excerpts = []
    for log_file in log_files:
        excerpt = read_file_tail(log_file.path)
        if excerpt:
            log_excerpts.append(f"{log_file.display_name}:\n{excerpt}")

    message = f"Thor Lite failed with exit code {returncode}."
    if not log_excerpts:
        return f"{message} No Thor Lite log output was produced."
    return f"{message}\n\n" + "\n\n".join(log_excerpts)


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
    task_config = task_config or {}

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
    if not input_files:
        raise RuntimeError("No input files were provided to Thor Lite.")
    mount_disk_images = task_config.get("mount_disk_images", False)
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
    disks_mounted = []
    thor_returncode = None
    try:
        with TemporaryDirectory(dir=output_path) as temp_dir:
            regular_files_added = False
            scan_paths = []

            for input_file in input_files:
                if "path" not in input_file:
                    raise RuntimeError(
                        "Input file does not have a path: "
                        f"{input_file.get('display_name', 'UNKNOWN FILE')}"
                    )

                input_file_path = input_file.get("path")
                display_name = input_file.get("display_name", input_file_path)
                validate_scan_target(input_file_path, display_name)

                if is_disk_image(input_file):
                    if not mount_disk_images:
                        raise RuntimeError(
                            "Disk image input is not supported in regular scan mode: "
                            f"{display_name}. Enable mount_disk_images to scan files "
                            "inside supported disk image filesystems."
                        )

                    try:
                        send_progress(self, "Mounting disk image", display_name)
                        block_device = BlockDevice(
                            input_file_path, min_partition_size=1
                        )
                        block_device.setup()
                        disks_mounted.append(block_device)
                        mountpoints = block_device.mount()
                        send_progress(
                            self,
                            "Mounted disk image",
                            f"{display_name}: {len(mountpoints)} mountpoint(s)",
                        )
                    except RuntimeError as e:
                        logger.error(
                            "Error mounting disk image %s (%s): %s",
                            display_name,
                            input_file_path,
                            str(e),
                        )
                        raise RuntimeError(
                            "Disk image input is not supported or could not be "
                            f"mounted by the Thor Lite worker: {display_name}."
                        ) from None

                    if not mountpoints:
                        raise RuntimeError(
                            "No mountpoints returned for input file "
                            f"{input_file.get('display_name')}"
                        )

                    for mountpoint in mountpoints:
                        validate_scan_target(mountpoint, display_name)
                        scan_paths.append(mountpoint)
                elif os.path.isfile(input_file_path):
                    filename = os.path.basename(input_file_path)
                    os.link(input_file_path, os.path.join(temp_dir, filename))
                    regular_files_added = True
                else:
                    scan_paths.append(input_file_path)

            if regular_files_added:
                scan_paths.insert(0, temp_dir)

            if not scan_paths:
                raise RuntimeError("No scan targets were produced from input files.")

            for scan_path in scan_paths:
                add_scan_path(thor_command, scan_path)

            logger.info("Thor Lite scan targets: %s", scan_paths)

            # Run Thor Lite
            progress_update_interval_in_s: Final[int] = 2
            logger.debug(f"Running Thor in {TASK_NAME}")
            with subprocess.Popen(thor_command) as proc:
                logger.debug(f"Waiting for Thor to finish in {TASK_NAME}")
                scan_started_at = time.monotonic()
                while proc.poll() is None:
                    elapsed_seconds = int(time.monotonic() - scan_started_at)
                    send_progress(
                        self,
                        "Running Thor Lite scan",
                        (
                            f"{len(scan_paths)} scan target(s), "
                            f"elapsed {elapsed_seconds}s"
                        ),
                        elapsed_seconds=elapsed_seconds,
                        scan_targets=len(scan_paths),
                    )
                    time.sleep(progress_update_interval_in_s)
                thor_returncode = proc.wait()
    finally:
        for block_device in disks_mounted:
            logger.debug(f"Unmounting image {block_device.image_path}")
            block_device.umount()

    # Populate the list of resulting output files.
    logger.debug(f"Collecting output files for {TASK_NAME}")
    for output_file in [html_output, json_log, txt_log]:
        if output_file_has_data(output_file):
            output_files.append(output_file.to_dict())
        else:
            logger.warning("Thor Lite did not create output file %s", output_file.path)

    if thor_returncode:
        raise RuntimeError(thor_failure_message(thor_returncode, [txt_log, json_log]))

    logger.info(f"Finished {TASK_NAME} for workflow {workflow_id}")

    return create_task_result(
        output_files=output_files,
        workflow_id=workflow_id,
        command=" ".join(thor_command),
        meta={},
    )
