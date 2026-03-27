
import bpy
import math
from bpy.types import Operator
from mathutils import Vector

from ..utils.Functions import (
    get_global_props,
    get_active_collection_of_selected_object,
    debug,
)
from .OT_KinematicPreview import is_kinematic_eligible


def _get_pattern_props():
    """Return the global panel properties."""
    return get_global_props()


def _duplicate_object(source, collection, index):
    """Create a full duplicate of source and link it into the collection.

    Returns the new object with a kinematic naming convention.
    """
    new_obj = source.copy()
    new_obj.data = source.data.copy()
    new_obj.name = f"{source.name}_kin_{index:02d}"
    collection.objects.link(new_obj)
    return new_obj


def _configure_rotation(obj, axis="Z", rot_min=0, rot_max=360, stages=1, duration=3000, easing="Linear"):
    """Set rotation kinematic properties on an object."""
    obj.tm_kinematic_animated = True
    obj.tm_kinematic_rot_axis = axis
    obj.tm_kinematic_rot_min = rot_min
    obj.tm_kinematic_rot_max = rot_max
    obj.tm_kinematic_rot_stages = stages
    for i in range(stages):
        setattr(obj, f"tm_kinematic_rot_s{i}_duration", duration)
        setattr(obj, f"tm_kinematic_rot_s{i}_easing", easing)


def _configure_translation(obj, axis="Y", trans_min=0, trans_max=8, stages=1,
                           duration=3000, easing="Linear", enable=True):
    """Set translation kinematic properties on an object."""
    obj.tm_kinematic_trans_enabled = enable
    obj.tm_kinematic_trans_axis = axis
    obj.tm_kinematic_trans_min = trans_min
    obj.tm_kinematic_trans_max = trans_max
    obj.tm_kinematic_trans_stages = stages
    for i in range(stages):
        setattr(obj, f"tm_kinematic_trans_s{i}_duration", duration)
        setattr(obj, f"tm_kinematic_trans_s{i}_easing", easing)
        setattr(obj, f"tm_kinematic_trans_s{i}_reverse", (i == 1))


def _generate_burst(source, collection, props):
    """Burst: N copies in a circle, each translates outward."""
    count = props.NU_kinematic_pattern_count
    radius = props.NU_kinematic_pattern_radius
    duration = props.NU_kinematic_pattern_duration
    easing = props.LI_kinematic_pattern_easing
    center = source.location.copy()

    generated = []
    for i in range(count):
        angle = i * (2 * math.pi / count)
        obj = _duplicate_object(source, collection, i)
        obj.location = center + Vector((
            math.cos(angle) * (radius * 0.25),
            math.sin(angle) * (radius * 0.25),
            0,
        ))
        obj.rotation_euler.z = angle

        _configure_rotation(obj, axis="Z", rot_min=0, rot_max=0, stages=1,
                            duration=duration, easing="None")
        _configure_translation(obj, axis="Y", trans_min=0, trans_max=radius,
                               stages=1, duration=duration, easing=easing)
        generated.append(obj)
    return generated


def _generate_ring(source, collection, props):
    """Ring: N copies in a circle, all rotating (turntable)."""
    count = props.NU_kinematic_pattern_count
    radius = props.NU_kinematic_pattern_radius
    duration = props.NU_kinematic_pattern_duration
    easing = props.LI_kinematic_pattern_easing
    center = source.location.copy()

    generated = []
    for i in range(count):
        angle = i * (2 * math.pi / count)
        obj = _duplicate_object(source, collection, i)
        obj.location = center + Vector((
            math.cos(angle) * radius,
            math.sin(angle) * radius,
            0,
        ))
        _configure_rotation(obj, axis="Z", rot_min=0, rot_max=360,
                            stages=1, duration=duration, easing=easing)
        generated.append(obj)
    return generated


def _generate_wave(source, collection, props):
    """Wave: N copies in a line, each with vertical oscillation offset."""
    count = props.NU_kinematic_pattern_count
    spacing = props.NU_kinematic_pattern_spacing
    amplitude = props.NU_kinematic_pattern_amplitude
    duration = props.NU_kinematic_pattern_duration
    easing = props.LI_kinematic_pattern_easing
    center = source.location.copy()

    generated = []
    for i in range(count):
        obj = _duplicate_object(source, collection, i)
        obj.location = center + Vector((i * spacing, 0, 0))

        obj.tm_kinematic_animated = True
        obj.tm_kinematic_trans_enabled = True
        obj.tm_kinematic_trans_axis = "Z"
        obj.tm_kinematic_trans_min = 0
        obj.tm_kinematic_trans_max = amplitude
        obj.tm_kinematic_trans_stages = 2

        stage_dur = duration // 2 if duration > 0 else 1500
        eas = easing if easing != "None" else "QuadInOut"

        obj.tm_kinematic_trans_s0_easing = eas
        obj.tm_kinematic_trans_s0_duration = stage_dur
        obj.tm_kinematic_trans_s0_reverse = False

        obj.tm_kinematic_trans_s1_easing = eas
        obj.tm_kinematic_trans_s1_duration = stage_dur
        obj.tm_kinematic_trans_s1_reverse = True

        # Rotation is effectively off but must be valid
        _configure_rotation(obj, axis="Z", rot_min=0, rot_max=0, stages=1,
                            duration=duration, easing="None")

        generated.append(obj)
    return generated


