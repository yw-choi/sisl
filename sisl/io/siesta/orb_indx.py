# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
from .sile import SileSiesta
from ..sile import add_sile, sile_fh_open

from sisl._internal import set_module
from sisl import Orbital, AtomicOrbital
from sisl import PeriodicTable, Atom, Atoms
from sisl._array import arrayi
from sisl.unit.siesta import unit_convert


__all__ = ['orbindxSileSiesta']


Bohr2Ang = unit_convert('Bohr', 'Ang')


@set_module("sisl.io.siesta")
class orbindxSileSiesta(SileSiesta):
    """ Orbital information file """

    @sile_fh_open()
    def read_supercell_nsc(self):
        """ Reads the supercell number of supercell information """
        # First line contains no no_s
        line = self.readline().split()
        no_s = int(line[1])
        self.readline()
        self.readline()
        nsc = [0] * 3

        def int_abs(i):
            return abs(int(i))

        for _ in range(no_s):
            line = self.readline().split()
            isc = list(map(int_abs, line[12:15]))
            if isc[0] > nsc[0]:
                nsc[0] = isc[0]
            if isc[1] > nsc[1]:
                nsc[1] = isc[1]
            if isc[2] > nsc[2]:
                nsc[2] = isc[2]

        return arrayi([n * 2 + 1 for n in nsc])

    @sile_fh_open()
    def read_basis(self, atoms=None):
        """ Returns a set of atoms corresponding to the basis-sets in the ORB_INDX file

        The specie names have a short field in the ORB_INDX file, hence the name may
        not necessarily be the same as provided in the species block

        Parameters
        ----------
        atoms : Atoms, optional
           list of atoms used for the species index
        """

        # First line contains no no_s
        line = self.readline().split()
        no = int(line[0])
        self.readline()
        self.readline()

        pt = PeriodicTable()

        def crt_atom(i_s, spec, orbs):
            if atoms is None:
                # The user has not specified an atomic basis
                i = pt.Z(spec)
                if isinstance(i, int):
                    return Atom(i, orbs)
                else:
                    return Atom(-1, orbs, tag=spec)
            # Get the atom and add the orbitals
            return atoms[i_s].copy(orbitals=orbs)

        # Now we begin by reading the atoms
        atom = []
        orbs = []
        specs = []
        ia = 1
        i_s = 0
        for _ in range(no):
            line = self.readline().split()

            i_a = int(line[1])
            spec = line[3]
            if i_a != ia:
                if i_s not in specs:
                    atom.append(crt_atom(i_s, spec, orbs))
                specs.append(i_s)
                ia = i_a
                orbs = []

            i_s = int(line[2]) - 1

            if i_s in specs:
                continue
            nlmz = list(map(int, line[5:9]))
            P = line[9] == 'T'
            rc = float(line[11]) * Bohr2Ang
            # Create the orbital
            o = AtomicOrbital(n=nlmz[0], l=nlmz[1], m=nlmz[2], zeta=nlmz[3], P=P, R=rc)
            orbs.append(o)

        if i_s not in specs:
            atom.append(crt_atom(i_s, spec, orbs))
        specs.append(i_s)

        # Now re-arrange the atoms and create the Atoms object
        return Atoms([atom[i] for i in specs])


add_sile('ORB_INDX', orbindxSileSiesta, gzip=True)
