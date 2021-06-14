"""
    Paradox asset files, read/write binary data.

    This is designed to be compatible with both Python 2 and Python 3 (so code can be shared across Maya and Blender)
    Critically, the way strings and binary data are handled must now be done with care, see...
        http://python-future.org/compatible_idioms.html#byte-string-literals

    author : ross-g
"""

from __future__ import print_function, unicode_literals

import sys
import json
import warnings
from struct import pack, unpack_from

try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

# Py2, Py3 compatibility
PY2 = sys.version_info[0] < 3
try:
    basestring
except NameError:
    basestring = str


""" ====================================================================================================================
    PDX data classes.
========================================================================================================================
"""


class PDXData(object):
    """
        Simple class that turns an XML element hierarchy with attributes into a object for more convenient
        access to attributes.
    """

    def __init__(self, element, depth=None):
        # use element tag as object name
        setattr(self, "name", element.tag)

        # object depth in hierarchy
        self.depth = depth or 0

        # object attribute collection
        self.attrlist = []

        # set XML element attributes as object attributes
        for attr in element.attrib:
            setattr(self, attr, element.attrib[attr])
            self.attrlist.append(attr)

        # iterate over XML element children, set these as attributes, nesting further PDXData objects
        for child in list(element):
            child_data = type(self)(child, self.depth + 1)
            if hasattr(self, child.tag):
                curr_data = getattr(self, child.tag)
                if type(curr_data) == list:
                    curr_data.append(child_data)
                else:
                    setattr(self, child.tag, [curr_data, child_data])
            else:
                setattr(self, child.tag, child_data)
                self.attrlist.append(child.tag)

    def __str__(self):
        indent = " " * 4
        string = []

        for _key in self.attrlist:
            _val = getattr(self, _key)

            if type(_val) == type(self):
                string.append("{}{}:".format(self.depth * indent, _key))
                string.append("{}".format(_val))

            else:
                if all(type(v) == type(self) for v in _val):
                    for v in _val:
                        string.append("{}{}:".format(self.depth * indent, _key))
                        string.append("{}".format(v))
                else:
                    data_len = len(_val)
                    data_type = list(set(type(v) for v in _val))[0].__name__
                    string.append("{}{} ({}, {}):  {}".format(self.depth * indent, _key, data_type, data_len, _val))

        return "\n".join(string)


class PDXDataJSON(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, PDXData):
            d = {}
            for attr in obj.attrlist:
                val = getattr(obj, attr)
                if isinstance(val, list):
                    d[attr] = [v for v in val]
                else:
                    d[attr] = val
            return d
        return super(PDXDataJSON, self).default(self, obj)


""" ====================================================================================================================
    Functions for reading and parsing binary data.
========================================================================================================================
"""


def parseProperty(bdata, pos):
    # starting at '!'
    pos += 1

    # get length of property name
    prop_name_length = unpack_from("b", bdata, offset=pos)[0]
    pos += 1

    # get property name as string
    prop_name = parseString(bdata, pos, prop_name_length)
    pos += prop_name_length

    # get property data
    prop_values, pos = parseData(bdata, pos)

    return prop_name, prop_values, pos


def parseObject(bdata, pos):
    # skip and record any repeated '[' characters
    objdepth = 0
    while unpack_from("c", bdata, offset=pos)[0].decode() == "[":
        objdepth += 1
        pos += 1

    # get object name as string
    obj_name = ""
    # we don't know the string length, so look for an ending byte of zero
    while unpack_from("b", bdata, offset=pos)[0] != 0:
        obj_name += unpack_from("c", bdata, offset=pos)[0].decode("latin-1")
        pos += 1

    # skip the ending zero byte
    pos += 1

    return obj_name, objdepth, pos


def parseString(bdata, pos, length):
    val_tuple = unpack_from("c" * length, bdata, offset=pos)  # TODO: should fmt here be "s" * length ?

    # turn the resulting tuple into a string of bytes
    string = b"".join(val_tuple).decode("latin-1")

    # check if the ending byte is zero and remove if so
    if string[-1] == chr(0):
        string = string[:-1]

    return string


