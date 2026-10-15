# reference629 明确跨 boot 宿主控制 v2（仅源码准备）

本目录由原 35-file preparation 逐 SHA 复制；原 adapter.py、support.py、cpu_prepare.py、native_runner.py、frozen/、source-original/ 和科学输入不变。
admission.py 只替换 native58 旧 waiter argv/returncode 门卫：采用已审查的 native58_crossboot_control.verify_actual_parent，对真实 e238 start/exit、wrapper、契约、新跨 boot 资源门卫和原 native58 收据进行只读核验。
58 case/worker/hostmap/full-video、60 ORT、pose、source/input/freeze/review 等原检查代码保持；新增 review.host_control 等于实际新宿主控制，所有新原件追加 bound_files。

旧 v1 preparation 与 481d manifest 不修改。宿主控制新源、原 source 和准确 diff 由新的 preparation-manifest 全封印；新增文件使 v2 inventory 超过原 35，不将新源冒充旧35。
原 README.md 保留为 v1 技术上下文，本文件是 v2 入口。

未来 CLI 沿用原 adapter.py 的显式参数，只将 preparation 路径/SHA 换成本目录的已审查新 seal。status 在缺少真实58终态/独立 review 时保持 waiting；prepare 只在全部实际证据齐后由 root 单独调用。不会执行未来科学作业、造 terminal review 或隐式转换 parent schema。
