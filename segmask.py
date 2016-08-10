#! /usr/bin/env python

import os
import re
import array
import glob
import sys
import fileinput
import pyimod
import numpy as np
from scipy import misc
from optparse import OptionParser
from subprocess import Popen, call, PIPE
from sys import stderr, exit, argv

def parse_args():
    global p
    p = OptionParser(usage = "%prog [options] file.mrc file.mod path_seg")
    p.add_option("--color",
                 dest = "color",
                 metavar = "R,G,B",
                 help = "Color to make all output objects, entered as a string "
                        "of comma-separated R, G, B values. E.g. ('1,0,0', "
                        "'0,1,1'). (Default: Turned off).")
    p.add_option("--filterByNContours",
                 dest = "filterByNContours",
                 metavar = "INT",
                 default = 0,
                 help = "Low threshold for object removal based on number "
                        "of contours. All objects containing a number of "
                        "contours less than or equal to the value entered "
                        "here will be removed. For example, if 3 is entered, "
                        "all objects with 3 or fewer contours will be deleted "
                        "and all objects with 4 or more contours will be "
                        "retained. (Default: Turned off).")
    p.add_option("--imodautor",
                 dest = "imodautor",
                 metavar = "FLOAT",
                 default = 0,
                 help = "Tolerance for point shaving when running imodauto. "
                        "The value specified here is used as input to the -R "
                        "flag of imodauto. Must range from 0-1. (Default: 0, "
                        "which means point shaving is turned off.")
    p.add_option("--imodautok",
                 dest = "imodautok",
                 metavar = "FLOAT",
                 default = 0,  
                 help = "Smooths the segmentation image with a kernel filter "
                        "whose Gaussian sigma is given by the specified value. "
                        "The value entered here is used as input to the -k flag "
                        "of imodauto. (Default: Turned off.")
    p.add_option("--mergeAll",
                 action = "store_true",
                 default = False,
                 dest = "mergeAll",
                 help = "Merges all output, masked objects into one final "
                        "object. This option is useful in cases where you want "
                        "to separate objects, filter them, and then rejoin. "
                        "(Default: False)")
    p.add_option("--name",
                 dest = "name",
                 metavar = "STRING",
                 help = "Name to assign to all output objects, entered as a "
                        "string. E.g. ('mitochondrion', 'nucleus'). (Default: "
                        "Turned off)")  
    p.add_option("--output",
                 dest = "path_out",
                 metavar = "PATH",
                 help = "Output path to save to (DEFAULT = Current directory.")
    p.add_option("--runImodfillin",
                 action = "store_true",
                 default = False,
                 dest = "runImodfillin",
                 help = "Runs imodfillin to interpolate missing contours in "
                        "file.mod before masking. The number of slices to skip "
                        "is specified by the flag --slicesToSkipCell. (Default: "
                        "False)") 
    p.add_option("--runPostprocessing",
                 action = "store_true",
                 default = False,
                 dest = "runPostprocessing",
                 help = "Runs postprocessing routine on the masked output. "
                        "First, imodmesh is run to mesh the entire output as "
                        "one object. Then, imodsortsurf is run to split the "
                        "meshed object into separate objects based on 3D conn- "
                        "ectivity. (Default: False)")
    p.add_option("--slicesToSkipCell",
                 dest = "slicesToSkipCell",
                 metavar = "INT",
                 default = 10,
                 help = "Number of slices to skip when interpolating missing "
                        "contours of the cell trace with imodfillin. The value "
                        "specified here is used as input to the -P flag in "
                        "imodmesh. (Default: 10)")
    p.add_option("--slicesToSkipOrganelle",
                 dest = "slicesToSkipOrganelle",
                 metavar = "INT",
                 default = 4,
                 help = "Number of slices to skep when meshing the final, "
                        "masked results. The value specified here is used as "
                        "input to the -P flag in imodmesh. (Default: 4)")
    (opts, args) = p.parse_args()
    file_mrc, file_mod, path_seg = check_args(args)
    return opts, file_mrc, file_mod, path_seg

def check_args(args):
    if len(args) is not 3:
        usage('Improper number of arguments.')
    file_mrc = args[0]
    file_mod = args[1]
    path_seg = args[2]
    if not os.path.isfile(file_mrc):
        usage('{} is not a valid file.'.format(file_mrc))
    if not os.path.isfile(file_mod):
        usage('{} is not a valid file.'.format(file_mod))
    if not os.path.isdir(path_seg):
        usage('The path {} does not exist'.format(path_seg))
    return file_mrc, file_mod, path_seg