def parseData(bdata, pos):
    # determine the  data type
    datatype = unpack_from("c", bdata, offset=pos)[0].decode()
    # TODO: use an array here instead of list for memory efficiency?
    datavalues = []

    if datatype == "i":
        # handle integer data
        pos += 1

        # count
        size = unpack_from("i", bdata, offset=pos)[0]
        pos += 4

        # values
        for i in range(0, size):
            val = unpack_from("i", bdata, offset=pos)[0]
            datavalues.append(val)
            pos += 4

    elif datatype == "f":
        # handle float data
        pos += 1

        # count
        size = unpack_from("i", bdata, offset=pos)[0]
        pos += 4

        # values
        for i in range(0, size):
            val = unpack_from("f", bdata, offset=pos)[0]
            datavalues.append(val)
            pos += 4

    elif datatype == "s":
        # handle string data
        pos += 1

        # count
        size = unpack_from("i", bdata, offset=pos)[0]
        # TODO: we are assuming that we always have a count of 1 string, not an array of multiple strings
        pos += 4

        # string length
        str_data_length = unpack_from("i", bdata, offset=pos)[0]
        pos += 4

        # value
        val = parseString(bdata, pos, str_data_length)
        datavalues.append(val)
        pos += str_data_length

    else:
        raise NotImplementedError(
            "Unknown data type encountered. {} at position {}\n{}".format(datatype, pos, bdata[pos - 10 : pos + 10])
        )

    return datavalues, pos


def read_meshfile(filepath):
    """
        Reads through a .mesh file and gathers all the data into hierarchical element structure.
        The resulting XML is not natively writable to string as it contains Python data types.
    """
    # read the data
    with open(filepath, "rb") as fp:
        fdata = fp.read()

    # create an XML structure to store the object hierarchy
    file_element = Xml.Element("File")

    # determine the file length and set initial file read position
    eof = len(fdata)
    pos = 0

    # read the file header '@@b@'
    header = unpack_from("c" * 4, fdata, pos)
    if bytes(b"".join(header)) == b"@@b@":
        pos = 4
    else:
        raise NotImplementedError("Unknown file header. {}".format(header))

    parent_element = file_element
    depth_list = [file_element]
    current_depth = 0

    # parse through until EOF
    while pos < eof:
        next_char = unpack_from("c", fdata, offset=pos)[0].decode()
        # we have a property
        if next_char == "!":
            # check the property type and values
            prop_name, prop_values, pos = parseProperty(fdata, pos)

            # assign property values to the parent object
            parent_element.set(prop_name, prop_values)

        # we have an object
        elif next_char == "[":
            # check the object type and hierarchy depth
            obj_name, depth, pos = parseObject(fdata, pos)

            # deeper branch of the tree => current parent valid
            # same or shallower branch of the tree => parent gets redefined back a level
            if not depth > current_depth:
                # remove elements from depth list, change parent
                depth_list = depth_list[:depth]
                parent_element = depth_list[-1]

            # create a new object as a child of the current parent
            new_element = Xml.SubElement(parent_element, obj_name)
            # update parent
            parent_element = new_element
            # update depth
            depth_list.append(parent_element)
            current_depth = depth

        # we have something that we can't parse
        else:
            raise NotImplementedError("Unknown object encountered.")

    return file_element


""" ====================================================================================================================
    Functions for writing XML tree to binary data.
========================================================================================================================
"""


def writeProperty(prop_name, prop_data):
    datastring = b""

    try:
        # write starting '!'
        datastring += pack("c", "!".encode())

        # write length of property name
        prop_name_length = len(prop_name)
        datastring += pack("b", prop_name_length)

        # write property name as string
        datastring += writeString(prop_name)

        # write property data
        datastring += writeData(prop_data)

    except NotImplementedError as err:
        print("Failed writing property: {}".format(prop_name))
        raise err

    return datastring


