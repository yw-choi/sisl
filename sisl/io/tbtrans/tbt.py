from __future__ import print_function, division

from numbers import Integral
try:
    from StringIO import StringIO
except Exception:
    from io import StringIO

import numpy as np
from numpy import in1d
import itertools

# The sparse matrix for the orbital/bond currents
from scipy.sparse import csr_matrix
from scipy.sparse import isspmatrix_csr

# Import sile objects
from ..sile import add_sile, sile_raise_write
from ._cdf import _devncSileTBtrans
from sisl.utils import *
import sisl._array as _a

from sisl import Geometry, Atoms, SuperCell
from sisl.messages import warn
from sisl._help import _range as range
from sisl.unit.siesta import unit_convert


__all__ = ['tbtncSileTBtrans', 'phtncSileTBtrans']
__all__ += ['tbtavncSileTBtrans', 'phtavncSileTBtrans']

Bohr2Ang = unit_convert('Bohr', 'Ang')
Ry2eV = unit_convert('Ry', 'eV')
Ry2K = unit_convert('Ry', 'K')
eV2Ry = unit_convert('eV', 'Ry')


class tbtncSileTBtrans(_devncSileTBtrans):
    r""" TBtrans output file object

    Implementation of the TBtrans output ``*.TBT.nc`` files which contains
    calculated quantities related to the NEGF code TBtrans.

    Although the TBtrans code is in fortran and the resulting NetCDF file variables
    are in fortran indexing (1-based), everything is returned as Python indexing (0-based)
    when using Python scripts.

    In the following equations we will use this notation:

    * :math:`\alpha` and :math:`\beta` are atomic indices
    * :math:`\nu` and :math:`\mu` are orbital indices

    A word on DOS normalization:

    All the device region DOS functions may request a normalization depending
    on a variety of functions. You are highly encouraged to read the documentation for
    the `norm` function and to consider the benefit of using the ``norm='atom'``
    normalization to more easily compare various partitions of DOS.

    Notes
    -----
    The API for this class are largely equivalent to the arguments of the `sdata` command-line
    tool, with the execption that the command-line tool uses Fortran indexing numbers (1-based).
    """
    _trans_type = 'TBT'
    _k_avg = False

    def write_tbtav(self, *args, **kwargs):
        """ Convert this to a TBT.AV.nc file, i.e. all k dependent quantites are averaged out.

        This command will overwrite any previous file with the ending TBT.AV.nc and thus
        will not take notice of any older files.
        """
        tbtavncSileTBtrans(self._file.replace('.nc', '.AV.nc'), mode='w', access=0).write(tbtav=self)

    def _value_avg(self, name, tree=None, kavg=False):
        """ Local method for obtaining the data from the SileCDF.

        This method checks how the file is access, i.e. whether
        data is stored in the object or it should be read consequtively.
        """
        if self._access > 0:
            if name in self._data:
                return self._data[name]

        v = self._variable(name, tree=tree)
        if self._k_avg:
            return v[:]

        wkpt = self.wk

        # Perform normalization
        orig_shape = v.shape
        if isinstance(kavg, bool):
            if kavg:
                nk = len(wkpt)
                data = v[0, ...] * wkpt[0]
                for i in range(1, nk):
                    data += v[i, :] * wkpt[i]
                data.shape = orig_shape[1:]
            else:
                data = v[:]

        elif isinstance(kavg, Integral):
            data = v[kavg, ...] * wkpt[kavg]
            data.shape = orig_shape[1:]

        else:
            # We assume kavg is some kind of iterable
            data = v[kavg[0], ...] * wkpt[kavg[0]]
            for i in range(1, len(kavg)):
                data += v[kavg[i], ...] * wkpt[kavg[i]]
            data.shape = orig_shape[1:]

        # Return data
        return data

    def _value_E(self, name, tree=None, kavg=False, E=None):
        """ Local method for obtaining the data from the SileCDF using an E index.

        """
        if E is None:
            return self._value_avg(name, tree, kavg)

        # Ensure that it is an index
        iE = self.Eindex(E)

        v = self._variable(name, tree=tree)
        if self._k_avg:
            return v[iE, ...]

        wkpt = self.wk

        # Perform normalization
        orig_shape = v.shape

        if isinstance(kavg, bool):
            if kavg:
                nk = len(wkpt)
                data = np.array(v[0, iE, ...]) * wkpt[0]
                for i in range(1, nk):
                    data += v[i, iE, ...] * wkpt[i]
                data.shape = orig_shape[2:]
            else:
                data = np.array(v[:, iE, ...])

        elif isinstance(kavg, Integral):
            data = np.array(v[kavg, iE, ...]) * wkpt[kavg]
            data.shape = orig_shape[2:]

        else:
            # We assume kavg is some kind of itterable
            data = v[kavg[0], iE, ...] * wkpt[kavg[0]]
            for i in kavg[1:]:
                data += v[i, iE, ...] * wkpt[i]
            data.shape = orig_shape[2:]

        # Return data
        return data

    def _elec(self, elec):
        """ Converts a string or integer to the corresponding electrode name

        Parameters
        ----------
        elec : str or int
           if `str` it is the *exact* electrode name, if `int` it is the electrode
           index

        Returns
        -------
        str : the electrode name
        """
        try:
            elec = int(elec)
            return self.elecs[elec]
        except:
            return elec

    @property
    def elecs(self):
        """ List of electrodes """
        elecs = list(self.groups.keys())

        # in cases of not calculating all
        # electrode transmissions we must ensure that
        # we add the last one
        var = self.groups[elecs[0]].variables.keys()
        for tvar in var:
            if tvar.endswith('.T'):
                tvar = tvar.split('.')[0]
                if tvar not in elecs:
                    elecs.append(tvar)
        return elecs

    def chemical_potential(self, elec):
        """ Return the chemical potential associated with the electrode `elec` """
        return self._value('mu', self._elec(elec))[0] * Ry2eV
    mu = chemical_potential

    def electronic_temperature(self, elec):
        """ Return temperature of the electrode electronic distribution in Kelvin """
        return self._value('kT', self._elec(elec))[0] * Ry2K

    def kT(self, elec):
        """ Return temperature of the electrode electronic distribution in eV """
        return self._value('kT', self._elec(elec))[0] * Ry2eV

    def eta(self, elec):
        """ The imaginary part used when calculating the self-energies in eV """
        try:
            return self._value('eta', self._elec(elec))[0] * Ry2eV
        except:
            return 0.

    def transmission(self, elec_from=0, elec_to=1, kavg=True):
        """ Transmission from `elec_from` to `elec_to`.

        The transmission between two electrodes may be retrieved
        from the `Sile`.

        Parameters
        ----------
        elec_from: str, int, optional
           the originating electrode
        elec_to: str, int, optional
           the absorbing electrode (different from `elec_from`)
        kavg: bool, int or array_like, optional
           whether the returned transmission is k-averaged, an explicit k-point
           or a selection of k-points

        See Also
        --------
        transmission_eig : the transmission decomposed in eigenchannels
        transmission_bulk : the total transmission in a periodic lead
        """
        elec_from = self._elec(elec_from)
        elec_to = self._elec(elec_to)
        if elec_from == elec_to:
            raise ValueError("Supplied elec_from and elec_to must not be the same.")

        return self._value_avg(elec_to + '.T', elec_from, kavg=kavg)

    def transmission_eig(self, elec_from=0, elec_to=1, kavg=True):
        """ Transmission eigenvalues from `elec_from` to `elec_to`.

        Parameters
        ----------
        elec_from: str, int, optional
           the originating electrode
        elec_to: str, int, optional
           the absorbing electrode (different from `elec_from`)
        kavg: bool, int or array_like, optional
           whether the returned transmission is k-averaged, an explicit k-point
           or a selection of k-points

        See Also
        --------
        transmission : the total transmission
        transmission_bulk : the total transmission in a periodic lead
        """
        elec_from = self._elec(elec_from)
        elec_to = self._elec(elec_to)
        if elec_from == elec_to:
            raise ValueError(
                "Supplied elec_from and elec_to must not be the same.")

        return self._value_avg(elec_to + '.T.Eig', elec_from, kavg=kavg)

    def transmission_bulk(self, elec=0, kavg=True):
        """ Bulk transmission for the `elec` electrode

        The bulk transmission is equivalent to creating a 2 terminal device with
        electrode `elec` tiled 3 times.

        Parameters
        ----------
        elec: str, int, optional
           the bulk electrode
        kavg: bool, int or array_like, optional
           whether the returned transmission is k-averaged, an explicit k-point
           or a selection of k-points

        See Also
        --------
        transmission : the total transmission
        transmission_eig : the transmission decomposed in eigenchannels
        """
        return self._value_avg('T', self._elec(elec), kavg=kavg)

    def norm(self, atom=None, orbital=None, norm='none'):
        r""" Normalization factor depending on the input

        The normalization can be performed in one of the below methods.
        In the following :math:`N` refers to the normalization constant
        that is to be used (i.e. the divisor):

        ``'none'``
           :math:`N=1`
        ``'all'``
           :math:`N` equals the number of orbitals in the total device region.
        ``'atom'``
           :math:`N` equals the total number of orbitals in the selected
           atoms. If `orbital` is an argument a conversion of `orbital` to the equivalent
           unique atoms is performed, and subsequently the total number of orbitals on the
           atoms is used. This makes it possible to compare the fraction of orbital DOS easier.
        ``'orbital'``
           :math:`N` is the sum of selected orbitals, if `atom` is specified, this
           is equivalent to the 'atom' option.

        Parameters
        ----------
        atom : array_like of int or bool, optional
           only return for a given set of atoms (default to all).
           *NOT* allowed with `orbital` keyword
        orbital : array_like of int or bool, optional
           only return for a given set of orbitals (default to all)
           *NOT* allowed with `atom` keyword
        norm : {'none', 'atom', 'orbital', 'all'}
           how the normalization of the summed DOS is performed (see `norm` routine)
        """
        # Cast to lower
        norm = norm.lower()
        if norm == 'none':
            NORM = 1.
        elif norm in ['all', 'atom', 'orbital']:
            NORM = float(self.no_d)
        else:
            raise ValueError('Error on norm keyword in when requesting normalization')

        if atom is None and orbital is None:
            return NORM

        # Now figure out what to do
        if atom is None:
            # Get pivoting indices to average over
            if norm == 'orbital':
                NORM = float(len(self.o2p(orbital)))
            elif norm == 'atom':
                geom = self.geom
                a = np.unique(geom.o2a(orbital))
                # Now sum the orbitals per atom
                NORM = float(_a.sumi(geom.firsto[a+1] - geom.firsto[a]))
            return NORM

        # atom is specified
        if norm in ['orbital', 'atom']:
            NORM = float(len(self.o2p(atom)))
        return NORM

    def _DOS(self, DOS, atom, orbital, sum, norm):
        """ Averages/sums the DOS

        Parameters
        ----------
        atom : array_like of int or bool, optional
           only return for a given set of atoms (default to all).
           *NOT* allowed with `orbital` keyword
        orbital : array_like of int or bool, optional
           only return for a given set of orbitals (default to all)
           *NOT* allowed with `atom` keyword
        sum : bool, optional
           whether the returned quantities are summed or returned *as is*, i.e. resolved per atom/orbital.
        norm : {'none', 'atom', 'orbital', 'all'}
           how the normalization of the summed DOS is performed (see `norm` routine)

        Returns
        -------
        numpy.ndarray : in order of the geometry orbitals (i.e. pivoted back to the device region).
                        If `atom` or `orbital` is specified they are returned in that order.
        """
        if not atom is None and not orbital is None:
            raise ValueError(('Both atom and orbital keyword in DOS request '
                              'cannot be specified, only one at a time.'))
        # Cast to lower
        norm = norm.lower()
        if norm == 'none':
            NORM = 1.
        elif norm in ['all', 'atom', 'orbital']:
            NORM = float(self.no_d)
        else:
            raise ValueError('Error on norm keyword in DOS request')

        if atom is None and orbital is None:
            # We simply return *everything*
            if sum:
                return _a.sumd(DOS, axis=-1) / NORM
            # We return the sorted DOS
            p = np.argsort(self.pivot())
            return DOS[..., p] / NORM

        # Now figure out what to do
        if atom is None:
            # orbital *must* be specified

            # Get pivoting indices to average over
            p = self.o2p(orbital)
            if norm == 'orbital':
                NORM = float(len(p))
            elif norm == 'atom':
                geom = self.geom
                a = np.unique(geom.o2a(orbital))
                # Now sum the orbitals per atom
                NORM = float(_a.sumi(geom.firsto[a+1] - geom.firsto[a]))

            if sum:
                return _a.sumd(DOS[..., p], axis=-1) / NORM
            # Else, we have to return the full subset
            return DOS[..., p] / NORM

        # atom is specified
        # Return the pivoting orbitals for the atom
        p = self.a2p(atom)
        if norm in ['orbital', 'atom']:
            NORM = float(len(p))

        if sum or isinstance(atom, Integral):
            # Regardless of SUM, when requesting a single atom
            # we return it
            return _a.sumd(DOS[..., p], axis=-1) / NORM

        # We default the case where 1-orbital systems are in use
        # Then it becomes *very* easy
        if len(p) == len(atom):
            return DOS[..., p] / NORM

        # This is the multi-orbital case...

        # We will return per-atom
        shp = list(DOS.shape[:-1])
        nDOS = np.empty(shp + [len(atom)], np.float64)

        # Quicker than re-creating the geometry on every instance
        geom = self.geom

        # Sum for new return stuff
        for i, a in enumerate(atom):
            pvt = self.o2p(geom.a2o(a, True))
            if len(pvt) == 0:
                nDOS[..., i] = 0.
            else:
                nDOS[..., i] = _a.sumd(DOS[..., pvt], axis=-1) / NORM

        return nDOS

    def DOS(self, E=None, kavg=True, atom=None, orbital=None, sum=True, norm='none'):
        r""" Green function density of states (DOS) (1/eV).

        Extract the DOS on a selected subset of atoms/orbitals in the device region

        .. math::

           \mathrm{DOS}(E) = -\frac{1}{\pi N} \sum_{\nu\in \mathrm{atom}/\mathrm{orbital}} \Im \mathbf{G}_{\nu\nu}(E)

        The normalization constant (:math:`N`) is defined in the routine `norm` and depends on the
        arguments.

        Parameters
        ----------
        E : float or int, optional
           optionally only return the DOS of atoms at a given energy point
        kavg: bool, int or array_like, optional
           whether the returned DOS is k-averaged, an explicit k-point
           or a selection of k-points
        atom : array_like of int or bool, optional
           only return for a given set of atoms (default to all).
           *NOT* allowed with `orbital` keyword
        orbital : array_like of int or bool, optional
           only return for a given set of orbitals (default to all)
           *NOT* allowed with `atom` keyword
        sum : bool, optional
           whether the returned quantities are summed or returned *as is*, i.e. resolved per atom/orbital.
        norm : {'none', 'atom', 'orbital', 'all'}
           how the normalization of the summed DOS is performed (see `norm` routine)

        See Also
        --------
        ADOS : the spectral density of states from an electrode
        BDOS : the bulk density of states in an electrode
        """
        return self._DOS(self._value_E('DOS', kavg=kavg, E=E),
                                  atom, orbital, sum, norm) * eV2Ry

    def ADOS(self, elec=0, E=None, kavg=True, atom=None, orbital=None, sum=True, norm='none'):
        r""" Spectral density of states (DOS) (1/eV).

        Extract the spectral DOS from electrode `elec` on a selected subset of atoms/orbitals in the device region

        .. math::
           \mathrm{ADOS}_\mathfrak{el}(E) = \frac{1}{2\pi N} \sum_{\nu\in \mathrm{atom}/\mathrm{orbital}} [\mathbf{G}(E)\Gamma_\mathfrak{el}\mathbf{G}^\dagger]_{\nu\nu}(E)

        The normalization constant (:math:`N`) is defined in the routine `norm` and depends on the
        arguments.

        Parameters
        ----------
        elec: str, int, optional
           electrode originating spectral function
        E : float or int, optional
           optionally only return the DOS of atoms at a given energy point
        kavg: bool, int or array_like, optional
           whether the returned DOS is k-averaged, an explicit k-point
           or a selection of k-points
        atom : array_like of int or bool, optional
           only return for a given set of atoms (default to all).
           *NOT* allowed with `orbital` keyword
        orbital : array_like of int or bool, optional
           only return for a given set of orbitals (default to all)
           *NOT* allowed with `atom` keyword
        sum : bool, optional
           whether the returned quantities are summed or returned *as is*, i.e. resolved per atom/orbital.
        norm : {'none', 'atom', 'orbital', 'all'}
           how the normalization of the summed DOS is performed (see `norm` routine).

        See Also
        --------
        DOS : the total density of states (including bound states)
        BDOS : the bulk density of states in an electrode
        """
        elec = self._elec(elec)
        return self._DOS(self._value_E('ADOS', elec, kavg=kavg, E=E),
                         atom, orbital, sum, norm) * eV2Ry

    def BDOS(self, elec=0, E=None, kavg=True, sum=True, norm='none'):
        r""" Bulk density of states (DOS) (1/eV).

        Extract the bulk DOS from electrode `elec` on a selected subset of atoms/orbitals in the device region

        .. math::

           \mathrm{BDOS}_\mathfrak{el}(E) = -\frac{1}{\pi} \Im\mathbf{G}(E)

        Parameters
        ----------
        elec: str, int, optional
           electrode where the bulk DOS is returned
        E : float or int, optional
           optionally only return the DOS of atoms at a given energy point
        kavg: bool, int or array_like, optional
           whether the returned DOS is k-averaged, an explicit k-point
           or a selection of k-points
        sum : bool, optional
           whether the returned quantities are summed or returned *as is*, i.e. resolved per atom/orbital.
        norm : {'none', 'atom', 'orbital', 'all'}
           whether the returned quantities are summed or normed by total number of orbitals.
           Currently one cannot extract DOS per atom/orbital.

        See Also
        --------
        DOS : the total density of states (including bound states)
        ADOS : the spectral density of states from an electrode
        """
        # The bulk DOS is already normalized per non-expanded cell
        # Hence the non-normalized quantity needs to be multiplied by
        #  product(bloch)
        elec = self._elec(elec)
        if norm in ['atom', 'orbital', 'all']:
            # This is normalized per non-expanded unit-cell, so no need to do Bloch
            N = 1. / len(self._dimension('no_u', elec))
        else:
            N = 1.
        if sum:
            return _a.sumd(self._value_E('DOS', elec, kavg=kavg, E=E), axis=-1) * eV2Ry * N
        else:
            return self._value_E('DOS', elec, kavg=kavg, E=E) * eV2Ry * N

    def _E_T_sorted(self, elec_from, elec_to, kavg=True):
        """ Internal routine for returning energies and transmission in a sorted array """
        E = self.E
        idx_sort = np.argsort(E)
        # Get transmission
        elec_from = self._elec(elec_from)
        elec_to = self._elec(elec_to)
        T = self.transmission(elec_from, elec_to, kavg)
        return E[idx_sort], T[idx_sort]

    def current(self, elec_from=0, elec_to=1, kavg=True):
        r""" Current from `from` to `to` using the k-weights and energy spacings in the file.

        Calculates the current as:

        .. math::
           I(\mu_t - \mu_f) = \frac{e}{h}\int\!\mathrm{d}E\, T(E) [n_F(\mu_t, k_B T_t) - n_F(\mu_f, k_B T_f)]

        The chemical potential and the temperature are taken from this object.

        Parameters
        ----------
        elec_from: str, int, optional
           the originating electrode
        elec_to: str, int, optional
           the absorbing electrode (different from `elec_from`)
        kavg: bool, int or array_like, optional
           whether the returned current is k-averaged, an explicit k-point
           or a selection of k-points

        See Also
        --------
        current_parameter : to explicitly set the electronic temperature and chemical potentials
        chemical_potential : routine that defines the chemical potential of the queried electrodes
        kT : routine that defines the electronic temperature of the queried electrodes
        """
        elec_from = self._elec(elec_from)
        elec_to = self._elec(elec_to)
        mu_f = self.chemical_potential(elec_from)
        kt_f = self.kT(elec_from)
        mu_t = self.chemical_potential(elec_to)
        kt_t = self.kT(elec_to)
        return self.current_parameter(elec_from, mu_f, kt_f,
                                      elec_to, mu_t, kt_t, kavg)

    def current_parameter(self, elec_from, mu_from, kt_from,
                          elec_to, mu_to, kt_to, kavg=True):
        r""" Current from `from` to `to` using the k-weights and energy spacings in the file.

        Calculates the current as:

        .. math::
           I(\mu_t - \mu_f) = \frac{e}{h}\int\!\mathrm{d}E\, T(E) [n_F(\mu_t, k_B T_t) - n_F(\mu_f, k_B T_f)]

        The chemical potential and the temperature are passed as arguments to
        this routine.

        Parameters
        ----------
        elec_from: str, int
           the originating electrode
        mu_from: float
           the chemical potential of the electrode (in eV)
        kt_from: float
           the electronic temperature of the electrode (in eV)
        elec_to: str, int
           the absorbing electrode (different from `elec_from`)
        mu_to: float
           the chemical potential of the electrode (in eV)
        kt_to: float
           the electronic temperature of the electrode (in eV)
        kavg: bool, int or array_like, optional
           whether the returned current is k-averaged, an explicit k-point
           or a selection of k-points

        See Also
        --------
        current : which calculates the current with the chemical potentials and temperatures set in the TBtrans calculation
        """
        elec_from = self._elec(elec_from)
        elec_to = self._elec(elec_to)
        # Get energies
        E, T = self._E_T_sorted(elec_from, elec_to, kavg)

        # We expect the tbtrans calcluation was created with the simple
        #   mid-rule!
        # The mid-rule is equivalent to adding a dE = (E[1] - E[0]) / 2
        # to both ends.
        dE = E[1] - E[0]

        # Check that the lower bound is sufficient
        print_warning = mu_from - kt_from * 3 < E[0] - dE / 2 or \
                        mu_to - kt_to * 3  < E[0] - dE / 2
        print_warning = mu_from + kt_from * 3 > E[-1] + dE / 2 or \
                        mu_to + kt_to * 3  > E[-1] + dE / 2 or \
                        print_warning
        if print_warning:
            # We should pretty-print a table of data
            m = max(len(elec_from), len(elec_to), 15)
            s = ("{:"+str(m)+"s} {:9.3f} : {:9.3f} eV\n").format('Energy range', E[0] - dE / 2, E[-1] + dE / 2)
            s += ("{:"+str(m)+"s} {:9.3f} : {:9.3f} eV\n").format(elec_from, mu_from - kt_from * 3, mu_from + kt_from * 3)
            s += ("{:"+str(m)+"s} {:9.3f} : {:9.3f} eV\n").format(elec_to, mu_to - kt_to * 3, mu_to + kt_to * 3)
            min_e = min(mu_from - kt_from * 3, mu_to - kt_to * 3)
            max_e = max(mu_from + kt_from * 3, mu_to + kt_to * 3)
            s += ("{:"+str(m)+"s} {:9.3f} : {:9.3f} eV\n").format('dFermi function', min_e, max_e)

            warn(self.__class__.__name__ + ".current_parameter cannot "
                 "accurately calculate the current due to the calculated energy range. "
                 "I.e. increase your calculated energy-range.\n" + s)

        def nf(E, mu, kT):
            return 1. / (np.exp((E - mu) / kT) + 1.)

        I = _a.sumd(T * dE * (nf(E, mu_from, kt_from) - nf(E, mu_to, kt_to)))
        return I * 1.6021766208e-19 / 4.135667662e-15

    def shot_noise(self, elec_from=0, elec_to=1, classical=False, kavg=True):
        r""" Shot-noise term `from` to `to` using the k-weights and energy spacings in the file.

        Calculates the shot-noise term according to `classical` (also known as the Poisson value). If `classical` is True the shot-noise calculated is:

        .. math::
           S_P(E, V) = \frac{2e^2}{h}|V|\sum_n T_n(E) = \frac{2e^3}{h}|V|T(E)

        while for `classical` False the Fermi-Dirac statistics is taken into account:

        .. math::
           S(E, V) = \frac{2e^2}{h}|V|\sum_n T_n(E) (1 - T_n(E))

        Raises
        ------
        SislWarning: If *all* of the calculated :math:`T_n(E)` values in the file are above 0.001.

        Parameters
        ----------
        elec_from: str, int, optional
           the originating electrode
        elec_to: str, int, optional
           the absorbing electrode (different from `elec_from`)
        classical: bool, optional
           which shot-noise to calculate
        kavg: bool, int or array_like, optional
           whether the returned shot-noise is k-averaged, an explicit k-point
           or a selection of k-points

        See Also
        --------
        fano_factor : the ratio between the quantum mechanial and the classical shot noise.
        """
        elec_from = self._elec(elec_from)
        elec_to = self._elec(elec_to)
        mu_f = self.chemical_potential(elec_from)
        mu_t = self.chemical_potential(elec_to)
        # The applied bias between the two electrodes
        V = abs(mu_f - mu_t)
        # Pre-factor
        e2OVERhV = 2 * 1.6021766208e-19 ** 2 / 4.135667662e-15 * V
        if classical:
            # Calculate the Poisson shot-noise
            return e3OVERhV * self.transmission(elec_from, elec_to, kavg=kavg)
        else:
            T = self.transmission_eig(elec_from, elec_to, kavg=kavg)
            # Check that at least one value is below the 0.001 limit
            if np.any(np.logical_and.reduce(T > 0.001, axis=-1)):
                warn(self.__class__.__name__ + ".shot_noise does possibly not have all relevant transmission eigenvalues in the "
                     "calculation. For some energy values all transmission eigenvalues are above 0.001")
            return e2OVERhV * (T * (1 - T)).sum(-1)

    def fano(self, elec_from=0, elec_to=1, kavg=True):
        r""" The Fano-factor for the calculation (requires calculated transmission eigenvalues)

        Calculate the Fano factor defined as:

        .. math::
           F(E) = \frac{\sum_n T_n(1 - T_n)}{\sum_n T_n} = S(E, V) / S_P(E, V)

        Parameters
        ----------
        elec_from: str, int, optional
           the originating electrode
        elec_to: str, int, optional
           the absorbing electrode (different from `elec_from`)
        kavg: bool, int or array_like, optional
           whether the returned Fano factor is k-averaged, an explicit k-point
           or a selection of k-points

        See Also
        --------
        shot_noise : internal routine to calculate the Fano factors (:math:`S(E, V)` and :math: `S_P(E, V)` are calculated in that routine)
        """
        elec_from = self._elec(elec_from)
        elec_to = self._elec(elec_to)
        return self.shot_noise(elec_from, elec_to, kavg=kavg) / self.shot_noise(elec_from, elec_to, classical=True, kavg=kavg)

    def _sparse_data(self, data, elec, E, kavg=True, isc=None):
        """ Internal routine for retrieving sparse data (orbital current, COOP) """
        # Get the geometry for obtaining the sparsity pattern.
        if elec is not None:
            elec = self._elec(elec)

        geom = self.geom

        # These are the row-pointers...
        rptr = np.insert(_a.cumsumi(self._value('n_col')), 0, 0)

        # Get column indices
        col = self._value('list_col') - 1

        # Default matrix size
        mat_size = [geom.no, geom.no_s]

        # Figure out the super-cell indices that are requested
        # First we figure out the indices, then
        # we build the array of allowed columns
        if isc is None:
            isc = [None, None, None]

        if isc[0] is None and isc[1] is None and isc[2] is None:
            all_col = None

        else:
            # The user has requested specific supercells
            # Here we create a list of supercell interactions.

            nsc = np.copy(geom.nsc)
            # Shorten to the unit-cell if there are no more
            for i in [0, 1, 2]:
                if nsc[i] == 1:
                    isc[i] = 0
                if not isc[i] is None:
                    nsc[i] = 1

            # Small function for creating the supercells allowed
            def ret_range(val, req):
                i = val // 2
                if req is None:
                    return range(-i, i+1)
                return [req]
            x = ret_range(nsc[0], isc[0])
            y = ret_range(nsc[1], isc[1])
            z = ret_range(nsc[2], isc[2])

            # Make a shrinking logical array for selecting a subset of the
            # orbital currents...
            all_col = _a.emptyi(len(x) * len(y) * len(z))
            for i, (ix, iy, iz) in enumerate(itertools.product(x, y, z)):
                all_col[i] = geom.sc_index([ix, iy, iz])

            # If the user requests a single supercell index, we will
            # return a square matrix
            if len(all_col) == 1:
                mat_size[1] = mat_size[0]

            # Transfer all_col to the range
            all_col = array_arange(all_col * geom.no,
                                   n=_a.fulli(len(all_col), geom.no))

            # Create a logical array for sub-indexing
            all_col = in1d(col, _a.arrayi(all_col))
            col = col[all_col]

            # recreate row-pointer
            cnz = np.count_nonzero
            def func(ptr1, ptr2):
                return cnz(all_col[ptr1:ptr2])
            tmp = _a.arrayi(map(func, rptr[:geom.no], rptr[1:]))
            rptr = np.insert(_a.cumsumi(tmp), 0, 0)
            del tmp

        if all_col is None:
            D = self._value_E(data, elec, kavg, E)
        else:
            D = self._value_E(data, elec, kavg, E)[..., all_col]

        return csr_matrix((D, col, rptr), shape=mat_size)

    def _sparse_data_orb_to_atom(self, Dij, uc=False):
        """ Reduce orbital sparse data to atomic sparse data

        Parameters
        ----------
        Dij : scipy.sparse.csr_matrix
           the input data
        uc : bool, optional
           whether the returned data are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.
        """
        geom = self.geom
        na = geom.na
        o2a = geom.o2a

        if not uc:
            uc = Dij.shape[0] == Dij.shape[1]

        # We convert to atomic bond-currents
        if uc:
            Dab = csr_matrix((na, na), dtype=Dij.dtype)

            def map_col(c):
                return o2a(c) % na

        else:
            Dab = csr_matrix((na, na * geom.n_s), dtype=Dij.dtype)

            map_col = o2a

        # Lets do array notation for speeding up the computations
        if not isspmatrix_csr(Dij):
            Dij = Dij.tocsr()

        # Check for the simple case of 1-orbital systems
        if geom.na == geom.no:
            # In this case it is extremely easy!
            # Just copy to the new data

            # Transfer all columns to the new columns
            Dab.indptr[:] = Dij.indptr.copy()
            if uc:
                Dab.indices = (Dij.indices % na).astype(np.int32, copy=False)
            else:
                Dab.indices = Dij.indices.copy()

        else:
            # The multi-orbital case

            # Loop all atoms to make the new pointer array
            # I.e. a consecutive array of pointers starting from
            #   firsto[.] .. lasto[.]
            iptr = Dij.indptr
            # Get first orbital
            fo = geom.firsto
            # Automatically create the new index pointer
            # from first and last orbital
            indptr = np.insert(_a.cumsumi(iptr[fo[1:]] - iptr[fo[:-1]]), 0, 0)

            # Now we have a new indptr, and the column indices have also
            # been processed.
            Dab.indptr[:] = indptr[:]
            # Transfer all columns to the new columns
            Dab.indices = map_col(Dij.indices).astype(np.int32, copy=False)

        # Copy data
        Dab.data = np.copy(Dij.data)
        # Note that we do not sum duplicates as that depends on the next routine
        # I.e. sometimes we want to remove negative values, etc.
        return Dab

    def orbital_current(self, elec, E, kavg=True, isc=None, take='all'):
        """ Orbital current originating from `elec` as a sparse matrix

        This will return a sparse matrix, see ``scipy.sparse.csr_matrix`` for details.
        Each matrix element of the sparse matrix corresponds to the orbital indices of the
        underlying geometry.

        Parameters
        ----------
        elec: str, int
           the electrode of originating electrons
        E: float or int
           the energy or the energy index of the orbital current. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned orbital current is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned bond currents from the unit-cell (``[None, None, None]``) to
           the given supercell, the default is all orbital currents for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.
        take : {'all', '+', '-'}
           which orbital currents to return, all, positive or negative values only.
           Default to ``'all'`` because it can then be used in the subsequent default
           arguments for `bond_current_from_orbital` and `atom_current_from_orbital`.

        Examples
        --------
        >>> Jij = tbt.orbital_current(0, -1.0) # orbital current @ E = -1 eV originating from electrode ``0`` # doctest: +SKIP
        >>> Jij[10, 11] # orbital current from the 11th to the 12th orbital # doctest: +SKIP

        See Also
        --------
        bond_current_from_orbital : transfer the orbital current to bond current
        bond_current : the bond current (orbital current summed over orbitals)
        atom_current_from_orbital : transfer the orbital current to atomic current
        atom_current : the atomic current for each atom (scalar representation of bond-currents)
        vector_current : an atomic field current for each atom (Cartesian representation of bond-currents)
        """
        J = self._sparse_data('J', elec, E, kavg, isc)

        if take == '+':
            J.data = np.where(J.data > 0, J.data, 0).astype(J.dtype, copy=False)
        elif take == '-':
            J.data = np.where(J.data > 0, 0, J.data).astype(J.dtype, copy=False)
        elif take != 'all':
            raise ValueError(self.__class__.__name__ + '.orbital_current "take" keyword has '
                             'wrong value ["all", "+", "-"] allowed.')

        # We will always remove the zeroes and sort the indices... (they should be sorted anyways)
        J.sort_indices()
        J.eliminate_zeros()

        return J

    def bond_current_from_orbital(self, Jij, sum='+', uc=False):
        r""" Bond-current between atoms (sum of orbital currents) from an external orbital current

        Conversion routine from orbital currents into bond currents.

        The bond currents are a sum over all orbital currents:

        .. math::
           J_{\alpha\beta} = \sum_{\nu\in\alpha}\sum_{\mu\in\beta} J_{\nu\mu}

        where if

        * ``sum='+'``:
          only :math:`J_{\nu\mu} > 0` are summed,
        * ``sum='-'``:
          only :math:`J_{\nu\mu} < 0` are summed,
        * ``sum='all'``:
          all :math:`J_{\nu\mu}` are summed.

        Parameters
        ----------
        Jij : scipy.sparse.csr_matrix
           the orbital currents as retrieved from `orbital_current`
        sum : {'+', 'all', '-'}
           If "+" is supplied only the positive orbital currents are used,
           for "-", only the negative orbital currents are used,
           else return both.
        uc : bool, optional
           whether the returned bond-currents are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        Examples
        --------
        >>> Jij = tbt.orbital_current(0, -1.0) # orbital current @ E = -1 eV originating from electrode ``0`` # doctest: +SKIP
        >>> Jab = tbt.bond_current_from_orbital(Jij) # doctest: +SKIP
        >>> Jab[2,3] # bond current between atom 3 and 4 # doctest: +SKIP

        See Also
        --------
        orbital_current : the orbital current between individual orbitals
        bond_current : the bond current (orbital current summed over orbitals)
        atom_current : the atomic current for each atom (scalar representation of bond-currents)
        vector_current : an atomic field current for each atom (Cartesian representation of bond-currents)
        """
        Jab = self._sparse_data_orb_to_atom(Jij, uc)

        if sum == '+':
            Jab.data = np.where(Jab.data > 0, Jab.data, 0).astype(Jab.dtype, copy=False)
        elif sum == '-':
            Jab.data = np.where(Jab.data > 0, 0, Jab.data).astype(Jab.dtype, copy=False)
        elif sum != 'all':
            raise ValueError(self.__class__.__name__ + '.bond_current_from_orbital "sum" keyword has '
                             'wrong value ["+", "-", "all"] allowed.')

        # Do in-place operations by removing all the things not required
        Jab.sort_indices()
        Jab.sum_duplicates()
        Jab.eliminate_zeros()

        return Jab

    def bond_current(self, elec, E, kavg=True, isc=None, sum='+', uc=False):
        """ Bond-current between atoms (sum of orbital currents)

        Short hand function for calling `orbital_current` and `bond_current_from_orbital`.

        Parameters
        ----------
        elec : str, int
           the electrode of originating electrons
        E : float or int
           A `float` for energy in eV, `int` for explicit energy index
           Unlike `orbital_current` this may not be `None` as the down-scaling of the
           orbital currents may not be equivalent for all energy points.
        kavg : bool, int or array_like, optional
           whether the returned bond current is k-averaged, an explicit k-point
           or a selection of k-points
        isc : array_like, optional
           the returned bond currents from the unit-cell (``[None, None, None]``) (default) to
           the given supercell. If ``[None, None, None]`` is passed all
           bond currents are returned.
        sum : {'+', 'all', '-'}
           If "+" is supplied only the positive orbital currents are used,
           for "-", only the negative orbital currents are used,
           else return the sum of both.
        uc : bool, optional
           whether the returned bond-currents are only in the unit-cell.
           If `True` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        Examples
        --------
        >>> Jij = tbt.orbital_current(0, -1.0) # orbital current @ E = -1 eV originating from electrode ``0`` # doctest: +SKIP
        >>> Jab1 = tbt.bond_current_from_orbital(Jij) # doctest: +SKIP
        >>> Jab2 = tbt.bond_current(0, -1.0) # doctest: +SKIP
        >>> Jab1 == Jab2 # doctest: +SKIP
        True

        See Also
        --------
        orbital_current : the orbital current between individual orbitals
        bond_current_from_orbital : transfer the orbital current to bond current
        atom_current : the atomic current for each atom (scalar representation of bond-currents)
        vector_current : an atomic field current for each atom (Cartesian representation of bond-currents)
        """
        elec = self._elec(elec)
        Jij = self.orbital_current(elec, E, kavg, isc)

        return self.bond_current_from_orbital(Jij, sum=sum, uc=uc)

    def atom_current_from_orbital(self, Jij, activity=True):
        r""" Atomic current of atoms by passing the orbital current

        The atomic current is a single number specifying a figure of the *magnitude*
        current flowing through each atom. It is thus *not* a quantity that can be related to
        the physical current flowing in/out of atoms but is merely a number that provides an
        idea of *how much* current this atom is redistributing.

        The atomic current may have two meanings based on these two equations

        .. math::
            J_\alpha^{|a|} &=\frac{1}{2} \sum_\beta \Big| \sum_{\nu\in \alpha}\sum_{\mu\in \beta} J_{\nu\mu} \Big|
            \\
            J_\alpha^{|o|} &=\frac{1}{2} \sum_\beta \sum_{\nu\in \alpha}\sum_{\mu\in \beta} \big| J_{\nu\mu} \big|

        If the *activity* current is requested (``activity=True``)
        :math:`J_\alpha^{\mathcal A} = \sqrt{ J_\alpha^{|a|} J_\alpha^{|o|} }` is returned.

        If ``activity=False`` :math:`J_\alpha^{|a|}` is returned.

        For geometries with all atoms only having 1-orbital, they are equivalent.

        Generally the activity current is a more rigorous figure of merit for the current
        flowing through an atom. More so than than the summed absolute atomic current due to
        the following reasoning. The activity current is a geometric mean of the absolute bond current
        and the absolute orbital current. This means that if there is an atom with a large orbital current
        it will have a larger activity current.

        Parameters
        ----------
        Jij: scipy.sparse.csr_matrix
           the orbital currents as retrieved from `orbital_current`
        activity: bool, optional
           ``True`` to return the activity current, see explanation above

        Examples
        --------
        >>> Jij = tbt.orbital_current(0, -1.03) # orbital current @ E = -1 eV originating from electrode ``0`` # doctest: +SKIP
        >>> Ja = tbt.atom_current_from_orbital(Jij) # doctest: +SKIP
        """
        # Create the bond-currents with all summations
        Jab = self.bond_current_from_orbital(Jij, sum='all')
        # We take the absolute and sum it over all connecting atoms
        Ja = np.asarray(abs(Jab).sum(1)).ravel()

        if activity:
            # Calculate the absolute summation of all orbital
            # currents and transfer it to a bond-current
            Jab = self.bond_current_from_orbital(abs(Jij), sum='all')

            # Sum to make it per atom, it is already the absolute
            Jo = np.asarray(Jab.sum(1)).ravel()

            # Return the geometric mean of the atomic current X orbital
            # current.
            Ja = np.sqrt(Ja * Jo)

        # Scale correctly
        Ja *= 0.5

        return Ja

    def atom_current(self, elec, E, kavg=True, activity=True):
        """ Atomic current of atoms

        Short hand function for calling `orbital_current` and `atom_current_from_orbital`.

        Parameters
        ----------
        elec: str, int
           the electrode of originating electrons
        E: float or int
           the energy or energy index of the atom current.
        kavg: bool, int or array_like, optional
           whether the returned atomic current is k-averaged, an explicit k-point
           or a selection of k-points
        activity: bool, optional
           whether the activity current is returned, see `atom_current_from_orbital` for details.

        See Also
        --------
        orbital_current : the orbital current between individual orbitals
        bond_current_from_orbital : transfer the orbital current to bond current
        bond_current : the bond current (orbital current summed over orbitals)
        vector_current : an atomic field current for each atom (Cartesian representation of bond-currents)
        """
        elec = self._elec(elec)
        Jorb = self.orbital_current(elec, E, kavg)

        return self.atom_current_from_orbital(Jorb, activity=activity)

    def vector_current_from_bond(self, Jab):
        r""" Vector for each atom being the sum of bond-current times the normalized bond between the atoms

        The vector current is defined as:

        .. math::
              \mathbf J_\alpha = \sum_\beta \frac{r_\beta - r_\alpha}{|r_\beta - r_\alpha|} \cdot J_{\alpha\beta}

        Where :math:`J_{\alpha\beta}` is the bond current between atom :math:`\alpha` and :math:`\beta` and
        :math:`r_\alpha` are the atomic coordinates.

        Parameters
        ----------
        Jab: scipy.sparse.csr_matrix
           the bond currents as retrieved from `bond_current`

        Returns
        -------
        numpy.ndarray : an array of vectors per atom in the Geometry (only non-zero for device atoms)

        See Also
        --------
        orbital_current : the orbital current between individual orbitals
        bond_current_from_orbital : transfer the orbital current to bond current
        bond_current : the bond current (orbital current summed over orbitals)
        atom_current : the atomic current for each atom (scalar representation of bond-currents)
        """
        geom = self.geom

        na = geom.na
        # vector currents
        Ja = _a.zerosd([na, 3])

        # Short-hand
        sqrt = np.sqrt

        # Loop atoms in the device region
        # These are the only atoms which may have bond-currents,
        # So no need to loop over any other atoms
        for ia in self.a_dev:
            # Get csr matrix
            Jia = Jab.getrow(ia)

            # Set diagonal to zero
            Jia[0, ia] = 0.
            # Remove the diagonal (prohibits the calculation of the
            # norm of the zero vector, hence required)
            Jia.eliminate_zeros()

            # Now calculate the vector elements
            # Remark that the vector goes from ia -> ja
            rv = geom.Rij(ia, Jia.indices)
            rv = rv / sqrt((rv ** 2).sum(1))[:, None]
            Ja[ia, :] = (Jia.data[:, None] * rv).sum(0)

        return Ja

    def vector_current(self, elec, E, kavg=True, sum='+'):
        """ Vector for each atom describing the *mean* path for the current travelling through the atom

        See `vector_current_from_bond` for details.

        Parameters
        ----------
        elec: str or int
           the electrode of originating electrons
        E: float or int
           the energy or energy index of the vector current.
           Unlike `orbital_current` this may not be `None` as the down-scaling of the
           orbital currents may not be equivalent for all energy points.
        kavg: bool, int or array_like, optional
           whether the returned vector current is k-averaged, an explicit k-point
           or a selection of k-points
        sum : {'+', '-', 'all'}
           By default only sum *outgoing* vector currents (``'+'``).
           The *incoming* vector currents may be retrieved by ``'-'``, while the
           average incoming and outgoing direction can be obtained with ``'all'``.
           In the last case the vector currents are divided by 2 to ensure the length
           of the vector is compatibile with the other options given a pristine system.

        Returns
        -------
        numpy.ndarray : an array of vectors per atom in the Geometry (only non-zero for device atoms)

        See Also
        --------
        orbital_current : the orbital current between individual orbitals
        bond_current_from_orbital : transfer the orbital current to bond current
        bond_current : the bond current (orbital current summed over orbitals)
        atom_current : the atomic current for each atom (scalar representation of bond-currents)
        """
        elec = self._elec(elec)
        # Imperative that we use the entire supercell structure to
        # retain vectors crossing the boundaries
        Jab = self.bond_current(elec, E, kavg, sum=sum)

        if sum == 'all':
            # When we divide by two one can *always* compare the bulk
            # vector currents using either of the sum-rules.
            # I.e. it will be much easier to distinguish differences
            # between "incoming" and "outgoing".
            return self.vector_current_from_bond(Jab) / 2

        return self.vector_current_from_bond(Jab)

    def orbital_COOP(self, E, kavg=True, isc=None):
        r""" Orbital COOP analysis of the Green function

        This will return a sparse matrix, see ``scipy.sparse.csr_matrix`` for details.
        Each matrix element of the sparse matrix corresponds to the COOP of the
        underlying geometry.

        The COOP analysis can be written as:

        .. math::
            \mathrm{COOP}^{\mathbf G}_{\nu\mu} &= \frac{-1}{2\pi}
              \Im\big[(\mathbf G - \mathbf G^\dagger)_{\nu\mu} \mathbf S_{\mu\nu} \big]

        The sum of the COOP DOS is equal to the DOS:

        .. math::
            \mathrm{DOS}_{\nu} &= \sum_\mu \mathrm{COOP}^{\mathbf G}_{\nu\mu}

        Parameters
        ----------
        E: float or int
           the energy or the energy index of COOP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COOP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COOP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COOP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.

        Examples
        --------
        >>> COOP = tbt.orbital_COOP(-1.0) # COOP @ E = -1 eV  # doctest: +SKIP
        >>> COOP[10, 11] # COOP value between the 11th and 12th orbital # doctest: +SKIP
        >>> COOP.sum(1).A[tbt.o_dev, 0] == tbt.DOS(sum=False)[tbt.Eindex(-1.0)] # doctest: +SKIP

        See Also
        --------
        atom_COOP_from_orbital : transfer an orbital COOP to atomic COOP
        atom_COOP : atomic COOP analysis of the Green function
        orbital_ACOOP : orbital resolved COOP analysis of the spectral function
        atom_ACOOP : atomic COOP analysis of the spectral function
        orbital_COHP : orbital resolved COHP analysis of the Green function
        atom_COHP_from_orbital : atomic COHP analysis from an orbital COHP
        atom_COHP : atomic COHP analysis of the Green function
        orbital_ACOHP : orbital resolved COHP analysis of the spectral function
        atom_ACOHP : atomic COHP analysis of the spectral function
        """
        return self.orbital_ACOOP(None, E, kavg, isc)

    def orbital_ACOOP(self, elec, E, kavg=True, isc=None):
        r""" Orbital COOP analysis of the spectral function

        This will return a sparse matrix, see ``scipy.sparse.csr_matrix`` for details.
        Each matrix element of the sparse matrix corresponds to the COOP of the
        underlying geometry.

        The COOP analysis can be written as:

        .. math::
            \mathrm{COOP}^{\mathbf A}_{\nu\mu} &= \frac{1}{2\pi} \Re\big[\mathbf A_{\nu\mu} \mathbf S_{\mu\nu} \big]

        The sum of the COOP DOS is equal to the DOS:

        .. math::
            \mathrm{ADOS}_{\nu} &= \sum_\mu \mathrm{COOP}^{\mathbf A}_{\nu\mu}

        Parameters
        ----------
        elec: str or int
           the electrode of the spectral function
        E: float or int
           the energy or the energy index of COOP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COOP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COOP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COOP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.

        Examples
        --------
        >>> COOP = tbt.orbital_ACOOP(0, -1.0) # COOP @ E = -1 eV from ``0`` spectral function # doctest: +SKIP
        >>> COOP[10, 11] # COOP value between the 11th and 12th orbital # doctest: +SKIP
        >>> COOP.sum(1).A[tbt.o_dev, 0] == tbt.ADOS(0, sum=False)[tbt.Eindex(-1.0)] # doctest: +SKIP

        See Also
        --------
        orbital_COOP : orbital resolved COOP analysis of the Green function
        atom_COOP_from_orbital : transfer an orbital COOP to atomic COOP
        atom_COOP : atomic COOP analysis of the Green function
        atom_ACOOP : atomic COOP analysis of the spectral function
        orbital_COHP : orbital resolved COHP analysis of the Green function
        atom_COHP_from_orbital : atomic COHP analysis from an orbital COHP
        atom_COHP : atomic COHP analysis of the Green function
        orbital_ACOHP : orbital resolved COHP analysis of the spectral function
        atom_ACOHP : atomic COHP analysis of the spectral function
        """
        COOP = self._sparse_data('COOP', elec, E, kavg, isc) * eV2Ry
        COOP.sort_indices()
        COOP.eliminate_zeros()
        return COOP

    def atom_COOP_from_orbital(self, COOP, uc=False):
        r""" Calculate the atomic COOP curve from the orbital COOP

        The atomic COOP are a sum over all orbital COOP:

        .. math::
            \mathrm{COOP}_{\alpha\beta} = \sum_{\nu\in\alpha}\sum_{\mu\in\beta} \mathrm{COOP}_{\nu\mu}

        Parameters
        ----------
        COOP : scipy.sparse.csr_matrix
           the orbital COOP as retrieved from `orbital_COOP` or `orbital_ACOOP`
        uc : bool, optional
           whether the returned COOP are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        See Also
        --------
        orbital_COOP : orbital resolved COOP analysis of the Green function
        orbital_ACOOP : orbital resolved COOP analysis of the spectral function
        atom_COOP : atomic COOP analysis of the Green function
        """
        COOP = self._sparse_data_orb_to_atom(COOP, uc)
        COOP.sort_indices()
        COOP.sum_duplicates()
        COOP.eliminate_zeros()
        return COOP

    def atom_COOP(self, E, kavg=True, isc=None, uc=False):
        r""" Atomic COOP curve of the Green function

        Parameters
        ----------
        E: float or int
           the energy or the energy index of COOP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COOP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COOP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COOP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.
        uc : bool, optional
           whether the returned COOP are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        See Also
        --------
        orbital_COOP : orbital resolved COOP analysis of the Green function
        atom_COOP_from_orbital : transfer an orbital COOP to atomic COOP
        atom_ACOOP : atomic COOP analysis of the spectral function
        atom_COHP : atomic COHP analysis of the Green function
        """
        return self.atom_ACOOP(None, E, kavg, isc, uc)

    def atom_ACOOP(self, elec, E, kavg=True, isc=None, uc=False):
        r""" Atomic COOP curve of the spectral function

        Parameters
        ----------
        elec: str or int
           the electrode of the spectral function
        E: float or int
           the energy or the energy index of COOP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COOP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COOP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COOP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.
        uc : bool, optional
           whether the returned COOP are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        See Also
        --------
        orbital_COOP : orbital resolved COOP analysis of the Green function
        atom_COOP_from_orbital : transfer an orbital COOP to atomic COOP
        atom_COOP : atomic COOP analysis of the Green function
        atom_ACOHP : atomic COHP analysis of the spectral function
        """
        COOP = self.orbital_ACOOP(elec, E, kavg, isc)
        return self.atom_COOP_from_orbital(COOP, uc)

    def orbital_COHP(self, E, kavg=True, isc=None):
        r""" Orbital resolved COHP analysis of the Green function

        This will return a sparse matrix, see ``scipy.sparse.csr_matrix`` for details.
        Each matrix element of the sparse matrix corresponds to the COHP of the
        underlying geometry.

        The COHP analysis can be written as:

        .. math::
            \mathrm{COHP}^{\mathbf G}_{\nu\mu} &= \frac{-1}{2\pi}
              \Im\big[(\mathbf G - \mathbf G^\dagger)_{\nu\mu} \mathbf H_{\mu\nu} \big]

        Parameters
        ----------
        E: float or int
           the energy or the energy index of COHP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COHP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COHP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COHP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.

        Examples
        --------
        >>> COHP = tbt.orbital_COHP(-1.0) # COHP @ E = -1 eV  # doctest: +SKIP
        >>> COHP[10, 11] # COHP value between the 11th and 12th orbital # doctest: +SKIP

        See Also
        --------
        atom_COHP_from_orbital : atomic COHP analysis from an orbital COHP
        atom_COHP : atomic COHP analysis of the Green function
        orbital_ACOHP : orbital resolved COHP analysis of the spectral function
        atom_ACOHP : atomic COHP analysis of the spectral function
        orbital_COOP : orbital resolved COOP analysis of the Green function
        atom_COOP_from_orbital : transfer an orbital COOP to atomic COOP
        atom_COOP : atomic COOP analysis of the Green function
        orbital_ACOOP : orbital resolved COOP analysis of the spectral function
        atom_ACOOP : atomic COOP analysis of the spectral function
        """
        return self.orbital_ACOHP(None, E, kavg, isc)

    def orbital_ACOHP(self, elec, E, kavg=True, isc=None):
        r""" Orbital resolved COHP analysis of the spectral function

        This will return a sparse matrix, see ``scipy.sparse.csr_matrix`` for details.
        Each matrix element of the sparse matrix corresponds to the COHP of the
        underlying geometry.

        The COHP analysis can be written as:

        .. math::
            \mathrm{COHP}^{\mathbf A}_{\nu\mu} &= \frac{1}{2\pi} \Re\big[\mathbf A_{\nu\mu}
                \mathbf H_{\nu\mu} \big]

        Parameters
        ----------
        elec: str or int
           the electrode of the spectral function
        E: float or int
           the energy or the energy index of COHP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COHP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COHP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COHP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.

        See Also
        --------
        orbital_COHP : orbital resolved COHP analysis of the Green function
        atom_COHP_from_orbital : atomic COHP analysis from an orbital COHP
        atom_COHP : atomic COHP analysis of the Green function
        atom_ACOHP : atomic COHP analysis of the spectral function
        orbital_COOP : orbital resolved COOP analysis of the Green function
        atom_COOP_from_orbital : transfer an orbital COOP to atomic COOP
        atom_COOP : atomic COOP analysis of the Green function
        orbital_ACOOP : orbital resolved COOP analysis of the spectral function
        atom_ACOOP : atomic COOP analysis of the spectral function
        """
        COHP = self._sparse_data('COHP', elec, E, kavg, isc)
        COHP.sort_indices()
        COHP.eliminate_zeros()
        return COHP

    def atom_COHP_from_orbital(self, COHP, uc=False):
        r""" Calculate the atomic COHP curve from the orbital COHP

        The atomic COHP are a sum over all orbital COHP:

        .. math::
            \mathrm{COHP}_{\alpha\beta} = \sum_{\nu\in\alpha}\sum_{\mu\in\beta} \mathrm{COHP}_{\nu\mu}

        Parameters
        ----------
        COHP : scipy.sparse.csr_matrix
           the orbital COHP as retrieved from `orbital_COHP` or `orbital_ACOHP`
        uc : bool, optional
           whether the returned COHP are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        See Also
        --------
        orbital_COHP : orbital resolved COHP analysis of the Green function
        orbital_ACOHP : orbital resolved COHP analysis of the spectral function
        atom_COHP : atomic COHP analysis of the Green function
        """
        return self.atom_COOP_from_orbital(COHP, uc)

    def atom_COHP(self, E, kavg=True, isc=None, uc=False):
        r""" Atomic COHP curve of the Green function

        Parameters
        ----------
        E: float or int
           the energy or the energy index of COHP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COHP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COHP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COHP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.
        uc : bool, optional
           whether the returned COHP are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        See Also
        --------
        orbital_COHP : orbital resolved COHP analysis of the Green function
        atom_COHP_from_orbital : transfer an orbital COHP to atomic COHP
        atom_ACOHP : atomic COHP analysis of the spectral function
        atom_COOP : atomic COOP analysis of the Green function
        """
        return self.atom_ACOHP(None, E, kavg, isc, uc)

    def atom_ACOHP(self, elec, E, kavg=True, isc=None, uc=False):
        r""" Atomic COHP curve of the spectral function

        Parameters
        ----------
        elec: str or int
           the electrode of the spectral function
        E: float or int
           the energy or the energy index of COHP. If an integer
           is passed it is the index, otherwise the index corresponding to
           ``Eindex(E)`` is used.
        kavg: bool, int or array_like, optional
           whether the returned COHP is k-averaged, an explicit k-point
           or a selection of k-points
        isc: array_like, optional
           the returned COHP from unit-cell (``[None, None, None]``) to
           the given supercell, the default is all COHP for the supercell.
           To only get unit cell orbital currents, pass ``[0, 0, 0]``.
        uc : bool, optional
           whether the returned COHP are only in the unit-cell.
           If ``True`` this will return a sparse matrix of ``shape = (self.na, self.na)``,
           else, it will return a sparse matrix of ``shape = (self.na, self.na * self.n_s)``.
           One may figure out the connections via `Geometry.sc_index`.

        See Also
        --------
        orbital_COHP : orbital resolved COHP analysis of the Green function
        atom_COHP_from_orbital : transfer an orbital COHP to atomic COHP
        atom_COHP : atomic COHP analysis of the Green function
        atom_ACOOP : atomic COOP analysis of the spectral function
        """
        COHP = self.orbital_ACOHP(elec, E, kavg, isc)
        return self.atom_COHP_from_orbital(COHP, uc)

    def read_data(self, *args, **kwargs):
        """ Read specific type of data.

        This is a generic routine for reading different parts of the data-file.

        Parameters
        ----------
        geom: bool, optional
           return the geometry
        atom_current: bool, optional
           return the atomic current flowing through an atom (the *activity* current)
        vector_current: bool, optional
           return the orbital currents as vectors
        """
        val = []
        for kw in kwargs:

            if kw in ['geom', 'geometry']:
                if kwargs[kw]:
                    val.append(self.read_geometry())

            elif kw == 'atom_current':
                if kwargs[kw]:
                    # TODO we need some way of handling arguments.
                    val.append(self.atom_current(*args))

            elif kw == 'vector_current':
                if kwargs[kw]:
                    # TODO we need some way of handling arguments.
                    val.append(self.vector_current(*args))

        if len(val) == 0:
            val = None
        elif len(val) == 1:
            val = val[0]
        return val

    def info(self, elec=None):
        """ Information about the calculated quantities available for extracting in this file

        Parameters
        ----------
        elec : str or int
           the electrode to request information from
        """
        if not elec is None:
            elec = self._elec(elec)

        # Create a StringIO object to retain the information
        out = StringIO()
        # Create wrapper function
        def prnt(*args, **kwargs):
            print(*args, file=out, **kwargs)

        def truefalse(bol, string, fdf=None):
            if bol:
                prnt("  + " + string + ": true")
            elif fdf is None:
                prnt("  - " + string + ": false")
            else:
                prnt("  - " + string + ": false\t\t["+', '.join(fdf) + ']')

        # Retrieve the device atoms
        prnt("Device information:")
        if self._k_avg:
            prnt("  - all data is k-averaged")
        else:
            # Print out some more information related to the
            # k-point sampling.
            # However, we still do not know whether TRS is
            # applied.
            kpt = self.k
            nA = len(np.unique(kpt[:, 0]))
            nB = len(np.unique(kpt[:, 1]))
            nC = len(np.unique(kpt[:, 2]))
            prnt(("  - number of kpoints: {} <- "
                   "[ A = {} , B = {} , C = {} ] (time-reversal unknown)").format(self.nk, nA, nB, nC))
        prnt("  - energy range:")
        E = self.E
        Em, EM = np.amin(E), np.amax(E)
        dE = np.diff(E)
        dEm, dEM = np.amin(dE) * 1000, np.amax(dE) * 1000 # convert to meV
        if (dEM - dEm) < 1e-3: # 0.001 meV
            prnt("     {:.5f} -- {:.5f} eV  [{:.3f} meV]".format(Em, EM, dEm))
        else:
            prnt("     {:.5f} -- {:.5f} eV  [{:.3f} -- {:.3f} meV]".format(Em, EM, dEm, dEM))
        prnt("  - atoms with DOS (fortran indices):")
        prnt("     " + list2str(self.a_dev + 1))
        truefalse('DOS' in self.variables, "DOS Green function", ['TBT.DOS.Gf'])
        if elec is None:
            elecs = self.elecs
        else:
            elecs = [elec]

        # Print out information for each electrode
        for elec in elecs:
            try:
                try:
                    bloch = self._value('bloch', elec)
                except:
                    bloch = [0] * 3
                prnt()
                prnt("Electrode: {}".format(elec))
                prnt("  - Bloch: [{}, {}, {}]".format(*bloch))
                gelec = self.groups[elec]
                prnt("  - chemical potential: {:.4f} eV".format(self.chemical_potential(elec)))
                prnt("  - electronic temperature: {:.2f} K".format(self.electronic_temperature(elec)))
                prnt("  - imaginary part: {:.4f} meV".format(self.eta(elec) * 1e3))
                truefalse('DOS' in gelec.variables, "DOS bulk", ['TBT.DOS.Elecs'])
                truefalse('ADOS' in gelec.variables, "DOS spectral", ['TBT.DOS.A'])
                truefalse('J' in gelec.variables, "orbital-current", ['TBT.DOS.A', 'TBT.Current.Orb'])
                truefalse('T' in gelec.variables, "transmission bulk", ['TBT.T.Bulk'])
                truefalse(elec + '.T' in gelec.variables, "transmission out", ['TBT.T.Out'])
                truefalse(elec + '.C' in gelec.variables, "transmission out correction", ['TBT.T.Out'])
                truefalse(elec + '.C.Eig' in gelec.variables, "transmission out correction (eigen)", ['TBT.T.Out', 'TBT.T.Eig'])
                for elec2 in self.elecs:
                    # Skip it self, checked above in .T and .C
                    if elec2 == elec:
                        continue
                    truefalse(elec2 + '.T' in gelec.variables, "transmission -> " + elec2)
                    truefalse(elec2 + '.T.Eig' in gelec.variables, "transmission (eigen) -> " + elec2, ['TBT.T.Eig'])
            except:
                prnt("  * no information available")
                if len(elecs) == 1:
                    prnt("\n\nAvailable electrodes are:")
                    for elec in self.elecs:
                        prnt(" - " + elec)
        s = out.getvalue()
        out.close()
        return s

    @default_ArgumentParser(description="Extract data from a TBT.nc file")
    def ArgumentParser(self, p=None, *args, **kwargs):
        """ Returns the arguments that is available for this Sile """

        # We limit the import to occur here
        import argparse

        namespace = default_namespace(_tbt=self,
                                      _geometry=self.geom,
                                      _data=[], _data_description=[],
                                      _data_header=[],
                                      _norm='atom',
                                      _Ovalue='',
                                      _Orng=None, _Erng=None,
                                      _krng=True)

        def ensure_E(func):
            """ This decorater ensures that E is the first element in the _data container """

            def assign_E(self, *args, **kwargs):
                ns = args[1]
                if len(ns._data) == 0:
                    # We immediately extract the energies
                    ns._data.append(ns._tbt.E[ns._Erng].flatten())
                    ns._data_header.append('Energy[eV]')
                return func(self, *args, **kwargs)
            return assign_E

        # Correct the geometry species information
        class GeometryAction(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):

                old_g = ns._geometry.copy()

                # Now read the file to read the geometry from
                g = Geometry.read(value)

                # Make sure g has the same # of orbitals
                atoms = [None] * len(old_g)
                for a, idx in g.atom:
                    for i in idx:
                        atoms[i] = a.copy(orbital=old_g.atom[i].R)
                g._atom = Atoms(atoms)

                ns._geometry = g
        p.add_argument('--geometry', '-G',
                       action=GeometryAction,
                       help=('Update the geometry of the output file, this enables one to set the species correctly,'
                             ' note this only affects output-files where species are important'))

        class ERange(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):
                E = ns._tbt.E
                Emap = strmap(float, value, E.min(), E.max())
                # Convert to actual indices
                E = []
                for begin, end in Emap:
                    if begin is None and end is None:
                        ns._Erng = None
                        return
                    elif begin is None:
                        E.append(range(ns._tbt.Eindex(end)+1))
                    elif end is None:
                        E.append(range(ns._tbt.Eindex(begin), len(ns._tbt.E)))
                    else:
                        E.append(range(ns._tbt.Eindex(begin), ns._tbt.Eindex(end)+1))
                # Issuing unique also sorts the entries
                ns._Erng = np.unique(_a.arrayi(E).flatten())
        p.add_argument('--energy', '-E',
                       action=ERange,
                       help="""Denote the sub-section of energies that are extracted: "-1:0,1:2" [eV]

                       This flag takes effect on all energy-resolved quantities and is reset whenever --plot or --out is called""")

        # k-range
        class kRange(argparse.Action):

            @collect_action
            def __call__(self, parser, ns, value, option_string=None):
                ns._krng = lstranges(strmap(int, value))
        if not self._k_avg:
            p.add_argument('--kpoint', '-k',
                           action=kRange,
                           help="""Denote the sub-section of k-indices that are extracted.

                           This flag takes effect on all k-resolved quantities and is reset whenever --plot or --out is called""")

        # The normalization method
        class NormAction(argparse.Action):

            @collect_action
            def __call__(self, parser, ns, value, option_string=None):
                ns._norm = value
        p.add_argument('--norm', '-N', action=NormAction, default='atom',
                       choices=['atom', 'all', 'none', 'orbital'],
                       help="""Specify the normalization method; "atom") total orbitals in selected atoms,
                       "all") total orbitals in the device region, "none") no normalization or "orbital") selected orbitals.

                       This flag only takes effect on --dos and --ados and is reset whenever --plot or --out is called""")

        # Try and add the atomic specification
        class AtomRange(argparse.Action):

            @collect_action
            def __call__(self, parser, ns, value, option_string=None):
                value = value.replace(' ', '')

                # Immediately convert to proper indices
                geom = ns._geometry
                a_dev = ns._tbt.a_dev[:] + 1

                # Sadly many shell interpreters does not
                # allow simple [] because they are expansion tokens
                # in the shell.
                # We bypass this by allowing *, [, {
                # * will "only" fail if files are named accordingly, else
                # it will be passed as-is.
                #       {    [    *
                sep = ['c', 'b', '*']
                failed = True
                while failed and len(sep) > 0:
                    try:
                        ranges = lstranges(strmap(int, value, a_dev.min(), a_dev.max(), sep.pop()))
                        failed = False
                    except:
                        pass
                if failed:
                    print(value)
                    raise ValueError("Could not parse the atomic/orbital ranges")

                # we have only a subset of the orbitals
                orbs = []
                no = 0
                asarrayi = _a.asarrayi
                for atoms in ranges:
                    if isinstance(atoms, list):
                        # this will be
                        #  atoms[0] == atom
                        #  atoms[1] == list of orbitals on the atom
                        if atoms[0] not in a_dev:
                            continue

                        # Get atoms and orbitals
                        ob = geom.a2o(atoms[0] - 1, True)
                        # We normalize for the total number of orbitals
                        # on the requested atoms.
                        # In this way the user can compare directly the DOS
                        # for same atoms with different sets of orbitals and the
                        # total will add up.
                        no += len(ob)
                        ob = ob[asarrayi(atoms[1]) - 1]
                    else:
                        if atoms not in a_dev:
                            continue
                        ob = geom.a2o(atoms - 1, True)
                        no += len(ob)
                    orbs.append(ob)

                if len(orbs) == 0:
                    print('Device atoms:')
                    print('  ', list2str(a_dev))
                    print('Input atoms:')
                    print('  ', value)
                    raise ValueError('Atomic/Orbital requests are not fully included in the device region.')

                # Add one to make the c-index equivalent to the f-index
                orbs = np.concatenate(orbs).flatten()

                # Check that the requested orbitals are all in the device region
                if len(orbs) != len(ns._tbt.o2p(orbs)):
                    # This should in principle never be called because of the
                    # checks above.
                    print('Device atoms:')
                    print('  ', list2str(a_dev))
                    print('Input atoms:')
                    print('  ', value)
                    raise ValueError('Atomic/Orbital requests are not fully included in the device region.')

                ns._Ovalue = value
                ns._Orng = orbs

        p.add_argument('--atom', '-a', type=str, action=AtomRange,
                       help="""Limit orbital resolved quantities to a sub-set of atoms/orbitals: "1-2[3,4]" will yield the 1st and 2nd atom and their 3rd and fourth orbital. Multiple comma-separated specifications are allowed. Note that some shells does not allow [] as text-input (due to expansion), {, [ or * are allowed orbital delimiters.

                       This flag takes effect on all atom/orbital resolved quantities (except BDOS, transmission_bulk) and is reset whenever --plot or --out is called""")

        class DataT(argparse.Action):

            @collect_action
            @ensure_E
            def __call__(self, parser, ns, values, option_string=None):
                e1 = ns._tbt._elec(values[0])
                if e1 not in ns._tbt.elecs:
                    raise ValueError('Electrode: "'+e1+'" cannot be found in the specified file.')
                e2 = ns._tbt._elec(values[1])
                if e2 not in ns._tbt.elecs:
                    if e2.strip() == '.':
                        for e2 in ns._tbt.elecs:
                            if e2 != e1:
                                try: # catches if T isn't calculated
                                    self(parser, ns, [e1, e2], option_string)
                                except:
                                    pass
                        return
                    raise ValueError('Electrode: "'+e2+'" cannot be found in the specified file.')

                # Grab the information
                data = ns._tbt.transmission(e1, e2, kavg=ns._krng)[ns._Erng]
                data.shape = (-1,)
                ns._data.append(data)
                ns._data_header.append('T:{}-{}[G]'.format(e1, e2))
                ns._data_description.append('Column {} is transmission from {} to {}'.format(len(ns._data), e1, e2))
        p.add_argument('-T', '--transmission', nargs=2, metavar=('ELEC1', 'ELEC2'),
                       action=DataT,
                       help='Store the transmission between two electrodes.')

        class DataBT(argparse.Action):

            @collect_action
            @ensure_E
            def __call__(self, parser, ns, value, option_string=None):
                e = ns._tbt._elec(value[0])
                if e not in ns._tbt.elecs:
                    if e.strip() == '.':
                        for e in ns._tbt.elecs:
                            try: # catches if B isn't calculated
                                self(parser, ns, [e], option_string)
                            except:
                                pass
                        return
                    raise ValueError('Electrode: "'+e+'" cannot be found in the specified file.')

                # Grab the information
                data = ns._tbt.transmission_bulk(e, kavg=ns._krng)[ns._Erng]
                data.shape = (-1,)
                ns._data.append(data)
                ns._data_header.append('BT:{}[G]'.format(e))
                ns._data_description.append('Column {} is bulk-transmission'.format(len(ns._data)))
        p.add_argument('-BT', '--transmission-bulk', nargs=1, metavar='ELEC',
                       action=DataBT,
                       help='Store the bulk transmission of an electrode.')

        class DataDOS(argparse.Action):

            @collect_action
            @ensure_E
            def __call__(self, parser, ns, value, option_string=None):
                if not value is None:
                    # we are storing the spectral DOS
                    e = ns._tbt._elec(value)
                    if e not in ns._tbt.elecs:
                        raise ValueError('Electrode: "'+e+'" cannot be found in the specified file.')
                    data = ns._tbt.ADOS(e, kavg=ns._krng, orbital=ns._Orng, norm=ns._norm)
                    ns._data_header.append('ADOS:{}[1/eV]'.format(e))
                else:
                    data = ns._tbt.DOS(kavg=ns._krng, orbital=ns._Orng, norm=ns._norm)
                    ns._data_header.append('DOS[1/eV]')
                NORM = int(ns._tbt.norm(orbital=ns._Orng, norm=ns._norm))

                # The flatten is because when ns._Erng is None, then a new
                # dimension (of size 1) is created
                ns._data.append(data[ns._Erng].flatten())
                if ns._Orng is None:
                    ns._data_description.append('Column {} is sum of all device atoms+orbitals with normalization 1/{}'.format(len(ns._data), NORM))
                else:
                    ns._data_description.append('Column {} is atoms[orbs] {} with normalization 1/{}'.format(len(ns._data), ns._Ovalue, NORM))

        p.add_argument('--dos', '-D', nargs='?', metavar='ELEC',
                       action=DataDOS, default=None,
                       help="""Store the DOS. If no electrode is specified, it is Green function, else it is the spectral function.""")
        p.add_argument('--ados', '-AD', metavar='ELEC',
                       action=DataDOS, default=None,
                       help="""Store the spectral DOS, same as --dos but requires an electrode-argument.""")

        class DataDOSBulk(argparse.Action):

            @collect_action
            @ensure_E
            def __call__(self, parser, ns, value, option_string=None):

                # we are storing the Bulk DOS
                e = ns._tbt._elec(value[0])
                if e not in ns._tbt.elecs:
                    raise ValueError('Electrode: "'+e+'" cannot be found in the specified file.')
                # Grab the information
                data = ns._tbt.BDOS(e, kavg=ns._krng, sum=False)
                ns._data_header.append('BDOS:{}[1/eV]'.format(e))
                # Select the energies, even if _Erng is None, this will work!
                no = data.shape[-1]
                data = np.mean(data[ns._Erng, ...], axis=-1).flatten()
                ns._data.append(data)
                ns._data_description.append('Column {} is sum of all electrode[{}] atoms+orbitals with normalization 1/{}'.format(len(ns._data), e, no))
        p.add_argument('--bulk-dos', '-BD', nargs=1, metavar='ELEC',
                       action=DataDOSBulk, default=None,
                       help="""Store the bulk DOS of an electrode.""")

        class DataTEig(argparse.Action):

            @collect_action
            @ensure_E
            def __call__(self, parser, ns, values, option_string=None):
                e1 = ns._tbt._elec(values[0])
                if e1 not in ns._tbt.elecs:
                    raise ValueError('Electrode: "'+e1+'" cannot be found in the specified file.')
                e2 = ns._tbt._elec(values[1])
                if e2 not in ns._tbt.elecs:
                    if e2.strip() == '.':
                        for e2 in ns._tbt.elecs:
                            if e1 != e2:
                                try: # catches if T-eig isn't calculated
                                    self(parser, ns, [e1, e2], option_string)
                                except:
                                    pass
                        return
                    raise ValueError('Electrode: "'+e2+'" cannot be found in the specified file.')

                # Grab the information
                data = ns._tbt.transmission_eig(e1, e2, kavg=ns._krng)
                # The shape is: E, neig
                neig = data.shape[-1]
                for eig in range(neig):
                    ns._data.append(data[ns._Erng, ..., eig].flatten())
                    ns._data_header.append('Teig({}):{}-{}[G]'.format(eig+1, e1, e2))
                    ns._data_description.append('Column {} is transmission eigenvalues from electrode {} to {}'.format(len(ns._data), e1, e2))
        p.add_argument('--transmission-eig', '-Teig', nargs=2, metavar=('ELEC1', 'ELEC2'),
                       action=DataTEig,
                       help='Store the transmission eigenvalues between two electrodes.')

        class Info(argparse.Action):
            """ Action to print information contained in the TBT.nc file, helpful before performing actions """

            def __call__(self, parser, ns, value, option_string=None):
                # First short-hand the file
                print(ns._tbt.info(value))

        p.add_argument('--info', '-i', action=Info, nargs='?', metavar='ELEC',
                       help='Print out what information is contained in the TBT.nc file, optionally only for one of the electrodes.')

        class Out(argparse.Action):

            @run_actions
            def __call__(self, parser, ns, value, option_string=None):

                out = value[0]

                try:
                    # We figure out if the user wants to write
                    # to a geometry
                    obj = get_sile(out, mode='w')
                    if hasattr(obj, 'write_geometry'):
                        with obj as fh:
                            fh.write_geometry(ns._geometry)
                        return
                    raise NotImplementedError
                except:
                    pass

                if len(ns._data) == 0:
                    # do nothing if data has not been collected
                    print("No data has been collected in the arguments, nothing will be written, have you forgotten arguments?")
                    return

                from sisl.io import TableSile
                TableSile(out, mode='w').write(*ns._data,
                                               comment=ns._data_description,
                                               header=ns._data_header)
                # Clean all data
                ns._data_description = []
                ns._data_header = []
                ns._data = []
                # These are expert options
                ns._norm = 'atom'
                ns._Ovalue = ''
                ns._Orng = None
                ns._Erng = None
                ns._krng = True
        p.add_argument('--out', '-o', nargs=1, action=Out,
                       help='Store the currently collected information (at its current invocation) to the out file.')

        class AVOut(argparse.Action):

            def __call__(self, parser, ns, value, option_string=None):
                ns._tbt.write_tbtav()
        p.add_argument('--tbt-av', action=AVOut, nargs=0,
                       help='Create "{0}" with the k-averaged quantities of this file.'.format(self.file.replace('TBT.nc', 'TBT.AV.nc')))

        class Plot(argparse.Action):

            @run_actions
            def __call__(self, parser, ns, value, option_string=None):

                if len(ns._data) == 0:
                    # do nothing if data has not been collected
                    print("No data has been collected in the arguments, nothing will be plotted, have you forgotten arguments?")
                    return

                from matplotlib import pyplot as plt
                plt.figure()

                for i in range(1, len(ns._data)):
                    plt.plot(ns._data[0], ns._data[i], label=ns._data_header[i])

                plt.legend(loc=8, ncol=3, bbox_to_anchor=(0.5, 1.0))
                if value is None:
                    plt.show()
                else:
                    plt.savefig(value)

                # Clean all data
                ns._data_description = []
                ns._data_header = []
                ns._data = []
                # These are expert options
                ns._norm = 'atom'
                ns._Ovalue = ''
                ns._Orng = None
                ns._Erng = None
                ns._krng = True
        p.add_argument('--plot', '-p', action=Plot, nargs='?', metavar='FILE',
                       help='Plot the currently collected information (at its current invocation).')

        return p, namespace


