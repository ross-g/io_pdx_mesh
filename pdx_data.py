"""
    Paradox asset files, read/write binary data.
    
    author : ross-g
"""

import os
import sys
import struct
import inspect

try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml


""" ================================================================================================
    PDX data classes.
====================================================================================================
"""


class PDXData(object):
    """
        Simple class to turn an XML element with attributes into a object for more convenient
        access to attributes.
    """
    def __init__(self, element):
        # use element tag as object name
        setattr(self, 'name', element.tag)
        # set element attributes as object attributes
        for attr in element.attrib:
            setattr(self, attr, element.attrib[attr])
        # iterate over element children, set these as attributes which nest further PDXData objects
        for child in list(element):
            child_data = type(self)(child)
            setattr(self, child.tag, child_data)

    def __str__(self):
        string = list()
        for k, v in self.__dict__.iteritems():
            string.append('{}: {}'.format(k, v))
        return '\n'.join(string)


""" ================================================================================================
    Functions for reading and parsing binary data.
====================================================================================================
"""


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

    return prop_name, prop_values, pos


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

    return obj_name, objdepth, pos


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

    return datavalues, pos


def read_meshfile(filepath, to_stdout=False):
    """
        Reads through a .mesh file and gathers all the data into hierarchical element structure.
        The resulting XML is not natively writable to string as it contains Python data types.
    """
    # read the data
    with open(filepath, 'rb') as fp:
        fdata = fp.read()

    # create a ordered dictionary to store the object hierarchy
    file_element = Xml.Element('File')
    file_element.attrib = dict(
        name=os.path.split(filepath)[1],
        path=os.path.split(filepath)[0]
    )

    # determine the file length
    eof = len(fdata)
    # set position in file to skip '@@b@'
    if fdata[:4] == '@@b@':
        pos = 4
    else:
        raise NotImplementedError("Unknown file header.")

    parent_element = file_element
    depth_list = [file_element]
    current_depth = 0

    # parse through until EOF
    while pos < eof:
        # we have a property
        if struct.unpack('c', fdata[pos])[0] == '!':
            # check the property type and values
            prop_name, prop_values, pos = parseProperty(fdata, pos)
            if to_stdout:
                print "  "*current_depth+"  ", prop_name, " (count", len(prop_values), ")"

            # assign property values to the parent object
            parent_element.set(prop_name, prop_values)

        # we have an object
        elif struct.unpack('c', fdata[pos])[0] == '[':
            # check the object type and hierarchy depth
            obj_name, depth, pos = parseObject(fdata, pos)
            if to_stdout:
                print "  "*depth, obj_name, depth

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


""" ================================================================================================
    Functions for writing XML tree to binary data.
====================================================================================================
"""


def writeProperty(prop_name, prop_data):
    datastring = b''

    # write starting '!'
    datastring += struct.pack('c', '!')

    # write length of property name
    prop_name_length = len(prop_name)
    datastring += struct.pack('b', prop_name_length)

    # write property name as string
    datastring += writeString(prop_name)

    # write property data
    datastring += writeData(prop_data)

    return datastring


def writeObject(obj_xml, obj_depth):
    datastring = b''

    # write object hierarchy depth
    datastring += struct.pack('c'*obj_depth, *'['*obj_depth)

    # write object name as string
    obj_name = obj_xml.tag
    datastring += writeString(obj_name)
    # write ending zero byte
    datastring += struct.pack('b', 0)

    return datastring


def writeString(string):
    datastring = b''

    datastring += struct.pack('c'*len(string), *string)

    # TODO: pad the string with zero bytes to boundary?
    # write ending zero byte
    # datastring += struct.pack('b', 0)

    return datastring


def writeData(data_array):
    datastring = b''

    # determine the data type in the array
    types = set([type(d) for d in data_array])
    if len(types) == 1:
        datatype = types.pop()
    else:
        raise NotImplementedError("Mixed data type encountered.")

    if datatype == int:
        # write the data type
        datastring += struct.pack('c', 'i')

        # write the data count
        size = len(data_array)
        datastring += struct.pack('i', size)

        # write the data values
        datastring += struct.pack('i'*size, *data_array)

    elif datatype == float:
        datastring += struct.pack('c', 'f')

        # count
        size = len(data_array)
        datastring += struct.pack('i', size)

        # values
        datastring += struct.pack('f'*size, *data_array)

    elif datatype == str:
        datastring += struct.pack('c', 's')

        # data count
        size = 1
        # TODO: we are assuming that we always have a count of 1 string, not an array of multiple strings
        datastring += struct.pack('i', size)

        # string length
        str_data_length = len(data_array[0])
        datastring += struct.pack('i', str_data_length)

        # values
        datastring += struct.pack('c'*str_data_length, *data_array[0])

    else:
        raise NotImplementedError("Unknown data type encountered.")

    return datastring


