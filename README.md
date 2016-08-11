[numpy]: http://www.numpy.org/
[scipy]: https://www.scipy.org/
[pyimod]: https://github.com/CRBS/PyIMOD
[imod]:http://bio3d.colorado.edu/imod/

# segmask

Given an input IMOD model file, MRC file, and a stack of segmentation images with the same dimensions as the MRC file, **segmask** will produce an output IMOD model file consisting of all segmented objects contained within the boundary of the input IMOD model file. This is most often used to create a model file consisting of all segmented organelles contained within a manually segmented cell boundary.

Scripts are also provided to run **segmask** on a cluster with SGE. In this way, numerous masks can be generated in parallel by submission of an array job.

### Requirements
* Python 2.7
* [Numpy][numpy]
* [Scipy][scipy]
* [PyIMOD][pyimod]
* [IMOD][imod]

### Example Usage
To run using a single IMOD mask model file:

    segmask/segmask.py input.mrc input_mask.mod /path/to/segmentation/stack

To submit a SGE array job with numerous masks on a cluster:

    segmask/grid/run_segmask.sh input.mrc /path/to/mask/files /path/to/segmentation/stack

