"""
    Paradox asset files, read/write binary data.
    
    author : ross-g
"""

import os, sys
import struct
import json

clear = lambda: os.system('cls')


""" ================================================================================================
    Variables.
====================================================================================================
"""

SETTINGS_FILE = os.path.join(os.environ['HOME'], 'Documents', 'Paradox Interactive', 'PdxExporter', 'settings', 'clausewitz.txt')


""" ================================================================================================
    Functions for reading binary data files.
====================================================================================================
"""

def readBinaryFile(filepath):
    with open(filepath, 'rb') as file:
        data = file.read()

    return data

def parseBinary(bdata):
    # determine the file length
    eof = len(bdata)

    # set inital position in file to skip '@@b@'
    pos = 4
    objdepth = 0

    # scan through until EOF
    obj_list = [['file']]
    while pos < eof:
        if struct.unpack('c', bdata[pos])[0] == '!':
            # we have a property
            if objdepth == None: objdepth = 0
            prop_name, prop_values, pos = parseProperty(bdata, pos)
            parent = obj_list[objdepth][-1]
            print "  "*objdepth+"  property:", prop_name, "("+parent+")", "\n", prop_values

        elif struct.unpack('c', bdata[pos])[0] == '[':
            # we have an object
            obj_name, objdepth, pos = parseObject(bdata, pos)
            if len(obj_list) == objdepth + 1:
                obj_list[objdepth].append(obj_name)
            else:
                obj_list.append([obj_name])
            parent = obj_list[objdepth-1][-1]
            print "  "*objdepth+"object:", obj_name, "("+parent+")"

        else:
            raise NotImplementedError("Unknown object encountered.")

def parseProperty(bdata, pos):
    # starting at '!'
    pos += 1

    # get length of property name
    prop_name_length = struct.unpack('b', bdata[pos])[0]
    pos += 1

    # get property name as string
    prop_name = parseString(bdata, pos, prop_name_length)
    pos += prop_name_length

    # get property data
    prop_values, pos = parseData(bdata, pos)

    return (prop_name, prop_values, pos)

def parseObject(bdata, pos):
    # skip and record any repeated '[' characters
    objdepth = 0
    while struct.unpack('c', bdata[pos])[0] == '[':
        objdepth += 1
        pos += 1

    # get object name as string
    obj_name = ''
    # we don't know the string length, so look for an ending byte of zero
    while struct.unpack('b', bdata[pos])[0] != 0:
        obj_name += struct.unpack('c', bdata[pos])[0]
        pos += 1
    
    # skip the ending zero byte
    pos += 1

    return (obj_name, objdepth, pos)

def parseString(bdata, pos, length):
    string = struct.unpack('c'*length, bdata[pos:pos+length])

    # check if the ending byte is zero and remove if so
    if string[-1] == chr(0):
        string = string[:-1]

    return ''.join(string)

def parseData(bdata, pos):
    datavalues = []
    # determine the  data type
    datatype = struct.unpack('c', bdata[pos])[0]

    if datatype == 'i':
        # handle integer data
        pos += 1

        # count
        size = struct.unpack('i', bdata[pos:pos+4])[0]
        pos += 4

        # values
        for i in range(0, size):
            val = struct.unpack('i', bdata[pos:pos+4])[0]
            datavalues.append(val)
            pos += 4

    elif datatype == 'f':
        # handle float data
        pos += 1

        # count
        size = struct.unpack('i', bdata[pos:pos+4])[0]
        pos += 4
        
        # values
        for i in range(0, size):
            val = struct.unpack('f', bdata[pos:pos+4])[0]
            datavalues.append(val)
            pos += 4

    elif datatype == 's':
        # handle string data
        pos += 1

        # count
        size = struct.unpack('i', bdata[pos:pos+4])[0]
        # TODO: we are assuming that we always have a count of 1 string, not an array of multiple strings
        pos += 4

        # string length
        str_data_length = struct.unpack('i', bdata[pos:pos+4])[0]
        pos += 4

        # value
        val = parseString(bdata, pos, str_data_length)
        datavalues.append(val)
        pos += str_data_length

    else:
        raise NotImplementedError("Unknown data type encountered.")

    return (datavalues, pos)

