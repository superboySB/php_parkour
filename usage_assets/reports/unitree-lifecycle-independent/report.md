# Unitree SDK lifecycle independent audit

The installed `far-unitree-sdk==0.1.6` provides no public `close`, `stop`, `shutdown`, `join` or `destroy` on `UnitreeInterface`. The Python application wrapper also has none. Its conditional `hasattr(interface, "close")` therefore does not stop the native command thread (`scripts/research/sim2sim.py:285–290`). Both the simulator bridge and inference process own this SDK, so both Python installations require any candidate upgrade.

| Runtime | Actual interpreter location | Installed extension SHA256 |
|---|---|---|
| train | `/isaac-sim/kit/python`, Python3.11.13; **not a venv** | `9200c9bd739eae1b730c03e3603571553d335646f4b871020d92b4ae7930c0a5` |
| inference | `/opt/php/envs/inference`, Python3.12.3 | `40632e9e05cb7e931c136eaa9ead62df37a19a905b7b38378f5c337040130f5a` |
| motion | `/opt/php/envs/motion`, Python3.12.3 | SDK absent |

## Confirmed upstream defect and fix

Official v0.1.6 commit `c20385ca7da1b4a254bc77bfa1db8ef2fdbca083` resets the recurrent-thread shared pointer directly at `python_binding/unitree_interface.cpp:30–38`. Its saved source SHA256 is `7ce9f6efdfe7c0f60abec352c1d820115bf24cb03616b588e1417c0440ae00a3`. v0.1.7 still does the same.

Official v0.1.8 commit `9cf396bda17485febbacb2fadec27c52e0aff391` calls `command_writer_ptr_->Wait()` before `.reset()` at `python_binding/unitree_interface.cpp:152–158`. Its comment identifies the callback-destruction/cancellation race. Saved source SHA256: `51cc3b819fd942f7fe27896119ecfb3b32d7d041f999f79e4ae476db1abc28f8`. [Old official source](https://github.com/amazon-far/unitree_sdk2/blob/c20385ca7da1b4a254bc77bfa1db8ef2fdbca083/python_binding/unitree_interface.cpp#L30); [fixed official source](https://github.com/amazon-far/unitree_sdk2/blob/9cf396bda17485febbacb2fadec27c52e0aff391/python_binding/unitree_interface.cpp#L152). These are raw source line numbers, not the GitHub HTML parser line numbers. All17 saved primary-source files/URLs/commits/SHA256 are in `upstream-sources.json`.

The installed CPython3.12 ELF disassembly supports the concern: `RecurrentThread::~RecurrentThread()` destroys its callable at `0x27a3dd`, then calls `Thread::~Thread()` at `0x27a3e9`; the latter calls `pthread_cancel` at `0x27b72f`. `RecurrentThread::Wait(long)` sets the quit flag and waits for the future. The outer interface destructor is hidden in the stripped binary, so that exact outer body was checked against official source rather than claimed to have been recovered from symbols. Captured ELF, dynamic symbols and bounded disassembly are under `installed/` and individually hashed in `installed-evidence.json`. Native `Wait()` is not exposed through pybind; accessing hidden thread objects with ctypes would be unsupported.

## Attribution limits

For original `low_speed_step:0041`, the kernel reports host **thread ID**394853 `command_writer` SIGSEGV at07:00:49.743842UTC, about52.9ms after inference JSON completion. Both worker bodies finished500ticks, but no explicit worker exitcode, host PID mapping or core was retained. This is a narrow shutdown-window crash consistent with the known upstream race; it does not uniquely assign the crashing worker or prove a single cause.

For `low_speed_climb_58:0022`, the simulator log explicitly reports Kit Python PID63669 `Segmentation fault (core dumped)`, matching its `sim-ready.pid`. Thus at least the simulator failure is directly assigned. The two kernel command-writer TIDs cannot each be bound to a worker from the old evidence. Features retained both original14-file cohorts under `outputs/research/sim2sim-failure-forensics/`; successful neighbors40/42 also emit shared-memory tracker warnings, so those warnings alone are not causal evidence. Both original cases remain execution failures.

## Candidate and required next check

Official [PyPI0.1.8](https://pypi.org/project/far-unitree-sdk/0.1.8/) provides both cp311 and cp312 x86_64 wheels. A separate derivative image can replace only the two SDK installations with hash-verified offline wheels. The factory preserves three positional arguments and default `MessageType.HG`, adding keyword-only `dds_config=None`; default DDS initialization retains `Init(0,nic)` (`cpp:83–120`). It also adds DDS initialization guards and an optional motion-switcher responder, so import/API compatibility is not a full behavior guarantee. Source commit association is the official tag; the wheel does not supply a compiler/source-build attestation.

The independent build/ABI report is `../unitree-sdk018-candidate/summary.md`. No existing image, package pin, active container or629 evidence is changed. A later fresh, isolated single-case run must retain both normal worker exits, PID mappings, finite500ticks/10s and a fresh decoded MP4. Neither an abrupt `os._exit(0)` workaround nor deleting an object under the old destructor is a verified cleanup fix. This audit itself used no robot construction, DDS, GPU, simulator or cloud access.