def writeObject(obj_xml, obj_depth):
    datastring = b""

    # write object hierarchy depth
    for x in range(obj_depth):
        datastring += pack("c", "[".encode())

    # write object name as string
    obj_name = obj_xml.tag
    if not len(obj_name) < 64:
        raise NotImplementedError("Object name is longer than 64 characters: {}".format(obj_name))
    datastring += writeString(obj_name)
    # write zero-byte ending
    datastring += pack("x")

    return datastring


def writeString(string):
    datastring = b""

    string = string.encode("latin-1")
    datastring += pack("{0}s".format(len(string)), string)

    return datastring


def writeData(data_array):
    datastring = b""

    # determine the data type in the array
    types = set([type(d) for d in data_array])
    if len(types) == 1:
        datatype = types.pop()
    elif len(types) < 1:
        return datastring
    else:
        raise NotImplementedError("Mixed data type encountered. {} - {}".format(types, data_array))

    if all(isinstance(d, int) for d in data_array):
        # write integer data
        datastring += pack("c", "i".encode())

        # write the data count
        size = len(data_array)
        datastring += pack("i", size)

        # write the data values
        datastring += pack("i" * size, *data_array)

    elif all(isinstance(d, float) for d in data_array):
        # write float data
        datastring += pack("c", "f".encode())

        # count
        size = len(data_array)
        datastring += pack("i", size)

        # values
        datastring += pack("f" * size, *data_array)

    elif all(isinstance(d, basestring) for d in data_array):
        # write string data
        datastring += pack("c", "s".encode())

        # count
        size = 1
        # TODO: we are assuming that we always have a count of 1 string, not an array of multiple strings
        datastring += pack("i", size)

        # string length
        str_data_length = len(data_array[0])
        datastring += pack("i", (str_data_length + 1))  # string length + 1 to account for zero-byte ending

        # values
        datastring += writeString(data_array[0])  # Py2 struct.pack cannot handle unicode strings
        # write zero-byte ending
        datastring += pack("x")

    else:
        raise NotImplementedError("Unknown data type encountered. {}\n{}".format(datatype, data_array))

    return datastring


def write_meshfile(filepath, root_xml):
    """
        Iterates over an XML element and writes the element structure back into a binary file as mesh data.
    """
    datastring = b""

    # write the file header '@@b@'
    header = "@@b@"
    for x in header:
        datastring += pack("c", x.encode())

    # write the file properties
    if root_xml.tag == "File":
        datastring += writeProperty("pdxasset", root_xml.get("pdxasset"))
    else:
        raise NotImplementedError("Unknown XML root encountered. {}".format(root_xml.tag))

    # TODO: writing properties would be easier if order was irrelevant, only under Py3 do Xml attributes maintain order
    # TODO: test in game files to determine if order of attributes or objects is important
    # write objects root
    object_xml = root_xml.find("object")
    if object_xml is not None:
        current_depth = 1
        datastring += writeObject(object_xml, current_depth)

        # write each shape node
        for shape_xml in object_xml:
            current_depth = 2
            datastring += writeObject(shape_xml, current_depth)

            # write each mesh
            for child_xml in shape_xml:
                current_depth = 3
                datastring += writeObject(child_xml, current_depth)

                if child_xml.tag == "mesh":
                    mesh_xml = child_xml
                    # write mesh properties
                    for prop in ["p", "n", "ta", "u0", "u1", "u2", "u3", "tri"]:
                        if mesh_xml.get(prop) is not None:
                            datastring += writeProperty(prop, mesh_xml.get(prop))

                    # write mesh sub-objects
                    aabb_xml = mesh_xml.find("aabb")
                    if aabb_xml is not None:
                        current_depth = 4
                        datastring += writeObject(aabb_xml, current_depth)
                        for prop in ["min", "max"]:
                            if aabb_xml.get(prop) is not None:
                                datastring += writeProperty(prop, aabb_xml.get(prop))

                    material_xml = mesh_xml.find("material")
                    if material_xml is not None:
                        current_depth = 4
                        datastring += writeObject(material_xml, current_depth)
                        for prop in ["shader", "diff", "n", "spec"]:
                            if material_xml.get(prop) is not None:
                                datastring += writeProperty(prop, material_xml.get(prop))

                    skin_xml = mesh_xml.find("skin")
                    if skin_xml is not None:
                        current_depth = 4
                        datastring += writeObject(skin_xml, current_depth)
                        for prop in ["bones", "ix", "w"]:
                            if skin_xml.get(prop) is not None:
                                datastring += writeProperty(prop, skin_xml.get(prop))

                elif child_xml.tag == "skeleton":
                    # write bone sub objects and properties
                    for bone_xml in child_xml:
                        current_depth = 4
                        datastring += writeObject(bone_xml, current_depth)
                        for prop in ["ix", "pa", "tx"]:
                            if bone_xml.get(prop) is not None:
                                datastring += writeProperty(prop, bone_xml.get(prop))

    # write locators root
    locator_xml = root_xml.find("locator")
    if locator_xml is not None:
        current_depth = 1
        datastring += writeObject(locator_xml, current_depth)

        # write each locator
        for locnode_xml in locator_xml:
            current_depth = 2
            datastring += writeObject(locnode_xml, current_depth)

            # write locator properties
            for prop in ["p", "q", "pa", "tx"]:
                if locnode_xml.get(prop) is not None:
                    datastring += writeProperty(prop, locnode_xml.get(prop))

    # write the data
    with open(filepath, "wb") as fp:
        fp.write(datastring)


