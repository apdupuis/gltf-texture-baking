bl_info = {
    "name": "GLTF Texture Baker",
    "author": "Alex Dupuis <alexander.p.dupuis@gmail.com>",
    "version": (1, 0),
    "blender": (2, 93, 0),
    "location": "Operator Search",
    "description": "Bake textures to prepare model for GLTF export",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
    "category": "Material",
}

import bpy
from ctypes import *
from time import sleep

# Handler type enum. Operator is 3
WM_HANDLER_TYPE_GIZMO = 1
WM_HANDLER_TYPE_UI = 2
WM_HANDLER_TYPE_OP = 3
WM_HANDLER_TYPE_DROPBOX = 4
WM_HANDLER_TYPE_KEYMAP = 5

# Generate listbase of appropriate type. None: generic
def listbase(type_=None):
    ptr = POINTER(type_)
    fields = ("first", ptr), ("last", ptr)
    return type("ListBase", (Structure,), {'_fields_': fields})

# Mini struct for Op handlers. *not* bContext!
class OpContext(Structure):
    pass
class wmEventHandler(Structure):  # Generic
    pass
class wmEventHandler_Op(Structure):  # Operator
    pass
class wmWindow(Structure):
    pass

wmEventHandler._fields_ = (
    ("next", POINTER(wmEventHandler)),
    ("prev", POINTER(wmEventHandler)),
    ("type", c_int),  # Enum
    ("flag", c_char),
    ("poll", c_void_p),
)
wmWindow._fields_ = (  # from DNA_windowmanager_types.h
    ("next", POINTER(wmWindow)),
    ("prev", POINTER(wmWindow)),
    ("ghostwin", c_void_p),
    ("gpuctx", c_void_p),
    ("parent", POINTER(wmWindow)),
    ("scene", c_void_p),
    ("new_scene", c_void_p),
    ("view_layer_name", c_char * 64),
    ("workspace_hook", c_void_p),
    ("global_areas", listbase(type_=None) * 3),
    ("screen", c_void_p),
    ("posx", c_short),
    ("posy", c_short),
    ("sizex", c_short),
    ("sizey", c_short),
    ("windowstate", c_short),
    ("monitor", c_short),
    ("active", c_short),
    ("cursor", c_short),
    ("lastcursor", c_short),
    ("modalcursor", c_short),
    ("grabcursor", c_short),
    ("addmousemove", c_short),
    ("winid", c_int),
    ("lock_pie_event", c_short),
    ("last_pie_event", c_short),
    ("eventstate", c_void_p),
    ("tweak", c_void_p),
    ("ime_data", c_void_p),
    ("queue", listbase(type_=None)),
    ("handlers", listbase(type_=None)),
    ("modalhandlers", listbase(type_=wmEventHandler)),
    ("gesture", listbase(type_=None)),
    ("stereo3d_format", c_void_p),
    ("drawcalls", listbase(type_=None)),
    ("cursor_keymap_status", c_void_p)
)
OpContext._fields_ = (
    ("win", POINTER(wmWindow)),
    ("area", c_void_p),  # <-- ScrArea ptr
    ("region", c_void_p),  # <-- ARegion ptr
    ("region_type", c_short)
)
wmEventHandler_Op._fields_ = (
    ("head", wmEventHandler),
    ("op", c_void_p), # <-- wmOperator
    ("is_file_select", c_bool),
    ("context", OpContext)
)

def get_num_running_modal_ops():
    
    modal_ops_count = 0
    
    window = bpy.context.window
    win = cast(window.as_pointer(), POINTER(wmWindow)).contents

    handle = win.modalhandlers.first
    
    while handle:
        if handle.contents.type == WM_HANDLER_TYPE_OP:
            modal_ops_count += 1
        handle = handle.contents.next
        
    return modal_ops_count

