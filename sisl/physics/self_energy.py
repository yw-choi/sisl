from __future__ import print_function, division

from numbers import Integral

import numpy as np
from numpy import dot, amax, conjugate
from numpy import subtract
from numpy import empty, zeros, identity
from numpy import zeros_like, empty_like
from numpy import complex128
from numpy import abs as _abs

from sisl.messages import warn, info
from sisl.utils.mathematics import fnorm
from sisl.utils.ranges import array_arange
from sisl._help import array_replace
import sisl._array as _a
from sisl.linalg import solve, inv
from sisl.physics.brillouinzone import BrillouinZone, MonkhorstPack
from sisl.physics.bloch import Bloch


__all__ = ['SelfEnergy', 'SemiInfinite']
__all__ += ['RecursiveSI', 'RealSpaceSE']


class SelfEnergy(object):
    """ Self-energy object able to calculate the dense self-energy for a given sparse matrix

    The self-energy object contains a `SparseGeometry` object which, in it-self
    contains the geometry.

    This is the base class for self-energies.
    """

    def __init__(self, *args, **kwargs):
        """ Self-energy class for constructing a self-energy. """
        pass

    def _setup(self, *args, **kwargs):
        """ Class specific setup routine """
        pass

    def self_energy(self, *args, **kwargs):
        raise NotImplementedError

    def __getattr__(self, attr):
        """ Overload attributes from the hosting object """
        pass


class SemiInfinite(SelfEnergy):
    """ Self-energy object able to calculate the dense self-energy for a given `SparseGeometry` in a semi-infinite chain.

    Parameters
    ----------
    spgeom : SparseGeometry
       any sparse geometry matrix which may return matrices
    infinite : str
       axis specification for the semi-infinite direction (`+A`/`-A`/`+B`/`-B`/`+C`/`-C`)
    eta : float, optional
       the default imaginary part of the self-energy calculation
    """

    def __init__(self, spgeom, infinite, eta=1e-4):
        """ Create a `SelfEnergy` object from any `SparseGeometry` """
        self.eta = eta

        # Determine whether we are in plus/minus direction
        if infinite.startswith('+'):
            self.semi_inf_dir = 1
        elif infinite.startswith('-'):
            self.semi_inf_dir = -1
        else:
            raise ValueError(self.__class__.__name__ + ": infinite keyword does not start with `+` or `-`.")

        # Determine the direction
        INF = infinite.upper()
        if INF.endswith('A'):
            self.semi_inf = 0
        elif INF.endswith('B'):
            self.semi_inf = 1
        elif INF.endswith('C'):
            self.semi_inf = 2

        # Check that the Hamiltonian does have a non-zero V along the semi-infinite direction
        if spgeom.geometry.sc.nsc[self.semi_inf] == 1:
            warn('Creating a semi-infinite self-energy with no couplings along the semi-infinite direction')

        # Finalize the setup by calling the class specific routine
        self._setup(spgeom)

    def __str__(self):
        """ String representation of SemiInfinite """
        return  '{0}{{direction: {1}{2}}}'.format(self.__class__.__name__,
                                                  {-1: '-', 1: '+'}.get(self.semi_inf_dir),
                                                  {0: 'A', 1: 'B', 2: 'C'}.get(self.semi_inf))


