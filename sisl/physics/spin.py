# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
import numpy as np

from sisl._internal import set_module
from sisl.messages import deprecate_method


__all__ = ['Spin']


@set_module("sisl.physics")
class Spin:
    r""" Spin class to determine configurations and spin components.

    The basic class `Spin` implements a generic method to determine a spin configuration.

    Its usage can be summarized in these few examples:

    >>> Spin(Spin.UNPOLARIZED) == Spin("unpolarized") == Spin()
    True
    >>> Spin(Spin.POLARIZED) == Spin("polarized") == Spin("p")
    True
    >>> Spin(Spin.NONCOLINEAR, dtype=np.complex128) == Spin("non-collinear") == Spin("nc")
    True
    >>> Spin(Spin.SPINORBIT, dtype=np.complex128) == Spin("spin-orbit") == Spin("so") == Spin("soc")
    True

    Note that a data-type may be associated with a spin-object. This is not to say
    that the data-type is used in the configuration, but merely that it helps
    any sub-classed or classes who use the spin-object to determine the
    usage of the different spin-components.

    Parameters
    ----------
    kind : str or int, Spin, optional
       specify the spin kind
    dtype : numpy.dtype, optional
       the data-type used for the spin-component. Default is ``np.float64``
    """

    #: Constant for an un-polarized spin configuration
    UNPOLARIZED = 0
    #: Constant for a polarized spin configuration
    POLARIZED = 1
    #: Constant for a non-collinear spin configuration
    NONCOLINEAR = 2
    #: Constant for a spin-orbit spin configuration
    SPINORBIT = 3

    #: The :math:`\boldsymbol\sigma_x` Pauli matrix
    X = np.array([[0, 1], [1, 0]], np.complex128)
    #: The :math:`\boldsymbol\sigma_y` Pauli matrix
    Y = np.array([[0, -1j], [1j, 0]], np.complex128)
    #: The :math:`\boldsymbol\sigma_z` Pauli matrix
    Z = np.array([[1, 0], [0, -1]], np.complex128)

    __slots__ = ("_size", "_kind", "_dtype")

    def __init__(self, kind="", dtype=None):

        if isinstance(kind, Spin):
            if dtype is None:
                dtype = kind._dtype
            self._kind = kind._kind
            self._dtype = dtype
            self._size = kind._size
            return

        if dtype is None:
            dtype = np.float64

        # Copy data-type
        self._dtype = dtype

        if isinstance(kind, str):
            kind = kind.lower()

        kind = {"unpolarized": Spin.UNPOLARIZED, "": Spin.UNPOLARIZED,
                Spin.UNPOLARIZED: Spin.UNPOLARIZED,
                "polarized": Spin.POLARIZED, "p": Spin.POLARIZED,
                "pol": Spin.POLARIZED,
                Spin.POLARIZED: Spin.POLARIZED,
                "noncolinear": Spin.NONCOLINEAR,
                "noncollinear": Spin.NONCOLINEAR,
                "non-colinear": Spin.NONCOLINEAR,
                "non-collinear": Spin.NONCOLINEAR, "nc": Spin.NONCOLINEAR,
                Spin.NONCOLINEAR: Spin.NONCOLINEAR,
                "spinorbit": Spin.SPINORBIT,
                "spin-orbit": Spin.SPINORBIT, "so": Spin.SPINORBIT,
                "soc": Spin.SPINORBIT, Spin.SPINORBIT: Spin.SPINORBIT}.get(kind)
        if kind is None:
            raise ValueError(f"{self.__class__.__name__} initialization went wrong because of wrong "
                             "kind specification. Could not determine the kind of spin!")

        # Now assert the checks
        self._kind = kind

        if np.dtype(dtype).kind == "c":
            size = {self.UNPOLARIZED: 1,
                     self.POLARIZED: 2,
                     self.NONCOLINEAR: 4,
                     self.SPINORBIT: 4}.get(kind)

        else:
            size = {self.UNPOLARIZED: 1,
                     self.POLARIZED: 2,
                     self.NONCOLINEAR: 4,
                     self.SPINORBIT: 8}.get(kind)

        self._size = size

    def __str__(self):
        if self.is_unpolarized:
            return f"{self.__class__.__name__}{{unpolarized, kind={self.dkind}}}"
        if self.is_polarized:
            return f"{self.__class__.__name__}{{polarized, kind={self.dkind}}}"
        if self.is_noncolinear:
            return f"{self.__class__.__name__}{{non-colinear, kind={self.dkind}}}"
        return f"{self.__class__.__name__}{{spin-orbit, kind={self.dkind}}}"

    def copy(self):
        """ Create a copy of the spin-object """
        return Spin(self.kind, self.dtype)

    @property
    def dtype(self):
        """ Data-type of the spin configuration """
        return self._dtype

    @property
    def dkind(self):
        """ Data-type kind """
        return np.dtype(self._dtype).kind

    @property
    def size(self):
        """ Number of elements to describe the spin-components """
        return self._size

    @property
    @deprecate_method("Use Spin.size instead")
    def spins(self):
        """ Number of elements to describe the spin-components """
        return self._size

    @property
    def spinor(self):
        """ Number of spinor components (1 or 2) """
        return min(2, self._size)

    @property
    def kind(self):
        """ A unique ID for the kind of spin configuration """
        return self._kind

    @property
    def is_unpolarized(self):
        """ True if the configuration is not polarized """
        # Regardless of data-type
        return self.kind == Spin.UNPOLARIZED

    @property
    def is_polarized(self):
        """ True if the configuration is polarized """
        return self.kind == Spin.POLARIZED

    is_colinear = is_polarized

    @property
    def is_noncolinear(self):
        """ True if the configuration non-collinear """
        return self.kind == Spin.NONCOLINEAR

    @property
    def is_diagonal(self):
        """ Whether the spin-box is only using the diagonal components

        This will return true for non-polarized and polarized spin configurations.
        Otherwise false.
        """
        return self.kind in (Spin.UNPOLARIZED, Spin.POLARIZED)

    @property
    @deprecate_method("Use 'not Spin.is_diagonal' instead")
    def has_noncolinear(self):
        """ True if the configuration is non-collinear or spin-orbit """
        return self.kind >= Spin.NONCOLINEAR

    @property
    def is_spinorbit(self):
        """ True if the configuration is spin-orbit """
        return self.kind == Spin.SPINORBIT

    def __len__(self):
        return self._size

    # Comparisons
    def __lt__(self, other):
        return self.kind < other.kind

    def __le__(self, other):
        return self.kind <= other.kind

    def __eq__(self, other):
        return self.kind == other.kind

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        return self.kind > other.kind

    def __ge__(self, other):
        return self.kind >= other.kind

    def __getstate__(self):
        return {
            "size": self.size,
            "kind": self.kind,
            "dtype": self.dtype
        }

    def __setstate__(self, state):
        self._size = state["size"]
        self._kind = state["kind"]
        self._dtype = state["dtype"]