def _generate_spiral(source, collection, props):
    """Spiral: N copies in a helix, rotating + translating vertically."""
    count = props.NU_kinematic_pattern_count
    radius = props.NU_kinematic_pattern_radius
    total_height = props.NU_kinematic_pattern_height
    duration = props.NU_kinematic_pattern_duration
    easing = props.LI_kinematic_pattern_easing
    center = source.location.copy()
    height_step = total_height / max(count - 1, 1)

    generated = []
    for i in range(count):
        angle = i * (2 * math.pi / count)
        height = i * height_step
        obj = _duplicate_object(source, collection, i)
        obj.location = center + Vector((
            math.cos(angle) * radius,
            math.sin(angle) * radius,
            height,
        ))
        _configure_rotation(obj, axis="Z", rot_min=0, rot_max=360,
                            stages=1, duration=duration, easing=easing)
        _configure_translation(obj, axis="Z", trans_min=0, trans_max=total_height,
                               stages=1, duration=duration, easing=easing)
        generated.append(obj)
    return generated


def _generate_grid(source, collection, props):
    """Grid: NxM grid, each rotating."""
    cols = props.NU_kinematic_pattern_cols
    rows = props.NU_kinematic_pattern_rows
    spacing = props.NU_kinematic_pattern_spacing
    duration = props.NU_kinematic_pattern_duration
    easing = props.LI_kinematic_pattern_easing
    center = source.location.copy()

    generated = []
    idx = 0
    for x in range(cols):
        for y in range(rows):
            obj = _duplicate_object(source, collection, idx)
            obj.location = center + Vector((x * spacing, y * spacing, 0))
            _configure_rotation(obj, axis="Z", rot_min=0, rot_max=360,
                                stages=1, duration=duration, easing=easing)
            generated.append(obj)
            idx += 1
    return generated


def _generate_custom(source, collection, props):
    """Custom: user provides Python expressions evaluated per-instance."""
    count = props.NU_kinematic_pattern_count
    expr_pos = props.ST_kinematic_pattern_expr_pos
    expr_rot = props.ST_kinematic_pattern_expr_rot
    expr_anim = props.ST_kinematic_pattern_expr_anim
    center = source.location.copy()

    generated = []
    for i in range(count):
        n = count
        angle = i * (2 * math.pi / max(n, 1))
        t = i / max(n - 1, 1)

        namespace = {
            "i": i,
            "n": n,
            "angle": angle,
            "t": t,
            "pi": math.pi,
            "sin": math.sin,
            "cos": math.cos,
            "radians": math.radians,
            "degrees": math.degrees,
            "sqrt": math.sqrt,
            "abs": abs,
        }

        # Evaluate position expression -> x, y, z
        try:
            pos_result = eval(f"({expr_pos})", {"__builtins__": {}}, namespace)
            if isinstance(pos_result, (list, tuple)) and len(pos_result) >= 3:
                px, py, pz = float(pos_result[0]), float(pos_result[1]), float(pos_result[2])
            else:
                px, py, pz = 0, 0, 0
        except Exception:
            px, py, pz = 0, 0, 0

        # Evaluate rotation expression -> rx, ry, rz
        try:
            rot_result = eval(f"({expr_rot})", {"__builtins__": {}}, namespace)
            if isinstance(rot_result, (list, tuple)) and len(rot_result) >= 3:
                rx, ry, rz = float(rot_result[0]), float(rot_result[1]), float(rot_result[2])
            else:
                rx, ry, rz = 0, 0, 0
        except Exception:
            rx, ry, rz = 0, 0, 0

        obj = _duplicate_object(source, collection, i)
        obj.location = center + Vector((px, py, pz))
        obj.rotation_euler = (rx, ry, rz)
        obj.tm_kinematic_animated = True

        # Default kinematic settings
        obj.tm_kinematic_rot_axis = "Z"
        obj.tm_kinematic_rot_min = 0
        obj.tm_kinematic_rot_max = 0
        obj.tm_kinematic_rot_stages = 1
        obj.tm_kinematic_rot_s0_duration = 3000
        obj.tm_kinematic_rot_s0_easing = "Linear"
        obj.tm_kinematic_trans_enabled = False

        # Evaluate animation expression (semicolon-separated assignments)
        anim_ns = {
            "i": i,
            "n": n,
            "angle": angle,
            "t": t,
            "pi": math.pi,
            "sin": math.sin,
            "cos": math.cos,
            "radians": math.radians,
            "degrees": math.degrees,
        }
        if expr_anim.strip():
            for stmt in expr_anim.split(";"):
                stmt = stmt.strip()
                if not stmt or "=" not in stmt:
                    continue
                key, _, val_expr = stmt.partition("=")
                key = key.strip()
                try:
                    val = eval(val_expr.strip(), {"__builtins__": {}}, anim_ns)
                except Exception:
                    continue

                prop_map = {
                    "rot_axis": "tm_kinematic_rot_axis",
                    "rot_min": "tm_kinematic_rot_min",
                    "rot_max": "tm_kinematic_rot_max",
                    "rot_stages": "tm_kinematic_rot_stages",
                    "rot_duration": "tm_kinematic_rot_s0_duration",
                    "rot_easing": "tm_kinematic_rot_s0_easing",
                    "trans_enabled": "tm_kinematic_trans_enabled",
                    "trans_axis": "tm_kinematic_trans_axis",
                    "trans_min": "tm_kinematic_trans_min",
                    "trans_max": "tm_kinematic_trans_max",
                    "trans_stages": "tm_kinematic_trans_stages",
                    "trans_duration": "tm_kinematic_trans_s0_duration",
                    "trans_easing": "tm_kinematic_trans_s0_easing",
                }
                prop_name = prop_map.get(key)
                if prop_name:
                    try:
                        setattr(obj, prop_name, val)
                    except Exception:
                        pass

        generated.append(obj)
    return generated