class RecursiveSI(SemiInfinite):
    """ Self-energy object using the Lopez-Sancho Lopez-Sancho algorithm """

    def __getattr__(self, attr):
        """ Overload attributes from the hosting object """
        return getattr(self.spgeom0, attr)

    def __str__(self):
        """ Representation of the RecursiveSI model """
        direction = {-1: '-', 1: '+'}
        axis = {0: 'A', 1: 'B', 2: 'C'}
        return '{0}{{direction: {1}{2},\n {3}\n}}'.format(self.__class__.__name__,
                                                          direction[self.semi_inf_dir], axis[self.semi_inf],
                                                          str(self.spgeom0).replace('\n', '\n '),
        )

    def _setup(self, spgeom):
        """ Setup the Lopez-Sancho internals for easy axes """

        # Create spgeom0 and spgeom1
        self.spgeom0 = spgeom.copy()
        nsc = np.copy(spgeom.geometry.sc.nsc)
        nsc[self.semi_inf] = 1
        self.spgeom0.set_nsc(nsc)

        # For spgeom1 we have to do it slightly differently
        old_nnz = spgeom.nnz
        self.spgeom1 = spgeom.copy()
        nsc[self.semi_inf] = 3

        # Already now limit the sparse matrices
        self.spgeom1.set_nsc(nsc)
        if self.spgeom1.nnz < old_nnz:
            warn("RecursiveSI: SparseGeometry has connections across the first neighbouring cell. "
                 "These values will be forced to 0 as the principal cell-interaction is a requirement")

        # I.e. we will delete all interactions that are un-important
        n_s = self.spgeom1.geometry.sc.n_s
        n = self.spgeom1.shape[0]
        # Figure out the matrix columns we should set to zero
        nsc = [None] * 3
        nsc[self.semi_inf] = self.semi_inf_dir
        # Get all supercell indices that we should delete
        idx = np.delete(_a.arangei(n_s),
                        _a.arrayi(spgeom.geometry.sc.sc_index(nsc)))

        cols = array_arange(idx * n, (idx + 1) * n)
        # Delete all values in columns, but keep them to retain the supercell information
        self.spgeom1._csr.delete_columns(cols, keep_shape=True)

    def green(self, E, k=(0, 0, 0), dtype=None, eps=1e-14, **kwargs):
        r""" Return a dense matrix with the bulk Green function at energy `E` and k-point `k` (default Gamma).

        Parameters
        ----------
        E : float/complex
          energy at which the calculation will take place
        k : array_like, optional
          k-point at which the Green function should be evaluated.
          the k-point should be in units of the reciprocal lattice vectors.
        dtype : numpy.dtype
          the resulting data type
        eps : float, optional
          convergence criteria for the recursion
        **kwargs : dict, optional
           arguments passed directly to the ``self.parent.Pk`` method (not ``self.parent.Sk``), for instance ``spin``

        Returns
        -------
        self-energy : the self-energy corresponding to the semi-infinite direction
        """
        if E.imag == 0.:
            E = E.real + 1j * self.eta

        # Get k-point
        k = _a.asarrayd(k)

        if dtype is None:
            dtype = complex128

        sp0 = self.spgeom0
        sp1 = self.spgeom1

        # As the SparseGeometry inherently works for
        # orthogonal and non-orthogonal basis, there is no
        # need to have two algorithms.
        GB = sp0.Sk(k, dtype=dtype, format='array') * E - sp0.Pk(k, dtype=dtype, format='array', **kwargs)
        n = GB.shape[0]

        ab = empty([n, 2, n], dtype=dtype)
        shape = ab.shape

        # Get direct arrays
        alpha = ab[:, 0, :].view()
        beta = ab[:, 1, :].view()

        # Get solve step arary
        ab2 = ab.view()
        ab2.shape = (n, 2 * n)

        if sp1.orthogonal:
            alpha[:, :] = sp1.Pk(k, dtype=dtype, format='array', **kwargs)
            beta[:, :] = conjugate(alpha.T)
        else:
            P = sp1.Pk(k, dtype=dtype, format='array', **kwargs)
            S = sp1.Sk(k, dtype=dtype, format='array')
            alpha[:, :] = P - S * E
            beta[:, :] = conjugate(P.T) - conjugate(S.T) * E
            del P, S

        while True:
            tab = solve(GB, ab2).reshape(shape)

            # Update bulk Green function
            subtract(GB, dot(alpha, tab[:, 1, :]), out=GB)
            subtract(GB, dot(beta, tab[:, 0, :]), out=GB)

            # Update forward/backward
            alpha[:, :] = dot(alpha, tab[:, 0, :])
            beta[:, :] = dot(beta, tab[:, 1, :])

            # Convergence criteria, it could be stricter
            if _abs(alpha).max() < eps:
                # Return the pristine Green function
                del ab, alpha, beta, ab2, tab
                return inv(GB, True)

        raise ValueError(self.__class__.__name__+'.green could not converge Green function calculation')

    def self_energy(self, E, k=(0, 0, 0), dtype=None, eps=1e-14, bulk=False, **kwargs):
        r""" Return a dense matrix with the self-energy at energy `E` and k-point `k` (default Gamma).

        Parameters
        ----------
        E : float/complex
          energy at which the calculation will take place
        k : array_like, optional
          k-point at which the self-energy should be evaluated.
          the k-point should be in units of the reciprocal lattice vectors.
        dtype : numpy.dtype
          the resulting data type
        eps : float, optional
          convergence criteria for the recursion
        bulk : bool, optional
          if true, :math:`E\cdot \mathbf S - \mathbf H -\boldsymbol\Sigma` is returned, else
          :math:`\boldsymbol\Sigma` is returned (default).
        **kwargs : dict, optional
           arguments passed directly to the ``self.parent.Pk`` method (not ``self.parent.Sk``), for instance ``spin``

        Returns
        -------
        self-energy : the self-energy corresponding to the semi-infinite direction
        """
        if E.imag == 0.:
            E = E.real + 1j * self.eta

        # Get k-point
        k = _a.asarrayd(k)

        if dtype is None:
            dtype = complex128

        sp0 = self.spgeom0
        sp1 = self.spgeom1

        # As the SparseGeometry inherently works for
        # orthogonal and non-orthogonal basis, there is no
        # need to have two algorithms.
        GB = sp0.Sk(k, dtype=dtype, format='array') * E - sp0.Pk(k, dtype=dtype, format='array', **kwargs)
        n = GB.shape[0]

        ab = empty([n, 2, n], dtype=dtype)
        shape = ab.shape

        # Get direct arrays
        alpha = ab[:, 0, :].view()
        beta = ab[:, 1, :].view()

        # Get solve step arary
        ab2 = ab.view()
        ab2.shape = (n, 2 * n)

        if sp1.orthogonal:
            alpha[:, :] = sp1.Pk(k, dtype=dtype, format='array', **kwargs)
            beta[:, :] = conjugate(alpha.T)
        else:
            P = sp1.Pk(k, dtype=dtype, format='array', **kwargs)
            S = sp1.Sk(k, dtype=dtype, format='array')
            alpha[:, :] = P - S * E
            beta[:, :] = conjugate(P.T) - conjugate(S.T) * E
            del P, S

        # Surface Green function (self-energy)
        if bulk:
            GS = GB.copy()
        else:
            GS = zeros_like(GB)

        # Specifying dot with 'out' argument should be faster
        tmp = empty_like(GS)
        while True:
            tab = solve(GB, ab2).reshape(shape)

            dot(alpha, tab[:, 1, :], tmp)
            # Update bulk Green function
            subtract(GB, tmp, out=GB)
            subtract(GB, dot(beta, tab[:, 0, :]), out=GB)
            # Update surface self-energy
            GS -= tmp

            # Update forward/backward
            alpha[:, :] = dot(alpha, tab[:, 0, :])
            beta[:, :] = dot(beta, tab[:, 1, :])

            # Convergence criteria, it could be stricter
            if _abs(alpha).max() < eps:
                # Return the pristine Green function
                del ab, alpha, beta, ab2, tab, GB
                if bulk:
                    return GS
                return - GS

        raise ValueError(self.__class__.__name__+': could not converge self-energy calculation')

    def self_energy_lr(self, E, k=(0, 0, 0), dtype=None, eps=1e-14, bulk=False, **kwargs):
        r""" Return two dense matrices with the left/right self-energy at energy `E` and k-point `k` (default Gamma).

        Note calculating the LR self-energies simultaneously requires that their chemical potentials are the same.
        I.e. only when the reference energy is equivalent in the left/right schemes does this make sense.

        Parameters
        ----------
        E : float/complex
          energy at which the calculation will take place, if complex, the hosting ``eta`` won't be used.
        k : array_like, optional
          k-point at which the self-energy should be evaluated.
          the k-point should be in units of the reciprocal lattice vectors.
        dtype : numpy.dtype, optional
          the resulting data type, default to ``np.complex128``
        eps : float, optional
          convergence criteria for the recursion
        bulk : bool, optional
          if true, :math:`E\cdot \mathbf S - \mathbf H -\boldsymbol\Sigma` is returned, else
          :math:`\boldsymbol\Sigma` is returned (default).
        **kwargs : dict, optional
           arguments passed directly to the ``self.parent.Pk`` method (not ``self.parent.Sk``), for instance ``spin``

        Returns
        -------
        left : the left self-energy
        right : the right self-energy
        """
        if E.imag == 0.:
            E = E.real + 1j * self.eta

        # Get k-point
        k = _a.asarrayd(k)

        if dtype is None:
            dtype = complex128

        sp0 = self.spgeom0
        sp1 = self.spgeom1

        # As the SparseGeometry inherently works for
        # orthogonal and non-orthogonal basis, there is no
        # need to have two algorithms.
        SmH0 = sp0.Sk(k, dtype=dtype, format='array') * E - sp0.Pk(k, dtype=dtype, format='array', **kwargs)
        GB = SmH0.copy()
        n = GB.shape[0]

        ab = empty([n, 2, n], dtype=dtype)
        shape = ab.shape

        # Get direct arrays
        alpha = ab[:, 0, :].view()
        beta = ab[:, 1, :].view()

        # Get solve step arary
        ab2 = ab.view()
        ab2.shape = (n, 2 * n)

        if sp1.orthogonal:
            alpha[:, :] = sp1.Pk(k, dtype=dtype, format='array', **kwargs)
            beta[:, :] = conjugate(alpha.T)
        else:
            P = sp1.Pk(k, dtype=dtype, format='array', **kwargs)
            S = sp1.Sk(k, dtype=dtype, format='array')
            alpha[:, :] = P - S * E
            beta[:, :] = conjugate(P.T) - conjugate(S.T) * E
            del P, S

        # Surface Green function (self-energy)
        if bulk:
            GS = GB.copy()
        else:
            GS = zeros_like(GB)

        # Specifying dot with 'out' argument should be faster
        tmp = empty_like(GS)
        while True:
            tab = solve(GB, ab2).reshape(shape)

            dot(alpha, tab[:, 1, :], tmp)
            # Update bulk Green function
            subtract(GB, tmp, out=GB)
            subtract(GB, dot(beta, tab[:, 0, :]), out=GB)
            # Update surface self-energy
            GS -= tmp

            # Update forward/backward
            alpha[:, :] = dot(alpha, tab[:, 0, :])
            beta[:, :] = dot(beta, tab[:, 1, :])

            # Convergence criteria, it could be stricter
            if _abs(alpha).max() < eps:
                # Return the pristine Green function
                del ab, alpha, beta, ab2, tab
                if self.semi_inf_dir == 1:
                    # GS is the "right" self-energy
                    if bulk:
                        return GB - GS + SmH0, GS
                    return GS - GB + SmH0, - GS
                # GS is the "left" self-energy
                if bulk:
                    return GS, GB - GS + SmH0
                return - GS, GS - GB + SmH0

        raise ValueError(self.__class__.__name__+': could not converge self-energy (LR) calculation')