add_sile('TBT.nc', tbtncSileTBtrans)
# Add spin-dependent files
add_sile('TBT_DN.nc', tbtncSileTBtrans)
add_sile('TBT_UP.nc', tbtncSileTBtrans)


class phtncSileTBtrans(tbtncSileTBtrans):
    """ PHtrans file object """
    _trans_type = 'PHT'

add_sile('PHT.nc', phtncSileTBtrans)


# The average files
# These are essentially equivalent to the TBT.nc files
# with the exception that the k-points have been averaged out.
class tbtavncSileTBtrans(tbtncSileTBtrans):
    """ TBtrans average file object

    This `Sile` implements the writing of the TBtrans output ``*.TBT.AV.nc`` sile which contains
    the k-averaged quantities related to the NEGF code TBtrans.

    See `tbtncSileTBtrans` for details as this object is essentially a copy of it.
    """
    _trans_type = 'TBT'
    _k_avg = True

    @property
    def nkpt(self):
        """ Always return 1, this is to signal other routines """
        return 1

    @property
    def wkpt(self):
        """ Always return [1.], this is to signal other routines """
        return _a.onesd(1)

    def write_tbtav(self, *args, **kwargs):
        """ Wrapper for writing the k-averaged TBT.AV.nc file.

        This write *requires* the TBT.nc `Sile` object passed as the first argument,
        or as the keyword ``from=tbt`` argument.

        Parameters
        ----------
        from : tbtncSileTBtrans
          the TBT.nc file object that has the k-sampled quantities.
        """

        if 'from' in kwargs:
            tbt = kwargs['from']
        elif len(args) > 0:
            tbt = args[0]
        else:
            raise ValueError("tbtncSileTBtrans has not been passed to write the averaged file")

        if not isinstance(tbt, tbtncSileTBtrans):
            raise ValueError('first argument of tbtavncSileTBtrans.write *must* be a tbtncSileTBtrans object')

        # Notify if the object is not in write mode.
        sile_raise_write(self)

        def copy_attr(f, t):
            t.setncatts({att: f.getncattr(att) for att in f.ncattrs()})

        # Retrieve k-weights
        nkpt = len(tbt.dimensions['nkpt'])
        wkpt = _a.asarrayd(tbt.variables['wkpt'][:])

        # First copy and re-create all entries in the output file
        for dvg in tbt:
            # Iterate all:
            #  root,
            #  dimensions,
            #  variables
            #  sub-groups, (start over again)

            # Root group
            if tbt.isDataset(dvg):
                # Copy attributes and continue
                copy_attr(dvg, self)
                continue

            # Ensure the group exists
            if tbt.isGroup(dvg):
                grp = self.createGroup(dvg.path)
                copy_attr(dvg, grp)
                continue

            # Ensure the group exists... (the above case handles groups)
            grp = self.createGroup(dvg.group().path)

            if tbt.isDimension(dvg):

                # In case the dimension is the k-point one
                # we remove that dimension
                if 'nkpt' == dvg.name:
                    continue

                # Simply re-create the dimension
                if dvg.isunlimited():
                    grp.createDimension(dvg.name, None)
                else:
                    grp.createDimension(dvg.name, len(dvg))

                continue

            # It *must* be a variable now

            # Quickly skip the k-point variable and the weights
            if dvg.name in ['kpt', 'wkpt']:
                continue

            # Down-scale the k-point dimension
            if 'nkpt' in dvg.dimensions:
                # Remove that dimension
                dims = list(dvg.dimensions)
                # Create slice
                idx = dims.index('nkpt')
                dims.pop(idx)
                dims = tuple(dims)
                has_kpt = True

            else:
                dims = dvg.dimensions[:]
                has_kpt = False

            v = grp.createVariable(dvg.name, dvg.dtype,
                                   dimensions=dims,
                                   **dvg.filters())

            # Copy attributes
            copy_attr(dvg, v)

            # Copy values
            if has_kpt:
                # Instead of constantly reading-writing to disk
                # (if buffer is too small)
                # we create a temporary array to hold the averaged
                # quantities.
                # This should only be faster for very large variables
                if idx == 0:
                    dat = np.asarray(dvg[0][:] * wkpt[0])
                    for k in range(1, nkpt):
                        dat += dvg[k][:] * wkpt[k]
                    v[:] = dat[:]
                else:
                    for slc in iter_shape(dvg.shape[:idx]):
                        dat = np.asarray(dvg[slc][0][:] * wkpt[0])
                        for k in range(1, nkpt):
                            dat += dvg[slc][k][:] * wkpt[k]
                        v[slc][:] = dat[:]
                del dat
            else:
                v[:] = dvg[:]

        # Update the source attribute to signal the originating file
        self.setncattr('source', 'k-average of: ' + tbt._file)
        self.sync()


add_sile('TBT.AV.nc', tbtavncSileTBtrans)
# Add spin-dependent files
add_sile('TBT_DN.AV.nc', tbtavncSileTBtrans)
add_sile('TBT_UP.AV.nc', tbtavncSileTBtrans)


class phtavncSileTBtrans(tbtavncSileTBtrans):
    """ PHtrans file object """
    _trans_type = 'PHT'

add_sile('PHT.AV.nc', phtavncSileTBtrans)