_PATTERN_GENERATORS = {
    "BURST": _generate_burst,
    "RING": _generate_ring,
    "WAVE": _generate_wave,
    "SPIRAL": _generate_spiral,
    "GRID": _generate_grid,
    "CUSTOM": _generate_custom,
}


class TM_OT_KinematicPatternGenerate(Operator):
    """Generate multiple copies of a mesh with kinematic animation properties arranged in a pattern"""
    bl_idname = "view3d.tm_kinematic_pattern_generate"
    bl_label = "Generate Kinematic Pattern"
    bl_description = "Create copies of the selected mesh arranged in a pattern with kinematic animation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            return False
        coll = get_active_collection_of_selected_object()
        if coll is None:
            return False
        return coll.tm_kinematic_enabled

    def execute(self, context):
        source = context.active_object
        coll = get_active_collection_of_selected_object()
        if source is None or source.type != "MESH":
            self.report({"WARNING"}, "Select a mesh object first")
            return {"CANCELLED"}
        if coll is None:
            self.report({"WARNING"}, "No active collection")
            return {"CANCELLED"}
        if not coll.tm_kinematic_enabled:
            self.report({"WARNING"}, "Enable 'Moving Item' on the collection first")
            return {"CANCELLED"}

        props = _get_pattern_props()
        pattern = props.LI_kinematic_pattern

        generator = _PATTERN_GENERATORS.get(pattern)
        if generator is None:
            self.report({"ERROR"}, f"Unknown pattern: {pattern}")
            return {"CANCELLED"}

        generated = generator(source, coll, props)

        # Ensure all generated objects have tm_kinematic_animated = True
        for obj in generated:
            obj.tm_kinematic_animated = True

        self.report({"INFO"}, f"Generated {len(generated)} kinematic objects ({pattern})")
        return {"FINISHED"}


class TM_OT_KinematicPatternClear(Operator):
    """Remove all objects matching _kin_## pattern from the active collection"""
    bl_idname = "view3d.tm_kinematic_pattern_clear"
    bl_label = "Clear Generated Pattern"
    bl_description = "Remove all generated kinematic pattern objects (_kin_##) from the active collection"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        coll = get_active_collection_of_selected_object()
        return coll is not None

    def execute(self, context):
        import re
        coll = get_active_collection_of_selected_object()
        if coll is None:
            self.report({"WARNING"}, "No active collection")
            return {"CANCELLED"}

        pattern = re.compile(r"_kin_\d{2}$")
        to_remove = [obj for obj in list(coll.objects) if pattern.search(obj.name)]

        count = len(to_remove)
        for obj in to_remove:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            # Clean up orphan mesh data
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

        self.report({"INFO"}, f"Removed {count} generated objects")
        return {"FINISHED"}
