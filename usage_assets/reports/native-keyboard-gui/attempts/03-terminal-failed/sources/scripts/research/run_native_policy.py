import sys
from pathlib import Path
sys.path.insert(0, '/workspace/php_parkour/scripts/research/gui_audit')
from observe_native import launch
launch('inference', Path(__file__).with_name('run_native_policy.gui-original.py'), 'bf388b4842a3866eac59d03aacc4afcbff532278d48e1e4f586e707bd64730f0')
