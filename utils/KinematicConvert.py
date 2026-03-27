import os
import sys
import json
import subprocess
import tempfile

from .Functions import (
    get_addon_assets_path,
    get_game_doc_path_items,
    debug,
)


# Projected materials that will be invisible on moving (kinematic) items
PROJECTED_MATERIALS = [
    'customconcrete', 'customplastic', 'custombricks', 'customice',
    'customsnow', 'customdirt', 'customgrass', 'customrock',
    'customsand', 'custommetal', 'custommetalpainted',
    'customroughwood', 'customglass', 'customplasticshiny',
]


def get_kinematic_template_path():
    """Get path to the kinematic template item"""
    return os.path.join(get_addon_assets_path(), "kinematic_templates", "base_kinematic.Item.Gbx")


def get_kinematic_converter_path():
    """Get path to the kinematic converter binary"""
    # For now, use dotnet run on the prototype project
    # TODO: Ship a compiled binary with the addon
    return os.path.expanduser("~/Projects/public/kinematic-converter-prototype/KinematicConverter")


def convert_to_kinematic_if_needed(item_convert):
    """Check if the collection has kinematic enabled and convert the item if so.

    Args:
        item_convert: ItemConvert instance with collection, gbx_item_filepath, etc.
    """
    coll = item_convert.collection
    if coll is None:
        return

    if not getattr(coll, 'tm_kinematic_enabled', False):
        return

    debug(f"Kinematic conversion requested for {item_convert.name_raw}")

    # Warn about projected materials that will be invisible on moving items
    for obj in coll.all_objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            if slot.material:
                link = getattr(slot.material, 'link', '').lower()
                base_tex = getattr(slot.material, 'baseTexture', '').lower()
                for proj_mat in PROJECTED_MATERIALS:
                    if proj_mat in link or proj_mat in base_tex:
                        item_convert.add_progress_step(
                            f"WARNING: Material '{slot.material.name}' uses projected texture "
                            f"'{link or base_tex}' which will be INVISIBLE on moving items!"
                        )

    # Build the item path
    item_gbx_path = item_convert.gbx_item_filepath

    if not os.path.exists(item_gbx_path):
        item_convert.add_progress_step(f"WARNING: Item file not found for kinematic conversion: {item_gbx_path}")
        return

    template_path = get_kinematic_template_path()
    if not os.path.exists(template_path):
        item_convert.add_progress_step(f"WARNING: Kinematic template not found: {template_path}")
        return

    # Build animation config from collection properties
    # Pad all stage arrays to 4 (template has 4 slots each)
    _none_stage = {"easing": "None", "duration": 0, "reverse": False}

    rot_count = getattr(coll, 'tm_kinematic_rot_stages', 1)
    rot_stages = []
    for i in range(4):
        if i < rot_count:
            rot_stages.append({
                "easing": getattr(coll, f'tm_kinematic_rot_s{i}_easing', 'Linear'),
                "duration": getattr(coll, f'tm_kinematic_rot_s{i}_duration', 3000),
                "reverse": getattr(coll, f'tm_kinematic_rot_s{i}_reverse', False),
            })
        else:
            rot_stages.append(_none_stage.copy())

    trans_enabled = getattr(coll, 'tm_kinematic_trans_enabled', False)
    trans_count = getattr(coll, 'tm_kinematic_trans_stages', 2) if trans_enabled else 0
    trans_stages = []
    for i in range(4):
        if i < trans_count:
            trans_stages.append({
                "easing": getattr(coll, f'tm_kinematic_trans_s{i}_easing', 'Linear'),
                "duration": getattr(coll, f'tm_kinematic_trans_s{i}_duration', 3000),
                "reverse": getattr(coll, f'tm_kinematic_trans_s{i}_reverse', (i == 1)),
            })
        else:
            trans_stages.append(_none_stage.copy())

    animation = {
        "rotAxis": getattr(coll, 'tm_kinematic_rot_axis', 'Y'),
        "angleMin": getattr(coll, 'tm_kinematic_rot_min', 0),
        "angleMax": getattr(coll, 'tm_kinematic_rot_max', 360),
        "rotStages": rot_stages,
        "transAxis": getattr(coll, 'tm_kinematic_trans_axis', 'Y'),
        "transMin": getattr(coll, 'tm_kinematic_trans_min', 0),
        "transMax": getattr(coll, 'tm_kinematic_trans_max', 8) if trans_enabled else 0,
        "transStages": trans_stages,
    }

    config = {
        "templatePath": template_path,
        "sourcePath": item_gbx_path,
        "outputPath": item_gbx_path,  # overwrite in place
        "animation": animation,
    }

    # Write config to temp file
    config_file = None
    try:
        config_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(config, config_file)
        config_file.close()

        converter_path = get_kinematic_converter_path()

        env = os.environ.copy()
        # macOS needs DYLD_LIBRARY_PATH for LZO and dotnet in PATH
        if sys.platform == 'darwin':
            env['DYLD_LIBRARY_PATH'] = '/opt/homebrew/lib'
            # Blender on macOS may not have homebrew in PATH
            env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + env.get('PATH', '')

        # Find dotnet - try common locations
        dotnet_cmd = 'dotnet'
        if sys.platform == 'darwin':
            for dotnet_path in ['/opt/homebrew/bin/dotnet', '/usr/local/bin/dotnet']:
                if os.path.exists(dotnet_path):
                    dotnet_cmd = dotnet_path
                    break

        cmd = [dotnet_cmd, 'run', '--project', converter_path, '--', config_file.name]

        debug(f"Running kinematic converter: {' '.join(cmd)}")
        item_convert.add_progress_step(f"Converting to kinematic (moving item)...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

        if result.returncode == 0:
            item_convert.add_progress_step(f"Kinematic conversion succeeded")
            debug(f"Kinematic conversion output:\n{result.stdout}")
        else:
            item_convert.add_progress_step(f"WARNING: Kinematic conversion failed (exit code {result.returncode})")
            debug(f"Kinematic converter stderr:\n{result.stderr}")
            debug(f"Kinematic converter stdout:\n{result.stdout}")

    except subprocess.TimeoutExpired:
        item_convert.add_progress_step(f"WARNING: Kinematic conversion timed out")
    except Exception as e:
        item_convert.add_progress_step(f"WARNING: Kinematic conversion error: {str(e)}")
    finally:
        if config_file and os.path.exists(config_file.name):
            os.unlink(config_file.name)
