from htmd.projections.projection import Projection
from htmd.molecule.molecule import Molecule

import logging
import numpy
import subprocess
import shutil
import os
import tempfile

logger = logging.getLogger(__name__)


def _getTempDirName(prefix=""):
    return os.path.join(tempfile._get_default_tempdir(),
                        prefix + next(tempfile._get_candidate_names()))


# Assumptions: file begins with #! FIELDS time
# first line is time
# only colvars follow
def _readColvar(colvar):
    data = []
    with open(colvar, "r") as file:
        headerline = file.readline()
        cvnames = headerline.strip().replace('#! FIELDS time ', '').split()

        for line in file:
            if line[0] == "#":
                continue
            cols_str = line.split()[1:]
            cols = [float(x) for x in cols_str]
            data.append(cols)
    return numpy.array(data)


class PlumedGroup():
    """ An atom group for use in the Plumed interface

    Parameters
    ----------
    mol: Molecule
        The molecule
    sel: str
        The atom selection defining the group
    """

    def __init__(self, label, mol, sel):
        al = mol.get("serial", sel)
        al = list(al)
        self.label = label
        self.mol = mol
        self.sel = sel
        self.code = "%s: GROUP ATOMS=%s" % (label, ",".join(map(str, al)))

    def __repr__(self):
        return self.code


class MetricPlumed2(Projection):
    """ Calculates generic collective variables through Plumed 2

    The collective variables are defined in PLUMED 2's syntax. PLUMED needs be installed
    separately; see http://www.plumed.org/.

    Parameters
    ----------
    plumed_inp_str: string
        The PLUMED script defining CVs - a string or a list of strings (which are concatenated)

    Example
    -------
    >>> dd = htmd.home(dataDir="adaptive")
    >>> fsims = htmd.simlist([dd + '/data/e1s1_1/', dd + '/data/e1s2_1/'],
    >>>                       dd + '/generators/1/structure.pdb')
    >>> metr = htmd.projections.metric.Metric(fsims)
    >>> metr.projection(MetricPlumed2(
    >>>     ['d1: DISTANCE ATOMS=2,3',
    >>>      'd2: DISTANCE ATOMS=5,6']))
    >>> data2 = metr.project()

    """

    def __init__(self, plumed_inp_str):
        # I am not sure at all about opening files here is good style
        self._precalculation_enabled = False
        self._plumed_exe = shutil.which("plumed")

        if not isinstance(plumed_inp_str, str):
            plumed_inp_str = "\n".join(plumed_inp_str)
        self._plumed_inp = plumed_inp_str

    # Only called if single topology
    def _precalculate(self, mol):
        logger.info("In _precalculate")
        self._precalculation_enabled = True

    def getMapping(self, mol):
        # Useful?
        return

    # Arguments are actually self, mol
    def project(self, mol):
        """ Project molecule.

        Parameters
        ------------
        mol : :class:`Molecule <htmd.molecule.molecule.Molecule>`
            A :class:`Molecule <htmd.molecule.molecule.Molecule>` object to project.

        Returns
        -------
        data : np.ndarray
            An array containing the projected data.
        """

        logger.info("_precalculate was called? %d" % self._precalculation_enabled)

        # --standalone-executable driver --box 100000,100000,100000 --mf_dcd /var/tmp/vmdplumed.8003/temp.dcd
        # --pdb /var/tmp/vmdplumed.8003/temp.pdb --plumed /var/tmp/vmdplumed.8003/META_INP

        td = _getTempDirName("metricplumed2-")
        os.mkdir(td)

        # PDB
        pdb = os.path.join(td, "temp.pdb")
        mol.write(pdb)

        # DCD
        dcd = os.path.join(td, "temp.dcd")
        mol.write(dcd)
        logger.info("Done writing %d frames in %s" % (mol.numFrames, dcd))

        # Colvar
        colvar = os.path.join(td, "temp.colvar")
        logger.info("Colvar file is " + colvar)

        # Metainp
        metainp = os.path.join(td, "temp.metainp")
        metainp_fp = open(metainp, "w+")
        metainp_fp.write("UNITS  LENGTH=A  ENERGY=kcal/mol  TIME=ps\n")
        metainp_fp.write(self._plumed_inp)
        metainp_fp.write('\nPRINT ARG=* FILE=%s\n# FLUSH STRIDE=1\n' % colvar)
        metainp_fp.close()

        cmd = [self._plumed_exe, '--standalone-executable',
               'driver',
               '--mf_dcd', dcd,
               '--pdb', pdb,
               '--plumed', metainp]
        logger.info("Invoking " + " ".join(cmd))
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            logger.error("Error from PLUMED (stdout): " + e.stdout.decode("utf-8"))
            logger.error("Error from PLUMED (stderr):" + e.stderr.decode("utf-8"))
            logger.error("Leaving temporary data in " + td)
            raise e

        data = _readColvar(colvar)
        shutil.rmtree(td)

        return data


if __name__ == "__main__":
    import numpy as np
    import htmd
    from htmd.projections.metricplumed2 import MetricPlumed2

    import doctest
    doctest.testmod()

    # One simulation
    mol = Molecule(os.path.join(htmd.home(), 'data', '1kdx', '1kdx_0.pdb'))
    mol.read(os.path.join(htmd.home(), 'data', '1kdx', '1kdx.dcd'))

    metric = MetricPlumed2(['d1: DISTANCE ATOMS=1,200',
                            'd2: DISTANCE ATOMS=5,6'])
#    metric = MetricPlumed2([''])
    data = metric.project(mol)
    ref = np.array([0.536674, 21.722393, 22.689391, 18.402114, 23.431387, 23.13392, 19.16376, 20.393544,
                    23.665517, 22.298349, 22.659769, 22.667669, 22.484084, 20.893447, 18.791701,
                    21.833056, 19.901318])
    assert np.all(np.abs(ref - data[:, 0]) < 0.01), 'Plumed demo calculation is broken'

    # Simlist
    # datadirs=glob(os.path.join(home(), 'data', 'adaptive', 'data', '*' )
    # fsims=simlist(glob(os.path.join(home(), 'data', 'adaptive', 'data', '*', '/')),
    #              os.path.join(home(), 'data', 'adaptive', 'generators', '1','structure.pdb'))


