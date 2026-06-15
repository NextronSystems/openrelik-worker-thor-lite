"""Tests tasks."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tasks import TASK_METADATA, command


class MockOutputFile:
    """Small output-file stand-in for openrelik-worker-common tests."""

    def __init__(self, path: Path, content: str | None = "thor output"):
        self.path = str(path)
        self.display_name = path.name
        if content is not None:
            path.write_text(content)

    def to_dict(self):
        return {"path": self.path, "display_name": Path(self.path).name}


class CompletedPopen:
    """Popen context manager that exits immediately."""

    def __init__(self, returncode=0):
        self.returncode = returncode

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def poll(self):
        return self.returncode

    def wait(self):
        return self.returncode


class RunningPopen(CompletedPopen):
    """Popen context manager that stays active for a few polls."""

    def __init__(self, returncode=0, active_polls=2):
        super().__init__(returncode)
        self.active_polls = active_polls
        self.poll_count = 0

    def poll(self):
        self.poll_count += 1
        if self.poll_count <= self.active_polls:
            return None
        return self.returncode


def _mock_outputs(tmp_path):
    return [
        MockOutputFile(tmp_path / "thor-report.html"),
        MockOutputFile(tmp_path / "thor-log.json"),
        MockOutputFile(tmp_path / "thor-log.txt"),
    ]


def _mock_outputs_without_html(tmp_path):
    return [
        MockOutputFile(tmp_path / "thor-report.html", content=None),
        MockOutputFile(tmp_path / "thor-log.json"),
        MockOutputFile(tmp_path / "thor-log.txt"),
    ]


def _create_task_result(**kwargs):
    return kwargs


def _path_values(thor_command):
    return [
        thor_command[index + 1]
        for index, value in enumerate(thor_command)
        if value == "--path"
    ]


def test_task_metadata_exposes_mount_disk_images_option():
    config_names = {item["name"] for item in TASK_METADATA["task_config"]}

    assert "mount_disk_images" in config_names


def test_command_scans_regular_inputs_from_temp_directory(tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("test")

    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True), patch(
        "src.tasks.create_output_file", side_effect=_mock_outputs(tmp_path)
    ), patch("src.tasks.create_task_result", side_effect=_create_task_result), patch(
        "src.tasks.subprocess.Popen", return_value=CompletedPopen()
    ) as mock_popen:
        result = command.run(
            None,
            task_config={},
            input_files=[{"path": str(input_file), "display_name": input_file.name}],
            output_path=str(tmp_path),
        )

    thor_command = mock_popen.call_args.args[0]
    path_values = _path_values(thor_command)

    assert len(path_values) == 1
    assert Path(path_values[0]).parent == tmp_path
    assert "--silent" in thor_command
    assert result["command"] == " ".join(thor_command)


def test_command_skips_missing_thor_output_files(tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("test")

    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True), patch(
        "src.tasks.create_output_file",
        side_effect=_mock_outputs_without_html(tmp_path),
    ), patch("src.tasks.create_task_result", side_effect=_create_task_result), patch(
        "src.tasks.subprocess.Popen", return_value=CompletedPopen()
    ):
        result = command.run(
            None,
            task_config={},
            input_files=[{"path": str(input_file), "display_name": input_file.name}],
            output_path=str(tmp_path),
        )

    output_names = {output_file["display_name"] for output_file in result["output_files"]}
    assert output_names == {"thor-log.json", "thor-log.txt"}


def test_command_sends_progress_data_while_thor_runs(tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("test")

    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True), patch(
        "src.tasks.create_output_file", side_effect=_mock_outputs(tmp_path)
    ), patch("src.tasks.create_task_result", side_effect=_create_task_result), patch(
        "src.tasks.subprocess.Popen", return_value=RunningPopen()
    ), patch("src.tasks.time.sleep"), patch.object(
        command, "send_event"
    ) as mock_send_event:
        command.run(
            None,
            task_config={},
            input_files=[{"path": str(input_file), "display_name": input_file.name}],
            output_path=str(tmp_path),
        )

    progress_events = [
        call.kwargs["data"]
        for call in mock_send_event.call_args_list
        if call.args[0] == "task-progress"
    ]

    assert progress_events
    assert all(data is not None for data in progress_events)
    assert any(
        data["status"] == "Running Thor Lite scan"
        and data["scan_targets"] == 1
        and "elapsed" in data["progress"]
        for data in progress_events
    )


def test_command_raises_thor_failure_with_log_excerpt(tmp_path):
    input_file = tmp_path / "input.txt"
    input_file.write_text("test")
    outputs = [
        MockOutputFile(tmp_path / "thor-report.html", content=None),
        MockOutputFile(tmp_path / "thor-log.json", content="license expired"),
        MockOutputFile(tmp_path / "thor-log.txt", content="No valid license file found"),
    ]

    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True), patch(
        "src.tasks.create_output_file", side_effect=outputs
    ), patch(
        "src.tasks.subprocess.Popen", return_value=CompletedPopen(returncode=1)
    ):
        with pytest.raises(RuntimeError, match="license expired"):
            command.run(
                None,
                task_config={},
                input_files=[
                    {"path": str(input_file), "display_name": input_file.name}
                ],
                output_path=str(tmp_path),
            )


def test_command_rejects_disk_image_without_mount_disk_images(tmp_path):
    input_file = tmp_path / "disk.E01"
    input_file.write_text("disk")

    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True), patch(
        "src.tasks.create_output_file", side_effect=_mock_outputs(tmp_path)
    ), patch("src.tasks.is_disk_image", return_value=True), patch(
        "src.tasks.BlockDevice"
    ) as mock_block_device, patch(
        "src.tasks.subprocess.Popen"
    ) as mock_popen:
        with pytest.raises(RuntimeError, match="Enable mount_disk_images"):
            command.run(
                None,
                task_config={},
                input_files=[
                    {"path": str(input_file), "display_name": input_file.name}
                ],
                output_path=str(tmp_path),
            )

    mock_block_device.assert_not_called()
    mock_popen.assert_not_called()


def test_command_mounts_disk_image_before_scanning(tmp_path):
    input_file = tmp_path / "disk.img"
    input_file.write_text("disk")
    mountpoint = tmp_path / "mounted-partition"
    mountpoint.mkdir()

    block_device = MagicMock()
    block_device.image_path = str(input_file)
    block_device.mount.return_value = [str(mountpoint)]

    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True), patch(
        "src.tasks.create_output_file", side_effect=_mock_outputs(tmp_path)
    ), patch("src.tasks.create_task_result", side_effect=_create_task_result), patch(
        "src.tasks.is_disk_image", return_value=True
    ), patch(
        "src.tasks.BlockDevice", return_value=block_device
    ) as mock_block_device, patch(
        "src.tasks.subprocess.Popen", return_value=CompletedPopen()
    ) as mock_popen, patch.object(
        command, "send_event"
    ):
        command.run(
            None,
            task_config={"mount_disk_images": True},
            input_files=[{"path": str(input_file), "display_name": input_file.name}],
            output_path=str(tmp_path),
        )

    mock_block_device.assert_called_once_with(str(input_file), min_partition_size=1)
    block_device.setup.assert_called_once_with()
    block_device.mount.assert_called_once_with()
    block_device.umount.assert_called_once_with()

    thor_command = mock_popen.call_args.args[0]
    assert _path_values(thor_command) == [str(mountpoint)]


def test_command_unmounts_disk_image_when_thor_fails(tmp_path):
    input_file = tmp_path / "disk.img"
    input_file.write_text("disk")
    mountpoint = tmp_path / "mounted-partition"
    mountpoint.mkdir()

    block_device = MagicMock()
    block_device.image_path = str(input_file)
    block_device.mount.return_value = [str(mountpoint)]

    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True), patch(
        "src.tasks.create_output_file", side_effect=_mock_outputs(tmp_path)
    ), patch("src.tasks.is_disk_image", return_value=True), patch(
        "src.tasks.BlockDevice", return_value=block_device
    ), patch(
        "src.tasks.subprocess.Popen", side_effect=RuntimeError("thor failed")
    ), patch.object(
        command, "send_event"
    ):
        with pytest.raises(RuntimeError, match="thor failed"):
            command.run(
                None,
                task_config={"mount_disk_images": True},
                input_files=[
                    {"path": str(input_file), "display_name": input_file.name}
                ],
                output_path=str(tmp_path),
            )

    block_device.umount.assert_called_once_with()


def test_command_raises_without_input_files(tmp_path):
    with patch.dict(os.environ, {"THOR_LICENSE": "license"}, clear=True):
        with pytest.raises(RuntimeError, match="No input files"):
            command.run(
                None,
                task_config={},
                input_files=[],
                output_path=str(tmp_path),
            )
