import bpy

default_tex_dim = 128

def get_material_output(i_material):
    i_mat_nodes = i_material.node_tree.nodes

    i_mat_output = None
    for node in i_mat_nodes:
        if node.type == "OUTPUT_MATERIAL":
            i_mat_output = node
            break

    return i_mat_output

def get_material_shader(i_material):
    i_mat_output = get_material_output(i_material)
    i_shader = None

    # check if we have a material output, and its first input is connected
    if i_mat_output is not None and i_mat_output.inputs[0].links:
        i_shader = i_mat_output.inputs[0].links[0].from_node

    return i_shader

# for a given material, return a list of inputs connected to the 
# output shader that we can bake 
def get_bake_list(i_material):
    bake_list = []
    i_shader = get_material_shader(i_material)
    if i_shader is not None:
        for idx, node_input in enumerate(i_shader.inputs):
                    if node_input.links:
                        input_info = {}
                        input_info['name'] = node_input.name
                        input_info['index'] = idx
                        bake_list.append(input_info)

    return bake_list

# create pop-up menu for user input 
class WM_OT_bakeTex(bpy.types.Operator):
    """Open the 'bake textures' dialog box"""
    bl_label = "Bake textures"
    bl_idname = "wm.baketextures"
    
    # define the properties that can be set in the pop-up window
    warnings = bpy.props.StringProperty(name = "warnings", default="all clear")
    tex_dim = bpy.props.IntProperty(name = "texture dimensions", default= default_tex_dim)
    bake_texture_list = []
    
    def execute(self, context):
        bake_textures(self.bake_texture_list, self.tex_dim)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # get the active object 
        obj = bpy.context.object
        # get the source material for the object
        src_mat = obj.active_material
        self.bake_texture_list = get_bake_list(src_mat)

        self.warnings = "baking textures:\n"

        for tex_to_bake in self.bake_texture_list:
            self.warnings += " " + tex_to_bake['name']

        return context.window_manager.invoke_props_dialog(self)

def register():
    bpy.utils.register_class(WM_OT_bakeTex)
    
def unregister():
    bpy.utils.unregister_class(WM_OT_bakeTex)
    
register()
bpy.ops.wm.baketextures('INVOKE_DEFAULT')

def bake_texture(input_info, i_bake_info):

    #create blank image for texture
    tex_name = i_bake_info['object'].name + "_" + input_info['name']
    tex_dim = i_bake_info['texture_dimensions']
    baked_image = bpy.data.images.new(name=tex_name, width=tex_dim, height=tex_dim, alpha=False)

    # add an image texture node to the material
    texture_node = i_bake_info['material_nodes'].new('ShaderNodeTexImage')
    # minimize texture node
    texture_node.hide = True

    # set the image texture to the generated image file 
    texture_node.image = baked_image

    material_node = i_bake_info['output_nodes']['material_output']

    # link the uv map to the image texture node
    uv_map = i_bake_info['output_nodes']['uv_map']
    i_bake_info['node_links'].new(uv_map.outputs[0], texture_node.inputs[0])

    # add the texture node to the bake_info dictionary
    i_bake_info['output_nodes']['baked_images'].append(texture_node)

    # set the image node to active so we can bake to it 
    texture_node.select = True
    i_bake_info['material_nodes'].active = texture_node

    # connect the textures to be baked directly to the material output
    shader_input = i_bake_info['output_nodes']['shader'].inputs[input_info['index']]
    shader_input_links = shader_input.links[0]
    original_texture_socket = shader_input_links.from_socket
    material_output = i_bake_info['output_nodes']['material_output']
    i_bake_info['node_links'].new(original_texture_socket, material_node.inputs[0])

    # bake the texture 
    bpy.ops.object.bake(type='EMIT')

    # connect texture node to the corresponding shader input
    i_bake_info['node_links'].new(texture_node.outputs[0], shader_input)

def bake_textures(texture_bake_list, tex_dim):
    # get the active object 
    obj = bpy.context.object

    # get the source material for the object
    src_mat = obj.active_material

    # make copy of the active object for baking the texture 
    bake_obj = obj.copy()
    bake_obj.data = obj.data.copy()
    bake_obj.name = obj.name + "_baked"
    # we have to link the new object to a collection to see it
    # TODO: link the object to (one of) the source's collections
    bpy.context.collection.objects.link(bake_obj)

    # make a copy of the original object's material for baking
    bake_mat = bake_obj.active_material.copy()
    bake_mat.name = src_mat.name + "_baked"
    bake_obj.active_material = bake_mat
    bake_mat_nodes = bake_mat.node_tree.nodes
    bake_mat_links = bake_mat.node_tree.links

    # add a uv map node to the material 
    bake_mat_uv_node = bake_mat_nodes.new('ShaderNodeUVMap')
    # TODO: specifically set the uv map to be used 

    # make a dictionary containing the nodes we'll use in the baked texture
    # as well as all necessary info like the object, the material, the texture dimensions
    bake_info = {}
    bake_info['object'] = bake_obj
    bake_info['material'] = bake_mat
    bake_info['texture_dimensions'] = tex_dim
    bake_info['bake_list'] = texture_bake_list
    bake_info['material_nodes'] = bake_mat_nodes
    bake_info['node_links'] = bake_mat_links
    bake_info['output_nodes'] = {}
    bake_info['output_nodes']['material_output'] = get_material_output(bake_mat)
    bake_info['output_nodes']['shader'] = get_material_shader(bake_mat)
    bake_info['output_nodes']['baked_images'] = []
    bake_info['output_nodes']['uv_map'] = bake_mat_uv_node

    # set render engine to cycles for baking 
    bpy.context.scene.render.engine = 'CYCLES'

    # iteratively bake all textures
    for tex_to_bake in texture_bake_list:
        bake_texture(tex_to_bake, bake_info)

    # set render engine back to eevee when finished baking
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'

    # connect shader back to material output
    bake_info['node_links'].new(bake_info['output_nodes']['shader'].outputs[0], bake_info['output_nodes']['material_output'].inputs[0])

    # clean up material to display the baked image 
    # delete all nodes not found in 'output nodes'
    for mat_node in bake_mat_nodes:
        if mat_node not in bake_info['output_nodes'].values() and mat_node not in bake_info['output_nodes']['baked_images']:
            bake_mat_nodes.remove(mat_node)

    # line up nodes, starting with the uv map
    current_x = 100
    starting_y = 100
    current_y = 100
    node_spacing = 50
    max_tex_node_width = 0

    bake_info['output_nodes']['uv_map'].location = (current_x, current_y)
    current_x += bake_info['output_nodes']['uv_map'].width + node_spacing

    # align the baked images
    for baked_image in bake_info['output_nodes']['baked_images']:
        baked_image.location = (current_x, current_y)
        current_y -= baked_image.height + node_spacing
        if(max_tex_node_width < baked_image.width):
            max_tex_node_width = baked_image.width

    current_y = starting_y
    current_x += max_tex_node_width + node_spacing

    # align the shader and material output nodes
    bake_info['output_nodes']['shader'].location = (current_x, current_y)
    current_x += bake_info['output_nodes']['shader'].width + node_spacing
    bake_info['output_nodes']['material_output'].location = (current_x, current_y)