def read_meshfile(filepath, to_stdout=False, full=False):
    """
        Reads through a .mesh file and instantiates PDX... classes based on the file hierarchy
        
        TODO
        This might need re-architecting, using nested lists to create the hierarchy leads to lots of arbitrary traversing the list back up the hierarchy
        where we need to reference anything other than the immediate parent, this could also be problematic where we have multiples of the same object
        type in a file.
        Possibly use tree structure?  https://gist.github.com/hrldcpr/2012250
        Possibly use named tuples? ordered dict?  https://docs.python.org/2.7/library/collections.html
        Possibly use self-defining classes?
    """
    # read the data
    fdata = readBinaryFile(filepath)

    # create the asset class, this represents the whole file
    pdxasset = PDXmodel(os.path.split(filepath)[1])
    # create a nested list to store the object hierarchy, this get populated by strings or classes 
    # depending on how we're handing the specific object
    obj_list = [['file']]
    obj_depth = 0
    
    
    # determine the file length
    eof = len(fdata)
    # set position in file to skip '@@b@'
    if fdata[:4] == '@@b@':
        pos = 4
    else:
        raise StandardError("Unknown file header")

    # parse through until EOF
    current_object = None
    while pos < eof:
        # we have a property
        if struct.unpack('c', fdata[pos])[0] == '!':
            # check the property type and values
            prop_name, prop_values, pos = parseProperty(fdata, pos)
            # check which object has this property
            parent_object = obj_list[obj_depth][-1]

            # assign property values to the parent object
            try:
                setattr(parent_object, prop_name, prop_values)
            except:
                # special case some properties, assign values to the grandparent
                if parent_object == 'aabb':
                    parent_mesh = obj_list[obj_depth-1][-1]
                    setattr(parent_mesh, parent_object+prop_name, prop_values)

            if to_stdout:
                if full:
                    print "  "*obj_depth+"  prop:", prop_name, "("+str(parent_object)+")", "\n", prop_values
                else:
                    print "  "*obj_depth+"  prop:", prop_name, "("+str(parent_object)+")"

        # we have an object
        elif struct.unpack('c', fdata[pos])[0] == '[':
            # check the object type and hierarchy depth
            obj_name, obj_depth, pos = parseObject(fdata, pos)
            # check which object contains this object in the hierarcy
            parent_object = obj_list[obj_depth-1][-1]

            # determine if this is a known object type, then instantiate it
            if obj_name == 'mesh':
                current_object = PDXmesh(parent_object)
                pdxasset.meshes.append(current_object)
            elif obj_name == 'material':
                current_object = PDXmaterial()
                parent_object.material = current_object
            elif obj_name == 'skin':
                current_object = PDXskin()
                parent_object.skin = current_object
            else:
                # some obects have type defined by their parent, instantiate them
                if parent_object == 'locator':
                    current_object = PDXlocator(obj_name)
                    pdxasset.locators.append(current_object)
                elif parent_object == 'skeleton':
                    # if not hasattr(parent_object, 'skeleton'):
                    #     parent_object.skeleton = []
                    current_object = PDXbone(obj_name)
                    parent_object = obj_list[obj_depth-1][-2]       # TODO this feels sloppy, we arbitrarily traverese the list back one more item at the right depth
                    parent_object.skeleton.append(current_object)
                # otherwise just store the name string instead
                else:
                    current_object = obj_name

            try:
                obj_list[obj_depth].append(current_object)
            except:
                obj_list.append([current_object])

            if to_stdout: print "  "*obj_depth+"obj:", current_object, "("+str(parent_object)+")", obj_depth

        else:
            raise NotImplementedError("Unknown object encountered.")

    return pdxasset


""" ================================================================================================
    Classes describing PDX objects.
====================================================================================================
"""

class PDXmodel(object):
    """
        mesh    (object)
        locator    (object)
    """
    def __init__(self, filename):
        self.filename = filename
        self.meshes = []
        self.locators = []

    def __str__(self):
        string = '{}'.format(self.filename)
        string += '\n\tmeshes:'
        for mesh in self.meshes:
            string += '\n\t\t{}'.format(mesh)
        string += '\n\tlocators:'
        for loc in self.locators:
            string += '\n\t\t{}'.format(loc)

        return string

