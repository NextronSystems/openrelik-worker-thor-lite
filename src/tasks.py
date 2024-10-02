# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess

from openrelik_worker_common.utils import (
    create_output_file,
    get_input_files,
    task_result,
)

from .app import celery

# Task name used to register and route the task to the correct queue.
TASK_NAME = "your-worker-package-name.tasks.your_task_name"

# Task metadata for registration in the core system.
TASK_METADATA = {
    "display_name": "<REPLACE_WITH_NAME_OF_THE_WORKER>",
    "description": "<REPLACE_WITH_DESCRIPTION_OF_THE_WORKER>",
    # Configuration that will be rendered as a web for in the UI, and any data entered
    # by the user will be available to the task function when executing (task_config).
    "task_config": [
        {
            "name": "<REPLACE_WITH_NAME>",
            "label": "<REPLACE_WITH_LABEL>",
            "description": "<REPLACE_WITH_DESCRIPTION>",
            "type": "<REPLACE_WITH_TYPE>",  # Types supported: text, textarea, checkbox
            "required": False,
        },
    ],
}


@celery.task(bind=True, name=TASK_NAME, metadata=TASK_METADATA)
def command(
    self,
    pipe_result: str = None,
    input_files: list = None,
    output_path: str = None,
    workflow_id: str = None,
    task_config: dict = None,
) -> str:
    """Run <REPLACE_WITH_COMMAND> on input files.

    Args:
        pipe_result: Base64-encoded result from the previous Celery task, if any.
        input_files: List of input file dictionaries (unused if pipe_result exists).
        output_path: Path to the output directory.
        workflow_id: ID of the workflow.
        task_config: User configuration for the task.

    Returns:
        Base64-encoded dictionary containing task results.
    """
    input_files = get_input_files(pipe_result, input_files or [])
    output_files = []
    base_command = ["<REPLACE_WITH_COMMAND>"]
    base_command_string = " ".join(base_command)

    for input_file in input_files:
        output_file = create_output_file(
            output_path,
            filename=input_file.get("filename"),
            file_extension="<REPLACE_WITH_FILE_EXTENSION>",
            data_type="<[OPTIONAL]_REPLACE_WITH_DATA_TYPE>",
        )
        command = base_command + [input_file.get("path")]

        # Run the command
        with open(output_file.path, "w") as fh:
            subprocess.Popen(command, stdout=fh)

        output_files.append(output_file.to_dict())

    if not output_files:
        raise RuntimeError("<REPLACE_WITH_ERROR_STRING>")

    return task_result(
        output_files=output_files,
        workflow_id=workflow_id,
        command=base_command_string,
        meta={},
    )