class TextureBaker:

    def __init__(self, obj, _tex_dim):
        self.obj = obj
        self.material = self.obj.active_material
        self.tex_dim = _tex_dim
        self.baked_texture_nodes = []
        self.nodes_to_keep = []
        self.bake_list = []
        self.previously_baked_texture_info = []
        
    def unused_node(self, node):
        return node not in self.nodes_to_keep and node not in self.baked_texture_nodes
        
    def clean_up_baked_material(self):
        # connect shader back to material output
        self.material_links.new(self.output_shader.outputs[0], self.material_output.inputs[0])
        
        # connect uv map to baked texture nodes, and texture nodes to shader 
        for baked_texture_info in self.previously_baked_texture_info:
            baked_texture_node = baked_texture_info['texture_node']
            shader_input = self.output_shader.inputs[baked_texture_info['index']]
            self.material_links.new(baked_texture_node.outputs[0], shader_input)
            self.material_links.new(self.material_uv_node.outputs[0], baked_texture_node.inputs[0])
        
        # delete all nodes we won't be using
        for node in self.material_nodes:
            if self.unused_node(node):
                self.material_nodes.remove(node)
                
        current_x_pos = 100
        starting_y_pos = 100
        current_y_pos = starting_y_pos
        node_spacing = 50
        max_tex_node_width = 0
        
        self.material_uv_node.location = (current_x_pos, current_y_pos)
        current_x_pos += self.material_uv_node.width + node_spacing
        
        # align all the baked texture nodes
        for baked_tex_node in self.baked_texture_nodes:
            baked_tex_node.location = (current_x_pos, current_y_pos)
            current_y_pos -= baked_tex_node.height + node_spacing
            max_tex_node_width = max(max_tex_node_width, baked_tex_node.width)
            
        current_y_pos = starting_y_pos
        current_x_pos += max_tex_node_width + node_spacing
        
        # line up the shader and material output nodes
        self.output_shader.location = (current_x_pos, current_y_pos)
        current_x_pos += self.output_shader.width + node_spacing
        self.material_output.location = (current_x_pos, current_y_pos)       
        
    def prep_for_baking(self):
        self.make_obj_bake_copy()
        self.make_material_bake_copy()
        self.material_uv_node = self.material_nodes.new('ShaderNodeUVMap')
        self.nodes_to_keep.append(self.material_uv_node)
        print("we should have made a dummy texture here")

        self.make_bake_list()
        self.previously_baked_texture_info = []
        
    def is_finished_baking(self):
        return len(self.bake_list) == 0
        
    def bake_next_texture(self):
        input_info = self.bake_list.pop(0)
        self.bake_texture(input_info)
        
    def bake_texture(self, _input_info):
        # create blank image for texture
        tex_name = self.obj.name + "_" + _input_info['name']
        tex_dim = self.tex_dim
        baked_image = bpy.data.images.new(name=tex_name, width=tex_dim, height=tex_dim, alpha=False)
        
        # add an image texture node to the material
        texture_node = self.material_nodes.new('ShaderNodeTexImage')
        # minimize texture node
        texture_node.hide = True
        
        # set the image texture to the generated image file
        texture_node.image = baked_image
        
        # link the uv map to the texture node 
        self.material_links.new(self.material_uv_node.outputs[0], texture_node.inputs[0])

        # append texture node to our list of nodes
        self.baked_texture_nodes.append(texture_node)
        
        # append texture node and its connection info to previously baked texture list
        baked_texture_info = _input_info
        baked_texture_info['texture_node'] = texture_node
        self.previously_baked_texture_info.append(baked_texture_info)
        
        # set the image node to active so we can bake to it
        texture_node.select = True
        self.material_nodes.active = texture_node
        
        # connect the nodes that will be baked directly to the material output
        shader_input = self.output_shader.inputs[_input_info['index']]
        shader_input_links = shader_input.links[0]
        src_node_socket = shader_input_links.from_socket
        self.material_links.new(src_node_socket, self.material_output.inputs[0])
        
        # bake the texture
        bpy.ops.object.bake('INVOKE_DEFAULT', type='EMIT')
    
    def make_obj_bake_copy(self):
        original_obj = self.obj
        self.obj = self.obj.copy()
        self.obj.data = original_obj.data.copy()
        self.obj.name = original_obj.name + "_baked"
        
        # set the material to the new object's material
        self.material = self.obj.active_material
        
        # add new object to the scene collection
        bpy.context.collection.objects.link(self.obj)

        # deselect old object
        original_obj.select_set(False)
        
    def make_material_bake_copy(self):
        original_material = self.material
        self.material = self.material.copy()
        self.material.name = original_material.name + "_baked"
        self.obj.active_material = self.material
        
        self.material_nodes = self.material.node_tree.nodes
        self.material_links = self.material.node_tree.links
        self.material_output = self.get_material_output()
        self.output_shader = self.get_output_shader()
        self.nodes_to_keep.append(self.material_output)
        self.nodes_to_keep.append(self.output_shader)
        
    def get_material_output(self):
        _material_output = None
        for node in self.material_nodes:
            if node.type == "OUTPUT_MATERIAL":
                _material_output = node
                break
            
        return _material_output
    
    def get_output_shader(self):
        _shader = None
        
        if self.material_output is not None and self.material_output.inputs[0].links:
            _shader = self.material_output.inputs[0].links[0].from_node
            
        return _shader
    
    def make_bake_list(self):
        self.bake_list = []
        
        if self.output_shader is None:
            print("No output shader!")
            return
        
        for idx, node_input in enumerate(self.output_shader.inputs):
            if node_input.links:
                input_info = {}
                input_info['name'] = node_input.name
                input_info['index'] = idx
                self.bake_list.append(input_info)
    