def write_animfile(filepath, root_xml):
    """
        Iterates over an XML element and writes the element structure back into a binary file as animation data.
    """
    datastring = b""

    # write the file header '@@b@'
    header = "@@b@"
    for x in header:
        datastring += pack("c", x.encode())

    # write the file properties
    if root_xml.tag == "File":
        datastring += writeProperty("pdxasset", root_xml.get("pdxasset"))
    else:
        raise NotImplementedError("Unknown XML root encountered. {}".format(root_xml.tag))

    # write info root
    info_xml = root_xml.find("info")
    if info_xml is not None:
        current_depth = 1
        datastring += writeObject(info_xml, current_depth)

        # write info properties
        for prop in ["fps", "sa", "j"]:
            if info_xml.get(prop) is not None:
                datastring += writeProperty(prop, info_xml.get(prop))

        # write each bone
        for bone_xml in info_xml:
            current_depth = 2
            datastring += writeObject(bone_xml, current_depth)

            # write bone properties
            for prop in ["sa", "t", "q", "s"]:
                if bone_xml.get(prop) is not None:
                    datastring += writeProperty(prop, bone_xml.get(prop))

    # write samples root
    samples_xml = root_xml.find("samples")
    if samples_xml is not None:
        current_depth = 1
        datastring += writeObject(samples_xml, current_depth)

        # write sample properties
        for prop in ["t", "q", "s"]:
            if samples_xml.get(prop) is not None:
                datastring += writeProperty(prop, samples_xml.get(prop))

    # write the data
    with open(filepath, "wb") as fp:
        fp.write(datastring)


""" ====================================================================================================================
    Main.
========================================================================================================================
"""


