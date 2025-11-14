import os
import sys
import subprocess

here = os.path.dirname(__file__)
requirements_path = os.path.join(here, "requirements.txt")

try:
    from .nodes.MakeFrame import GetKeyFrames, MakeGrid, BreakGrid
except:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', requirements_path])
    from .nodes.MakeFrame import GetKeyFrames, MakeGrid, BreakGrid

NODE_CLASS_MAPPINGS = {
    "GetKeyFrames": GetKeyFrames,
    "MakeGrid": MakeGrid,
    "BreakGrid": BreakGrid,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GetKeyFrames": "GetKeyFrames",
    "MakeGrid": "MakeGrid",
    "BreakGrid": "BreakGrid",
}
