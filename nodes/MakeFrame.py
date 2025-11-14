import torch
import numpy as np
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
                "scene_cut_method": (["MSE", "SSIM", "pHash"],),
                "scene_select_method": (["Uniform", "Peak_Difference", "Edge_Change_Rate", "Highest_Contrast"],),
                "num_keyframes": ("INT", {
                        "default": 12, 
                        "min": 1,
                        "max": 4096,
                        "step": 1
                }),
                "threshold": ("FLOAT", {
                        "default": 0.1,
                        "min": 0.0,
                        "max": 10000.0,
                        "step": 0.01
                }),
                "central_focus_ratio": ("FLOAT", {
                        "default": 0.3,
                        "min": 0.1,
                        "max": 1.0,
                        "step": 0.05
                }),
            },
        }
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("Keyframes", "keyframe_indices")

    FUNCTION = "getkeyframes"
    CATEGORY = "Frames"

    def getkeyframes(self, frames, scene_cut_method, scene_select_method, num_keyframes, threshold, central_focus_ratio):
        num_frames = frames.shape[0]
        if num_frames < 2:
            return (frames, ", ".join(map(str, range(num_frames))))

        # --- 1. Calculate Frame Differences ---
        frames_pil = mfu.cat_to_pils(frames)
        if scene_cut_method == "MSE":
            frame_diffs = mfu.calculate_mse_diff(frames[:-1], frames[1:])
        elif scene_cut_method == "SSIM":
            frame_diffs = mfu.calculate_ssim_diff(frames_pil[:-1], frames_pil[1:])
        elif scene_cut_method == "pHash":
            frame_diffs = mfu.calculate_phash_diff(frames_pil[:-1], frames_pil[1:])

        # --- Normalize Diffs ---
        if frame_diffs.numel() > 0:
            max_diff = torch.max(frame_diffs)
            if max_diff > 0:
                frame_diffs = frame_diffs / max_diff

        # --- 2. Scene Segmentation with Priority Filtering ---
        potential_cut_indices = (frame_diffs > threshold).nonzero(as_tuple=True)[0]
        
        if len(potential_cut_indices) + 1 > num_keyframes:
            num_cuts_to_keep = max(0, num_keyframes - 1)
            if num_cuts_to_keep > 0:
                cut_diffs = frame_diffs[potential_cut_indices]
                _, top_indices = torch.topk(cut_diffs, k=num_cuts_to_keep)
                final_cut_indices = potential_cut_indices[top_indices]
            else:
                final_cut_indices = torch.tensor([], dtype=torch.long)
        else:
            final_cut_indices = potential_cut_indices

        scene_boundaries = [0] + [(i.item() + 1) for i in sorted(final_cut_indices)] + [num_frames]
        scene_boundaries = sorted(list(set(scene_boundaries)))

        scenes = []
        for i in range(len(scene_boundaries) - 1):
            start, end = scene_boundaries[i], scene_boundaries[i+1]
            if start < end:
                scenes.append(list(range(start, end)))
        
        if not scenes:
             scenes.append(list(range(num_frames)))

        # --- 3. Dynamic Quota Allocation ---
        num_scenes = len(scenes)
        if num_scenes == 0:
            return (torch.zeros((0, frames.shape[1], frames.shape[2], frames.shape[3]), dtype=frames.dtype, device=frames.device), "")

        base_quota = num_keyframes / num_scenes
        quotas = [min(int(base_quota), len(scene)) for scene in scenes]
        remaining_quota = num_keyframes - sum(quotas)
        
        if remaining_quota > 0:
            priority_scores = [(base_quota - q) / len(s) if len(s) > 0 else 0 for q, s in zip(quotas, scenes)]
            sorted_scenes_indices = np.argsort(priority_scores)[::-1]
            
            for i in sorted_scenes_indices:
                if remaining_quota == 0: break
                if quotas[i] < len(scenes[i]):
                    quotas[i] += 1
                    remaining_quota -= 1

        # --- 4. Keyframe Extraction within Scenes ---
        keyframe_indices = []
        
        def find_peaks_with_suppression(scores, num_peaks, suppression_radius=1):
            peaks = []
            scores_copy = scores.clone()
            for _ in range(num_peaks):
                if not len(scores_copy) > 0 or scores_copy.max() < 0: break
                
                peak_idx = torch.argmax(scores_copy).item()
                peaks.append(peak_idx)
                
                start = max(0, peak_idx - suppression_radius)
                end = min(len(scores_copy), peak_idx + suppression_radius + 1)
                scores_copy[start:end] = -1
            return sorted(peaks)

        for i, scene in enumerate(scenes):
            quota = quotas[i]
            if quota == 0: continue

            if len(scene) <= quota:
                keyframe_indices.extend(scene)
                continue

            if scene_select_method == "Uniform":
                indices_to_sample = np.linspace(0, len(scene) - 1, quota, dtype=int)
                keyframe_indices.extend([scene[j] for j in indices_to_sample])

            else:
                scene_frames_pil = [frames_pil[i] for i in scene]
                
                if scene_select_method == "Peak_Difference":
                    base_frame_pil = scene_frames_pil[0]
                    if scene_cut_method == "MSE":
                        base_frame_t = frames[scene[0]].unsqueeze(0)
                        scene_frames_t = frames[scene]
                        internal_diffs = mfu.calculate_mse_diff(base_frame_t.repeat(len(scene),1,1,1), scene_frames_t)
                    elif scene_cut_method == "SSIM":
                        internal_diffs = mfu.calculate_ssim_diff([base_frame_pil] * len(scene_frames_pil), scene_frames_pil)
                    else: # pHash
                        internal_diffs = mfu.calculate_phash_diff([base_frame_pil] * len(scene_frames_pil), scene_frames_pil)
                    
                    peak_indices_in_scene = find_peaks_with_suppression(internal_diffs, quota)
                    keyframe_indices.extend([scene[j] for j in peak_indices_in_scene])

                elif scene_select_method == "Edge_Change_Rate":
                    if len(scene) < 2:
                        keyframe_indices.extend(scene)
                        continue
                    internal_diffs = torch.tensor([mfu.calculate_edge_diff(scene_frames_pil[j], scene_frames_pil[j+1], central_focus_ratio) for j in range(len(scene_frames_pil)-1)])
                    
                    peak_indices_in_diff_array = find_peaks_with_suppression(internal_diffs, quota)
                    keyframe_indices.extend([scene[j + 1] for j in peak_indices_in_diff_array])

                elif scene_select_method == "Highest_Contrast":
                    contrasts = torch.tensor([mfu.calculate_contrast(p) for p in scene_frames_pil])
                    peak_indices_in_scene = find_peaks_with_suppression(contrasts, quota)
                    keyframe_indices.extend([scene[j] for j in peak_indices_in_scene])

        # --- 5. Final Touches ---
        keyframe_indices = sorted(list(set(keyframe_indices)))

        if not keyframe_indices:
            keyframe_tensors = torch.zeros((0, frames.shape[1], frames.shape[2], frames.shape[3]), dtype=frames.dtype, device=frames.device)
        else:
            keyframe_tensors = frames[keyframe_indices]
        
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
        pils = mfu.normalize_size(pils)
        rows, cols = mfu.get_grid_aspect(len(pils), pils[0].width, pils[0].height)
        if len(pils) < rows*cols:
            pils = mfu.padlist(pils, rows*cols)
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
