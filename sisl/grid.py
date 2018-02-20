from __future__ import print_function, division

from numbers import Integral, Real
from math import pi

import numpy as np
from numpy import int32, float64
from numpy import floor, dot, add, cos, sin
from numpy import ogrid, stack, take

from ._help import ensure_array
import sisl._array as _a
from .shape import Shape
from .utils import default_ArgumentParser, default_namespace
from .utils import cmd, strseq, direction
from .utils import array_arange
from .supercell import SuperCellChild
from .atom import Atom
from .geometry import Geometry

__all__ = ['Grid', 'sgrid']


class Grid(SuperCellChild):
    """ Real-space grid information with associated geometry.

    This grid object handles cell vectors and divisions of said grid.

    Parameters
    ----------
    shape : float or (3,) of int
        the shape of the grid. A ``float`` specifies the grid spacing in Angstrom, while
        a list of integers specifies the exact grid size.
    bc : list of int (3, 2) or (3, ), optional
        the boundary conditions for each of the cell's planes. Default to periodic BC.
    sc : SuperCell, optional
        the supercell that this grid represents. `sc` has precedence if both `geom` and `sc`
        has been specified. Default to ``[1, 1, 1]``.
    dtype : numpy.dtype, optional
        the data-type of the grid, default to `numpy.float64`.
    geom : Geometry, optional
        associated geometry with the grid. If `sc` has not been passed the supercell will
        be taken from this geometry.
    """

    #: Constant for defining a periodic boundary condition
    PERIODIC = 1
    #: Constant for defining a Neumann boundary condition
    NEUMANN = 2
    #: Constant for defining a Dirichlet boundary condition
    DIRICHLET = 3
    #: Constant for defining an open boundary condition
    OPEN = 4

    def __init__(self, shape, bc=None, sc=None, dtype=None, geom=None):
        """ Initialize a `Grid` object.

        Initialize a `Grid` object.

        Parameters
        ----------
        shape : list of ints or float
           the size of each grid dimension, if a float it is the grid-spacing in Ang
        bc : int or list of int, optional
           the boundary condition (`Grid.PERIODIC`/`Grid.NEUMANN`/`Grid.DIRICHLET`/`Grid.OPEN`).
           This should be a (3, 2) list of values corresponding to each grid-direction.
           The first/second value for each direction is the lower/upper part of the grid.
        sc : SuperCell or list, optional
           the associated supercell
        """
        if bc is None:
            bc = [[self.PERIODIC] * 2] * 3

        self.set_supercell(sc)

        # Create the atomic structure in the grid, if possible
        self.set_geometry(geom)

        if isinstance(shape, Real):
            d = (self.cell ** 2).sum(1) ** 0.5
            shape = list(map(int, np.rint(d / shape)))

        # Create the grid
        self.set_grid(shape, dtype=dtype)

        # Create the grid boundary conditions
        self.set_bc(bc)

        # If the user sets the super-cell, that has precedence.
        if sc is not None:
            self.geom.set_sc(sc)
            self.set_sc(sc)

    def __getitem__(self, key):
        """ Returns the grid contained """
        return self.grid[key]

    def __setitem__(self, key, val):
        """ Updates the grid contained """
        self.grid[key] = val

    @property
    def geom(self):
        return self.geometry

    def set_geometry(self, geometry):
        """ Sets the `Geometry` for the grid.

        Setting the `Geometry` for the grid is a possibility
        to attach atoms to the grid.

        It is not a necessary entity.
        """
        if geometry is None:
            # Fake geometry
            self.set_geometry(Geometry([0, 0, 0], Atom['H'], sc=self.sc))
        else:
            self.geometry = geometry
            self.set_sc(geometry.sc)
    set_geom = set_geometry

    def fill(self, val):
        """ Fill the grid with this value

        Parameters
        ----------
        val : numpy.dtype
           all grid-points will have this value after execution
        """
        self.grid.fill(val)

    def interp(self, shape, method='linear', **kwargs):
        """ Returns an interpolated version of the grid

        Parameters
        ----------
        shape : int, array_like
            the new shape of the grid
        method : str
            the method used to perform the interpolation,
            see `scipy.interpolate.interpn` for further details.
        **kwargs :
            optional arguments passed to the interpolation algorithm
            The interpolation routine is `scipy.interpolate.interpn`
        """
        # Get current grid spacing
        dold = (
            np.linspace(0, 1, self.shape[0]),
            np.linspace(0, 1, self.shape[1]),
            np.linspace(0, 1, self.shape[2])
        )

        # Interpolate
        from scipy.interpolate import interpn

        # Create new grid
        grid = self.__class__(shape, bc=np.copy(self.bc), sc=self.sc.copy())
        # Clean-up to reduce memory
        del grid.grid

        # Create new mesh-grid
        dnew = np.concatenate(np.meshgrid(
            np.linspace(0, 1, shape[0]),
            np.linspace(0, 1, shape[1]),
            np.linspace(0, 1, shape[2])), axis=0)
        dnew.shape = (-1, 3)

        grid.grid = interpn(dold, self.grid, dnew, method=method, **kwargs)
        # immediately delete the dnew (which is VERY large)
        del dold, dnew
        # Ensure that the grid has the correct shape
        grid.grid.shape = tuple(shape)

        return grid

    @property
    def size(self):
        """ Returns size of the grid """
        return np.prod(self.grid.shape)

    @property
    def shape(self):
        """ Returns the shape of the grid """
        return self.grid.shape

    @property
    def dtype(self):
        """ Returns the data-type of the grid """
        return self.grid.dtype

    @property
    def dkind(self):
        """ The data-type of the grid (in str) """
        return np.dtype(self.grid.dtype).kind

    def set_grid(self, shape, dtype=None):
        """ Create the internal grid of certain size. """
        shape = ensure_array(shape).ravel()
        if dtype is None:
            dtype = np.float64
        self.grid = np.zeros(shape, dtype=dtype)

    def set_bc(self, boundary=None, a=None, b=None, c=None):
        """ Set the boundary conditions on the grid

        Parameters
        ----------
        boundary: (3, 2) or (3, ) or int, optional
           boundary condition for all boundaries (or the same for all)
        a: int or list of int, optional
           boundary condition for the first unit-cell vector direction
        b: int or list of int, optional
           boundary condition for the second unit-cell vector direction
        c: int or list of int, optional
           boundary condition for the third unit-cell vector direction

        Raises
        ------
        ValueError : if specifying periodic one one boundary, so must the opposite side.
        """
        if not boundary is None:
            if isinstance(boundary, Integral):
                self.bc = _a.arrayi([[boundary] * 2] * 3)
            else:
                self.bc = _a.asarrayi(boundary)
        if not a is None:
            self.bc[0, :] = a
        if not b is None:
            self.bc[1, :] = b
        if not c is None:
            self.bc[2, :] = c

        # shorthand for bc
        bc = self.bc[:, :]
        for i in range(3):
            if (bc[i, 0] == self.PERIODIC and bc[i, 1] != self.PERIODIC) or \
               (bc[i, 0] != self.PERIODIC and bc[i, 1] == self.PERIODIC):
                raise ValueError(self.__class__.__name__ + '.set_bc has a one non-periodic and '
                                 'one periodic direction. If one direction is periodic, both instances '
                                 'must have that BC.')

    # Aliases
    set_boundary = set_bc
    set_boundary_condition = set_bc

    def copy(self):
        """ Returns a copy of the object. """
        grid = self.__class__(np.copy(self.shape), bc=np.copy(self.bc),
                              dtype=self.dtype, geom=self.geom.copy())
        grid.grid = self.grid.copy()
        return grid

    def swapaxes(self, a, b):
        """ Returns Grid with swapped axis

        If ``swapaxes(0,1)`` it returns the 0 in the 1 values.
        """
        # Create index vector
        idx = _a.arangei(3)
        idx[b] = a
        idx[a] = b
        s = np.copy(self.shape)
        grid = self.__class__(s[idx], bc=self.bc[idx],
                              sc=self.sc.swapaxes(a, b), dtype=self.dtype,
                              geom=self.geom.copy())
        # We need to force the C-order or we loose the contiguity
        grid.grid = np.copy(np.swapaxes(self.grid, a, b), order='C')
        return grid

    @property
    def dcell(self):
        """ Returns the delta-cell """
        # Calculate the grid-distribution
        shape = ensure_array(self.shape).reshape(1, -3)
        return self.cell / shape

    @property
    def dvolume(self):
        """ Volume of the grids voxel elements """
        return self.sc.volume / self.size

    def cross_section(self, idx, axis):
        """ Takes a cross-section of the grid along axis `axis`

        Remark: This API entry might change to handle arbitrary
        cuts via rotation of the axis """
        idx = ensure_array(idx).flatten()
        # First calculate the new shape
        shape = list(self.shape)
        cell = np.copy(self.cell)
        # Down-scale cell
        cell[axis, :] /= shape[axis]
        shape[axis] = 1
        grid = self.__class__(shape, bc=np.copy(self.bc), geom=self.geom.copy())
        # Update cell shape (the cell is smaller now)
        grid.set_sc(cell)

        if axis == 0:
            grid.grid[:, :, :] = self.grid[idx, :, :]
        elif axis == 1:
            grid.grid[:, :, :] = self.grid[:, idx, :]
        elif axis == 2:
            grid.grid[:, :, :] = self.grid[:, :, idx]
        else:
            raise ValueError('Unknown axis specification in cross_section')

        return grid

    def sum(self, axis):
        """ Returns the grid summed along axis `axis`. """
        # First calculate the new shape
        shape = list(self.shape)
        cell = np.copy(self.cell)
        # Down-scale cell
        cell[axis, :] /= shape[axis]
        shape[axis] = 1

        grid = self.__class__(shape, bc=np.copy(self.bc), geom=self.geom.copy())
        # Update cell shape (the cell is smaller now)
        grid.set_sc(cell)

        # Calculate sum (retain dimensions)
        np.sum(self.grid, axis=axis, keepdims=True, out=grid.grid)
        return grid

    def average(self, axis):
        """ Returns the average grid along direction `axis` """
        n = self.shape[axis]
        g = self.sum(axis)
        g /= float(n)
        return g

    # for compatibility
    mean = average

    def remove_part(self, idx, axis, above):
        """ Removes parts of the grid via above/below designations.

        Works exactly opposite to `sub_part`

        Parameters
        ----------
        idx : array_like
           the indices of the grid axis `axis` to be removed
           for ``above=True`` grid[:idx,...]
           for ``above=False`` grid[idx:,...]
        axis : int
           the axis segment from which we retain the indices `idx`
        above: bool
           if ``True`` will retain the grid:
              ``grid[:idx,...]``
           else it will retain the grid:
              ``grid[idx:,...]``
        """
        return self.sub_part(idx, axis, not above)

    def sub_part(self, idx, axis, above):
        """ Retains parts of the grid via above/below designations.

        Works exactly opposite to `remove_part`

        Parameters
        ----------
        idx : array_like
           the indices of the grid axis `axis` to be retained
           for ``above=True`` grid[idx:,...]
           for ``above=False`` grid[:idx,...]
        axis : int
           the axis segment from which we retain the indices `idx`
        above: bool
           if ``True`` will retain the grid:
              ``grid[idx:,...]``
           else it will retain the grid:
              ``grid[:idx,...]``
        """
        if above:
            sub = _a.arangei(idx, self.shape[axis])
        else:
            sub = _a.arangei(0, idx)
        return self.sub(sub, axis)

    def sub(self, idx, axis):
        """ Retains certain indices from a specified axis.

        Works exactly opposite to `remove`.

        Parameters
        ----------
        idx : array_like
           the indices of the grid axis `axis` to be retained
        axis : int
           the axis segment from which we retain the indices `idx`

        Raises
        ------
        ValueError : if the length of the indices is 0
        """
        idx = ensure_array(idx).flatten()

        # Calculate new shape
        shape = list(self.shape)
        cell = np.copy(self.cell)
        old_N = shape[axis]

        # Calculate new shape
        shape[axis] = len(idx)
        if shape[axis] < 1:
            raise ValueError('You cannot retain no indices.')

        # Down-scale cell
        cell[axis, :] = cell[axis, :] / old_N * shape[axis]

        grid = self.__class__(shape, bc=np.copy(self.bc), geom=self.geom.copy())
        # Update cell shape (the cell is smaller now)
        grid.set_sc(cell)

        # Remove the indices
        # First create the opposite, index
        if axis == 0:
            grid.grid[:, :, :] = self.grid[idx, :, :]
        elif axis == 1:
            grid.grid[:, :, :] = self.grid[:, idx, :]
        elif axis == 2:
            grid.grid[:, :, :] = self.grid[:, :, idx]

        return grid

    def remove(self, idx, axis):
        """ Removes certain indices from a specified axis.

        Works exactly opposite to `sub`.

        Parameters
        ----------
        idx : array_like
           the indices of the grid axis `axis` to be removed
        axis : int
           the axis segment from which we remove all indices `idx`
        """
        ret_idx = np.delete(_a.arangei(self.shape[axis]), ensure_array(idx))
        return self.sub(ret_idx, axis)

    def _index_shape(self, shape):
        """ Internal routine for shape-indices """
        # First grab the sphere, subsequent indices will be reduced
        # by the actual shape
        sphere = shape.toSphere()
        R = sphere.radius[0]

        # Figure out the max-min indices with a spacing of 1 radians
        rad1 = pi / 180
        theta, phi = ogrid[-pi:pi:rad1, 0:pi:rad1]
        nrxyz = (theta.size, phi.size, 3)

        rxyz = _a.emptyd(nrxyz)
        rxyz[..., 2] = R * cos(phi) + sphere.center[2]
        sin(phi, out=phi)
        rxyz[..., 0] = R * cos(theta) * phi + sphere.center[0]
        rxyz[..., 1] = R * sin(theta) * phi + sphere.center[1]
        del theta, phi, nrxyz

        # Get all indices of the spherical circumference
        idx = self.index(rxyz)
        del rxyz

        # Get min/max
        idx_min = idx.min(0)
        idx_max = idx.max(0)
        del idx

        dc = self.dcell

        # Now to find the actual points inside the shape
        # First create all points in the square and then retrieve all indices
        # within.
        # TODO, see if we can optimize this a bit.
        addouter = add.outer
        ix = _a.aranged(idx_min[0], idx_max[0] + 0.5)
        iy = _a.aranged(idx_min[1], idx_max[1] + 0.5)
        iz = _a.aranged(idx_min[2], idx_max[2] + 0.5)
        output_shape = (ix.size, iy.size, iz.size, 3)
        rx = addouter(addouter(ix * dc[0, 0], iy * dc[1, 0]), iz * dc[2, 0])
        ry = addouter(addouter(ix * dc[0, 1], iy * dc[1, 1]), iz * dc[2, 1])
        rz = addouter(addouter(ix * dc[0, 2], iy * dc[1, 2]), iz * dc[2, 2])
        rxyz = _a.emptyd(output_shape)
        rxyz[:, :, :, 0] = rx
        rxyz[:, :, :, 1] = ry
        rxyz[:, :, :, 2] = rz
        del rx, ry, rz
        idx = shape.within_index(rxyz.reshape(-1, 3))
        del rxyz
        i = _a.emptyi(output_shape)
        i[:, :, :, 0] = ix.reshape(-1, 1, 1)
        i[:, :, :, 1] = iy.reshape(1, -1, 1)
        i[:, :, :, 2] = iz.reshape(1, 1, -1)
        del ix, iy, iz
        i.shape = (-1, 3)
        i = take(i, idx, axis=0)
        del idx

        return i

    def index(self, coord, axis=None):
        """ Returns the index along axis `axis` where `coord` exists

        Parameters
        ----------
        coord : (*, 3) or float or Shape
            the coordinate of the axis. If a float is passed `axis` is
            also required in which case it corresponds to the length along the
            lattice vector corresponding to `axis`.
            If a Shape a list of coordinates that fits the voxel positions
            are returned (all internal points also).
        axis : int
            the axis direction of the index
        """
        if isinstance(coord, Shape):
            # We have to do something differently
            return self._index_shape(coord)

        rcell = self.rcell / (2 * np.pi)

        coord = ensure_array(coord, float64)
        if coord.size == 1: # float
            if axis is None:
                raise ValueError(self.__class__.__name__ + '.index requires the '
                                 'coordinate to be 3 values when an axis has not '
                                 'been specified.')

            c = (self.dcell[axis, :] ** 2).sum() ** 0.5
            return int(floor(coord[0] / c))

        # Ensure we return values in the same dimensionality
        ndim = coord.ndim
        coord.shape = (-1, 3)

        shape = np.array(self.shape).reshape(3, -1)

        # dot(rcell / 2pi, coord) is the fraction in the
        # cell. So * l / (l / self.shape) will
        # give the float of dcell lattice vectors (where l is the length of
        # each lattice vector)
        if axis is None:
            if ndim == 1:
                return floor(dot(rcell, coord.T) * shape).astype(int32).reshape(3)
            else:
                return floor(dot(rcell, coord.T) * shape).T.astype(int32)
        if ndim == 1:
            return floor(dot(rcell[axis, :], coord.T) * shape[axis]).astype(int32)[0]
        else:
            return floor(dot(rcell[axis, :], coord.T) * shape[axis]).T.astype(int32)

    def append(self, other, axis):
        """ Appends other `Grid` to this grid along axis """
        shape = list(self.shape)
        shape[axis] += other.shape[axis]
        return self.__class__(shape, bc=np.copy(self.bc),
                              geom=self.geom.append(other.geom, axis))

    @staticmethod
    def read(sile, *args, **kwargs):
        """ Reads grid from the `Sile` using `read_grid`

        Parameters
        ----------
        sile : Sile, str
            a `Sile` object which will be used to read the grid
            if it is a string it will create a new sile using `get_sile`.
        * : args passed directly to ``read_grid(,**)``
        """
        # This only works because, they *must*
        # have been imported previously
        from sisl.io import get_sile, BaseSile
        if isinstance(sile, BaseSile):
            return sile.read_grid(*args, **kwargs)
        else:
            with get_sile(sile) as fh:
                return fh.read_grid(*args, **kwargs)

    def write(self, sile, *args, **kwargs):
        """ Writes grid to the `Sile` using `write_grid`

        Parameters
        ----------
        sile : Sile, str
            a `Sile` object which will be used to write the grid
            if it is a string it will create a new sile using `get_sile`
        """

        # This only works because, they *must*
        # have been imported previously
        from sisl.io import get_sile, BaseSile
        if isinstance(sile, BaseSile):
            sile.write_grid(self, *args, **kwargs)
        else:
            with get_sile(sile, 'w') as fh:
                fh.write_grid(self, *args, **kwargs)

    def __repr__(self):
        """ Representation of object """
        return self.__class__.__name__ + '{{kind={kind}, [{} {} {}]}}'.format(*self.shape, kind=self.dkind)

    def _check_compatibility(self, other, msg):
        """ Internal check for asserting two grids are commensurable """
        if self == other:
            return True
        s1 = repr(self)
        s2 = repr(other)
        raise ValueError('Grids are not compatible, ' +
                         s1 + '-' + s2 + '. ', msg)

    def _compatible_copy(self, other, *args, **kwargs):
        """ Returns a copy of self with an additional check of commensurable """
        if isinstance(other, Grid):
            self._check_compatibility(other, *args, **kwargs)
        return self.copy()

    def __eq__(self, other):
        """ Returns true if the two grids are commensurable

        There will be no check of the values _on_ the grid. """
        return self.shape == other.shape

    def __ne__(self, other):
        """ Returns whether two grids have the same shape """
        return not (self == other)

    def __abs__(self):
        r""" Return the absolute value :math:`|grid|` """
        dtype = self.dtype
        if dtype == np.complex128:
            dtype = np.float64
        elif dtype == np.complex64:
            dtype = np.float32
        a = self.copy()
        a.grid = np.absolute(self.grid).astype(dtype, copy=False)
        return a

    def __add__(self, other):
        """ Returns a new grid with the addition of two grids

        Returns same shape with same cell as the first
        """
        if isinstance(other, Grid):
            grid = self._compatible_copy(other, 'they cannot be added')
            grid.grid = self.grid + other.grid
        else:
            grid = self.copy()
            grid.grid = self.grid + other
        return grid

    def __iadd__(self, other):
        """ Returns a new grid with the addition of two grids

        Returns same shape with same cell as the first
        """
        if isinstance(other, Grid):
            self._check_compatibility(other, 'they cannot be added')
            self.grid += other.grid
        else:
            self.grid += other
        return self

    def __sub__(self, other):
        """ Returns a new grid with the difference of two grids

        Returns same shape with same cell as the first
        """
        if isinstance(other, Grid):
            grid = self._compatible_copy(other, 'they cannot be subtracted')
            np.subtract(self.grid, other.grid, out=grid.grid)
        else:
            grid = self.copy()
            np.subtract(self.grid, other, out=grid.grid)
        return grid

    def __isub__(self, other):
        """ Returns a same grid with the difference of two grids

        Returns same shape with same cell as the first
        """
        if isinstance(other, Grid):
            self._check_compatibility(other, 'they cannot be subtracted')
            self.grid -= other.grid
        else:
            self.grid -= other
        return self

    def __div__(self, other):
        return self.__truediv__(other)

    def __idiv__(self, other):
        return self.__itruediv__(other)

    def __truediv__(self, other):
        if isinstance(other, Grid):
            grid = self._compatible_copy(other, 'they cannot be divided')
            np.divide(self.grid, other.grid, out=grid.grid)
        else:
            grid = self.copy()
            np.divide(self.grid, other, out=grid.grid)
        return grid

    def __itruediv__(self, other):
        if isinstance(other, Grid):
            self._check_compatibility(other, 'they cannot be divided')
            self.grid /= other.grid
        else:
            self.grid /= other
        return self

    def __mul__(self, other):
        if isinstance(other, Grid):
            grid = self._compatible_copy(other, 'they cannot be multiplied')
            np.multiply(self.grid, other.grid, out=grid.grid)
        else:
            grid = self.copy()
            np.multiply(self.grid, other, out=grid.grid)
        return grid

    def __imul__(self, other):
        if isinstance(other, Grid):
            self._check_compatibility(other, 'they cannot be multiplied')
            self.grid *= other.grid
        else:
            self.grid *= other
        return self

    # Here comes additional supplementary routines which enables an easy
    # work-through case with other programs.
    def mgrid(self, *slices):
        """ Return a list of indices corresponding to the slices

        The returned values are equivalent to `numpy.mgrid` but they are returned
        in a (*, 3) array.

        Parameters
        ----------
        *slices : slice or list of int or int
            return a linear list of indices that points to the collective slice
            made by the passed arguments

        Returns
        -------
        indices : (*, 3), linear indices for each of the sliced values
        """
        if len(slices) == 1:
            g = np.mgrid[slices[0]]
        else:
            g = np.mgrid[slices]
        indices = _a.emptyi(g.size).reshape(-1, 3)
        indices[:, 0] = g[0].flatten()
        indices[:, 1] = g[1].flatten()
        indices[:, 2] = g[2].flatten()
        del g
        return indices

    def pyamg_index(self, index):
        r""" Calculate `pyamg` matrix indices from a list of grid indices

        Parameters
        ----------
        index : (*,3) of int
            a list of indices of the grid along each grid axis

        Returns
        -------
        pyamg linear indices for the matrix

        See Also
        --------
        index : query indices from coordinates (directly passable to this method)
        mgrid : Grid equivalent to `numpy.mgrid`. Grid.mgrid returns indices in shapes (*, 3), contrary to numpy's `numpy.mgrid`

        Raises
        ------
        ValueError : if any of the passed indices are below 0 or above the number of elements per axis
        """
        index = ensure_array(index).reshape(-1, 3)
        grid = _a.arrayi(self.shape[:])
        if np.any(index < 0) or np.any(index >= grid.reshape(1, 3)):
            raise ValueError(self.__class__.__name__ + '.pyamg_index erroneous values for grid indices')
        # Skipping factor per element
        cp = _a.arrayi([[grid[1] * grid[2], grid[2], 1]])
        return (cp * index).sum(1)

    def pyamg_source(self, b, pyamg_indices, value):
        r""" Fix the source term to `value`.

        Parameters
        ----------
        b : numpy.ndarray
           a vector containing RHS of :math:`A x = b` for the solution of the grid stencil
        pyamg_indices : list of int
           the linear pyamg matrix indices where the value of the grid is fixed. I.e. the indices should
           correspond to returned quantities from `pyamg_indices`.
        """
        b[ensure_array(pyamg_indices)] = value

    def pyamg_fix(self, A, b, pyamg_indices, value):
        r""" Fix values for the stencil to `value`.

        Parameters
        ----------
        A : scipy.sparse.csr_matrix
           sparse matrix describing the LHS for the linear system of equations
        b : numpy.ndarray
           a vector containing RHS of :math:`A x = b` for the solution of the grid stencil
        pyamg_indices : list of int
           the linear pyamg matrix indices where the value of the grid is fixed. I.e. the indices should
           correspond to returned quantities from `pyamg_indices`.
        value : float
           the value of the grid to fix the value at
        """
        pyamg_indices = ensure_array(pyamg_indices)
        s = array_arange(A.indptr[pyamg_indices], A.indptr[pyamg_indices+1])
        A.data[s] = 0
        # clean-up
        del s
        A.eliminate_zeros()
        # Specify that these indices are not to be tampered with
        A[pyamg_indices, pyamg_indices] = 1.
        # force RHS value
        self.pyamg_source(b, pyamg_indices, value)
        A.prune() # try and clean-up unneccessary memory

    def pyamg_boundary_condition(self, A, b, bc=None):
        r""" Attach boundary conditions to the `pyamg` grid-matrix `A` with default boundary conditions as specified for this `Grid`

        Parameters
        ----------
        A : scipy.sparse.csr_matrix
           sparse matrix describing the grid
        b : numpy.ndarray
           a vector containing RHS of :math:`A x = b` for the solution of the grid stencil
        bc : list of BC, optional
           the specified boundary conditions.
           Default to the grid's boundary conditions, else `bc` *must* be a list of elements
           with elements corresponding to `Grid.PERIODIC`/`Grid.NEUMANN`...
        """
        C = -1
        def Neumann(idx_bc, idx_p1):
            # TODO check this BC
            # Set all boundary equations to 0
            s = array_arange(A.indptr[idx_bc], A.indptr[idx_bc+1])
            A.data[s] = 0
            # force the boundary cells to equal the neighbouring cell
            A[idx_bc, idx_bc] = -C # I am not sure this is correct, but setting it to 0 does NOT work
            A[idx_bc, idx_p1] = C
            # ensure the neighbouring cell doesn't connect to the boundary (no back propagation)
            A[idx_p1, idx_bc] = 0
            # Ensure the sum of the source for the neighbouring cells equals 0
            # To make it easy to figure out the diagonal elements we first
            # set it to 0, then sum off-diagonal terms, and set the diagonal
            # equal to the sum.
            A[idx_p1, idx_p1] = 0
            n = A.indptr[idx_p1+1] - A.indptr[idx_p1]
            s = array_arange(A.indptr[idx_p1], n=n)
            n = np.split(A.data[s], np.cumsum(n)[:-1])
            n = ensure_array(map(np.sum, n))
            # update diagonal
            A[idx_p1, idx_p1] = -n
            del s, n
            A.eliminate_zeros()
            b[idx_bc] = 0.
        def Dirichlet(idx):
            # Default pyamg Poisson matrix has Dirichlet BC
            b[idx] = 0.
        def Periodic(idx1, idx2):
            A[idx1, idx2] = C
            A[idx2, idx1] = C

        def sl2idx(sl):
            return self.pyamg_index(self.mgrid(sl))

        # Create slices
        sl = [slice(0, g) for g in self.shape]

        for i in range(3):
            # We have a periodic direction
            new_sl = sl[:]

            # LOWER BOUNDARY
            bc = self.bc[i, 0]
            new_sl[i] = slice(0, 1)
            idx1 = sl2idx(new_sl) # lower

            if self.bc[i, 0] == self.PERIODIC or \
               self.bc[i, 1] == self.PERIODIC:
                if self.bc[i, 0] != self.bc[i, 1]:
                    raise ValueError('*Must* not happen')
                new_sl[i] = slice(self.shape[i]-1, self.shape[i])
                idx2 = sl2idx(new_sl) # upper
                Periodic(idx1, idx2)
                del idx2
                continue

            if bc == self.NEUMANN:
                # Retrieve next index
                new_sl[i] = slice(1, 2)
                idx2 = sl2idx(new_sl) # lower + 1
                Neumann(idx1, idx2)
                del idx2
            elif bc == self.DIRICHLET:
                Dirichlet(idx1)

            # UPPER BOUNDARY
            bc = self.bc[i, 1]
            new_sl[i] = slice(self.shape[i]-1, self.shape[i])
            idx1 = sl2idx(new_sl) # upper

            if bc == self.NEUMANN:
                # Retrieve next index
                new_sl[i] = slice(self.shape[i]-2, self.shape[i]-1)
                idx2 = sl2idx(new_sl) # upper - 1
                Neumann(idx1, idx2)
                del idx2
            elif bc == self.DIRICHLET:
                Dirichlet(idx1)

        A.prune()

    def topyamg(self):
        r""" Create a `pyamg` stencil matrix to be used in pyamg

        This allows retrieving the grid matrix equivalent of the real-space grid.
        Subsequently the returned matrix may be used in pyamg for solutions etc.

        The `pyamg` suite is it-self a rather complicated code with many options.
        For details we refer to `pyamg <pyamg https://github.com/pyamg/pyamg/>`_.

        Returns
        -------
        A : scipy.sparse.csr_matrix which contains the grid stencil for a `pyamg` solver.
        b : numpy.ndarray containing RHS of the linear system of equations.

        Examples
        --------
        This example proves the best method for a variety of cases in regards of the 3D Poisson problem:

        >>> grid = Grid(0.01)
        >>> A, b = grid.topyamg() # automatically setups the current boundary conditions
        >>> # add terms etc. to A and/or b
        >>> import pyamg
        >>> from scipy.sparse.linalg import cg
        >>> ml = pyamg.aggregation.smoothed_aggregation_solver(A, max_levels=1000)
        >>> M = ml.aspreconditioner(cycle='W') # pre-conditioner
        >>> x, info = cg(A, b, tol=1e-12, M=M)

        See Also
        --------
        pyamg_index : convert grid indices into the sparse matrix indices for ``A``
        pyamg_fix : fixes stencil for indices and fixes the source for the RHS matrix (uses `pyamg_source`)
        pyamg_source : fix the RHS matrix ``b`` to a constant value
        pyamg_boundary_condition : setup the sparse matrix ``A`` to given boundary conditions (called in this routine)
        """
        from pyamg.gallery import poisson
        # Initially create the CSR matrix
        A = poisson(self.shape, dtype=self.dtype, format='csr')
        b = np.zeros(A.shape[0], dtype=A.dtype)

        # Now apply the boundary conditions
        self.pyamg_boundary_condition(A, b)
        return A, b

    @classmethod
    def _ArgumentParser_args_single(cls):
        """ Returns the options for `Grid.ArgumentParser` in case they are the only options """
        return {'limit_arguments': False,
                'short': True,
                'positional_out': True,
            }

    # Hook into the Grid class to create
    # an automatic ArgumentParser which makes actions
    # as the options are read.
    @default_ArgumentParser(description="Manipulate a Grid object in sisl.")
    def ArgumentParser(self, p=None, *args, **kwargs):
        """ Create and return a group of argument parsers which manipulates it self `Grid`.

        Parameters
        ----------
        p: ArgumentParser, None
           in case the arguments should be added to a specific parser. It defaults
           to create a new.
        limit_arguments: bool, True
           If `False` additional options will be created which are similar to other options.
           For instance `--repeat-x` which is equivalent to `--repeat x`.
        short: bool, False
           Create short options for a selected range of options
        positional_out: bool, False
           If `True`, adds a positional argument which acts as --out. This may be handy if only the geometry is in the argument list.
        """
        limit_args = kwargs.get('limit_arguments', True)
        short = kwargs.get('short', False)

        def opts(*args):
            if short:
                return args
            return [args[0]]

        # We limit the import to occur here
        import argparse

        # The first thing we do is adding the Grid to the NameSpace of the
        # parser.
        # This will enable custom actions to interact with the grid in a
        # straight forward manner.
        d = {
            "_grid": self.copy(),
            "_stored_grid": False,
        }
        namespace = default_namespace(**d)

        # Define actions
        class SetGeometry(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):
                ns._geometry = Geometry.read(value)
                ns._grid.set_geometry(ns._geometry)
        p.add_argument(*opts('--geometry', '-G'), action=SetGeometry,
                       help='Define the geometry attached to the Grid.')

        # Define size of grid
        class InterpGrid(argparse.Action):

            def __call__(self, parser, ns, values, option_string=None):
                ns._grid = ns._grid.interp([int(x) for x in values])
        p.add_argument(*opts('--interp'), nargs=3,
                       action=InterpGrid,
                       help='Interpolate the grid.')

        # substract another grid
        # They *MUST* be conmensurate.
        class DiffGrid(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):
                grid = Grid.read(value)
                ns._grid -= grid
                del grid
        p.add_argument(*opts('--diff', '-d'), action=DiffGrid,
                       help='Subtract another grid (they must be commensurate).')

        class AverageGrid(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):
                ns._grid = ns._grid.average(direction(value))
        p.add_argument(*opts('--average'), metavar='DIR',
                       action=AverageGrid,
                       help='Take the average of the grid along DIR.')

        class SumGrid(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):
                ns._grid = ns._grid.sum(direction(value))
        p.add_argument(*opts('--sum'), metavar='DIR',
                       action=SumGrid,
                       help='Take the sum of the grid along DIR.')

        # Create-subsets of the grid
        class SubDirectionGrid(argparse.Action):

            def __call__(self, parser, ns, values, option_string=None):
                # The unit-cell direction
                axis = direction(values[1])
                # Figure out whether this is a fractional or
                # distance in Ang
                is_frac = 'f' in values[0]
                rng = strseq(float, values[0].replace('f', ''))
                if isinstance(rng, tuple):
                    if is_frac:
                        rng = tuple(rng)
                    # we have bounds
                    if rng[0] is None:
                        idx1 = 0
                    else:
                        idx1 = ns._grid.index(rng[0], axis=axis)
                    if rng[1] is None:
                        idx2 = ns._grid.shape[axis]
                    else:
                        idx2 = ns._grid.index(rng[1], axis=axis)
                    ns._grid = ns._grid.sub(_a.arangei(idx1, idx2), axis)
                    return
                elif rng < 0.:
                    if is_frac:
                        rng = ns._grid.cell[axis, :] * abs(rng)
                    b = False
                else:
                    if is_frac:
                        rng = ns._grid.cell[axis, :] * rng
                    b = True
                idx = ns._grid.index(rng, axis=axis)
                ns._grid = ns._grid.sub_part(idx, axis, b)
        p.add_argument(*opts('--sub'), nargs=2, metavar=('COORD', 'DIR'),
                       action=SubDirectionGrid,
                       help='Reduce the grid by taking a subset of the grid (along DIR).')

        # Create-subsets of the grid
        class RemoveDirectionGrid(argparse.Action):

            def __call__(self, parser, ns, values, option_string=None):
                # The unit-cell direction
                axis = direction(values[1])
                # Figure out whether this is a fractional or
                # distance in Ang
                is_frac = 'f' in values[0]
                rng = strseq(float, values[0].replace('f', ''))
                if isinstance(rng, tuple):
                    # we have bounds
                    if not (rng[0] is None or rng[1] is None):
                        raise NotImplementedError('Can not figure out how to apply mid-removal of grids.')
                    if rng[0] is None:
                        idx1 = 0
                    else:
                        idx1 = ns._grid.index(rng[0], axis=axis)
                    if rng[1] is None:
                        idx2 = ns._grid.shape[axis]
                    else:
                        idx2 = ns._grid.index(rng[1], axis=axis)
                    ns._grid = ns._grid.remove(_a.arangei(idx1, idx2), axis)
                    return
                elif rng < 0.:
                    if is_frac:
                        rng = ns._grid.cell[axis, :] * abs(rng)
                    b = True
                else:
                    if is_frac:
                        rng = ns._grid.cell[axis, :] * rng
                    b = False
                idx = ns._grid.index(rng, axis=axis)
                ns._grid = ns._grid.remove_part(idx, axis, b)
        p.add_argument(*opts('--remove'), nargs=2, metavar=('COORD', 'DIR'),
                       action=RemoveDirectionGrid,
                       help='Reduce the grid by removing a subset of the grid (along DIR).')

        # Define size of grid
        class PrintInfo(argparse.Action):

            def __call__(self, parser, ns, values, option_string=None):
                ns._stored_grid = True
                print(ns._grid)
        p.add_argument(*opts('--info'), nargs=0,
                       action=PrintInfo,
                       help='Print, to stdout, some regular information about the grid.')

        class Out(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):
                if value is None:
                    return
                if len(value) == 0:
                    return
                ns._grid.write(value[0])
                # Issue to the namespace that the grid has been written, at least once.
                ns._stored_grid = True
        p.add_argument(*opts('--out', '-o'), nargs=1, action=Out,
                       help='Store the grid (at its current invocation) to the out file.')

        # If the user requests positional out arguments, we also add that.
        if kwargs.get('positional_out', False):
            p.add_argument('out', nargs='*', default=None,
                           action=Out,
                           help='Store the grid (at its current invocation) to the out file.')

        # We have now created all arguments
        return p, namespace