def get_z_from_ImodContour(cont):
    """
    Returns the Z value of a given ImodContour object. If the contour has more
    than one Z value, returns the mode of the list of all Z values and prints
    a warning message. 
    """
    cont_u = np.unique([int(x) for x in cont.points[2::3]])
    if len(cont_u == 1):
        uq = cont_u[0]
    else:
        uq = max(set(cont_u), key = list.count)
        print 'WARNING: Contour has more than one Z value. Selecting the ' \
            'most common Z value.' 
    return uq

def usage(errstr):
    print ""
    p.print_help()
    print ""
    print "ERROR: {}".format(errstr)
    print ""
    exit(1)

if __name__ == "__main__":
    opts, file_mrc, file_mod, path_seg = parse_args()

    # Set and check the output directory
    if opts.path_out:
        path_out = opts.path_out
    else:
        path_out = os.getcwd()
    if not os.path.isdir(path_out):
        usage("The output path {} does not exist.".format(path_out))

    # Create temporary directory in the output path
    path_tmp = os.path.join(path_out, "tmp")
    if os.path.isdir(path_tmp):
        usage("There is already a folder with the name tmp in the output "
              "path {}".format(path_out))
    os.makedirs(path_tmp)

    # Load cell model file in PyIMOD
    print 'Loading IMOD model file {}'.format(file_mod)
    mod = pyimod.ImodModel(file_mod)

    # Run imodfillin, if desired. First, existing mesh data is removed and
    # replaced with a new mesh obtained by skipping across a number of slices,
    # specified by the optional argument --slicesToSkipCell. Imodfillin is then 
    # run with the -e flag, so that contours are appended to the existing
    # object. 
    if opts.runImodfillin:
        print 'Running imodmesh/imodfillin...'
        print '# Contours before: {}'.format(mod.Objects[0].nContours)
        mod = pyimod.utils.ImodCmd(mod, 'imodmesh -e')
        mod = pyimod.utils.ImodCmd(mod,
            'imodmesh -CTs -P {}'.format(opts.slicesToSkipCell))
        mod = pyimod.utils.ImodCmd(mod, 'imodfillin -e') 
        print '# Contours after: {}'.format(mod.Objects[0].nContours)

    # Remove small contours and sort contours
    print 'Removing small contours and reordering...'
    print '# Contours before: {}'.format(mod.Objects[0].nContours)
    mod.removeSmallContours()
    mod.Objects[0].sortContours()
    print '# Contours after: {}'.format(mod.Objects[0].nContours)

    # Get the minimum and maximum slice values of the cell trace 
    zmin = get_z_from_ImodContour(mod.Objects[0].Contours[0])
    zmax = get_z_from_ImodContour(mod.Objects[0].Contours[-1])
    print 'Z min: {}'.format(zmin)
    print 'Z max: {}'.format(zmax)

    # Check that all slices between zmin and zmax have a contour. If not,
    # continue with the process, but print a warning message.
    zprev = zmin
    zlist = []
    for iCont in range(mod.Objects[0].nContours):
        zi = get_z_from_ImodContour(mod.Objects[0].Contours[iCont])
        print 'Contour: {0}, Z: {1}'.format(iCont+1, zi) 
        if iCont and zi != (zprev + 1):
            print 'WARNING: Missing contour'
        zlist.append(zi)
        zprev = zi
    print zlist

    # Get number of slices in MRC file 
    dims = pyimod.mrc.get_dims(file_mrc)
    nColMrc = int(dims[0])
    nRowMrc = int(dims[1])
    nslices = int(dims[2])

    # Get list of all segmented organelle files
    filesOrg = sorted(glob.glob(os.path.join(path_seg , '*')))
    print filesOrg

    # Write edited model file to disk
    file_cell = os.path.join(path_tmp, 'cell.mod')
    pyimod.ImodWrite(mod, file_cell)
 
    # Loop over all Z values in the cell trace 
    C = 0
    for zi in zlist:
        print 'Processing Z = {}'.format(zi) 
        # Create a TIF image of the cell mask. This is done by first using
        # imodmop to mask the cell, and then convert it to TIF using mrc2tif. 
        file_tmp = os.path.join(path_tmp, str(zi).zfill(4))
        cmd = 'imodmop -mask 1 -zminmax {0},{0} {1} {2} {3}'.format(zi,
            file_cell, file_mrc, file_tmp + '.mrc')
        print cmd
        call(cmd.split())
        cmd = 'mrc2tif {0} {1}'.format(file_tmp + '.mrc', file_tmp + '.tif')
        print cmd
        call(cmd.split())
        os.remove(file_tmp + '.mrc')

        # Read cell mask image to numpy array
        imgCell = misc.imread(file_tmp + '.tif') 

        # Read the organelle segmentation image to a numpy array 
        imgOrg = misc.imread(filesOrg[zi - 1])
    
        # Resize images, if necessary.
        if (imgCell.shape[0] != nRowMrc) or (imgCell.shape[1] != nColMrc):        
            imgCell = misc.imresize(imgOrg, [nRowMrc, nColMrc])

        if (imgOrg.shape[0] != nRowMrc) or (imgOrg.shape[1] != nColMrc):
            imgOrg = misc.imresize(imgOrg, [nRowMrc, nColMrc])

        # Find the intersection of imgOrg and imgCell. Write this image file.
        imgMask = np.logical_and(imgCell, imgOrg)
        imgMask.astype('uint8')
        misc.imsave(file_tmp + '.tif', imgMask) 

        # Run imodauto. First, construct a string of options based upon the 
        # user input from flags. 
        iastr = '-E 255 -u -R {0}'.format(opts.imodautor)
        if opts.imodautok:
            iastr += ' -k {}'.format(opts.imodautok) 
        cmd = 'imodauto {0} {1} {2}'.format(iastr, file_tmp + '.tif',
            file_tmp + '.mod')
        print cmd
        call(cmd.split())
        os.remove(file_tmp + '.tif')

        # Translate the imodauto results in z so they match the correct slice
        cmd = 'imodtrans -tz {0} {1} {1}'.format(zi - 1, file_tmp + '.mod')
        call(cmd.split())
        os.remove(file_tmp + '.mod~')  

        # Convert the translated model to a point listing compatible with
        # model2point
        cmd = 'model2point -object {0} {1}'.format(file_tmp + '.mod',
            file_tmp + '.txt')   
        print cmd
        call(cmd.split())
        os.remove(file_tmp + '.mod')

        # Append to growing file of point listings
        file_out = os.path.join(path_tmp, 'out')
        if not os.stat(file_tmp + '.txt').st_size == 0:
            with open(file_tmp + '.txt') as fid:
                lastline = (list(fid)[-1])
            fid.close()
            ncont = int(lastline.split()[1])
            with open(file_out + '.txt', 'a+') as outfile:
                with open(file_tmp + '.txt', 'r+') as infile:
                    for line in infile:
                        lsplit = line.split()
                        newline = '1 {0} {1} {2} {3}\n'.format(int(lsplit[1]) + C,
                            lsplit[2], lsplit[3], lsplit[4])
                        outfile.write(newline)
            C = C + ncont    
        os.remove(file_tmp + '.txt') 
    os.remove(file_cell)

    # Convert point listing to final model file
    cmd = 'point2model -image {0} {1} {2}'.format(file_mrc, file_out + '.txt',
        file_out + '.mod')
    print cmd
    call(cmd.split()) 

    # Run postprocessing, if necessary
    if opts.runPostprocessing:
        mod = pyimod.ImodModel(file_out + '.mod')       
 
        # Remove existing mesh information
        mod = pyimod.utils.ImodCmd(mod, 'imodmesh -e')

        # Remesh
        mod = pyimod.utils.ImodCmd(mod,
            'imodmesh -CTs -P {}'.format(opts.slicesToSkipOrganelle))

        # Run imodsortsurf
        mod = pyimod.utils.ImodCmd(mod, 'imodsortsurf -s')

        # Filter objects by number of contours, if necessary
        if opts.filterByNContours:
            mod.filterByNContours('>', int(opts.filterByNContours))

        # Merge objects, if necessary
        if opts.mergeAll:
            mod.moveObjects(1, '2-{}'.format(mod.nObjects))

        # Remesh
        mod = pyimod.utils.ImodCmd(mod, 'imodmesh -e')
        mod = pyimod.utils.ImodCmd(mod, 
            'imodmesh -CTs -P {}'.format(opts.slicesToSkipOrganelle))   

        # Set name and color across all objects, if necessary
        if opts.color:
            mod.setAll(color = opts.color)
        if opts.name:
            mod.setAll(name = opts.name)

        # Write output
        pyimod.ImodWrite(mod, file_out + '_postprocessed.mod')   

