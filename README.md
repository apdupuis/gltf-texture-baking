# GLTF Texture Baking

A Blender script for converting an object's material into a GLTF-ready format. When running the script, the selected object and its materials are copied before baking its textures, preserving the original object for future editing. The new object's material is cleaned to avoid any problems when exporting to GLTF.

## Usage

To load the script into a Blender file, go to the Text Editor (shortcut Shift-F11), click "Open", and load bakeTexture.py.

When you want to bake an object's materials to textures, select that object, then run (Alt/Option-P) bakeTexture.py in the Text Editor.