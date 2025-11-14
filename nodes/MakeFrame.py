import cv2
import torch
import numpy as np
import os
import random
from PIL import Image
from .. import makeframeutils as mfu

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class GetKeyFrames:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "frames": ("IMAGE", ),
                "num_keyframes": ("INT", {
                        "default": 12, 
                        "min": 2,
                        "max": 4096,
                        "step": 1
                }),
                "include_first_frame": ("BOOLEAN", {
                        "default": True,
                        "label_on": "True",
                        "label_off": "False"
                }),
                "include_last_frame": ("BOOLEAN", {
                        "default": True,
                        "label_on": "True",
                        "label_off": "False"
                }),
            },
        }
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("Keyframes", "keyframe_indices")

    FUNCTION = "getkeyframes"
    CATEGORY = "Frames"

    def getkeyframes(self, frames, num_keyframes, include_first_frame, include_last_frame):
        # Input 'frames' is a standard ComfyUI IMAGE batch tensor: (N, H, W, C)
        num_frames = frames.shape[0]

        if num_frames < 2:
            # Not enough frames to compare, return the input as is.
            keyframe_indices = list(range(num_frames))
        else:
            # Ensure num_keyframes is valid. We can select from num_frames - 1 differences.
            max_keyframes = num_frames - 1
            # Handle case where num_keyframes might be larger than available differences
            N = np.clip(num_keyframes, 1, max_keyframes) if max_keyframes > 0 else 0

            if N > 0:
                # Calculate differences between consecutive frames in a vectorized way
                diffs = frames[1:].float() - frames[:-1].float()
                frame_diff_norms = torch.norm(diffs, p=2, dim=(1, 2, 3))

                # Get indices of the frames with the largest changes
                _, top_indices = torch.topk(frame_diff_norms, k=N, largest=True)

                # An index `i` in `frame_diff_norms` corresponds to the difference
                # between `frames[i]` and `frames[i+1]`. We choose `frames[i+1]` as the keyframe.
                keyframe_indices = sorted([idx.item() + 1 for idx in top_indices])
            else:
                keyframe_indices = []


            # Add first and last frames if requested
            if include_first_frame:
                keyframe_indices.insert(0, 0)
            if include_last_frame:
                keyframe_indices.append(num_frames - 1)

            # Remove duplicates and sort
            keyframe_indices = sorted(list(set(keyframe_indices)))

        # Select keyframes from the original tensor
        if not keyframe_indices:
            keyframe_tensors = torch.zeros((0, frames.shape[1], frames.shape[2], frames.shape[3]), dtype=frames.dtype, device=frames.device)
        else:
            keyframe_tensors = frames[keyframe_indices]
        
        # ComfyUI doesn't have a native LIST type for outputs.
        # We return the indices as a comma-separated string.
        indices_as_string = ", ".join(map(str, keyframe_indices))

        return (keyframe_tensors, indices_as_string)

class MakeGrid:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "frames": ("IMAGE", ),
                "max_width": ("INT", {
                        "default": 2048, 
                        "min": 64,
                        "max": 8000,
                        "step": 8
                }),
                "max_height": ("INT", {
                        "default": 2048, 
                        "min": 64,
                        "max": 8000,
                        "step": 8
                }),
            },
        }
    
    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("Grid", "Rows", "Columns")

    FUNCTION = "makegrid"
    CATEGORY = "Frames"

    def makegrid(self, frames, max_width, max_height):

        pils = mfu.cat_to_pils(frames)
        pils = mfu.normalize_size(pils) #normalize sizes to /8
        rows, cols = mfu.get_grid_aspect(len(pils), pils[0].width, pils[0].height)
        if len(pils) < rows*cols:
            pils = mfu.padlist(pils, rows*cols) #pad list with repeats (black space bad)
        if not rows == 8: max_height = mfu.closest_lcm(max_height, 8, rows)
        if not cols == 8: max_width = mfu.closest_lcm(max_width, 8, cols)

        grid = mfu.constrain_image(mfu.MakeGrid(pils, rows, cols), max_width, max_height)
        grid = mfu.pil_to_tens(grid).to(device)
        return (grid, rows, cols)

class BreakGrid:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "grid": ("IMAGE",),
                "rows": ("INT",{}),
                "columns": ("INT",{}),
            },
        }
    
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Frames",)

    FUNCTION = "breakgrid"
    CATEGORY = "Frames"

    def breakgrid(self, grid, rows, columns):
        pilgrids = mfu.cat_to_pils(grid)
        frames =[]
        for pilgrid in pilgrids:
            frames.extend(mfu.BreakGrid(pilgrid, rows, columns))
        frame_tensors = [mfu.pil_to_tens(frame) for frame in frames]
        cat_frame_tensors = torch.cat(frame_tensors, dim = 0).unsqueeze(0)

        return (cat_frame_tensors)