class PDXmesh(object):
    """
        object    (object)
            shape    (object)  shape name in Maya
                mesh    (object)
                    p    (float)  verts
                    n    (float)  normals
                    ta    (float)  tangents
                    u    (float)  UVs
                    tri    (int)  triangles
                    aabb    (object)
                        min    (float)  min bounding box
                        max    (float)  max bounding box
                    material    (object)
                    skin    (object)
                        bones    (int)  used bones
                        ix    (int)  skin ids
                        w    (float)  skin weights
                skeleton    (object)
    """
    def __init__(self, name):
        self.name = name    # shape node name
        self.p = None
        self.n = None
        self.ta = None
        self.u = None
        self.tri = None
        self.aabbmin = None
        self.aabbmax = None
        self.material = None    # a mesh only has one material
        self.skin = None        # a mesh only has one skin
        self.skeleton = []    # a list of bone objects

    def __str__(self):
        return 'PDXmesh-{}'.format(self.name)

class PDXmaterial(object):
    """
        material    (object)
            shader    (string)  shader name
            diff    (string)  diffuse texture
            n    (string)  normal texture
            spec    (string)  specular texture
    """
    def __init__(self):
        self.shader = None
        self.diff = None
        self.n = None
        self.spec = None

    def get_textures(self):
        texture_dict = {key:val for (key,val) in (self.__dict__).items() if key != 'shader'}
        return texture_dict
        
    def __str__(self):
        return 'PDXmaterial-{}'.format(self.shader)

class PDXskin(object):
    """
        skin    (object)
            bones    (int)  number of influences, used to traverse other data
            ix    (int)  bone indices per vert
            w    (float)  skin weights per vert corresponding to the bone indices
    """
    def __init__(self):
        self.bones = None
        self.ix = None
        self.w = None
        
    def __str__(self):
        return 'PDXskin'

class PDXbone(object):
    """
        bone    (object)
            ix    (int)  index
            pa    (int)  parent index, omitted for root
            tx    (float)  transform, 3*4 matrix
    """
    def __init__(self, name):
        self.name = name
        self.ix = None
        self.pa = None
        self.tx = None
        
    def __str__(self):
        return 'PDXbone-{}'.format(self.name)

class PDXlocator(object):
    """
        locator    (object)
            node    (object)
                p    (float)  position?
                q    (float)  quarternion?
                pa    (string)  parent bone?
    """
    def __init__(self, name):
        self.name = name
        self.p = None
        self.q = None
        self.pa = None
        
    def __str__(self):
        return 'PDXlocator-{}'.format(self.name)



""" ================================================================================================
    Main.
====================================================================================================
"""

if __name__ == '__main__':
    """
        When run like this we just print the contents of the mesh file to stdout
    """
    clear()
    a_file = sys.argv[1]
    if len(sys.argv) == 3:
        full = sys.argv[2]
    else:
        full = False
    # a_file = r"C:\Users\Ross\Documents\GitHub\io_pdx_mesh\test files\test_object.mesh"
    # a_file = r"C:\Users\Ross\Documents\GitHub\io_pdx_mesh\test files\scan_detail.mesh" # SIMPLE locator, skeleton, skin
    # a_file = r"C:\Users\Ross\Documents\GitHub\io_pdx_mesh\test files\robot_01_portrait.mesh" # COMPLEX locators, skeletons, skins
    # a_file = r"C:\Users\Ross\Documents\GitHub\io_pdx_mesh\test files\combat_items\torpedo.mesh" # multiple meshes, collision shader

    print read_meshfile(a_file, to_stdout=True, full=full)



"""
.mesh file format

General binary format is:
    data description
    data type
    depth of data
    data content

=======================================================================================================================
    header    (@@b@ for binary, @@t@ for text)?
    pdxasset    (int)  number of assets?
        object    (object)  parent item for all 3D objects
            shape    (object)
                mesh    (object)
                    ...  multiple meshes per shape, used for different material IDs
                mesh    (object)
                    ...
                mesh    (object)
                    p    (float)  verts
                    n    (float)  normals
                    ta    (float)  tangents
                    u    (float)  UVs
                    tri    (int)  triangles
                    aabb    (object)
                        min    (float)  min bounding box
                        max    (float)  max bounding box
                    material    (object)
                        shader    (string)  shader name
                        diff    (string)  texture_diffuse
                        n    (string)  texture_normal
                        spec    (string)  texture_spec
                    skin    (object)
                        bones    (int)  used bones?
                        ix    (int)  skin ids
                        w    (float)  skin weights
                skeleton    (object)
                    bone    (object)
                        ix    (int)  index
                        pa    (int)  parent index, omitted for root
                        tx    (float)  transform, 3*4 matrix
        locator    (object)  parent item for all locators
            node    (object)
                p    (float)  position?
                q    (float)  quarternion?
                pa    (string)  parent bone?
=======================================================================================================================
"""