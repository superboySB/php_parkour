import sys
from pathlib import Path
sys.path.insert(0, '/workspace/php_parkour/scripts/research/gui_audit')
from observe_native import launch
launch('simulator', Path(__file__).with_name('run_sim.gui-original.py'), '08720f65c163dda0f926b17bf28caa6288614708c6679675f0f2d7e70a27f0ef')