if __name__ == "__main__":
    """When called from the command line we can just print the structure and contents of the .mesh or .anim file to
    stdout or write directly to a text file. """
    if PY2:
        warnings.warn(
            "Commandline mode is only supported under Python 3 (running from {0})".format(
                ".".join(str(c) for c in sys.version_info)
            )
        )

    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="io_pdx_mesh CLI")
    parser.add_argument("path")
    parser.add_argument("--outdir", "-out", required=False, default=None)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--totext", "-txt", action="store_true", default=False)
    group.add_argument("--tojson", "-json", action="store_true", default=False)
    args = parser.parse_args()

    file_list = []
    path = Path(args.path)
    suffix = ".json" if args.tojson else ".txt"
    outdir = None

    # run on this single file
    if path.is_file():
        try:
            out_filepath = Path(args.outdir)
        except TypeError:
            out_filepath = path.parent / path.name
        outdir = out_filepath.parent

        file_list.append([path, (out_filepath).with_suffix(suffix)])

    # run on this whole folder structure, recursively
    elif path.is_dir():
        try:
            outdir = Path(args.outdir)
        except TypeError:
            outdir = path

        all_files = []
        for ext in ["*.mesh", "*.anim"]:
            all_files.extend(path.rglob(ext))
        for fullpath in all_files:
            file_list.append([fullpath, (outdir / fullpath.relative_to(path)).with_suffix(suffix)])

    print_only = args.totext is False and args.tojson is False
    n = len(file_list)
    for i, (filepath, outpath) in enumerate(file_list):
        pdx_data = PDXData(read_meshfile(str(filepath)))

        if print_only:
            print("-" * 120)
            print(str(filepath))
            print()
            print(str(pdx_data))

        else:
            print("{0}/{1} : {2} --> {3}".format(i + 1, n, filepath.relative_to(path.parent), outpath.relative_to(outdir)))
            outpath.parent.mkdir(parents=True, exist_ok=True)
            with open(str(outpath), "wt") as fp:
                if args.totext:
                    fp.write(str(pdx_data) + "\n")
                if args.tojson:
                    json.dump(pdx_data, fp, indent=2, cls=PDXDataJSON)


"""
General binary format is:
    data description
    data type
    depth of data
    data content


.mesh file format
========================================================================================================================
    header    (@@b@ for binary, @@t@ for text)
    pdxasset    (int)  number of assets? file format version?
        object    (object)  parent item for all 3D objects
            lodperc    (float)  list of LOD switches, percentage size of bounding sphere?  [IMPERATOR]
            loddist    (float)  list of LOD switches, some distance metric?  [EU4/STELLARIS/HOI4]
            shape    (object)
                ...  multiple shapes, used for meshes under different node transforms
            shape    (object)
                lod    (int)  LOD level of shape, 0 based
                mesh    (object)
                    ...  multiple meshes per shape, used for different material IDs
                mesh    (object)
                    ...
                mesh    (object)
                    p    (float)  verts
                    n    (float)  normals
                    ta    (float)  tangents
                    u0    (float)  UVs
                    tri    (int)  triangles
                    boundingsphere    (float)  centre and radius of mesh spherical bounds  [IMPERATOR/CK3]
                    aabb    (object)
                        min    (float)  min bounding box
                        max    (float)  max bounding box
                    material    (object)
                        shader    (string)  shader name
                        diff    (string)  diffuse texture
                        n    (string)  normal texture
                        spec    (string)  specular texture
                    skin    (object)
                        bones    (int)  num skin influences
                        ix    (int)  skin bone ids
                        w    (float)  skin weights
                skeleton    (object)
                    bone    (object)
                        ix    (int)  index
                        pa    (int)  parent index, omitted for root
                        tx    (float)  inverse worldspace transform, 3*4 matrix (transforms bone back to scene origin)
        locator    (object)  parent item for all locators
            node    (object)
                p    (float)  position
                q    (float)  quarternion
                pa    (string)  parent name
                tx    (float)  worldspace transform, 4*4 matrix (allow locator scale)  [IMPERATOR]


.anim file format
========================================================================================================================
    header    (@@b@ for binary, @@t@ for text)
    pdxasset    (int)  number of assets?
        info    (object)
            fps    (float)  anim speed
            sa    (int)  num keyframes
            j    (int)  num bones
            bone    (object)
                ...  multiple bones, not all may be animated based on 'sa' attribute
            bone    (object)
                ...
            bone    (object)
                sa    (string)  animation curve types, combination of 's', 't', 'q'
                t    (float)  initial translation as vector
                q    (float)  initial rotation as quaternion
                s    (float)  initial scale as single float
        samples    (object)
            t   (floats)    list of translations (size 3), by bone, by frame (translation from parent, in parent space)
            q   (floats)    list of rotations (size 4), by bone, by frame (rotation from parent, in parent space)
            s   (floats)    list of scales (size 1), by bone, by frame
"""