def write_meshfile(filepath, root_xml):
    """
        Iterates over an XML element and writes the hierarchical element structure to binary file.
    """
    datastring = b''

    # write the file header '@@b@'
    header = '@@b@'
    datastring += struct.pack('c'*len(header), *header)

    # write the file properties
    if root_xml.tag == 'File':
        datastring += writeProperty('pdxasset', root_xml.get('pdxasset'))
    else:
        raise NotImplementedError("Unknown XML root encountered.")

    # TODO: writing properties would be easier if order was irrelevant, you should test this

    # write objects root
    object_xml = root_xml.find('object')
    if object_xml:
        current_depth = 1
        datastring += writeObject(object_xml, current_depth)

        # write each shape node
        for child_xml in object_xml:
            current_depth = 2
            datastring += writeObject(child_xml, current_depth)

            # write each mesh
            for mesh_xml in child_xml.findall('mesh'):
                current_depth = 3
                datastring += writeObject(mesh_xml, current_depth)

                # write mesh properties
                for prop in ['p', 'n', 'ta', 'u0', 'tri']:
                    if mesh_xml.get(prop) is not None:
                        datastring += writeProperty(prop, mesh_xml.get(prop))

                # write mesh sub-objects
                aabb_xml = mesh_xml.find('aabb')
                if aabb_xml is not None:
                    current_depth = 4
                    datastring += writeObject(aabb_xml, current_depth)
                    for prop in ['min', 'max']:
                        if aabb_xml.get(prop) is not None:
                            datastring += writeProperty(prop, aabb_xml.get(prop))

                material_xml = mesh_xml.find('material')
                if material_xml is not None:
                    current_depth = 4
                    datastring += writeObject(material_xml, current_depth)
                    for prop in ['shader', 'diff', 'n', 'spec']:
                        if material_xml.get(prop) is not None:
                            datastring += writeProperty(prop, material_xml.get(prop))

                skin_xml = mesh_xml.find('skin')
                if skin_xml is not None:
                    current_depth = 4
                    datastring += writeObject(skin_xml, current_depth)
                    for prop in ['bones', 'ix', 'w']:
                        if skin_xml.get(prop) is not None:
                            datastring += writeProperty(prop, skin_xml.get(prop))

    # write locators root
    locator_xml = root_xml.find('locator')
    if locator_xml:
        current_depth = 1
        datastring += writeObject(locator_xml, current_depth)

        # write each locator
        for child_xml in locator_xml:
            current_depth = 2
            datastring += writeObject(child_xml, current_depth)

            # write locator properties
            for prop in ['p', 'q', 'pa']:
                datastring += writeProperty(prop, child_xml.get(prop))

    # write the data
    with open(filepath, 'wb') as fp:
        fp.write(datastring)


""" ================================================================================================
    Main.
====================================================================================================
"""


if __name__ == '__main__':
    """
       When called as a script we just print the structure and contents of the mesh file to stdout
    """
    clear = lambda: os.system('cls')
    clear()
    _script_dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
    a_file = os.path.join(_script_dir, 'test files', 'archipelago_frigate.mesh')

    if len(sys.argv) > 1:
        a_file = sys.argv[1]

    data = read_meshfile(a_file)
    
    for elem in data.iter():
        print 'object', elem.tag
        for k, v in elem.items():
            print '    property', k, type(v)

    b_file = os.path.join(_script_dir, 'test files', 'test_write.mesh')
    write_meshfile(b_file, data)


"""
.mesh file format

General binary format is:
    data description
    data type
    depth of data
    data content

====================================================================================================
    header    (@@b@ for binary, @@t@ for text)?
    pdxasset    (int)  number of assets?
        object    (object)  parent item for all 3D objects
            shape    (object)
                ...  multiple shapes, used for meshes under different node transforms
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
====================================================================================================
"""
