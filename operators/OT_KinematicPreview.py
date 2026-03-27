
import bpy
import math
from bpy.types import Operator
from bpy.props import StringProperty

from ..utils.Functions import (
    get_active_collection_of_selected_object,
    debug,
)


# Global dict to store original transforms keyed by (collection_name, object_name)
_original_transforms = {}

# Special name prefixes to exclude from kinematic animated parts list
KINEMATIC_EXCLUDE_PREFIXES = ("_trigger_", "_socket_", "_ignore_", "_icon_only_")


def is_kinematic_eligible(obj):
    """Check if an object is eligible to be an animated kinematic part."""
    if obj.type != "MESH":
        return False
    name_lower = obj.name.lower()
    for prefix in KINEMATIC_EXCLUDE_PREFIXES:
        if prefix in name_lower:
            return False
    return True


def apply_easing(t, easing):
    """Apply easing function to a linear t (0-1)."""
    if easing == "Linear":
        return t
    if easing == "QuadIn":
        return t * t
    if easing == "QuadOut":
        return t * (2.0 - t)
    if easing == "QuadInOut":
        return 2.0 * t * t if t < 0.5 else -1.0 + (4.0 - 2.0 * t) * t
    # "None" means no animation
    return 0.0


def compute_animation_value(obj, prefix, total_progress):
    """Compute the animation value (0.0 - 1.0) for rotation or translation at a given total_progress.

    Args:
        obj: The Blender object with kinematic properties.
        prefix: "rot" or "trans".
        total_progress: float 0.0 to 1.0 representing overall animation progress.

    Returns:
        float: animation value between 0.0 and 1.0.
    """
    num_stages = getattr(obj, f"tm_kinematic_{prefix}_stages", 1)

    # Gather stage data
    stages = []
    for i in range(num_stages):
        easing = getattr(obj, f"tm_kinematic_{prefix}_s{i}_easing", "Linear")
        duration = getattr(obj, f"tm_kinematic_{prefix}_s{i}_duration", 3000)
        reverse = getattr(obj, f"tm_kinematic_{prefix}_s{i}_reverse", False)
        stages.append({
            "easing": easing,
            "duration": duration,
            "reverse": reverse,
        })

    total_duration = sum(s["duration"] for s in stages if s["duration"] > 0)
    if total_duration == 0:
        return 0.0

    elapsed = total_progress * total_duration

    for stage in stages:
        if stage["duration"] <= 0:
            continue
        if elapsed <= stage["duration"]:
            t = elapsed / stage["duration"]
            t = apply_easing(t, stage["easing"])
            if stage["reverse"]:
                t = 1.0 - t
            return t
        elapsed -= stage["duration"]

    # Past the end — return final state
    last_active = None
    for s in stages:
        if s["duration"] > 0:
            last_active = s
    if last_active and last_active["reverse"]:
        return 0.0
    return 1.0


def store_original_transform(coll, obj):
    """Store the original transform for an object in a collection."""
    key = (coll.name, obj.name)
    if key not in _original_transforms:
        _original_transforms[key] = {
            "location": obj.location.copy(),
            "rotation_euler": obj.rotation_euler.copy(),
        }


def get_original_transform(coll, obj):
    """Get the stored original transform for an object."""
    key = (coll.name, obj.name)
    return _original_transforms.get(key, None)


def restore_original_transform(coll, obj):
    """Restore object to its original transform."""
    orig = get_original_transform(coll, obj)
    if orig:
        obj.location = orig["location"].copy()
        obj.rotation_euler = orig["rotation_euler"].copy()


def clear_original_transforms(coll):
    """Clear all stored transforms for a collection."""
    keys_to_remove = [k for k in _original_transforms if k[0] == coll.name]
    for k in keys_to_remove:
        del _original_transforms[k]