class MATERIAL_OT_gltf_baker(bpy.types.Operator):
    """Operator which runs its self from a timer"""
    bl_idname = "wm.gltf_texture_baker"
    bl_label = "GLTF Texture Baker"

    tex_dim: bpy.props.IntProperty(
        name="Texture Dimensions",
        description="Size of the baked texture in pixels",
        default=32,
        min=1,
    )

    _timer = None
    previous_num_modal_ops = 0

    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}:
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            current_num_modal_ops = get_num_running_modal_ops()
    
            if current_num_modal_ops <= self.previous_num_modal_ops:
                if self.texture_baker.is_finished_baking():
                    self.texture_baker.clean_up_baked_material()
                    return {'FINISHED'}
                else:
                    print("starting a new bake")
                    self.texture_baker.bake_next_texture()
            else:
                pass

        return {'PASS_THROUGH'}

    def execute(self, context):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        
        self.previous_num_modal_ops = get_num_running_modal_ops()
        self.texture_baker = TextureBaker(bpy.context.active_object, self.tex_dim)
        self.texture_baker.prep_for_baking()
    
        bpy.context.scene.render.engine = 'CYCLES'
        
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)

class GltfBakerPreferences(bpy.types.AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = __name__

    tex_dim: bpy.props.IntProperty(
        name="Texture Dimensions",
        description="Size of the baked texture in pixels",
        default=32,
        min=1,
    )

class VIEW3D_PT_gltf_baker(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Bake'
    bl_label = 'Texture baking'

    def get_active_object(self, context):
        if context.active_object is not None and context.active_object in context.selected_objects:
            return context.active_object
        else:
            return None

    def draw(self, context):
        settings_col = self.layout.column(align=True)
        settings_col.label(text="Bake settings")
        bake_prefs = context.preferences.addons[__name__].preferences
        settings_col.prop(bake_prefs, "tex_dim")
        
        bake_col = self.layout.column(align=True)
        active_object = self.get_active_object(context)
        if active_object:
            bake_col.label(text="Object to bake:")
            bake_col.label(text="    "+active_object.name)
            bake_props = bake_col.operator("wm.gltf_texture_baker",
                text='Bake textures')
            bake_props.tex_dim = bake_prefs.tex_dim
        else:
            bake_col.label(text='- no object selected! -')

def register():
    bpy.utils.register_class(MATERIAL_OT_gltf_baker)
    bpy.utils.register_class(VIEW3D_PT_gltf_baker)
    bpy.utils.register_class(GltfBakerPreferences)

def unregister():
    bpy.utils.unregister_class(MATERIAL_OT_gltf_baker)
    bpy.utils.unregister_class(VIEW3D_PT_gltf_baker)
    bpy.utils.unregister_class(GltfBakerPreferences)