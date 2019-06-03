![GitHub last commit](https://img.shields.io/github/last-commit/ross-g/io_pdx_mesh.svg)
![Github All Releases](https://img.shields.io/github/downloads/ross-g/io_pdx_mesh/total.svg)
  
  
### IO PDX MESH
This project aims to allow editing of mesh and animation files used in the various Clausewitz Engine games created by [Paradox Development Studios](https://www.paradoxplaza.com) It's designed to run in *both* Maya and Blender.

### Download
Click here to view the [latest relase](https://github.com/ross-g/io_pdx_mesh/releases/latest) and download the __*io_pdx_mesh.zip*__ file (this works with both Maya and Blender).
  
  
#### Maya Installation
* Go to your Maya user scripts path. (eg on Windows: `C:\Users\...\Documents\maya\scripts`)  
* Extract the contents of the zip file directly into this path.  
* Start Maya and change the `Command Line` to Python by clicking the label.  
* Then use the command `import io_pdx_mesh;reload(io_pdx_mesh)` to launch the tool.  
* You can highlight this command and use the middle-mouse button to drag it into a shelf button to save it.  
* The tool window will now open.  
![Maya](https://raw.githubusercontent.com/wiki/ross-g/io_pdx_mesh/images/maya/tool_ui_01.png)

#### Blender Installation
* Start Blender and open the `User Preferences` panel.  
* Switch to the `Add-ons` tab and select `Install Add-on from file`. Pick the zip file you have downloaded.  
* Tick the checkbox to enable the add-on and you should see a new tab in the `Tool Shelf` of the `3D View`. (`View > Tool Shelf` if you have it closed)  
* The `Tool Shelf` will now have a `PDX Blender Tools` tab.  
![Blender](https://raw.githubusercontent.com/wiki/ross-g/io_pdx_mesh/images/blender/tool_ui_01.png)