class RealSpaceSE(SelfEnergy):
    r""" Calculate real-space self-energy (or Green function) for a given physical object with periodicity

    The real-space self-energy is calculated via the k-averaged Green function:

    .. math::
        \boldsymbol\Sigma^\mathcal{R}(E) = \mathbf S^\mathcal{R} (E+i\eta) - \mathbf H^\mathcal{R}
             - \sum_{\mathbf k} \mathbf G_{\mathbf k}(E)

    The method actually used is relying on `RecursiveSI` and `~sisl.physics.Bloch` objects.

    Parameters
    ----------
    parent : SparseOrbitalBZ
        a physical object from which to calculate the real-space self-energy.
        The parent object *must* have only 3 supercells along the direction where
        self-energies are used.
    semi_axis : int
        semi-infinite direction (where self-energies are used and thus *exact* precision)
    k_axes : array_like of int
        the axes where k-points are desired. 1 or 2 values are required and the `semi_axis`
        cannot be one of them
    unfold : (3,) of int
        number of times the `parent` structure is tiled along each direction
        The resulting Green function/self-energy ordering is always tiled along
        the semi-infinite direction first, and then the transverse direction.
    eta : float, optional
        imaginary part in the self-energy calculations (default 1e-4 eV)
    dk : float, optional
        fineness of the default integration grid, specified in units of Ang, default to 1000 which
        translates to 1000 k-points along reciprocal cells of length 1. Ang^-1.
    bz : BrillouinZone, optional
        integration k-points, if not passed the number of k-points will be determined using
        `dk` and time-reversal symmetry will be determined by `trs`
    trs: bool, optional
        whether time-reversal symmetry is used in the BrillouinZone integration, default
        to true.

    Examples
    --------
    >>> graphene = geom.graphene()
    >>> H = Hamiltonian(graphene)
    >>> H.construct([(0.1, 1.44), (0, -2.7)])
    >>> rse = RealSpaceSE(H, 0, 1, (3, 4, 1))
    >>> rse.green(0.1)

    The Brillouin zone integration is determined naturally.

    >>> graphene = geom.graphene()
    >>> H = Hamiltonian(graphene)
    >>> H.construct([(0.1, 1.44), (0, -2.7)])
    >>> rse = RealSpaceSE(H, 0, 1, (3, 4, 1))
    >>> rse.set_options(eta=1e-3, bz=MonkhorstPack(H, [1, 1000, 1]))
    >>> rse.initialize()
    >>> rse.green(0.1) # eta = 1e-3
    >>> rse.green(0.1 + 1j * 1e-4) # eta = 1e-4

    Manually specify Brillouin zone integration and default :math:`\eta` value.
    """

    def __init__(self, parent, semi_axis, k_axes, unfold=(1, 1, 1), **options):
        """ Initialize real-space self-energy calculator """
        self.parent = parent

        # Store axes
        self._semi_axis = semi_axis
        self._k_axes = np.sort(_a.asarrayi(k_axes).ravel())

        # Check axis
        s_ax = self._semi_axis
        k_ax = self._k_axes
        if s_ax in k_ax:
            raise ValueError(self.__class__.__name__ + ' found the self-energy direction to be '
                             'the same as one of the k-axes, this is not allowed.')
        if np.any(self.parent.nsc[k_ax] < 3):
            raise ValueError(self.__class__.__name__ + ' found k-axes without periodicity. '
                             'Correct k_axes via .set_options.')
        if self.parent.nsc[s_ax] != 3:
            raise ValueError(self.__class__.__name__ + ' found the self-energy direction to be '
                             'incompatible with the parent object. It *must* have 3 supercells along the '
                             'semi-infinite direction.')

        # Local variables for the completion of the details
        self._unfold = _a.arrayi([max(1, un) for un in unfold])

        # Check that the unfold is 1 for the non-k/semi axes
        check_unfold = array_replace(self._unfold, (k_ax, 1), (s_ax, 1))
        if np.any(check_unfold > 1):
            raise ValueError(self.__class__.__name__ + ' found unfolding along a non-k, non-semi '
                             'direction. Please correct your settings by having all unfolded axes in either '
                             'a semi-infinite or k-averaged direction.')

        self._options = {
            # fineness of the integration k-grid [Ang]
            'dk': 1000,
            # whether TRS is used (G + G.T) * 0.5
            'trs': True,
            # imaginary part used in the Green function calculation (unless an imaginary energy is passed)
            'eta': 1e-4,
            # The BrillouinZone used for integration
            'bz': None,
        }
        self.set_options(**options)
        self.initialize()

    def set_options(self, **options):
        """ Update options in the real-space self-energy

        After updating options one should re-call `initialize` for consistency.

        Parameters
        ----------
        eta : float, optional
            imaginary part in the self-energy calculations (default 1e-4 eV)
        dk : float, optional
            fineness of the default integration grid, specified in units of Ang, default to 1000 which
            translates to 1000 k-points along reciprocal cells of length 1. Ang^-1.
        bz : BrillouinZone, optional
            integration k-points, if not passed the number of k-points will be determined using
            `dk` and time-reversal symmetry will be determined by `trs`
        trs: bool, optional
            whether time-reversal symmetry is used in the BrillouinZone integration, default
            to true.
        """
        self._options.update(options)

    def real_space_parent(self):
        """ Return the parent object in the real-space unfolded region """
        s_ax = self._semi_axis
        k_ax = self._k_axes
        # Always start with the semi-infinite direction, since we
        # Bloch expand the other directions
        P0 = self.parent.tile(self._unfold[s_ax], s_ax)
        for ax in k_ax:
            P0 = P0.tile(self._unfold[ax], ax)
        # Only specify the used axis without periodicity
        # This will allow one to use the real-space self-energy
        # for *circles*
        nsc = array_replace(P0.nsc, (s_ax, 1), (k_ax, 1))
        P0.set_nsc(nsc)
        return P0

    def real_space_coupling(self, ret_indices=False):
        """ Real-space coupling parent where sites fold into the parent real-space unit cell

        The resulting parent object only contains the inner-cell couplings for the elements that couple
        out of the real-space matrix.

        Parameters
        ----------
        ret_indices : bool, optional
           if true, also return the atomic indices (corresponding to `real_space_parent`) that encompass the coupling matrix

        Returns
        -------
        parent : parent object only retaining the elements of the atoms that couple out of the primary unit cell
        atom_index : indices for the atoms that couple out of the geometry (`ret_indices`)
        """
        s_ax = self._semi_axis
        k_ax = self._k_axes

        # If there are any axes that still has k-point sampling (for e.g. circles)
        # we should remove that periodicity before figuring out which atoms that connect out.
        # This is because the self-energy should *only* remain on the sites connecting
        # out of the self-energy used. The k-axis retains all atoms, per see.
        PC = self.parent.tile(self._unfold[s_ax], s_ax)
        for ax in k_ax:
            PC = PC.tile(self._unfold[ax], ax)

        nsc = array_replace(PC.nsc, (s_ax, None), (k_ax, None), other=1)
        PC.set_nsc(nsc)

        # Geometry short-hand
        g = PC.geometry
        # Remove all inner-cell couplings (0, 0, 0) to figure out the
        # elements that couple out of the real-space region
        n = PC.shape[0]
        idx = g.sc.sc_index([0, 0, 0])
        cols = _a.arangei(idx * n, (idx + 1) * n)
        csr = PC._csr.copy([0]) # we just want the sparse pattern, so forget about the other elements
        csr.delete_columns(cols, keep_shape=True)
        # Now PC only contains couplings along the k and semi-inf directions
        # Extract the connecting orbitals and reduce them to unique atomic indices
        orbs = g.osc2uc(csr.col[array_arange(csr.ptr[:-1], n=csr.ncol)], True)
        atom_idx = g.o2a(orbs, True)

        # Only retain coupling atoms
        # Remove all out-of-cell couplings such that we only have inner-cell couplings
        # Or, if we retain periodicity along a given direction, we will retain those
        # as well.
        PC = self.parent.tile(self._unfold[s_ax], s_ax)
        for ax in k_ax:
            PC = PC.tile(self._unfold[ax], ax)
        PC = PC.sub(atom_idx)

        # Truncate nsc along the repititions
        nsc = array_replace(PC.nsc, (s_ax, 1), (k_ax, 1))
        PC.set_nsc(nsc)
        if ret_indices:
            return PC, atom_idx
        return PC

    def initialize(self):
        """ Initialize the internal data-arrays used for efficient calculation of the real-space quantities

        This method should first be called *after* all options has been specified.

        If the user hasn't specified the ``bz`` value as an option this method will update the internal
        integration Brillouin zone based on ``dk`` and ``trs`` options.
        """
        s_ax = self._semi_axis
        k_ax = self._k_axes

        # Create temporary access elements in the calculation dictionary
        # to be used in .green and .self_energy
        P0 = self.real_space_parent()
        V_atoms = self.real_space_coupling(True)[1]
        self._calc = {
            # The below algorithm requires the direction to be negative
            # if changed, B, C should be reversed below
            'SE': RecursiveSI(self.parent, '-' + 'ABC'[s_ax], eta=self._options['eta']),
            # Used to calculate the real-space self-energy
            'P0': P0.Pk,
            'S0': P0.Sk,
            # Orbitals in the coupling atoms
            'orbs': P0.a2o(V_atoms, True).reshape(-1, 1),
        }

        # Update the BrillouinZone integration grid in case it isn't specified
        if self._options['bz'] is None:
            # Update the integration grid
            # Note this integration grid is based on the big system.
            sc = self.parent.sc * self._unfold
            rcell = fnorm(sc.rcell)[k_ax]
            nk = _a.onesi(3)
            nk[k_ax] = np.ceil(self._options['dk'] * rcell).astype(np.int32)
            self._options['bz'] = MonkhorstPack(sc, nk, trs=self._options['trs'])

    def self_energy(self, E, k=(0, 0, 0), bulk=False, coupling=False, dtype=None, **kwargs):
        r""" Calculate the real-space self-energy

        The real space self-energy is calculated via:

        .. math::
            \boldsymbol\Sigma^{\mathcal{R}}(E) = \mathbf S^{\mathcal{R}} E - \mathbf H^{\mathcal{R}}
               - \sum_{\mathbf k} \mathbf G_{\mathbf k}(E)

        Parameters
        ----------
        E : float/complex
           energy to evaluate the real-space self-energy at
        k : array_like, optional
           only viable for 3D bulk systems with real-space self-energies along 2 directions.
           I.e. this would correspond to circular self-energies.
        bulk : bool, optional
           if true, :math:`\mathbf S^{\mathcal{R}} E - \mathbf H^{\mathcal{R}} - \boldsymbol\Sigma^\mathcal{R}`
           is returned, otherwise :math:`\boldsymbol\Sigma^\mathcal{R}` is returned
        coupling: bool, optional
           if True, only the self-energy terms located on the coupling geometry (`coupling_geometry`)
           are returned
        dtype : numpy.dtype, optional
          the resulting data type, default to ``np.complex128``
        **kwargs : dict, optional
           arguments passed directly to the ``self.parent.Pk`` method (not ``self.parent.Sk``), for instance ``spin``
        """
        if dtype is None:
            dtype = complex128
        if E.imag == 0:
            E = E.real + 1j * self._options['eta']

        # Calculate the Green function
        G = self.green(E, k, dtype=dtype)

        if coupling:
            orbs = self._calc['orbs']
            iorbs = _a.arangei(orbs.size).reshape(1, -1)
            I = zeros([G.shape[0], orbs.size], dtype)
            # Set diagonal
            I[orbs.ravel(), iorbs.ravel()] = 1.
            if bulk:
                return solve(G, I, True, True)[orbs, iorbs]
            return (self._calc['S0'](k, dtype=dtype) * E - self._calc['P0'](k, dtype=dtype, **kwargs))[orbs, orbs.T].toarray() \
                - solve(G, I, True, True)[orbs, iorbs]
        if bulk:
            return inv(G, True)
        return (self._calc['S0'](k, dtype=dtype) * E - self._calc['P0'](k, dtype=dtype, **kwargs)).toarray() - inv(G, True)

    def green(self, E, k=(0, 0, 0), dtype=None, **kwargs):
        r""" Calculate the real-space Green function

        The real space Green function is calculated via:

        .. math::
            \mathbf G^\mathcal{R}(E) = \sum_{\mathbf k} \mathbf G_{\mathbf k}(E)

        Parameters
        ----------
        E : float/complex
           energy to evaluate the real-space Green function at
        k : array_like, optional
           only viable for 3D bulk systems with real-space Green functions along 2 directions.
           I.e. this would correspond to a circular real-space Green function
        dtype : numpy.dtype, optional
          the resulting data type, default to ``np.complex128``
        **kwargs : dict, optional
           arguments passed directly to the ``self.parent.Pk`` method (not ``self.parent.Sk``), for instance ``spin``
        """
        opt = self._options

        # Retrieve integration k-grid
        bz = opt['bz']
        try:
            # If the BZ implements TRS (MonkhorstPack) then force it
            trs = bz._trs >= 0
        except:
            trs = opt['trs']

        if dtype is None:
            dtype = complex128

        # Now we are to calculate the real-space self-energy
        if E.imag == 0:
            E = E.real + 1j * opt['eta']

        # Used axes
        s_ax = self._semi_axis
        k_ax = self._k_axes

        k = _a.asarrayd(k)
        is_k = np.any(k != 0.)
        if is_k:
            axes = [s_ax] + k_ax.tolist()
            if np.any(k[axes] != 0.):
                raise ValueError('{}.green requires the k-point to be zero along the integrated axes.'.format(self.__class__.__name__))
            if trs:
                raise ValueError('{}.green requires a k-point sampled Green function to not use time reversal symmetry.'.format(self.__class__.__name__))
            # Shift k-points to get the correct k-point in the larger one.
            bz._k += k.reshape(1, 3)

        # Calculate both left and right at the same time.
        SE = self._calc['SE'].self_energy_lr

        # Define Bloch unfolding routine and number of tiles along the semi-inf direction
        unfold = self._unfold.copy()
        tile = unfold[s_ax]
        unfold[s_ax] = 1
        bloch = Bloch(unfold)

        if tile == 1:
            # When not tiling, it can be simplified quite a bit
            M0 = self._calc['SE'].spgeom0
            M0Pk = M0.Pk
            if self.parent.orthogonal:
                # Orthogonal *always* identity
                S0E = identity(len(M0), dtype=dtype) * E
                def _calc_green(k, dtype, no, tile, idx0):
                    SL, SR = SE(E, k, dtype=dtype, **kwargs)
                    return inv(S0E - M0Pk(k, dtype=dtype, format='array', **kwargs) - SL - SR, True)
            else:
                M0Sk = M0.Sk
                def _calc_green(k, dtype, no, tile, idx0):
                    SL, SR = SE(E, k, dtype=dtype, **kwargs)
                    return inv(M0Sk(k, dtype=dtype, format='array') * E - M0Pk(k, dtype=dtype, format='array', **kwargs) - SL - SR, True)

        else:
            M1 = self._calc['SE'].spgeom1
            M1Pk = M1.Pk
            if self.parent.orthogonal:
                def _calc_green(k, dtype, no, tile, idx0):
                    # Calculate left/right self-energies
                    Gf, A2 = SE(E, k, dtype=dtype, bulk=True, **kwargs) # A1 == Gf, because of memory usage
                    B = - M1Pk(k, dtype=dtype, format='array', **kwargs)
                    # C = conjugate(B.T)

                    tY = - solve(Gf, conjugate(B.T), True, True)
                    Gf = inv(A2 + dot(B, tY), True)
                    tX = - solve(A2, B, True, True)

                    # Since this is the pristine case, we know that
                    # G11 and G22 are the same:
                    #  G = [A1 + C.tX]^-1 == [A2 + B.tY]^-1

                    G = empty([tile, no, tile, no], dtype=dtype)
                    G[idx0, :, idx0, :] = Gf.reshape(1, no, no)
                    for i in range(1, tile):
                        G[idx0[i:], :, idx0[:-i], :] = dot(tX, G[i-1, :, 0, :]).reshape(1, no, no)
                        G[idx0[:-i], :, idx0[i:], :] = dot(tY, G[0, :, i-1, :]).reshape(1, no, no)
                    return G.reshape(tile * no, -1)

            else:
                M1Sk = M1.Sk
                def _calc_green(k, dtype, no, tile, idx0):
                    Gf, A2 = SE(E, k, dtype=dtype, bulk=True, **kwargs) # A1 == Gf, because of memory usage
                    tY = M1Sk(k, dtype=dtype, format='array') # S
                    tX = M1Pk(k, dtype=dtype, format='array', **kwargs) # H
                    B = tY * E - tX
                    # C = _conj(tY.T) * E - _conj(tX.T)

                    tY = - solve(Gf, conjugate(tY.T) * E - conjugate(tX.T), True, True)
                    Gf = inv(A2 + dot(B, tY), True)
                    tX = - solve(A2, B, True, True)

                    G = empty([tile, no, tile, no], dtype=dtype)
                    G[idx0, :, idx0, :] = Gf.reshape(1, no, no)
                    for i in range(1, tile):
                        G[idx0[i:], :, idx0[:-i], :] = dot(tX, G[i-1, :, 0, :]).reshape(1, no, no)
                        G[idx0[:-i], :, idx0[i:], :] = dot(tY, G[0, :, i-1, :]).reshape(1, no, no)
                    return G.reshape(tile * no, -1)

        # Create functions used to calculate the real-space Green function
        # For TRS we only-calculate +k and average by using G(k) = G(-k)^T
        # The extra arguments is because the internal decorator is actually pretty slow
        # to filter out unused arguments.

        # If using Bloch's theorem we need to wrap the Green function calculation
        # as the method call.
        if len(bloch) > 1:
            def _func_bloch(k, dtype, no, tile, idx0):
                return bloch(_calc_green, k, dtype=dtype, no=no, tile=tile, idx0=idx0)
        else:
            _func_bloch = _calc_green

        # Tiling indices
        idx0 = _a.arangei(tile)
        no = len(self.parent)

        # calculate the Green function
        G = bz.asaverage().call(_func_bloch, dtype=dtype, no=no, tile=tile, idx0=idx0)

        if is_k:
            # Revert k-points
            bz._k -= k.reshape(1, 3)

        if trs:
            # Faster to do it once, than per G
            return (G + G.T) * 0.5
        return G

    def clear(self):
        """ Clears the internal arrays created in `initialize` """
        del self._calc
