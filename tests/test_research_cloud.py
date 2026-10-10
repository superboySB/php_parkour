"""GPU allocation must not select another user's computing/graphics GPU."""
import importlib.util
import hashlib
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "select_idle_gpu", Path(__file__).resolve().parents[1] / "scripts/research/select_idle_gpu.py"
)
gpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpu)


def xml_gpu(minor, memory="1 MiB", utilization="0 %", processes=""):
    return f"""<gpu><minor_number>{minor}</minor_number><uuid>GPU-{minor}</uuid>
    <product_name>Test</product_name><fb_memory_usage><used>{memory}</used></fb_memory_usage>
    <utilization><gpu_util>{utilization}</gpu_util></utilization>
    <processes>{processes}</processes></gpu>"""


def test_nvidia_indices_are_not_linux_minor_numbers():
    occupied = "<process_info><pid>123</pid><type>G</type></process_info>"
    rows = gpu.inspect("<nvidia_smi_log>" + xml_gpu(7, processes=occupied) + xml_gpu(6) + "</nvidia_smi_log>")
    assert [row["index"] for row in rows] == [0, 1]
    assert rows[1]["uuid"] == "GPU-6"
    assert not rows[0]["idle"] and rows[1]["idle"]


def test_unreported_processes_and_busy_utilization_fail_closed():
    xml = xml_gpu(0).replace("<processes></processes>", "")
    xml += xml_gpu(1, utilization="1 %")
    xml += xml_gpu(2, memory="65 MiB")
    xml += xml_gpu(3, processes="N/A")
    xml += xml_gpu(4, utilization="N/A")
    assert not any(row["idle"] for row in gpu.inspect("<nvidia_smi_log>" + xml + "</nvidia_smi_log>"))


def test_source_transfer_is_frozen_before_collaborator_edits(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/research/cloud.py"
    cloud_spec = importlib.util.spec_from_file_location("php_cloud", path)
    cloud = importlib.util.module_from_spec(cloud_spec)
    cloud_spec.loader.exec_module(cloud)
    source = tmp_path / "live" / "example.py"
    source.parent.mkdir()
    source.write_text("before = True\n")
    entry = {"path": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
             "symlink": False, "mode": source.stat().st_mode & 0o777}
    monkeypatch.setattr(cloud, "ROOT", source.parent)
    monkeypatch.setattr(cloud, "source_files", lambda: [entry])
    original_copy = cloud.shutil.copy2

    def copy_and_edit(*args, **kwargs):
        result = original_copy(*args, **kwargs)
        source.write_text("after = True\n")
        return result

    monkeypatch.setattr(cloud.shutil, "copy2", copy_and_edit)
    staged = tmp_path / "frozen"
    assert cloud.stage_source(staged) == [entry]
    assert (staged / source.name).read_text() == "before = True\n"
    assert source.read_text() == "after = True\n"