def sgrid(grid=None, argv=None, ret_grid=False):
    """ Main script for sgrid.

    This routine may be called with `argv` and/or a `Sile` which is the grid at hand.

    Parameters
    ----------
    grid : Grid or BaseSile
       this may either be the grid, as-is, or a `Sile` which contains
       the grid.
    argv : list of str
       the arguments passed to sgrid
    ret_grid : bool, optional
       whether the function should return the grid
    """
    import sys
    import os.path as osp
    import argparse

    from sisl.io import get_sile, BaseSile

    # The file *MUST* be the first argument
    # (except --help|-h)

    # We cannot create a separate ArgumentParser to retrieve a positional arguments
    # as that will grab the first argument for an option!

    # Start creating the command-line utilities that are the actual ones.
    description = """
This manipulation utility is highly advanced and one should note that the ORDER of
options is determining the final structure. For instance:

   {0} ElectrostaticPotential.grid.nc --diff Other.grid.nc --sub z 0.:0.2f

is NOT equivalent to:

   {0} ElectrostaticPotential.grid.nc --sub z 0.:0.2f --diff Other.grid.nc

This may be unexpected but enables one to do advanced manipulations.
    """.format(osp.basename(sys.argv[0]))

    if argv is not None:
        if len(argv) == 0:
            argv = ['--help']
    elif len(sys.argv) == 1:
        # no arguments
        # fake a help
        argv = ['--help']
    else:
        argv = sys.argv[1:]

    # Ensure that the arguments have pre-pended spaces
    argv = cmd.argv_negative_fix(argv)

    p = argparse.ArgumentParser('Manipulates real-space grids in commonly encounterd files.',
                           formatter_class=argparse.RawDescriptionHelpFormatter,
                           description=description)

    # First read the input "Sile"
    if grid is None:
        argv, input_file = cmd.collect_input(argv)
        with get_sile(input_file) as fh:
            grid = fh.read_grid()

    elif isinstance(grid, Grid):
        # Do nothing, the grid is already created
        pass

    elif isinstance(grid, BaseSile):
        grid = grid.read_grid()
        # Store the input file...
        input_file = grid.file

    # Do the argument parser
    p, ns = grid.ArgumentParser(p, **grid._ArgumentParser_args_single())

    # Now the arguments should have been populated
    # and we will sort out if the input options
    # is only a help option.
    try:
        if not hasattr(ns, '_input_file'):
            setattr(ns, '_input_file', input_file)
    except:
        pass

    # Now try and figure out the actual arguments
    p, ns, argv = cmd.collect_arguments(argv, input=False,
                                        argumentparser=p,
                                        namespace=ns)

    # We are good to go!!!
    args = p.parse_args(argv, namespace=ns)
    g = args._grid

    if not args._stored_grid:
        # We should write out the information to the stdout
        # This is merely for testing purposes and may not be used for anything.
        print(g)

    if ret_grid:
        return g
    return 0
