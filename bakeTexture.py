import bpy

default_tex_dim = 128

# create pop-up menu for user input 
class WM_OT_bakeTex(bpy.types.Operator):
    """Open the 'bake textures' dialog box"""
    bl_label = "Bake textures"
    bl_idname = "wm.baketextures"
    
    # define the properties that can be set in the pop-up window
    tex_dim = bpy.props.IntProperty(name = "texture dimensions", default= default_tex_dim)
    
    def execute(self, context):
        bake_textures(self.tex_dim)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

def register():
    bpy.utils.register_class(WM_OT_bakeTex)
    
def unregister():
    bpy.utils.unregister_class(WM_OT_bakeTex)
    
register()
bpy.ops.wm.baketextures('INVOKE_DEFAULT')

def bake_textures(tex_dim):
    # get the active object 
    obj = bpy.context.object

    # get the source material for the object
    src_mat = obj.active_material
    src_mat_nodes = src_mat.node_tree.nodes
    src_mat_links = src_mat.node_tree.links

    # check if the output shader is a principled bsdf 
    # first we find the Material Output node, if it exists
    src_mat_output = None
    for node in src_mat_nodes:
        if node.type == "OUTPUT_MATERIAL":
            src_mat_output = node
            break

    # if we don't find a material output, create it
    if src_mat_output is None:
        print('material does not have an output!')
    else:
        src_shader = src_mat_output.inputs[0].links[0].from_node
        if src_shader.type == 'BSDF_PRINCIPLED':
            print('we are using the right shader')
        else:
            print('warning: shader type is ' + src_shader.type)

    return
    
    # make copy of the active object for baking the texture 
    bake_obj = obj.copy()
    bake_obj.data = obj.data.copy()
    bake_obj.name = obj.name + "_baked"
    # we have to link the new object to a collection to see it
    bpy.context.collection.objects.link(bake_obj)

    #create blank image for texture
    tex_name = bake_obj.name + "_tex"
    generated_tex = bpy.data.images.new(name=tex_name, width=tex_dim, height=tex_dim, alpha=False)

    print("created new texture " + generated_tex.name)

    # make a copy of the original object's material for baking
    bake_mat = bake_obj.active_material.copy()
    bake_mat.name = src_mat.name + "_baked"
    bake_obj.active_material = bake_mat

    # get the node tree for the baked material so we can edit it 
    bake_mat_node_tree = bake_mat.node_tree
    bake_mat_nodes = bake_mat_node_tree.nodes

    # add a uv map node to the material 
    bake_mat_uv_node = bake_mat_nodes.new('ShaderNodeUVMap')
    bake_mat_uv_node.location = (100, 100)
    # TODO: specifically set the uv map to be used 

    # set horizontal spacing between generated nodes 
    node_spacing = 50

    # add an image texture node to the material
    bake_mat_tex_node = bake_mat_nodes.new('ShaderNodeTexImage')
    bake_mat_tex_node.location = (bake_mat_uv_node.location[0] + bake_mat_uv_node.width + node_spacing, 100)
    
    # set the image texture to the generated image file 
    bake_mat_tex_node.image = generated_tex

    # link the uv map to the image texture node 
    bake_mat_node_tree.links.new(bake_mat_uv_node.outputs[0], bake_mat_tex_node.inputs[0])

    # set the image node to active so we can bake to it 
    bake_mat_tex_node.select = True
    bake_mat_node_tree.nodes.active = bake_mat_tex_node

    # set render engine to cycles for baking 
    bpy.context.scene.render.engine = 'CYCLES'

    # bake the texture 
    bpy.ops.object.bake(type='EMIT')

    # set render engine back to eevee when finished baking
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'

    # clean up material to display the baked image 
    # delete all nodes except for uv map and image texture
    for mat_node in bake_mat_nodes:
        if mat_node != bake_mat_tex_node and mat_node != bake_mat_uv_node:
            bake_mat_nodes.remove(mat_node)
            
    # add in emission node and material output 
    bake_mat_emission_node = bake_mat_nodes.new('ShaderNodeEmission')
    bake_mat_emission_node.location = (bake_mat_tex_node.location[0] + bake_mat_tex_node.width + node_spacing, 100)
    bake_mat_output_node = bake_mat_nodes.new('ShaderNodeOutputMaterial')
    bake_mat_output_node.location = (bake_mat_emission_node.location[0] + bake_mat_emission_node.width + node_spacing, 100)

    # connect image texture to emission node 
    bake_mat_node_tree.links.new(bake_mat_tex_node.outputs[0], bake_mat_emission_node.inputs[0])
    # connect emission node to material output
    bake_mat_node_tree.links.new(bake_mat_emission_node.outputs[0], bake_mat_output_node.inputs[0])