def update_kinematic_preview(coll, progress):
    """Update all animated objects in a collection based on preview progress.

    Args:
        coll: The Blender collection with tm_kinematic_enabled.
        progress: float 0.0 to 1.0.
    """
    from mathutils import Matrix, Vector

    for obj in coll.all_objects:
        if not is_kinematic_eligible(obj):
            continue
        if not getattr(obj, "tm_kinematic_animated", False):
            continue

        # Store original transform on first use
        store_original_transform(coll, obj)
        orig = get_original_transform(coll, obj)

        # Start from original transform
        new_location = orig["location"].copy()
        new_rotation = orig["rotation_euler"].copy()

        # Rotation
        rot_value = compute_animation_value(obj, "rot", progress)
        rot_min = math.radians(obj.tm_kinematic_rot_min)
        rot_max = math.radians(obj.tm_kinematic_rot_max)
        angle = rot_min + rot_value * (rot_max - rot_min)

        axis = obj.tm_kinematic_rot_axis
        if axis == "X":
            new_rotation.x = orig["rotation_euler"].x + angle
        elif axis == "Y":
            new_rotation.y = orig["rotation_euler"].y + angle
        elif axis == "Z":
            new_rotation.z = orig["rotation_euler"].z + angle

        # Translation
        if obj.tm_kinematic_trans_enabled:
            trans_value = compute_animation_value(obj, "trans", progress)
            trans_min = obj.tm_kinematic_trans_min
            trans_max = obj.tm_kinematic_trans_max
            offset = trans_min + trans_value * (trans_max - trans_min)

            trans_axis = obj.tm_kinematic_trans_axis
            if trans_axis == "X":
                new_location.x = orig["location"].x + offset
            elif trans_axis == "Y":
                new_location.y = orig["location"].y + offset
            elif trans_axis == "Z":
                new_location.z = orig["location"].z + offset

        obj.location = new_location
        obj.rotation_euler = new_rotation


def on_preview_progress_update(self, context):
    """Called when the preview slider moves on a collection."""
    # 'self' is the Collection that owns the property
    coll = self
    if coll and coll.tm_kinematic_enabled:
        update_kinematic_preview(coll, coll.tm_kinematic_preview_progress)


class TM_OT_KinematicPreviewReset(Operator):
    """Reset all animated objects to their original transforms"""
    bl_idname = "view3d.tm_kinematic_preview_reset"
    bl_label = "Reset Preview"
    bl_description = "Reset all animated objects to their original positions"

    def execute(self, context):
        coll = get_active_collection_of_selected_object()
        if coll is None:
            self.report({"WARNING"}, "No active collection")
            return {"CANCELLED"}

        for obj in coll.all_objects:
            if not is_kinematic_eligible(obj):
                continue
            if not getattr(obj, "tm_kinematic_animated", False):
                continue
            restore_original_transform(coll, obj)

        coll.tm_kinematic_preview_progress = 0.0
        clear_original_transforms(coll)

        # Force viewport update
        if context.area:
            context.area.tag_redraw()

        return {"FINISHED"}


class TM_OT_KinematicPreviewPlay(Operator):
    """Toggle play/pause of the animation preview"""
    bl_idname = "view3d.tm_kinematic_preview_play"
    bl_label = "Play Preview"
    bl_description = "Play or pause the animation preview"

    _timer = None
    _playing = False
    _instance = None

    @classmethod
    def poll(cls, context):
        return True

    @classmethod
    def is_playing(cls):
        return cls._playing

    def modal(self, context, event):
        if not TM_OT_KinematicPreviewPlay._playing:
            self._stop_timer(context)
            return {"CANCELLED"}

        if event.type == "TIMER":
            coll = get_active_collection_of_selected_object()
            if coll is None or not coll.tm_kinematic_enabled:
                self._stop_timer(context)
                TM_OT_KinematicPreviewPlay._playing = False
                return {"CANCELLED"}

            progress = coll.tm_kinematic_preview_progress
            progress += 0.005
            if progress >= 1.0:
                progress = 0.0

            coll.tm_kinematic_preview_progress = progress

            for area in context.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()

            return {"PASS_THROUGH"}

        if event.type in {"ESC", "RIGHTMOUSE"}:
            TM_OT_KinematicPreviewPlay._playing = False
            self._stop_timer(context)
            return {"CANCELLED"}

        return {"PASS_THROUGH"}

    def execute(self, context):
        if TM_OT_KinematicPreviewPlay._playing:
            # Pause
            TM_OT_KinematicPreviewPlay._playing = False
            return {"FINISHED"}

        # Play
        TM_OT_KinematicPreviewPlay._playing = True
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0 / 30.0, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _stop_timer(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
