bl_info = {
    "name": "Universal Snow Mask Tool",
    "author": "OpenAI Codex",
    "version": (1, 3, 2),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > Snow Mask",
    "description": "Import FBX, apply an adjustable snow mask material, and sync controls across submeshes.",
    "category": "Material",
}
import math
import re
import struct
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import bpy
import mathutils

TEMPLATE_BLEND = Path(r"C:\Users\caishuo01\Documents\BlenderSnowMask\snow_mask_hp_bank01_original_texture_snow_mix_new.blend")
TEMPLATE_MATERIAL = "M_hp_bank01_02_OriginalTexture_SnowMix"
SNOW_GROUP_NAME = "NG_Adjustable_Snow_Mask"
CONTROL_NODE_NAME = "SNOW_MASK_CONTROLS"
SNOW_COLOR = (0.86, 0.90, 0.94, 1.0)
SNOW_ROUGHNESS = 0.88
SNOW_METALLIC = 0.0
SNOW_NORMAL_STRENGTH_SCALE = 0.35


def clean_name(name):
    for prefix in ("Material::", "Model::", "Texture::", "Video::", "Geometry::"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def socket(node, *names):
    if node is None:
        return None
    for name in names:
        if name in node.inputs:
            return node.inputs[name]
    return None


def set_input(node, names, value):
    sock = socket(node, *names)
    if sock is not None:
        sock.default_value = value


def copy_socket_value(src, dst):
    try:
        dst.default_value = src.default_value
    except Exception:
        pass


def clear_material(mat):
    mat.use_nodes = True
    tree = mat.node_tree
    for node in list(tree.nodes):
        tree.nodes.remove(node)
    return tree


def is_ascii_fbx(path):
    with open(path, "rb") as stream:
        return not stream.read(23).startswith(b"Kaydara FBX Binary")


def load_image(path, colorspace="sRGB"):
    if not path:
        return None
    path = Path(path)
    if not path.exists():
        return None
    image = bpy.data.images.load(str(path), check_existing=True)
    try:
        image.colorspace_settings.name = colorspace
    except Exception:
        pass
    if path.suffix.lower() in {".tga", ".png"}:
        image.alpha_mode = "CHANNEL_PACKED"
    return image


def append_template_assets():
    materials_to_load = []
    groups_to_load = []
    with bpy.data.libraries.load(str(TEMPLATE_BLEND), link=False) as (data_from, data_to):
        if TEMPLATE_MATERIAL in data_from.materials and TEMPLATE_MATERIAL not in bpy.data.materials:
            materials_to_load.append(TEMPLATE_MATERIAL)
        if SNOW_GROUP_NAME in data_from.node_groups and SNOW_GROUP_NAME not in bpy.data.node_groups:
            groups_to_load.append(SNOW_GROUP_NAME)
        data_to.materials = materials_to_load
        data_to.node_groups = groups_to_load
    if SNOW_GROUP_NAME not in bpy.data.node_groups:
        raise RuntimeError(f"Missing node group: {SNOW_GROUP_NAME}")


def template_control_node():
    append_template_assets()
    mat = bpy.data.materials.get(TEMPLATE_MATERIAL)
    if not mat or not mat.node_tree:
        return None
    return mat.node_tree.nodes.get(CONTROL_NODE_NAME)


def copy_template_defaults(group_node):
    source_node = template_control_node()
    if not source_node:
        return
    by_name = {inp.name: inp for inp in source_node.inputs}
    for dst in group_node.inputs:
        src = by_name.get(dst.name)
        if src:
            copy_socket_value(src, dst)


def find_principled(mat):
    if not mat or not mat.node_tree:
        return None
    for node in mat.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            return node
    return None


def linked_image_from_socket(sock):
    if not sock:
        return None
    for link in sock.links:
        node = link.from_node
        if node.bl_idname == "ShaderNodeTexImage" and node.image:
            return node.image
    return None


def image_by_suffix(mat, suffixes):
    if not mat or not mat.node_tree:
        return None
    suffixes = tuple(s.lower() for s in suffixes)
    for node in mat.node_tree.nodes:
        image = getattr(node, "image", None)
        if not image:
            continue
        stem = Path(bpy.path.abspath(image.filepath or image.name)).stem.lower()
        if stem.endswith(suffixes):
            return image
    return None


def material_source_images(original_mat):
    bsdf = find_principled(original_mat)
    diffuse = linked_image_from_socket(socket(bsdf, "Base Color")) if bsdf else None
    normal = image_by_suffix(original_mat, ("_n", "_normal"))
    packed_m = image_by_suffix(original_mat, ("_m", "_orm", "_mr", "_mask"))
    diffuse = diffuse or image_by_suffix(original_mat, ("_d", "_diff", "_diffuse", "_albedo", "_basecolor"))
    return diffuse, normal, packed_m


def new_tex_node(tree, name, image, loc, colorspace=None):
    if not image:
        return None
    if colorspace:
        try:
            image.colorspace_settings.name = colorspace
        except Exception:
            pass
    node = tree.nodes.new("ShaderNodeTexImage")
    node.name = name
    node.label = name
    node.image = image
    node.location = loc
    return node


def create_snow_mix_material(original_mat, shared_name=None):
    append_template_assets()
    base_name = clean_name(original_mat.name if original_mat else "Base")
    mat_name = shared_name or f"M_{base_name}_OriginalTexture_SnowMix"
    if mat_name in bpy.data.materials:
        bpy.data.materials.remove(bpy.data.materials[mat_name])
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    mat.blend_method = "OPAQUE"
    mat.diffuse_color = (0.75, 0.78, 0.80, 1.0)
    tree = clear_material(mat)
    nodes = tree.nodes
    links = tree.links
    diffuse_img, normal_img, packed_m_img = material_source_images(original_mat)
    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (650, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    set_input(bsdf, ["Alpha"], 1.0)
    # Texture nodes intentionally use the mesh active UV. Different FBX files may use different UV set names.
    diffuse = new_tex_node(tree, "Original Diffuse (Alpha Ignored)", diffuse_img, (-820, 260), "sRGB")
    normal = new_tex_node(tree, "Original Normal", normal_img, (-820, -220), "Non-Color")
    packed_m = new_tex_node(tree, "Original Packed M/Mask", packed_m_img, (-820, -560), "Non-Color")
    snow = nodes.new("ShaderNodeGroup")
    snow.name = CONTROL_NODE_NAME
    snow.label = "SNOW MASK CONTROLS - universal material"
    snow.node_tree = bpy.data.node_groups[SNOW_GROUP_NAME]
    snow.location = (-520, 560)
    copy_template_defaults(snow)
    if normal and "Normal Map Color" in snow.inputs:
        links.new(normal.outputs["Color"], snow.inputs["Normal Map Color"])
        if "Use Normal Map 0 Geo 1 NormalMap" in snow.inputs:
            snow.inputs["Use Normal Map 0 Geo 1 NormalMap"].default_value = 1.0
    mix_color = nodes.new("ShaderNodeMix")
    mix_color.name = "Mix Original Color With Snow"
    mix_color.label = "Original + Snow by Final Mask"
    mix_color.data_type = "RGBA"
    mix_color.factor_mode = "UNIFORM"
    mix_color.location = (120, 250)
    links.new(snow.outputs["Final Mask"], mix_color.inputs["Factor"])
    if diffuse:
        links.new(diffuse.outputs["Color"], mix_color.inputs[6])
    else:
        mix_color.inputs[6].default_value = (0.55, 0.55, 0.55, 1.0)
    mix_color.inputs[7].default_value = SNOW_COLOR
    mask_to_color = nodes.new("ShaderNodeValToRGB")
    mask_to_color.name = "Debug Mask To Color"
    mask_to_color.location = (360, 470)
    mask_to_color.color_ramp.elements[0].position = 0.0
    mask_to_color.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    mask_to_color.color_ramp.elements[1].position = 1.0
    mask_to_color.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    links.new(snow.outputs["Final Mask"], mask_to_color.inputs["Fac"])

    show_original = nodes.new("ShaderNodeValue")
    show_original.name = "SHOW_ORIGINAL_TEXTURE"
    show_original.label = "Show Original Texture 1 / Mask Only 0"
    show_original.outputs[0].default_value = 1.0
    show_original.location = (360, 620)

    preview_switch = nodes.new("ShaderNodeMix")
    preview_switch.name = "Preview Original Or Debug Mask"
    preview_switch.label = "Show Original Texture / Mask Only"
    preview_switch.data_type = "RGBA"
    preview_switch.factor_mode = "UNIFORM"
    preview_switch.location = (470, 250)
    links.new(show_original.outputs[0], preview_switch.inputs["Factor"])
    links.new(mask_to_color.outputs["Color"], preview_switch.inputs[6])
    links.new(mix_color.outputs[2], preview_switch.inputs[7])
    links.new(preview_switch.outputs[2], bsdf.inputs["Base Color"])
    if normal:
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.name = "Original Normal Map"
        normal_map.location = (-230, -220)
        normal_strength = nodes.new("ShaderNodeMapRange")
        normal_strength.name = "Reduce Normal Under Snow"
        normal_strength.location = (-500, -80)
        normal_strength.clamp = True
        normal_strength.inputs["From Min"].default_value = 0.0
        normal_strength.inputs["From Max"].default_value = 1.0
        normal_strength.inputs["To Min"].default_value = 1.0
        normal_strength.inputs["To Max"].default_value = SNOW_NORMAL_STRENGTH_SCALE
        links.new(snow.outputs["Final Mask"], normal_strength.inputs["Value"])
        links.new(normal_strength.outputs["Result"], normal_map.inputs["Strength"])
        links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    if packed_m:
        separate = nodes.new("ShaderNodeSeparateColor")
        separate.name = "Separate Packed Material Channels"
        separate.location = (-500, -560)
        links.new(packed_m.outputs["Color"], separate.inputs["Color"])
        metal_mix = nodes.new("ShaderNodeMix")
        metal_mix.name = "Mix Metallic With Snow"
        metal_mix.data_type = "FLOAT"
        metal_mix.factor_mode = "UNIFORM"
        metal_mix.location = (120, -440)
        links.new(snow.outputs["Final Mask"], metal_mix.inputs["Factor"])
        links.new(separate.outputs[0], metal_mix.inputs[2])
        metal_mix.inputs[3].default_value = SNOW_METALLIC
        links.new(metal_mix.outputs[0], bsdf.inputs["Metallic"])
        rough_mix = nodes.new("ShaderNodeMix")
        rough_mix.name = "Mix Roughness With Snow"
        rough_mix.data_type = "FLOAT"
        rough_mix.factor_mode = "UNIFORM"
        rough_mix.location = (120, -650)
        links.new(snow.outputs["Final Mask"], rough_mix.inputs["Factor"])
        links.new(separate.outputs[1], rough_mix.inputs[2])
        rough_mix.inputs[3].default_value = SNOW_ROUGHNESS
        links.new(rough_mix.outputs[0], bsdf.inputs["Roughness"])
    else:
        set_input(bsdf, ["Metallic"], 0.0)
        set_input(bsdf, ["Roughness"], SNOW_ROUGHNESS)
    ensure_normal_noise_blend_node_group()
    ensure_top_projection_nodes(mat)
    return mat


def snow_control_nodes(materials=None):
    materials = materials or bpy.data.materials
    for mat in materials:
        if mat and mat.node_tree:
            node = mat.node_tree.nodes.get(CONTROL_NODE_NAME)
            if node:
                yield mat, node


def sync_snow_controls_from(source_mat):
    if not source_mat or not source_mat.node_tree:
        return 0
    source_node = source_mat.node_tree.nodes.get(CONTROL_NODE_NAME)
    if not source_node:
        return 0
    source_inputs = {inp.name: inp for inp in source_node.inputs}
    count = 0
    for mat, node in snow_control_nodes():
        if mat == source_mat:
            continue
        for dst in node.inputs:
            src = source_inputs.get(dst.name)
            if src:
                copy_socket_value(src, dst)
        count += 1
    return count


DEBUG_VIEW_SOCKET = "Debug View 0 Final 1 Normal 2 Corner 3 Ground"
DEBUG_VIEW_LABELS = {
    0: "Final Mask",
    1: "Normal Mask",
    2: "Corner Mask",
    3: "Ground Mask",
    4: "Top Projection Mask",
}
DEBUG_VIEW_OUTPUTS = {
    0: "Final Mask",
    1: "Normal Up Mask",
    2: "Corner Height Mask",
    3: "Ground Bottom Mask",
    4: "Top Projection Mask",
}


def connect_debug_mask_output(mat, debug_value):
    if not mat or not mat.node_tree:
        return False
    tree = mat.node_tree
    snow = tree.nodes.get(CONTROL_NODE_NAME)
    mask_to_color = tree.nodes.get(DEBUG_MASK_COLOR_NODE)
    if not snow or not mask_to_color:
        return False
    output_name = DEBUG_VIEW_OUTPUTS.get(int(debug_value), "Final Mask")
    if "Fac" not in mask_to_color.inputs:
        return False
    if int(debug_value) == 0 and TOP_PROJECTION_FINAL_MAX_NODE in tree.nodes:
        source_socket = tree.nodes[TOP_PROJECTION_FINAL_MAX_NODE].outputs["Value"]
    elif int(debug_value) == 4 and TOP_PROJECTION_WEIGHT_MATH_NODE in tree.nodes:
        source_socket = tree.nodes[TOP_PROJECTION_WEIGHT_MATH_NODE].outputs["Value"]
    elif output_name in snow.outputs:
        source_socket = snow.outputs[output_name]
    else:
        return False
    for link in list(mask_to_color.inputs["Fac"].links):
        tree.links.remove(link)
    tree.links.new(source_socket, mask_to_color.inputs["Fac"])
    return True


def set_all_debug_view(debug_value):
    count = 0
    for mat, node in snow_control_nodes():
        if DEBUG_VIEW_SOCKET in node.inputs:
            node.inputs[DEBUG_VIEW_SOCKET].default_value = float(debug_value)
        ensure_preview_switch(mat)
        if connect_debug_mask_output(mat, debug_value):
            count += 1
    return count


SHOW_ORIGINAL_NODE = "SHOW_ORIGINAL_TEXTURE"
DEBUG_MASK_COLOR_NODE = "Debug Mask To Color"
PREVIEW_SWITCH_NODE = "Preview Original Or Debug Mask"
TOP_PROJECTION_ATTRIBUTE = "SnowTopProjectionMask"
TOP_PROJECTION_ATTR_NODE = "Top Projection Mask Attribute"
TOP_PROJECTION_ENABLE_NODE = "TOP_PROJECTION_ENABLE"
TOP_PROJECTION_WEIGHT_NODE = "TOP_PROJECTION_WEIGHT"
TOP_PROJECTION_ENABLE_MATH_NODE = "Top Projection x Enable"
TOP_PROJECTION_WEIGHT_MATH_NODE = "Top Projection x Weight"
TOP_PROJECTION_FINAL_MAX_NODE = "Final Mask With Top Projection"
NORMAL_NOISE_BLEND_SOCKET = "Normal Noise Blend 0 Clean 1 Noisy"



def get_group_input_node(node_group):
    for node in node_group.nodes:
        if node.bl_idname == "NodeGroupInput":
            return node
    return None


def add_group_float_input(node_group, name, default=0.0, min_value=0.0, max_value=1.0):
    if name not in [item.name for item in node_group.interface.items_tree]:
        socket_item = node_group.interface.new_socket(name=name, in_out="INPUT", socket_type="NodeSocketFloat")
        for attr, value in (("default_value", default), ("min_value", min_value), ("max_value", max_value)):
            try:
                setattr(socket_item, attr, value)
            except Exception:
                pass
    group_input = get_group_input_node(node_group)
    if group_input and name in group_input.outputs:
        try:
            group_input.outputs[name].default_value = default
        except Exception:
            pass
        return group_input.outputs[name]
    return None


def ensure_normal_noise_blend_node_group():
    node_group = bpy.data.node_groups.get(SNOW_GROUP_NAME)
    if not node_group:
        return False
    blend_socket = add_group_float_input(node_group, NORMAL_NOISE_BLEND_SOCKET, 1.0, 0.0, 1.0)
    group_input = get_group_input_node(node_group)
    clean_node = node_group.nodes.get("Normal Up Smooth Mask")
    noisy_node = node_group.nodes.get("Normal Mask + Noise")
    normal_enable = node_group.nodes.get("Normal Enable")
    if not group_input or not blend_socket or not clean_node or not noisy_node or not normal_enable:
        return False
    nodes = node_group.nodes
    links = node_group.links

    inv = nodes.get("Normal Noise Blend 1 - Factor") or nodes.new("ShaderNodeMath")
    inv.name = "Normal Noise Blend 1 - Factor"
    inv.operation = "SUBTRACT"
    inv.location = (-555, 505)
    inv.inputs[0].default_value = 1.0

    clean_mul = nodes.get("Normal Clean x BlendInv") or nodes.new("ShaderNodeMath")
    clean_mul.name = "Normal Clean x BlendInv"
    clean_mul.operation = "MULTIPLY"
    clean_mul.location = (-360, 420)

    noisy_mul = nodes.get("Normal Noisy x Blend") or nodes.new("ShaderNodeMath")
    noisy_mul.name = "Normal Noisy x Blend"
    noisy_mul.operation = "MULTIPLY"
    noisy_mul.location = (-360, 300)

    lerp = nodes.get("Normal Clean Noisy Lerp") or nodes.new("ShaderNodeMath")
    lerp.name = "Normal Clean Noisy Lerp"
    lerp.operation = "ADD"
    lerp.location = (-170, 420)

    def reconnect(from_socket, to_socket):
        for link in list(to_socket.links):
            links.remove(link)
        links.new(from_socket, to_socket)

    reconnect(blend_socket, inv.inputs[1])
    reconnect(clean_node.outputs["Result"], clean_mul.inputs[0])
    reconnect(inv.outputs["Value"], clean_mul.inputs[1])
    reconnect(noisy_node.outputs["Value"], noisy_mul.inputs[0])
    reconnect(blend_socket, noisy_mul.inputs[1])
    reconnect(clean_mul.outputs["Value"], lerp.inputs[0])
    reconnect(noisy_mul.outputs["Value"], lerp.inputs[1])
    reconnect(lerp.outputs["Value"], normal_enable.inputs[0])
    return True


def set_all_normal_noise_blend(value):
    ensure_normal_noise_blend_node_group()
    count = 0
    for _mat, node in snow_control_nodes():
        if NORMAL_NOISE_BLEND_SOCKET in node.inputs:
            node.inputs[NORMAL_NOISE_BLEND_SOCKET].default_value = float(value)
            count += 1
    return count


def ensure_top_projection_nodes(mat):
    if not mat or not mat.node_tree:
        return False
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    snow = nodes.get(CONTROL_NODE_NAME)
    if not snow or "Final Mask" not in snow.outputs:
        return False

    attr = nodes.get(TOP_PROJECTION_ATTR_NODE) or nodes.new("ShaderNodeAttribute")
    attr.name = TOP_PROJECTION_ATTR_NODE
    attr.label = "Top Projection Mask Attribute"
    attr.attribute_name = TOP_PROJECTION_ATTRIBUTE
    attr.location = (-120, 780)

    enable = nodes.get(TOP_PROJECTION_ENABLE_NODE) or nodes.new("ShaderNodeValue")
    enable.name = TOP_PROJECTION_ENABLE_NODE
    enable.label = "Top Projection Enable"
    enable.location = (-120, 640)

    weight = nodes.get(TOP_PROJECTION_WEIGHT_NODE) or nodes.new("ShaderNodeValue")
    weight.name = TOP_PROJECTION_WEIGHT_NODE
    weight.label = "Top Projection Weight"
    if weight.outputs[0].default_value == 0.0:
        weight.outputs[0].default_value = 1.0
    weight.location = (-120, 560)

    enabled_mul = nodes.get(TOP_PROJECTION_ENABLE_MATH_NODE) or nodes.new("ShaderNodeMath")
    enabled_mul.name = TOP_PROJECTION_ENABLE_MATH_NODE
    enabled_mul.operation = "MULTIPLY"
    enabled_mul.location = (80, 740)

    weighted_mul = nodes.get(TOP_PROJECTION_WEIGHT_MATH_NODE) or nodes.new("ShaderNodeMath")
    weighted_mul.name = TOP_PROJECTION_WEIGHT_MATH_NODE
    weighted_mul.operation = "MULTIPLY"
    weighted_mul.location = (260, 740)

    final_max = nodes.get(TOP_PROJECTION_FINAL_MAX_NODE) or nodes.new("ShaderNodeMath")
    final_max.name = TOP_PROJECTION_FINAL_MAX_NODE
    final_max.label = "Final Mask With Top Projection"
    final_max.operation = "MAXIMUM"
    final_max.location = (430, 740)

    def connect_single(from_socket, to_socket):
        if len(to_socket.links) == 1 and to_socket.links[0].from_socket == from_socket:
            return
        for link in list(to_socket.links):
            links.remove(link)
        links.new(from_socket, to_socket)

    connect_single(snow.outputs["Final Mask"], final_max.inputs[0])
    connect_single(attr.outputs["Fac"], enabled_mul.inputs[0])
    connect_single(enable.outputs[0], enabled_mul.inputs[1])
    connect_single(enabled_mul.outputs["Value"], weighted_mul.inputs[0])
    connect_single(weight.outputs[0], weighted_mul.inputs[1])
    connect_single(weighted_mul.outputs["Value"], final_max.inputs[1])

    final_socket = snow.outputs["Final Mask"]
    for link in list(final_socket.links):
        if link.to_node == final_max:
            continue
        to_socket = link.to_socket
        links.remove(link)
        links.new(final_max.outputs["Value"], to_socket)
    return True


def ensure_all_top_projection_nodes():
    return sum(1 for mat, _node in snow_control_nodes() if ensure_top_projection_nodes(mat))


def set_all_top_projection_enabled(enabled):
    count = 0
    for mat, _node in snow_control_nodes():
        if ensure_top_projection_nodes(mat):
            mat.node_tree.nodes[TOP_PROJECTION_ENABLE_NODE].outputs[0].default_value = 1.0 if enabled else 0.0
            count += 1
    return count


def set_all_top_projection_weight(weight):
    count = 0
    for mat, _node in snow_control_nodes():
        if ensure_top_projection_nodes(mat):
            mat.node_tree.nodes[TOP_PROJECTION_WEIGHT_NODE].outputs[0].default_value = float(weight)
            count += 1
    return count


def ensure_preview_switch(mat):
    if not mat or not mat.node_tree:
        return False
    tree = mat.node_tree
    nodes = tree.nodes
    links = tree.links
    snow = nodes.get(CONTROL_NODE_NAME)
    bsdf = find_principled(mat)
    if not snow or not bsdf or "Final Mask" not in snow.outputs:
        return False
    ensure_top_projection_nodes(mat)

    show_original = nodes.get(SHOW_ORIGINAL_NODE)
    if not show_original:
        show_original = nodes.new("ShaderNodeValue")
        show_original.name = SHOW_ORIGINAL_NODE
        show_original.label = "Show Original Texture 1 / Mask Only 0"
        show_original.outputs[0].default_value = 1.0
        show_original.location = (360, 620)

    mask_to_color = nodes.get(DEBUG_MASK_COLOR_NODE)
    if not mask_to_color:
        mask_to_color = nodes.new("ShaderNodeValToRGB")
        mask_to_color.name = DEBUG_MASK_COLOR_NODE
        mask_to_color.location = (360, 470)
        mask_to_color.color_ramp.elements[0].position = 0.0
        mask_to_color.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
        mask_to_color.color_ramp.elements[1].position = 1.0
        mask_to_color.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    if not any(link.from_node == snow and link.to_node == mask_to_color for link in mask_to_color.inputs["Fac"].links):
        for link in list(mask_to_color.inputs["Fac"].links):
            links.remove(link)
        links.new(snow.outputs["Final Mask"], mask_to_color.inputs["Fac"])

    preview_switch = nodes.get(PREVIEW_SWITCH_NODE)
    if not preview_switch:
        preview_switch = nodes.new("ShaderNodeMix")
        preview_switch.name = PREVIEW_SWITCH_NODE
        preview_switch.label = "Show Original Texture / Mask Only"
        preview_switch.data_type = "RGBA"
        preview_switch.factor_mode = "UNIFORM"
        preview_switch.location = (470, 250)

    current_base = bsdf.inputs["Base Color"].links[0].from_socket if bsdf.inputs["Base Color"].links else None
    if current_base and current_base.node != preview_switch:
        for link in list(preview_switch.inputs[7].links):
            links.remove(link)
        links.new(current_base, preview_switch.inputs[7])
    for link in list(preview_switch.inputs["Factor"].links):
        links.remove(link)
    links.new(show_original.outputs[0], preview_switch.inputs["Factor"])
    for link in list(preview_switch.inputs[6].links):
        links.remove(link)
    links.new(mask_to_color.outputs["Color"], preview_switch.inputs[6])
    if not bsdf.inputs["Base Color"].links or bsdf.inputs["Base Color"].links[0].from_node != preview_switch:
        for link in list(bsdf.inputs["Base Color"].links):
            links.remove(link)
        links.new(preview_switch.outputs[2], bsdf.inputs["Base Color"])
    return True


def ensure_all_preview_switches():
    return sum(1 for mat, _node in snow_control_nodes() if ensure_preview_switch(mat))


def set_all_show_original(show_original):
    count = 0
    for mat, _node in snow_control_nodes():
        if ensure_preview_switch(mat):
            mat.node_tree.nodes[SHOW_ORIGINAL_NODE].outputs[0].default_value = 1.0 if show_original else 0.0
            count += 1
    return count


def apply_snow_to_all_mesh_materials():
    """Create one snow material per original material, preserving each submesh texture set."""
    originals = []
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            for slot in obj.material_slots:
                if slot.material and (not slot.material.node_tree or CONTROL_NODE_NAME not in slot.material.node_tree.nodes):
                    if slot.material not in originals:
                        originals.append(slot.material)
    if not originals:
        return 0
    mapping = {mat: create_snow_mix_material(mat) for mat in originals}
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            for slot in obj.material_slots:
                if slot.material in mapping:
                    slot.material = mapping[slot.material]
    return len(mapping)


def snow_material_items(self, context):
    items = []
    for index, (mat, _node) in enumerate(snow_control_nodes()):
        items.append((mat.name, mat.name, "", index))
    if not items:
        items.append(("", "No snow materials found", "", 0))
    return items


def parse_number_block(text, key, caster=float):
    match = re.search(r"\b" + re.escape(key) + r"\s*:\s*([^\n}]*(?:\n\s*,[^\n}]*)*)", text)
    if not match:
        return []
    return [caster(item) for item in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", match.group(1))]


def extract_named_blocks(text, block_name):
    pattern = re.compile(r"\b" + re.escape(block_name) + r"\s*:\s*\"([^\"]+)\"[^\{]*\{")
    pos = 0
    while True:
        match = pattern.search(text, pos)
        if not match:
            break
        start = match.end()
        depth = 1
        idx = start
        while idx < len(text) and depth:
            if text[idx] == "{":
                depth += 1
            elif text[idx] == "}":
                depth -= 1
            idx += 1
        yield match.group(1), text[start:idx - 1]
        pos = idx


def ascii_connections(text, relation):
    expr = re.compile(r'Connect:\s*"OO",\s*"([^"]+)",\s*"([^"]+)"')
    return [(a, b) for a, b in expr.findall(text) if relation(a, b)]


def read_ascii_fbx_model_materials(text):
    model_mats = {}
    for material, model in ascii_connections(text, lambda a, b: a.startswith("Material::") and b.startswith("Model::")):
        model_mats.setdefault(clean_name(model), []).append(clean_name(material))
    return model_mats


def read_ascii_fbx_textures(text, fbx_path):
    texture_files = {}
    texture_uvsets = {}
    for name, block in extract_named_blocks(text, "Texture"):
        clean = clean_name(name)
        file_match = re.search(r'(?:FileName|RelativeFilename):\s*"([^"]+)"', block)
        if file_match:
            texture_files[clean] = (fbx_path.parent / file_match.group(1)).resolve()
        uvset_match = re.search(r'Property:\s*"UVSet"[^\n]*,\s*"([^"]*)"', block)
        if uvset_match:
            texture_uvsets[clean] = uvset_match.group(1).strip()
    texture_models = {}
    for tex, model in ascii_connections(text, lambda a, b: a.startswith("Texture::") and b.startswith("Model::")):
        texture_models.setdefault(clean_name(model), []).append(clean_name(tex))
    return texture_files, texture_models, texture_uvsets


def add_existing_sibling_maps(texture_paths):
    paths = list(dict.fromkeys(Path(p) for p in texture_paths))
    stems = {p.stem.lower(): p for p in paths}
    additions = []
    for path in paths:
        stem = path.stem
        if stem.lower().endswith(("_d", "_n")):
            base = stem[:-2]
            for suffix in ("_d", "_n", "_m"):
                candidate = path.with_name(base + suffix + path.suffix)
                if candidate.exists() and candidate.stem.lower() not in stems:
                    additions.append(candidate)
                    stems[candidate.stem.lower()] = candidate
    paths.extend(additions)
    return paths


def make_base_material(mat_name, texture_paths):
    texture_paths = add_existing_sibling_maps(texture_paths)
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = find_principled(mat)
    diffuse_path = next((p for p in texture_paths if Path(p).stem.lower().endswith("_d")), None)
    normal_path = next((p for p in texture_paths if Path(p).stem.lower().endswith("_n")), None)
    packed_path = next((p for p in texture_paths if Path(p).stem.lower().endswith("_m")), None)
    if diffuse_path:
        tex = new_tex_node(tree, "Original Diffuse", load_image(diffuse_path, "sRGB"), (-550, 180))
        tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if normal_path:
        tex = new_tex_node(tree, "Original Normal", load_image(normal_path, "Non-Color"), (-550, -160))
        norm = tree.nodes.new("ShaderNodeNormalMap")
        norm.location = (-250, -160)
        tree.links.new(tex.outputs["Color"], norm.inputs["Color"])
        tree.links.new(norm.outputs["Normal"], bsdf.inputs["Normal"])
    if packed_path:
        new_tex_node(tree, "Original Packed M/Mask", load_image(packed_path, "Non-Color"), (-550, -420))
    return mat


def texture_paths_for_material(mat_name, model_texture_names, texture_files):
    mat_lower = mat_name.lower()
    he_match = re.search(r"he\d+", mat_lower)
    if he_match:
        token = he_match.group(0)
        paths = [texture_files[t] for t in model_texture_names if t in texture_files and token in t.lower()]
        if paths:
            return paths
    return [texture_files[t] for t in model_texture_names if t in texture_files]


def import_ascii_fbx_lightweight(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    model_mats = read_ascii_fbx_model_materials(text)
    texture_files, texture_models, texture_uvsets = read_ascii_fbx_textures(text, path)
    imported = []
    for model_name, block in extract_named_blocks(text, "Model"):
        clean_model = clean_name(model_name)
        verts = parse_number_block(block, "Vertices", float)
        indices = parse_number_block(block, "PolygonVertexIndex", int)
        if not verts or not indices:
            continue
        vertices = [(verts[i], verts[i + 1], verts[i + 2]) for i in range(0, len(verts), 3)]
        faces = []
        current = []
        for raw in indices:
            if raw < 0:
                current.append(-raw - 1)
                faces.append(tuple(current))
                current = []
            else:
                current.append(raw)
        mesh = bpy.data.meshes.new(clean_model + "_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(clean_model, mesh)
        bpy.context.collection.objects.link(obj)
        imported_uv_names = []
        for uv_block_match in re.finditer(r'LayerElementUV:\s*\d+\s*\{(.*?)\n\s*\}', block, re.S):
            uv_block = uv_block_match.group(1)
            uv_name_match = re.search(r'Name:\s*"([^"]+)"', uv_block)
            uv_name = uv_name_match.group(1) if uv_name_match else f"UVMap_{len(imported_uv_names)}"
            uv_values = parse_number_block(uv_block, "UV", float)
            uv_indices = parse_number_block(uv_block, "UVIndex", int)
            if uv_values and uv_indices:
                uv_layer = mesh.uv_layers.new(name=uv_name)
                imported_uv_names.append(uv_name)
                uv_direct = [(uv_values[i], uv_values[i + 1]) for i in range(0, len(uv_values), 2)]
                cursor = 0
                for poly in mesh.polygons:
                    for loop_idx in poly.loop_indices:
                        if cursor < len(uv_indices) and uv_indices[cursor] < len(uv_direct):
                            uv_layer.data[loop_idx].uv = uv_direct[uv_indices[cursor]]
                        cursor += 1
        preferred_uv = ""
        for texture_name in texture_models.get(clean_model, []):
            uvset = texture_uvsets.get(texture_name, "")
            if uvset:
                preferred_uv = uvset
                break
        if preferred_uv and preferred_uv in mesh.uv_layers:
            mesh.uv_layers.active = mesh.uv_layers[preferred_uv]
        mat_names = model_mats.get(clean_model, []) or [clean_model + "_mat"]
        model_texture_names = texture_models.get(clean_model, [])
        for mat_name in mat_names:
            paths = texture_paths_for_material(mat_name, model_texture_names, texture_files)
            mesh.materials.append(make_base_material(clean_name(mat_name), paths))
        material_indices = parse_number_block(block, "Materials", int)
        if material_indices:
            for poly, mat_index in zip(mesh.polygons, material_indices):
                poly.material_index = min(max(mat_index, 0), max(len(mesh.materials) - 1, 0))
        imported.append(obj)
    if not imported:
        raise RuntimeError("ASCII FBX fallback could not find mesh geometry.")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    return imported




def neox_pos_to_blender(position):
    x, y, z = position
    return (x, -z, y)


def neox_vec_to_blender(vector):
    x, y, z = vector
    return (x, -z, y)


def parse_neox_xml_readonly(path):
    raw = Path(path).read_bytes()
    for encoding in ("utf-8", "gbk", "utf-8-sig"):
        try:
            return ElementTree.fromstring(raw.decode(encoding))
        except Exception:
            continue
    return ElementTree.fromstring(raw.decode("utf-8", errors="ignore"))


def find_neox_res_root(path):
    current = Path(path).resolve().parent
    for parent in (current, *current.parents):
        if parent.name.lower() == "res":
            return parent
    return current


def resolve_neox_resource_path(resource_root, gim_dir, value):
    if not value:
        return None
    value = value.replace("/", "\\")
    candidates = []
    value_path = Path(value)
    if value_path.is_absolute():
        candidates.append(value_path)
    candidates.append(resource_root / value)
    candidates.append(gim_dir / value)
    candidates.append(gim_dir / Path(value).name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def read_gim_submeshes(gim_path):
    root = parse_neox_xml_readonly(gim_path)
    submesh_node = root.find("SubMesh")
    submeshes = []
    if submesh_node is not None:
        for child in list(submesh_node):
            submeshes.append({
                "name": child.attrib.get("Name", child.tag),
                "material_index": int(child.attrib.get("MtlIdx", len(submeshes))),
            })
    return submeshes


def read_mtg_materials(mtg_path, resource_root, gim_dir):
    root = parse_neox_xml_readonly(mtg_path)
    material_group = root.find("MaterialGroup")
    materials = []
    if material_group is None:
        return materials
    for material_slot in list(material_group):
        material_node = material_slot.find("Material")
        if material_node is None:
            continue
        param_table = material_node.find("ParamTable")
        params = {}
        if param_table is not None:
            for param in list(param_table):
                params[param.tag] = param.attrib.get("Value", "")
        materials.append({
            "name": material_node.attrib.get("Name", material_slot.tag),
            "diffuse": resolve_neox_resource_path(resource_root, gim_dir, params.get("Tex0")),
            "normal": resolve_neox_resource_path(resource_root, gim_dir, params.get("NormalMap")),
            "param": resolve_neox_resource_path(resource_root, gim_dir, params.get("ParamMap")),
            "params": params,
        })
    return materials


def read_neox_mesh(mesh_path, submesh_count):
    data = Path(mesh_path).read_bytes()
    offset = 0

    def unpack(fmt):
        nonlocal offset
        size = struct.calcsize(fmt)
        values = struct.unpack_from(fmt, data, offset)
        offset += size
        return values

    _mark, version, mesh_type = unpack("<IIh")
    if version < 0x50002:
        raise RuntimeError(f"Unsupported NeoX mesh version: {hex(version)}")
    has_morph, = unpack("<?")
    if has_morph:
        raise RuntimeError("NeoX morph mesh is not supported by this preview importer.")
    has_track, = unpack("<?")
    if has_track:
        raise RuntimeError("NeoX track mesh is not supported by this preview importer.")
    if mesh_type == 1:
        bone_count, = unpack("<h")
        offset += bone_count + bone_count * 32
        has_bone_bounding, = unpack("<?")
        if has_bone_bounding:
            offset += bone_count * 7 * 4
        offset += bone_count * 16 * 4
        has_key_bounding, = unpack("<?")
        if has_key_bounding:
            raise RuntimeError("NeoX per-key bounding mesh is not supported by this preview importer.")

    geometry_offset, = unpack("<I")
    offset = geometry_offset
    block_count, = unpack("<h")
    block_offsets = list(unpack("<" + "I" * block_count))
    pair_count, = unpack("<h")
    offset += pair_count * 6
    offset = block_offsets[0]

    sub_infos = []
    global_has_color = False
    for _index in range(submesh_count):
        vertex_count, triangle_count, uv_count, has_color = unpack("<IIb?")
        sub_infos.append({"vertex_count": vertex_count, "triangle_count": triangle_count, "uv_count": uv_count, "has_color": has_color})
        global_has_color = global_has_color or has_color
    for sub_info in sub_infos:
        sub_info["has_color"] = global_has_color

    _lod_index, total_vertex_count, total_triangle_count = unpack("<hII")
    positions = [unpack("<fff") for _ in range(total_vertex_count)]
    normals = [unpack("<fff") for _ in range(total_vertex_count)]
    has_tangent, = unpack("<h")
    tangents = [unpack("<fff") for _ in range(total_vertex_count)] if has_tangent else []
    triangles = [unpack("<HHH") for _ in range(total_triangle_count)]
    uvs = [[] for _ in range(total_vertex_count)]
    vertex_offset = 0
    for sub_info in sub_infos:
        for _uv_index in range(sub_info["uv_count"]):
            for sub_vertex_index in range(sub_info["vertex_count"]):
                u, v = unpack("<ff")
                uvs[vertex_offset + sub_vertex_index].append((u, v))
        vertex_offset += sub_info["vertex_count"]
    colors = [None] * total_vertex_count
    vertex_offset = 0
    for sub_info in sub_infos:
        if sub_info["has_color"]:
            for sub_vertex_index in range(sub_info["vertex_count"]):
                b, g, r, a = unpack("<BBBB")
                colors[vertex_offset + sub_vertex_index] = (r / 255.0, g / 255.0, b / 255.0, a / 255.0)
        vertex_offset += sub_info["vertex_count"]
    return {"sub_infos": sub_infos, "positions": positions, "normals": normals, "tangents": tangents, "triangles": triangles, "uvs": uvs, "colors": colors}


def make_neox_base_material(material_info):
    mat = bpy.data.materials.new(material_info.get("name") or "NeoXMaterial")
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = find_principled(mat)
    diffuse_path = material_info.get("diffuse")
    normal_path = material_info.get("normal")
    param_path = material_info.get("param")
    if diffuse_path:
        tex = new_tex_node(tree, "NeoX Tex0 Diffuse", load_image(diffuse_path, "sRGB"), (-650, 220))
        if tex:
            tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if normal_path:
        tex = new_tex_node(tree, "NeoX NormalMap", load_image(normal_path, "Non-Color"), (-650, -120))
        if tex:
            norm = tree.nodes.new("ShaderNodeNormalMap")
            norm.location = (-350, -120)
            tree.links.new(tex.outputs["Color"], norm.inputs["Color"])
            tree.links.new(norm.outputs["Normal"], bsdf.inputs["Normal"])
    if param_path:
        tex = new_tex_node(tree, "NeoX ParamMap R=Rough G=Metal A=AO", load_image(param_path, "Non-Color"), (-650, -420))
        if tex:
            separate = tree.nodes.new("ShaderNodeSeparateColor")
            separate.name = "Separate NeoX ParamMap"
            separate.location = (-360, -420)
            tree.links.new(tex.outputs["Color"], separate.inputs["Color"])
            tree.links.new(separate.outputs[0], bsdf.inputs["Roughness"])
            tree.links.new(separate.outputs[1], bsdf.inputs["Metallic"])
    return mat


def import_gim(path):
    gim_path = Path(path)
    gim_dir = gim_path.parent
    resource_root = find_neox_res_root(gim_path)
    submeshes = read_gim_submeshes(gim_path)
    if not submeshes:
        raise RuntimeError("GIM has no SubMesh entries.")
    mesh_path = gim_path.with_suffix(".mesh")
    mtg_path = gim_path.with_suffix(".mtg")
    mesh_data = read_neox_mesh(mesh_path, len(submeshes))
    material_infos = read_mtg_materials(mtg_path, resource_root, gim_dir)
    base_materials = [make_neox_base_material(info) for info in material_infos]
    imported = []
    vertex_offset = 0
    triangle_offset = 0
    for submesh_index, submesh in enumerate(submeshes):
        sub_info = mesh_data["sub_infos"][submesh_index]
        vertex_count = sub_info["vertex_count"]
        triangle_count = sub_info["triangle_count"]
        vertices = [neox_pos_to_blender(pos) for pos in mesh_data["positions"][vertex_offset:vertex_offset + vertex_count]]
        faces = []
        for tri in mesh_data["triangles"][triangle_offset:triangle_offset + triangle_count]:
            faces.append(tuple(index - vertex_offset for index in tri))
        mesh = bpy.data.meshes.new(submesh["name"] + "_Mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        try:
            mesh.normals_split_custom_set_from_vertices([neox_vec_to_blender(n) for n in mesh_data["normals"][vertex_offset:vertex_offset + vertex_count]])
            mesh.use_auto_smooth = True if hasattr(mesh, "use_auto_smooth") else False
        except Exception:
            pass
        obj = bpy.data.objects.new(submesh["name"], mesh)
        bpy.context.collection.objects.link(obj)
        mat_index = submesh["material_index"]
        if 0 <= mat_index < len(base_materials):
            mesh.materials.append(base_materials[mat_index])
        for uv_index in range(sub_info["uv_count"]):
            uv_layer = mesh.uv_layers.new(name=f"UVChannel_{uv_index}")
            for poly in mesh.polygons:
                for loop_index in poly.loop_indices:
                    vertex_index = mesh.loops[loop_index].vertex_index + vertex_offset
                    if uv_index < len(mesh_data["uvs"][vertex_index]):
                        u, v = mesh_data["uvs"][vertex_index][uv_index]
                        uv_layer.data[loop_index].uv = (u, 1.0 - v)
        if mesh.uv_layers:
            mesh.uv_layers.active = mesh.uv_layers[0]
        if any(color is not None for color in mesh_data["colors"][vertex_offset:vertex_offset + vertex_count]):
            color_attr = mesh.color_attributes.new(name="NeoXVertexColor", type="BYTE_COLOR", domain="CORNER")
            for poly in mesh.polygons:
                for loop_index in poly.loop_indices:
                    vertex_index = mesh.loops[loop_index].vertex_index + vertex_offset
                    color_attr.data[loop_index].color = mesh_data["colors"][vertex_index] or (1, 1, 1, 1)
        imported.append(obj)
        vertex_offset += vertex_count
        triangle_offset += triangle_count
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = imported[0]
    return imported


def polygon_sample_points(obj, poly, inset=0.08):
    center = obj.matrix_world @ poly.center
    points = [center]
    world_vertices = [obj.matrix_world @ obj.data.vertices[index].co for index in poly.vertices]
    for point in world_vertices:
        points.append(center.lerp(point, max(0.0, min(1.0, 1.0 - inset))))
    for index, point in enumerate(world_vertices):
        next_point = world_vertices[(index + 1) % len(world_vertices)]
        midpoint = (point + next_point) * 0.5
        points.append(center.lerp(midpoint, max(0.0, min(1.0, 1.0 - inset))))
    return points


def ray_hits_face_from_top(depsgraph, obj, poly, point, origin_z, min_z, self_tolerance):
    origin = mathutils.Vector((point.x, point.y, origin_z))
    hit, location, _normal, face_index, hit_obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph, origin, mathutils.Vector((0.0, 0.0, -1.0)), distance=(origin_z - min_z + 20.0)
    )
    if not hit:
        return False
    if hit_obj == obj and face_index == poly.index:
        return True
    if hit_obj == obj:
        hit_poly = obj.data.polygons[face_index] if 0 <= face_index < len(obj.data.polygons) else None
        if hit_poly:
            target_z = (obj.matrix_world @ poly.center).z
            hit_z = location.z
            same_height = abs(hit_z - target_z) <= self_tolerance
            same_normal = (obj.matrix_world.to_3x3() @ hit_poly.normal).normalized().z >= 0.0
            if same_height and same_normal:
                return True
    return False


def dilate_face_attribute(mesh, attr, steps):
    if steps <= 0:
        return
    edge_to_faces = {}
    for poly in mesh.polygons:
        for edge_key in poly.edge_keys:
            edge_to_faces.setdefault(tuple(sorted(edge_key)), []).append(poly.index)
    neighbors = {poly.index: set() for poly in mesh.polygons}
    for face_indices in edge_to_faces.values():
        if len(face_indices) < 2:
            continue
        for face_index in face_indices:
            neighbors[face_index].update(other for other in face_indices if other != face_index)
    marked = {index for index, item in enumerate(attr.data) if item.value > 0.5}
    for _step in range(steps):
        expanded = set(marked)
        for face_index in marked:
            expanded.update(neighbors.get(face_index, ()))
        marked = expanded
    for index in marked:
        attr.data[index].value = 1.0


def bake_top_projection_mask(target_objects=None, normal_z_min=0.0, sample_inset=0.08, self_tolerance=0.35, dilate_steps=1):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    meshes = [obj for obj in (target_objects or bpy.context.scene.objects) if obj.type == "MESH"]
    if not meshes:
        return 0, 0
    min_z = min((obj.matrix_world @ mathutils.Vector(corner)).z for obj in meshes for corner in obj.bound_box)
    max_z = max((obj.matrix_world @ mathutils.Vector(corner)).z for obj in meshes for corner in obj.bound_box)
    height = max(max_z - min_z, 1.0)
    origin_z = max_z + height + 10.0
    marked = 0
    total = 0
    for obj in meshes:
        mesh = obj.data
        attr = mesh.attributes.get(TOP_PROJECTION_ATTRIBUTE)
        if attr is None:
            attr = mesh.attributes.new(TOP_PROJECTION_ATTRIBUTE, "FLOAT", "FACE")
        for item in attr.data:
            item.value = 0.0
        for poly in mesh.polygons:
            total += 1
            world_normal = (obj.matrix_world.to_3x3() @ poly.normal).normalized()
            if world_normal.z < normal_z_min:
                continue
            for point in polygon_sample_points(obj, poly, sample_inset):
                if ray_hits_face_from_top(depsgraph, obj, poly, point, origin_z, min_z, self_tolerance):
                    attr.data[poly.index].value = 1.0
                    marked += 1
                    break
        dilate_face_attribute(mesh, attr, dilate_steps)
        mesh.update()
    marked_after = 0
    for obj in meshes:
        attr = obj.data.attributes.get(TOP_PROJECTION_ATTRIBUTE)
        if attr:
            marked_after += sum(1 for item in attr.data if item.value > 0.5)
    return marked_after, total


def import_model(path):
    path = Path(path)
    if path.suffix.lower() == ".gim":
        return import_gim(path)
    if is_ascii_fbx(path):
        return import_ascii_fbx_lightweight(path)
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path))
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def import_fbx(path):
    return import_model(path)


def setup_preview_scene():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 96
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.world.color = (0.03, 0.035, 0.04)
    for obj in list(bpy.data.objects):
        if obj.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    sun = bpy.data.objects.new("Snow Preview Sun", bpy.data.lights.new("Snow Preview Sun", "SUN"))
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (0.7, 0.0, -0.7)
    sun.data.energy = 2.2
    area = bpy.data.objects.new("Snow Preview Softbox", bpy.data.lights.new("Snow Preview Softbox", "AREA"))
    bpy.context.collection.objects.link(area)
    area.location = (0, -4, 5)
    area.data.energy = 550
    area.data.size = 5
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        return
    min_v = mathutils.Vector((math.inf, math.inf, math.inf))
    max_v = mathutils.Vector((-math.inf, -math.inf, -math.inf))
    for obj in meshes:
        for corner in obj.bound_box:
            world = obj.matrix_world @ mathutils.Vector(corner)
            min_v.x, min_v.y, min_v.z = min(min_v.x, world.x), min(min_v.y, world.y), min(min_v.z, world.z)
            max_v.x, max_v.y, max_v.z = max(max_v.x, world.x), max(max_v.y, world.y), max(max_v.z, world.z)
    center = (min_v + max_v) * 0.5
    size = max((max_v - min_v).x, (max_v - min_v).y, (max_v - min_v).z, 1.0)
    cam_data = bpy.data.cameras.new("Snow Preview Camera")
    cam = bpy.data.objects.new("Snow Preview Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (center.x + size * 0.85, center.y - size * 1.55, center.z + size * 0.72)
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 35
    scene.camera = cam
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1100


class SNOWMASK_OT_import_apply(bpy.types.Operator):
    bl_idname = "snowmask.import_apply"
    bl_label = "Import FBX/GIM And Apply Snow"
    bl_options = {"REGISTER", "UNDO"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def execute(self, context):
        import_model(self.filepath)
        count = apply_snow_to_all_mesh_materials()
        setup_preview_scene()
        self.report({"INFO"}, f"Imported FBX and created {count} independent snow material(s).")
        return {"FINISHED"}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class SNOWMASK_OT_apply_all(bpy.types.Operator):
    bl_idname = "snowmask.apply_all"
    bl_label = "Create Independent Snow Materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = apply_snow_to_all_mesh_materials()
        self.report({"INFO"}, f"Created {count} independent snow material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_sync_from_active(bpy.types.Operator):
    bl_idname = "snowmask.sync_from_active"
    bl_label = "Sync From Active Material"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat = context.object.active_material if context.object else None
        count = sync_snow_controls_from(mat)
        if count == 0:
            self.report({"WARNING"}, "Active material has no SNOW_MASK_CONTROLS node.")
        else:
            self.report({"INFO"}, f"Copied only snow parameters to {count} material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_sync_from_selected(bpy.types.Operator):
    bl_idname = "snowmask.sync_from_selected"
    bl_label = "Sync From Template Material"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat_name = context.scene.snowmask_template_material
        mat = bpy.data.materials.get(mat_name)
        count = sync_snow_controls_from(mat)
        if count == 0:
            self.report({"WARNING"}, "Selected template material has no SNOW_MASK_CONTROLS node.")
        else:
            self.report({"INFO"}, f"Copied only snow parameters from {mat_name} to {count} material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_set_debug_view(bpy.types.Operator):
    bl_idname = "snowmask.set_debug_view"
    bl_label = "Set Snow Debug View"
    bl_options = {"REGISTER", "UNDO"}

    debug_value: bpy.props.IntProperty(name="Debug View", default=0, min=0, max=4)

    def execute(self, context):
        ensure_all_preview_switches()
        count = set_all_debug_view(self.debug_value)
        label = DEBUG_VIEW_LABELS.get(self.debug_value, str(self.debug_value))
        if count == 0:
            self.report({"WARNING"}, "No SNOW_MASK_CONTROLS debug inputs found.")
        else:
            self.report({"INFO"}, f"Set {label} debug view on {count} material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_set_show_original(bpy.types.Operator):
    bl_idname = "snowmask.set_show_original"
    bl_label = "Set Show Original Texture"
    bl_options = {"REGISTER", "UNDO"}

    show_original: bpy.props.BoolProperty(name="Show Original Texture", default=True)

    def execute(self, context):
        count = set_all_show_original(self.show_original)
        label = "Original + Snow" if self.show_original else "Mask Only"
        if count == 0:
            self.report({"WARNING"}, "No snow materials found for preview switch.")
        else:
            self.report({"INFO"}, f"Set {label} preview on {count} material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_set_normal_noise_blend(bpy.types.Operator):
    bl_idname = "snowmask.set_normal_noise_blend"
    bl_label = "Set Normal Noise Blend"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = set_all_normal_noise_blend(context.scene.snowmask_normal_noise_blend)
        if count == 0:
            self.report({"WARNING"}, "No Normal Noise Blend inputs found; materials may need upgrade.")
        else:
            self.report({"INFO"}, f"Set Normal Noise Blend on {count} material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_bake_top_projection(bpy.types.Operator):
    bl_idname = "snowmask.bake_top_projection"
    bl_label = "Bake Top Projection Mask"
    bl_options = {"REGISTER", "UNDO"}

    selected_only: bpy.props.BoolProperty(name="Selected Only", default=False)
    normal_z_min: bpy.props.FloatProperty(name="Normal Z Min", default=-0.05, min=-1.0, max=1.0)
    sample_inset: bpy.props.FloatProperty(name="Sample Inset", default=0.08, min=0.0, max=0.45)
    self_tolerance: bpy.props.FloatProperty(name="Self Tolerance", default=0.35, min=0.0, max=10.0)
    dilate_steps: bpy.props.IntProperty(name="Dilate Steps", default=1, min=0, max=8)

    def execute(self, context):
        objects = context.selected_objects if self.selected_only else None
        marked, total = bake_top_projection_mask(objects, self.normal_z_min, self.sample_inset, self.self_tolerance, self.dilate_steps)
        ensure_all_top_projection_nodes()
        set_all_top_projection_enabled(True)
        set_all_top_projection_weight(context.scene.snowmask_top_projection_weight)
        self.report({"INFO"}, f"Baked top projection mask: {marked}/{total} faces marked.")
        return {"FINISHED"}


class SNOWMASK_OT_set_top_projection_enabled(bpy.types.Operator):
    bl_idname = "snowmask.set_top_projection_enabled"
    bl_label = "Set Top Projection Enabled"
    bl_options = {"REGISTER", "UNDO"}

    enabled: bpy.props.BoolProperty(name="Enabled", default=True)

    def execute(self, context):
        count = set_all_top_projection_enabled(self.enabled)
        self.report({"INFO"}, f"Top Projection {'enabled' if self.enabled else 'disabled'} on {count} material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_set_top_projection_weight(bpy.types.Operator):
    bl_idname = "snowmask.set_top_projection_weight"
    bl_label = "Set Top Projection Weight"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        count = set_all_top_projection_weight(context.scene.snowmask_top_projection_weight)
        self.report({"INFO"}, f"Set Top Projection Weight on {count} material(s).")
        return {"FINISHED"}


class SNOWMASK_OT_setup_preview(bpy.types.Operator):
    bl_idname = "snowmask.setup_preview"
    bl_label = "Setup Snow Preview Lighting"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        setup_preview_scene()
        return {"FINISHED"}


LANGUAGE_ITEMS = (
    ("ZH", "中文", "中文界面"),
    ("EN", "English", "English UI"),
)

UI_TEXT = {
    "ZH": {
        "import_apply": "导入 FBX/GIM 并应用覆雪",
        "create_independent": "为当前材质创建独立覆雪材质",
        "template": "模板材质",
        "sync_template": "从模板同步覆雪参数",
        "sync_active": "从当前材质同步覆雪参数",
        "normal_mask": "法线顶面积雪",
        "noise_blend": "Noise 混合",
        "apply_normal_blend": "应用 Normal Noise 混合",
        "top_projection": "顶部投影覆雪",
        "bake": "烘焙",
        "on": "开启",
        "off": "关闭",
        "weight": "强度",
        "apply_top_weight": "应用投影强度",
        "debug": "全局 Debug 视图",
        "final": "最终",
        "normal": "法线",
        "corner": "角落",
        "ground": "底部",
        "top": "投影",
        "preview": "预览模式",
        "original_snow": "原贴图+覆雪",
        "mask_only": "只看 Mask",
        "setup_preview": "设置预览灯光/相机",
        "hint_textures": "每个 submesh 保留自己的贴图。",
        "hint_params": "同步只会复制覆雪参数。",
        "language": "语言",
    },
    "EN": {
        "import_apply": "Import FBX/GIM And Apply Snow",
        "create_independent": "Create Independent Snow Materials",
        "template": "Template",
        "sync_template": "Sync From Template Material",
        "sync_active": "Sync From Active Material",
        "normal_mask": "Normal Mask",
        "noise_blend": "Noise Blend",
        "apply_normal_blend": "Apply Normal Noise Blend",
        "top_projection": "Top Projection",
        "bake": "Bake",
        "on": "On",
        "off": "Off",
        "weight": "Weight",
        "apply_top_weight": "Apply Top Projection Weight",
        "debug": "Global Debug View",
        "final": "Final",
        "normal": "Normal",
        "corner": "Corner",
        "ground": "Ground",
        "top": "Top",
        "preview": "Preview Mode",
        "original_snow": "Original+Snow",
        "mask_only": "Mask Only",
        "setup_preview": "Setup Snow Preview Lighting",
        "hint_textures": "Each submesh keeps its own textures.",
        "hint_params": "Only SNOW_MASK_CONTROLS values are synced.",
        "language": "Language",
    },
}


def ui_text(context, key):
    lang = getattr(context.scene, "snowmask_ui_language", "ZH")
    return UI_TEXT.get(lang, UI_TEXT["ZH"]).get(key, key)


class SNOWMASK_PT_panel(bpy.types.Panel):
    bl_label = "Universal Snow Mask Tool"
    bl_idname = "SNOWMASK_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Snow Mask"

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "snowmask_ui_language", text=ui_text(context, "language"))
        layout.operator("snowmask.import_apply", text=ui_text(context, "import_apply"), icon="IMPORT")
        layout.operator("snowmask.apply_all", text=ui_text(context, "create_independent"), icon="MATERIAL")
        layout.separator()
        layout.prop(context.scene, "snowmask_template_material", text=ui_text(context, "template"))
        layout.operator("snowmask.sync_from_selected", text=ui_text(context, "sync_template"), icon="COPYDOWN")
        layout.operator("snowmask.sync_from_active", text=ui_text(context, "sync_active"), icon="PASTEDOWN")
        layout.separator()
        layout.label(text=ui_text(context, "normal_mask"))
        layout.prop(context.scene, "snowmask_normal_noise_blend", text=ui_text(context, "noise_blend"))
        layout.operator("snowmask.set_normal_noise_blend", text=ui_text(context, "apply_normal_blend"))
        layout.separator()
        layout.label(text=ui_text(context, "top_projection"))
        row = layout.row(align=True)
        row.operator("snowmask.bake_top_projection", text=ui_text(context, "bake"))
        op = row.operator("snowmask.set_top_projection_enabled", text=ui_text(context, "on"))
        op.enabled = True
        op = row.operator("snowmask.set_top_projection_enabled", text=ui_text(context, "off"))
        op.enabled = False
        layout.prop(context.scene, "snowmask_top_projection_weight", text=ui_text(context, "weight"))
        layout.operator("snowmask.set_top_projection_weight", text=ui_text(context, "apply_top_weight"))
        layout.separator()
        layout.label(text=ui_text(context, "debug"))
        row = layout.row(align=True)
        op = row.operator("snowmask.set_debug_view", text=ui_text(context, "final"))
        op.debug_value = 0
        op = row.operator("snowmask.set_debug_view", text=ui_text(context, "normal"))
        op.debug_value = 1
        row = layout.row(align=True)
        op = row.operator("snowmask.set_debug_view", text=ui_text(context, "corner"))
        op.debug_value = 2
        op = row.operator("snowmask.set_debug_view", text=ui_text(context, "ground"))
        op.debug_value = 3
        op = row.operator("snowmask.set_debug_view", text=ui_text(context, "top"))
        op.debug_value = 4
        layout.label(text=ui_text(context, "preview"))
        row = layout.row(align=True)
        op = row.operator("snowmask.set_show_original", text=ui_text(context, "original_snow"))
        op.show_original = True
        op = row.operator("snowmask.set_show_original", text=ui_text(context, "mask_only"))
        op.show_original = False
        layout.separator()
        layout.operator("snowmask.setup_preview", text=ui_text(context, "setup_preview"), icon="LIGHT")
        layout.label(text=ui_text(context, "hint_textures"))
        layout.label(text=ui_text(context, "hint_params"))


CLASSES = (
    SNOWMASK_OT_import_apply,
    SNOWMASK_OT_apply_all,
    SNOWMASK_OT_sync_from_active,
    SNOWMASK_OT_sync_from_selected,
    SNOWMASK_OT_set_debug_view,
    SNOWMASK_OT_set_show_original,
    SNOWMASK_OT_set_normal_noise_blend,
    SNOWMASK_OT_bake_top_projection,
    SNOWMASK_OT_set_top_projection_enabled,
    SNOWMASK_OT_set_top_projection_weight,
    SNOWMASK_OT_setup_preview,
    SNOWMASK_PT_panel,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.snowmask_ui_language = bpy.props.EnumProperty(
        name="语言 / Language",
        description="Snow Mask Tool UI language",
        items=LANGUAGE_ITEMS,
        default="ZH",
    )
    bpy.types.Scene.snowmask_template_material = bpy.props.EnumProperty(
        name="Snow Template Material",
        description="Material whose SNOW_MASK_CONTROLS values will be copied to all other snow materials",
        items=snow_material_items,
    )
    bpy.types.Scene.snowmask_normal_noise_blend = bpy.props.FloatProperty(
        name="Normal Noise Blend",
        description="0 = clean top-facing normal mask, 1 = noisy normal mask",
        default=1.0,
        min=0.0,
        max=1.0,
    )
    bpy.types.Scene.snowmask_top_projection_weight = bpy.props.FloatProperty(
        name="Top Projection Weight",
        description="Strength for the baked top-projection coverage mask",
        default=1.0,
        min=0.0,
        max=1.0,
    )


def unregister():
    if hasattr(bpy.types.Scene, "snowmask_ui_language"):
        del bpy.types.Scene.snowmask_ui_language
    if hasattr(bpy.types.Scene, "snowmask_template_material"):
        del bpy.types.Scene.snowmask_template_material
    if hasattr(bpy.types.Scene, "snowmask_normal_noise_blend"):
        del bpy.types.Scene.snowmask_normal_noise_blend
    if hasattr(bpy.types.Scene, "snowmask_top_projection_weight"):
        del bpy.types.Scene.snowmask_top_projection_weight
    for cls in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass


if __name__ == "__main__":
    register()

